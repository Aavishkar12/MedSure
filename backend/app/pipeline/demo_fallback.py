"""
Demo fallback module.
Provides pre-extracted reference JSON for the six designated synthetic sample documents
ONLY when DEMO_FALLBACK=true and live extraction fails.
OFF by default.
"""

from typing import Any, Dict, Optional, Tuple

# The six designated synthetic sample reference datasets
SAMPLE_DISCHARGE_SUMMARY = {
    "patient": {
        "name": "Lakshmi Narayanan",
        "age": 68,
        "sex": "Female",
        "uhid": "SHH-204518",
        "ip_no": "IP/26/09/0731",
        "blood_group": "B+",
    },
    "hospital": "Sunshine Heart Hospital",
    "admission_date": "2026-09-23",
    "discharge_date": "2026-09-28",
    "consultant": "Dr. R. K. Sharma, MD, DM (Cardiology)",
    "diagnosis": "Acute Decompensated Heart Failure, Dilated Cardiomyopathy",
    "medicines": [
        {
            "name": "Tab Furosemide",
            "dose": "40 mg",
            "frequency": "OD (Once Daily, Morning)",
            "purpose": "Diuretic (reduces fluid accumulation)",
            "duration": "Continue until review",
        },
        {
            "name": "Tab Metoprolol Succinate",
            "dose": "25 mg",
            "frequency": "BD (Twice Daily)",
            "purpose": "Beta-blocker (regulates heart rate and pressure)",
            "duration": "Continue until review",
        },
        {
            "name": "Tab Spironolactone",
            "dose": "25 mg",
            "frequency": "OD (Once Daily)",
            "purpose": "Potassium-sparing diuretic",
            "duration": "Continue until review",
        },
    ],
    "advice": [
        "Strict salt restriction (< 2 g/day)",
        "Fluid restriction up to 1.5 L/day",
        "Daily morning weight monitoring",
    ],
    "follow_up": {
        "date": "2026-10-05",
        "time": "10:30",
        "department": "Cardiology OPD Room 12",
        "note": "Bring discharge summary, latest electrolytes, and BP log.",
    },
    "warning_signs": [
        "Sudden weight gain (> 1.5 kg in 2 days)",
        "Severe shortness of breath at rest or when lying flat",
        "Marked swelling of feet or abdomen",
    ],
}

SAMPLE_INVESTIGATION_REPORT = {
    "report_date": "2026-09-24",
    "tests": [
        {"name": "Hemoglobin", "value": "11.2", "unit": "g/dL", "reference_range": "12.0 - 15.0", "flag": "Low"},
        {"name": "Total Leukocyte Count", "value": "7800", "unit": "/cu.mm", "reference_range": "4000 - 11000", "flag": "Normal"},
        {"name": "Serum Creatinine", "value": "1.3", "unit": "mg/dL", "reference_range": "0.6 - 1.2", "flag": "High"},
        {"name": "Blood Urea Nitrogen", "value": "28", "unit": "mg/dL", "reference_range": "7 - 20", "flag": "High"},
        {"name": "Serum Sodium", "value": "134", "unit": "mEq/L", "reference_range": "135 - 145", "flag": "Low"},
        {"name": "Serum Potassium", "value": "4.2", "unit": "mEq/L", "reference_range": "3.5 - 5.0", "flag": "Normal"},
        {"name": "Serum Chloride", "value": "99", "unit": "mEq/L", "reference_range": "96 - 106", "flag": "Normal"},
        {"name": "Random Blood Sugar", "value": "142", "unit": "mg/dL", "reference_range": "70 - 140", "flag": "High"},
        {"name": "NT-proBNP", "value": "3420", "unit": "pg/mL", "reference_range": "< 300", "flag": "High"},
    ],
    "imaging_findings": [
        {"study": "ECG", "finding": "Sinus rhythm, rate 88/min, Left ventricular hypertrophy, non-specific ST-T changes"},
        {"study": "Chest X-Ray", "finding": "Cardiomegaly with bilateral pulmonary venous congestion and mild interstitial edema"},
        {"study": "Echocardiogram", "finding": "Dilated left ventricle, LVEF 35%, moderate mitral regurgitation, impaired relaxation"},
    ],
    "impression": "Severe LV systolic dysfunction with elevated filling pressures consistent with Acute Decompensated Heart Failure.",
}

