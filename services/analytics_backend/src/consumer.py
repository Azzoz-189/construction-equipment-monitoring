"""
Kafka Consumer for Equipment Analytics.

This module provides a consumer that reads equipment events from Kafka
and persists them to the PostgreSQL database.
"""

import json
import logging
import signal
import threading
import time
from typing import Optional, List, Dict, Any

from confluent_kafka import Consumer, KafkaError, KafkaException
from sqlalchemy.engine import Engine

from .db_models import EquipmentEvent, get_session

logger = logging.getLogger(__name__)


class AnalyticsConsumer:
    """
    Kafka consumer for equipment analytics events.
    
    Consumes messages from the equipment-events topic, parses the JSON payload,
    and inserts records into the PostgreSQL database with batch optimization.
    """
    
    # Batch configuration
    BATCH_SIZE = 100  # Commit every N messages
    BATCH_TIMEOUT = 5.0  # Or every T seconds
    
    def __init__(self, kafka_config: dict, db_uri: str, engine: Optional[Engine] = None):
        """
        Initialize Kafka consumer and database connection.
        
        Args:
            kafka_config: Kafka configuration dictionary containing:
                - bootstrap_servers: Kafka broker addresses
                - topic: Topic to consume from
                - consumer_group: Consumer group ID
            db_uri: PostgreSQL connection URI
            engine: Optional pre-existing SQLAlchemy engine
        """
        self._running = False
        self._consumer: Optional[Consumer] = None
        self._topic = kafka_config.get("topic", "equipment-events")
        
        # Set up Kafka consumer configuration
        self._kafka_conf = {
            "bootstrap.servers": kafka_config.get("bootstrap_servers", "kafka:9092"),
            "group.id": kafka_config.get("consumer_group", "analytics-consumer"),
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,  # Manual commit for better control
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": 30000,
        }
        
        # Database setup
        if engine is not None:
            self._engine = engine
        else:
            from .db_models import init_db
            self._engine = init_db(db_uri)
        
        self._SessionLocal = get_session(self._engine)
        
        # Batch processing state
        self._batch: List[EquipmentEvent] = []
        self._last_commit_time = time.time()
        
        # Thread for running consumer
        self._thread: Optional[threading.Thread] = None
        
        logger.info(f"AnalyticsConsumer initialized for topic: {self._topic}")
    
    def start(self, blocking: bool = True) -> None:
        """
        Start consuming messages.
        
        Args:
            blocking: If True, runs in current thread. If False, spawns a background thread.
        """
        if blocking:
            self._run_consumer()
        else:
            self._thread = threading.Thread(target=self._run_consumer, daemon=True)
            self._thread.start()
            logger.info("Consumer started in background thread")
    
    def _run_consumer(self) -> None:
        """Main consumer loop."""
        self._running = True
        self._consumer = Consumer(self._kafka_conf)
        
        try:
            self._consumer.subscribe([self._topic])
            logger.info(f"Subscribed to topic: {self._topic}")
            
            while self._running:
                msg = self._consumer.poll(timeout=1.0)
                
                if msg is None:
                    # No message received, check if we need to flush batch
                    self._check_batch_timeout()
                    continue
                
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        # End of partition, not an error
                        logger.debug(
                            f"Reached end of partition {msg.partition()} at offset {msg.offset()}"
                        )
                    elif msg.error().code() == KafkaError.UNKNOWN_TOPIC_OR_PART:
                        logger.warning(f"Topic {self._topic} not found, waiting...")
                        time.sleep(5)
                    else:
                        logger.error(f"Kafka error: {msg.error()}")
                    continue
                
                # Process the message
                try:
                    value = msg.value()
                    if value is not None:
                        message_data = json.loads(value.decode("utf-8"))
                        self.process_message(message_data)
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to decode JSON message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                
        except KafkaException as e:
            logger.error(f"Kafka exception: {e}")
        finally:
            # Flush any remaining batch
            self._flush_batch()
            if self._consumer:
                self._consumer.close()
            logger.info("Consumer stopped")
    
    def process_message(self, message: dict) -> None:
        """
        Parse Kafka message JSON and add to batch for database insertion.
        
        Expected message structure:
        {
            "frame_id": int,
            "equipment_id": str,
            "equipment_class": str,
            "timestamp": str,
            "current_state": str,
            "current_activity": str,
            "motion": {
                "source": str,
                ...
            },
            "utilization": {
                "utilization_percent": float
            },
            "time_analytics": {
                "total_tracked_seconds": float,
                "total_active_seconds": float,
                "total_idle_seconds": float
            }
        }
        
        Args:
            message: Parsed JSON message from Kafka
        """
        try:
            # Extract nested fields
            utilization = message.get("utilization", {})
            time_analytics = message.get("time_analytics", {})
            
            # Create database record
            event = EquipmentEvent(
                frame_id=message.get("frame_id", 0),
                equipment_id=message.get("equipment_id", "UNKNOWN"),
                equipment_class=message.get("equipment_class", "unknown"),
                timestamp=message.get("timestamp", "00:00:00.000"),
                current_state=utilization.get("current_state", "UNKNOWN"),
                current_activity=utilization.get("current_activity", "UNKNOWN"),
                motion_source=utilization.get("motion_source", "none"),
                total_tracked_seconds=time_analytics.get("total_tracked_seconds", 0.0),
                total_active_seconds=time_analytics.get("total_active_seconds", 0.0),
                total_idle_seconds=time_analytics.get("total_idle_seconds", 0.0),
                utilization_percent=time_analytics.get("utilization_percent", 0.0),
                video_source=message.get("video_source"),
            )
            
            self._batch.append(event)
            
            # Check if we should commit batch
            if len(self._batch) >= self.BATCH_SIZE:
                self._flush_batch()
                
        except Exception as e:
            logger.error(f"Error creating event record: {e}, message: {message}")
    
    def _check_batch_timeout(self) -> None:
        """Check if batch should be flushed due to timeout."""
        if self._batch and (time.time() - self._last_commit_time) >= self.BATCH_TIMEOUT:
            self._flush_batch()
    
    def _flush_batch(self) -> None:
        """Flush the current batch to the database."""
        if not self._batch:
            return
        
        session = self._SessionLocal()
        try:
            session.bulk_save_objects(self._batch)
            session.commit()
            
            logger.debug(f"Committed batch of {len(self._batch)} records")
            
            # Commit Kafka offsets after successful DB write
            if self._consumer:
                self._consumer.commit(asynchronous=False)
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to commit batch: {e}")
        finally:
            session.close()
            self._batch = []
            self._last_commit_time = time.time()
    
    def stop(self) -> None:
        """Graceful shutdown of the consumer."""
        logger.info("Stopping consumer...")
        self._running = False
        
        # Wait for thread to finish if running in background
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        
        logger.info("Consumer shutdown complete")
    
    def is_running(self) -> bool:
        """Check if consumer is currently running."""
        return self._running


def create_consumer_with_signals(kafka_config: dict, db_uri: str, engine: Optional[Engine] = None) -> AnalyticsConsumer:
    """
    Create a consumer with signal handlers for graceful shutdown.
    
    Args:
        kafka_config: Kafka configuration dictionary
        db_uri: PostgreSQL connection URI
        engine: Optional pre-existing SQLAlchemy engine
        
    Returns:
        Configured AnalyticsConsumer instance
    """
    consumer = AnalyticsConsumer(kafka_config, db_uri, engine)
    
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        consumer.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    return consumer
