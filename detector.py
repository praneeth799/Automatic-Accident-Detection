"""
Real-Time Accident Detector
Works with:
- Webcam (live)
- Video file (python main.py --source video.mp4)
- RTSP stream

TRAINED_MODEL = False  → base YOLOv8 (vehicle proximity detection)
TRAINED_MODEL = True   → after training on accident dataset
"""

import cv2
import os
import threading
import time
from datetime import datetime
from collections import deque

from ultralytics import YOLO
from utils.severity import SeverityAnalyzer
from utils.recorder import ClipRecorder
from utils.location import get_location
from alerts.caller import EmergencyAlert
from database.db_manager import save_accident

# ------------------------------------------------------------------ #
#  CHANGE TO True AFTER TRAINING                                       #
# ------------------------------------------------------------------ #
TRAINED_MODEL = False

VEHICLE_CLASSES  = {"car","truck","bus","motorcycle","bicycle","motorbike","van"}
ACCIDENT_CLASSES = {"accident","crash","collision","Accident","accident-car"}


class AccidentDetector:
    def __init__(self, config):
        self.config      = config
        self.conf_thresh = config.get("confidence_threshold", 0.40)

        print("[SYSTEM] Loading YOLOv8 model...")
        self.model = YOLO(config["model_path"])
        print(f"[SYSTEM] Model loaded")
        print(f"[SYSTEM] Mode: {'TRAINED' if TRAINED_MODEL else 'BASE MODEL'}")

        self.sev      = SeverityAnalyzer()
        self.recorder = ClipRecorder(config["recordings_dir"])
        self.alert    = EmergencyAlert(config)

        fps = config.get("fps", 25)
        self.frame_buffer  = deque(maxlen=fps * 10)
        self.prev_frame    = None
        self.cooldown      = {}
        self.cooldown_secs = 60

        # Base model: consecutive frame counter
        self.vframe_count = 0
        self.VFRAME_THRESH = 6    # detect after 6 consecutive frames (~0.2s)
        self.MIN_VEHICLES  = 2

    def _open_source(self, source, camera_id):
        """Open webcam or video file."""
        if isinstance(source, int):
            # Webcam
            for backend, name in [
                (cv2.CAP_MSMF,  "MSMF"),
                (cv2.CAP_DSHOW, "DirectShow"),
                (cv2.CAP_ANY,   "Default"),
            ]:
                print(f"[{camera_id}] Trying backend: {name}...")
                cap = cv2.VideoCapture(source, backend)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 30)
                    for _ in range(3):
                        cap.read()
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        print(f"[{camera_id}] Camera opened: {name}")
                        return cap
                cap.release()
            return None
        else:
            # Video file or RTSP
            cap = cv2.VideoCapture(source)
            if cap.isOpened():
                print(f"[{camera_id}] Video opened: {source}")
                return cap
            return None

    def run(self, source=0, camera_id="CAM_01"):
        cap = self._open_source(source, camera_id)
        if cap is None:
            print(f"[ERROR] Cannot open source: {source}")
            return

        fps    = cap.get(cv2.CAP_PROP_FPS) or 25
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        is_video = not isinstance(source, int)

        print(f"\n{'='*55}")
        print(f"  AccidentWatch — LIVE DETECTION")
        print(f"  Source   : {'Video: '+str(source) if is_video else 'Webcam'}")
        print(f"  Camera   : {camera_id}")
        print(f"  Feed     : {width}x{height} @ {fps:.0f} FPS")
        print(f"  Alert to : {self.config['alert_phone']}")
        print(f"  Press Q  : to quit")
        print(f"{'='*55}\n")

        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                if is_video:
                    print("[INFO] Video ended.")
                    break
                time.sleep(0.05)
                continue

            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            self.frame_buffer.append(frame.copy())
            frame_count += 1

            # Run detection
            if TRAINED_MODEL:
                annotated, detected, confidence, boxes = self._detect_trained(frame)
            else:
                annotated, detected, confidence, boxes = self._detect_base(frame)

            if detected:
                self._handle_accident(
                    frame, annotated, boxes, confidence,
                    camera_id, fps, width, height
                )

            self.prev_frame = frame.copy()

            # Overlay
            self._draw_overlay(annotated, detected, confidence, frame_count)

            cv2.imshow(f"AccidentWatch | {camera_id}", annotated)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()

    def _detect_trained(self, frame):
        """Use after training — detects 'accident' class."""
        results    = self.model(frame, conf=self.conf_thresh, verbose=False)
        annotated  = results[0].plot()
        detected   = False
        confidence = 0.0
        boxes      = []

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                label  = self.model.names[cls_id]
                if label in ACCIDENT_CLASSES and conf >= self.conf_thresh:
                    detected   = True
                    confidence = max(confidence, conf)
                    boxes.append({
                        "label": label, "confidence": conf,
                        "xyxy":  box.xyxy[0].tolist()
                    })

        return annotated, detected, confidence, boxes

    def _detect_base(self, frame):
        """
        Base model: detects vehicles and triggers alert
        when 2+ vehicles stay close for 6+ consecutive frames.
        Works immediately without training.
        """
        results   = self.model(frame, conf=self.conf_thresh, verbose=False)
        annotated = results[0].plot()
        boxes     = []

        for r in results:
            for box in r.boxes:
                cls_id = int(box.cls[0])
                conf   = float(box.conf[0])
                label  = self.model.names[cls_id]
                if label.lower() in VEHICLE_CLASSES:
                    boxes.append({
                        "label": label, "confidence": conf,
                        "xyxy":  box.xyxy[0].tolist()
                    })

        close = self._check_proximity(boxes, frame.shape[1], frame.shape[0])

        if len(boxes) >= self.MIN_VEHICLES and close:
            self.vframe_count += 1
        else:
            self.vframe_count = max(0, self.vframe_count - 1)

        detected   = self.vframe_count >= self.VFRAME_THRESH
        confidence = min(0.55 + self.vframe_count * 0.05, 0.95) if detected else 0.0

        return annotated, detected, confidence, boxes

    def _check_proximity(self, boxes, w, h):
        if len(boxes) < 2:
            return False
        for i in range(len(boxes)):
            for j in range(i+1, len(boxes)):
                b1, b2 = boxes[i]["xyxy"], boxes[j]["xyxy"]
                c1x = (b1[0]+b1[2])/2
                c1y = (b1[1]+b1[3])/2
                c2x = (b2[0]+b2[2])/2
                c2y = (b2[1]+b2[3])/2
                dist = ((c1x-c2x)**2 + (c1y-c2y)**2)**0.5
                if dist < w * 0.30:
                    return True
        return False

    def _handle_accident(self, frame, annotated, boxes, confidence,
                         camera_id, fps, width, height):
        now = time.time()
        if camera_id in self.cooldown:
            if now - self.cooldown[camera_id] < self.cooldown_secs:
                return
        self.cooldown[camera_id] = now
        self.vframe_count = 0

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n{'!'*55}")
        print(f"  ACCIDENT DETECTED")
        print(f"  Camera     : {camera_id}")
        print(f"  Time       : {timestamp}")
        print(f"  Confidence : {int(confidence*100)}%")

        # Severity
        severity, score, detail = self.sev.analyze(
            frame, boxes, confidence, self.prev_frame
        )
        print(f"  Severity   : {severity} ({int(score*100)}%)")

        # Location
        print(f"  Fetching location...")
        loc = get_location()
        print(f"  Address    : {loc['full_address']}")
        print(f"  Source     : {loc.get('source','IP')}")

        # Record clip
        clip_path = self.recorder.save_clip(
            list(self.frame_buffer), camera_id, timestamp, fps, width, height
        )

        # Snapshot
        snapshot_path = self.recorder.save_snapshot(annotated, camera_id, timestamp)

        # Database
        alert_data = {
            "camera_id":       camera_id,
            "timestamp":       timestamp,
            "severity":        severity,
            "severity_score":  score,
            "severity_detail": detail,
            "confidence":      confidence,
            "clip_path":       clip_path,
            "snapshot_path":   snapshot_path,
            "location_info":   loc,
        }
        accident_id = save_accident(alert_data, loc, detail)
        print(f"  DB Record  : Accident #{accident_id}")
        print(f"{'!'*55}\n")

        # SMS + Call in background
        threading.Thread(
            target=self.alert.send,
            args=(alert_data, accident_id),
            daemon=True
        ).start()

    def _draw_overlay(self, frame, detected, confidence, frame_count):
        if detected:
            color  = (0, 0, 255)
            status = f"ACCIDENT DETECTED {int(confidence*100)}%"
        else:
            vfc    = self.vframe_count if not TRAINED_MODEL else 0
            color  = (0, 255, 0)
            status = f"MONITORING | {vfc}/{self.VFRAME_THRESH} frames"

        cv2.rectangle(frame, (0, 0), (420, 36), (0, 0, 0), -1)
        cv2.putText(frame, status, (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
        cv2.putText(frame, f"Frame:{frame_count} | Q=quit",
                    (8, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160,160,160), 1)