SAMPLE_HOSPITAL_BILL = {
    "vendor": "Sunshine Heart Hospital",
    "bill_no": "SHH-IP-2026-4412",
    "bill_date": "2026-09-28",
    "line_items": [
        {"no": 1, "description": "Room Rent - Deluxe Cardiology Bed", "date": "2026-09-23", "qty": 5, "rate": 3500.0, "amount": 17500.0, "category": "Accommodation"},
        {"no": 2, "description": "Nursing Care Charges", "date": "2026-09-23", "qty": 5, "rate": 800.0, "amount": 4000.0, "category": "Nursing"},
        {"no": 3, "description": "ICU Step-Down Monitoring", "date": "2026-09-23", "qty": 2, "rate": 2500.0, "amount": 5000.0, "category": "Monitoring"},
        {"no": 4, "description": "Consultant Physician Visit Charges", "date": "2026-09-23", "qty": 5, "rate": 1000.0, "amount": 5000.0, "category": "Consultation"},
        {"no": 5, "description": "Duty Doctor Rounding Fees", "date": "2026-09-23", "qty": 5, "rate": 500.0, "amount": 2500.0, "category": "Consultation"},
        {"no": 6, "description": "12-Lead Electrocardiogram (ECG)", "date": "2026-09-23", "qty": 2, "rate": 450.0, "amount": 900.0, "category": "Investigation"},
        {"no": 7, "description": "Comprehensive 2D Echocardiography", "date": "2026-09-24", "qty": 1, "rate": 3200.0, "amount": 3200.0, "category": "Investigation"},
        {"no": 8, "description": "Chest Digital Radiography (AP View)", "date": "2026-09-24", "qty": 1, "rate": 850.0, "amount": 850.0, "category": "Investigation"},
        {"no": 9, "description": "Biochemistry - Comprehensive Electrolyte Panel", "date": "2026-09-24", "qty": 2, "rate": 650.0, "amount": 1300.0, "category": "Laboratory"},
        {"no": 10, "description": "Renal Function Profile", "date": "2026-09-24", "qty": 2, "rate": 800.0, "amount": 1600.0, "category": "Laboratory"},
        {"no": 11, "description": "NT-proBNP Immunoassay", "date": "2026-09-24", "qty": 1, "rate": 2800.0, "amount": 2800.0, "category": "Laboratory"},
        {"no": 12, "description": "Complete Hemogram", "date": "2026-09-24", "qty": 2, "rate": 450.0, "amount": 900.0, "category": "Laboratory"},
        {"no": 13, "description": "IV Cannulation & Infusion Set", "date": "2026-09-23", "qty": 2, "rate": 350.0, "amount": 700.0, "category": "Consumables"},
        {"no": 14, "description": "Syringe Pump & Tubing Charges", "date": "2026-09-23", "qty": 2, "rate": 1200.0, "amount": 2400.0, "category": "Equipment"},
        {"no": 15, "description": "Continuous Pulse Oximetry & Oxygen Therapy", "date": "2026-09-23", "qty": 3, "rate": 1500.0, "amount": 4500.0, "category": "Therapy"},
        {"no": 16, "description": "Biomedical Waste Disposal & Sanitisation", "date": "2026-09-28", "qty": 1, "rate": 1200.0, "amount": 1200.0, "category": "Hospital Charges"},
        {"no": 17, "description": "Administrative Processing & Discharge Dossier", "date": "2026-09-28", "qty": 1, "rate": 3000.0, "amount": 3000.0, "category": "Administration"},
    ],
    "gross_total": 57350.0,
    "computed_total": 57350.0,
    "totals_match": True,
    "payments": [
        {"date": "2026-09-23", "amount": 25000.0, "mode": "UPI / Net Banking", "paid_by": "Family Advance"}
    ],
    "advance_paid": 25000.0,
    "balance_due": 32350.0,
}

SAMPLE_PHARMACY_BILL = {
    "vendor": "Apollo Pharmacy - Sunshine Hospital Ext",
    "bill_no": "AP-SH-90812",
    "bill_date": "2026-09-28",
    "line_items": [
        {"no": 1, "description": "Tab Lasix (Furosemide) 40mg", "date": "2026-09-28", "qty": 30, "rate": 4.5, "amount": 135.0, "category": "Medicines"},
        {"no": 2, "description": "Tab Betaloc (Metoprolol Succinate) 25mg", "date": "2026-09-28", "qty": 60, "rate": 11.2, "amount": 672.0, "category": "Medicines"},
        {"no": 3, "description": "Tab Aldactone (Spironolactone) 25mg", "date": "2026-09-28", "qty": 30, "rate": 7.5, "amount": 225.0, "category": "Medicines"},
        {"no": 4, "description": "Tab Entresto (Sacubitril/Valsartan) 50mg", "date": "2026-09-28", "qty": 28, "rate": 65.0, "amount": 1820.0, "category": "Medicines"},
        {"no": 5, "description": "Digital Blood Pressure Monitor Strips & Acc", "date": "2026-09-28", "qty": 1, "rate": 220.0, "amount": 220.0, "category": "Surgicals"},
    ],
    "gross_total": 3072.0,
    "computed_total": 3072.0,
    "totals_match": True,
    "payments": [
        {"date": "2026-09-28", "amount": 3072.0, "mode": "Card", "paid_by": "Patient"}
    ],
    "advance_paid": 0.0,
    "balance_due": 0.0,
}

