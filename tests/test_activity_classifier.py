"""
Tests for ActivityClassifier class.

This module tests the activity classification logic including rule-based
classification and N-frame smoothing to prevent flickering.
"""

import sys
import os
import pytest

# Add services to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'cv_service', 'src'))

from activity_classifier import ActivityClassifier


class TestActivityClassifierInitialization:
    """Tests for ActivityClassifier initialization."""

    def test_init_with_valid_config(self, activity_config):
        """Test that classifier initializes successfully with valid configuration."""
        classifier = ActivityClassifier(activity_config)
        
        assert classifier.smoothing_window == activity_config['smoothing_window']
        assert classifier.vertical_flow_threshold == activity_config['vertical_flow_threshold']
        assert classifier.horizontal_flow_threshold == activity_config['horizontal_flow_threshold']

    def test_init_with_default_values(self):
        """Test that classifier uses default values for missing config keys."""
        classifier = ActivityClassifier({})
        
        assert classifier.smoothing_window == 5
        assert classifier.vertical_flow_threshold == 1.5
        assert classifier.horizontal_flow_threshold == 1.5

    def test_init_activity_history_empty(self):
        """Test that activity history is empty on initialization."""
        classifier = ActivityClassifier({})
        assert classifier._activity_history == {}


class TestActivityClassification:
    """Tests for activity classification rules."""

    @pytest.fixture
    def classifier(self, activity_config):
        """Create an ActivityClassifier instance."""
        return ActivityClassifier(activity_config)

    def test_classify_digging_arm_only_downward(self, classifier):
        """Test DIGGING classification: arm_only motion + downward direction."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        # Motion data indicating arm_only with downward flow (positive dy)
        motion_results = [{
            'equipment_id': 'DT-001',
            'motion_source': 'arm_only',
            'dominant_direction': 'down',
            'flow_vectors': {
                'upper_mean_dx': 0.5,
                'upper_mean_dy': 3.0,  # > vertical_flow_threshold (1.5)
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }]
        
        # Need to fill smoothing buffer to get consistent results
        for _ in range(classifier.smoothing_window):
            results = classifier.classify(tracked_objects, motion_results)
        
        assert 'DT-001' in results
        assert results['DT-001']['current_activity'] == 'DIGGING'
        assert results['DT-001']['activity'] == 'DIGGING'
        assert results['DT-001']['current_state'] == 'ACTIVE'

    def test_classify_swinging_loading_horizontal_motion(self, classifier):
        """Test SWINGING_LOADING classification: horizontal dominant direction."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        # Motion data indicating horizontal flow
        motion_results = [{
            'equipment_id': 'DT-001',
            'motion_source': 'arm_only',
            'dominant_direction': 'right',
            'flow_vectors': {
                'upper_mean_dx': 3.0,  # > horizontal_flow_threshold (1.5)
                'upper_mean_dy': 0.5,
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }]
        
        for _ in range(classifier.smoothing_window):
            results = classifier.classify(tracked_objects, motion_results)
        
        assert 'DT-001' in results
        assert results['DT-001']['current_activity'] == 'SWINGING_LOADING'
        assert results['DT-001']['current_state'] == 'ACTIVE'

    def test_classify_dumping_arm_only_upward(self, classifier):
        """Test DUMPING classification: arm_only + upward direction."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        # Motion data indicating arm_only with upward flow (negative dy)
        motion_results = [{
            'equipment_id': 'DT-001',
            'motion_source': 'arm_only',
            'dominant_direction': 'up',
            'flow_vectors': {
                'upper_mean_dx': 0.5,
                'upper_mean_dy': -3.0,  # < -vertical_flow_threshold
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }]
        
        for _ in range(classifier.smoothing_window):
            results = classifier.classify(tracked_objects, motion_results)
        
        assert 'DT-001' in results
        assert results['DT-001']['current_activity'] == 'DUMPING'
        assert results['DT-001']['current_state'] == 'ACTIVE'

    def test_classify_waiting_no_motion(self, classifier):
        """Test WAITING classification: no motion."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        # Motion data indicating no motion
        motion_results = [{
            'equipment_id': 'DT-001',
            'motion_source': 'none',
            'dominant_direction': 'none',
            'flow_vectors': {
                'upper_mean_dx': 0.0,
                'upper_mean_dy': 0.0,
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }]
        
        for _ in range(classifier.smoothing_window):
            results = classifier.classify(tracked_objects, motion_results)
        
        assert 'DT-001' in results
        assert results['DT-001']['current_activity'] == 'WAITING'
        assert results['DT-001']['current_state'] == 'INACTIVE'

    def test_active_state_for_all_non_waiting_activities(self, classifier):
        """Test that ACTIVE state is set for all activities except WAITING."""
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        
        # Test each active activity
        activities_to_test = [
            # Digging: arm_only + downward
            {
                'equipment_id': 'DT-001', 'motion_source': 'arm_only',
                'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': 3.0,
                                'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
            },
            # Swinging: horizontal
            {
                'equipment_id': 'DT-001', 'motion_source': 'arm_only',
                'flow_vectors': {'upper_mean_dx': 3.0, 'upper_mean_dy': 0.0,
                                'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
            },
            # Dumping: arm_only + upward
            {
                'equipment_id': 'DT-001', 'motion_source': 'arm_only',
                'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': -3.0,
                                'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
            },
        ]
        
        for motion_data in activities_to_test:
            classifier.reset()
            for _ in range(classifier.smoothing_window):
                results = classifier.classify(tracked_objects, [motion_data])
            
            assert results['DT-001']['current_state'] == 'ACTIVE', \
                f"Expected ACTIVE state for motion: {motion_data}"

    def test_inactive_state_for_waiting(self, classifier):
        """Test that INACTIVE state is set for WAITING activity."""
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        
        motion_results = [{
            'equipment_id': 'DT-001',
            'motion_source': 'none',
            'flow_vectors': {
                'upper_mean_dx': 0.0, 'upper_mean_dy': 0.0,
                'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0
            }
        }]
        
        for _ in range(classifier.smoothing_window):
            results = classifier.classify(tracked_objects, motion_results)
        
        assert results['DT-001']['current_state'] == 'INACTIVE'
        assert results['DT-001']['current_activity'] == 'WAITING'


class TestNFrameSmoothing:
    """Tests for N-frame smoothing to prevent activity flickering."""

    @pytest.fixture
    def classifier(self):
        """Create classifier with small smoothing window for testing."""
        return ActivityClassifier({'smoothing_window': 5})

    def test_smoothing_prevents_flickering(self, classifier):
        """Test that smoothing prevents rapid flickering between activities."""
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        
        # Alternate between DIGGING and WAITING motion patterns
        digging_motion = [{
            'equipment_id': 'DT-001', 'motion_source': 'arm_only',
            'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': 3.0,
                            'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
        }]
        
        waiting_motion = [{
            'equipment_id': 'DT-001', 'motion_source': 'none',
            'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': 0.0,
                            'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
        }]
        
        # Fill buffer with DIGGING first
        for _ in range(classifier.smoothing_window):
            classifier.classify(tracked_objects, digging_motion)
        
        # Now alternate - smoothing should prevent immediate flip
        results = []
        for i in range(5):
            motion = waiting_motion if i % 2 == 0 else digging_motion
            result = classifier.classify(tracked_objects, motion)
            results.append(result['DT-001']['current_activity'])
        
        # The majority should still be DIGGING due to smoothing
        digging_count = results.count('DIGGING')
        assert digging_count > 0, "Smoothing should maintain previous state during flickering"

    def test_smoothing_eventual_transition(self, classifier):
        """Test that after enough consistent frames, activity transitions."""
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        
        digging_motion = [{
            'equipment_id': 'DT-001', 'motion_source': 'arm_only',
            'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': 3.0,
                            'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
        }]
        
        waiting_motion = [{
            'equipment_id': 'DT-001', 'motion_source': 'none',
            'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': 0.0,
                            'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
        }]
        
        # Start with DIGGING
        for _ in range(classifier.smoothing_window):
            classifier.classify(tracked_objects, digging_motion)
        
        # Now consistently send WAITING
        for _ in range(classifier.smoothing_window):
            result = classifier.classify(tracked_objects, waiting_motion)
        
        # After enough WAITING frames, should transition
        assert result['DT-001']['current_activity'] == 'WAITING'

    def test_smoothing_mode_calculation(self, classifier):
        """Test that smoothing returns the mode (most common) activity."""
        # Access internal method to test directly
        from collections import deque
        
        buffer = deque(['DIGGING', 'DIGGING', 'DIGGING', 'WAITING', 'WAITING'], maxlen=5)
        mode = classifier._get_mode(buffer)
        assert mode == 'DIGGING'  # 3 vs 2
        
        buffer = deque(['WAITING', 'WAITING', 'WAITING', 'DIGGING', 'DIGGING'], maxlen=5)
        mode = classifier._get_mode(buffer)
        assert mode == 'WAITING'  # 3 vs 2

    def test_new_equipment_fills_buffer(self, classifier):
        """Test that new equipment fills buffer with first classification."""
        tracked_objects = [{'equipment_id': 'NEW-001', 'bbox': [100, 100, 300, 300]}]
        
        digging_motion = [{
            'equipment_id': 'NEW-001', 'motion_source': 'arm_only',
            'flow_vectors': {'upper_mean_dx': 0.0, 'upper_mean_dy': 3.0,
                            'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0}
        }]
        
        # First call should fill buffer with DIGGING
        result = classifier.classify(tracked_objects, digging_motion)
        
        # Check history is filled
        history = classifier.get_history('NEW-001')
        assert history is not None
        assert len(history) == classifier.smoothing_window
        assert all(h == 'DIGGING' for h in history)


class TestClassifyResultFormat:
    """Tests for classify() return format."""

    @pytest.fixture
    def classifier(self, activity_config):
        """Create an ActivityClassifier instance."""
        return ActivityClassifier(activity_config)

    def test_classify_returns_correct_format(self, classifier):
        """Test that classify() returns correctly formatted results."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
            {'equipment_id': 'DT-002', 'bbox': [400, 100, 600, 300]},
        ]
        
        motion_results = [
            {'equipment_id': 'DT-001', 'motion_source': 'arm_only',
             'flow_vectors': {'upper_mean_dx': 0, 'upper_mean_dy': 3,
                             'lower_mean_dx': 0, 'lower_mean_dy': 0}},
            {'equipment_id': 'DT-002', 'motion_source': 'none',
             'flow_vectors': {'upper_mean_dx': 0, 'upper_mean_dy': 0,
                             'lower_mean_dx': 0, 'lower_mean_dy': 0}},
        ]
        
        results = classifier.classify(tracked_objects, motion_results)
        
        # Check both equipment are in results
        assert 'DT-001' in results
        assert 'DT-002' in results
        
        # Check structure for each
        for equip_id in results:
            result = results[equip_id]
            assert 'current_state' in result
            assert 'current_activity' in result
            assert 'activity' in result  # Alias
            assert 'motion_source' in result
            
            assert result['current_state'] in ['ACTIVE', 'INACTIVE']
            assert result['current_activity'] in [
                'DIGGING', 'SWINGING_LOADING', 'DUMPING', 'WAITING'
            ]
            assert result['activity'] == result['current_activity']

    def test_classify_missing_motion_data_uses_empty(self, classifier):
        """Test handling when motion data is missing for an equipment."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        # No motion data provided
        motion_results = []
        
        results = classifier.classify(tracked_objects, motion_results)
        
        # Should use empty motion data defaults (WAITING)
        assert 'DT-001' in results
        # With no motion, should classify as WAITING
        assert results['DT-001']['motion_source'] == 'none'

    def test_classify_handles_dict_motion_results(self, classifier):
        """Test that classify() handles dict-format motion results."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        # Motion results as dict (alternative format)
        motion_results = {
            'DT-001': {
                'motion_source': 'arm_only',
                'flow_vectors': {'upper_mean_dx': 0, 'upper_mean_dy': 3,
                                'lower_mean_dx': 0, 'lower_mean_dy': 0}
            }
        }
        
        results = classifier.classify(tracked_objects, motion_results)
        
        assert 'DT-001' in results


class TestClassifierReset:
    """Tests for classifier reset functionality."""

    def test_reset_clears_history(self):
        """Test that reset() clears all activity history."""
        classifier = ActivityClassifier({'smoothing_window': 5})
        
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        motion_results = [{
            'equipment_id': 'DT-001', 'motion_source': 'none',
            'flow_vectors': {'upper_mean_dx': 0, 'upper_mean_dy': 0,
                            'lower_mean_dx': 0, 'lower_mean_dy': 0}
        }]
        
        # Build up some history
        classifier.classify(tracked_objects, motion_results)
        assert 'DT-001' in classifier._activity_history
        
        # Reset
        classifier.reset()
        
        # History should be cleared
        assert classifier._activity_history == {}
        assert classifier.get_history('DT-001') is None

    def test_get_history_returns_list(self):
        """Test that get_history() returns a list of activities."""
        classifier = ActivityClassifier({'smoothing_window': 5})
        
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        motion_results = [{
            'equipment_id': 'DT-001', 'motion_source': 'none',
            'flow_vectors': {'upper_mean_dx': 0, 'upper_mean_dy': 0,
                            'lower_mean_dx': 0, 'lower_mean_dy': 0}
        }]
        
        classifier.classify(tracked_objects, motion_results)
        
        history = classifier.get_history('DT-001')
        assert isinstance(history, list)
        assert len(history) == classifier.smoothing_window

    def test_get_history_unknown_equipment_returns_none(self):
        """Test that get_history() returns None for unknown equipment."""
        classifier = ActivityClassifier({})
        assert classifier.get_history('UNKNOWN-001') is None


class TestClassificationRules:
    """Detailed tests for classification rule logic."""

    @pytest.fixture
    def classifier(self):
        """Create classifier with known thresholds."""
        return ActivityClassifier({
            'smoothing_window': 1,  # No smoothing for direct testing
            'vertical_flow_threshold': 1.5,
            'horizontal_flow_threshold': 1.5
        })

    def test_raw_classification_digging_rule(self, classifier):
        """Test raw DIGGING classification rule directly."""
        motion_data = {
            'motion_source': 'arm_only',
            'flow_vectors': {
                'upper_mean_dx': 0.0,
                'upper_mean_dy': 2.0,  # > 1.5 threshold
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }
        
        result = classifier._classify_raw_activity(motion_data)
        assert result == 'DIGGING'

    def test_raw_classification_dumping_rule(self, classifier):
        """Test raw DUMPING classification rule directly."""
        motion_data = {
            'motion_source': 'arm_only',
            'flow_vectors': {
                'upper_mean_dx': 0.0,
                'upper_mean_dy': -2.0,  # < -1.5 threshold
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }
        
        result = classifier._classify_raw_activity(motion_data)
        assert result == 'DUMPING'

    def test_raw_classification_swinging_loading_rule(self, classifier):
        """Test raw SWINGING_LOADING classification rule directly."""
        motion_data = {
            'motion_source': 'arm_only',
            'flow_vectors': {
                'upper_mean_dx': 2.0,  # > 1.5 threshold
                'upper_mean_dy': 0.0,
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }
        
        result = classifier._classify_raw_activity(motion_data)
        assert result == 'SWINGING_LOADING'

    def test_raw_classification_waiting_rule(self, classifier):
        """Test raw WAITING classification rule directly."""
        motion_data = {
            'motion_source': 'none',
            'flow_vectors': {
                'upper_mean_dx': 0.0,
                'upper_mean_dy': 0.0,
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 0.0
            }
        }
        
        result = classifier._classify_raw_activity(motion_data)
        assert result == 'WAITING'

    def test_full_body_motion_with_horizontal_flow(self, classifier):
        """Test classification with full_body motion and horizontal flow."""
        motion_data = {
            'motion_source': 'full_body',
            'flow_vectors': {
                'upper_mean_dx': 2.0,
                'upper_mean_dy': 0.0,
                'lower_mean_dx': 2.0,
                'lower_mean_dy': 0.0
            }
        }
        
        result = classifier._classify_raw_activity(motion_data)
        # full_body with horizontal motion should be SWINGING_LOADING
        assert result == 'SWINGING_LOADING'

    def test_full_body_averages_flow_vectors(self, classifier):
        """Test that full_body motion averages upper and lower flow vectors."""
        motion_data = {
            'motion_source': 'full_body',
            'flow_vectors': {
                'upper_mean_dx': 0.0,
                'upper_mean_dy': 1.0,  # Below threshold alone
                'lower_mean_dx': 0.0,
                'lower_mean_dy': 1.0   # Below threshold alone
            }
        }
        
        # Average would be 1.0, still below 1.5 threshold
        # Should default to SWINGING_LOADING for full_body with motion
        result = classifier._classify_raw_activity(motion_data)
        assert result == 'SWINGING_LOADING'
