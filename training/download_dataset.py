"""
Download construction equipment detection datasets for YOLOv8 fine-tuning.

Supports multiple download methods:
1. Roboflow Universe (requires API key)
2. Kaggle datasets (requires kaggle CLI)
3. Direct URL download (no auth needed)

Usage:
    python download_dataset.py --method roboflow --api-key YOUR_KEY
    python download_dataset.py --method kaggle
    python download_dataset.py --method direct
"""

import argparse
import os
import shutil
import zipfile
from pathlib import Path


# Target classes for construction equipment detection
TARGET_CLASSES = ["excavator", "dump_truck", "wheel_loader", "crane", "bulldozer"]

# Dataset output directory
DEFAULT_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "datasets", "construction_equipment")


def download_roboflow(api_key: str, output_dir: str) -> str:
    """
    Download construction equipment dataset from Roboflow Universe.

    Recommended datasets:
    - "Construction_Equipment" by ConstructionEquipment (9999 images)
      URL: https://universe.roboflow.com/constructionequipment-ejop6/construction_equipment
      Classes: crane, excavator, tractor, truck

    - "Construction Equipment" by Yolo (1520 images)
      URL: https://universe.roboflow.com/yolo-lt96t/construction-equipment-6r96y-h5vko
      Classes: Excavator

    Args:
        api_key: Roboflow API key (get from https://app.roboflow.com/settings/api)
        output_dir: Directory to save dataset

    Returns:
        Path to the downloaded dataset directory.
    """
    try:
        from roboflow import Roboflow
    except ImportError:
        print("ERROR: roboflow package not installed. Run: pip install roboflow")
        raise

    rf = Roboflow(api_key=api_key)

    # Primary dataset: Construction_Equipment (9999 images, 4 classes)
    print("Downloading 'Construction_Equipment' dataset from Roboflow Universe...")
    print("Classes: crane, excavator, tractor, truck")
    project = rf.workspace("constructionequipment-ejop6").project("construction_equipment")
    version = project.version(1)
    dataset = version.download("yolov8", location=output_dir)

    print(f"Dataset downloaded to: {output_dir}")
    print("NOTE: You may need to remap class names to match target classes.")
    print(f"  Target classes: {TARGET_CLASSES}")
    return output_dir


def download_kaggle(output_dir: str) -> str:
    """
    Download construction vehicle dataset from Kaggle.

    Dataset: 'cubeai/construction-vehicle-detection-for-yolov8'
    URL: https://www.kaggle.com/datasets/cubeai/construction-vehicle-detection-for-yolov8

    Requires:
        - kaggle CLI installed: pip install kaggle
        - Kaggle API token at ~/.kaggle/kaggle.json

    Args:
        output_dir: Directory to save dataset

    Returns:
        Path to the downloaded dataset directory.
    """
    import subprocess

    os.makedirs(output_dir, exist_ok=True)

    dataset_name = "cubeai/construction-vehicle-detection-for-yolov8"
    zip_path = os.path.join(output_dir, "dataset.zip")

    print(f"Downloading '{dataset_name}' from Kaggle...")
    cmd = [
        "kaggle", "datasets", "download",
        "-d", dataset_name,
        "-p", output_dir,
        "--force"
    ]

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        print("ERROR: kaggle CLI not found. Run: pip install kaggle")
        print("Also ensure your Kaggle API token is at ~/.kaggle/kaggle.json")
        raise
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Kaggle download failed: {e.stderr}")
        raise

    # Extract zip
    zip_files = list(Path(output_dir).glob("*.zip"))
    for zf in zip_files:
        print(f"Extracting {zf}...")
        with zipfile.ZipFile(zf, "r") as z:
            z.extractall(output_dir)
        os.remove(zf)

    print(f"Dataset extracted to: {output_dir}")
    _organize_yolo_splits(output_dir)
    return output_dir


