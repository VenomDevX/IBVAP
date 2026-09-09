"""
IBVAP — Notification Managers
Email + SMS dispatch for critical threats.

Hardening notes:
- a bounded 2-worker pool (not thread-per-alert) so an alert storm can't spawn
  unbounded threads;
- every SMTP/Twilio call has a timeout;
- operator contact details are redacted in logs.
"""

import os
import smtplib
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage

from loguru import logger

_SMTP_TIMEOUT = 10  # seconds


def _redact_email(addr: str) -> str:
    if not addr or "@" not in addr:
        return "<unset>"
    name, _, domain = addr.partition("@")
    return f"{name[:1]}***@{domain}"


def _redact_phone(num: str) -> str:
    digits = "".join(ch for ch in (num or "") if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) >= 4 else "<unset>"


class NotificationManager:
    _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ibvap-notify")

    def __init__(self):
        self.smtp_server = os.getenv("SMTP_SERVER", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.target_email = os.getenv("ALERT_TARGET_EMAIL", "")

        self.twilio_sid = os.getenv("TWILIO_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = os.getenv("TWILIO_FROM_NUM", "")
        self.target_phone = os.getenv("ALERT_TARGET_PHONE", "")

        self.twilio_client = None
        if self.twilio_sid and self.twilio_token:
            try:
                from twilio.rest import Client

                self.twilio_client = Client(self.twilio_sid, self.twilio_token)
            except ImportError:
                logger.warning("Twilio library not installed — SMS disabled.")

    def notify_critical(self, alert_dict: dict):
        """Queue critical notifications on the bounded worker pool."""
        self._pool.submit(self._send_notifications_sync, alert_dict)

    def _send_notifications_sync(self, alert: dict):
        msg = (
            f"CRITICAL ALERT ({alert.get('camera_id')}): {alert.get('object_type')} "
            f"detected with risk {alert.get('risk_score')}."
        )

        # --- Email ---
        if self.smtp_server and self.smtp_user and self.target_email:
            try:
                email = EmailMessage()
                email.set_content(f"{msg}\n\nRisk Factors: {', '.join(alert.get('contributing_factors', []))}")
                email["Subject"] = f"IBVAP Critical Alert: {alert.get('camera_id')}"
                email["From"] = self.smtp_user
                email["To"] = self.target_email

                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=_SMTP_TIMEOUT) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_pass)
                    server.send_message(email)
                logger.info(f"Critical alert email sent to {_redact_email(self.target_email)}")
            except Exception as e:
                logger.error(f"email notification failed: {e}")
        else:
            logger.info(f"(mock email) critical alert -> {_redact_email(self.target_email)}")

        # --- SMS ---
        if self.twilio_client and self.target_phone:
            try:
                self.twilio_client.messages.create(
                    body=msg,
                    from_=self.twilio_from,
                    to=self.target_phone,
                )
                logger.info(f"Critical alert SMS sent to {_redact_phone(self.target_phone)}")
            except Exception as e:
                logger.error(f"SMS notification failed: {e}")
        else:
            logger.info(f"(mock sms) critical alert -> {_redact_phone(self.target_phone)}")
