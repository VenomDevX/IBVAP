"""
IBVAP — Notification Managers
Handles sending Email and SMS alerts for critical threats.
"""

import os
import smtplib
from email.message import EmailMessage
from loguru import logger
import threading

class NotificationManager:
    def __init__(self):
        # Email config
        self.smtp_server = os.getenv("SMTP_SERVER", "")
        self.smtp_port = int(os.getenv("SMTP_PORT", 587))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_pass = os.getenv("SMTP_PASS", "")
        self.target_email = os.getenv("ALERT_TARGET_EMAIL", "")

        # Twilio config
        self.twilio_sid = os.getenv("TWILIO_SID", "")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
        self.twilio_from = os.getenv("TWILIO_FROM_NUM", "")
        self.target_phone = os.getenv("ALERT_TARGET_PHONE", "")

        # Only import twilio if configured
        self.twilio_client = None
        if self.twilio_sid and self.twilio_token:
            try:
                from twilio.rest import Client
                self.twilio_client = Client(self.twilio_sid, self.twilio_token)
            except ImportError:
                logger.warning("Twilio library not installed. SMS disabled.")

    def notify_critical(self, alert_dict: dict):
        """Send critical notifications in a background thread."""
        thread = threading.Thread(target=self._send_notifications_sync, args=(alert_dict,))
        thread.daemon = True
        thread.start()

    def _send_notifications_sync(self, alert: dict):
        msg = f"CRITICAL ALERT ({alert.get('camera_id')}): {alert.get('object_type')} detected with risk {alert.get('risk_score')}."
        
        # Email
        if self.smtp_server and self.smtp_user and self.target_email:
            try:
                email = EmailMessage()
                email.set_content(f"{msg}\n\nRisk Factors: {', '.join(alert.get('contributing_factors', []))}")
                email['Subject'] = f"IBVAP Critical Alert: {alert.get('camera_id')}"
                email['From'] = self.smtp_user
                email['To'] = self.target_email

                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.starttls()
                    server.login(self.smtp_user, self.smtp_pass)
                    server.send_message(email)
                logger.info(f"📧 Critical alert email sent to {self.target_email}")
            except Exception as e:
                logger.error(f"Failed to send email notification: {e}")
        else:
            logger.info(f"📧 (MOCKED EMAIL) To {self.target_email or 'Admin'}: {msg}")

        # SMS
        if self.twilio_client and self.target_phone:
            try:
                self.twilio_client.messages.create(
                    body=msg,
                    from_=self.twilio_from,
                    to=self.target_phone
                )
                logger.info(f"📱 Critical alert SMS sent to {self.target_phone}")
            except Exception as e:
                logger.error(f"Failed to send SMS notification: {e}")
        else:
            logger.info(f"📱 (MOCKED SMS) To {self.target_phone or 'Admin'}: {msg}")
