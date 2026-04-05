"""
Shared pytest fixtures for CV service tests.

This module provides common fixtures for loading configuration and
creating test data used across all test modules.
"""

import os
import pytest
import yaml
import numpy as np


@pytest.fixture
def config():
    """
    Load test configuration from settings.yaml.
    
    Returns:
        dict: Full configuration dictionary from settings.yaml
    """
    config_path = os.path.join(
        os.path.dirname(__file__), '..', 'config', 'settings.yaml'
    )
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture
def detection_config(config):
    """
    Extract detection configuration section.
    
    Returns:
        dict: Detection configuration with model, threshold, device, etc.
    """
    return config['detection']


@pytest.fixture
def tracking_config(config):
    """
    Extract tracking configuration section.
    
    Returns:
        dict: Tracking configuration with thresholds and ID prefixes.
    """
    return config['tracking']


@pytest.fixture
def motion_config(config):
    """
    Extract motion analysis configuration section.
    
    Returns:
        dict: Motion configuration with magnitude threshold, region ratio, etc.
    """
    return config['motion']


@pytest.fixture
def activity_config(config):
    """
    Extract activity classification configuration section.
    
    Returns:
        dict: Activity configuration with smoothing window and thresholds.
    """
    return config['activity']


@pytest.fixture
def sample_frame():
    """
    Create a sample BGR frame for testing.
    
    Returns:
        np.ndarray: 480x640x3 BGR frame filled with gray color.
    """
    return np.ones((480, 640, 3), dtype=np.uint8) * 128


@pytest.fixture
def sample_grayscale_frame():
    """
    Create a sample grayscale frame for testing.
    
    Returns:
        np.ndarray: 480x640 grayscale frame filled with gray value.
    """
    return np.ones((480, 640), dtype=np.uint8) * 128


@pytest.fixture
def sample_detection():
    """
    Create a sample detection result.
    
    Returns:
        dict: Detection with bbox, confidence, class_id, and class_name.
    """
    return {
        "bbox": [100.0, 100.0, 300.0, 300.0],
        "confidence": 0.85,
        "class_id": 7,
        "class_name": "truck"
    }


@pytest.fixture
def sample_tracked_object():
    """
    Create a sample tracked object.
    
    Returns:
        dict: Tracked object with equipment_id and bbox.
    """
    return {
        "equipment_id": "DT-001",
        "bbox": [100, 100, 300, 300],
        "class_name": "truck",
        "confidence": 0.85
    }


@pytest.fixture
def sample_motion_result():
    """
    Create a sample motion analysis result.
    
    Returns:
        dict: Motion result with motion_source, magnitudes, and flow vectors.
    """
    return {
        "equipment_id": "DT-001",
        "motion_source": "arm_only",
        "upper_magnitude": 5.0,
        "lower_magnitude": 0.5,
        "dominant_direction": "down",
        "flow_vectors": {
            "upper_mean_dx": 0.5,
            "upper_mean_dy": 4.5,
            "lower_mean_dx": 0.1,
            "lower_mean_dy": 0.1
        }
    }


@pytest.fixture
def sample_activity_result():
    """
    Create a sample activity classification result.
    
    Returns:
        dict: Activity result with state, activity, and motion_source.
    """
    return {
        "current_state": "ACTIVE",
        "current_activity": "DIGGING",
        "activity": "DIGGING",
        "motion_source": "arm_only"
    }
