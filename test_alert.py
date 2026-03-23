"""
Test Alert — Call + SMS
IMPORTANT: This sends a REAL call and SMS to your phone.
Run only after filling config.json with Twilio credentials.

python test_alert.py
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.db_manager import init_db, save_accident
from utils.location import get_location
from alerts.caller import EmergencyAlert

print("="*55)
print("  ACCIDENTWATCH — ALERT TEST")
print("="*55)

init_db()

# Step 1: Get real location
print("\n[1] Detecting laptop location...")
loc = get_location()
print(f"    Address   : {loc['full_address']}")
print(f"    Area      : {loc.get('area','N/A')}")
print(f"    Road      : {loc.get('road','N/A')}")
print(f"    Maps      : {loc['maps_link']}")
if loc.get("landmarks"):
    print(f"    Landmarks : {', '.join(loc['landmarks'])}")

# Step 2: Save test record to DB
print("\n[2] Saving to database...")
detail = {
    "model_confidence":  0.91,
    "vehicles_involved": 2,
    "area_coverage":     0.34,
    "motion_blur_score": 0.62,
    "overlap_score":     0.45,
    "frame_diff_score":  0.55,
    "final_score":       0.78,
    "label":             "HIGH"
}
data = {
    "camera_id":       "CAM_01",
    "timestamp":       "20260319_180000",
    "severity":        "HIGH",
    "severity_score":  0.78,
    "severity_detail": detail,
    "confidence":      0.91,
    "clip_path":       "recordings/test.mp4",
    "snapshot_path":   "recordings/test.jpg",
    "location_info":   loc,
}
acc_id = save_accident(data, loc, detail)
print(f"    Accident ID : #{acc_id}")

# Step 3: Send real alert
print("\n[3] Sending call + SMS to your phone...")
config = json.load(open("config.json"))
alert  = EmergencyAlert(config)
alert.send(data, acc_id)

print("\n" + "="*55)
print("  ✅ DONE! Check your phone:")
print(f"  📞 Call → {config['alert_phone']}")
print(f"  💬 SMS  → {config['alert_phone']}")
print("="*55)
