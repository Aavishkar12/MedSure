from app.pipeline.classifier import classify_document_text
from app.pipeline.parsers import (
    parse_discharge_summary,
    parse_investigation_report,
    parse_bill,
    parse_insurance_policy,
    parse_unknown,
)
from app.pipeline.validator import normalize_amount, normalize_date, validate_bill_totals


# -------------------------------------------------------------
# Normalization & Validation Unit Tests
# -------------------------------------------------------------

def test_normalize_amount():
    assert normalize_amount("₹57,350.00") == 57350.00
    assert normalize_amount("Rs. 3,072") == 3072.00
    assert normalize_amount("INR 6,300.50") == 6300.50
    assert normalize_amount("25000") == 25000.00
    assert normalize_amount(None) is None
    assert normalize_amount("Invalid") is None


def test_normalize_date():
    assert normalize_date("2026-09-23") == "2026-09-23"
    assert normalize_date("23/09/2026") == "2026-09-23"
    assert normalize_date("23-09-2026") == "2026-09-23"
    assert normalize_date("23 Sep 2026") == "2026-09-23"
    assert normalize_date("September 23, 2026") == "2026-09-23"
    assert normalize_date("28-Sep-2026") == "2026-09-28"
    assert normalize_date(None) is None
    assert normalize_date("Not a date") is None


def test_validate_bill_totals_matching():
    computed, matches, warnings = validate_bill_totals(
        line_item_amounts=[1000.0, 2000.0, 3350.0],
        gross_total=6350.0,
        advance_paid=2000.0,
        payment_amounts=[1000.0],
        balance_due=3350.0,
    )
    assert computed == 6350.0
    assert matches is True
    assert len(warnings) == 0


def test_validate_bill_totals_mismatch_warning():
    computed, matches, warnings = validate_bill_totals(
        line_item_amounts=[1000.0, 2000.0],
        gross_total=5000.0,
        advance_paid=1000.0,
        payment_amounts=[],
        balance_due=4000.0,
    )
    assert computed == 3000.0
    assert matches is False
    assert any("does not match printed gross total" in w for w in warnings)


# -------------------------------------------------------------
# Document Classification Unit Tests
# -------------------------------------------------------------

def test_classifier_discharge_summary():
    text = """
    ST. HELENA HOSPITAL
    DISCHARGE SUMMARY
    Patient Name: Lakshmi Narayanan  Age: 68  Sex: Female
    Admission Date: 2026-09-23  Discharge Date: 2026-09-28
    UHID: SHH-204518  IP No: IP/26/09/0731
    Diagnosis: Acute Decompensated Heart Failure
    """
    doc_type, conf = classify_document_text(text)
    assert doc_type == "discharge_summary"
    assert conf > 0.70


def test_classifier_investigation_report():
    text = """
    CENTRAL DIAGNOSTIC LABORATORY
    INVESTIGATION REPORT
    Specimen: Blood  Report Date: 2026-09-24
    Hemoglobin: 11.2 g/dL (Reference Range: 12.0 - 15.0) Flag: Low
    Imaging Findings:
    Echocardiogram: LVEF 35%, dilated LV
    ECG: Sinus tachycardia
    Impression: Reduced systolic function.
    """
    doc_type, conf = classify_document_text(text)
    assert doc_type == "investigation_report"
    assert conf > 0.70


def test_classifier_hospital_bill():
    text = """
    APOLLO HOSPITALS
    INPATIENT FINAL BILL
    Bill No: BILL-2026-9081  Bill Date: 2026-09-28
    Gross Total: ₹57,350.00
    Advance Paid: ₹25,000.00
    Balance Due: ₹32,350.00
    """
    doc_type, conf = classify_document_text(text)
    assert doc_type == "hospital_bill"
    assert conf > 0.70


def test_classifier_pharmacy_bill():
    text = """
    MEDPLUS PHARMACY & CHEMIST
    RETAIL TAX INVOICE
    DL No: 20B/1234  GSTIN: 33AAAAA0000A1Z5
    1. Tab Furosemide 40mg  Batch: B812 Exp: 2028-05  Qty: 30 Rate: 3.50 Amount: 105.00
    Gross Total: ₹3,072.00
    """
    doc_type, conf = classify_document_text(text)
    assert doc_type == "pharmacy_bill"
    assert conf > 0.70


