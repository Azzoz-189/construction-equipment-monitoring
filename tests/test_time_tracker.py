"""
Tests for TimeTracker class.

This module tests the time tracking functionality for equipment utilization
including active/idle time accumulation and utilization percentage calculations.
"""

import sys
import os
import pytest

# Add services to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services', 'cv_service', 'src'))

from time_tracker import TimeTracker


class TestTimeTrackerInitialization:
    """Tests for TimeTracker initialization."""

    def test_init_creates_empty_tracker(self):
        """Test that TimeTracker initializes with empty statistics."""
        tracker = TimeTracker()
        
        assert tracker._equipment_stats == {}
        assert tracker._last_timestamp is None

    def test_get_stats_unknown_equipment_returns_zeros(self):
        """Test that get_stats returns zeros for unknown equipment."""
        tracker = TimeTracker()
        
        stats = tracker.get_stats('UNKNOWN-001')
        
        assert stats['total_tracked_seconds'] == 0.0
        assert stats['total_active_seconds'] == 0.0
        assert stats['total_idle_seconds'] == 0.0
        assert stats['utilization_percent'] == 0.0


class TestTimeTrackerUpdate:
    """Tests for TimeTracker.update() method."""

    @pytest.fixture
    def tracker(self):
        """Create a TimeTracker instance."""
        return TimeTracker()

    def test_update_active_equipment_increments_active_seconds(self, tracker):
        """Test that active equipment increments active_seconds and tracked_seconds."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {
                'current_state': 'ACTIVE',
                'current_activity': 'DIGGING'
            }
        }
        
        # Update at 30 FPS (each frame = 1/30 second)
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        stats = tracker.get_stats('DT-001')
        
        expected_delta = 1.0 / 30.0
        assert abs(stats['total_tracked_seconds'] - expected_delta) < 0.001
        assert abs(stats['total_active_seconds'] - expected_delta) < 0.001
        assert stats['total_idle_seconds'] == 0.0

    def test_update_inactive_equipment_increments_idle_seconds(self, tracker):
        """Test that inactive equipment increments idle_seconds and tracked_seconds."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {
                'current_state': 'INACTIVE',
                'current_activity': 'WAITING'
            }
        }
        
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        stats = tracker.get_stats('DT-001')
        
        expected_delta = 1.0 / 30.0
        assert abs(stats['total_tracked_seconds'] - expected_delta) < 0.001
        assert stats['total_active_seconds'] == 0.0
        assert abs(stats['total_idle_seconds'] - expected_delta) < 0.001

    def test_utilization_percent_calculation(self, tracker):
        """Test utilization_percent calculation: 10s active out of 15s tracked = 66.7%."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        active_activity = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'}
        }
        
        inactive_activity = {
            'DT-001': {'current_state': 'INACTIVE', 'current_activity': 'WAITING'}
        }
        
        # Simulate 30 FPS, process frames to get desired time
        # 10 seconds active = 300 frames at 30 FPS
        # 5 seconds idle = 150 frames at 30 FPS
        
        for _ in range(300):  # 10 seconds active
            tracker.update(tracked_objects, active_activity, '00:00:01.000', fps=30.0)
        
        for _ in range(150):  # 5 seconds idle
            tracker.update(tracked_objects, inactive_activity, '00:00:02.000', fps=30.0)
        
        stats = tracker.get_stats('DT-001')
        
        # Total should be ~15 seconds
        assert abs(stats['total_tracked_seconds'] - 15.0) < 0.1
        assert abs(stats['total_active_seconds'] - 10.0) < 0.1
        assert abs(stats['total_idle_seconds'] - 5.0) < 0.1
        
        # Utilization should be ~66.67%
        expected_utilization = (10.0 / 15.0) * 100.0
        assert abs(stats['utilization_percent'] - expected_utilization) < 0.1

    def test_multiple_equipment_tracked_independently(self, tracker):
        """Test that multiple equipment are tracked independently."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
            {'equipment_id': 'DT-002', 'bbox': [400, 100, 600, 300]},
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'},
            'DT-002': {'current_state': 'INACTIVE', 'current_activity': 'WAITING'},
        }
        
        # Update both equipment
        for _ in range(30):  # 1 second at 30 FPS
            tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        stats_1 = tracker.get_stats('DT-001')
        stats_2 = tracker.get_stats('DT-002')
        
        # DT-001 should be all active
        assert abs(stats_1['total_active_seconds'] - 1.0) < 0.1
        assert stats_1['total_idle_seconds'] < 0.1
        
        # DT-002 should be all idle
        assert stats_2['total_active_seconds'] < 0.1
        assert abs(stats_2['total_idle_seconds'] - 1.0) < 0.1

    def test_equipment_disappear_reappear_stats_persist(self, tracker):
        """Test that equipment stats persist when equipment disappears and reappears."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'}
        }
        
        # First appearance - 1 second
        for _ in range(30):
            tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        stats_before = tracker.get_stats('DT-001')
        assert abs(stats_before['total_active_seconds'] - 1.0) < 0.1
        
        # Equipment disappears (empty tracked_objects)
        tracker.update([], {}, '00:00:02.000', fps=30.0)
        
        # Stats should still be there
        stats_during = tracker.get_stats('DT-001')
        assert abs(stats_during['total_active_seconds'] - 1.0) < 0.1
        
        # Equipment reappears - another 1 second
        for _ in range(30):
            tracker.update(tracked_objects, activities, '00:00:03.000', fps=30.0)
        
        stats_after = tracker.get_stats('DT-001')
        # Should have accumulated 2 seconds total
        assert abs(stats_after['total_active_seconds'] - 2.0) < 0.1

    def test_division_by_zero_protection(self, tracker):
        """Test protection against division by zero for utilization calculation."""
        # Get stats for equipment with 0 tracked seconds
        stats = tracker.get_stats('NEVER-TRACKED')
        
        # Should return 0% utilization, not error
        assert stats['utilization_percent'] == 0.0
        assert stats['total_tracked_seconds'] == 0.0

    def test_fps_zero_protection(self, tracker):
        """Test protection against zero FPS."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'}
        }
        
        # Should not raise error with fps=0
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=0.0)
        
        stats = tracker.get_stats('DT-001')
        # With fps=0, time_delta = 1.0/max(0,1) = 1.0 second
        assert abs(stats['total_tracked_seconds'] - 1.0) < 0.1


