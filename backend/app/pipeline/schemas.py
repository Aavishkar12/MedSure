from datetime import datetime, timezone
from typing import Any, List, Optional
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# -------------------------------------------------------------
# A. Discharge Summary
# -------------------------------------------------------------

class PatientDetails(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None
    uhid: Optional[str] = None
    ip_no: Optional[str] = None
    blood_group: Optional[str] = None


class DischargeMedicine(BaseModel):
    name: Optional[str] = None
    dose: Optional[str] = None
    frequency: Optional[str] = None
    purpose: Optional[str] = None
    duration: Optional[str] = None


class FollowUpDetails(BaseModel):
    date: Optional[str] = None
    time: Optional[str] = None
    department: Optional[str] = None
    note: Optional[str] = None


class DischargeSummaryFields(BaseModel):
    patient: PatientDetails = Field(default_factory=PatientDetails)
    hospital: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    consultant: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: List[DischargeMedicine] = Field(default_factory=list)
    advice: List[str] = Field(default_factory=list)
    follow_up: FollowUpDetails = Field(default_factory=FollowUpDetails)
    warning_signs: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# B. Investigation Report
# -------------------------------------------------------------

class LabTestItem(BaseModel):
    name: Optional[str] = None
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None
    flag: Optional[str] = None


class ImagingFinding(BaseModel):
    study: Optional[str] = None
    finding: Optional[str] = None


class InvestigationReportFields(BaseModel):
    report_date: Optional[str] = None
    tests: List[LabTestItem] = Field(default_factory=list)
    imaging_findings: List[ImagingFinding] = Field(default_factory=list)
    impression: Optional[str] = None


# -------------------------------------------------------------
# C. Hospital, Pharmacy, and Lab Bills
# -------------------------------------------------------------

class BillLineItem(BaseModel):
    no: Optional[int] = None
    description: Optional[str] = None
    date: Optional[str] = None
    qty: Optional[float] = None
    rate: Optional[float] = None
    amount: Optional[float] = None
    category: Optional[str] = None


class BillPaymentItem(BaseModel):
    date: Optional[str] = None
    amount: Optional[float] = None
    mode: Optional[str] = None
    paid_by: Optional[str] = None


class BillFields(BaseModel):
    vendor: Optional[str] = None
    bill_no: Optional[str] = None
    bill_date: Optional[str] = None
    line_items: List[BillLineItem] = Field(default_factory=list)
    gross_total: Optional[float] = None
    computed_total: Optional[float] = None
    totals_match: Optional[bool] = None
    payments: List[BillPaymentItem] = Field(default_factory=list)
    advance_paid: Optional[float] = None
    balance_due: Optional[float] = None


# -------------------------------------------------------------
# D. Insurance Policy
# -------------------------------------------------------------

class InsuredMember(BaseModel):
    name: Optional[str] = None
    relation: Optional[str] = None
    age: Optional[int] = None
    sex: Optional[str] = None


class PolicyPeriod(BaseModel):
    start: Optional[str] = None
    end: Optional[str] = None


class PrePostDays(BaseModel):
    pre: Optional[int] = None
    post: Optional[int] = None


class TpaDetails(BaseModel):
    name: Optional[str] = None
    helpline: Optional[str] = None


class InsurancePolicyFields(BaseModel):
    insurer: Optional[str] = None
    policy_no: Optional[str] = None
    policyholder: Optional[str] = None
    insured_members: List[InsuredMember] = Field(default_factory=list)
    policy_period: PolicyPeriod = Field(default_factory=PolicyPeriod)
    inception_date: Optional[str] = None
    sum_insured: Optional[float] = None
    room_rent_limit_per_day: Optional[float] = None
    copay_percent: Optional[float] = None
    pre_post_hospitalisation_days: PrePostDays = Field(default_factory=PrePostDays)
    claim_submission_days: Optional[int] = None
    non_payable_categories: List[str] = Field(default_factory=list)
    required_documents: List[str] = Field(default_factory=list)
    tpa: TpaDetails = Field(default_factory=TpaDetails)


# -------------------------------------------------------------
# E. Unknown Document Fields
# -------------------------------------------------------------

class UnknownDocumentFields(BaseModel):
    summary: Optional[str] = None
    extracted_headings: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# Common Metadata Envelope
# -------------------------------------------------------------

class DocumentExtractionEnvelope(BaseModel):
    schema_version: str = "1.0.0"
    doc_id: str
    case_id: str
    source_file: str
    file_hash: str
    doc_type: str
    classification_confidence: Optional[float] = None
    pages: int = 0
    extraction_method: str = "mlkit"
    extraction_confidence: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    extracted_at: str = Field(default_factory=utc_now_iso)
    fields: dict[str, Any] = Field(default_factory=dict)


class CaseExtractionEnvelope(BaseModel):
    schema_version: str = "1.0.0"
    case_id: str
    generated_at: str = Field(default_factory=utc_now_iso)
    total_documents: int = 0
    documents: List[DocumentExtractionEnvelope] = Field(default_factory=list)
