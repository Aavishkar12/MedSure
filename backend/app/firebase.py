"""Firebase Admin: ID token verification and FCM. Everything Firebase-specific lives here."""

import json
import logging
from functools import lru_cache
from pathlib import Path

try:
    import firebase_admin
    from firebase_admin import auth, credentials, messaging
except ImportError:
    firebase_admin = None
    auth = None
    credentials = None
    messaging = None

from .config import settings

log = logging.getLogger("medsure.firebase")


@lru_cache
def _app():
    if not firebase_admin:
        return None
    raw = settings.firebase_credentials.strip()
    if not raw:
        return None
    if not raw.startswith("{") and not Path(raw).is_file():
        # .env.example points at a key file a new checkout does not have yet. Push and token sign-in
        # stay off; everything else (documents, AI, dev sign-in) must keep working.
        log.warning(f"FIREBASE_CREDENTIALS file not found: {raw}. Push and Firebase sign-in are disabled.")
        return None
    try:
        cred = credentials.Certificate(json.loads(raw) if raw.startswith("{") else raw)
    except ValueError as e:
        # Usually the Android app's google-services.json saved here by mistake: that is a different file.
        log.warning(f"FIREBASE_CREDENTIALS is not a service-account key ({e}). Push and Firebase sign-in are disabled.")
        return None
    return firebase_admin.initialize_app(cred)


def enabled() -> bool:
    return _app() is not None


def verify_token(id_token: str) -> dict:
    # Tolerate a server clock that is slightly off, or fresh tokens are rejected as "used too early".
    return auth.verify_id_token(id_token, app=_app(), clock_skew_seconds=60)


def send_push(tokens: list[str], title: str, body: str, data: dict[str, str]) -> tuple[int, list[str]]:
    """Returns (delivered count, tokens that are no longer registered).

    Sent as a high-priority data message so the app draws the notification itself, including when it is
    in the background. That is what lets it add buttons such as "Call".
    """
    message = messaging.MulticastMessage(
        tokens=tokens,
        # No title/body makes it a silent update: the app refreshes and shows nothing.
        data={**data, **({"title": title, "body": body} if body else {})},
        android=messaging.AndroidConfig(priority="high"),
    )
    resp = messaging.send_each_for_multicast(message, app=_app())
    dead = [t for t, r in zip(tokens, resp.responses) if isinstance(r.exception, messaging.UnregisteredError)]
    return resp.success_count, dead
