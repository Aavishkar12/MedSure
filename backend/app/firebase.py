"""Firebase Admin: ID token verification and FCM. Everything Firebase-specific lives here."""

import json
from functools import lru_cache

import firebase_admin
from firebase_admin import auth, credentials, messaging

from .config import settings


@lru_cache
def _app():
    raw = settings.firebase_credentials.strip()
    if not raw:
        return None
    cred = credentials.Certificate(json.loads(raw) if raw.startswith("{") else raw)
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
