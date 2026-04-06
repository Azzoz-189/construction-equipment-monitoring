"""
LSTM Temporal Activity Classifier Module.

This module implements an LSTM-based activity classifier that processes
sequences of motion features to capture temporal patterns like digging cycles.
It enhances the rule-based classifier with learned temporal modeling.

Designed for CPU-only deployment (~500KB model, ~5-10ms inference).

Activity classifications:
- DIGGING: Arm-only downward motion cycles (excavating)
- DUMPING: Arm-only upward motion (releasing material)
- SWINGING_LOADING: Horizontal/rotational motion (rotating/loading)
- WAITING: No significant motion (idle)
"""

import os
import math
import logging
from collections import deque
from typing import Optional

import numpy as np

try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

# Configure module logger
logger = logging.getLogger(__name__)


def extract_features(motion_result: dict, bbox: tuple, frame_shape: tuple) -> list:
    """
    Extract 12-dimensional feature vector from a single frame's analysis.

    Features:
        0: mean_dx (horizontal flow)
        1: mean_dy (vertical flow)
        2: magnitude (overall motion magnitude)
        3: motion_source_encoded (0=none, 1=arm_only, 2=full_body)
        4: bbox_width_normalized (bbox_w / frame_w)
        5: bbox_height_normalized (bbox_h / frame_h)
        6: aspect_ratio (bbox_w / bbox_h)
        7: center_x_normalized (center_x / frame_w)
        8: center_y_normalized (center_y / frame_h)
        9: upper_magnitude (motion in upper region)
        10: lower_magnitude (motion in lower region)
        11: direction_encoded (0=none, 1=up, 2=down, 3=left, 4=right)

    Args:
        motion_result: Motion analysis result dict from MotionAnalyzer.
        bbox: Bounding box as (x1, y1, x2, y2).
        frame_shape: Frame dimensions as (height, width) or (height, width, channels).

    Returns:
        List of 12 float feature values.
    """
    flow_vectors = motion_result.get('flow_vectors', {})
    upper_dx = flow_vectors.get('upper_mean_dx', 0.0)
    upper_dy = flow_vectors.get('upper_mean_dy', 0.0)
    lower_dx = flow_vectors.get('lower_mean_dx', 0.0)
    lower_dy = flow_vectors.get('lower_mean_dy', 0.0)

    # Feature 0-1: Mean flow direction
    mean_dx = (upper_dx + lower_dx) / 2.0
    mean_dy = (upper_dy + lower_dy) / 2.0

    # Feature 2: Overall motion magnitude
    upper_mag = motion_result.get('upper_magnitude', 0.0)
    lower_mag = motion_result.get('lower_magnitude', 0.0)
    magnitude = max(upper_mag, lower_mag)

    # Feature 3: Motion source encoded
    motion_source = motion_result.get('motion_source', 'none')
    motion_source_map = {'none': 0, 'arm_only': 1, 'full_body': 2}
    motion_source_encoded = motion_source_map.get(motion_source, 0)

    # Parse bbox and frame shape
    frame_h = frame_shape[0] if len(frame_shape) >= 2 else 480
    frame_w = frame_shape[1] if len(frame_shape) >= 2 else 640

    if len(bbox) >= 4:
        x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
    else:
        x1, y1, x2, y2 = 0.0, 0.0, 0.0, 0.0

    bbox_w = max(x2 - x1, 1.0)
    bbox_h = max(y2 - y1, 1.0)

    # Feature 4-5: Normalized bbox dimensions
    bbox_width_normalized = bbox_w / max(frame_w, 1)
    bbox_height_normalized = bbox_h / max(frame_h, 1)

    # Feature 6: Aspect ratio
    aspect_ratio = bbox_w / bbox_h

    # Feature 7-8: Normalized center position
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    center_x_normalized = center_x / max(frame_w, 1)
    center_y_normalized = center_y / max(frame_h, 1)

    # Feature 9-10: Upper and lower magnitudes
    upper_magnitude = upper_mag
    lower_magnitude = lower_mag

    # Feature 11: Direction encoded
    direction = motion_result.get('dominant_direction', 'none')
    direction_map = {'none': 0, 'up': 1, 'down': 2, 'left': 3, 'right': 4}
    direction_encoded = direction_map.get(direction, 0)

    return [
        float(mean_dx),
        float(mean_dy),
        float(magnitude),
        float(motion_source_encoded),
        float(bbox_width_normalized),
        float(bbox_height_normalized),
        float(aspect_ratio),
        float(center_x_normalized),
        float(center_y_normalized),
        float(upper_magnitude),
        float(lower_magnitude),
        float(direction_encoded),
    ]


