"""
Analytics Backend Entrypoint.

Runs Kafka consumer in a background thread and FastAPI server in the main thread.
Handles graceful shutdown on SIGTERM/SIGINT signals.
"""

import logging
import os
import signal
import sys
import threading
from pathlib import Path

import yaml
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def load_config(config_path: str = None) -> dict:
    """
    Load configuration from YAML file.
    
    Args:
        config_path: Path to configuration file. If None, uses default paths.
        
    Returns:
        Configuration dictionary
    """
    if config_path is None:
        # Try multiple possible config paths
        possible_paths = [
            Path("/app/config/settings.yaml"),  # Docker path
            Path("config/settings.yaml"),  # Local relative path
            Path(__file__).parent.parent.parent.parent / "config" / "settings.yaml",  # From src
        ]
        
        for path in possible_paths:
            if path.exists():
                config_path = str(path)
                break
        else:
            raise FileNotFoundError(
                f"Config file not found. Tried: {[str(p) for p in possible_paths]}"
            )
    
    logger.info(f"Loading configuration from: {config_path}")
    
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    
    return config


def main():
    """
    Main entrypoint for the analytics backend service.
    
    Initializes database, starts Kafka consumer in background thread,
    and runs FastAPI server in the main thread.
    """
    logger.info("=" * 60)
    logger.info("Starting Equipment Analytics Backend Service")
    logger.info("=" * 60)
    
    # Load configuration
    try:
        config = load_config()
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    kafka_config = config.get("kafka", {})
    db_config = config.get("database", {})
    db_uri = db_config.get("uri", "postgresql://postgres:postgres@postgres:5432/equipment_analytics")
    
    logger.info(f"Kafka bootstrap servers: {kafka_config.get('bootstrap_servers')}")
    logger.info(f"Kafka topic: {kafka_config.get('topic')}")
    logger.info(f"Database host: {db_config.get('host')}")
    
    # Initialize database
    from .db_models import init_db
    from .api import app, set_engine
    from .consumer import AnalyticsConsumer
    
    logger.info("Initializing database...")
    try:
        engine = init_db(db_uri)
        set_engine(engine)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        sys.exit(1)
    
    # Create Kafka consumer
    consumer = AnalyticsConsumer(kafka_config, db_uri, engine)
    
    # Shutdown event for coordinating graceful shutdown
    shutdown_event = threading.Event()
    
    def signal_handler(signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        shutdown_event.set()
        consumer.stop()
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Start Kafka consumer in background thread
    logger.info("Starting Kafka consumer in background thread...")
    consumer.start(blocking=False)
    
    # Configure uvicorn with enough concurrency for MJPEG streams + API
    uvicorn_config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        access_log=True,
        timeout_keep_alive=65,
        limit_concurrency=50,
    )
    
    # Start FastAPI server
    logger.info("Starting FastAPI server on port 8000...")
    server = uvicorn.Server(uvicorn_config)
    
    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        logger.info("Shutting down services...")
        consumer.stop()
        logger.info("Analytics Backend Service stopped")


if __name__ == "__main__":
    main()