def test_classifier_lab_bill():
    text = """
    SRM DIAGNOSTIC CENTRE
    LAB INVOICE
    Invoice No: LAB-2026-441  Date: 2026-09-24
    Test Charges: Complete Blood Count, Renal Profile, Electrolytes
    Gross Total: ₹6,300.00
    """
    doc_type, conf = classify_document_text(text)
    assert doc_type == "lab_bill"
    assert conf > 0.70


def test_classifier_insurance_policy():
    text = """
    STAR HEALTH INSURANCE
    HEALTH INSURANCE POLICY SCHEDULE
    Policy Number: MHA/FF/2026/0048213
    Policyholder: Lakshmi Narayanan
    Sum Insured: ₹500,000
    Co-pay: 10%  Room Rent Limit: ₹4,000 per day
    Claim submission window: 15 days
    """
    doc_type, conf = classify_document_text(text)
    assert doc_type == "insurance_policy"
    assert conf > 0.70


def test_classifier_unknown():
    text = "Hello world! This is a random personal diary note with no medical or billing contents."
    doc_type, conf = classify_document_text(text)
    assert doc_type == "unknown"
    assert conf == 0.0


# -------------------------------------------------------------
# Discharge Summary Parser Unit Tests
# -------------------------------------------------------------

def test_parse_discharge_summary():
    sample_text = """
    ST. HELENA MULTISPECIALITY HOSPITAL
    DISCHARGE SUMMARY
    Patient Name: Lakshmi Narayanan
    Age: 68 Yrs  Sex: Female  Blood Group: B+
    UHID: SHH-204518  IP Number: IP/26/09/0731
    Date of Admission: 23-09-2026
    Date of Discharge: 28-09-2026
    Consultant: Dr. K. Venkatraman, MD, DM (Cardiology)
    Discharge Diagnosis: Congestive Cardiac Failure, Hypertensive Heart Disease

    Discharge Medications:
    1. Furosemide 40 mg - 1 tab once daily in morning for 14 days (Diuretic)
    2. Metoprolol 25 mg - 1 tab twice daily for 30 days (Beta blocker)
    3. Spironolactone 25 mg - 1 tab once daily for 14 days (Potassium sparing diuretic)

    Advice on Discharge:
    - Restrict salt intake (< 2g/day)
    - Fluid restriction 1.5 litres per day
    - Daily morning weight recording

    Follow-up:
    Review in Cardiology OPD on 05-10-2026 at 10:30 AM with Dr. K. Venkatraman

    Warning Signs:
    - Sudden increase in breathlessness
    - Swelling in legs or rapid weight gain
    - Chest discomfort or dizziness
    """

    fields, warnings = parse_discharge_summary(sample_text)

    assert fields.patient.name == "Lakshmi Narayanan"
    assert fields.patient.age == 68
    assert fields.patient.sex == "Female"
    assert fields.patient.uhid == "SHH-204518"
    assert fields.patient.ip_no == "IP/26/09/0731"
    assert fields.admission_date == "2026-09-23"
    assert fields.discharge_date == "2026-09-28"

    assert len(fields.medicines) == 3
    med_names = [m.name for m in fields.medicines]
    assert any("Furosemide" in n for n in med_names)
    assert any("Metoprolol" in n for n in med_names)
    assert any("Spironolactone" in n for n in med_names)

    assert fields.follow_up.date == "2026-10-05"
    assert "10:30" in (fields.follow_up.time or "")
    assert len(fields.advice) >= 2
    assert len(fields.warning_signs) >= 2


def test_parse_discharge_summary_missing_optional_fields():
    minimal_text = """
    DISCHARGE SUMMARY
    Patient Name: Lakshmi Narayanan
    Discharge Date: 2026-09-28
    """
    fields, warnings = parse_discharge_summary(minimal_text)
    assert fields.patient.name == "Lakshmi Narayanan"
    assert fields.patient.age is None
    assert fields.patient.uhid is None
    assert fields.admission_date is None
    assert fields.discharge_date == "2026-09-28"
    assert len(fields.medicines) == 0
    assert any("No discharge medicines" in w for w in warnings)


# -------------------------------------------------------------
# Investigation Report Parser Unit Tests
# -------------------------------------------------------------

