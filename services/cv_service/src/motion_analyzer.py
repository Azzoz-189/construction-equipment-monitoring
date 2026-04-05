"""
Motion Analyzer Module for Articulated Equipment Motion Detection.

This module implements region-based optical flow analysis to detect articulated
motion in construction equipment (e.g., excavator arm moving while tracks are
stationary). This is the key differentiator for accurate activity classification.

The approach:
1. Split each tracked object's bounding box into upper (arm/boom) and lower (base/tracks) regions
2. Compute optical flow independently for each region
3. Classify motion source based on which regions are moving
"""

import logging
from typing import Optional

import cv2
import numpy as np

# Configure module logger
logger = logging.getLogger(__name__)


class MotionAnalyzer:
    """
    Analyzes motion patterns in tracked equipment using region-based optical flow.
    
    This analyzer detects articulated motion by comparing motion in different
    regions of the equipment:
    - Upper region: boom/arm area (for excavators, cranes, etc.)
    - Lower region: tracks/wheels/base
    
    Motion classification:
    - "full_body": Both regions moving (driving/traveling)
    - "arm_only": Only upper region moving (digging, swinging, loading)
    - "none": Equipment is stationary
    
    Attributes:
        magnitude_threshold: Minimum optical flow magnitude to classify as "moving"
        upper_region_ratio: Fraction of bbox height for upper region (default 0.5)
        flow_method: Optical flow algorithm to use (currently only "farneback")
        min_region_size: Minimum region dimension in pixels for valid analysis
    """
    
    # Minimum region size in pixels for reliable optical flow
    MIN_REGION_SIZE = 10
    
    # Farneback optical flow parameters (optimized for construction equipment)
    FARNEBACK_PARAMS = {
        'pyr_scale': 0.5,    # Pyramid scale < 1 for multi-resolution
        'levels': 3,          # Number of pyramid levels
        'winsize': 15,        # Averaging window size
        'iterations': 3,      # Iterations at each pyramid level
        'poly_n': 5,          # Size of pixel neighborhood
        'poly_sigma': 1.2,    # Gaussian sigma for polynomial expansion
        'flags': 0            # No flags
    }
    
    def __init__(self, config: dict):
        """
        Initialize motion analyzer with configuration.
        
        Args:
            config: Configuration dictionary with motion analysis parameters.
                Expected keys from settings.yaml motion section:
                - magnitude_threshold (float): Minimum magnitude to consider moving (default: 2.0)
                - upper_region_ratio (float): Fraction of bbox for upper region (default: 0.5)
                - flow_method (str): Optical flow method to use (default: "farneback")
        
        Raises:
            ValueError: If upper_region_ratio is not in (0, 1) range.
        """
        self.magnitude_threshold = config.get('magnitude_threshold', 2.0)
        self.upper_region_ratio = config.get('upper_region_ratio', 0.5)
        self.flow_method = config.get('flow_method', 'farneback')
        
        # Validate configuration
        if not 0 < self.upper_region_ratio < 1:
            raise ValueError(
                f"upper_region_ratio must be in (0, 1), got {self.upper_region_ratio}"
            )
        
        logger.info(
            f"MotionAnalyzer initialized: threshold={self.magnitude_threshold}, "
            f"upper_ratio={self.upper_region_ratio}, method={self.flow_method}"
        )
    
    def analyze(
        self,
        prev_frame_gray: np.ndarray,
        curr_frame_gray: np.ndarray,
        tracked_objects: list[dict]
    ) -> list[dict]:
        """
        Analyze motion for each tracked object between two consecutive frames.
        
        This method computes region-based optical flow for each tracked object
        and classifies the motion source (full_body, arm_only, or none).
        
        Args:
            prev_frame_gray: Previous frame in grayscale (np.uint8).
            curr_frame_gray: Current frame in grayscale (np.uint8).
            tracked_objects: List of tracked objects, each with:
                - 'bbox': [x1, y1, x2, y2] bounding box coordinates
                - 'equipment_id': Unique identifier for the equipment
        
        Returns:
            List of motion analysis results, one per tracked object:
            {
                "equipment_id": str,
                "motion_source": str,        # "full_body", "arm_only", "none"
                "upper_magnitude": float,    # Mean flow magnitude in upper region
                "lower_magnitude": float,    # Mean flow magnitude in lower region
                "dominant_direction": str,   # "up", "down", "left", "right", "none"
                "flow_vectors": {            # Summarized flow for activity classifier
                    "upper_mean_dx": float,
                    "upper_mean_dy": float,
                    "lower_mean_dx": float,
                    "lower_mean_dy": float
                }
            }
        
        Note:
            Objects with invalid or too-small bounding boxes will have
            motion_source="none" and zero magnitudes.
        """
        results = []
        frame_height, frame_width = prev_frame_gray.shape[:2]
        
        for obj in tracked_objects:
            equipment_id = obj.get('equipment_id', 'unknown')
            bbox = obj.get('bbox', [])
            
            # Validate bbox
            if len(bbox) != 4:
                logger.warning(f"Invalid bbox for {equipment_id}: {bbox}")
                results.append(self._create_empty_result(equipment_id))
                continue
            
            # Extract and clip bbox coordinates
            x1, y1, x2, y2 = self._clip_bbox(
                bbox, frame_width, frame_height
            )
            
            # Check if region is large enough for analysis
            region_width = x2 - x1
            region_height = y2 - y1
            
            if region_width < self.MIN_REGION_SIZE or region_height < self.MIN_REGION_SIZE:
                logger.debug(
                    f"Region too small for {equipment_id}: {region_width}x{region_height}"
                )
                results.append(self._create_empty_result(equipment_id))
                continue
            
            # Extract regions from both frames
            prev_region = prev_frame_gray[y1:y2, x1:x2]
            curr_region = curr_frame_gray[y1:y2, x1:x2]
            
            # Compute and analyze optical flow
            result = self._analyze_region_flow(
                prev_region, curr_region, equipment_id
            )
            results.append(result)
        
        return results
    
    def _clip_bbox(
        self,
        bbox: list,
        frame_width: int,
        frame_height: int
    ) -> tuple[int, int, int, int]:
        """
        Clip bounding box coordinates to frame boundaries.
        
        Args:
            bbox: [x1, y1, x2, y2] bounding box coordinates.
            frame_width: Width of the frame.
            frame_height: Height of the frame.
        
        Returns:
            Tuple of clipped (x1, y1, x2, y2) as integers.
        """
        x1 = max(0, int(bbox[0]))
        y1 = max(0, int(bbox[1]))
        x2 = min(frame_width, int(bbox[2]))
        y2 = min(frame_height, int(bbox[3]))
        
        return x1, y1, x2, y2
    
    def _analyze_region_flow(
        self,
        prev_region: np.ndarray,
        curr_region: np.ndarray,
        equipment_id: str
    ) -> dict:
        """
        Analyze optical flow in upper and lower sub-regions.
        
        This method splits the region into upper (arm/boom) and lower (base/tracks)
        sub-regions, computes optical flow for each, and classifies the motion.
        
        Args:
            prev_region: Previous frame region (grayscale).
            curr_region: Current frame region (grayscale).
            equipment_id: Equipment identifier for the result.
        
        Returns:
            Motion analysis result dictionary.
        """
        region_height = prev_region.shape[0]
        split_y = int(region_height * self.upper_region_ratio)
        
        # Split into upper and lower regions
        prev_upper = prev_region[:split_y, :]
        curr_upper = curr_region[:split_y, :]
        prev_lower = prev_region[split_y:, :]
        curr_lower = curr_region[split_y:, :]
        
        # Compute optical flow for each region
        upper_flow = self._compute_optical_flow(prev_upper, curr_upper)
        lower_flow = self._compute_optical_flow(prev_lower, curr_lower)
        
        # Calculate magnitudes and mean flow vectors
        upper_magnitude, upper_mean_dx, upper_mean_dy = self._compute_flow_stats(upper_flow)
        lower_magnitude, lower_mean_dx, lower_mean_dy = self._compute_flow_stats(lower_flow)
        
        # Classify motion source
        motion_source = self._classify_motion(upper_magnitude, lower_magnitude)
        
        # Determine dominant direction from the active region(s)
        dominant_direction = self._compute_dominant_direction(
            upper_magnitude, lower_magnitude,
            upper_mean_dx, upper_mean_dy,
            lower_mean_dx, lower_mean_dy
        )
        
        return {
            "equipment_id": equipment_id,
            "motion_source": motion_source,
            "upper_magnitude": float(upper_magnitude),
            "lower_magnitude": float(lower_magnitude),
            "dominant_direction": dominant_direction,
            "flow_vectors": {
                "upper_mean_dx": float(upper_mean_dx),
                "upper_mean_dy": float(upper_mean_dy),
                "lower_mean_dx": float(lower_mean_dx),
                "lower_mean_dy": float(lower_mean_dy)
            }
        }
    
    def _compute_optical_flow(
        self,
        prev_gray: np.ndarray,
        curr_gray: np.ndarray
    ) -> Optional[np.ndarray]:
        """
        Compute dense optical flow using Farneback method.
        
        Args:
            prev_gray: Previous frame region (grayscale, uint8).
            curr_gray: Current frame region (grayscale, uint8).
        
        Returns:
            Optical flow array of shape (H, W, 2) with (dx, dy) per pixel,
            or None if computation fails.
        """
        # Validate region size
        if prev_gray.size == 0 or curr_gray.size == 0:
            return None
        
        if prev_gray.shape[0] < 3 or prev_gray.shape[1] < 3:
            return None
        
        try:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray,
                curr_gray,
                None,
                pyr_scale=self.FARNEBACK_PARAMS['pyr_scale'],
                levels=self.FARNEBACK_PARAMS['levels'],
                winsize=self.FARNEBACK_PARAMS['winsize'],
                iterations=self.FARNEBACK_PARAMS['iterations'],
                poly_n=self.FARNEBACK_PARAMS['poly_n'],
                poly_sigma=self.FARNEBACK_PARAMS['poly_sigma'],
                flags=self.FARNEBACK_PARAMS['flags']
            )
            return flow
        except cv2.error as e:
            logger.error(f"Optical flow computation failed: {e}")
            return None
    
    def _compute_flow_stats(
        self,
        flow: Optional[np.ndarray]
    ) -> tuple[float, float, float]:
        """
        Compute flow statistics: mean magnitude and mean direction vectors.
        
        Args:
            flow: Optical flow array of shape (H, W, 2) or None.
        
        Returns:
            Tuple of (mean_magnitude, mean_dx, mean_dy).
        """
        if flow is None or flow.size == 0:
            return 0.0, 0.0, 0.0
        
        # Extract dx and dy components
        dx = flow[..., 0]
        dy = flow[..., 1]
        
        # Compute magnitude at each pixel
        magnitude = np.sqrt(dx**2 + dy**2)
        
        # Calculate mean values
        mean_magnitude = float(np.mean(magnitude))
        mean_dx = float(np.mean(dx))
        mean_dy = float(np.mean(dy))
        
        return mean_magnitude, mean_dx, mean_dy
    
    def _classify_motion(
        self,
        upper_magnitude: float,
        lower_magnitude: float
    ) -> str:
        """
        Classify motion source based on region magnitudes.
        
        Motion classification logic:
        - If both regions moving: "full_body" (whole machine traveling)
        - If only upper moving: "arm_only" (articulated motion - digging, swinging)
        - If only lower moving: "full_body" (driving with stationary arm)
        - If neither moving: "none" (stationary)
        
        Args:
            upper_magnitude: Mean optical flow magnitude in upper region.
            lower_magnitude: Mean optical flow magnitude in lower region.
        
        Returns:
            Motion source classification: "full_body", "arm_only", or "none".
        """
        upper_moving = upper_magnitude > self.magnitude_threshold
        lower_moving = lower_magnitude > self.magnitude_threshold
        
        if upper_moving and lower_moving:
            return "full_body"
        elif upper_moving and not lower_moving:
            return "arm_only"
        elif not upper_moving and lower_moving:
            return "full_body"
        else:
            return "none"
    
    def _compute_dominant_direction(
        self,
        upper_magnitude: float,
        lower_magnitude: float,
        upper_mean_dx: float,
        upper_mean_dy: float,
        lower_mean_dx: float,
        lower_mean_dy: float
    ) -> str:
        """
        Compute dominant motion direction from active regions.
        
        Direction is determined from the region with highest motion,
        using OpenCV coordinate system (y increases downward):
        - dy < 0: "up"
        - dy > 0: "down"
        - dx < 0: "left"
        - dx > 0: "right"
        
        Args:
            upper_magnitude: Mean magnitude in upper region.
            lower_magnitude: Mean magnitude in lower region.
            upper_mean_dx: Mean horizontal flow in upper region.
            upper_mean_dy: Mean vertical flow in upper region.
            lower_mean_dx: Mean horizontal flow in lower region.
            lower_mean_dy: Mean vertical flow in lower region.
        
        Returns:
            Dominant direction: "up", "down", "left", "right", or "none".
        """
        # Use flow from the region with higher motion
        if upper_magnitude >= lower_magnitude:
            dx, dy = upper_mean_dx, upper_mean_dy
            magnitude = upper_magnitude
        else:
            dx, dy = lower_mean_dx, lower_mean_dy
            magnitude = lower_magnitude
        
        # Check if motion is significant enough to determine direction
        if magnitude < self.magnitude_threshold:
            return "none"
        
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        
        # Determine dominant axis and direction
        if abs_dy > abs_dx:
            # Vertical motion dominant
            if dy < 0:
                return "up"
            else:
                return "down"
        elif abs_dx > abs_dy:
            # Horizontal motion dominant
            if dx < 0:
                return "left"
            else:
                return "right"
        else:
            # Equal or negligible motion
            return "none"
    
    def _create_empty_result(self, equipment_id: str) -> dict:
        """
        Create an empty motion result for invalid/skipped objects.
        
        Args:
            equipment_id: Equipment identifier.
        
        Returns:
            Motion result dict with "none" motion and zero values.
        """
        return {
            "equipment_id": equipment_id,
            "motion_source": "none",
            "upper_magnitude": 0.0,
            "lower_magnitude": 0.0,
            "dominant_direction": "none",
            "flow_vectors": {
                "upper_mean_dx": 0.0,
                "upper_mean_dy": 0.0,
                "lower_mean_dx": 0.0,
                "lower_mean_dy": 0.0
            }
        }
