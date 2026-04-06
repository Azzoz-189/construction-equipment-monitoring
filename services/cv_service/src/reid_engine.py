"""
Appearance-based Re-Identification Engine for Construction Equipment.

Uses HSV color histograms + spatial proximity for matching equipment
that temporarily leaves and re-enters the camera frame.
"""

import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ReIDEngine:
    """
    Re-identification engine using appearance features (color histograms)
    and spatial proximity to match equipment across track losses.
    """
    
    def __init__(self, config: dict):
        """
        Args:
            config: Reid configuration dict with keys:
                - enabled (bool): Whether Re-ID is active
                - similarity_threshold (float): Min similarity for match (0-1, default 0.65)
                - max_lost_buffer (int): Max lost tracks to keep (default 50)
                - histogram_bins (list): HSV bins [H, S, V] (default [8, 8, 8])
                - feature_ttl_seconds (int): How long to keep lost features (default 300)
        """
        self.enabled = config.get('enabled', True)
        self.similarity_threshold = config.get('similarity_threshold', 0.65)
        self.max_lost_buffer = config.get('max_lost_buffer', 50)
        self.histogram_bins = config.get('histogram_bins', [8, 8, 8])
        self.feature_ttl_seconds = config.get('feature_ttl_seconds', 300)
        
        # Active tracks: equipment_id -> {histogram, last_bbox, last_seen_time, features_history}
        self._active_features: Dict[str, dict] = {}
        
        # Lost tracks: equipment_id -> {histogram, last_bbox, lost_time, features_history}
        self._lost_buffer: Dict[str, dict] = {}
        
        logger.info(
            f"ReIDEngine initialized: enabled={self.enabled}, "
            f"threshold={self.similarity_threshold}, "
            f"max_buffer={self.max_lost_buffer}, "
            f"bins={self.histogram_bins}"
        )
    
    def extract_histogram(self, frame: np.ndarray, bbox: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
        """
        Extract HSV color histogram from equipment bounding box region.
        
        Args:
            frame: Full video frame (BGR)
            bbox: (x1, y1, x2, y2) bounding box coordinates
            
        Returns:
            Normalized histogram as numpy array, or None if extraction fails
        """
        try:
            x1, y1, x2, y2 = [int(c) for c in bbox]
            h, w = frame.shape[:2]
            
            # Clamp to frame bounds
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            # Minimum bbox size check
            if (x2 - x1) < 10 or (y2 - y1) < 10:
                return None
            
            # Extract region
            roi = frame[y1:y2, x1:x2]
            
            # Convert to HSV
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            
            # Create mask to exclude very dark/very bright pixels (shadows/highlights)
            mask = cv2.inRange(hsv, (0, 30, 30), (180, 255, 250))
            
            # Calculate histogram
            hist = cv2.calcHist(
                [hsv], [0, 1, 2], mask,
                self.histogram_bins, 
                [0, 180, 0, 256, 0, 256]
            )
            
            # Normalize
            cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
            
            return hist.flatten()
            
        except Exception as e:
            logger.debug(f"Histogram extraction failed: {e}")
            return None
    
    def compare_histograms(self, hist1: np.ndarray, hist2: np.ndarray) -> float:
        """
        Compare two histograms using correlation method.
        
        Returns:
            Similarity score between 0.0 (different) and 1.0 (identical)
        """
        if hist1 is None or hist2 is None:
            return 0.0
        
        # Use correlation (higher = more similar, range -1 to 1)
        correlation = cv2.compareHist(
            hist1.reshape(-1).astype(np.float32),
            hist2.reshape(-1).astype(np.float32),
            cv2.HISTCMP_CORREL
        )
        
        # Normalize to 0-1 range
        return max(0.0, correlation)
    
    def _spatial_proximity_score(
        self, 
        bbox1: Tuple[int, int, int, int], 
        bbox2: Tuple[int, int, int, int],
        frame_diagonal: float
    ) -> float:
        """
        Compute spatial proximity score between two bounding boxes.
        Closer boxes get higher scores.
        
        Returns:
            Score between 0.0 (very far) and 1.0 (same location)
        """
        cx1 = (bbox1[0] + bbox1[2]) / 2
        cy1 = (bbox1[1] + bbox1[3]) / 2
        cx2 = (bbox2[0] + bbox2[2]) / 2
        cy2 = (bbox2[1] + bbox2[3]) / 2
        
        distance = np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)
        
        # Normalize by frame diagonal — equipment within 30% of diagonal considered close
        normalized_dist = distance / (frame_diagonal * 0.3)
        
        return max(0.0, 1.0 - normalized_dist)
    
    def update_active_track(
        self, 
        equipment_id: str, 
        frame: np.ndarray, 
        bbox: Tuple[int, int, int, int]
    ):
        """
        Update appearance features for an actively tracked equipment.
        Called every frame for each tracked equipment.
        """
        if not self.enabled:
            return
            
        histogram = self.extract_histogram(frame, bbox)
        if histogram is None:
            return
        
        current_time = time.time()
        
        if equipment_id in self._active_features:
            entry = self._active_features[equipment_id]
            # Exponential moving average of histogram for robustness
            alpha = 0.3
            entry['histogram'] = alpha * histogram + (1 - alpha) * entry['histogram']
            entry['last_bbox'] = bbox
            entry['last_seen_time'] = current_time
        else:
            self._active_features[equipment_id] = {
                'histogram': histogram,
                'last_bbox': bbox,
                'last_seen_time': current_time,
            }
    
    def mark_track_lost(self, equipment_id: str):
        """
        Move an equipment's features from active to lost buffer.
        Called when ByteTrack loses a track.
        """
        if not self.enabled:
            return
            
        if equipment_id in self._active_features:
            features = self._active_features.pop(equipment_id)
            features['lost_time'] = time.time()
            self._lost_buffer[equipment_id] = features
            
            # Enforce buffer size limit (remove oldest)
            if len(self._lost_buffer) > self.max_lost_buffer:
                oldest_id = min(
                    self._lost_buffer, 
                    key=lambda k: self._lost_buffer[k]['lost_time']
                )
                del self._lost_buffer[oldest_id]
            
            logger.debug(f"Track lost: {equipment_id} moved to Re-ID buffer "
                        f"(buffer size: {len(self._lost_buffer)})")
    
    def try_reidentify(
        self, 
        frame: np.ndarray, 
        bbox: Tuple[int, int, int, int],
        frame_shape: Tuple[int, int]
    ) -> Optional[str]:
        """
        Try to re-identify a new detection as a previously lost equipment.
        
        Args:
            frame: Current video frame
            bbox: Bounding box of new detection
            frame_shape: (height, width) of the frame
            
        Returns:
            equipment_id if match found, None otherwise
        """
        if not self.enabled or not self._lost_buffer:
            return None
        
        histogram = self.extract_histogram(frame, bbox)
        if histogram is None:
            return None
        
        current_time = time.time()
        frame_diagonal = np.sqrt(frame_shape[0]**2 + frame_shape[1]**2)
        
        # Clean expired entries
        expired = [
            eid for eid, features in self._lost_buffer.items()
            if (current_time - features['lost_time']) > self.feature_ttl_seconds
        ]
        for eid in expired:
            del self._lost_buffer[eid]
            logger.debug(f"Expired Re-ID entry: {eid}")
        
        # Find best match
        best_match_id = None
        best_score = 0.0
        
        for equipment_id, features in self._lost_buffer.items():
            # Appearance similarity (histogram comparison)
            appearance_score = self.compare_histograms(histogram, features['histogram'])
            
            # Spatial proximity score
            spatial_score = self._spatial_proximity_score(
                bbox, features['last_bbox'], frame_diagonal
            )
            
            # Combined score: 70% appearance, 30% spatial
            combined_score = 0.7 * appearance_score + 0.3 * spatial_score
            
            if combined_score > best_score:
                best_score = combined_score
                best_match_id = equipment_id
        
        # Check if best match exceeds threshold
        if best_match_id and best_score >= self.similarity_threshold:
            # Remove from lost buffer (it's been re-identified)
            matched_features = self._lost_buffer.pop(best_match_id)
            
            # Add back to active features with updated position
            self._active_features[best_match_id] = {
                'histogram': matched_features['histogram'],
                'last_bbox': bbox,
                'last_seen_time': current_time,
            }
            
            logger.info(
                f"Re-identified equipment: {best_match_id} "
                f"(score: {best_score:.3f}, "
                f"absent: {current_time - matched_features['lost_time']:.1f}s)"
            )
            return best_match_id
        
        return None
    
    def get_active_ids(self) -> List[str]:
        """Get list of currently active equipment IDs."""
        return list(self._active_features.keys())
    
    def get_lost_ids(self) -> List[str]:
        """Get list of equipment IDs in lost buffer."""
        return list(self._lost_buffer.keys())
    
    def get_stats(self) -> dict:
        """Get Re-ID engine statistics."""
        return {
            'active_tracks': len(self._active_features),
            'lost_buffer_size': len(self._lost_buffer),
            'lost_equipment_ids': list(self._lost_buffer.keys()),
        }
    
    def reset(self):
        """Clear all features and buffers (e.g., on channel switch)."""
        self._active_features.clear()
        self._lost_buffer.clear()
        logger.info("ReIDEngine reset: all features and buffers cleared")