def test_parse_investigation_report():
    sample_text = """
    METROPOLIS DIAGNOSTIC SERVICES
    INVESTIGATION REPORT
    Report Date: 24/09/2026

    Test Name              Observed Value   Units    Reference Range   Flag
    Hemoglobin             10.5             g/dL     12.0 - 15.0       Low
    Total WBC Count        8400             /cu.mm   4000 - 11000      Normal
    Platelet Count         210000           /cu.mm   150000 - 450000   Normal
    Serum Creatinine       1.4              mg/dL    0.7 - 1.2         High
    Blood Urea             42.0             mg/dL    15 - 40           High
    Serum Sodium           138.0            mEq/L    135 - 145         Normal
    Serum Potassium        4.2              mEq/L    3.5 - 5.0         Normal
    Serum Bilirubin Total  0.9              mg/dL    0.2 - 1.0         Normal
    SGPT / ALT             34.0             U/L      10 - 40           Normal

    Imaging Findings:
    ECG: Sinus rhythm with non-specific ST-T changes
    Chest X-Ray: Cardiomegaly with mild pulmonary vascular congestion
    Echocardiogram: Impaired left ventricular systolic function, LVEF 35%

    Impression: Moderate LV systolic dysfunction with mild renal impairment.
    """

    fields, warnings = parse_investigation_report(sample_text)
    assert fields.report_date == "2026-09-24"
    assert len(fields.tests) == 9

    test_map = {t.name: t for t in fields.tests}
    assert any("Hemoglobin" in k for k in test_map)
    assert any("Creatinine" in k for k in test_map)
    assert any("Potassium" in k for k in test_map)

    assert len(fields.imaging_findings) >= 2
    assert any("LVEF 35" in f.finding for f in fields.imaging_findings)
    assert fields.impression is not None


# -------------------------------------------------------------
# Bills Parser Unit Tests
# -------------------------------------------------------------

def test_parse_hospital_bill():
    sample_text = """
    ST. HELENA HOSPITAL
    FINAL INPATIENT BILL
    Bill No: HB-2026-0812   Bill Date: 2026-09-28
    Patient: Lakshmi Narayanan

    No.  Particulars                      Qty   Rate       Amount
    1.   Room Rent (ICU)                  2     6500.00    13000.00
    2.   Room Rent (Private Room)         3     3500.00    10500.00
    3.   Nursing Charges                  5     800.00     4000.00
    4.   Consultant Doctor Visits         5     1000.00    5000.00
    5.   ECG charges                      2     450.00     900.00
    6.   Echocardiography                 1     2500.00    2500.00
    7.   Chest X-Ray Digital              1     750.00     750.00
    8.   Complete Blood Count             2     400.00     800.00
    9.   Renal Function Test              3     800.00     2400.00
    10.  Serum Electrolytes               2     600.00     1200.00
    11.  Liver Function Test              1     900.00     900.00
    12.  IV Infusion & Cannulation        1     1200.00    1200.00
    13.  Oxygen Therapy (hours)           10    150.00     1500.00
    14.  Pharmacy & Consumables           1     6800.00    6800.00
    15.  Biomedical Waste Disposal        1     400.00     400.00
    16.  Medical Record Maintenance       1     500.00     500.00
    17.  Admission & Administrative Fee   1     5000.00    5000.00

    Gross Total: ₹57,350.00
    Advance Paid: ₹25,000.00
    Balance Due: ₹32,350.00
    """

    fields, warnings = parse_bill(sample_text, "hospital_bill")
    assert fields.bill_no == "HB-2026-0812"
    assert fields.bill_date == "2026-09-28"
    assert len(fields.line_items) == 17
    assert fields.gross_total == 57350.00
    assert fields.advance_paid == 25000.00
    assert fields.balance_due == 32350.00
    assert fields.computed_total == 57350.00
    assert fields.totals_match is True


