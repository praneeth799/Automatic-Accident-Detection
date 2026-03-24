"""
Emergency Alert System
- SMS via Fast2SMS (Indian numbers - FREE, works instantly)
- Voice Call via Twilio
Both fire when camera detects accident in VIDEO/WEBCAM.
"""

import time
import logging
import requests
from twilio.rest import Client
from utils.severity import SeverityAnalyzer
from utils.location import format_location_for_sms, format_location_for_call
from database.db_manager import log_alert

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)


class EmergencyAlert:
    def __init__(self, config):
        self.twilio       = Client(
            config["twilio"]["account_sid"],
            config["twilio"]["auth_token"]
        )
        self.alert_phone  = config["alert_phone"]
        self.from_number  = config["twilio"]["from_number"]
        self.fast2sms_key = config.get("fast2sms_api_key", "")
        self.sev          = SeverityAnalyzer()

    def send(self, data, accident_id):
        """Send SMS + Voice Call when camera detects accident."""
        loc       = data["location_info"]
        timestamp = data["timestamp"]
        ts        = timestamp
        time_str  = (f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} "
                     f"{ts[8:10]}:{ts[10:12]}:{ts[12:14]}")

        logger.info("=" * 55)
        logger.info("  ACCIDENT CONFIRMED — SENDING ALERTS")
        logger.info(f"  Location  : {loc['full_address']}")
        logger.info(f"  Source    : {loc.get('source','IP')}")
        logger.info(f"  Severity  : {data['severity']}")
        logger.info(f"  Time      : {time_str}")
        logger.info(f"  Maps      : {loc['maps_link']}")
        logger.info("=" * 55)

        # Step 1 — SMS
        sms_status = self._send_sms(data, loc, data.get("severity_detail", {}), time_str)
        if accident_id:
            log_alert(accident_id, "SMS", self.alert_phone, sms_status)

        time.sleep(2)

        # Step 2 — Voice Call
        call_status = self._make_call(data, loc, time_str)
        if accident_id:
            log_alert(accident_id, "VOICE_CALL", self.alert_phone, call_status)

    # ------------------------------------------------------------------ #
    #  SMS — Fast2SMS for Indian numbers                                   #
    # ------------------------------------------------------------------ #
    def _send_sms(self, data, loc, detail, time_str):
        """
        Sends SMS via Fast2SMS to Indian mobile numbers.
        Falls back to Twilio if Fast2SMS key not set.
        """
        severity = data["severity"]
        conf     = int(data["confidence"] * 100)
        score    = int(data.get("severity_score", 0) * 100)
        vehicles = detail.get("vehicles_involved", "?")

        actions = {
            "LOW":      "Monitor when possible.",
            "MEDIUM":   "Send police and ambulance immediately.",
            "HIGH":     "Dispatch ambulance and fire services NOW.",
            "CRITICAL": "CALL 112 IMMEDIATELY. Life threatening."
        }
        action = actions.get(severity, "Respond immediately.")

        # Build location block
        loc_lines = [f"Address: {loc['full_address']}"]
        if loc.get("road"):
            loc_lines.append(f"Road: {loc['road']}")
        if loc.get("area"):
            loc_lines.append(f"Area: {loc['area']}")
        if loc.get("postal"):
            loc_lines.append(f"PIN: {loc['postal']}")
        if loc.get("landmarks"):
            loc_lines.append(f"Nearby: {', '.join(loc['landmarks'])}")
        loc_lines.append(f"Maps: {loc['maps_link']}")
        loc_block = "\n".join(loc_lines)

        message = (
            f"ACCIDENT ALERT\n"
            f"--- LOCATION ---\n"
            f"{loc_block}\n"
            f"--- DETAILS ---\n"
            f"Time: {time_str}\n"
            f"Camera: {data['camera_id']}\n"
            f"Severity: {severity}\n"
            f"Score: {score}%\n"
            f"AI Confidence: {conf}%\n"
            f"Vehicles: {vehicles}\n"
            f"--- ACTION ---\n"
            f"{action}\n"
            f"Evidence recorded. RESPOND NOW!"
        )

        # Try Fast2SMS first
        if self.fast2sms_key and self.fast2sms_key != "PASTE_YOUR_FAST2SMS_KEY_HERE":
            result = self._fast2sms(message)
            if result == "sent":
                return "sent"

        # Fallback to Twilio SMS
        return self._twilio_sms(message)

    def _fast2sms(self, message):
        """Send via Fast2SMS API."""
        try:
            # Extract 10-digit Indian number
            phone = self.alert_phone.strip()
            phone = phone.replace("+91", "").replace("+", "").strip()
            if phone.startswith("91") and len(phone) == 12:
                phone = phone[2:]
            phone = phone[-10:]  # always take last 10 digits

            logger.info(f"[SMS] Sending via Fast2SMS to: {phone}")

            r = requests.get(
                "https://www.fast2sms.com/dev/bulkV2",
                params={
                    "authorization": self.fast2sms_key,
                    "message":       message,
                    "language":      "english",
                    "route":         "q",
                    "numbers":       phone,
                },
                headers={"cache-control": "no-cache"},
                timeout=15
            )

            logger.info(f"[SMS] Fast2SMS response: {r.status_code} — {r.text}")
            resp = r.json()

            if resp.get("return") is True:
                logger.info(f"[SMS] Fast2SMS sent! ID: {resp.get('request_id','')}")
                return "sent"
            else:
                logger.error(f"[SMS] Fast2SMS error: {resp.get('message', resp)}")
                return "failed"

        except Exception as e:
            logger.error(f"[SMS] Fast2SMS exception: {e}")
            return "failed"

    def _twilio_sms(self, message):
        """Send via Twilio SMS (fallback)."""
        try:
            msg = self.twilio.messages.create(
                body=message,
                to=self.alert_phone,
                from_=self.from_number,
            )
            logger.info(f"[SMS] Twilio SMS sent! SID: {msg.sid}")
            return msg.status
        except Exception as e:
            logger.error(f"[SMS] Twilio SMS failed: {e}")
            return "failed"

    # ------------------------------------------------------------------ #
    #  VOICE CALL — Twilio                                                 #
    # ------------------------------------------------------------------ #
    def _make_call(self, data, loc, time_str):
        try:
            severity               = data["severity"]
            conf                   = int(data["confidence"] * 100)
            location_str, landmark = format_location_for_call(loc)

            sev_msgs = {
                "LOW":      "Severity LOW. Minor accident. Please check location.",
                "MEDIUM":   "Severity MEDIUM. Moderate accident. Send help immediately.",
                "HIGH":     "Severity HIGH. Serious accident. Multiple vehicles. Call emergency services now.",
                "CRITICAL": "Severity CRITICAL. Life threatening accident. Call one one two immediately.",
            }
            sev_msg = sev_msgs.get(severity, "Accident detected.")

            src = loc.get("source", "")
            src_msg = ""
            if "GPS" in src:
                src_msg = "Location from laptop GPS. "
            elif "WiFi" in src:
                src_msg = "Location from WiFi signal. "

            msg = (
                f"EMERGENCY ALERT. EMERGENCY ALERT. "
                f"Automatic accident detection system activated. "
                f"Accident detected by camera {data['camera_id']}. "
                f"Location: {location_str}. "
                f"{landmark}"
                f"{src_msg}"
                f"Time of accident: {time_str}. "
                f"Confidence: {conf} percent. "
                f"{sev_msg} "
                f"A full SMS with location and Google Maps link "
                f"has been sent to your phone. "
                f"Evidence video recorded for investigation. "
                f"This message will repeat. "
                f"EMERGENCY ALERT. "
                f"Accident at {location_str}. "
                f"{sev_msg}"
            )

            safe  = msg.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            twiml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<Response>'
                f'<Say voice="Polly.Joanna" language="en-US">{safe}</Say>'
                '<Pause length="1"/>'
                f'<Say voice="Polly.Joanna" language="en-US">{safe}</Say>'
                '</Response>'
            )

            call = self.twilio.calls.create(
                twiml=twiml,
                to=self.alert_phone,
                from_=self.from_number,
            )
            logger.info(f"[CALL] Placed! SID: {call.sid}")
            return call.status

        except Exception as e:
            logger.error(f"[CALL] Failed: {e}")
            return "failed"