def download_direct(output_dir: str) -> str:
    """
    Download a publicly available construction equipment dataset via direct URL.

    This method tries to use ultralytics hub or publicly hosted datasets
    that don't require authentication.

    Args:
        output_dir: Directory to save dataset

    Returns:
        Path to the downloaded dataset directory.
    """
    import urllib.request

    os.makedirs(output_dir, exist_ok=True)

    # Public construction equipment datasets (direct download links)
    # These are commonly available open datasets
    urls = [
        # Open Images V7 subset - construction vehicles
        # You can generate a subset at: https://storage.googleapis.com/openimages/web/index.html
    ]

    if not urls:
        print("No direct download URLs configured.")
        print("Recommended alternatives:")
        print("  1. Use --method roboflow with an API key")
        print("  2. Use --method kaggle with kaggle CLI")
        print("  3. Use bootstrap_dataset.py to create a dataset from your videos")
        print("")
        print("Creating placeholder directory structure...")
        _create_placeholder_structure(output_dir)
        return output_dir

    for url in urls:
        filename = url.split("/")[-1]
        filepath = os.path.join(output_dir, filename)
        print(f"Downloading {filename}...")
        urllib.request.urlretrieve(url, filepath)

        if filepath.endswith(".zip"):
            with zipfile.ZipFile(filepath, "r") as z:
                z.extractall(output_dir)
            os.remove(filepath)

    _organize_yolo_splits(output_dir)
    return output_dir


def _create_placeholder_structure(output_dir: str) -> None:
    """Create the expected YOLO dataset directory structure with placeholder files."""
    for split in ["train", "valid", "test"]:
        images_dir = os.path.join(output_dir, split, "images")
        labels_dir = os.path.join(output_dir, split, "labels")
        os.makedirs(images_dir, exist_ok=True)
        os.makedirs(labels_dir, exist_ok=True)

    print(f"Placeholder directory structure created at: {output_dir}")
    print("  train/images/  train/labels/")
    print("  valid/images/  valid/labels/")
    print("  test/images/   test/labels/")
    print("")
    print("Add your images (.jpg) and YOLO labels (.txt) to these directories.")
    print("Label format per line: <class_id> <x_center> <y_center> <width> <height>")
    print(f"Class mapping: { {i: c for i, c in enumerate(TARGET_CLASSES)} }")


def _organize_yolo_splits(output_dir: str) -> None:
    """Ensure the dataset has proper train/valid/test split structure."""
    expected_splits = ["train", "valid", "test"]
    existing = [d for d in expected_splits if os.path.isdir(os.path.join(output_dir, d))]

    if len(existing) >= 2:
        print(f"Dataset already has splits: {existing}")
        return

    # Check for alternative split names
    alt_names = {"val": "valid", "validation": "valid"}
    for alt, standard in alt_names.items():
        alt_path = os.path.join(output_dir, alt)
        std_path = os.path.join(output_dir, standard)
        if os.path.isdir(alt_path) and not os.path.isdir(std_path):
            shutil.move(alt_path, std_path)
            print(f"Renamed {alt}/ -> {standard}/")

    # If only images directory exists (flat structure), create splits
    images_dir = os.path.join(output_dir, "images")
    labels_dir = os.path.join(output_dir, "labels")
    if os.path.isdir(images_dir) and os.path.isdir(labels_dir):
        print("Flat structure detected. Creating train/valid/test splits (80/15/5)...")
        _split_flat_dataset(output_dir, train_ratio=0.8, val_ratio=0.15)


