"""
Bootstrap Dataset Creator for Construction Equipment Detection.

Creates a pseudo-labeled dataset by running the current YOLOv8n (COCO) model
on video frames from the project's video directory. Detected vehicles are
extracted with bounding boxes and saved in YOLO format for fine-tuning.

This bootstrap approach lets the model learn to detect the specific equipment
types present in the deployment environment, even without a purpose-built
construction equipment dataset.

Usage:
    python bootstrap_dataset.py
    python bootstrap_dataset.py --video-dir ../videos --frame-skip 30
    python bootstrap_dataset.py --frames-dir ../frames
"""

import argparse
import os
import random
import shutil
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

# Resolve script directory safely (works in Docker exec, standalone, etc.)
try:
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _SCRIPT_DIR = os.path.abspath("training")

_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)

# COCO class IDs that map to construction equipment
COCO_TO_CONSTRUCTION = {
    2: 2,   # car -> vehicle (small vehicles on site)
    5: 0,   # bus -> heavy_equipment (large vehicles / heavy machinery)
    7: 1,   # truck -> dump_truck (direct mapping)
}

# Construction equipment class names (bootstrap classes)
CONSTRUCTION_CLASSES = ["heavy_equipment", "dump_truck", "vehicle"]


def extract_frames_from_video(
    video_path: str,
    output_dir: str,
    frame_skip: int = 30,
    max_frames: int = 2000,
) -> list[str]:
    """
    Extract frames from a video file at regular intervals.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save extracted frames.
        frame_skip: Extract every Nth frame.
        max_frames: Maximum number of frames to extract.

    Returns:
        List of saved frame file paths.
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        print(f"ERROR: Cannot open video: {video_path}")
        return []

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"Video: {video_path}")
    print(f"  Total frames: {total_frames}, FPS: {fps:.1f}")
    print(f"  Extracting every {frame_skip}th frame (max {max_frames})...")

    saved_frames = []
    frame_idx = 0
    extracted = 0

    while cap.isOpened() and extracted < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_skip == 0:
            filename = f"frame_{frame_idx:06d}.jpg"
            filepath = os.path.join(output_dir, filename)
            cv2.imwrite(filepath, frame)
            saved_frames.append(filepath)
            extracted += 1

        frame_idx += 1

    cap.release()
    print(f"  Extracted {extracted} frames")
    return saved_frames


def collect_existing_frames(frames_dir: str, max_frames: int = 2000) -> list[str]:
    """
    Collect existing frame images from the frames directory.

    Args:
        frames_dir: Directory containing frame images.
        max_frames: Maximum number of frames to collect.

    Returns:
        List of frame file paths.
    """
    if not os.path.isdir(frames_dir):
        print(f"Frames directory not found: {frames_dir}")
        return []

    extensions = {".jpg", ".jpeg", ".png", ".bmp"}
    frames = sorted([
        os.path.join(frames_dir, f)
        for f in os.listdir(frames_dir)
        if os.path.splitext(f)[1].lower() in extensions
        and f != "latest_frame.jpg"
    ])

    if len(frames) > max_frames:
        # Evenly sample frames
        step = len(frames) // max_frames
        frames = frames[::step][:max_frames]

    print(f"Collected {len(frames)} frames from {frames_dir}")
    return frames


def generate_pseudo_labels(
    model: YOLO,
    frame_paths: list[str],
    output_images_dir: str,
    output_labels_dir: str,
    confidence_threshold: float = 0.4,
    class_mapping: dict = None,
) -> int:
    """
    Run YOLO detection on frames and save pseudo-labels in YOLO format.

    Args:
        model: Loaded YOLO model instance.
        frame_paths: List of paths to frame images.
        output_images_dir: Directory to save images.
        output_labels_dir: Directory to save YOLO label files.
        confidence_threshold: Minimum confidence for including detections.
        class_mapping: Optional mapping from COCO class IDs to custom class IDs.

    Returns:
        Number of frames with at least one detection.
    """
    if class_mapping is None:
        class_mapping = COCO_TO_CONSTRUCTION

    os.makedirs(output_images_dir, exist_ok=True)
    os.makedirs(output_labels_dir, exist_ok=True)

    target_coco_classes = list(class_mapping.keys())
    frames_with_detections = 0

    for i, frame_path in enumerate(frame_paths):
        if (i + 1) % 50 == 0 or i == 0:
            print(f"  Processing frame {i + 1}/{len(frame_paths)}...")

        frame = cv2.imread(frame_path)
        if frame is None:
            continue

        h, w = frame.shape[:2]

        # Run detection
        results = model(frame, imgsz=640, device="cpu", verbose=False)

        if not results or len(results) == 0:
            continue

        result = results[0]
        if result.boxes is None or len(result.boxes) == 0:
            continue

        boxes = result.boxes.xyxy.cpu().numpy()
        confidences = result.boxes.conf.cpu().numpy()
        class_ids = result.boxes.cls.cpu().numpy().astype(int)

        # Filter and convert to YOLO format
        yolo_labels = []
        for bbox, conf, cls_id in zip(boxes, confidences, class_ids):
            if cls_id not in target_coco_classes:
                continue
            if conf < confidence_threshold:
                continue

            # Map COCO class to construction class
            new_cls_id = class_mapping[cls_id]

            # Convert xyxy to YOLO format (x_center, y_center, width, height) normalized
            x1, y1, x2, y2 = bbox
            x_center = ((x1 + x2) / 2) / w
            y_center = ((y1 + y2) / 2) / h
            box_w = (x2 - x1) / w
            box_h = (y2 - y1) / h

            yolo_labels.append(f"{new_cls_id} {x_center:.6f} {y_center:.6f} {box_w:.6f} {box_h:.6f}")

        if yolo_labels:
            # Save image
            img_name = f"bootstrap_{i:06d}.jpg"
            img_path = os.path.join(output_images_dir, img_name)
            shutil.copy2(frame_path, img_path)

            # Save label
            lbl_name = f"bootstrap_{i:06d}.txt"
            lbl_path = os.path.join(output_labels_dir, lbl_name)
            with open(lbl_path, "w") as f:
                f.write("\n".join(yolo_labels) + "\n")

            frames_with_detections += 1

    return frames_with_detections


def split_dataset(
    images_dir: str,
    labels_dir: str,
    output_dir: str,
    train_ratio: float = 0.8,
    val_ratio: float = 0.15,
) -> dict:
    """
    Split generated dataset into train/valid/test splits.

    Args:
        images_dir: Directory with all images.
        labels_dir: Directory with all labels.
        output_dir: Root output directory for splits.
        train_ratio: Fraction for training set.
        val_ratio: Fraction for validation set.

    Returns:
        Dict with split counts: {'train': N, 'valid': N, 'test': N}
    """
    image_files = sorted([
        f for f in os.listdir(images_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ])

    random.seed(42)
    random.shuffle(image_files)

    n = len(image_files)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    splits = {
        "train": image_files[:n_train],
        "valid": image_files[n_train:n_train + n_val],
        "test": image_files[n_train + n_val:],
    }

    counts = {}
    for split_name, files in splits.items():
        split_img_dir = os.path.join(output_dir, split_name, "images")
        split_lbl_dir = os.path.join(output_dir, split_name, "labels")
        os.makedirs(split_img_dir, exist_ok=True)
        os.makedirs(split_lbl_dir, exist_ok=True)

        for img_file in files:
            src_img = os.path.join(images_dir, img_file)
            dst_img = os.path.join(split_img_dir, img_file)
            shutil.copy2(src_img, dst_img)

            lbl_file = os.path.splitext(img_file)[0] + ".txt"
            src_lbl = os.path.join(labels_dir, lbl_file)
            if os.path.exists(src_lbl):
                dst_lbl = os.path.join(split_lbl_dir, lbl_file)
                shutil.copy2(src_lbl, dst_lbl)

        counts[split_name] = len(files)
        print(f"  {split_name}: {len(files)} images")

    return counts


def create_dataset_yaml(output_dir: str, yaml_path: str) -> str:
    """
    Create dataset.yaml for the bootstrap dataset.

    Args:
        output_dir: Root dataset directory.
        yaml_path: Path to save the YAML file.

    Returns:
        Path to the created YAML file.
    """
    import yaml

    config = {
        "path": os.path.abspath(output_dir),
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(CONSTRUCTION_CLASSES),
        "names": {i: name for i, name in enumerate(CONSTRUCTION_CLASSES)},
    }

    with open(yaml_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)

    print(f"Dataset YAML saved to: {yaml_path}")
    return yaml_path


def main():
    parser = argparse.ArgumentParser(
        description="Create bootstrap dataset from project videos/frames"
    )
    parser.add_argument(
        "--video-dir",
        type=str,
        default=os.path.join(_PROJECT_ROOT, "videos"),
        help="Directory containing video files",
    )
    parser.add_argument(
        "--frames-dir",
        type=str,
        default=os.path.join(_PROJECT_ROOT, "frames"),
        help="Directory containing extracted frames",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(_SCRIPT_DIR, "datasets", "bootstrap"),
        help="Output directory for bootstrap dataset",
    )
    parser.add_argument(
        "--frame-skip",
        type=int,
        default=30,
        help="Extract every Nth frame from videos",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=2000,
        help="Maximum frames to process",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.4,
        help="Minimum detection confidence",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="YOLO model for pseudo-labeling",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Bootstrap Dataset Creator")
    print("=" * 60)

    # Step 1: Collect frames
    all_frames = []

    # From existing frames directory
    if os.path.isdir(args.frames_dir):
        all_frames.extend(collect_existing_frames(args.frames_dir, args.max_frames))

    # From video files
    if os.path.isdir(args.video_dir):
        video_extensions = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
        video_files = [
            os.path.join(args.video_dir, f)
            for f in os.listdir(args.video_dir)
            if os.path.splitext(f)[1].lower() in video_extensions
        ]
        remaining = args.max_frames - len(all_frames)
        per_video = max(1, remaining // max(1, len(video_files)))
        for vf in video_files:
            temp_dir = os.path.join(args.output, "_temp_frames")
            frames = extract_frames_from_video(vf, temp_dir, args.frame_skip, per_video)
            all_frames.extend(frames)

    if not all_frames:
        print("ERROR: No frames found. Provide --video-dir or --frames-dir")
        return

    print(f"\nTotal frames collected: {len(all_frames)}")

    # Step 2: Generate pseudo-labels
    print("\nLoading YOLO model for pseudo-labeling...")
    model = YOLO(args.model)

    temp_images = os.path.join(args.output, "_temp_images")
    temp_labels = os.path.join(args.output, "_temp_labels")

    print("Generating pseudo-labels...")
    n_detected = generate_pseudo_labels(
        model=model,
        frame_paths=all_frames,
        output_images_dir=temp_images,
        output_labels_dir=temp_labels,
        confidence_threshold=args.confidence,
    )
    print(f"Frames with detections: {n_detected}/{len(all_frames)}")

    if n_detected == 0:
        print("WARNING: No detections found. Try lowering --confidence threshold.")
        return

    # Step 3: Split into train/valid/test
    print("\nSplitting dataset...")
    counts = split_dataset(temp_images, temp_labels, args.output)

    # Cleanup temp directories
    for temp_dir in [temp_images, temp_labels, os.path.join(args.output, "_temp_frames")]:
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)

    # Step 4: Create dataset.yaml
    yaml_path = os.path.join(args.output, "dataset.yaml")
    create_dataset_yaml(args.output, yaml_path)

    print("\n" + "=" * 60)
    print("Bootstrap dataset created successfully!")
    print(f"  Location: {args.output}")
    print(f"  Train: {counts.get('train', 0)} images")
    print(f"  Valid: {counts.get('valid', 0)} images")
    print(f"  Test:  {counts.get('test', 0)} images")
    print(f"  Classes: {CONSTRUCTION_CLASSES}")
    print("")
    print("NOTE: This is a PSEUDO-LABELED dataset using COCO detections as proxy.")
    print("The labels map COCO vehicle classes to construction equipment classes.")
    print("For best results, manually verify and correct a subset of labels.")
    print("")
    print("Next: Fine-tune with:")
    print(f"  python training/finetune_yolo.py --data {yaml_path} --epochs 50")
    print("=" * 60)


if __name__ == "__main__":
    main()
