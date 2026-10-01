"""Push (FCM), voice call and SMS (Twilio), email (SMTP).

Every channel runs in DRY-RUN mode when its credentials are missing: it logs what it would have
sent and returns the provider reference "dryrun". That lets you build and demo the whole flow
before you have a Firebase project or a Twilio account.
"""
import logging
import smtplib
from email.message import EmailMessage

from .config import settings

log = logging.getLogger("medsure.notify")


class InvalidPushToken(Exception):
    """FCM says this device token is no longer valid; delete it."""


class Notifier:
    def __init__(self) -> None:
        self._fcm_ready: bool | None = None
        self._twilio = None

    # ---------- Push (FCM) ----------
    def _init_fcm(self) -> bool:
        if self._fcm_ready is not None:
            return self._fcm_ready
        self._fcm_ready = False
        if settings.fcm_credentials_file:
            try:
                import firebase_admin
                from firebase_admin import credentials

                if not firebase_admin._apps:
                    firebase_admin.initialize_app(credentials.Certificate(settings.fcm_credentials_file))
                self._fcm_ready = True
            except Exception as e:  # missing file, bad JSON, ...
                log.error("FCM disabled: %s", e)
        return self._fcm_ready

    def push(self, token: str, data: dict[str, str]) -> str:
        """Send a high-priority data message. The app's FirebaseMessagingService builds the notification."""
        if not self._init_fcm():
            log.warning("[DRY-RUN push] token=%s… data=%s", token[:10], data)
            return "dryrun"
        from firebase_admin import messaging

        try:
            msg = messaging.Message(
                token=token,
                data={k: str(v) for k, v in data.items()},
                android=messaging.AndroidConfig(priority="high", ttl=300),
            )
            return messaging.send(msg)
        except (messaging.UnregisteredError, messaging.SenderIdMismatchError) as e:
            raise InvalidPushToken(str(e))

    # ---------- Voice + SMS (Twilio) ----------
    def _client(self):
        if not (settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_from_number):
            return None
        if self._twilio is None:
            from twilio.rest import Client

            self._twilio = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        return self._twilio

    def call(self, to: str, voice_url: str, status_url: str) -> str:
        client = self._client()
        if client is None:
            log.warning("[DRY-RUN call] to=%s voice_url=%s", to, voice_url)
            return "dryrun"
        call = client.calls.create(
            to=to,
            from_=settings.twilio_from_number,
            url=voice_url,
            method="POST",
            status_callback=status_url,
            status_callback_method="POST",
            status_callback_event=["completed"],   # fires for answered, busy, no-answer, failed, canceled
            timeout=25,                            # ring for ~25 seconds
        )
        return call.sid

    def sms(self, to: str, text: str) -> str:
        client = self._client()
        if client is None:
            log.warning("[DRY-RUN sms] to=%s text=%s", to, text)
            return "dryrun"
        msg = client.messages.create(to=to, from_=settings.twilio_sms_from or settings.twilio_from_number, body=text)
        return msg.sid

    # ---------- Email (OTP) ----------
    def email(self, to: str, subject: str, body: str) -> None:
        if not settings.smtp_host:
            log.warning("[DRY-RUN email] to=%s subject=%s body=%s", to, subject, body)
            return
        m = EmailMessage()
        m["From"], m["To"], m["Subject"] = settings.smtp_from, to, subject
        m.set_content(body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(m)


_notifier: Notifier = Notifier()


def get_notifier() -> Notifier:
    return _notifier


def set_notifier(n: Notifier) -> None:
    """Swap the notifier (tests use a recording fake)."""
    global _notifier
    _notifier = n
