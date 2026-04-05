"""
Tests for EquipmentDetector class.

This module tests the equipment detection functionality using mocked YOLO model
to ensure tests can run without actual model weights.
"""

import sys
import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

# Add services to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'cv_service', 'src'))


class TestEquipmentDetectorInitialization:
    """Tests for EquipmentDetector initialization."""

    @patch('detector.YOLO')
    def test_init_with_valid_config(self, mock_yolo, detection_config):
        """Test that detector initializes successfully with valid configuration."""
        from detector import EquipmentDetector
        
        mock_yolo.return_value = MagicMock()
        
        detector = EquipmentDetector(detection_config)
        
        assert detector.confidence_threshold == detection_config['confidence_threshold']
        assert detector.device == detection_config['device']
        assert detector.input_size == detection_config['input_size']
        assert detector.target_classes == set(detection_config['target_classes'])
        mock_yolo.assert_called_once_with(detection_config['model'])

    @patch('detector.YOLO')
    def test_init_missing_required_keys_raises_value_error(self, mock_yolo):
        """Test that missing config keys raise ValueError."""
        from detector import EquipmentDetector
        
        incomplete_config = {
            'model': 'yolov8n.pt',
            'confidence_threshold': 0.4
            # Missing: device, input_size, target_classes, class_names
        }
        
        with pytest.raises(ValueError) as exc_info:
            EquipmentDetector(incomplete_config)
        
        assert "Missing required config keys" in str(exc_info.value)

    @patch('detector.YOLO')
    def test_init_model_load_failure_raises_runtime_error(self, mock_yolo, detection_config):
        """Test that model load failure raises RuntimeError."""
        from detector import EquipmentDetector
        
        mock_yolo.side_effect = Exception("Model not found")
        
        with pytest.raises(RuntimeError) as exc_info:
            EquipmentDetector(detection_config)
        
        assert "Failed to load model" in str(exc_info.value)


