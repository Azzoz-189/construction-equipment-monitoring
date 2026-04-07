"""Quick 3-epoch training test, then full 20-epoch training."""
import os
import sys
import shutil

# Log to file
log_path = '/app/training/training_log.txt'
log_file = open(log_path, 'w', buffering=1)

def log(msg):
    print(msg, flush=True)
    log_file.write(msg + '\n')
    log_file.flush()

log("=== YOLOv8 Fine-tuning Script ===")

from ultralytics import YOLO

DATA_YAML = '/app/training/datasets/bootstrap/dataset.yaml'
PROJECT = '/app/training/runs'
MODEL_OUTPUT = '/app/models/construction_yolov8n.pt'

# Phase 1: Quick 3-epoch test
log("\n--- Phase 1: Quick 3-epoch test ---")
model = YOLO('yolov8n.pt')
try:
    results = model.train(
        data=DATA_YAML,
        epochs=3,
        imgsz=640,
        batch=4,
        device='cpu',
        project=PROJECT,
        name='quick_test',
        workers=1,
        cache=True,
        verbose=True,
        exist_ok=True,
    )
    log("Quick test PASSED!")
    log(f"Results dir: {PROJECT}/quick_test")
except Exception as e:
    log(f"Quick test FAILED: {e}")
    import traceback
    log(traceback.format_exc())
    sys.exit(1)

# Phase 2: Full 20-epoch training
log("\n--- Phase 2: Full 20-epoch training ---")
model2 = YOLO('yolov8n.pt')
try:
    results2 = model2.train(
        data=DATA_YAML,
        epochs=20,
        imgsz=640,
        batch=4,
        device='cpu',
        project=PROJECT,
        name='construction_equipment',
        workers=1,
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
    log("Full training PASSED!")
except Exception as e:
    log(f"Full training FAILED: {e}")
    import traceback
    log(traceback.format_exc())
    sys.exit(1)

# Copy best model
best_path = os.path.join(PROJECT, 'construction_equipment', 'weights', 'best.pt')
os.makedirs(os.path.dirname(MODEL_OUTPUT), exist_ok=True)
if os.path.exists(best_path):
    shutil.copy2(best_path, MODEL_OUTPUT)
    log(f"Best model copied to {MODEL_OUTPUT}")
else:
    # Try last.pt as fallback
    last_path = os.path.join(PROJECT, 'construction_equipment', 'weights', 'last.pt')
    if os.path.exists(last_path):
        shutil.copy2(last_path, MODEL_OUTPUT)
        log(f"Last model copied to {MODEL_OUTPUT} (best.pt not found)")
    else:
        log(f"WARNING: No model weights found at {best_path}")

# Phase 3: Verify model
log("\n--- Phase 3: Model Verification ---")
import glob
if os.path.exists(MODEL_OUTPUT):
    model3 = YOLO(MODEL_OUTPUT)
    test_images = glob.glob('/app/training/datasets/bootstrap/test/images/*.jpg')
    if test_images:
        results3 = model3(test_images[0], verbose=False)
        for r in results3:
            log(f"Detections: {len(r.boxes)}")
            for box in r.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                log(f"  Class {cls} ({model3.names[cls]}): {conf:.3f}")
    log("Model verification complete!")
else:
    log("Model not found for verification!")

log("\n=== Training pipeline complete! ===")
log_file.close()
