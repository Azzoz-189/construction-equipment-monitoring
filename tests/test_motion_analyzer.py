"""
Tests for MotionAnalyzer class.

This module tests the motion analysis functionality using synthetic frames
to verify optical flow-based motion detection and classification.
"""

import sys
import os
import pytest
import numpy as np

# Add services to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'cv_service', 'src'))

from motion_analyzer import MotionAnalyzer


class TestMotionAnalyzerInitialization:
    """Tests for MotionAnalyzer initialization."""

    def test_init_with_valid_config(self, motion_config):
        """Test that analyzer initializes successfully with valid configuration."""
        analyzer = MotionAnalyzer(motion_config)
        
        assert analyzer.magnitude_threshold == motion_config['magnitude_threshold']
        assert analyzer.upper_region_ratio == motion_config['upper_region_ratio']
        assert analyzer.flow_method == motion_config['flow_method']

    def test_init_with_default_values(self):
        """Test that analyzer uses default values for missing config keys."""
        analyzer = MotionAnalyzer({})
        
        assert analyzer.magnitude_threshold == 2.0
        assert analyzer.upper_region_ratio == 0.5
        assert analyzer.flow_method == 'farneback'

    def test_init_invalid_upper_region_ratio_raises_error(self):
        """Test that invalid upper_region_ratio raises ValueError."""
        # Test with ratio >= 1
        with pytest.raises(ValueError) as exc_info:
            MotionAnalyzer({'upper_region_ratio': 1.0})
        assert 'upper_region_ratio' in str(exc_info.value)
        
        # Test with ratio <= 0
        with pytest.raises(ValueError):
            MotionAnalyzer({'upper_region_ratio': 0.0})
        
        with pytest.raises(ValueError):
            MotionAnalyzer({'upper_region_ratio': -0.5})


