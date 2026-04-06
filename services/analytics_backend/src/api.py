"""
FastAPI REST API for Equipment Analytics.

This module provides REST endpoints for the dashboard to query
equipment state, history, and utilization metrics.
"""

import logging
from typing import List, Optional
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
import asyncio
from pathlib import Path
from pydantic import BaseModel
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from .db_models import EquipmentEvent, get_session

logger = logging.getLogger(__name__)

# FastAPI application
app = FastAPI(
    title="Equipment Analytics API",
    description="REST API for equipment utilization monitoring and analytics",
    version="1.0.0"
)

# Enable CORS for Streamlit dashboard and other frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global engine reference (set during startup)
_engine: Optional[Engine] = None
_SessionLocal = None


def set_engine(engine: Engine) -> None:
    """
    Set the database engine for the API.
    
    Args:
        engine: SQLAlchemy Engine instance
    """
    global _engine, _SessionLocal
    _engine = engine
    _SessionLocal = get_session(engine)


def get_db() -> Session:
    """
    Dependency injection for database sessions.
    
    Yields:
        Database session with automatic cleanup
    """
    if _SessionLocal is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ============================================================================
# Response Models
# ============================================================================

class EquipmentSummary(BaseModel):
    """Summary of a single equipment's current state."""
    equipment_id: str
    equipment_class: str
    current_state: str
    current_activity: str
    utilization_percent: float
    total_idle_dwell_seconds: float = 0.0
    current_idle_streak_seconds: float = 0.0
    times_re_identified: int = 0
    last_seen: Optional[str] = None
    
    class Config:
        from_attributes = True


class EquipmentEventResponse(BaseModel):
    """Full equipment event record."""
    id: int
    frame_id: int
    equipment_id: str
    equipment_class: str
    timestamp: str
    current_state: str
    current_activity: str
    motion_source: str
    total_tracked_seconds: float
    total_active_seconds: float
    total_idle_seconds: float
    utilization_percent: float
    created_at: Optional[str] = None
    
    class Config:
        from_attributes = True


class EquipmentUtilizationSummary(BaseModel):
    """Per-equipment utilization summary."""
    equipment_id: str
    equipment_class: str
    total_tracked_seconds: float
    total_active_seconds: float
    total_idle_seconds: float
    utilization_percent: float
    total_idle_dwell_seconds: float = 0.0
    current_idle_streak_seconds: float = 0.0
    times_re_identified: int = 0
    event_count: int


class UtilizationSummaryResponse(BaseModel):
    """Aggregate utilization statistics."""
    total_equipment: int
    active_count: int
    inactive_count: int
    avg_utilization: float
    avg_idle_dwell: float = 0.0
    max_idle_dwell: float = 0.0
    equipment: List[EquipmentUtilizationSummary]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    database: str
    message: str


class LatestFrameEquipment(BaseModel):
    """Equipment data for the latest frame."""
    equipment_id: str
    equipment_class: str
    current_state: str
    current_activity: str
    motion_source: str
    utilization_percent: float
    timestamp: str
    frame_id: int


