"""
Activity Classifier Module for Equipment Activity Classification.

This module implements rule-based activity classification for tracked construction
equipment based on motion analysis results. It uses a state machine approach with
N-frame smoothing to prevent rapid flickering between states.

Activity classifications:
- DIGGING: Arm-only downward motion (excavating)
- SWINGING_LOADING: Horizontal motion (rotating/loading)
- DUMPING: Arm-only upward motion (releasing material)
- WAITING: No significant motion (idle)
"""

import logging
from collections import deque
from typing import Optional

# Configure module logger
logger = logging.getLogger(__name__)


class ActivityClassifier:
    """
    Classifies equipment activity based on motion analysis results.
    
    Uses rule-based classification with N-frame smoothing to prevent
    rapid state changes due to noisy motion detection.
    
    Attributes:
        smoothing_window: Number of frames to consider for mode-based smoothing
        vertical_flow_threshold: Minimum vertical flow for direction detection
        horizontal_flow_threshold: Minimum horizontal flow for direction detection
    """
    
    # Activity constants
    ACTIVITY_DIGGING = "DIGGING"
    ACTIVITY_SWINGING_LOADING = "SWINGING_LOADING"
    ACTIVITY_DUMPING = "DUMPING"
    ACTIVITY_WAITING = "WAITING"
    
    # State constants
    STATE_ACTIVE = "ACTIVE"
    STATE_INACTIVE = "INACTIVE"
    
    def __init__(self, config: dict):
        """
        Initialize ActivityClassifier with configuration.
        
        Args:
            config: Configuration dictionary with activity parameters.
                Expected keys from settings.yaml activity section:
                - smoothing_window (int): N-frame smoothing window size (default: 5)
                - vertical_flow_threshold (float): Threshold for vertical motion (default: 1.5)
                - horizontal_flow_threshold (float): Threshold for horizontal motion (default: 1.5)
        """
        self.smoothing_window = config.get('smoothing_window', 5)
        self.vertical_flow_threshold = config.get('vertical_flow_threshold', 1.5)
        self.horizontal_flow_threshold = config.get('horizontal_flow_threshold', 1.5)
        
        # Per-equipment activity history for N-frame smoothing
        # Maps equipment_id -> deque of recent raw classifications
        self._activity_history: dict[str, deque] = {}
        
        logger.info(
            f"ActivityClassifier initialized: smoothing_window={self.smoothing_window}, "
            f"vertical_threshold={self.vertical_flow_threshold}, "
            f"horizontal_threshold={self.horizontal_flow_threshold}"
        )
    
    def classify(
        self,
        tracked_objects: list[dict],
        motion_results: list[dict]
    ) -> dict:
        """
        Classify activity for each tracked equipment based on motion analysis.
        
        Args:
            tracked_objects: From tracker.update() - list with equipment_id, bbox, etc.
            motion_results: From motion_analyzer.analyze() - list with equipment_id,
                           motion_source, dominant_direction, flow_vectors, etc.
        
        Returns:
            dict mapping equipment_id -> {
                "current_state": str,      # "ACTIVE" or "INACTIVE"
                "current_activity": str,   # Activity classification
                "activity": str,           # Alias for current_activity (for main.py compatibility)
                "motion_source": str       # "full_body", "arm_only", "none"
            }
        """
        results = {}
        
        # Build a lookup map for motion results by equipment_id
        motion_map = self._build_motion_map(motion_results)
        
        for obj in tracked_objects:
            equipment_id = obj.get('equipment_id', 'unknown')
            
            # Get motion data for this equipment
            motion_data = motion_map.get(equipment_id, self._empty_motion_data())
            
            # Classify raw activity based on motion rules
            raw_activity = self._classify_raw_activity(motion_data)
            
            # Apply N-frame smoothing
            smoothed_activity = self._apply_smoothing(equipment_id, raw_activity)
            
            # Determine state from activity
            current_state = (
                self.STATE_INACTIVE 
                if smoothed_activity == self.ACTIVITY_WAITING 
                else self.STATE_ACTIVE
            )
            
            motion_source = motion_data.get('motion_source', 'none')
            
            results[equipment_id] = {
                "current_state": current_state,
                "current_activity": smoothed_activity,
                "activity": smoothed_activity,  # Alias for main.py compatibility
                "motion_source": motion_source
            }
        
        return results
    
    def _build_motion_map(self, motion_results: list[dict]) -> dict:
        """
        Build a lookup map from equipment_id to motion data.
        
        Args:
            motion_results: List of motion analysis results
        
        Returns:
            Dict mapping equipment_id -> motion_data dict
        """
        motion_map = {}
        
        # Handle both list and dict inputs for robustness
        if isinstance(motion_results, dict):
            # If it's already a dict, assume it's keyed by equipment_id
            return motion_results
        
        if isinstance(motion_results, list):
            for motion_data in motion_results:
                if isinstance(motion_data, dict):
                    equipment_id = motion_data.get('equipment_id')
                    if equipment_id:
                        motion_map[equipment_id] = motion_data
        
        return motion_map
    
    def _empty_motion_data(self) -> dict:
        """Return empty motion data structure for missing equipment."""
        return {
            'motion_source': 'none',
            'dominant_direction': 'none',
            'flow_vectors': {
                'upper_mean_dx': 0.0,
                'upper_mean_dy': 0.0,
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }
    
    def _classify_raw_activity(self, motion_data: dict) -> str:
        """
        Classify activity based on motion rules (before smoothing).
        
        Activity classification rules:
        - DIGGING: arm_only AND dominant vertical downward (dy > threshold)
        - SWINGING_LOADING: (arm_only OR full_body) AND horizontal (|dx| > threshold)
        - DUMPING: arm_only AND dominant vertical upward (dy < -threshold)
        - WAITING: motion_source == "none"
        - Default with motion: SWINGING_LOADING
        
        Args:
            motion_data: Motion analysis result dict
        
        Returns:
            Raw activity classification string
        """
        motion_source = motion_data.get('motion_source', 'none')
        
        # WAITING: No significant motion
        if motion_source == 'none':
            return self.ACTIVITY_WAITING
        
        # Get flow vectors for direction analysis
        flow_vectors = motion_data.get('flow_vectors', {})
        
        # Use upper region flow for arm-based activities
        upper_dx = flow_vectors.get('upper_mean_dx', 0.0)
        upper_dy = flow_vectors.get('upper_mean_dy', 0.0)
        
        # For full_body motion, consider both regions
        lower_dx = flow_vectors.get('lower_mean_dx', 0.0)
        lower_dy = flow_vectors.get('lower_mean_dy', 0.0)
        
        # Determine primary flow direction based on motion source
        if motion_source == 'arm_only':
            dx, dy = upper_dx, upper_dy
        else:
            # For full_body, average both regions
            dx = (upper_dx + lower_dx) / 2.0
            dy = (upper_dy + lower_dy) / 2.0
        
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        
        # Apply classification rules
        
        # DIGGING: arm_only AND downward motion (positive dy in OpenCV = downward)
        if motion_source == 'arm_only' and dy > self.vertical_flow_threshold:
            return self.ACTIVITY_DIGGING
        
        # DUMPING: arm_only AND upward motion (negative dy in OpenCV = upward)
        if motion_source == 'arm_only' and dy < -self.vertical_flow_threshold:
            return self.ACTIVITY_DUMPING
        
        # SWINGING_LOADING: horizontal motion
        if abs_dx > self.horizontal_flow_threshold:
            return self.ACTIVITY_SWINGING_LOADING
        
        # Default: if there IS motion but no specific rule matches
        # Default to SWINGING_LOADING (general active movement)
        if motion_source in ('arm_only', 'full_body'):
            return self.ACTIVITY_SWINGING_LOADING
        
        # Fallback to WAITING
        return self.ACTIVITY_WAITING
    
    def _apply_smoothing(self, equipment_id: str, raw_activity: str) -> str:
        """
        Apply N-frame smoothing to prevent rapid activity flickering.
        
        Uses mode (most common) activity from the last N classifications.
        
        Args:
            equipment_id: Equipment identifier
            raw_activity: Current raw classification
        
        Returns:
            Smoothed activity classification
        """
        # Initialize history buffer if new equipment
        if equipment_id not in self._activity_history:
            self._activity_history[equipment_id] = deque(maxlen=self.smoothing_window)
            # Fill buffer with first classification
            for _ in range(self.smoothing_window):
                self._activity_history[equipment_id].append(raw_activity)
        else:
            # Add new classification to history
            self._activity_history[equipment_id].append(raw_activity)
        
        # Return mode (most common) activity
        return self._get_mode(self._activity_history[equipment_id])
    
    def _get_mode(self, activity_buffer: deque) -> str:
        """
        Get the most common (mode) activity from the buffer.
        
        Args:
            activity_buffer: Deque of recent activity classifications
        
        Returns:
            Most frequent activity in the buffer
        """
        if not activity_buffer:
            return self.ACTIVITY_WAITING
        
        # Count occurrences of each activity
        counts: dict[str, int] = {}
        for activity in activity_buffer:
            counts[activity] = counts.get(activity, 0) + 1
        
        # Return the activity with highest count
        # In case of tie, prefer the most recent classification
        max_count = max(counts.values())
        
        # Iterate in reverse order to prefer recent on tie
        for activity in reversed(list(activity_buffer)):
            if counts[activity] == max_count:
                return activity
        
        return self.ACTIVITY_WAITING
    
    def reset(self) -> None:
        """Reset all activity history buffers (e.g., for new video)."""
        self._activity_history.clear()
        logger.debug("ActivityClassifier history reset")
    
    def get_history(self, equipment_id: str) -> Optional[list]:
        """
        Get activity history for a specific equipment.
        
        Args:
            equipment_id: Equipment identifier
        
        Returns:
            List of recent activity classifications or None if not tracked
        """
        if equipment_id in self._activity_history:
            return list(self._activity_history[equipment_id])
        return None