SAMPLE_LAB_BILL = {
    "vendor": "Thyrocare / Sunshine Diagnostics",
    "bill_no": "LAB-INV-77341",
    "bill_date": "2026-09-24",
    "line_items": [
        {"no": 1, "description": "Cardiac Biomarkers - NT-proBNP Quantitative", "date": "2026-09-24", "qty": 1, "rate": 2800.0, "amount": 2800.0, "category": "Cardiac"},
        {"no": 2, "description": "High Sensitivity Troponin-I", "date": "2026-09-24", "qty": 1, "rate": 1200.0, "amount": 1200.0, "category": "Cardiac"},
        {"no": 3, "description": "Renal Function Test (Urea, Creatinine, Uric Acid)", "date": "2026-09-24", "qty": 1, "rate": 750.0, "amount": 750.0, "category": "Biochemistry"},
        {"no": 4, "description": "Electrolytes Panel (Na+, K+, Cl-)", "date": "2026-09-24", "qty": 1, "rate": 550.0, "amount": 550.0, "category": "Biochemistry"},
        {"no": 5, "description": "Complete Blood Count (CBC with Automated ESR)", "date": "2026-09-24", "qty": 1, "rate": 450.0, "amount": 450.0, "category": "Hematology"},
        {"no": 6, "description": "Liver Function Test (LFT Profile)", "date": "2026-09-24", "qty": 1, "rate": 800.0, "amount": 800.0, "category": "Biochemistry"},
        {"no": 7, "description": "Home Phlebotomy & Sample Collection Charges", "date": "2026-09-24", "qty": 1, "rate": 350.0, "amount": 350.0, "category": "Service"},
    ],
    "gross_total": 6300.0,
    "computed_total": 6300.0,
    "totals_match": True,
    "payments": [
        {"date": "2026-09-24", "amount": 6300.0, "mode": "UPI", "paid_by": "Family"}
    ],
    "advance_paid": 0.0,
    "balance_due": 0.0,
}

SAMPLE_INSURANCE_POLICY = {
    "insurer": "Star Health and Allied Insurance Co. Ltd.",
    "policy_no": "MHA/FF/2026/0048213",
    "policyholder": "Narayanan S.",
    "insured_members": [
        {"name": "Lakshmi Narayanan", "relation": "Spouse", "age": 68, "sex": "Female"},
        {"name": "Narayanan S.", "relation": "Self", "age": 72, "sex": "Male"},
    ],
    "policy_period": {
        "start": "2026-01-15",
        "end": "2027-01-14",
    },
    "inception_date": "2018-01-15",
    "sum_insured": 500000.0,
    "room_rent_limit_per_day": 4000.0,
    "copay_percent": 10.0,
    "pre_post_hospitalisation_days": {
        "pre": 30,
        "post": 60,
    },
    "claim_submission_days": 15,
    "non_payable_categories": [
        "Toiletries and cosmetic items",
        "Administrative charges",
        "Admission kit fees",
        "Attendant food charges",
    ],
    "required_documents": [
        "Original hospital final bill with detailed breakup",
        "Original payment receipts and advance slips",
        "Discharge summary with complete clinical notes",
        "Investigation reports with radiological films and lab results",
        "Original pharmacy bills with doctor's prescriptions",
        "Cancelled cheque with account holder's name for NEFT settlement",
    ],
    "tpa": {
        "name": "Medi Assist Insurance TPA Pvt. Ltd.",
        "helpline": "1800-425-2255",
    },
}


def get_demo_fallback_extraction(filename: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Checks if filename matches one of the six designated synthetic samples.
    Returns (doc_type, fields_dict) or None.
    Never returns sample data for arbitrary unrecognized documents.
    """
    fn = filename.lower()
    if "discharge" in fn:
        return "discharge_summary", SAMPLE_DISCHARGE_SUMMARY
    elif "investigation" in fn or "lab_report" in fn:
        return "investigation_report", SAMPLE_INVESTIGATION_REPORT
    elif "hospital_bill" in fn or ("hospital" in fn and "bill" in fn):
        return "hospital_bill", SAMPLE_HOSPITAL_BILL
    elif "pharmacy" in fn:
        return "pharmacy_bill", SAMPLE_PHARMACY_BILL
    elif "lab_bill" in fn or "lab_invoice" in fn:
        return "lab_bill", SAMPLE_LAB_BILL
    elif "policy" in fn or "insurance" in fn:
        return "insurance_policy", SAMPLE_INSURANCE_POLICY
    return None
