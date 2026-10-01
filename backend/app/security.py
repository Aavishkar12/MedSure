import hashlib
import hmac
import re
import secrets
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User
from .timeutil import utcnow

bearer = HTTPBearer(auto_error=False)


def normalize_phone(raw: str) -> str:
    """Indian numbers by default: 10 digits -> +91XXXXXXXXXX. Anything with a country code is kept."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if 11 <= len(digits) <= 15:
        return "+" + digits
    raise ValueError("invalid phone number")


def normalize_email(raw: str) -> str:
    return raw.strip().lower()


def new_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(code: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), code.encode(), hashlib.sha256).hexdigest()


def code_matches(code: str, expected_hash: str) -> bool:
    if settings.dev_mode and settings.dev_otp and hmac.compare_digest(code, settings.dev_otp):
        return True
    return hmac.compare_digest(hash_code(code), expected_hash)


def create_token(user_id: int) -> str:
    exp = utcnow() + timedelta(hours=settings.jwt_hours)
    return jwt.encode({"sub": str(user_id), "exp": exp}, settings.jwt_secret, algorithm="HS256")


def current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None:
        raise HTTPException(401, "Missing bearer token")
    try:
        data = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=["HS256"])
        user = db.get(User, int(data["sub"]))
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
    if user is None:
        raise HTTPException(401, "Unknown user")
    return user
