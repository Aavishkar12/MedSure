import re
from typing import Tuple, List, Optional
from ..schemas import InsurancePolicyFields, InsuredMember, PolicyPeriod, PrePostDays, TpaDetails
from ..validator import normalize_amount, normalize_date


def parse_insurance_policy(text: str) -> Tuple[InsurancePolicyFields, List[str]]:
    warnings: List[str] = []
    fields = InsurancePolicyFields()

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1. Insurer
    for line in lines[:4]:
        lower = line.lower()
        if any(w in lower for w in ["insurance", "assurance", "general insurance", "health insurance"]):
            fields.insurer = line
            break

    # 2. Policy Number
    m_pno = re.search(
        r"\b(?:Policy\s*Number|Policy\s*No\.?|Certificate\s*No\.?)\s*[:\-]\s*([A-Za-z0-9\-_/]+)",
        text,
        re.IGNORECASE,
    )
    if m_pno:
        fields.policy_no = m_pno.group(1).strip()

    # 3. Policyholder
    m_ph = re.search(
        r"\b(?:Policyholder|Proposer\s*Name|Insured\s*Name|Name\s*of\s*the\s*Insured)\s*[:\-]\s*([A-Za-z\s\.]+?)(?=\s{2,}|\n|\t|UHID|Age|$)",
        text,
        re.IGNORECASE,
    )
    if m_ph:
        fields.policyholder = m_ph.group(1).strip()

    # 4. Inception Date
    m_inc = re.search(r"\b(?:Inception\s*Date|First\s*Inception|Date\s*of\s*Inception)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_inc:
        fields.inception_date = normalize_date(m_inc.group(1).strip()) or m_inc.group(1).strip()

    # 5. Policy Period
    m_period = re.search(
        r"(?:Policy\s*Period|Period\s*of\s*Insurance|Coverage\s*Period)\s*[:\-]?\s*(?:From\s*)?([^\n\r,]+?)\s*(?:to|-)\s*([^\n\r,]+)",
        text,
        re.IGNORECASE,
    )
    if m_period:
        p_start = normalize_date(m_period.group(1).strip()) or m_period.group(1).strip()
        p_end = normalize_date(m_period.group(2).strip()) or m_period.group(2).strip()
        fields.policy_period = PolicyPeriod(start=p_start, end=p_end)

    # 6. Sum Insured
    m_si = re.search(
        r"\b(?:Sum\s*Insured|Base\s*Sum\s*Insured|Coverage\s*Amount)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{1,2})?)",
        text,
        re.IGNORECASE,
    )
    if m_si:
        fields.sum_insured = normalize_amount(m_si.group(1))

    # 7. Room Rent Limit Per Day
    m_rr = re.search(
        r"\b(?:Room\s*Rent\s*(?:Limit|Cap)?|Daily\s*Room\s*Rent)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{1,2})?)(?:\s*(?:per\s*day|/day|day))?",
        text,
        re.IGNORECASE,
    )
    if m_rr:
        fields.room_rent_limit_per_day = normalize_amount(m_rr.group(1))

    # 8. Copay Percent
    m_copay = re.search(r"\b(?:Co[\s-]*pay|Copayment|Co-payment)\s*(?:percentage|percent|%)?\s*[:\-]?\s*(\d{1,2})\s*%", text, re.IGNORECASE)
    if m_copay:
        try:
            fields.copay_percent = float(m_copay.group(1))
        except ValueError:
            pass

    # 9. Pre / Post Hospitalisation Days
    # e.g.: Pre-hospitalisation: 30 days, Post-hospitalisation: 60 days
    m_pre = re.search(r"\bPre[\s-]*hospitali[sz]ation\s*[:\-]?\s*(\d+)\s*days?", text, re.IGNORECASE)
    m_post = re.search(r"\bPost[\s-]*hospitali[sz]ation\s*[:\-]?\s*(\d+)\s*days?", text, re.IGNORECASE)
    if m_pre or m_post:
        pre_val = int(m_pre.group(1)) if m_pre else None
        post_val = int(m_post.group(1)) if m_post else None
        fields.pre_post_hospitalisation_days = PrePostDays(pre=pre_val, post=post_val)

    # 10. Claim Submission Days
    m_csd = re.search(
        r"\b(?:Claim\s*submission\s*(?:window|limit|period|timeframe|within)?|Submit\s*claims?\s*within)\s*[:\-]?\s*(\d+)\s*days?",
        text,
        re.IGNORECASE,
    )
    if m_csd:
        try:
            fields.claim_submission_days = int(m_csd.group(1))
        except ValueError:
            pass

    # 11. Insured Members list
    # e.g.: Lakshmi Narayanan (Self, 68, F), Arjun (Son, 38, M)
    members: List[InsuredMember] = []
    m_sec = re.search(r"(?:Insured\s*Persons?|Insured\s*Members?|Persons\s*Covered)\s*[:\-]?\s*(.*?)(?=(?:Policy\s*Period|Sum\s*Insured|Terms|$))", text, re.IGNORECASE | re.DOTALL)
    if m_sec:
        m_lines = [l.strip(" -•\t") for l in m_sec.group(1).splitlines() if l.strip(" -•\t")]
        for m_l in m_lines:
            # Pattern: Name | Relation | Age | Sex
            m_parts = re.split(r"[,|\t]\s*", m_l)
            if len(m_parts) >= 2:
                mem_name = m_parts[0].strip()
                mem_rel = m_parts[1].strip() if len(m_parts) > 1 else None
                mem_age = None
                mem_sex = None
                for p in m_parts[2:]:
                    p_clean = p.strip()
                    if p_clean.isdigit():
                        mem_age = int(p_clean)
                    elif p_clean.lower() in ("m", "male", "f", "female"):
                        mem_sex = "Female" if p_clean.lower().startswith("f") else "Male"
                if mem_name and not mem_name.lower().startswith("name"):
                    members.append(InsuredMember(name=mem_name, relation=mem_rel, age=mem_age, sex=mem_sex))
    fields.insured_members = members

    # 12. Non-payable Categories
    m_non = re.search(
        r"(?:Non[\s-]*payable\s*items?|Excluded\s*items?|Exclusions|List\s*of\s*non[\s-]*payables)\s*[:\-]?\s*(.*?)(?=(?:Required\s*Documents|TPA|$))",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_non:
        raw_non = m_non.group(1).strip()
        fields.non_payable_categories = [l.strip(" -•\t") for l in raw_non.splitlines() if l.strip(" -•\t")]

    # 13. Required Documents
    m_req = re.search(
        r"(?:Required\s*Documents|Documents\s*required\s*for\s*claim|Checklist\s*of\s*documents)\s*[:\-]?\s*(.*?)(?=(?:TPA|Helpline|Terms|Signature|$))",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_req:
        raw_req = m_req.group(1).strip()
        fields.required_documents = [l.strip(" -•\t") for l in raw_req.splitlines() if l.strip(" -•\t")]

    # 14. TPA details
    tpa_obj = TpaDetails()
    m_tpa = re.search(r"\b(?:TPA\s*Name|TPA|Third\s*Party\s*Administrator)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_tpa:
        tpa_obj.name = m_tpa.group(1).strip()
    m_help = re.search(r"\b(?:TPA\s*Helpline|Helpline\s*No|Toll\s*Free|Customer\s*Care)\s*[:\-]\s*([0-9\-\s\+]+)", text, re.IGNORECASE)
    if m_help:
        tpa_obj.helpline = m_help.group(1).strip()
    fields.tpa = tpa_obj

    # Validation checks
    if not fields.policy_no:
        warnings.append("Policy number could not be found.")
    if fields.sum_insured is None:
        warnings.append("Sum insured could not be determined.")

    return fields, warnings