if TORCH_AVAILABLE:
    class ActivityLSTM(nn.Module):
        """
        Lightweight LSTM model for temporal activity classification.

        Designed for CPU-only deployment with ~500KB model size
        and ~5-10ms inference time.

        Args:
            input_size: Dimension of input features per timestep (default: 12).
            hidden_size: LSTM hidden state dimension (default: 64).
            num_layers: Number of stacked LSTM layers (default: 2).
            num_classes: Number of activity classes (default: 4).
            dropout: Dropout probability for regularization (default: 0.3).
        """

        def __init__(
            self,
            input_size: int = 12,
            hidden_size: int = 64,
            num_layers: int = 2,
            num_classes: int = 4,
            dropout: float = 0.3,
        ):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size,
                hidden_size,
                num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0.0,
            )
            self.fc = nn.Sequential(
                nn.Linear(hidden_size, 32),
                nn.ReLU(),
                nn.Dropout(dropout),
                nn.Linear(32, num_classes),
            )

        def forward(self, x):
            """
            Forward pass.

            Args:
                x: Input tensor of shape (batch, seq_len, input_size).

            Returns:
                Logits tensor of shape (batch, num_classes).
            """
            lstm_out, _ = self.lstm(x)
            # Use last timestep output
            out = self.fc(lstm_out[:, -1, :])
            return out

else:
    # Stub when torch is not available
    class ActivityLSTM:
        """Stub ActivityLSTM when PyTorch is not installed."""

        def __init__(self, *args, **kwargs):
            raise ImportError("PyTorch is required for ActivityLSTM but not installed")