class TestTimeTrackerGetStats:
    """Tests for get_stats and get_all_stats methods."""

    @pytest.fixture
    def populated_tracker(self):
        """Create a TimeTracker with some data."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
            {'equipment_id': 'DT-002', 'bbox': [400, 100, 600, 300]},
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'},
            'DT-002': {'current_state': 'INACTIVE', 'current_activity': 'WAITING'},
        }
        
        # Add some time
        for _ in range(60):  # 2 seconds at 30 FPS
            tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        return tracker

    def test_get_stats_returns_correct_format(self, populated_tracker):
        """Test that get_stats returns correctly formatted dictionary."""
        stats = populated_tracker.get_stats('DT-001')
        
        assert 'total_tracked_seconds' in stats
        assert 'total_active_seconds' in stats
        assert 'total_idle_seconds' in stats
        assert 'utilization_percent' in stats
        
        assert isinstance(stats['total_tracked_seconds'], float)
        assert isinstance(stats['total_active_seconds'], float)
        assert isinstance(stats['total_idle_seconds'], float)
        assert isinstance(stats['utilization_percent'], float)

    def test_get_all_stats_returns_all_equipment(self, populated_tracker):
        """Test that get_all_stats returns stats for all tracked equipment."""
        all_stats = populated_tracker.get_all_stats()
        
        assert 'DT-001' in all_stats
        assert 'DT-002' in all_stats
        
        for equip_id in all_stats:
            stats = all_stats[equip_id]
            assert 'total_tracked_seconds' in stats
            assert 'utilization_percent' in stats

    def test_update_returns_all_stats(self, populated_tracker):
        """Test that update() returns stats for all tracked equipment."""
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'}
        }
        
        result = populated_tracker.update(tracked_objects, activities, '00:00:02.000', fps=30.0)
        
        # Should return stats for all equipment, not just those in current frame
        assert 'DT-001' in result
        assert 'DT-002' in result


class TestTimeTrackerReset:
    """Tests for TimeTracker reset functionality."""

    def test_reset_clears_all_stats(self):
        """Test that reset() clears all statistics."""
        tracker = TimeTracker()
        
        # Add some data
        tracked_objects = [{'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}]
        activities = {'DT-001': {'current_state': 'ACTIVE'}}
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        assert 'DT-001' in tracker._equipment_stats
        
        # Reset
        tracker.reset()
        
        assert tracker._equipment_stats == {}
        assert tracker._last_timestamp is None

    def test_get_equipment_ids(self):
        """Test get_equipment_ids returns list of tracked IDs."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
            {'equipment_id': 'DT-002', 'bbox': [400, 100, 600, 300]},
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE'},
            'DT-002': {'current_state': 'INACTIVE'},
        }
        
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        ids = tracker.get_equipment_ids()
        
        assert isinstance(ids, list)
        assert 'DT-001' in ids
        assert 'DT-002' in ids


