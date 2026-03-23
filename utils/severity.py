"""
Real-Time Severity Analyzer — 6 factors
"""

import cv2
import numpy as np


class SeverityAnalyzer:

    def analyze(self, frame, boxes, confidence, prev_frame=None):
        h, w  = frame.shape[:2]
        area  = h * w
        d     = {}

        d["model_confidence"]  = round(float(confidence), 3)
        d["vehicles_involved"] = len(boxes)
        obj_score = min(len(boxes) / 4.0, 1.0)

        total = sum(
            (b["xyxy"][2]-b["xyxy"][0]) * (b["xyxy"][3]-b["xyxy"][1])
            for b in boxes
        )
        d["area_coverage"]     = round(min(total / max(area, 1), 1.0), 3)
        d["motion_blur_score"] = self._blur(frame, boxes, w, h)
        d["overlap_score"]     = self._overlap(boxes)
        d["frame_diff_score"]  = self._diff(frame, prev_frame)

        score = round(min(
            d["model_confidence"]  * 0.25 +
            obj_score              * 0.20 +
            d["area_coverage"]     * 0.20 +
            d["motion_blur_score"] * 0.15 +
            d["overlap_score"]     * 0.10 +
            d["frame_diff_score"]  * 0.10,
            1.0
        ), 3)
        d["final_score"] = score

        if score < 0.30:
            label = "LOW"
        elif score < 0.55:
            label = "MEDIUM"
        elif score < 0.75:
            label = "HIGH"
        else:
            label = "CRITICAL"

        d["label"] = label
        return label, score, d

    def _blur(self, frame, boxes, w, h):
        if not boxes:
            return 0.0
        x1,y1,x2,y2 = [int(v) for v in boxes[0]["xyxy"]]
        roi = frame[max(0,y1):min(h,y2), max(0,x1):min(w,x2)]
        if roi.size == 0:
            return 0.0
        var = cv2.Laplacian(
            cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), cv2.CV_64F
        ).var()
        return round(max(0.0, 1.0 - var / 500.0), 3)

    def _overlap(self, boxes):
        if len(boxes) < 2:
            return 0.0
        best = 0.0
        for i in range(len(boxes)):
            for j in range(i+1, len(boxes)):
                b1, b2 = boxes[i]["xyxy"], boxes[j]["xyxy"]
                ix = max(0, min(b1[2],b2[2]) - max(b1[0],b2[0]))
                iy = max(0, min(b1[3],b2[3]) - max(b1[1],b2[1]))
                inter = ix * iy
                a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
                a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
                iou = inter / max(a1+a2-inter, 1e-6)
                best = max(best, iou)
        return round(min(best, 1.0), 3)

    def _diff(self, frame, prev):
        if prev is None:
            return 0.0
        try:
            if frame.shape != prev.shape:
                prev = cv2.resize(prev, (frame.shape[1], frame.shape[0]))
            diff = cv2.absdiff(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(prev,  cv2.COLOR_BGR2GRAY)
            )
            return round(min(np.mean(diff) / 255.0 * 5.0, 1.0), 3)
        except Exception:
            return 0.0

    def voice_message(self, severity, location_str, landmark_str):
        msgs = {
            "LOW": (
                f"Alert. Minor accident detected at {location_str}. "
                f"{landmark_str}"
                f"Severity is LOW. Please check the location."
            ),
            "MEDIUM": (
                f"Warning. Moderate accident detected at {location_str}. "
                f"{landmark_str}"
                f"Severity is MEDIUM. Vehicles involved. "
                f"Injuries possible. Send help immediately."
            ),
            "HIGH": (
                f"Emergency. Serious accident detected at {location_str}. "
                f"{landmark_str}"
                f"Severity is HIGH. Multiple vehicles involved. "
                f"Immediate medical attention required. "
                f"Call emergency services now."
            ),
            "CRITICAL": (
                f"Critical emergency. Life threatening accident at {location_str}. "
                f"{landmark_str}"
                f"Severity is CRITICAL. Major collision. "
                f"Possible fatalities. Call one one two immediately."
            ),
        }
        return msgs.get(severity, f"Accident at {location_str}. Respond now.")

    def sms_detail(self, severity, detail):
        v = detail.get("vehicles_involved", 1)
        s = int(detail.get("final_score", 0) * 100)
        items = {
            "LOW":      f"Minor incident. {v} vehicle(s).\nPossible scrape or minor contact.\nAction: Monitor and check.",
            "MEDIUM":   f"Moderate accident. {v} vehicle(s).\nCollision with possible injuries.\nAction: Send police + ambulance.",
            "HIGH":     f"Serious accident! {v} vehicle(s).\nSignificant collision. Injuries likely.\nAction: Ambulance + fire services NOW.",
            "CRITICAL": f"CRITICAL accident!! {v} vehicle(s).\nMajor collision. Fatalities possible.\nAction: CALL 112 IMMEDIATELY.",
        }
        return items.get(severity, "Accident detected. Respond immediately.")