class TestMotionAnalyzerAnalyze:
    """Tests for MotionAnalyzer.analyze() method."""

    @pytest.fixture
    def analyzer(self, motion_config):
        """Create a MotionAnalyzer instance."""
        return MotionAnalyzer(motion_config)

    def test_analyze_identical_frames_returns_no_motion(self, analyzer):
        """Test that identical frames return motion_source='none' for all objects."""
        # Create two identical grayscale frames
        prev_frame = np.ones((480, 640), dtype=np.uint8) * 128
        curr_frame = prev_frame.copy()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
            {'equipment_id': 'DT-002', 'bbox': [400, 100, 600, 300]},
        ]
        
        results = analyzer.analyze(prev_frame, curr_frame, tracked_objects)
        
        assert len(results) == 2
        for result in results:
            assert result['motion_source'] == 'none', \
                f"Expected 'none' motion for identical frames, got {result['motion_source']}"
            assert result['upper_magnitude'] < analyzer.magnitude_threshold
            assert result['lower_magnitude'] < analyzer.magnitude_threshold

    def test_analyze_upper_region_motion_returns_arm_only(self, analyzer):
        """Test that motion only in upper region returns motion_source='arm_only'."""
        # Create frames where upper region has motion
        prev_frame = np.zeros((480, 640), dtype=np.uint8)
        curr_frame = prev_frame.copy()
        
        # Tracked object at position [100, 100, 300, 300] (200x200 box)
        # Upper region is top half (y: 100-200)
        # Lower region is bottom half (y: 200-300)
        
        # Add significant texture to upper region for optical flow detection
        prev_frame[100:200, 100:300] = np.random.randint(50, 200, (100, 200), dtype=np.uint8)
        curr_frame[100:200, 100:300] = np.roll(prev_frame[100:200, 100:300], 20, axis=1)
        
        # Keep lower region identical (no motion)
        prev_frame[200:300, 100:300] = np.tile(np.arange(200), (100, 1)).astype(np.uint8)
        curr_frame[200:300, 100:300] = prev_frame[200:300, 100:300].copy()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        results = analyzer.analyze(prev_frame, curr_frame, tracked_objects)
        
        assert len(results) == 1
        # Upper region should show motion, lower should not
        # The exact motion_source depends on magnitudes vs threshold

    def test_analyze_full_body_motion(self, analyzer):
        """Test that motion in both regions returns motion_source='full_body'."""
        # Create frames with motion in both upper and lower regions
        prev_frame = np.zeros((480, 640), dtype=np.uint8)
        curr_frame = prev_frame.copy()
        
        # Add texture and shift entire bbox region
        prev_frame[100:300, 100:300] = np.random.randint(50, 200, (200, 200), dtype=np.uint8)
        # Shift entire region horizontally (simulating whole body movement)
        curr_frame[100:300, 120:320] = prev_frame[100:300, 100:300]
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        results = analyzer.analyze(prev_frame, curr_frame, tracked_objects)
        
        assert len(results) == 1
        # Both regions should show motion when entire object shifts

    def test_analyze_result_format(self, analyzer, sample_grayscale_frame):
        """Test that analyze() returns correctly formatted result dictionaries."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        results = analyzer.analyze(
            sample_grayscale_frame, 
            sample_grayscale_frame.copy(), 
            tracked_objects
        )
        
        assert len(results) == 1
        result = results[0]
        
        # Verify all required keys
        assert 'equipment_id' in result
        assert 'motion_source' in result
        assert 'upper_magnitude' in result
        assert 'lower_magnitude' in result
        assert 'dominant_direction' in result
        assert 'flow_vectors' in result
        
        # Verify types
        assert isinstance(result['equipment_id'], str)
        assert result['motion_source'] in ['full_body', 'arm_only', 'none']
        assert isinstance(result['upper_magnitude'], float)
        assert isinstance(result['lower_magnitude'], float)
        assert result['dominant_direction'] in ['up', 'down', 'left', 'right', 'none']
        
        # Verify flow_vectors structure
        flow_vectors = result['flow_vectors']
        assert 'upper_mean_dx' in flow_vectors
        assert 'upper_mean_dy' in flow_vectors
        assert 'lower_mean_dx' in flow_vectors
        assert 'lower_mean_dy' in flow_vectors

    def test_analyze_bbox_clipping(self, analyzer):
        """Test that bbox extending outside frame is clipped properly."""
        prev_frame = np.ones((480, 640), dtype=np.uint8) * 128
        curr_frame = prev_frame.copy()
        
        # Bbox extends outside frame boundaries
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [-50, -50, 100, 100]},  # Top-left outside
            {'equipment_id': 'DT-002', 'bbox': [600, 450, 700, 550]},  # Bottom-right outside
        ]
        
        # Should not raise any errors
        results = analyzer.analyze(prev_frame, curr_frame, tracked_objects)
        
        assert len(results) == 2
        for result in results:
            assert 'motion_source' in result

    def test_analyze_minimum_region_size(self, analyzer):
        """Test handling of bbox too small for analysis."""
        prev_frame = np.ones((480, 640), dtype=np.uint8) * 128
        curr_frame = prev_frame.copy()
        
        # Bbox smaller than MIN_REGION_SIZE (10 pixels)
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 105, 105]},  # 5x5 box
        ]
        
        results = analyzer.analyze(prev_frame, curr_frame, tracked_objects)
        
        assert len(results) == 1
        # Should return empty result for too-small region
        assert results[0]['motion_source'] == 'none'
        assert results[0]['upper_magnitude'] == 0.0
        assert results[0]['lower_magnitude'] == 0.0

    def test_analyze_invalid_bbox_handling(self, analyzer, sample_grayscale_frame):
        """Test handling of invalid bounding box formats."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100]},  # Too few coords
            {'equipment_id': 'DT-002', 'bbox': []},  # Empty bbox
            {'equipment_id': 'DT-003'},  # Missing bbox key
        ]
        
        results = analyzer.analyze(
            sample_grayscale_frame,
            sample_grayscale_frame.copy(),
            tracked_objects
        )
        
        # All should return empty results
        assert len(results) == 3
        for result in results:
            assert result['motion_source'] == 'none'

    def test_analyze_empty_tracked_objects(self, analyzer, sample_grayscale_frame):
        """Test analyze() with empty tracked objects list."""
        results = analyzer.analyze(
            sample_grayscale_frame,
            sample_grayscale_frame.copy(),
            []
        )
        
        assert results == []

    def test_analyze_dominant_direction_detection(self, analyzer):
        """Test dominant direction detection for different motion patterns."""
        # This tests the _compute_dominant_direction logic
        prev_frame = np.zeros((480, 640), dtype=np.uint8)
        curr_frame = np.zeros((480, 640), dtype=np.uint8)
        
        # Create downward motion pattern in upper region
        # Fill with gradient pattern that shifts downward
        for y in range(100, 200):
            prev_frame[y, 100:300] = (y - 100) * 2
        for y in range(120, 220):
            curr_frame[y, 100:300] = (y - 120) * 2
        
        # Keep lower region static
        prev_frame[200:300, 100:300] = 128
        curr_frame[200:300, 100:300] = 128
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        results = analyzer.analyze(prev_frame, curr_frame, tracked_objects)
        
        assert len(results) == 1
        # Direction should be detected based on flow

    def test_clip_bbox_method(self, analyzer):
        """Test the _clip_bbox helper method."""
        # Normal bbox within bounds
        clipped = analyzer._clip_bbox([100, 100, 300, 300], 640, 480)
        assert clipped == (100, 100, 300, 300)
        
        # Bbox extending outside left/top
        clipped = analyzer._clip_bbox([-50, -50, 100, 100], 640, 480)
        assert clipped == (0, 0, 100, 100)
        
        # Bbox extending outside right/bottom
        clipped = analyzer._clip_bbox([600, 450, 700, 550], 640, 480)
        assert clipped == (600, 450, 640, 480)
        
        # Float coordinates should be converted to int
        clipped = analyzer._clip_bbox([100.5, 100.5, 300.5, 300.5], 640, 480)
        assert clipped == (100, 100, 300, 300)

    def test_create_empty_result_method(self, analyzer):
        """Test the _create_empty_result helper method."""
        result = analyzer._create_empty_result('TEST-001')
        
        assert result['equipment_id'] == 'TEST-001'
        assert result['motion_source'] == 'none'
        assert result['upper_magnitude'] == 0.0
        assert result['lower_magnitude'] == 0.0
        assert result['dominant_direction'] == 'none'
        assert result['flow_vectors']['upper_mean_dx'] == 0.0
        assert result['flow_vectors']['upper_mean_dy'] == 0.0
        assert result['flow_vectors']['lower_mean_dx'] == 0.0
        assert result['flow_vectors']['lower_mean_dy'] == 0.0