class LatestFrameResponse(BaseModel):
    """Response for latest frame data."""
    frame_id: int
    equipment: List[LatestFrameEquipment]


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint.
    
    Verifies the API is running and database connection is healthy.
    """
    try:
        # Test database connection
        db.execute(func.now())
        return HealthResponse(
            status="healthy",
            database="connected",
            message="Equipment Analytics API is running"
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Database connection failed: {str(e)}")


@app.get("/api/equipment", response_model=List[EquipmentSummary], tags=["Equipment"])
async def list_equipment(channel: Optional[str] = None, db: Session = Depends(get_db)):
    """
    List all tracked equipment with their LATEST state.
    
    Returns the most recent record for each unique equipment_id.
    Optionally filter by video channel (video_source).
    """
    try:
        # Subquery to get the max id (latest record) for each equipment
        base_query = db.query(
            EquipmentEvent.equipment_id,
            func.max(EquipmentEvent.id).label("max_id")
        )
        if channel and channel.lower() != "all":
            base_query = base_query.filter(EquipmentEvent.video_source == channel)
        subquery = base_query.group_by(EquipmentEvent.equipment_id).subquery()
        
        # Join with main table to get full records
        latest_events = (
            db.query(EquipmentEvent)
            .join(
                subquery,
                (EquipmentEvent.equipment_id == subquery.c.equipment_id) &
                (EquipmentEvent.id == subquery.c.max_id)
            )
            .all()
        )
        
        return [
            EquipmentSummary(
                equipment_id=event.equipment_id,
                equipment_class=event.equipment_class,
                current_state=event.current_state,
                current_activity=event.current_activity,
                utilization_percent=event.utilization_percent,
                total_idle_dwell_seconds=event.total_idle_dwell_seconds or 0.0,
                current_idle_streak_seconds=event.current_idle_streak_seconds or 0.0,
                times_re_identified=event.times_re_identified or 0,
                last_seen=event.created_at.isoformat() if event.created_at else None
            )
            for event in latest_events
        ]
        
    except Exception as e:
        logger.error(f"Error fetching equipment list: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch equipment: {str(e)}")


@app.get(
    "/api/equipment/{equipment_id}/history",
    response_model=List[EquipmentEventResponse],
    tags=["Equipment"]
)
async def get_equipment_history(
    equipment_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Get time-series history for a specific equipment.
    
    Args:
        equipment_id: The equipment identifier (e.g., "DT-001")
        limit: Maximum number of records to return (default 100, max 1000)
        
    Returns:
        List of events ordered by created_at descending
    """
    try:
        events = (
            db.query(EquipmentEvent)
            .filter(EquipmentEvent.equipment_id == equipment_id)
            .order_by(desc(EquipmentEvent.created_at))
            .limit(limit)
            .all()
        )
        
        if not events:
            raise HTTPException(
                status_code=404,
                detail=f"No events found for equipment: {equipment_id}"
            )
        
        return [
            EquipmentEventResponse(
                id=event.id,
                frame_id=event.frame_id,
                equipment_id=event.equipment_id,
                equipment_class=event.equipment_class,
                timestamp=event.timestamp,
                current_state=event.current_state,
                current_activity=event.current_activity,
                motion_source=event.motion_source,
                total_tracked_seconds=event.total_tracked_seconds,
                total_active_seconds=event.total_active_seconds,
                total_idle_seconds=event.total_idle_seconds,
                utilization_percent=event.utilization_percent,
                created_at=event.created_at.isoformat() if event.created_at else None
            )
            for event in events
        ]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching equipment history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch history: {str(e)}")


