"""Full training only - run with: docker exec -d container python /app/training/run_full_train.py"""
import os, sys, shutil, glob
log_f = open('/app/training/full_train_log.txt', 'w', buffering=1)
def log(m):
    log_f.write(m + '\n'); log_f.flush()
log("Starting full training...")
from ultralytics import YOLO
log("YOLO imported")
model = YOLO('yolov8n.pt')
log("Model loaded, starting training...")
try:
    results = model.train(
        data='/app/training/datasets/bootstrap/dataset.yaml',
        epochs=10,
        imgsz=640,
        batch=4,
        device='cpu',
        project='/app/training/runs',
        name='construction_equipment',
        workers=0,
        cache=True,
        patience=5,
        pretrained=True,
        optimizer='AdamW',
        lr0=0.001,
        augment=True,
        mosaic=0.5,
        verbose=True,
        exist_ok=True,
    )
    log("Training DONE!")
except Exception as e:
    import traceback
    log(f"FAILED: {e}\n{traceback.format_exc()}")
    sys.exit(1)
best = '/app/training/runs/construction_equipment/weights/best.pt'
out = '/app/models/construction_yolov8n.pt'
os.makedirs(os.path.dirname(out), exist_ok=True)
if os.path.exists(best):
    shutil.copy2(best, out)
    log(f"Model saved to {out}")
else:
    last = '/app/training/runs/construction_equipment/weights/last.pt'
    if os.path.exists(last):
        shutil.copy2(last, out)
        log(f"Last model saved to {out}")
# Verify
log("Verifying model...")
m2 = YOLO(out)
imgs = glob.glob('/app/training/datasets/bootstrap/test/images/*.jpg')
if imgs:
    r = m2(imgs[0], verbose=False)
    for det in r:
        log(f"Detections: {len(det.boxes)}")
        for b in det.boxes:
            c, cf = int(b.cls[0]), float(b.conf[0])
            log(f"  {m2.names[c]}: {cf:.3f}")
log("=== COMPLETE ===")
log_f.close()
