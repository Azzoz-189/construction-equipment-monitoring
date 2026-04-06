"""
Database Models for Equipment Analytics.

This module defines SQLAlchemy models for storing equipment events
and provides database initialization functions with optional TimescaleDB support.
"""

import datetime
import logging
from typing import Optional

from sqlalchemy import Column, Integer, String, Float, DateTime, create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

Base = declarative_base()


class EquipmentEvent(Base):
    """
    Model for storing equipment tracking events.
    
    Each record represents a point-in-time snapshot of an equipment's state,
    activity, and utilization metrics as detected by the CV service.
    """
    __tablename__ = "equipment_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    frame_id = Column(Integer, nullable=False)
    equipment_id = Column(String(20), nullable=False, index=True)
    equipment_class = Column(String(50), nullable=False)
    timestamp = Column(String(20), nullable=False)  # Video timestamp "HH:MM:SS.mmm"
    current_state = Column(String(10), nullable=False)  # ACTIVE/INACTIVE
    current_activity = Column(String(30), nullable=False)  # DIGGING/SWINGING_LOADING/DUMPING/WAITING
    motion_source = Column(String(20), nullable=False)  # full_body/arm_only/none
    total_tracked_seconds = Column(Float, default=0.0)
    total_active_seconds = Column(Float, default=0.0)
    total_idle_seconds = Column(Float, default=0.0)
    utilization_percent = Column(Float, default=0.0)
    total_idle_dwell_seconds = Column(Float, default=0.0)
    current_idle_streak_seconds = Column(Float, default=0.0)
    times_re_identified = Column(Integer, default=0)
    video_source = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    def __repr__(self) -> str:
        return (
            f"<EquipmentEvent(id={self.id}, equipment_id='{self.equipment_id}', "
            f"state='{self.current_state}', activity='{self.current_activity}')>"
        )
    
    def to_dict(self) -> dict:
        """Convert model instance to dictionary."""
        return {
            "id": self.id,
            "frame_id": self.frame_id,
            "equipment_id": self.equipment_id,
            "equipment_class": self.equipment_class,
            "timestamp": self.timestamp,
            "current_state": self.current_state,
            "current_activity": self.current_activity,
            "motion_source": self.motion_source,
            "total_tracked_seconds": self.total_tracked_seconds,
            "total_active_seconds": self.total_active_seconds,
            "total_idle_seconds": self.total_idle_seconds,
            "utilization_percent": self.utilization_percent,
            "total_idle_dwell_seconds": self.total_idle_dwell_seconds,
            "current_idle_streak_seconds": self.current_idle_streak_seconds,
            "times_re_identified": self.times_re_identified,
            "video_source": self.video_source,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


def init_db(db_uri: str) -> Engine:
    """
    Initialize the database connection and create tables.
    
    This function creates all tables defined in the Base metadata and
    optionally sets up TimescaleDB hypertable for time-series optimization.
    
    Args:
        db_uri: PostgreSQL connection URI
        
    Returns:
        SQLAlchemy Engine instance
    """
    logger.info(f"Initializing database connection...")
    
    engine = create_engine(
        db_uri,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False
    )
    
    # Drop and recreate tables to handle schema changes (prototype)
    Base.metadata.drop_all(engine)
    logger.info("Dropped existing tables for schema migration")
    
    # Create all tables
    Base.metadata.create_all(engine)
    logger.info("Database tables created successfully")
    
    # Attempt to create TimescaleDB hypertable for time-series optimization
    _setup_timescaledb(engine)
    
    return engine


def _setup_timescaledb(engine: Engine) -> None:
    """
    Attempt to set up TimescaleDB hypertable on the equipment_events table.
    
    This is wrapped in try/except since TimescaleDB extension may not be
    available in basic PostgreSQL installations.
    
    Args:
        engine: SQLAlchemy Engine instance
    """
    try:
        with engine.connect() as conn:
            # Check if TimescaleDB extension is available
            result = conn.execute(text(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')"
            ))
            timescale_exists = result.scalar()
            
            if not timescale_exists:
                # Try to create the extension
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
                conn.commit()
                logger.info("TimescaleDB extension created")
            
            # Check if table is already a hypertable
            result = conn.execute(text("""
                SELECT EXISTS(
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'equipment_events'
                )
            """))
            is_hypertable = result.scalar()
            
            if not is_hypertable:
                # Convert to hypertable
                conn.execute(text("""
                    SELECT create_hypertable(
                        'equipment_events', 
                        'created_at',
                        if_not_exists => TRUE,
                        migrate_data => TRUE
                    )
                """))
                conn.commit()
                logger.info("TimescaleDB hypertable created on equipment_events.created_at")
            else:
                logger.info("Table is already a TimescaleDB hypertable")
                
    except Exception as e:
        logger.warning(
            f"TimescaleDB setup skipped (extension may not be available): {e}"
        )
        logger.info("Continuing with standard PostgreSQL tables")


def get_session(engine: Engine) -> sessionmaker:
    """
    Create a sessionmaker bound to the given engine.
    
    Args:
        engine: SQLAlchemy Engine instance
        
    Returns:
        Configured sessionmaker class
    """
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db_session(engine: Engine):
    """
    Context manager for database sessions with automatic cleanup.
    
    Args:
        engine: SQLAlchemy Engine instance
        
    Yields:
        Database session
    """
    SessionLocal = get_session(engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
