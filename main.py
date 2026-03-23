"""
AccidentWatch — Real-Time Detection
Laptop webcam → YOLOv8 → Severity → Location → DB → Twilio

Usage:
  python main.py              # built-in webcam
  python main.py --source 1   # external webcam
  python main.py --source video.mp4  # test with video
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import init_db
from detector import AccidentDetector


def main():
    parser = argparse.ArgumentParser(description="AccidentWatch Real-Time")
    parser.add_argument("--source",    default="0",     help="Camera index or video path")
    parser.add_argument("--camera_id", default="CAM_01",help="Camera name")
    parser.add_argument("--config",    default="config.json")
    args = parser.parse_args()

    # Load config
    if not os.path.exists(args.config):
        print(f"ERROR: {args.config} not found!")
        sys.exit(1)

    with open(args.config) as f:
        config = json.load(f)

    # Create folders
    os.makedirs(config["recordings_dir"], exist_ok=True)
    os.makedirs("models", exist_ok=True)

    # Init database
    init_db()

    # Parse source
    source = int(args.source) if args.source.isdigit() else args.source

    # Start detection
    detector = AccidentDetector(config)
    detector.run(source=source, camera_id=args.camera_id)


if __name__ == "__main__":
    main()