@app.get(
    "/api/utilization/summary",
    response_model=UtilizationSummaryResponse,
    tags=["Utilization"]
)
async def get_utilization_summary(channel: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get aggregate utilization statistics.
    
    Returns total equipment count, active/inactive counts,
    average utilization, and per-equipment summaries.
    Optionally filter by video channel (video_source).
    """
    try:
        # Get the latest event for each equipment to determine current state
        base_query = db.query(
            EquipmentEvent.equipment_id,
            func.max(EquipmentEvent.id).label("max_id")
        )
        if channel and channel.lower() != "all":
            base_query = base_query.filter(EquipmentEvent.video_source == channel)
        subquery = base_query.group_by(EquipmentEvent.equipment_id).subquery()
        
        latest_events = (
            db.query(EquipmentEvent)
            .join(
                subquery,
                (EquipmentEvent.equipment_id == subquery.c.equipment_id) &
                (EquipmentEvent.id == subquery.c.max_id)
            )
            .all()
        )
        
        if not latest_events:
            return UtilizationSummaryResponse(
                total_equipment=0,
                active_count=0,
                inactive_count=0,
                avg_utilization=0.0,
                equipment=[]
            )
        
        # Calculate counts
        active_count = sum(1 for e in latest_events if e.current_state == "ACTIVE")
        inactive_count = len(latest_events) - active_count
        
        # Calculate average utilization
        avg_utilization = sum(e.utilization_percent for e in latest_events) / len(latest_events)
        
        # Per-equipment summaries
        equipment_summaries = []
        for event in latest_events:
            # Get event count for this equipment
            count_query = db.query(func.count(EquipmentEvent.id)).filter(
                EquipmentEvent.equipment_id == event.equipment_id
            )
            if channel and channel.lower() != "all":
                count_query = count_query.filter(EquipmentEvent.video_source == channel)
            event_count = count_query.scalar()
            
            equipment_summaries.append(
                EquipmentUtilizationSummary(
                    equipment_id=event.equipment_id,
                    equipment_class=event.equipment_class,
                    total_tracked_seconds=event.total_tracked_seconds,
                    total_active_seconds=event.total_active_seconds,
                    total_idle_seconds=event.total_idle_seconds,
                    utilization_percent=event.utilization_percent,
                    total_idle_dwell_seconds=event.total_idle_dwell_seconds or 0.0,
                    current_idle_streak_seconds=event.current_idle_streak_seconds or 0.0,
                    times_re_identified=event.times_re_identified or 0,
                    event_count=event_count
                )
            )
        
        # Calculate dwell time aggregates
        dwell_values = [e.total_idle_dwell_seconds or 0.0 for e in latest_events]
        avg_idle_dwell = sum(dwell_values) / len(dwell_values) if dwell_values else 0.0
        max_idle_dwell = max(dwell_values) if dwell_values else 0.0
        
        return UtilizationSummaryResponse(
            total_equipment=len(latest_events),
            active_count=active_count,
            inactive_count=inactive_count,
            avg_utilization=round(avg_utilization, 2),
            avg_idle_dwell=round(avg_idle_dwell, 2),
            max_idle_dwell=round(max_idle_dwell, 2),
            equipment=equipment_summaries
        )
        
    except Exception as e:
        logger.error(f"Error fetching utilization summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {str(e)}")


@app.get(
    "/api/latest-frame",
    response_model=LatestFrameResponse,
    tags=["Real-time"]
)
async def get_latest_frame(channel: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get the latest processed frame data for all equipment.
    
    Useful for real-time dashboard updates showing current state
    of all equipment in the most recently processed video frame.
    Optionally filter by video channel (video_source).
    """
    try:
        # Get the maximum frame_id
        max_frame_query = db.query(func.max(EquipmentEvent.frame_id))
        if channel and channel.lower() != "all":
            max_frame_query = max_frame_query.filter(EquipmentEvent.video_source == channel)
        max_frame_id = max_frame_query.scalar()
        
        if max_frame_id is None:
            return LatestFrameResponse(frame_id=0, equipment=[])
        
        # Get all equipment in that frame
        frame_query = db.query(EquipmentEvent).filter(EquipmentEvent.frame_id == max_frame_id)
        if channel and channel.lower() != "all":
            frame_query = frame_query.filter(EquipmentEvent.video_source == channel)
        events = frame_query.all()
        
        return LatestFrameResponse(
            frame_id=max_frame_id,
            equipment=[
                LatestFrameEquipment(
                    equipment_id=event.equipment_id,
                    equipment_class=event.equipment_class,
                    current_state=event.current_state,
                    current_activity=event.current_activity,
                    motion_source=event.motion_source,
                    utilization_percent=event.utilization_percent,
                    timestamp=event.timestamp,
                    frame_id=event.frame_id
                )
                for event in events
            ]
        )
        
    except Exception as e:
        logger.error(f"Error fetching latest frame: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch latest frame: {str(e)}")


# Additional utility endpoint
@app.get("/api/stats", tags=["Statistics"])
async def get_stats(channel: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Get general statistics about the events in the database.
    
    Returns total event count, unique equipment count, and frame range.
    Optionally filter by video channel (video_source).
    """
    try:
        base = db.query(EquipmentEvent)
        if channel and channel.lower() != "all":
            base = base.filter(EquipmentEvent.video_source == channel)
        
        total_events = base.with_entities(func.count(EquipmentEvent.id)).scalar() or 0
        unique_equipment = base.with_entities(func.count(func.distinct(EquipmentEvent.equipment_id))).scalar() or 0
        min_frame = base.with_entities(func.min(EquipmentEvent.frame_id)).scalar() or 0
        max_frame = base.with_entities(func.max(EquipmentEvent.frame_id)).scalar() or 0
        
        return {
            "total_events": total_events,
            "unique_equipment": unique_equipment,
            "frame_range": {
                "min": min_frame,
                "max": max_frame
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch stats: {str(e)}")


# ============================================================================
# Frame Image Endpoints
# ============================================================================

# Frame output directory (shared with cv-service)
FRAME_DIR = Path("/app/frames")


@app.get("/api/latest-frame-image", tags=["Frames"])
async def get_latest_frame_image():
    """
    Serve the latest annotated frame as a JPEG image.
    
    Returns the most recently processed video frame with
    bounding boxes and equipment labels drawn on it.
    """
    latest_frame_path = FRAME_DIR / "latest_frame.jpg"
    
    if not latest_frame_path.exists():
        raise HTTPException(
            status_code=404,
            detail="No frame available yet. Waiting for CV service to process video."
        )
    
    return FileResponse(
        path=str(latest_frame_path),
        media_type="image/jpeg",
        filename="latest_frame.jpg"
    )


@app.get("/api/stream/mjpeg", tags=["Streaming"])
async def stream_mjpeg():
    """
    MJPEG stream endpoint for continuous real-time frame streaming.
    Returns multipart/x-mixed-replace stream of annotated JPEG frames.
    Auto-closes after ~120 seconds to prevent stale connection pile-up.
    """
    import time as _time
    frame_dir = Path("/app/frames")
    
    async def frame_generator():
        last_mtime = 0
        last_data = None
        start = _time.monotonic()
        max_duration = 120  # Close after 120s; client JS will reconnect
        frames_sent = 0
        
        while (_time.monotonic() - start) < max_duration:
            try:
                latest_frame_path = frame_dir / "latest_frame.jpg"
                
                if latest_frame_path.exists():
                    current_mtime = latest_frame_path.stat().st_mtime
                    
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        # Use async file I/O to prevent blocking the event loop
                        frame_data = await asyncio.to_thread(latest_frame_path.read_bytes)
                        
                        if len(frame_data) > 0:
                            last_data = frame_data
                            yield (
                                b'--frame\r\n'
                                b'Content-Type: image/jpeg\r\n'
                                b'Content-Length: ' + str(len(frame_data)).encode() + b'\r\n'
                                b'Cache-Control: no-cache, no-store\r\n'
                                b'\r\n' + frame_data + b'\r\n'
                            )
                            frames_sent += 1
                    elif frames_sent == 0 and last_data is None:
                        # First request and frame exists but mtime unchanged:
                        # send it once so the client sees something immediately
                        frame_data = await asyncio.to_thread(latest_frame_path.read_bytes)
                        if len(frame_data) > 0:
                            last_data = frame_data
                            last_mtime = current_mtime
                            yield (
                                b'--frame\r\n'
                                b'Content-Type: image/jpeg\r\n'
                                b'Content-Length: ' + str(len(frame_data)).encode() + b'\r\n'
                                b'Cache-Control: no-cache, no-store\r\n'
                                b'\r\n' + frame_data + b'\r\n'
                            )
                            frames_sent += 1
                
                # Poll at ~15Hz for smoother streaming (~67ms interval)
                await asyncio.sleep(0.067)
                
            except GeneratorExit:
                return
            except Exception:
                await asyncio.sleep(0.2)
    
    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Connection": "keep-alive"
        }
    )


# ============================================================================
# Video Channel Endpoints
# ============================================================================

@app.get("/api/videos", tags=["Video Channels"])
async def list_videos():
    """List all available video files as channels."""
    video_dir = Path("/app/videos")
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.webm', '.flv'}

    videos = []
    if video_dir.exists():
        for f in sorted(video_dir.iterdir()):
            if f.is_file() and f.suffix.lower() in video_extensions:
                videos.append({
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                    "channel_id": f.stem  # filename without extension as channel ID
                })

    # Read current selected video
    control_file = Path("/app/frames/selected_video.txt")
    current_video = None
    if control_file.exists():
        current_video = control_file.read_text().strip()

    return {
        "videos": videos,
        "current_video": current_video,
        "total_channels": len(videos)
    }


@app.post("/api/videos/select", tags=["Video Channels"])
async def select_video(request: dict):
    """Select a video channel to process.

    Body: {"filename": "video_name.mp4"}
    """
    filename = request.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")

    # Allow "all" to reset to processing all videos
    if filename.lower() != "all":
        video_path = Path("/app/videos") / filename
        if not video_path.exists():
            raise HTTPException(status_code=404, detail=f"Video '{filename}' not found")

    # Write control file for CV service to pick up
    control_file = Path("/app/frames/selected_video.txt")
    control_file.parent.mkdir(parents=True, exist_ok=True)
    control_file.write_text(filename)

    return {
        "status": "ok",
        "selected_video": filename,
        "message": f"CV service will switch to '{filename}' on next frame check"
    }


@app.get("/api/frame/{frame_id}", tags=["Frames"])
async def get_frame_by_id(frame_id: int):
    """
    Serve a specific frame by its ID.
    
    Args:
        frame_id: The frame number to retrieve
    
    Returns:
        The annotated frame image as JPEG
    """
    frame_path = FRAME_DIR / f"frame_{frame_id:06d}.jpg"
    
    if not frame_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Frame {frame_id} not found. It may have been cleaned up or not processed yet."
        )
    
    return FileResponse(
        path=str(frame_path),
        media_type="image/jpeg",
        filename=f"frame_{frame_id}.jpg"
    )