def _split_flat_dataset(
    output_dir: str, train_ratio: float = 0.8, val_ratio: float = 0.15
) -> None:
    """Split a flat images/labels structure into train/valid/test."""
    import random

    images_dir = os.path.join(output_dir, "images")
    labels_dir = os.path.join(output_dir, "labels")

    image_files = sorted([
        f for f in os.listdir(images_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.bmp'))
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

    for split_name, files in splits.items():
        split_img_dir = os.path.join(output_dir, split_name, "images")
        split_lbl_dir = os.path.join(output_dir, split_name, "labels")
        os.makedirs(split_img_dir, exist_ok=True)
        os.makedirs(split_lbl_dir, exist_ok=True)

        for img_file in files:
            src_img = os.path.join(images_dir, img_file)
            dst_img = os.path.join(split_img_dir, img_file)
            shutil.copy2(src_img, dst_img)

            # Copy corresponding label
            label_file = os.path.splitext(img_file)[0] + ".txt"
            src_lbl = os.path.join(labels_dir, label_file)
            if os.path.exists(src_lbl):
                dst_lbl = os.path.join(split_lbl_dir, label_file)
                shutil.copy2(src_lbl, dst_lbl)

        print(f"  {split_name}: {len(files)} images")

    # Remove original flat dirs
    shutil.rmtree(images_dir)
    shutil.rmtree(labels_dir)
    print("Split complete. Original flat directories removed.")


def remap_classes(dataset_dir: str, class_mapping: dict) -> None:
    """
    Remap class IDs in YOLO label files.

    Useful when downloaded dataset has different class IDs than our target.

    Args:
        dataset_dir: Root dataset directory with train/valid/test splits
        class_mapping: Dict mapping old class ID -> new class ID
                       e.g., {0: 0, 1: 3, 2: 1, 3: 4} 

    Example:
        If Roboflow dataset has: {0: crane, 1: excavator, 2: tractor, 3: truck}
        And we want:             {0: excavator, 1: dump_truck, 2: wheel_loader, 3: crane, 4: bulldozer}
        Then mapping would be:   {0: 3, 1: 0, 2: 2, 3: 1}  (crane->3, excavator->0, etc.)
    """
    for split in ["train", "valid", "test"]:
        labels_dir = os.path.join(dataset_dir, split, "labels")
        if not os.path.isdir(labels_dir):
            continue

        count = 0
        for label_file in os.listdir(labels_dir):
            if not label_file.endswith(".txt"):
                continue

            filepath = os.path.join(labels_dir, label_file)
            with open(filepath, "r") as f:
                lines = f.readlines()

            new_lines = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 5:
                    old_id = int(parts[0])
                    if old_id in class_mapping:
                        parts[0] = str(class_mapping[old_id])
                        new_lines.append(" ".join(parts) + "\n")
                    # Skip classes not in mapping (discard)

            with open(filepath, "w") as f:
                f.writelines(new_lines)
            count += 1

        print(f"Remapped {count} label files in {split}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download construction equipment dataset for YOLOv8 fine-tuning"
    )
    parser.add_argument(
        "--method",
        choices=["roboflow", "kaggle", "direct"],
        default="direct",
        help="Download method (default: direct)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Roboflow API key (required for roboflow method)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for dataset"
    )
    parser.add_argument(
        "--remap",
        action="store_true",
        help="Remap class IDs after download (interactive)"
    )
    args = parser.parse_args()

    print(f"Download method: {args.method}")
    print(f"Output directory: {args.output}")
    print(f"Target classes: {TARGET_CLASSES}")
    print("=" * 60)

    if args.method == "roboflow":
        if not args.api_key:
            api_key = os.environ.get("ROBOFLOW_API_KEY")
            if not api_key:
                print("ERROR: Roboflow API key required.")
                print("  Use --api-key YOUR_KEY or set ROBOFLOW_API_KEY env variable")
                print("  Get your key at: https://app.roboflow.com/settings/api")
                exit(1)
        else:
            api_key = args.api_key
        download_roboflow(api_key, args.output)

    elif args.method == "kaggle":
        download_kaggle(args.output)

    elif args.method == "direct":
        download_direct(args.output)

    print("\nDone! Dataset is ready at:", args.output)
    print("Next steps:")
    print("  1. Verify dataset structure (train/valid/test with images/ and labels/)")
    print("  2. Update training/dataset.yaml 'path' if needed")
    print("  3. Run: python training/finetune_yolo.py --data training/dataset.yaml --epochs 50")
