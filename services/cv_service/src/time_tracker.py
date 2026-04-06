"""
Time Tracker Module for Equipment Utilization Time Analytics.

This module tracks active/idle time for each piece of equipment over the
course of video processing, providing real-time utilization statistics.

Metrics tracked per equipment:
- total_tracked_seconds: Total time equipment has been tracked
- total_active_seconds: Time spent in ACTIVE state (working)
- total_idle_seconds: Time spent in INACTIVE state (waiting)
- utilization_percent: Percentage of tracked time spent active
"""

import logging
import time as _time
from typing import Optional

# Configure module logger
logger = logging.getLogger(__name__)


class TimeTracker:
    """
    Tracks time-based utilization metrics for all tracked equipment.
    
    Maintains per-equipment counters that accumulate across frames and
    persist through temporary disappearances (equipment leaving/entering frame).
    
    Attributes:
        _equipment_stats: Dict mapping equipment_id -> time statistics dict
        _last_timestamp: Last processed timestamp for delta calculation
    """
    
    # State constants (should match ActivityClassifier)
    STATE_ACTIVE = "ACTIVE"
    STATE_INACTIVE = "INACTIVE"
    
    def __init__(self):
        """
        Initialize time tracker.
        
        No configuration required - time tracking uses frame-based updates
        with configurable FPS passed to update() method.
        """
        # Per-equipment statistics
        # Maps equipment_id -> {total_tracked_seconds, total_active_seconds, total_idle_seconds}
        self._equipment_stats: dict[str, dict] = {}
        
        # Track last processed timestamp (not currently used, but useful for debugging)
        self._last_timestamp: Optional[str] = None
        
        # History buffer for equipment that lost tracking (for Re-ID restoration)
        # equipment_id -> {stats_snapshot, lost_time}
        self._equipment_history: dict[str, dict] = {}
        
        # Dwell time tracking per equipment
        # equipment_id -> {current_idle_streak_seconds, total_idle_dwell_seconds,
        #                   times_re_identified, last_activity_change, last_state}
        self._dwell_data: dict[str, dict] = {}
        
        logger.info("TimeTracker initialized")
    
    def update(
        self,
        tracked_objects: list[dict],
        activities: dict,
        frame_timestamp: str,
        fps: float = 30.0
    ) -> dict:
        """
        Update time tracking for all tracked equipment.
        
        Called once per processed frame to increment time counters based on
        current activity states. Time delta is calculated as 1/fps seconds
        per frame (or adjusted for frame_skip if needed).
        
        Args:
            tracked_objects: List of tracked objects with equipment_id
            activities: Dict from ActivityClassifier.classify() mapping
                       equipment_id -> {"current_state": str, ...}
            frame_timestamp: Current frame timestamp "HH:MM:SS.mmm" (for reference)
            fps: Video FPS for time delta calculation (default 30.0)
        
        Returns:
            dict mapping equipment_id -> {
                "total_tracked_seconds": float,
                "total_active_seconds": float,
                "total_idle_seconds": float,
                "utilization_percent": float
            }
        """
        # Calculate time delta for this frame
        # Note: If frame_skip is used, the effective time per processed frame
        # would be (frame_skip / fps), but since main.py doesn't pass frame_skip,
        # we use 1/fps which represents each processed frame's contribution
        time_delta = 1.0 / max(fps, 1.0)  # Prevent division by zero
        
        # Update timestamp reference
        self._last_timestamp = frame_timestamp
        
        # Process each tracked equipment
        for obj in tracked_objects:
            equipment_id = obj.get('equipment_id', 'unknown')
            
            # Initialize stats for new equipment
            if equipment_id not in self._equipment_stats:
                self._equipment_stats[equipment_id] = {
                    "total_tracked_seconds": 0.0,
                    "total_active_seconds": 0.0,
                    "total_idle_seconds": 0.0
                }
            
            # Initialize dwell data for new equipment
            if equipment_id not in self._dwell_data:
                self._dwell_data[equipment_id] = {
                    "current_idle_streak_seconds": 0.0,
                    "total_idle_dwell_seconds": 0.0,
                    "times_re_identified": 0,
                    "last_activity_change": frame_timestamp,
                    "last_state": self.STATE_INACTIVE,
                }
            
            # Get current state from activity classification
            activity_info = activities.get(equipment_id, {})
            current_state = activity_info.get('current_state', self.STATE_INACTIVE)
            
            # Update dwell tracking
            dwell = self._dwell_data[equipment_id]
            prev_state = dwell["last_state"]
            
            if current_state != prev_state:
                # State changed — record the transition timestamp
                dwell["last_activity_change"] = frame_timestamp
                dwell["last_state"] = current_state
                if current_state == self.STATE_ACTIVE:
                    # Became active → reset idle streak
                    dwell["current_idle_streak_seconds"] = 0.0
            
            # Update idle streak and total idle dwell
            if current_state != self.STATE_ACTIVE:
                dwell["current_idle_streak_seconds"] += time_delta
                dwell["total_idle_dwell_seconds"] += time_delta
            
            # Update time counters
            stats = self._equipment_stats[equipment_id]
            
            # Always increment total tracked time
            stats["total_tracked_seconds"] += time_delta
            
            # Increment active or idle time based on state
            if current_state == self.STATE_ACTIVE:
                stats["total_active_seconds"] += time_delta
            else:
                stats["total_idle_seconds"] += time_delta
        
        # Build and return current stats for all tracked equipment
        return self._build_all_stats()
    
    def get_stats(self, equipment_id: str) -> dict:
        """
        Get current time stats for a specific equipment.
        
        Args:
            equipment_id: Equipment identifier
        
        Returns:
            Dict with time statistics, or empty stats if equipment not found:
            {
                "total_tracked_seconds": float,
                "total_active_seconds": float,
                "total_idle_seconds": float,
                "utilization_percent": float
            }
        """
        if equipment_id not in self._equipment_stats:
            return {
                "total_tracked_seconds": 0.0,
                "total_active_seconds": 0.0,
                "total_idle_seconds": 0.0,
                "utilization_percent": 0.0
            }
        
        return self._build_stats(equipment_id)
    
    def get_all_stats(self) -> dict:
        """
        Get time stats for all tracked equipment.
        
        Returns:
            Dict mapping equipment_id -> time statistics dict
        """
        return self._build_all_stats()
    
    def _build_stats(self, equipment_id: str) -> dict:
        """
        Build complete stats dict for an equipment including utilization percent.
        
        Args:
            equipment_id: Equipment identifier
        
        Returns:
            Stats dict with calculated utilization_percent
        """
        stats = self._equipment_stats.get(equipment_id, {
            "total_tracked_seconds": 0.0,
            "total_active_seconds": 0.0,
            "total_idle_seconds": 0.0
        })
        
        # Calculate utilization percentage
        total_tracked = stats.get("total_tracked_seconds", 0.0)
        total_active = stats.get("total_active_seconds", 0.0)
        
        if total_tracked > 0:
            utilization_percent = (total_active / total_tracked) * 100.0
        else:
            utilization_percent = 0.0
        
        return {
            "total_tracked_seconds": stats.get("total_tracked_seconds", 0.0),
            "total_active_seconds": stats.get("total_active_seconds", 0.0),
            "total_idle_seconds": stats.get("total_idle_seconds", 0.0),
            "utilization_percent": utilization_percent
        }
    
    def _build_all_stats(self) -> dict:
        """
        Build stats for all tracked equipment.
        
        Returns:
            Dict mapping equipment_id -> stats dict
        """
        return {
            equipment_id: self._build_stats(equipment_id)
            for equipment_id in self._equipment_stats
        }
    
    def mark_equipment_lost(self, equipment_id: str) -> None:
        """
        Save stats for equipment that lost tracking (left frame).
        
        Preserves accumulated stats in history so they can be restored
        if the equipment is re-identified later.
        
        Args:
            equipment_id: Equipment identifier
        """
        stats = self._equipment_stats.get(equipment_id)
        dwell = self._dwell_data.get(equipment_id)
        if stats is not None:
            self._equipment_history[equipment_id] = {
                "stats_snapshot": dict(stats),
                "dwell_snapshot": dict(dwell) if dwell else None,
                "lost_time": _time.monotonic(),
            }
            logger.debug(
                f"Equipment {equipment_id} marked lost — stats preserved "
                f"(tracked={stats['total_tracked_seconds']:.1f}s)"
            )
    
    def restore_equipment(self, equipment_id: str) -> None:
        """
        Restore accumulated stats for re-identified equipment.
        
        If the equipment was previously tracked and then lost, this method
        restores its stats from history and adds the absent duration as idle time.
        
        Args:
            equipment_id: Equipment identifier that was re-identified
        """
        history = self._equipment_history.pop(equipment_id, None)
        if history is None:
            logger.debug(f"No history for equipment {equipment_id}, nothing to restore")
            return
        
        snapshot = history["stats_snapshot"]
        dwell_snapshot = history.get("dwell_snapshot")
        lost_time = history["lost_time"]
        absent_duration = _time.monotonic() - lost_time
        
        # Restore base stats and add absent duration as idle
        self._equipment_stats[equipment_id] = {
            "total_tracked_seconds": snapshot["total_tracked_seconds"] + absent_duration,
            "total_active_seconds": snapshot["total_active_seconds"],
            "total_idle_seconds": snapshot["total_idle_seconds"] + absent_duration,
        }
        
        # Restore dwell data
        if dwell_snapshot:
            self._dwell_data[equipment_id] = {
                "current_idle_streak_seconds": dwell_snapshot["current_idle_streak_seconds"] + absent_duration,
                "total_idle_dwell_seconds": dwell_snapshot["total_idle_dwell_seconds"] + absent_duration,
                "times_re_identified": dwell_snapshot["times_re_identified"] + 1,
                "last_activity_change": dwell_snapshot["last_activity_change"],
                "last_state": self.STATE_INACTIVE,
            }
        else:
            self._dwell_data[equipment_id] = {
                "current_idle_streak_seconds": absent_duration,
                "total_idle_dwell_seconds": absent_duration,
                "times_re_identified": 1,
                "last_activity_change": self._last_timestamp or "00:00:00.000",
                "last_state": self.STATE_INACTIVE,
            }
        
        logger.info(
            f"Equipment {equipment_id} restored via Re-ID — "
            f"absent {absent_duration:.1f}s added as idle, "
            f"re-ID count={self._dwell_data[equipment_id]['times_re_identified']}"
        )
    
    def get_dwell_stats(self, equipment_id: str) -> dict:
        """
        Get dwell time statistics for a specific equipment.
        
        Args:
            equipment_id: Equipment identifier
        
        Returns:
            Dict with dwell time statistics
        """
        dwell = self._dwell_data.get(equipment_id)
        if dwell is None:
            return {
                "total_idle_dwell_seconds": 0.0,
                "current_idle_streak_seconds": 0.0,
                "times_re_identified": 0,
                "last_activity_change": "00:00:00.000",
            }
        return {
            "total_idle_dwell_seconds": dwell["total_idle_dwell_seconds"],
            "current_idle_streak_seconds": dwell["current_idle_streak_seconds"],
            "times_re_identified": dwell["times_re_identified"],
            "last_activity_change": dwell["last_activity_change"],
        }
    
    def reset(self) -> None:
        """
        Reset all time tracking statistics.
        
        Called when starting to process a new video file to ensure
        fresh statistics for each video.
        """
        self._equipment_stats.clear()
        self._last_timestamp = None
        self._equipment_history.clear()
        self._dwell_data.clear()
        logger.debug("TimeTracker statistics reset")
    
    def get_equipment_ids(self) -> list:
        """
        Get list of all equipment IDs being tracked.
        
        Returns:
            List of equipment ID strings
        """
        return list(self._equipment_stats.keys())
    
    def get_total_utilization(self) -> dict:
        """
        Calculate aggregate utilization across all equipment.
        
        Returns:
            Dict with aggregate statistics:
            {
                "total_equipment_count": int,
                "total_tracked_seconds": float,
                "total_active_seconds": float,
                "total_idle_seconds": float,
                "average_utilization_percent": float
            }
        """
        if not self._equipment_stats:
            return {
                "total_equipment_count": 0,
                "total_tracked_seconds": 0.0,
                "total_active_seconds": 0.0,
                "total_idle_seconds": 0.0,
                "average_utilization_percent": 0.0
            }
        
        total_tracked = 0.0
        total_active = 0.0
        total_idle = 0.0
        
        for stats in self._equipment_stats.values():
            total_tracked += stats.get("total_tracked_seconds", 0.0)
            total_active += stats.get("total_active_seconds", 0.0)
            total_idle += stats.get("total_idle_seconds", 0.0)
        
        if total_tracked > 0:
            avg_utilization = (total_active / total_tracked) * 100.0
        else:
            avg_utilization = 0.0
        
        return {
            "total_equipment_count": len(self._equipment_stats),
            "total_tracked_seconds": total_tracked,
            "total_active_seconds": total_active,
            "total_idle_seconds": total_idle,
            "average_utilization_percent": avg_utilization
        }