class LSTMActivityClassifier:
    """
    LSTM-based activity classifier that maintains per-equipment feature buffers
    and classifies activities based on temporal sequences.

    Falls back gracefully to rule-based classification when:
    - PyTorch is not installed
    - No trained model file is available
    - LSTM confidence is below threshold
    - Feature buffer is not yet full

    Attributes:
        ACTIVITIES: List of activity class names.
        ACTIVITY_TO_STATE: Mapping from activity to equipment state.
    """

    ACTIVITIES = ['DIGGING', 'DUMPING', 'SWINGING_LOADING', 'WAITING']
    ACTIVITY_TO_STATE = {
        'DIGGING': 'ACTIVE',
        'DUMPING': 'ACTIVE',
        'SWINGING_LOADING': 'ACTIVE',
        'WAITING': 'INACTIVE',
    }

    def __init__(self, config: dict):
        """
        Initialize LSTM activity classifier.

        Args:
            config: Configuration dictionary with keys:
                - model_path (str): Path to trained .pth file (optional).
                - sequence_length (int): Number of frames in sequence (default: 16).
                - confidence_threshold (float): Min confidence for LSTM prediction (default: 0.6).
                - fallback_to_rules (bool): Whether to fall back to rules on low confidence (default: True).
        """
        self.sequence_length = config.get('sequence_length', 16)
        self.confidence_threshold = config.get('confidence_threshold', 0.6)
        self.fallback_to_rules = config.get('fallback_to_rules', True)
        self.model = None

        # Per-equipment feature buffer
        self._feature_buffers: dict[str, deque] = {}

        # Load model if available
        model_path = config.get('model_path', '')
        if model_path and os.path.exists(model_path):
            self._load_model(model_path)
        else:
            logger.info(
                "No LSTM model found at '%s' — will use rule-based fallback for all predictions",
                model_path,
            )

    def _load_model(self, path: str) -> None:
        """
        Load trained LSTM model from disk.

        Args:
            path: Filesystem path to the .pth state dict file.
        """
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch not available — cannot load LSTM model")
            return

        try:
            self.model = ActivityLSTM()
            state_dict = torch.load(path, map_location='cpu', weights_only=True)
            self.model.load_state_dict(state_dict)
            self.model.eval()
            logger.info("LSTM model loaded from %s", path)
        except Exception as e:
            logger.warning("Failed to load LSTM model: %s", e)
            self.model = None

    def update(
        self,
        equipment_id: str,
        motion_result: dict,
        bbox: tuple,
        frame_shape: tuple,
    ) -> dict:
        """
        Add a frame's features to the buffer and classify activity.

        Args:
            equipment_id: Unique equipment identifier.
            motion_result: Motion analysis result dict from MotionAnalyzer.
            bbox: Bounding box as (x1, y1, x2, y2).
            frame_shape: Frame dimensions as (height, width) or (height, width, channels).

        Returns:
            Dict with keys:
                - activity (str): Predicted activity label.
                - state (str): Equipment state ('ACTIVE' or 'INACTIVE').
                - confidence (float): Prediction confidence [0, 1].
                - method (str): 'lstm' or 'rule_fallback'.
        """
        # Extract features
        features = extract_features(motion_result, bbox, frame_shape)

        # Add to buffer
        if equipment_id not in self._feature_buffers:
            self._feature_buffers[equipment_id] = deque(maxlen=self.sequence_length)
        self._feature_buffers[equipment_id].append(features)

        # Try LSTM prediction if model available and buffer full
        if (
            self.model is not None
            and TORCH_AVAILABLE
            and len(self._feature_buffers[equipment_id]) >= self.sequence_length
        ):
            return self._predict_lstm(equipment_id, motion_result)

        # Fallback to rule-based
        return self._predict_rules(motion_result)

    def _predict_lstm(self, equipment_id: str, motion_result: dict) -> dict:
        """
        Run LSTM inference on the feature buffer for an equipment.

        Args:
            equipment_id: Equipment identifier whose buffer to use.
            motion_result: Latest motion result for rule fallback.

        Returns:
            Classification result dict.
        """
        with torch.no_grad():
            features = list(self._feature_buffers[equipment_id])
            tensor = torch.FloatTensor([features])  # (1, seq_len, 12)
            logits = self.model(tensor)
            probs = torch.softmax(logits, dim=1)
            confidence, predicted = probs.max(dim=1)

            activity = self.ACTIVITIES[predicted.item()]
            conf = confidence.item()

            if conf >= self.confidence_threshold:
                return {
                    'activity': activity,
                    'state': self.ACTIVITY_TO_STATE[activity],
                    'confidence': conf,
                    'method': 'lstm',
                }
            elif self.fallback_to_rules:
                result = self._predict_rules(motion_result)
                result['confidence'] = max(result['confidence'], conf)
                return result

        return self._predict_rules(motion_result)

    def _predict_rules(self, motion_result: dict) -> dict:
        """
        Rule-based fallback using motion analysis.

        Mirrors the logic from the existing ActivityClassifier to maintain
        consistent behaviour when LSTM is unavailable or uncertain.

        Args:
            motion_result: Motion analysis result dict.

        Returns:
            Classification result dict with method='rule_fallback'.
        """
        motion_source = motion_result.get('motion_source', 'none')
        magnitude = max(
            motion_result.get('upper_magnitude', 0.0),
            motion_result.get('lower_magnitude', 0.0),
        )

        flow_vectors = motion_result.get('flow_vectors', {})
        upper_dy = flow_vectors.get('upper_mean_dy', 0.0)
        lower_dy = flow_vectors.get('lower_mean_dy', 0.0)
        upper_dx = flow_vectors.get('upper_mean_dx', 0.0)
        lower_dx = flow_vectors.get('lower_mean_dx', 0.0)

        if motion_source == 'arm_only':
            mean_dy = upper_dy
            mean_dx = upper_dx
        else:
            mean_dy = (upper_dy + lower_dy) / 2.0
            mean_dx = (upper_dx + lower_dx) / 2.0

        if motion_source == 'none' or magnitude < 1.0:
            activity = 'WAITING'
        elif motion_source == 'arm_only':
            if mean_dy > 1.5:
                activity = 'DIGGING'
            elif mean_dy < -1.5:
                activity = 'DUMPING'
            else:
                activity = 'SWINGING_LOADING'
        else:
            if abs(mean_dx) > 1.5:
                activity = 'SWINGING_LOADING'
            else:
                activity = 'SWINGING_LOADING'

        return {
            'activity': activity,
            'state': self.ACTIVITY_TO_STATE[activity],
            'confidence': 0.5,
            'method': 'rule_fallback',
        }

    def reset(self) -> None:
        """Clear all per-equipment feature buffers."""
        self._feature_buffers.clear()
        logger.debug("LSTMActivityClassifier feature buffers reset")

    def get_buffer_status(self) -> dict:
        """
        Get the current status of all feature buffers.

        Returns:
            Dict mapping equipment_id to buffer fill count.
        """
        return {
            eq_id: len(buf)
            for eq_id, buf in self._feature_buffers.items()
        }


