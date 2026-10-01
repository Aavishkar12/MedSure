from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .rules import Breathing, Medicine, Swelling

class OtpRequest(BaseModel):
    phone: str
    email: str


class VerifyIn(BaseModel):
    phone: str
    email: str
    otp_phone: str = Field(min_length=6, max_length=6)
    otp_email: str = Field(min_length=6, max_length=6)
    role: Literal["patient", "family"]
    name: str | None = Field(default=None, max_length=120)
    language: str = "en"


class TokenOut(BaseModel):
    token: str
    role: str
    user_id: int
    case_id: int


class DeviceIn(BaseModel):
    fcm_token: str = Field(min_length=10, max_length=500)


class MemberIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str
    email: str
    relation: Literal["son", "daughter", "spouse", "other"] = "other"
    permission: Literal["approve", "view"] = "approve"


class MemberOut(BaseModel):
    user_id: int
    name: str
    relation: str
    permission: str
    allow_alert_calls: bool
    priority: int


class SettingsIn(BaseModel):
    allow_alert_calls: bool | None = None
    language: str | None = None


class CheckinIn(BaseModel):
    breathing: Breathing
    swelling: Swelling
    medicine: Medicine
    note: str | None = Field(default=None, max_length=500)


class CheckinOut(BaseModel):
    checkin_id: int
    status: Literal["green", "amber", "red"]
    reasons: list[str]
    alert_id: str | None = None
    cancel_window_seconds: int = 0


class AttemptOut(BaseModel):
    user_id: int
    channel: str
    status: str
    created_at: datetime


class AlertOut(BaseModel):
    id: str
    level: str
    status: str
    summary: str
    created_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: int | None
    acknowledged_via: str | None
    attempts: list[AttemptOut] = []
