"""
Train YOLOv8 on Video-based Accident Dataset

After training:
  1. Set TRAINED_MODEL = True in detector.py
  2. Run: python main.py --source video.mp4
         python main.py --source 0  (webcam)

Run:
  python train.py --dataset dataset --model s --epochs 100
"""

import argparse, os, shutil, yaml
from pathlib import Path
from ultralytics import YOLO


def create_yaml(dataset_root):
    dataset_root = os.path.abspath(dataset_root)

    # Use existing data.yaml from Roboflow if present
    for candidate in ["data.yaml", "dataset.yaml"]:
        yaml_path = os.path.join(dataset_root, candidate)
        if os.path.exists(yaml_path):
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f)
            cfg["path"] = dataset_root
            out = "dataset.yaml"
            with open(out, "w") as f:
                yaml.dump(cfg, f)
            print(f"[TRAIN] Using existing YAML: {yaml_path}")
            return out

    # Auto-create
    cfg = {
        "path":  dataset_root,
        "train": "images/train",
        "val":   "images/val",
        "nc":    2,
        "names": {0: "accident", 1: "non-accident"},
    }
    out = "dataset.yaml"
    with open(out, "w") as f:
        yaml.dump(cfg, f)
    print(f"[TRAIN] Created dataset.yaml")
    return out


def train(yaml_path, model_size="s", epochs=100, batch=8, imgsz=640):
    model = YOLO(f"yolov8{model_size}.pt")
    print(f"\n{'='*55}")
    print(f"  Training YOLOv8{model_size.upper()} for Accident Detection")
    print(f"  Epochs : {epochs} | Batch : {batch} | ImgSize : {imgsz}")
    print(f"  This model detects accidents in VIDEO frames")
    print(f"{'='*55}\n")

    model.train(
        data=dataset_yaml,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        project="runs/train",
        name="accident_detector",
        patience=20,
        save=True,
        save_period=10,
        device="cpu",
        workers=2,
        augment=True,
        mixup=0.1,
        fliplr=0.5,
        hsv_s=0.7,
        hsv_v=0.4,
        verbose=True,
    )

    best = Path("runs/train/accident_detector/weights/best.pt")
    if best.exists():
        os.makedirs("models", exist_ok=True)
        shutil.copy(best, "models/accident_yolov8_best.pt")
        print(f"\n{'='*55}")
        print(f"  Training Complete!")
        print(f"  Model saved: models/accident_yolov8_best.pt")
        print(f"  Now open detector.py and set TRAINED_MODEL = True")
        print(f"  Then run: python main.py --source video.mp4")
        print(f"{'='*55}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="dataset")
    parser.add_argument("--model",   default="s", choices=["n","s","m","l","x"])
    parser.add_argument("--epochs",  type=int, default=100)
    parser.add_argument("--batch",   type=int, default=8)
    parser.add_argument("--imgsz",   type=int, default=640)
    args = parser.parse_args()

    dataset_yaml = create_yaml(args.dataset)
    train(dataset_yaml, args.model, args.epochs, args.batch, args.imgsz)
