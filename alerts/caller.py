"""
Emergency Alert System
- Voice Call via Twilio (works on Indian numbers)
- SMS via Fast2SMS (FREE, works on ALL Indian numbers)
  Fast2SMS is an Indian SMS gateway - no DLT issues
  Sign up free at https://fast2sms.com
  Get API key from dashboard

SMS contains:
  - GPS/WiFi exact location
  - Street, Area, PIN code
  - Nearby landmarks
  - Severity level + score
  - Time of accident
  - Google Maps link
  - Action required
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
        # Twilio for voice calls
        self.twilio = Client(
            config["twilio"]["account_sid"],
            config["twilio"]["auth_token"]
        )
        self.alert_phone = config["alert_phone"]
        self.from_number = config["twilio"]["from_number"]

        # Fast2SMS for Indian SMS
        self.fast2sms_key = config.get("fast2sms_api_key", "")

        self.sev = SeverityAnalyzer()

    def send(self, data, accident_id):
        """Send SMS then Voice Call when accident detected."""
        loc       = data["location_info"]
        severity  = data["severity"]
        detail    = data.get("severity_detail", {})
        timestamp = data["timestamp"]

        ts       = timestamp
        time_str = (f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} "
                    f"{ts[8:10]}:{ts[10:12]}:{ts[12:14]}")

        logger.info("═" * 55)
        logger.info("  🚨 ACCIDENT CONFIRMED — SENDING ALERTS")
        logger.info(f"  Location  : {loc['full_address']}")
        logger.info(f"  Source    : {loc.get('source','IP')}")
        logger.info(f"  Area      : {loc.get('area','N/A')}")
        logger.info(f"  Road      : {loc.get('road','N/A')}")
        logger.info(f"  Severity  : {severity}")
        logger.info(f"  Time      : {time_str}")
        logger.info(f"  Maps      : {loc['maps_link']}")
        logger.info("═" * 55)

        # Step 1: Send SMS via Fast2SMS (Indian numbers)
        sms_status = self._send_sms_fast2sms(data, loc, detail, time_str)
        if accident_id:
            log_alert(accident_id, "SMS", self.alert_phone, sms_status)

        time.sleep(1)

        # Step 2: Voice Call via Twilio
        call_status = self._make_call(data, loc, detail, time_str)
        if accident_id:
            log_alert(accident_id, "VOICE_CALL", self.alert_phone, call_status)

    # ------------------------------------------------------------------ #
    #  SMS via Fast2SMS (Indian numbers — FREE)                           #
    # ------------------------------------------------------------------ #
    def _send_sms_fast2sms(self, data, loc, detail, time_str):
        """
        Send SMS using Fast2SMS — works on ALL Indian numbers.
        No DLT issues, no restrictions on trial.
        Get free API key from https://fast2sms.com
        """
        try:
            if not self.fast2sms_key:
                logger.warning("[SMS] Fast2SMS key not set. Trying Twilio SMS...")
                return self._send_sms_twilio(data, loc, detail, time_str)

            severity = data["severity"]
            conf     = int(data["confidence"] * 100)
            score    = int(data.get("severity_score", 0) * 100)
            vehicles = detail.get("vehicles_involved", "?")

            actions = {
                "LOW":      "Monitor when possible.",
                "MEDIUM":   "Send police + ambulance.",
                "HIGH":     "Dispatch ambulance NOW.",
                "CRITICAL": "CALL 112 IMMEDIATELY."
            }
            action = actions.get(severity, "Respond immediately.")

            # Build SMS
            loc_block = format_location_for_sms(loc)
            message   = (
                f"ACCIDENT ALERT\n"
                f"{'='*30}\n"
                f"LOCATION\n"
                f"{loc_block}\n"
                f"{'='*30}\n"
                f"DETAILS\n"
                f"Time     : {time_str}\n"
                f"Camera   : {data['camera_id']}\n"
                f"Severity : {severity}\n"
                f"Score    : {score}%\n"
                f"Conf     : {conf}%\n"
                f"Vehicles : {vehicles}\n"
                f"{'='*30}\n"
                f"ACTION: {action}\n"
                f"Evidence saved. RESPOND NOW!"
            )

            # Extract 10-digit number
            phone = self.alert_phone.replace("+91", "").replace("+", "")
            if phone.startswith("91") and len(phone) == 12:
                phone = phone[2:]

            r = requests.get(
                "https://www.fast2sms.com/dev/bulkV2",
                params={
                    "authorization": self.fast2sms_key,
                    "message":       message,
                    "language":      "english",
                    "route":         "q",
                    "numbers":       phone,
                },
                timeout=10
            )
            resp = r.json()
            if resp.get("return") == True:
                logger.info(f"[SMS] ✅ Fast2SMS sent! ID: {resp.get('request_id')}")
                return "sent"
            else:
                logger.error(f"[SMS] Fast2SMS failed: {resp}")
                return self._send_sms_twilio(data, loc, detail, time_str)

        except Exception as e:
            logger.error(f"[SMS] Fast2SMS error: {e}")
            return self._send_sms_twilio(data, loc, detail, time_str)

    # ------------------------------------------------------------------ #
    #  SMS via Twilio (fallback)                                          #
    # ------------------------------------------------------------------ #
    def _send_sms_twilio(self, data, loc, detail, time_str):
        """Twilio SMS fallback — may not work on Indian trial."""
        try:
            severity = data["severity"]
            conf     = int(data["confidence"] * 100)
            score    = int(data.get("severity_score", 0) * 100)
            vehicles = detail.get("vehicles_involved", "?")

            emojis  = {"LOW":"🟡","MEDIUM":"🟠","HIGH":"🔴","CRITICAL":"🚨"}
            actions = {
                "LOW":      "Monitor situation.",
                "MEDIUM":   "Send police + ambulance.",
                "HIGH":     "Dispatch ambulance + fire NOW.",
                "CRITICAL": "CALL 112 IMMEDIATELY."
            }

            loc_block = format_location_for_sms(loc)
            body = (
                f"{emojis.get(severity,'⚠️')} ACCIDENT ALERT\n"
                f"{'='*32}\n"
                f"LOCATION\n{loc_block}\n"
                f"{'='*32}\n"
                f"DETAILS\n"
                f"Time     : {time_str}\n"
                f"Camera   : {data['camera_id']}\n"
                f"Severity : {severity}\n"
                f"Score    : {score}%\n"
                f"Conf     : {conf}%\n"
                f"Vehicles : {vehicles}\n"
                f"{'='*32}\n"
                f"ACTION: {actions.get(severity,'Respond now.')}\n"
                f"RESPOND IMMEDIATELY!"
            )

            msg = self.twilio.messages.create(
                body=body,
                to=self.alert_phone,
                from_=self.from_number,
            )
            logger.info(f"[SMS] ✅ Twilio SMS sent! SID: {msg.sid}")
            return msg.status

        except Exception as e:
            logger.error(f"[SMS] ❌ Twilio SMS failed: {e}")
            return "failed"

    # ------------------------------------------------------------------ #
    #  VOICE CALL via Twilio                                              #
    # ------------------------------------------------------------------ #
    def _make_call(self, data, loc, detail, time_str):
        try:
            severity     = data["severity"]
            conf         = int(data["confidence"] * 100)
            location_str, landmark_str = format_location_for_call(loc)

            sev_msgs = {
                "LOW": (
                    "Severity level is LOW. "
                    "Minor accident. Please check when possible."
                ),
                "MEDIUM": (
                    "Severity level is MEDIUM. "
                    "Moderate accident. Vehicles involved. "
                    "Send help immediately."
                ),
                "HIGH": (
                    "Severity level is HIGH. "
                    "Serious accident. Multiple vehicles. "
                    "Immediate medical attention required. "
                    "Call emergency services now."
                ),
                "CRITICAL": (
                    "Severity level is CRITICAL. "
                    "Life threatening. Major collision. "
                    "Call one one two immediately."
                ),
            }
            sev_msg = sev_msgs.get(severity, "Accident detected. Respond now.")

            source_msg = ""
            src = loc.get("source", "")
            if "GPS" in src:
                source_msg = "Location detected from laptop GPS. "
            elif "WiFi" in src:
                source_msg = "Location detected from WiFi signal. "

            full_msg = (
                f"EMERGENCY ALERT. EMERGENCY ALERT. "
                f"Accident detection system activated. "
                f"Camera {data['camera_id']} detected an accident. "
                f"Location: {location_str}. "
                f"{landmark_str}"
                f"{source_msg}"
                f"Time: {time_str}. "
                f"Confidence: {conf} percent. "
                f"{sev_msg} "
                f"An SMS with full details and Google Maps link "
                f"has been sent to your phone. "
                f"Evidence recorded. Repeating. "
                f"EMERGENCY ALERT. "
                f"Accident at {location_str}. "
                f"{sev_msg}"
            )

            safe  = (full_msg
                     .replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))
            twiml = (
                f'<?xml version="1.0" encoding="UTF-8"?>'
                f"<Response>"
                f'<Say voice="Polly.Joanna" language="en-US">{safe}</Say>'
                f"<Pause length=\"1\"/>"
                f'<Say voice="Polly.Joanna" language="en-US">{safe}</Say>'
                f"</Response>"
            )

            call = self.twilio.calls.create(
                twiml=twiml,
                to=self.alert_phone,
                from_=self.from_number,
            )
            logger.info(f"[CALL] ✅ Placed! SID: {call.sid}")
            return call.status

        except Exception as e:
            logger.error(f"[CALL] ❌ Failed: {e}")
            return "failed"