class TrainingDataGenerator:
    """
    Generate pseudo-labeled training data from the rule-based classifier.

    Runs the existing pipeline and saves features + labels for LSTM training.
    This enables bootstrapping LSTM training from the rule-based system.
    """

    ACTIVITIES = ['DIGGING', 'DUMPING', 'SWINGING_LOADING', 'WAITING']

    def __init__(self, sequence_length: int = 16):
        """
        Initialize training data generator.

        Args:
            sequence_length: Number of frames per training sequence.
        """
        self.sequence_length = sequence_length

    def generate_from_video(
        self,
        video_path: str,
        detector,
        tracker,
        motion_analyzer,
        rule_classifier,
        frame_skip: int = 3,
        resize_width: int = 640,
    ) -> list:
        """
        Process a video and generate (feature_sequence, label) pairs.

        Args:
            video_path: Path to video file.
            detector: EquipmentDetector instance.
            tracker: EquipmentTracker instance.
            motion_analyzer: MotionAnalyzer instance.
            rule_classifier: ActivityClassifier instance.
            frame_skip: Process every Nth frame.
            resize_width: Resize width for inference.

        Returns:
            List of (feature_sequence, label_index) tuples where
            feature_sequence is a list of ``sequence_length`` feature vectors.
        """
        import cv2

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            logger.warning("Cannot open video: %s", video_path)
            return []

        # Per-equipment buffers and samples
        buffers: dict[str, deque] = {}
        samples = []
        prev_gray = None
        frame_idx = 0

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_skip != 0:
                frame_idx += 1
                continue

            # Resize
            if resize_width and frame.shape[1] != resize_width:
                aspect = frame.shape[0] / frame.shape[1]
                new_h = int(resize_width * aspect)
                frame = cv2.resize(frame, (resize_width, new_h))

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            frame_shape = frame.shape[:2]

            # Detect and track
            detections = detector.detect(frame)
            tracked = tracker.update(detections, frame)

            # Motion analysis
            motion_results_list = []
            if prev_gray is not None:
                motion_results_list = motion_analyzer.analyze(prev_gray, gray, tracked)

            # Classify with rule-based
            activities = rule_classifier.classify(tracked, motion_results_list)

            # Build motion map
            motion_map = {}
            if isinstance(motion_results_list, list):
                for mr in motion_results_list:
                    if isinstance(mr, dict) and 'equipment_id' in mr:
                        motion_map[mr['equipment_id']] = mr

            # Extract features and collect samples
            for obj in tracked:
                eq_id = obj.get('equipment_id', 'unknown')
                bbox = obj.get('bbox', (0, 0, 0, 0))
                motion_data = motion_map.get(eq_id, {
                    'motion_source': 'none',
                    'upper_magnitude': 0.0,
                    'lower_magnitude': 0.0,
                    'dominant_direction': 'none',
                    'flow_vectors': {
                        'upper_mean_dx': 0.0, 'upper_mean_dy': 0.0,
                        'lower_mean_dx': 0.0, 'lower_mean_dy': 0.0,
                    },
                })

                features = extract_features(motion_data, tuple(bbox), frame_shape)

                if eq_id not in buffers:
                    buffers[eq_id] = deque(maxlen=self.sequence_length)
                buffers[eq_id].append(features)

                # Get label from rule-based classifier
                activity_info = activities.get(eq_id, {})
                activity_label = activity_info.get('activity', 'WAITING')

                if len(buffers[eq_id]) >= self.sequence_length:
                    label_idx = (
                        self.ACTIVITIES.index(activity_label)
                        if activity_label in self.ACTIVITIES
                        else 3  # WAITING
                    )
                    samples.append((list(buffers[eq_id]), label_idx))

            prev_gray = gray
            frame_idx += 1

        cap.release()
        logger.info(
            "Generated %d training samples from %s", len(samples), video_path
        )
        return samples


