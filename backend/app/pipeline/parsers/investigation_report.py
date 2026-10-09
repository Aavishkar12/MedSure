import re
from typing import Tuple, List, Optional
from ..schemas import InvestigationReportFields, LabTestItem, ImagingFinding
from ..validator import normalize_date


def parse_investigation_report(text: str) -> Tuple[InvestigationReportFields, List[str]]:
    warnings: List[str] = []
    fields = InvestigationReportFields()

    # 1. Report Date
    m_date = re.search(r"\b(?:Report\s*Date|Date\s*of\s*Report|Reported\s*On|Date)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_date:
        raw_d = m_date.group(1).strip()
        norm_d = normalize_date(raw_d)
        fields.report_date = norm_d or raw_d

    # 2. Lab Tests extraction
    # Tables with Test Name | Result / Value | Units | Reference Range | Flag
    # e.g.: "Serum Creatinine    1.8    mg/dL    0.7 - 1.3    High"
    test_items: List[LabTestItem] = []

    # Regex pattern to match standard lab test rows
    # Look for lines with numeric values, units, and ranges
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # Skip lines that belong to imaging or impression sections
    in_imaging = False
    in_impression = False

    imaging_findings: List[ImagingFinding] = []
    impression_text = []

    for line in lines:
        lower = line.lower()
        if any(h in lower for h in ["imaging findings", "radiology", "ecg", "echocardiogram", "chest x-ray", "x-ray"]):
            in_imaging = True
            in_impression = False
        if "impression:" in lower or "summary of findings:" in lower or "conclusion:" in lower:
            in_impression = True
            in_imaging = False

        if in_impression:
            impression_text.append(line)
            continue

        if in_imaging:
            # Check for study and finding
            # e.g. "ECG: Sinus tachycardia with T wave inversion"
            # "Echocardiogram: Dilated left ventricle, LVEF 35%, moderate MR"
            # "Chest X-Ray: Bilateral pulmonary venous congestion"
            m_study = re.match(r"^((?:ECG|Echocardiogram|Echo|Chest\s*X-?Ray|X-?Ray|CT\s*Scan|Ultrasound|USG)[A-Za-z\s]*)\s*[:\-]\s*(.+)$", line, re.IGNORECASE)
            if m_study:
                imaging_findings.append(
                    ImagingFinding(
                        study=m_study.group(1).strip(),
                        finding=m_study.group(2).strip(),
                    )
                )
            elif len(imaging_findings) > 0 and not any(h in lower for h in ["test", "investigation", "biochemistry"]):
                # Append continued finding
                imaging_findings[-1].finding += f" {line.strip()}"
            continue

        # Look for lab test row pattern:
        # Test Name, Value (float/number), Unit, Reference Range, Flag (Optional)
        # Match lines like: "Hemoglobin 10.2 g/dL 12.0 - 15.0 Low"
        m_test = re.search(
            r"^([A-Za-z0-9\s\(\)/_\-\+]+?)(?:\s{2,}|\t|:)\s*([-+]?\d+(?:\.\d+)?)\s*([A-Za-z/%μµ\-]+)?\s*([0-9\.\-\s<>to]+)?\s*(High|Low|Normal|Critical|Abnormal)?$",
            line,
            re.IGNORECASE,
        )
        if m_test:
            t_name = m_test.group(1).strip() if m_test.group(1) else ""
            t_val = m_test.group(2) if m_test.group(2) else ""
            t_unit = m_test.group(3).strip() if m_test.group(3) else None
            t_range = m_test.group(4).strip() if m_test.group(4) else None
            t_flag = m_test.group(5).strip().capitalize() if m_test.group(5) else None

            # Skip header lines
            if t_name.lower() in ("test name", "investigation", "parameter", "name"):
                continue

            if t_name and t_val:
                test_items.append(
                    LabTestItem(
                        name=t_name,
                        value=t_val,
                        unit=t_unit,
                        reference_range=t_range,
                        flag=t_flag,
                    )
                )
        else:
            # Fallback regex for tabular rows separated by multiple spaces or tabs
            parts = re.split(r"\s{2,}|\t", line)
            if len(parts) >= 2 and re.match(r"^[-+]?\d+(?:\.\d+)?$", parts[1].strip()):
                t_name = parts[0].strip()
                t_val = parts[1].strip()
                t_unit = parts[2].strip() if len(parts) > 2 else None
                t_range = parts[3].strip() if len(parts) > 3 else None
                t_flag = parts[4].strip().capitalize() if len(parts) > 4 else None

                if t_name.lower() not in ("test name", "investigation", "parameter", "name"):
                    test_items.append(
                        LabTestItem(
                            name=t_name,
                            value=t_val,
                            unit=t_unit,
                            reference_range=t_range,
                            flag=t_flag,
                        )
                    )

    # 3. Dedicated LVEF search in text if not yet in findings
    m_lvef = re.search(r"\bLVEF\s*(?:of|is|[:\-])?\s*(\d{1,2}%?)", text, re.IGNORECASE)
    if m_lvef and not any("lvef" in (f.finding or "").lower() for f in imaging_findings):
        lvef_val = m_lvef.group(1)
        imaging_findings.append(ImagingFinding(study="Echocardiogram", finding=f"LVEF {lvef_val}"))

    # 4. Impression
    if impression_text:
        full_imp = " ".join(impression_text).strip()
        full_imp = re.sub(r"^(?:Impression|Conclusion|Summary\s*of\s*findings)\s*[:\-]\s*", "", full_imp, flags=re.IGNORECASE)
        fields.impression = full_imp.strip()
    else:
        m_imp = re.search(r"\b(?:Impression|Conclusion)\s*[:\-]\s*([^\n\r]+(?:\n[^\n\r]+)?)", text, re.IGNORECASE)
        if m_imp:
            fields.impression = m_imp.group(1).strip()

    fields.tests = test_items
    fields.imaging_findings = imaging_findings

    if not fields.tests and not fields.imaging_findings:
        warnings.append("No laboratory tests or imaging findings could be parsed from the document.")

    return fields, warnings
