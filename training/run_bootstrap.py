"""
Run bootstrap dataset creation inside the container.
Usage: python /app/training/run_bootstrap.py
All output goes to /app/training/bootstrap_log.txt
"""
import os
import sys
import shutil
import glob
import random

# Force unbuffered output
sys.stdout = open('/app/training/bootstrap_log.txt', 'w', buffering=1)
sys.stderr = sys.stdout

print("=== Bootstrap Dataset Runner ===", flush=True)

# Clean up any previous partial run
output_dir = "/app/training/datasets/bootstrap"
if os.path.exists(output_dir):
    shutil.rmtree(output_dir)
    print(f"Cleaned up previous run at {output_dir}", flush=True)

import cv2
import numpy as np

print("Importing YOLO...", flush=True)
from ultralytics import YOLO

# Config
VIDEO_DIR = "/app/videos"
FRAME_SKIP = 30
MAX_FRAMES = 3000
CONFIDENCE = 0.3

# Class mapping: COCO -> construction
COCO_MAP = {
    2: 2,   # car -> vehicle
    5: 0,   # bus -> heavy_equipment
    7: 1,   # truck -> dump_truck
}
CLASS_NAMES = ["heavy_equipment", "dump_truck", "vehicle"]
TARGET_COCO = set(COCO_MAP.keys())

# Step 1: Extract frames from videos
print("\n--- Step 1: Extracting frames from videos ---", flush=True)
video_exts = {".mp4", ".avi", ".mkv", ".mov", ".webm"}
videos = sorted([
    os.path.join(VIDEO_DIR, f) for f in os.listdir(VIDEO_DIR)
    if os.path.splitext(f)[1].lower() in video_exts
])
print(f"Found {len(videos)} videos", flush=True)

all_frames = []
temp_frames_dir = os.path.join(output_dir, "_temp_frames")
os.makedirs(temp_frames_dir, exist_ok=True)

per_video_max = max(1, MAX_FRAMES // max(1, len(videos)))
for vi, vpath in enumerate(videos):
    cap = cv2.VideoCapture(vpath)
    if not cap.isOpened():
        print(f"  SKIP: Cannot open {vpath}", flush=True)
        continue
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    print(f"  Video {vi+1}/{len(videos)}: {os.path.basename(vpath)}", flush=True)
    print(f"    Frames: {total}, FPS: {fps:.1f}, extracting every {FRAME_SKIP}th", flush=True)
    
    idx = 0
    extracted = 0
    while cap.isOpened() and extracted < per_video_max:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % FRAME_SKIP == 0:
            fname = f"v{vi:02d}_f{idx:06d}.jpg"
            fpath = os.path.join(temp_frames_dir, fname)
            cv2.imwrite(fpath, frame)
            all_frames.append(fpath)
            extracted += 1
        idx += 1
    cap.release()
    print(f"    Extracted {extracted} frames", flush=True)

print(f"\nTotal frames extracted: {len(all_frames)}", flush=True)

if not all_frames:
    print("ERROR: No frames extracted!", flush=True)
    sys.exit(1)

# Step 2: Pseudo-label with YOLO
print("\n--- Step 2: Pseudo-labeling with YOLOv8n ---", flush=True)
model = YOLO("yolov8n.pt")

temp_images = os.path.join(output_dir, "_temp_images")
temp_labels = os.path.join(output_dir, "_temp_labels")
os.makedirs(temp_images, exist_ok=True)
os.makedirs(temp_labels, exist_ok=True)

frames_with_dets = 0
total_dets = 0

for i, fpath in enumerate(all_frames):
    if (i + 1) % 100 == 0 or i == 0:
        print(f"  Processing frame {i+1}/{len(all_frames)}...", flush=True)
    
    frame = cv2.imread(fpath)
    if frame is None:
        continue
    h, w = frame.shape[:2]
    
    results = model(frame, imgsz=640, device="cpu", verbose=False)
    if not results or len(results) == 0:
        continue
    
    result = results[0]
    if result.boxes is None or len(result.boxes) == 0:
        continue
    
    boxes = result.boxes.xyxy.cpu().numpy()
    confs = result.boxes.conf.cpu().numpy()
    clss = result.boxes.cls.cpu().numpy().astype(int)
    
    yolo_labels = []
    for bbox, conf, cls_id in zip(boxes, confs, clss):
        if cls_id not in TARGET_COCO:
            continue
        if conf < CONFIDENCE:
            continue
        new_cls = COCO_MAP[cls_id]
        x1, y1, x2, y2 = bbox
        xc = ((x1 + x2) / 2) / w
        yc = ((y1 + y2) / 2) / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h
        yolo_labels.append(f"{new_cls} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    
    if yolo_labels:
        img_name = f"bootstrap_{i:06d}.jpg"
        shutil.copy2(fpath, os.path.join(temp_images, img_name))
        with open(os.path.join(temp_labels, f"bootstrap_{i:06d}.txt"), "w") as f:
            f.write("\n".join(yolo_labels) + "\n")
        frames_with_dets += 1
        total_dets += len(yolo_labels)

print(f"\nFrames with detections: {frames_with_dets}/{len(all_frames)}", flush=True)
print(f"Total detections: {total_dets}", flush=True)

if frames_with_dets == 0:
    print("ERROR: No detections found! Check confidence threshold.", flush=True)
    sys.exit(1)

# Step 3: Split dataset
print("\n--- Step 3: Splitting into train/valid/test ---", flush=True)
image_files = sorted([f for f in os.listdir(temp_images) if f.endswith(".jpg")])
random.seed(42)
random.shuffle(image_files)

n = len(image_files)
n_train = int(n * 0.80)
n_val = int(n * 0.15)

splits = {
    "train": image_files[:n_train],
    "valid": image_files[n_train:n_train+n_val],
    "test": image_files[n_train+n_val:],
}

for split, files in splits.items():
    img_dir = os.path.join(output_dir, split, "images")
    lbl_dir = os.path.join(output_dir, split, "labels")
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(lbl_dir, exist_ok=True)
    for f in files:
        shutil.copy2(os.path.join(temp_images, f), os.path.join(img_dir, f))
        lf = f.replace(".jpg", ".txt")
        src_lbl = os.path.join(temp_labels, lf)
        if os.path.exists(src_lbl):
            shutil.copy2(src_lbl, os.path.join(lbl_dir, lf))
    print(f"  {split}: {len(files)} images", flush=True)

# Cleanup temp
for d in [temp_images, temp_labels, temp_frames_dir]:
    if os.path.isdir(d):
        shutil.rmtree(d)

# Step 4: Create dataset.yaml
print("\n--- Step 4: Creating dataset.yaml ---", flush=True)
import yaml
ds_yaml = {
    "path": output_dir,
    "train": "train/images",
    "val": "valid/images",
    "test": "test/images",
    "nc": len(CLASS_NAMES),
    "names": {i: name for i, name in enumerate(CLASS_NAMES)},
}
yaml_path = os.path.join(output_dir, "dataset.yaml")
with open(yaml_path, "w") as f:
    yaml.dump(ds_yaml, f, default_flow_style=False)
print(f"Saved dataset.yaml to {yaml_path}", flush=True)

print("\n=== Bootstrap complete! ===", flush=True)
for split, files in splits.items():
    print(f"  {split}: {len(files)} images", flush=True)
print(f"  Classes: {CLASS_NAMES}", flush=True)
print(f"  Total detections: {total_dets}", flush=True)
