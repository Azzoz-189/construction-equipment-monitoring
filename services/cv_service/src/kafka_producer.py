"""
Kafka Producer for Equipment Events.

Publishes equipment utilization and activity events to Kafka for downstream
analytics processing. Uses confluent-kafka for optimal CPU performance.
"""

import json
import logging
from typing import Optional, Callable

from confluent_kafka import Producer, KafkaError, KafkaException

logger = logging.getLogger(__name__)


class EquipmentKafkaProducer:
    """
    Kafka producer for publishing equipment utilization events.
    
    Handles serialization, partitioning by equipment_id, and delivery
    confirmation with error handling.
    """
    
    def __init__(self, config: dict):
        """
        Initialize Kafka producer.
        
        Args:
            config: Kafka configuration dictionary with keys:
                - bootstrap_servers: Kafka broker addresses
                - topic: Target topic name
                - client_id: Producer client identifier
        """
        self._topic = config.get("topic", "equipment-events")
        self._bootstrap_servers = config.get("bootstrap_servers", "localhost:9092")
        self._client_id = config.get("client_id", "cv-service-producer")
        
        # Producer configuration for reliability and performance
        producer_config = {
            "bootstrap.servers": self._bootstrap_servers,
            "client.id": self._client_id,
            # Delivery settings
            "acks": "all",  # Wait for all replicas
            "retries": 3,
            "retry.backoff.ms": 100,
            # Performance tuning
            "linger.ms": 5,  # Small batching delay
            "batch.size": 16384,
            # Connection settings
            "socket.timeout.ms": 30000,
            "request.timeout.ms": 30000,
        }
        
        self._producer: Optional[Producer] = None
        self._connected = False
        self._pending_count = 0
        
        try:
            self._producer = Producer(producer_config)
            self._connected = True
            logger.info(
                f"Kafka producer initialized - servers: {self._bootstrap_servers}, "
                f"topic: {self._topic}"
            )
        except KafkaException as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise
    
    def _delivery_callback(self, err: Optional[KafkaError], msg) -> None:
        """
        Callback invoked on message delivery or failure.
        
        Args:
            err: Error if delivery failed, None on success
            msg: The message that was delivered or failed
        """
        self._pending_count = max(0, self._pending_count - 1)
        
        if err is not None:
            logger.error(
                f"Message delivery failed: {err.str()} - "
                f"topic: {msg.topic()}, key: {msg.key()}"
            )
        else:
            logger.debug(
                f"Message delivered - topic: {msg.topic()}, "
                f"partition: {msg.partition()}, offset: {msg.offset()}"
            )
    
    def publish(self, event: dict) -> None:
        """
        Publish an equipment event to Kafka.
        
        Event schema:
        {
            "frame_id": int,
            "equipment_id": str,
            "equipment_class": str,
            "timestamp": str,  # "HH:MM:SS.mmm"
            "utilization": {
                "current_state": str,      # "ACTIVE" or "INACTIVE"
                "current_activity": str,   # Activity type
                "motion_source": str       # Motion detection source
            },
            "time_analytics": {
                "total_tracked_seconds": float,
                "total_active_seconds": float,
                "total_idle_seconds": float,
                "utilization_percent": float
            }
        }
        
        Args:
            event: Equipment event dictionary matching the schema
        
        Raises:
            ValueError: If event is missing required fields
            RuntimeError: If producer is not connected
        """
        if not self._connected or self._producer is None:
            logger.warning("Kafka producer not connected, skipping publish")
            return
        
        # Validate required fields
        required_fields = ["frame_id", "equipment_id", "equipment_class", "timestamp"]
        missing = [f for f in required_fields if f not in event]
        if missing:
            raise ValueError(f"Event missing required fields: {missing}")
        
        # Use equipment_id as partition key for ordering
        key = event["equipment_id"]
        
        try:
            # Serialize event to JSON
            value = json.dumps(event, default=str).encode("utf-8")
            key_bytes = key.encode("utf-8") if key else None
            
            # Produce message asynchronously
            self._producer.produce(
                topic=self._topic,
                key=key_bytes,
                value=value,
                callback=self._delivery_callback
            )
            self._pending_count += 1
            
            # Trigger delivery callbacks without blocking
            self._producer.poll(0)
            
            logger.debug(f"Event queued for equipment {key}, frame {event['frame_id']}")
            
        except BufferError:
            # Local queue is full, wait for some deliveries
            logger.warning("Producer buffer full, flushing...")
            self._producer.poll(1.0)
            # Retry once
            self._producer.produce(
                topic=self._topic,
                key=key_bytes,
                value=value,
                callback=self._delivery_callback
            )
            self._pending_count += 1
            
        except KafkaException as e:
            logger.error(f"Failed to publish event: {e}")
            raise
    
    def flush(self, timeout: float = 10.0) -> int:
        """
        Flush any pending messages to Kafka.
        
        Blocks until all messages are delivered or timeout expires.
        
        Args:
            timeout: Maximum time to wait in seconds
        
        Returns:
            Number of messages still in queue after flush
        """
        if self._producer is None:
            return 0
        
        remaining = self._producer.flush(timeout)
        if remaining > 0:
            logger.warning(f"{remaining} messages still pending after flush timeout")
        else:
            logger.debug("All messages flushed successfully")
        
        return remaining
    
    def close(self) -> None:
        """
        Clean up producer resources.
        
        Flushes pending messages and closes the producer connection.
        """
        if self._producer is not None:
            logger.info("Closing Kafka producer...")
            # Flush with generous timeout
            remaining = self.flush(timeout=30.0)
            if remaining > 0:
                logger.warning(f"Closing with {remaining} undelivered messages")
            
            self._producer = None
            self._connected = False
            logger.info("Kafka producer closed")
    
    @property
    def is_connected(self) -> bool:
        """Check if producer is connected."""
        return self._connected
    
    @property
    def pending_messages(self) -> int:
        """Get approximate count of pending messages."""
        return self._pending_count
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.close()
        return False