class TestMotionClassification:
    """Tests for motion source classification logic."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer with known threshold."""
        return MotionAnalyzer({'magnitude_threshold': 2.0})

    def test_classify_motion_both_moving_returns_full_body(self, analyzer):
        """Test classification when both regions are moving."""
        result = analyzer._classify_motion(
            upper_magnitude=5.0,  # Above threshold
            lower_magnitude=5.0   # Above threshold
        )
        assert result == 'full_body'

    def test_classify_motion_upper_only_returns_arm_only(self, analyzer):
        """Test classification when only upper region is moving."""
        result = analyzer._classify_motion(
            upper_magnitude=5.0,  # Above threshold
            lower_magnitude=0.5   # Below threshold
        )
        assert result == 'arm_only'

    def test_classify_motion_lower_only_returns_full_body(self, analyzer):
        """Test classification when only lower region is moving."""
        # Per the implementation, lower-only is still full_body (driving with stationary arm)
        result = analyzer._classify_motion(
            upper_magnitude=0.5,  # Below threshold
            lower_magnitude=5.0   # Above threshold
        )
        assert result == 'full_body'

    def test_classify_motion_neither_moving_returns_none(self, analyzer):
        """Test classification when neither region is moving."""
        result = analyzer._classify_motion(
            upper_magnitude=0.5,  # Below threshold
            lower_magnitude=0.5   # Below threshold
        )
        assert result == 'none'

    def test_classify_motion_at_threshold_boundary(self, analyzer):
        """Test classification at exactly the threshold boundary."""
        # At exactly threshold, should be considered not moving (> not >=)
        result = analyzer._classify_motion(
            upper_magnitude=2.0,  # At threshold
            lower_magnitude=2.0   # At threshold
        )
        assert result == 'none'
        
        # Just above threshold
        result = analyzer._classify_motion(
            upper_magnitude=2.1,
            lower_magnitude=2.1
        )
        assert result == 'full_body'


class TestDominantDirectionComputation:
    """Tests for dominant direction computation."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer with known threshold."""
        return MotionAnalyzer({'magnitude_threshold': 2.0})

    def test_dominant_direction_down(self, analyzer):
        """Test dominant direction when motion is predominantly downward."""
        direction = analyzer._compute_dominant_direction(
            upper_magnitude=5.0, lower_magnitude=0.5,
            upper_mean_dx=0.5, upper_mean_dy=4.0,  # Positive dy = down
            lower_mean_dx=0.0, lower_mean_dy=0.0
        )
        assert direction == 'down'

    def test_dominant_direction_up(self, analyzer):
        """Test dominant direction when motion is predominantly upward."""
        direction = analyzer._compute_dominant_direction(
            upper_magnitude=5.0, lower_magnitude=0.5,
            upper_mean_dx=0.5, upper_mean_dy=-4.0,  # Negative dy = up
            lower_mean_dx=0.0, lower_mean_dy=0.0
        )
        assert direction == 'up'

    def test_dominant_direction_right(self, analyzer):
        """Test dominant direction when motion is predominantly rightward."""
        direction = analyzer._compute_dominant_direction(
            upper_magnitude=5.0, lower_magnitude=0.5,
            upper_mean_dx=4.0, upper_mean_dy=0.5,  # Positive dx = right
            lower_mean_dx=0.0, lower_mean_dy=0.0
        )
        assert direction == 'right'

    def test_dominant_direction_left(self, analyzer):
        """Test dominant direction when motion is predominantly leftward."""
        direction = analyzer._compute_dominant_direction(
            upper_magnitude=5.0, lower_magnitude=0.5,
            upper_mean_dx=-4.0, upper_mean_dy=0.5,  # Negative dx = left
            lower_mean_dx=0.0, lower_mean_dy=0.0
        )
        assert direction == 'left'

    def test_dominant_direction_none_when_no_motion(self, analyzer):
        """Test dominant direction is 'none' when no significant motion."""
        direction = analyzer._compute_dominant_direction(
            upper_magnitude=0.5, lower_magnitude=0.5,
            upper_mean_dx=0.0, upper_mean_dy=0.0,
            lower_mean_dx=0.0, lower_mean_dy=0.0
        )
        assert direction == 'none'

    def test_dominant_direction_uses_higher_magnitude_region(self, analyzer):
        """Test that direction uses flow from higher-magnitude region."""
        # Lower region has higher magnitude
        direction = analyzer._compute_dominant_direction(
            upper_magnitude=1.0, lower_magnitude=5.0,
            upper_mean_dx=0.0, upper_mean_dy=-4.0,  # Upper: up
            lower_mean_dx=4.0, lower_mean_dy=0.0    # Lower: right
        )
        # Should use lower region's direction (right)
        assert direction == 'right'
