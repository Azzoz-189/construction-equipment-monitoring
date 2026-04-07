"""Quick test to verify YOLO detection works on extracted frames."""
import sys
import glob
from ultralytics import YOLO

print("Loading model...", flush=True)
m = YOLO("yolov8n.pt")
imgs = sorted(glob.glob("/app/training/datasets/bootstrap/_temp_frames/*.jpg"))
print(f"Found {len(imgs)} frames", flush=True)

if not imgs:
    print("No frames found!", flush=True)
    sys.exit(1)

# Test first frame
r = m(imgs[0], verbose=False)
boxes = r[0].boxes
print(f"Detections in first frame: {len(boxes)}", flush=True)
for c, f in zip(boxes.cls, boxes.conf):
    cls_id = int(c)
    conf = float(f)
    name = m.names[cls_id]
    print(f"  cls={cls_id} ({name}) conf={conf:.2f}", flush=True)

# Count target classes across first 10 frames
target = {2, 5, 7}
total_target = 0
for img in imgs[:10]:
    r = m(img, verbose=False)
    for c in r[0].boxes.cls:
        if int(c) in target:
            total_target += 1
print(f"\nTarget class detections (cls 2,5,7) in first 10 frames: {total_target}", flush=True)
print("Done!", flush=True)
