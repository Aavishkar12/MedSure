from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

DOC_TYPES = ["discharge_summary", "lab_report", "prescription", "bill", "id_proof", "policy"]


def now() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: str = Field(primary_key=True)  # Firebase uid
    name: str = ""
    email: Optional[str] = Field(default=None, index=True)


class Device(SQLModel, table=True):
    token: str = Field(primary_key=True)  # FCM registration token
    user_id: str = Field(foreign_key="user.id", index=True)
    platform: str = "android"
    updated_at: datetime = Field(default_factory=now)


class Case(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    patient_name: str
    created_by: str = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=now)


class CaseMember(SQLModel, table=True):
    case_id: int = Field(foreign_key="case.id", primary_key=True)
    user_id: str = Field(foreign_key="user.id", primary_key=True)
    role: str = "family"  # patient | family


class Document(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    doc_type: str
    filename: str
    path: str
    sha256: str = Field(index=True)
    text: Optional[str] = None  # OCR / extracted text with [Page N] markers
    status: str = "processing"  # processing | ready | failed
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=now)


class DischargeCard(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    document_id: int = Field(foreign_key="document.id")
    # diagnosis, medicines[], lab_values[], precautions[], follow_ups[] — each with source_page
    data: dict = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class BillItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    document_id: int = Field(foreign_key="document.id")
    description: str
    amount: float
    explanation: str = ""
    worth_asking: bool = False
    ask_reason: Optional[str] = None
    concept: Optional[str] = None  # shared key for smart linking, e.g. "kidney_function"


class Claim(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    mode: str = "cashless"  # cashless | reimbursement
    insurer: str = ""
    status: str = "not_submitted"  # not_submitted | submitted | query_raised | approved | denied
    created_at: datetime = Field(default_factory=now)


class ChecklistItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    claim_id: int = Field(foreign_key="claim.id", index=True)
    label: str
    doc_type: str


class Draft(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    claim_id: Optional[int] = Field(default=None, foreign_key="claim.id")
    kind: str  # claim_letter | appeal_letter | family_summary
    body: str
    status: str = "draft"  # draft -> approved -> sent
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=now)


class Checkin(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    answers: dict = Field(default_factory=dict, sa_column=Column(JSON))
    flags: list = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=now)


class TimelineEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    case_id: int = Field(foreign_key="case.id", index=True)
    kind: str  # document | discharge_card | bill | claim | draft | checkin
    title: str
    ref_id: Optional[int] = None
    created_at: datetime = Field(default_factory=now)
