"""
Fine-tune YOLOv8n on construction equipment dataset.

This script fine-tunes the YOLOv8n model (pretrained on COCO) to detect
construction equipment classes: excavator, dump_truck, wheel_loader, crane, bulldozer.

Usage:
    python finetune_yolo.py --data dataset.yaml --epochs 50
    python finetune_yolo.py --data dataset.yaml --epochs 2 --device cpu  # Quick test
    python finetune_yolo.py --data dataset.yaml --epochs 50 --device 0   # GPU training
"""

import argparse
import os
import shutil

import yaml
from ultralytics import YOLO

# Default construction equipment classes
CONSTRUCTION_CLASSES = [
    "excavator",
    "dump_truck",
    "wheel_loader",
    "crane",
    "bulldozer",
]


def create_dataset_yaml(data_dir: str, output_path: str, classes: list) -> str:
    """
    Create YOLO dataset configuration file.

    Args:
        data_dir: Absolute path to dataset root directory.
        output_path: Path to write the YAML config file.
        classes: List of class name strings.

    Returns:
        The output_path where the config was saved.
    """
    config = {
        "path": data_dir,
        "train": "train/images",
        "val": "valid/images",
        "test": "test/images",
        "nc": len(classes),
        "names": classes,
    }
    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"Dataset config saved to {output_path}")
    return output_path


def finetune(
    data_yaml: str,
    base_model: str = "yolov8n.pt",
    epochs: int = 50,
    imgsz: int = 640,
    batch: int = 8,
    device: str = "cpu",
    project: str = "runs/train",
    name: str = "construction_equipment",
):
    """
    Fine-tune YOLOv8n on construction equipment data.

    Args:
        data_yaml: Path to dataset YAML configuration file.
        base_model: Path to base YOLOv8 model weights.
        epochs: Number of training epochs.
        imgsz: Input image size for training.
        batch: Batch size (reduce for CPU or low-memory GPU).
        device: Training device - 'cpu', '0' (GPU 0), '0,1' (multi-GPU).
        project: Project directory for saving training runs.
        name: Name of this training run.

    Returns:
        Training results object from ultralytics.
    """
    print("=" * 60)
    print("YOLOv8n Fine-Tuning for Construction Equipment Detection")
    print("=" * 60)
    print(f"  Base model:  {base_model}")
    print(f"  Dataset:     {data_yaml}")
    print(f"  Epochs:      {epochs}")
    print(f"  Image size:  {imgsz}")
    print(f"  Batch size:  {batch}")
    print(f"  Device:      {device}")
    print(f"  Output:      {project}/{name}")
    print("=" * 60)

    # Load pretrained YOLOv8n
    model = YOLO(base_model)

    # Start fine-tuning
    results = model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=project,
        name=name,
        patience=10,           # Early stopping patience
        save=True,             # Save checkpoints
        plots=True,            # Generate training plots
        verbose=True,          # Verbose output
        workers=2,             # CPU-friendly worker count
        cache=True,            # Cache images for speed
        pretrained=True,       # Use pretrained weights
        optimizer="AdamW",     # Optimizer
        lr0=0.001,             # Initial learning rate
        lrf=0.01,              # Final learning rate factor
        warmup_epochs=3,       # Warmup epochs
        augment=True,          # Enable augmentation
        mosaic=0.5,            # Mosaic augmentation probability
        mixup=0.1,             # Mixup augmentation probability
    )

    # Export best model to models/ directory
    best_model_path = os.path.join(project, name, "weights", "best.pt")
    output_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models",
        "construction_yolov8n.pt",
    )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if os.path.exists(best_model_path):
        shutil.copy2(best_model_path, output_path)
        print(f"\nBest model exported to: {output_path}")
        print("To use this model, update config/settings.yaml:")
        print('  model: "models/construction_yolov8n.pt"')
        print("  custom_model: true")
    else:
        print(f"\nWARNING: Best model not found at {best_model_path}")
        print("Check the training output for errors.")

    return results


def validate_model(model_path: str, data_yaml: str, device: str = "cpu"):
    """
    Run validation on the fine-tuned model.

    Args:
        model_path: Path to the trained model weights.
        data_yaml: Path to dataset YAML configuration.
        device: Inference device.

    Returns:
        Validation metrics from ultralytics.
    """
    print(f"\nValidating model: {model_path}")
    model = YOLO(model_path)
    metrics = model.val(data=data_yaml, device=device, verbose=True)

    print(f"\nValidation Results:")
    print(f"  mAP50:    {metrics.box.map50:.4f}")
    print(f"  mAP50-95: {metrics.box.map:.4f}")

    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fine-tune YOLOv8n on construction equipment dataset"
    )
    parser.add_argument(
        "--data",
        type=str,
        required=True,
        help="Path to dataset.yaml",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt",
        help="Base model path (default: yolov8n.pt)",
    )
    parser.add_argument("--epochs", type=int, default=50, help="Training epochs")
    parser.add_argument("--batch", type=int, default=8, help="Batch size")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument(
        "--device", type=str, default="cpu", help="Device: cpu, 0, 0,1"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validation after training",
    )

    args = parser.parse_args()

    results = finetune(
        data_yaml=args.data,
        base_model=args.model,
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        device=args.device,
    )

    if args.validate:
        model_path = os.path.join(
            "runs", "train", "construction_equipment", "weights", "best.pt"
        )
        if os.path.exists(model_path):
            validate_model(model_path, args.data, args.device)
        else:
            print("Skipping validation: best.pt not found")
