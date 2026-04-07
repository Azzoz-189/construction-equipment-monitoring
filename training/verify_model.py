"""Verify the fine-tuned model. Output to /app/training/verify_log.txt"""
import os, sys, glob
log_f = open('/app/training/verify_log.txt', 'w', buffering=1)
def log(m):
    log_f.write(m + '\n'); log_f.flush()
log("=== Model Verification ===")
from ultralytics import YOLO
model_path = '/app/models/construction_yolov8n.pt'
log(f"Loading model from {model_path}")
if not os.path.exists(model_path):
    log("ERROR: Model not found!")
    sys.exit(1)
model = YOLO(model_path)
log(f"Model classes: {model.names}")
images = sorted(glob.glob('/app/training/datasets/bootstrap/test/images/*.jpg'))
log(f"Test images: {len(images)}")
total_dets = 0
for img_path in images[:5]:
    results = model(img_path, verbose=False)
    for r in results:
        n = len(r.boxes)
        total_dets += n
        log(f"  {os.path.basename(img_path)}: {n} detections")
        for box in r.boxes:
            cls = int(box.cls[0])
            conf = float(box.conf[0])
            log(f"    {model.names[cls]}: {conf:.3f}")
log(f"Total detections in {min(5, len(images))} test images: {total_dets}")
log("=== Verification DONE ===")
log_f.close()
