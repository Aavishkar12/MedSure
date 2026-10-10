import re
from datetime import datetime
from typing import Optional, List, Tuple


def normalize_amount(raw_val: Optional[str | float | int]) -> Optional[float]:
    """
    Cleans and normalizes monetary strings to float.
    Removes ₹, Rs, Rs., INR, spaces, commas.
    Returns float or None.
    """
    if raw_val is None:
        return None
    if isinstance(raw_val, (int, float)):
        return round(float(raw_val), 2)

    val_str = str(raw_val).strip()
    if not val_str:
        return None

    # Remove currency markers and spaces
    cleaned = re.sub(r"[₹\s]|Rs\.?|INR", "", val_str, flags=re.IGNORECASE)
    # Remove thousand separators
    cleaned = cleaned.replace(",", "")

    # Match numeric portion including negative and decimals
    match = re.search(r"[-+]?\d*\.?\d+", cleaned)
    if match:
        try:
            return round(float(match.group(0)), 2)
        except ValueError:
            return None
    return None


def normalize_date(raw_date: Optional[str]) -> Optional[str]:
    """
    Normalizes a variety of date formats into ISO format: YYYY-MM-DD.
    Supports formats like:
      - 2026-09-23
      - 23/09/2026, 23-09-2026
      - 23 Sep 2026, 23-Sep-2026, 23 September 2026
      - September 23, 2026
    """
    if not raw_date:
        return None

    d_str = raw_date.strip()
    if not d_str:
        return None

    # Direct match for already ISO YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d_str):
        return d_str

    # Common date formats in Indian medical reports and bills
    formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%d %b %Y",
        "%d-%b-%Y",
        "%d %B %Y",
        "%d-%B-%Y",
        "%b %d, %Y",
        "%B %d, %Y",
        "%d %b, %Y",
        "%d %b %y",
        "%d/%m/%y",
        "%d-%m-%y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(d_str, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Try extracting date pattern within text
    date_regexes = [
        (r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", lambda m: f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"),
        (r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", lambda m: f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"),
    ]

    for pat, formatter in date_regexes:
        m = re.search(pat, d_str)
        if m:
            try:
                candidate = formatter(m)
                # Verify valid date
                datetime.strptime(candidate, "%Y-%m-%d")
                return candidate
            except ValueError:
                pass

    return None


def validate_bill_totals(
    line_item_amounts: List[float],
    gross_total: Optional[float],
    advance_paid: Optional[float],
    payment_amounts: List[float],
    balance_due: Optional[float],
) -> Tuple[Optional[float], Optional[bool], List[str]]:
    """
    Validates arithmetic for bill items, gross totals, payments, and balance due.
    Returns:
      (computed_total, totals_match, warnings)
    Rules:
      - A mismatch must generate a warning in the JSON.
      - Never silently change a printed total or overwrite a discrepancy.
    """
    warnings: List[str] = []
    computed_total: Optional[float] = None
    totals_match: Optional[bool] = None

    if line_item_amounts:
        computed_total = round(sum(line_item_amounts), 2)

    if gross_total is not None and computed_total is not None:
        diff = round(abs(computed_total - gross_total), 2)
        if diff <= 1.0:  # Allow 1 rupee rounding tolerance
            totals_match = True
        else:
            totals_match = False
            warnings.append(
                f"Computed line-item total (INR {computed_total}) does not match printed gross total (INR {gross_total}). Difference: INR {round(computed_total - gross_total, 2)}"
            )

    # Balance due verification
    if gross_total is not None and balance_due is not None:
        total_payments = sum(payment_amounts) if payment_amounts else 0.0
        adv = advance_paid if advance_paid is not None else 0.0
        expected_balance = round(gross_total - adv - total_payments, 2)
        diff_bal = round(abs(expected_balance - balance_due), 2)
        if diff_bal > 1.0:
            warnings.append(
                f"Computed balance due (INR {expected_balance}) does not match printed balance due (INR {balance_due})."
            )

    return computed_total, totals_match, warnings