class TestTotalUtilization:
    """Tests for aggregate utilization calculations."""

    @pytest.fixture
    def tracker_with_data(self):
        """Create tracker with known utilization data."""
        tracker = TimeTracker()
        
        # DT-001: 2 seconds tracked, all active (100% utilization)
        # DT-002: 2 seconds tracked, all idle (0% utilization)
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]},
            {'equipment_id': 'DT-002', 'bbox': [400, 100, 600, 300]},
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE', 'current_activity': 'DIGGING'},
            'DT-002': {'current_state': 'INACTIVE', 'current_activity': 'WAITING'},
        }
        
        for _ in range(60):  # 2 seconds at 30 FPS
            tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        return tracker

    def test_get_total_utilization_returns_correct_format(self, tracker_with_data):
        """Test that get_total_utilization returns correct format."""
        total = tracker_with_data.get_total_utilization()
        
        assert 'total_equipment_count' in total
        assert 'total_tracked_seconds' in total
        assert 'total_active_seconds' in total
        assert 'total_idle_seconds' in total
        assert 'average_utilization_percent' in total

    def test_get_total_utilization_values(self, tracker_with_data):
        """Test get_total_utilization calculates correct aggregate values."""
        total = tracker_with_data.get_total_utilization()
        
        assert total['total_equipment_count'] == 2
        # Total tracked = 2s + 2s = 4s
        assert abs(total['total_tracked_seconds'] - 4.0) < 0.1
        # Total active = 2s (only DT-001)
        assert abs(total['total_active_seconds'] - 2.0) < 0.1
        # Total idle = 2s (only DT-002)
        assert abs(total['total_idle_seconds'] - 2.0) < 0.1
        # Average utilization = 2/4 = 50%
        assert abs(total['average_utilization_percent'] - 50.0) < 0.1

    def test_get_total_utilization_empty_tracker(self):
        """Test get_total_utilization with no tracked equipment."""
        tracker = TimeTracker()
        total = tracker.get_total_utilization()
        
        assert total['total_equipment_count'] == 0
        assert total['total_tracked_seconds'] == 0.0
        assert total['total_active_seconds'] == 0.0
        assert total['total_idle_seconds'] == 0.0
        assert total['average_utilization_percent'] == 0.0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_missing_current_state_defaults_to_inactive(self):
        """Test that missing current_state defaults to INACTIVE."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        # Activity without current_state
        activities = {
            'DT-001': {'current_activity': 'UNKNOWN'}
        }
        
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        stats = tracker.get_stats('DT-001')
        # Should be counted as idle (default)
        assert stats['total_idle_seconds'] > 0
        assert stats['total_active_seconds'] == 0

    def test_equipment_with_no_activity_data(self):
        """Test handling of equipment with no activity data."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        # Empty activities dict
        activities = {}
        
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=30.0)
        
        stats = tracker.get_stats('DT-001')
        # Should be counted as idle (default)
        assert stats['total_idle_seconds'] > 0

    def test_high_fps_values(self):
        """Test with high FPS values."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE'}
        }
        
        # 120 FPS
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=120.0)
        
        stats = tracker.get_stats('DT-001')
        expected_delta = 1.0 / 120.0
        assert abs(stats['total_tracked_seconds'] - expected_delta) < 0.001

    def test_very_low_fps_values(self):
        """Test with very low FPS values."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE'}
        }
        
        # 1 FPS (e.g., timelapse)
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=1.0)
        
        stats = tracker.get_stats('DT-001')
        expected_delta = 1.0  # 1 second per frame
        assert abs(stats['total_tracked_seconds'] - expected_delta) < 0.001

    def test_negative_fps_treated_as_minimum(self):
        """Test that negative FPS is treated as minimum value."""
        tracker = TimeTracker()
        
        tracked_objects = [
            {'equipment_id': 'DT-001', 'bbox': [100, 100, 300, 300]}
        ]
        
        activities = {
            'DT-001': {'current_state': 'ACTIVE'}
        }
        
        # Negative FPS should be treated as max(fps, 1.0)
        tracker.update(tracked_objects, activities, '00:00:01.000', fps=-5.0)
        
        stats = tracker.get_stats('DT-001')
        # With fps=-5, max(-5, 1) = 1, so delta = 1.0 second
        assert abs(stats['total_tracked_seconds'] - 1.0) < 0.001
