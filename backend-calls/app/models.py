import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .timeutil import utcnow


def new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("phone", name="uq_users_phone"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))          # E.164, e.g. +919876543210
    email: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(10))           # patient | family
    language: Mapped[str] = mapped_column(String(8), default="en")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    devices: Mapped[list["Device"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Case(Base):
    """One patient's recovery case. The patient owns it; family join through CaseMember."""
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    patient: Mapped[User] = relationship()
    members: Mapped[list["CaseMember"]] = relationship(back_populates="case", order_by="CaseMember.priority, CaseMember.id")


class CaseMember(Base):
    __tablename__ = "case_members"
    __table_args__ = (UniqueConstraint("case_id", "user_id", name="uq_case_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    relation: Mapped[str] = mapped_column(String(20), default="other")
    permission: Mapped[str] = mapped_column(String(10), default="approve")   # approve | view
    allow_alert_calls: Mapped[bool] = mapped_column(Boolean, default=True)   # consent for automated calls
    priority: Mapped[int] = mapped_column(Integer, default=0)                # lower = called first
    added_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Case] = relationship(back_populates="members")
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    fcm_token: Mapped[str] = mapped_column(String(500), unique=True)
    platform: Mapped[str] = mapped_column(String(10), default="android")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="devices")


class OtpCode(Base):
    __tablename__ = "otp_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    email: Mapped[str] = mapped_column(String(200))
    phone_hash: Mapped[str] = mapped_column(String(64))
    email_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used: Mapped[bool] = mapped_column(Boolean, default=False)


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    answers: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(8))           # green | amber | red (set by rules, never by an LLM)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_due", "status", "next_run_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    checkin_id: Mapped[int] = mapped_column(ForeignKey("checkins.id"))
    level: Mapped[str] = mapped_column(String(8))            # amber | red
    summary: Mapped[str] = mapped_column(Text, default="")
    # open: escalating | notified: amber, push only | acknowledged | exhausted | cancelled
    status: Mapped[str] = mapped_column(String(14), default="open")
    current_idx: Mapped[int] = mapped_column(Integer, default=0)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    acknowledged_via: Mapped[str | None] = mapped_column(String(10), nullable=True)   # call | app
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    case: Mapped[Case] = relationship()


class AlertAttempt(Base):
    """One push, call or SMS sent for an alert."""
    __tablename__ = "alert_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[str] = mapped_column(ForeignKey("alerts.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(6))          # push | call | sms
    status: Mapped[str] = mapped_column(String(20))
    provider_ref: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    alert_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    actor: Mapped[str] = mapped_column(String(40))           # system | user:<id> | twilio
    action: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