def train_from_pseudo_labels(
    data_dir: str,
    output_path: str,
    epochs: int = 50,
    batch_size: int = 32,
    learning_rate: float = 1e-3,
    sequence_length: int = 16,
) -> Optional[str]:
    """
    Train LSTM using pseudo-labeled data generated by rule-based classifier.

    This function orchestrates end-to-end training:
    1. Discovers video files in data_dir
    2. Processes each video to extract feature sequences and pseudo-labels
    3. Splits data into train/val (80/20)
    4. Trains the ActivityLSTM model
    5. Saves the best model to output_path

    Args:
        data_dir: Directory containing video files.
        output_path: Where to save the trained .pth model.
        epochs: Number of training epochs.
        batch_size: Training batch size.
        learning_rate: Optimizer learning rate.
        sequence_length: Number of frames per training sequence.

    Returns:
        Path to saved model, or None on failure.
    """
    if not TORCH_AVAILABLE:
        logger.error("PyTorch is required for training but not installed")
        return None

    import cv2
    from pathlib import Path

    # Late imports to avoid circular dependency when used inside cv_service
    try:
        from services.cv_service.src.detector import EquipmentDetector
        from services.cv_service.src.tracker import EquipmentTracker
        from services.cv_service.src.motion_analyzer import MotionAnalyzer
        from services.cv_service.src.activity_classifier import ActivityClassifier
    except ImportError:
        from .detector import EquipmentDetector
        from .tracker import EquipmentTracker
        from .motion_analyzer import MotionAnalyzer
        from .activity_classifier import ActivityClassifier

    # Find video files
    video_dir = Path(data_dir)
    extensions = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}
    video_files = [
        f for f in video_dir.iterdir()
        if f.is_file() and f.suffix.lower() in extensions
    ]

    if not video_files:
        logger.error("No video files found in %s", data_dir)
        return None

    logger.info("Found %d video files for training", len(video_files))

    # Initialize pipeline components with default config
    detector = EquipmentDetector({'confidence_threshold': 0.4, 'device': 'cpu'})
    tracker = EquipmentTracker({'track_thresh': 0.25, 'track_buffer': 90, 'match_thresh': 0.8})
    motion_analyzer = MotionAnalyzer({'magnitude_threshold': 2.0, 'upper_region_ratio': 0.5})
    rule_classifier = ActivityClassifier({
        'smoothing_window': 5,
        'vertical_flow_threshold': 1.5,
        'horizontal_flow_threshold': 1.5,
    })

    generator = TrainingDataGenerator(sequence_length=sequence_length)

    # Collect training samples from all videos
    all_samples = []
    for vf in video_files:
        logger.info("Processing video: %s", vf.name)
        samples = generator.generate_from_video(
            str(vf), detector, tracker, motion_analyzer, rule_classifier
        )
        all_samples.extend(samples)

    if len(all_samples) < batch_size:
        logger.error(
            "Insufficient training data: %d samples (need at least %d)",
            len(all_samples), batch_size,
        )
        return None

    logger.info("Total training samples: %d", len(all_samples))

    # Prepare tensors
    features_list = [s[0] for s in all_samples]
    labels_list = [s[1] for s in all_samples]

    X = torch.FloatTensor(features_list)  # (N, seq_len, 12)
    y = torch.LongTensor(labels_list)     # (N,)

    # Train/val split (80/20)
    n_total = len(X)
    n_train = int(n_total * 0.8)
    indices = torch.randperm(n_total)

    X_train, y_train = X[indices[:n_train]], y[indices[:n_train]]
    X_val, y_val = X[indices[n_train:]], y[indices[n_train:]]

    logger.info("Train: %d samples, Val: %d samples", len(X_train), len(X_val))

    # Create DataLoaders
    train_dataset = torch.utils.data.TensorDataset(X_train, y_train)
    val_dataset = torch.utils.data.TensorDataset(X_val, y_val)
    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True
    )
    val_loader = torch.utils.data.DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False
    )

    # Initialize model, loss, optimizer
    model = ActivityLSTM()
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', patience=5, factor=0.5
    )

    # Ensure output directory exists
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Training loop
    best_val_loss = float('inf')
    best_epoch = 0

    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for batch_X, batch_y in train_loader:
            optimizer.zero_grad()
            outputs = model(batch_X)
            loss = criterion(outputs, batch_y)
            loss.backward()
            optimizer.step()

            train_loss += loss.item() * batch_X.size(0)
            _, predicted = outputs.max(1)
            train_correct += predicted.eq(batch_y).sum().item()
            train_total += batch_y.size(0)

        train_loss /= max(train_total, 1)
        train_acc = train_correct / max(train_total, 1)

        # Validate
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                val_loss += loss.item() * batch_X.size(0)
                _, predicted = outputs.max(1)
                val_correct += predicted.eq(batch_y).sum().item()
                val_total += batch_y.size(0)

        val_loss /= max(val_total, 1)
        val_acc = val_correct / max(val_total, 1)

        scheduler.step(val_loss)

        logger.info(
            "Epoch %d/%d — Train Loss: %.4f Acc: %.3f | Val Loss: %.4f Acc: %.3f",
            epoch + 1, epochs, train_loss, train_acc, val_loss, val_acc,
        )

        # Save best model
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_epoch = epoch + 1
            torch.save(model.state_dict(), output_path)
            logger.info("Saved best model at epoch %d (val_loss=%.4f)", best_epoch, best_val_loss)

    logger.info(
        "Training complete. Best model at epoch %d with val_loss=%.4f",
        best_epoch, best_val_loss,
    )

    # Report model size
    model_size = os.path.getsize(output_path) / 1024
    logger.info("Model size: %.1f KB", model_size)

    return output_path
            