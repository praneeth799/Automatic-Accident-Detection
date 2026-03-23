"""
Real-Time Accident Detector
Uses laptop webcam → YOLOv8 → severity analysis →
location detection → database → Twilio call + SMS
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


class AccidentDetector:
    def __init__(self, config):
        self.config     = config
        self.conf_thresh = config.get("confidence_threshold", 0.55)

        print("[SYSTEM] Loading YOLOv8 model...")
        self.model = YOLO(config["model_path"])
        print("[SYSTEM] Model loaded ✅")

        self.sev      = SeverityAnalyzer()
        self.recorder = ClipRecorder(config["recordings_dir"])
        self.alert    = EmergencyAlert(config)

        fps = config.get("fps", 25)
        self.frame_buffer  = deque(maxlen=fps * 10)  # 10s pre-buffer
        self.prev_frame    = None
        self.cooldown      = {}
        self.cooldown_secs = 60  # 60s between alerts per camera

    # ------------------------------------------------------------------ #
    #  OPEN LAPTOP WEBCAM                                                  #
    # ------------------------------------------------------------------ #
    def _open_webcam(self, source, camera_id):
        """Open laptop webcam with Windows-compatible backends."""
        if isinstance(source, int):
            backends = [
                (cv2.CAP_MSMF,  "MSMF"),
                (cv2.CAP_DSHOW, "DirectShow"),
                (cv2.CAP_ANY,   "Default"),
            ]
            for backend, name in backends:
                print(f"[{camera_id}] Trying: {name}...")
                cap = cv2.VideoCapture(source, backend)
                if cap.isOpened():
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    cap.set(cv2.CAP_PROP_FPS, 30)
                    for _ in range(5):
                        cap.read()
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.size > 0:
                        print(f"[{camera_id}] ✅ Webcam opened: {name}")
                        return cap
                cap.release()
            return None
        else:
            cap = cv2.VideoCapture(source)
            return cap if cap.isOpened() else None

    # ------------------------------------------------------------------ #
    #  MAIN REAL-TIME LOOP                                                 #
    # ------------------------------------------------------------------ #
    def run(self, source=0, camera_id="CAM_01"):
        """
        Start real-time detection on laptop webcam.
        source: 0 = built-in webcam, 1 = external webcam
        """
        cap = self._open_webcam(source, camera_id)
        if cap is None:
            print(f"[ERROR] Cannot open webcam. Make sure:")
            print(f"  1. No other app is using the camera (Teams, Zoom)")
            print(f"  2. Camera drivers are installed")
            print(f"  3. Try --source 1 if built-in cam is index 0")
            return

        fps    = cap.get(cv2.CAP_PROP_FPS) or 30
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))  or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480

        print(f"\n{'═'*55}")
        print(f"  AccidentWatch — LIVE DETECTION")
        print(f"  Camera  : {camera_id} (Laptop Webcam)")
        print(f"  Feed    : {width}x{height} @ {fps:.0f} FPS")
        print(f"  Model   : {self.config['model_path']}")
        print(f"  Alert → : {self.config['alert_phone']}")
        print(f"  Press Q to stop")
        print(f"{'═'*55}\n")

        frame_count = 0

        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("[WARN] Frame read failed. Retrying...")
                time.sleep(0.1)
                continue

            # Resize if needed
            if frame.shape[1] != width or frame.shape[0] != height:
                frame = cv2.resize(frame, (width, height))

            # Buffer frame for pre-accident recording
            self.frame_buffer.append(frame.copy())
            frame_count += 1

            # Run YOLOv8 detection on every frame
            annotated, detected, confidence, boxes = self._detect(frame)

            # Only trigger if accident actually detected by camera
            if detected:
                self._handle_accident(
                    frame, annotated, boxes, confidence,
                    camera_id, fps, width, height
                )

            # Update previous frame for severity diff analysis
            self.prev_frame = frame.copy()

            # Overlay status on frame
            self._draw_status(annotated, detected, confidence, frame_count)

            # Show live window
            cv2.imshow(f"AccidentWatch | {camera_id} | LIVE", annotated)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                print(f"\n[SYSTEM] Stopped by user.")
                break

        cap.release()
        cv2.destroyAllWindows()

    # ------------------------------------------------------------------ #
    #  YOLO DETECTION                                                      #
    # ------------------------------------------------------------------ #
    def _detect(self, frame):
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

                # Only trigger on accident class
                if label in ("accident", "crash", "collision") and conf >= self.conf_thresh:
                    detected   = True
                    confidence = max(confidence, conf)
                    boxes.append({
                        "label":      label,
                        "confidence": conf,
                        "xyxy":       box.xyxy[0].tolist()
                    })

        return annotated, detected, confidence, boxes

    # ------------------------------------------------------------------ #
    #  ACCIDENT HANDLER                                                    #
    # ------------------------------------------------------------------ #
    def _handle_accident(self, frame, annotated, boxes, confidence,
                         camera_id, fps, width, height):
        """
        Called ONLY when camera detects an accident.
        Runs full pipeline: severity → location → record → DB → alert.
        """
        now = time.time()

        # Cooldown — prevent duplicate alerts
        if camera_id in self.cooldown:
            if now - self.cooldown[camera_id] < self.cooldown_secs:
                return
        self.cooldown[camera_id] = now

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        print(f"\n{'!'*55}")
        print(f"  🚨 ACCIDENT DETECTED BY LAPTOP CAMERA")
        print(f"  Camera     : {camera_id}")
        print(f"  Time       : {timestamp}")
        print(f"  Confidence : {int(confidence*100)}%")

        # Step 1: Severity analysis
        severity, score, detail = self.sev.analyze(
            frame, boxes, confidence, self.prev_frame
        )
        print(f"  Severity   : {severity}")
        print(f"  Score      : {int(score*100)}%")
        print(f"  Vehicles   : {detail.get('vehicles_involved', 0)}")

        # Step 2: Get real laptop location
        print(f"\n  Fetching laptop location...")
        loc = get_location()
        print(f"  Address    : {loc['full_address']}")
        print(f"  Area       : {loc.get('area', '')}")
        print(f"  Road       : {loc.get('road', '')}")
        if loc.get("landmarks"):
            print(f"  Landmarks  : {', '.join(loc['landmarks'])}")
        print(f"  Maps       : {loc['maps_link']}")

        # Step 3: Record evidence clip
        clip_path = self.recorder.save_clip(
            list(self.frame_buffer), camera_id,
            timestamp, fps, width, height
        )

        # Step 4: Save snapshot
        snapshot_path = self.recorder.save_snapshot(annotated, camera_id, timestamp)

        # Step 5: Save to database
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
        print(f"  DB Record  : Accident #{accident_id} saved")
        print(f"{'!'*55}\n")

        # Step 6: Fire Twilio call + SMS in background thread
        # This runs in background so camera keeps detecting
        threading.Thread(
            target=self.alert.send,
            args=(alert_data, accident_id),
            daemon=True
        ).start()

    # ------------------------------------------------------------------ #
    #  STATUS OVERLAY ON LIVE FEED                                         #
    # ------------------------------------------------------------------ #
    def _draw_status(self, frame, detected, confidence, frame_count):
        """Draw status text on live camera feed."""
        color  = (0, 0, 255) if detected else (0, 255, 0)
        status = f"ACCIDENT {int(confidence*100)}%" if detected else "MONITORING"
        cv2.putText(
            frame, status,
            (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
            0.8, color, 2
        )
        cv2.putText(
            frame, f"Frame: {frame_count}",
            (10, 55), cv2.FONT_HERSHEY_SIMPLEX,
            0.5, (200, 200, 200), 1
        )