def test_parse_pharmacy_bill():
    sample_text = """
    APOLLO PHARMACY
    CASH INVOICE
    Bill No: PH-98214  Bill Date: 28-09-2026

    1. Tab Furosemide 40mg (Strip of 10)     Qty: 2   Rate: 46.00    Amount: 92.00
    2. Tab Metoprolol 25mg (Strip of 10)     Qty: 3   Rate: 110.00   Amount: 330.00
    3. Tab Spironolactone 25mg (Strip of 10) Qty: 2   Rate: 125.00   Amount: 250.00
    4. Tab Pantoprazole 40mg (Strip of 15)   Qty: 2   Rate: 200.00   Amount: 400.00
    5. Injection Enoxaparin 40mg Prefilled   Qty: 2   Rate: 1000.00  Amount: 2000.00

    Gross Total: ₹3,072.00
    """
    fields, warnings = parse_bill(sample_text, "pharmacy_bill")
    assert fields.bill_no == "PH-98214"
    assert len(fields.line_items) == 5
    assert fields.gross_total == 3072.00
    assert fields.computed_total == 3072.00
    assert fields.totals_match is True


def test_parse_lab_bill():
    sample_text = """
    LAL PATHLABS
    LAB INVOICE
    Bill No: LAB-INV-7731  Bill Date: 24-09-2026

    1. Complete Blood Count              Amount: 600.00
    2. Renal Function Profile            Amount: 1100.00
    3. Serum Electrolytes (Na/K/Cl)      Amount: 700.00
    4. Liver Function Test Complete      Amount: 1200.00
    5. Serum Troponin-I Quantitative     Amount: 1400.00
    6. Urine Routine & Microscopy        Amount: 300.00
    7. Home Blood Collection Fee         Amount: 1000.00

    Gross Total: ₹6,300.00
    """
    fields, warnings = parse_bill(sample_text, "lab_bill")
    assert fields.bill_no == "LAB-INV-7731"
    assert len(fields.line_items) == 7
    assert fields.gross_total == 6300.00
    assert fields.computed_total == 6300.00
    assert fields.totals_match is True


# -------------------------------------------------------------
# Insurance Policy Parser Unit Tests
# -------------------------------------------------------------

def test_parse_insurance_policy():
    sample_text = """
    MAX HEALTH INSURANCE COMPANY LIMITED
    FAMILY FLOATER HEALTH INSURANCE POLICY SCHEDULE
    Policy Number: MHA/FF/2026/0048213
    Policyholder: Lakshmi Narayanan
    Inception Date: 2020-04-15
    Policy Period: From 2026-04-15 to 2027-04-14
    Base Sum Insured: ₹500,000

    Insured Persons:
    Lakshmi Narayanan, Self, 68, Female
    Arjun Narayanan, Son, 38, Male

    Policy Terms:
    Room Rent Limit: ₹4,000 per day
    Co-pay: 10% on all claims
    Pre-hospitalisation: 30 days
    Post-hospitalisation: 60 days
    Claim submission window: 15 days from discharge

    Non-payable items:
    - Gloves and face masks
    - Sanitizers and disinfectants
    - Admission registration fees

    Required Documents for Claim:
    - Original Discharge Summary
    - Itemized Hospital Final Bill with breakup
    - Investigation and Diagnostic Reports
    - Pharmacy Bills with doctor prescriptions
    - Payment Receipts and Settlement voucher

    Third Party Administrator:
    TPA Name: Medi Assist TPA Services
    TPA Helpline: 1800-425-9449
    """

    fields, warnings = parse_insurance_policy(sample_text)
    assert fields.policy_no == "MHA/FF/2026/0048213"
    assert fields.policyholder == "Lakshmi Narayanan"
    assert fields.sum_insured == 500000.00
    assert fields.room_rent_limit_per_day == 4000.00
    assert fields.copay_percent == 10.0
    assert fields.claim_submission_days == 15
    assert fields.pre_post_hospitalisation_days.pre == 30
    assert fields.pre_post_hospitalisation_days.post == 60
    assert len(fields.insured_members) >= 1
    assert len(fields.required_documents) >= 4
    assert "Medi Assist" in (fields.tpa.name or "")
    assert "1800-425-9449" in (fields.tpa.helpline or "")


def test_parse_unknown_document():
    text = """
    INSTRUCTIONS FOR AIR CONDITIONER REMOTE
    Power On/Off: Press the red button.
    Temp: Use up and down arrows.
    """
    fields, warnings = parse_unknown(text)
    assert "could not be categorized" in warnings[0]
    assert fields.summary is not None
