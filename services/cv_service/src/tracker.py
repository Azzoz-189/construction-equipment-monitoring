"""
Equipment Tracking Module

This module provides multi-object tracking capabilities using ByteTrack
algorithm via the supervision library for tracking detected equipment
across video frames.
"""

import logging
from typing import Any

import numpy as np
import supervision as sv

# Configure module logger
logger = logging.getLogger(__name__)


class EquipmentTracker:
    """
    Equipment tracker using ByteTrack algorithm for multi-object tracking.
    
    This tracker maintains consistent identities for detected equipment
    across video frames, assigning friendly equipment IDs with class-based
    prefixes (e.g., "DT-001" for trucks, "VH-001" for cars).
    
    Attributes:
        tracker: ByteTrack tracker instance from supervision library.
        equipment_id_prefix: Mapping of class names to ID prefixes.
        track_to_equipment_id: Mapping from internal track IDs to equipment IDs.
        class_counters: Per-class counters for generating sequential IDs.
        track_classes: Mapping from track IDs to their equipment classes.
    """
    
    def __init__(self, config: dict) -> None:
        """
        Initialize ByteTrack tracker via supervision library.
        
        Args:
            config: Configuration dictionary with keys:
                - track_thresh: Detection confidence threshold for track activation
                - track_buffer: Number of frames to keep lost tracks alive
                - match_thresh: IOU threshold for matching detections to tracks
                - equipment_id_prefix: Dict mapping class names to ID prefixes
                  (e.g., {truck: "DT", car: "VH", bus: "BU", default: "EQ"})
        
        Raises:
            ValueError: If required config keys are missing.
        """
        logger.info("Initializing EquipmentTracker...")
        
        # Validate required config keys
        required_keys = ['track_thresh', 'track_buffer', 'match_thresh', 'equipment_id_prefix']
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise ValueError(f"Missing required config keys: {missing_keys}")
        
        # Store configuration
        self.equipment_id_prefix = config['equipment_id_prefix']
        
        # Initialize ByteTrack tracker
        self.tracker = sv.ByteTrack(
            track_activation_threshold=config['track_thresh'],
            lost_track_buffer=config['track_buffer'],
            minimum_matching_threshold=config['match_thresh']
        )
        
        # Mapping from internal track_id to friendly equipment_id
        # This ensures consistent IDs across frames
        self.track_to_equipment_id: dict[int, str] = {}
        
        # Mapping from track_id to equipment class name
        self.track_classes: dict[int, str] = {}
        
        # Per-class counters for generating sequential equipment IDs
        self.class_counters: dict[str, int] = {}
        
        logger.info(
            f"EquipmentTracker initialized - "
            f"track_thresh: {config['track_thresh']}, "
            f"track_buffer: {config['track_buffer']}, "
            f"match_thresh: {config['match_thresh']}"
        )
    
    def _get_equipment_id_prefix(self, class_name: str) -> str:
        """
        Get the equipment ID prefix for a given class name.
        
        Args:
            class_name: The equipment class name (e.g., "truck", "car")
        
        Returns:
            The prefix string for the equipment ID (e.g., "DT" for truck)
        """
        return self.equipment_id_prefix.get(
            class_name, 
            self.equipment_id_prefix.get('default', 'EQ')
        )
    
    def _generate_equipment_id(self, class_name: str) -> str:
        """
        Generate a new unique equipment ID for a given class.
        
        The ID format is "{PREFIX}-{NUMBER:03d}" where PREFIX is determined
        by the equipment class and NUMBER is a sequential counter.
        
        Args:
            class_name: The equipment class name (e.g., "truck", "car")
        
        Returns:
            A unique equipment ID string (e.g., "DT-001", "VH-002")
        """
        prefix = self._get_equipment_id_prefix(class_name)
        
        # Initialize counter for this class if not exists
        if class_name not in self.class_counters:
            self.class_counters[class_name] = 0
        
        # Increment counter and generate ID
        self.class_counters[class_name] += 1
        equipment_id = f"{prefix}-{self.class_counters[class_name]:03d}"
        
        logger.debug(f"Generated new equipment ID: {equipment_id} for class: {class_name}")
        
        return equipment_id
    
    def _detections_to_sv_format(
        self, 
        detections: list[dict[str, Any]]
    ) -> tuple[sv.Detections, list[str]]:
        """
        Convert detection dictionaries to supervision Detections format.
        
        Args:
            detections: List of detection dicts from EquipmentDetector
        
        Returns:
            Tuple of (sv.Detections object, list of class names)
        """
        if not detections:
            # Return empty detections
            return sv.Detections.empty(), []
        
        # Extract arrays from detection dicts
        bboxes = np.array([d['bbox'] for d in detections], dtype=np.float32)
        confidences = np.array([d['confidence'] for d in detections], dtype=np.float32)
        class_ids = np.array([d['class_id'] for d in detections], dtype=int)
        class_names = [d['class_name'] for d in detections]
        
        # Create supervision Detections object
        sv_detections = sv.Detections(
            xyxy=bboxes,
            confidence=confidences,
            class_id=class_ids
        )
        
        return sv_detections, class_names
    
    def update(
        self, 
        detections: list[dict[str, Any]], 
        frame: np.ndarray
    ) -> list[dict[str, Any]]:
        """
        Update tracker with new detections.
        
        Processes new detections, updates the ByteTrack tracker, and returns
        tracked objects with consistent equipment IDs across frames.
        
        Args:
            detections: List of detection dicts from EquipmentDetector, each with:
                - bbox: [x1, y1, x2, y2] pixel coordinates
                - confidence: Detection confidence score
                - class_id: COCO class ID
                - class_name: Friendly class name
            frame: Current video frame as numpy array (used by tracker for dimensions)
        
        Returns:
            List of tracked object dictionaries, each containing:
                - equipment_id: Unique friendly ID (e.g., "DT-001")
                - equipment_class: Equipment class name (e.g., "truck")
                - bbox: [x1, y1, x2, y2] pixel coordinates
                - confidence: Detection confidence score
                - track_id: Internal ByteTrack tracker ID
        
        Example:
            >>> tracker = EquipmentTracker(config)
            >>> tracked = tracker.update(detections, frame)
            >>> for obj in tracked:
            ...     print(f"{obj['equipment_id']}: {obj['equipment_class']}")
        """
        if frame is None or frame.size == 0:
            logger.warning("Received empty or None frame, returning empty tracks")
            return []
        
        # Convert detections to supervision format
        sv_detections, class_names = self._detections_to_sv_format(detections)
        
        # Handle empty detections
        if len(sv_detections) == 0:
            logger.debug("No detections to track")
            return []
        
        # Update ByteTrack tracker
        try:
            tracked_detections = self.tracker.update_with_detections(sv_detections)
        except Exception as e:
            logger.error(f"Tracker update failed: {e}")
            return []
        
        # Process tracked objects
        tracked_objects = []
        
        # Check if there are any tracked detections
        if tracked_detections is None or len(tracked_detections) == 0:
            logger.debug("No tracks after update")
            return tracked_objects
        
        # Get tracker IDs (ByteTrack assigns these)
        tracker_ids = tracked_detections.tracker_id
        
        if tracker_ids is None:
            logger.debug("No tracker IDs assigned")
            return tracked_objects
        
        # Process each tracked detection
        for i, track_id in enumerate(tracker_ids):
            track_id = int(track_id)
            
            # Get detection data
            bbox = tracked_detections.xyxy[i].tolist()
            confidence = float(tracked_detections.confidence[i]) if tracked_detections.confidence is not None else 0.0
            
            # Find the corresponding class name
            # Match tracked detection back to original detection by bbox proximity
            class_name = self._find_class_for_tracked_detection(
                tracked_detections.xyxy[i], 
                detections
            )
            
            # Check if this track already has an equipment ID assigned
            if track_id not in self.track_to_equipment_id:
                # New track - assign equipment ID
                equipment_id = self._generate_equipment_id(class_name)
                self.track_to_equipment_id[track_id] = equipment_id
                self.track_classes[track_id] = class_name
                logger.info(f"New track assigned: track_id={track_id} -> equipment_id={equipment_id}")
            else:
                # Existing track - use existing equipment ID
                equipment_id = self.track_to_equipment_id[track_id]
                class_name = self.track_classes.get(track_id, class_name)
            
            tracked_object = {
                "equipment_id": equipment_id,
                "equipment_class": class_name,
                "bbox": bbox,
                "confidence": confidence,
                "track_id": track_id
            }
            tracked_objects.append(tracked_object)
        
        logger.debug(f"Tracking {len(tracked_objects)} equipment objects")
        
        return tracked_objects
    
    def _find_class_for_tracked_detection(
        self, 
        tracked_bbox: np.ndarray, 
        original_detections: list[dict[str, Any]]
    ) -> str:
        """
        Find the class name for a tracked detection by matching bboxes.
        
        Args:
            tracked_bbox: Bounding box from tracked detection [x1, y1, x2, y2]
            original_detections: Original detection list with class names
        
        Returns:
            The class name of the best matching detection, or "unknown"
        """
        if not original_detections:
            return "unknown"
        
        best_match_idx = -1
        best_iou = 0.0
        
        for idx, det in enumerate(original_detections):
            det_bbox = np.array(det['bbox'])
            iou = self._compute_iou(tracked_bbox, det_bbox)
            if iou > best_iou:
                best_iou = iou
                best_match_idx = idx
        
        if best_match_idx >= 0 and best_iou > 0.5:
            return original_detections[best_match_idx]['class_name']
        
        return "unknown"
    
    @staticmethod
    def _compute_iou(bbox1: np.ndarray, bbox2: np.ndarray) -> float:
        """
        Compute Intersection over Union (IoU) between two bounding boxes.
        
        Args:
            bbox1: First bounding box [x1, y1, x2, y2]
            bbox2: Second bounding box [x1, y1, x2, y2]
        
        Returns:
            IoU score between 0 and 1
        """
        # Compute intersection
        x1 = max(bbox1[0], bbox2[0])
        y1 = max(bbox1[1], bbox2[1])
        x2 = min(bbox1[2], bbox2[2])
        y2 = min(bbox1[3], bbox2[3])
        
        intersection = max(0, x2 - x1) * max(0, y2 - y1)
        
        # Compute union
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        union = area1 + area2 - intersection
        
        if union <= 0:
            return 0.0
        
        return intersection / union
    
    def reset(self) -> None:
        """
        Reset the tracker state.
        
        Clears all track mappings and counters, effectively starting fresh.
        Useful when processing a new video or after significant scene changes.
        """
        logger.info("Resetting tracker state")
        self.tracker.reset()
        self.track_to_equipment_id.clear()
        self.track_classes.clear()
        self.class_counters.clear()
