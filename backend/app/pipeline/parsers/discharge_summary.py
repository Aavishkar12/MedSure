import re
from typing import Tuple, List, Optional
from ..schemas import DischargeSummaryFields, PatientDetails, DischargeMedicine, FollowUpDetails
from ..validator import normalize_date


def parse_discharge_summary(text: str) -> Tuple[DischargeSummaryFields, List[str]]:
    warnings: List[str] = []
    fields = DischargeSummaryFields()

    # 1. Hospital Header
    # Often top 1-2 lines before "Discharge Summary"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines[:5]:
        if "hospital" in line.lower() or "medical centre" in line.lower() or "healthcare" in line.lower() or "institute" in line.lower():
            fields.hospital = line
            break

    # 2. Patient details
    p_name = None
    m_name = re.search(r"(?:Patient\s*(?:Name)?|Pt\s*Name|Name)\s*[:\-]\s*([A-Za-z\s\.]+?)(?=\s{2,}|\n|\t|Age|UHID|Sex|Gender|DOA|DOB|IP|Admission|Discharge|$)", text, re.IGNORECASE)
    if m_name:
        p_name = m_name.group(1).strip()
        fields.patient.name = p_name

    m_age = re.search(r"\bAge\s*[:\-]\s*(\d{1,3})\s*(?:Y|Yrs|Years)?", text, re.IGNORECASE)
    if m_age:
        try:
            fields.patient.age = int(m_age.group(1))
        except ValueError:
            pass

    m_sex = re.search(r"\b(?:Sex|Gender)\s*[:\-]\s*(Female|Male|F|M|Other)\b", text, re.IGNORECASE)
    if m_sex:
        s_val = m_sex.group(1).strip().capitalize()
        if s_val == "F":
            s_val = "Female"
        elif s_val == "M":
            s_val = "Male"
        fields.patient.sex = s_val

    m_uhid = re.search(r"\bUHID\s*[:\-]\s*([A-Za-z0-9\-_/]+)", text, re.IGNORECASE)
    if m_uhid:
        fields.patient.uhid = m_uhid.group(1).strip()

    m_ip = re.search(r"\b(?:IP\s*(?:No|Number)|Inpatient\s*(?:No|Number))\s*[:\-]\s*([A-Za-z0-9\-_/]+)", text, re.IGNORECASE)
    if m_ip:
        fields.patient.ip_no = m_ip.group(1).strip()

    m_bg = re.search(r"\bBlood\s*Group\s*[:\-]\s*([A-Za-z0-9+\-]+)", text, re.IGNORECASE)
    if m_bg:
        fields.patient.blood_group = m_bg.group(1).strip()

    # 3. Dates
    m_adm = re.search(r"\b(?:Admission\s*Date|Date\s*of\s*Admission|DOA)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_adm:
        raw_adm = m_adm.group(1).strip()
        norm_adm = normalize_date(raw_adm)
        fields.admission_date = norm_adm or raw_adm

    m_dis = re.search(r"\b(?:Discharge\s*Date|Date\s*of\s*Discharge|DOD)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_dis:
        raw_dis = m_dis.group(1).strip()
        norm_dis = normalize_date(raw_dis)
        fields.discharge_date = norm_dis or raw_dis

    # 4. Consultant
    m_doc = re.search(r"\b(?:Consultant|Treating\s*Doctor|Doctor\s*In\s*Charge)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_doc:
        fields.consultant = m_doc.group(1).strip()

    # 5. Diagnosis
    m_diag = re.search(
        r"\b(?:Discharge\s*Diagnosis|Final\s*Diagnosis|Diagnosis)\s*[:\-]\s*([^\n\r]+(?:\n[^\n\r]+)?)",
        text,
        re.IGNORECASE,
    )
    if m_diag:
        d_val = m_diag.group(1).strip()
        # Cut off if next major heading starts
        d_val = re.split(r"(?:Chief\s*Complaints|History|Course|Medicines|Advice|Investigations)", d_val, flags=re.IGNORECASE)[0].strip()
        fields.diagnosis = d_val

    # 6. Medicines extraction
    med_section = ""
    m_med_sec = re.search(
        r"(?:Discharge\s*Medications|Medications\s*at\s*Discharge|Medicines\s*Prescribed|Prescription|Rx)\s*[:\-]?\s*(.*?)(?=(?:Advice\s*on\s*Discharge|Discharge\s*Advice|Follow[\s-]*Up|Warning\s*Signs|Emergency\s*Signs|$))",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_med_sec:
        med_section = m_med_sec.group(1).strip()
    else:
        # Fallback search for lines with medicine indicators
        med_section = text

    # Parse individual medicines (lines like: Furosemide 40 mg - 1 tab OD x 5 days (Diuretic))
    med_lines = [l.strip() for l in med_section.splitlines() if l.strip()]
    parsed_meds: List[DischargeMedicine] = []

    dose_pattern = r"(\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml|IU|units?))"
    freq_pattern = r"(once\s*daily|twice\s*daily|thrice\s*daily|OD|BD|TDS|QID|1-0-1|1-0-0|0-0-1|0-1-0|PRN|SOS|as\s*needed|bedtime|morning|night)"
    dur_pattern = r"(\d+\s*(?:days?|weeks?|months?))"

    for line in med_lines:
        # Ignore headers
        if re.match(r"^(?:S\.?No|Medicine|Name|Dose|Frequency|Duration|Remarks)", line, re.IGNORECASE):
            continue
        # Look for dosage keyword in line
        if re.search(dose_pattern, line, re.IGNORECASE) or re.search(freq_pattern, line, re.IGNORECASE):
            # Clean leading bullet/numbers
            cleaned = re.sub(r"^\d+[\.\)\-]\s*", "", line).strip()
            
            # Extract dose
            m_d = re.search(dose_pattern, cleaned, re.IGNORECASE)
            dose = m_d.group(1) if m_d else None

            # Extract frequency
            m_f = re.search(freq_pattern, cleaned, re.IGNORECASE)
            freq = m_f.group(1) if m_f else None

            # Extract duration
            m_dur = re.search(dur_pattern, cleaned, re.IGNORECASE)
            duration = m_dur.group(1) if m_dur else None

            # Extract purpose (often in parentheses or after dash)
            m_pur = re.search(r"\(([^)]+)\)|(?:for|purpose[:\-])\s*([^\n\r,\.]+)", cleaned, re.IGNORECASE)
            purpose = (m_pur.group(1) or m_pur.group(2)).strip() if m_pur else None

            # Extract medicine name (usually the first 1-3 words before dose)
            name_candidate = cleaned
            if dose:
                name_candidate = cleaned[:cleaned.find(dose)].strip()
            elif freq:
                name_candidate = cleaned[:cleaned.find(freq)].strip()

            # Clean name candidate
            name_candidate = re.sub(r"^(Tab\.?|Cap\.?|Inj\.?|Syr\.?)\s*", "", name_candidate, flags=re.IGNORECASE).strip()
            name_candidate = name_candidate.strip(" -:,")

            if name_candidate:
                parsed_meds.append(
                    DischargeMedicine(
                        name=name_candidate,
                        dose=dose,
                        frequency=freq,
                        purpose=purpose,
                        duration=duration,
                    )
                )

    fields.medicines = parsed_meds

    # 7. Follow-up
    m_fu = re.search(r"Follow[\s-]*up\s*[:\-]?\s*(.*?)(?=(?:Warning\s*Signs|Emergency|$))", text, re.IGNORECASE | re.DOTALL)
    if m_fu:
        fu_text = m_fu.group(1).strip()
        fu_obj = FollowUpDetails()
        # Find date
        norm_fu_date = normalize_date(fu_text)
        if norm_fu_date:
            fu_obj.date = norm_fu_date
        # Find time
        m_time = re.search(r"\b(\d{1,2}:\d{2}\s*(?:AM|PM|hrs)?)\b", fu_text, re.IGNORECASE)
        if m_time:
            fu_obj.time = m_time.group(1).strip()
        # Find department / doctor
        m_dept = re.search(r"(?:with|in|at)\s*(?:Dr\.?\s*[A-Za-z\s]+|([A-Za-z\s]+(?:OPD|Clinic|Department|Cardiology|Nephrology)))", fu_text, re.IGNORECASE)
        if m_dept:
            fu_obj.department = m_dept.group(0).strip()
        fu_obj.note = fu_text.splitlines()[0].strip() if fu_text else None
        fields.follow_up = fu_obj

    # 8. Advice
    m_adv = re.search(r"(?:Discharge\s*Advice|Advice\s*on\s*Discharge|General\s*Advice)\s*[:\-]?\s*(.*?)(?=(?:Follow[\s-]*up|Warning\s*Signs|$))", text, re.IGNORECASE | re.DOTALL)
    if m_adv:
        adv_text = m_adv.group(1).strip()
        fields.advice = [l.strip(" -•\t") for l in adv_text.splitlines() if l.strip(" -•\t")]

    # 9. Warning Signs
    m_ws = re.search(r"(?:Warning\s*Signs|Red\s*Flags|When\s*to\s*seek\s*immediate\s*help)\s*[:\-]?\s*(.*?)(?=(?:Discharge|Signature|$))", text, re.IGNORECASE | re.DOTALL)
    if m_ws:
        ws_text = m_ws.group(1).strip()
        fields.warning_signs = [l.strip(" -•\t") for l in ws_text.splitlines() if l.strip(" -•\t")]

    # Validation checks
    if not fields.patient.name:
        warnings.append("Patient name could not be identified.")
    if not fields.discharge_date:
        warnings.append("Discharge date not found or could not be normalized.")
    if not fields.medicines:
        warnings.append("No discharge medicines extracted.")

    return fields, warnings
