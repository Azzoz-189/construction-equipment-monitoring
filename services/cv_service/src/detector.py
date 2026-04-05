"""
Equipment Detection Module

This module provides equipment detection capabilities using YOLOv8 model
for identifying vehicles/equipment (cars, buses, trucks) in video frames.
"""

import logging
from typing import Any

import numpy as np
from ultralytics import YOLO

# Configure module logger
logger = logging.getLogger(__name__)


class EquipmentDetector:
    """
    Equipment detector using YOLOv8 model for detecting vehicles/equipment.
    
    This detector is configured to identify specific classes of vehicles
    (car, bus, truck) from COCO dataset classes and returns detection
    results with bounding boxes, confidence scores, and class information.
    
    Attributes:
        model: The loaded YOLOv8 model instance.
        confidence_threshold: Minimum confidence score for valid detections.
        device: Computing device for inference (cpu/cuda).
        input_size: Input image size for the model.
        target_classes: List of COCO class IDs to detect.
        class_names: Mapping from class IDs to friendly names.
    """
    
    def __init__(self, config: dict) -> None:
        """
        Initialize YOLOv8n model for equipment detection.
        
        Args:
            config: Configuration dictionary with keys:
                - model: Path to YOLOv8 model weights (e.g., "yolov8n.pt")
                - confidence_threshold: Minimum confidence for detections (0-1)
                - device: Computing device ("cpu" or "cuda")
                - input_size: Input image size for inference (e.g., 640)
                - target_classes: List of COCO class IDs to detect (e.g., [2, 5, 7])
                - class_names: Dict mapping class IDs to names (e.g., {2: "car"})
        
        Raises:
            ValueError: If required config keys are missing.
            RuntimeError: If model fails to load.
        """
        logger.info("Initializing EquipmentDetector...")
        
        # Validate required config keys
        required_keys = ['model', 'confidence_threshold', 'device', 
                         'input_size', 'target_classes', 'class_names']
        missing_keys = [key for key in required_keys if key not in config]
        if missing_keys:
            raise ValueError(f"Missing required config keys: {missing_keys}")
        
        # Store configuration
        self.confidence_threshold = config['confidence_threshold']
        self.device = config['device']
        self.input_size = config['input_size']
        self.target_classes = set(config['target_classes'])
        self.class_names = config['class_names']
        
        # Load YOLOv8 model
        model_path = config['model']
        try:
            logger.info(f"Loading YOLOv8 model from: {model_path}")
            self.model = YOLO(model_path)
            logger.info(f"Model loaded successfully on device: {self.device}")
        except Exception as e:
            logger.error(f"Failed to load YOLOv8 model: {e}")
            raise RuntimeError(f"Failed to load model '{model_path}': {e}") from e
        
        logger.info(
            f"EquipmentDetector initialized - "
            f"threshold: {self.confidence_threshold}, "
            f"target_classes: {self.target_classes}, "
            f"device: {self.device}"
        )
    
    def detect(self, frame: np.ndarray) -> list[dict[str, Any]]:
        """
        Run detection on a single frame.
        
        Performs object detection using YOLOv8 and filters results to only
        include target equipment classes with confidence above threshold.
        
        Args:
            frame: Input image as numpy array in BGR format (H, W, C).
        
        Returns:
            List of detection dictionaries, each containing:
                - bbox: Bounding box as [x1, y1, x2, y2] in pixel coordinates
                - confidence: Detection confidence score (0-1)
                - class_id: COCO class ID (int)
                - class_name: Friendly class name (e.g., "truck", "car", "bus")
            
            Returns empty list if no valid detections found.
        
        Example:
            >>> detector = EquipmentDetector(config)
            >>> detections = detector.detect(frame)
            >>> for det in detections:
            ...     print(f"{det['class_name']}: {det['confidence']:.2f}")
        """
        if frame is None or frame.size == 0:
            logger.warning("Received empty or None frame, returning empty detections")
            return []
        
        # Run inference with YOLOv8
        # YOLOv8 handles resizing internally based on imgsz parameter
        try:
            results = self.model(
                frame,
                imgsz=self.input_size,
                device=self.device,
                verbose=False  # Suppress YOLO's default output
            )
        except Exception as e:
            logger.error(f"Detection inference failed: {e}")
            return []
        
        # Parse detection results
        detections = []
        
        # results is a list, get the first (and only) result for single image
        if not results or len(results) == 0:
            return detections
        
        result = results[0]
        
        # Check if there are any detections
        if result.boxes is None or len(result.boxes) == 0:
            logger.debug("No detections in frame")
            return detections
        
        # Extract detection data
        boxes = result.boxes.xyxy.cpu().numpy()  # [x1, y1, x2, y2]
        confidences = result.boxes.conf.cpu().numpy()
        class_ids = result.boxes.cls.cpu().numpy().astype(int)
        
        # Filter and process detections
        for bbox, confidence, class_id in zip(boxes, confidences, class_ids):
            # Skip if not a target class
            if class_id not in self.target_classes:
                continue
            
            # Skip if below confidence threshold
            if confidence < self.confidence_threshold:
                continue
            
            # Get friendly class name
            class_name = self.class_names.get(class_id, f"class_{class_id}")
            
            detection = {
                "bbox": bbox.tolist(),  # [x1, y1, x2, y2] as list
                "confidence": float(confidence),
                "class_id": int(class_id),
                "class_name": class_name
            }
            detections.append(detection)
        
        logger.debug(f"Detected {len(detections)} equipment objects in frame")
        
        return detections