class TestEquipmentDetectorDetect:
    """Tests for EquipmentDetector.detect() method."""

    @pytest.fixture
    def mock_detector(self, detection_config):
        """Create a detector with mocked YOLO model."""
        with patch('detector.YOLO') as mock_yolo:
            mock_model = MagicMock()
            mock_yolo.return_value = mock_model
            
            from detector import EquipmentDetector
            detector = EquipmentDetector(detection_config)
            detector._mock_model = mock_model
            
            yield detector

    def test_detect_returns_correct_format(self, mock_detector, sample_frame):
        """Test that detect() returns correct detection dictionary format."""
        # Mock YOLO results
        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[100, 100, 300, 300]])
        mock_boxes.conf.cpu.return_value.numpy.return_value = np.array([0.85])
        mock_boxes.cls.cpu.return_value.numpy.return_value = np.array([7])
        
        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_result.boxes.__len__ = lambda self: 1
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(sample_frame)
        
        assert len(detections) == 1
        detection = detections[0]
        
        # Verify all required keys exist
        assert 'bbox' in detection
        assert 'confidence' in detection
        assert 'class_id' in detection
        assert 'class_name' in detection
        
        # Verify types
        assert isinstance(detection['bbox'], list)
        assert len(detection['bbox']) == 4
        assert isinstance(detection['confidence'], float)
        assert isinstance(detection['class_id'], int)
        assert isinstance(detection['class_name'], str)

    def test_detect_with_empty_frame_returns_empty_list(self, mock_detector):
        """Test that detect() handles empty or None frame gracefully."""
        # Test with None
        assert mock_detector.detect(None) == []
        
        # Test with empty array
        empty_frame = np.array([])
        assert mock_detector.detect(empty_frame) == []

    def test_detect_filters_by_target_classes(self, mock_detector, sample_frame):
        """Test that detect() only returns detections for target classes."""
        # Mock YOLO results with multiple classes (including non-target class 0=person)
        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu.return_value.numpy.return_value = np.array([
            [100, 100, 200, 200],  # Class 0 (person) - should be filtered
            [200, 200, 400, 400],  # Class 7 (truck) - should be kept
            [300, 100, 500, 300],  # Class 2 (car) - should be kept
        ])
        mock_boxes.conf.cpu.return_value.numpy.return_value = np.array([0.9, 0.8, 0.7])
        mock_boxes.cls.cpu.return_value.numpy.return_value = np.array([0, 7, 2])
        
        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_result.boxes.__len__ = lambda self: 3
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(sample_frame)
        
        # Should only have 2 detections (truck and car, not person)
        assert len(detections) == 2
        class_ids = [d['class_id'] for d in detections]
        assert 0 not in class_ids  # Person should be filtered out
        assert 7 in class_ids  # Truck should be present
        assert 2 in class_ids  # Car should be present

    def test_detect_filters_by_confidence_threshold(self, mock_detector, sample_frame):
        """Test that detect() filters out low confidence detections."""
        # Mock YOLO results with varying confidence
        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu.return_value.numpy.return_value = np.array([
            [100, 100, 200, 200],  # High confidence
            [200, 200, 400, 400],  # Below threshold
        ])
        mock_boxes.conf.cpu.return_value.numpy.return_value = np.array([0.85, 0.2])
        mock_boxes.cls.cpu.return_value.numpy.return_value = np.array([7, 7])
        
        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_result.boxes.__len__ = lambda self: 2
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(sample_frame)
        
        # Should only have 1 detection (high confidence one)
        assert len(detections) == 1
        assert detections[0]['confidence'] == 0.85

    def test_detect_no_detections_returns_empty_list(self, mock_detector, sample_frame):
        """Test that detect() returns empty list when no objects detected."""
        mock_result = MagicMock()
        mock_result.boxes = None
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(sample_frame)
        
        assert detections == []

    def test_detect_inference_error_returns_empty_list(self, mock_detector, sample_frame):
        """Test that detect() handles inference errors gracefully."""
        mock_detector._mock_model.side_effect = Exception("Inference failed")
        
        detections = mock_detector.detect(sample_frame)
        
        assert detections == []

    def test_detect_class_names_mapping(self, mock_detector, sample_frame):
        """Test that detect() correctly maps class IDs to friendly names."""
        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu.return_value.numpy.return_value = np.array([
            [100, 100, 200, 200],
            [200, 200, 400, 400],
            [300, 100, 500, 300],
        ])
        mock_boxes.conf.cpu.return_value.numpy.return_value = np.array([0.9, 0.8, 0.7])
        mock_boxes.cls.cpu.return_value.numpy.return_value = np.array([7, 2, 5])
        
        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_result.boxes.__len__ = lambda self: 3
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(sample_frame)
        
        class_names = {d['class_id']: d['class_name'] for d in detections}
        assert class_names[7] == 'truck'
        assert class_names[2] == 'car'
        assert class_names[5] == 'bus'

    def test_detect_with_synthetic_blank_frame(self, mock_detector):
        """Test detection with a synthetic blank frame created with numpy."""
        # Create a blank frame
        blank_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # Mock empty results
        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.__len__ = lambda self: 0
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(blank_frame)
        
        # Should return empty list for blank frame (no real objects)
        assert isinstance(detections, list)

    def test_detect_bbox_values_are_lists(self, mock_detector, sample_frame):
        """Test that bbox values are converted to lists (not numpy arrays)."""
        mock_boxes = MagicMock()
        mock_boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[100.5, 100.5, 300.5, 300.5]])
        mock_boxes.conf.cpu.return_value.numpy.return_value = np.array([0.85])
        mock_boxes.cls.cpu.return_value.numpy.return_value = np.array([7])
        
        mock_result = MagicMock()
        mock_result.boxes = mock_boxes
        mock_result.boxes.__len__ = lambda self: 1
        
        mock_detector._mock_model.return_value = [mock_result]
        
        detections = mock_detector.detect(sample_frame)
        
        assert isinstance(detections[0]['bbox'], list)
        assert all(isinstance(coord, float) for coord in detections[0]['bbox'])
