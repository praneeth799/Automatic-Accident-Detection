"""
Emergency Alert — Twilio Call + SMS
ONLY triggered when laptop camera detects an accident.
Never called during testing unless accident is real.
"""

import time
import logging
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
        self.client      = Client(
            config["twilio"]["account_sid"],
            config["twilio"]["auth_token"]
        )
        self.alert_phone = config["alert_phone"]
        self.from_number = config["twilio"]["from_number"]
        self.sev         = SeverityAnalyzer()

    def send(self, data, accident_id):
        """
        Send voice call + SMS.
        Only called when camera detects a real accident.
        """
        loc        = data["location_info"]
        severity   = data["severity"]
        detail     = data["severity_detail"]
        confidence = data["confidence"]
        timestamp  = data["timestamp"]

        logger.info(f"[ALERT] ═══════════════════════════════")
        logger.info(f"[ALERT] ACCIDENT CONFIRMED BY CAMERA")
        logger.info(f"[ALERT] Location  : {loc['full_address']}")
        logger.info(f"[ALERT] Area      : {loc.get('area','')}")
        logger.info(f"[ALERT] Road      : {loc.get('road','')}")
        logger.info(f"[ALERT] Landmarks : {loc.get('landmarks',[])}")
        logger.info(f"[ALERT] Severity  : {severity}")
        logger.info(f"[ALERT] Confidence: {int(confidence*100)}%")
        logger.info(f"[ALERT] Maps      : {loc['maps_link']}")
        logger.info(f"[ALERT] ═══════════════════════════════")

        # 1. Voice call
        call_status = self._call(data, loc, detail)
        log_alert(accident_id, "VOICE_CALL", self.alert_phone, call_status)

        time.sleep(3)

        # 2. SMS
        sms_status = self._sms(data, loc, detail, timestamp)
        log_alert(accident_id, "SMS", self.alert_phone, sms_status)

    # ------------------------------------------------------------------ #
    #  VOICE CALL                                                          #
    # ------------------------------------------------------------------ #
    def _call(self, data, loc, detail):
        try:
            location_str, landmark_str = format_location_for_call(loc)
            voice_msg = self.sev.voice_message(
                data["severity"], location_str, landmark_str
            )

            full = (
                f"EMERGENCY ALERT. EMERGENCY ALERT. "
                f"Laptop camera has detected an accident. "
                f"Camera {data['camera_id']}. "
                f"Location: {location_str}. "
                f"{landmark_str}"
                f"Detection confidence: {int(data['confidence']*100)} percent. "
                f"{voice_msg} "
                f"Evidence video has been recorded for investigation. "
                f"This message will now repeat. "
                f"EMERGENCY ALERT. "
                f"Accident at {location_str}. "
                f"Severity {data['severity']}. "
                f"Respond immediately."
            )

            safe = (full
                    .replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;"))

            twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna" language="en-US">{safe}</Say>
  <Pause length="1"/>
  <Say voice="Polly.Joanna" language="en-US">{safe}</Say>
</Response>"""

            call = self.client.calls.create(
                twiml=twiml,
                to=self.alert_phone,
                from_=self.from_number,
            )
            logger.info(f"[CALL] ✅ Placed! SID: {call.sid}")
            return call.status

        except Exception as e:
            logger.error(f"[CALL] ❌ Failed: {e}")
            return "failed"

    # ------------------------------------------------------------------ #
    #  SMS                                                                 #
    # ------------------------------------------------------------------ #
    def _sms(self, data, loc, detail, timestamp):
        try:
            ts       = timestamp
            time_str = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]} {ts[8:10]}:{ts[10:12]}:{ts[12:14]}"

            emojis = {
                "LOW":      "🟡",
                "MEDIUM":   "🟠",
                "HIGH":     "🔴",
                "CRITICAL": "🚨"
            }
            emoji = emojis.get(data["severity"], "⚠️")
            desc  = self.sev.sms_detail(data["severity"], detail)
            loc_block = format_location_for_sms(loc)

            body = (
                f"{emoji} ACCIDENT ALERT {emoji}\n"
                f"{'='*32}\n"
                f"{loc_block}\n"
                f"{'='*32}\n"
                f"Camera   : {data['camera_id']}\n"
                f"Time     : {time_str}\n"
                f"{'='*32}\n"
                f"Severity : {data['severity']}\n"
                f"Score    : {int(data['severity_score']*100)}%\n"
                f"AI Conf  : {int(data['confidence']*100)}%\n"
                f"Vehicles : {detail.get('vehicles_involved','?')}\n"
                f"{'='*32}\n"
                f"{desc}\n"
                f"{'='*32}\n"
                f"Evidence saved in database\n"
                f"RESPOND IMMEDIATELY!"
            )

            msg = self.client.messages.create(
                body=body,
                to=self.alert_phone,
                from_=self.from_number,
            )
            logger.info(f"[SMS]  ✅ Sent! SID: {msg.sid}")
            return msg.status

        except Exception as e:
            logger.error(f"[SMS]  ❌ Failed: {e}")
            return "failed"
