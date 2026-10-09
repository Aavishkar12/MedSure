import re
from typing import Tuple, List, Optional
from ..schemas import BillFields, BillLineItem, BillPaymentItem
from ..validator import normalize_amount, normalize_date, validate_bill_totals


def parse_bill(text: str, bill_subtype: str = "hospital_bill") -> Tuple[BillFields, List[str]]:
    warnings: List[str] = []
    fields = BillFields()

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1. Vendor
    for line in lines[:4]:
        lower = line.lower()
        if any(w in lower for w in ["hospital", "pharmacy", "chemist", "lab", "diagnostics", "healthcare", "medical"]):
            fields.vendor = line
            break
    if not fields.vendor and len(lines) > 0:
        fields.vendor = lines[0]

    # 2. Bill No
    m_bno = re.search(r"\b(?:Bill\s*No|Invoice\s*No|Bill\s*#|Receipt\s*No|Invoice\s*#)\s*[:\-]\s*([A-Za-z0-9\-_/]+)", text, re.IGNORECASE)
    if m_bno:
        fields.bill_no = m_bno.group(1).strip()

    # 3. Bill Date
    m_bdate = re.search(r"\b(?:Bill\s*Date|Invoice\s*Date|Date)\s*[:\-]\s*([^\n\r,]+)", text, re.IGNORECASE)
    if m_bdate:
        raw_bdate = m_bdate.group(1).strip()
        fields.bill_date = normalize_date(raw_bdate) or raw_bdate

    # 4. Printed Totals
    # Gross Total / Total Amount / Subtotal / Net Total
    m_gross = re.search(r"\b(?:Gross\s*Total|Total\s*Amount|Grand\s*Total|Invoice\s*Total|Net\s*Amount|Total)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if m_gross:
        fields.gross_total = normalize_amount(m_gross.group(1))

    # Advance paid
    m_adv = re.search(r"\b(?:Advance\s*Paid|Advance|Deposit\s*Paid|Less\s*Advance)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if m_adv:
        fields.advance_paid = normalize_amount(m_adv.group(1))

    # Balance due
    m_bal = re.search(r"\b(?:Balance\s*Due|Balance\s*Payable|Amount\s*Due|Net\s*Due|Outstanding)\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{1,2})?)", text, re.IGNORECASE)
    if m_bal:
        fields.balance_due = normalize_amount(m_bal.group(1))

    # 5. Line items extraction
    line_items: List[BillLineItem] = []
    item_counter = 1

    for line in lines:
        lower = line.lower()

        # Skip headers, metadata lines and summary rows
        if any(h in lower for h in [
            "particulars", "description", "item name", "s.no", "sl no", "qty   rate",
            "bill no", "invoice no", "patient", "uhid", "bill date", "date of", "admission date", "discharge date",
            "gross total", "grand total", "sub total", "subtotal", "total amount",
            "advance paid", "balance due", "authorized signatory", "terms & conditions"
        ]):
            continue

        # Pattern A: Numbered row with multiple columns
        # E.g. "1. Room Rent (ICU)   2   6500.00   13000.00"
        # E.g. "1. Tab Furosemide 40mg (Strip of 10)  Qty: 2  Rate: 46.00  Amount: 92.00"
        m_num = re.match(r"^(\d+)[\.\)]?\s+(.+)$", line)
        if m_num:
            idx_val = int(m_num.group(1))
            rest = m_num.group(2).strip()

            # Find all numbers with possible currency or decimals at the end
            # Extract final amount
            m_amt = re.search(r"(?:INR|Rs\.?|₹|Amount[:\s]*)?\s*([0-9,]+(?:\.\d{2})?)\s*$", rest, re.IGNORECASE)
            if m_amt:
                amt_str = m_amt.group(1)
                num_amt = normalize_amount(amt_str)
                if num_amt is not None:
                    desc_part = rest[:m_amt.start()].strip()
                    # Clean out trailing Qty / Rate if present
                    m_qr = re.search(r"(?:Qty[:\s]*(\d+(?:\.\d+)?))?\s*(?:Rate[:\s]*([0-9,]+(?:\.\d{2})?))?\s*$", desc_part, re.IGNORECASE)
                    qty_val = 1.0
                    rate_val = num_amt
                    if m_qr and (m_qr.group(1) or m_qr.group(2)):
                        if m_qr.group(1):
                            qty_val = float(m_qr.group(1))
                        if m_qr.group(2):
                            rate_val = normalize_amount(m_qr.group(2))
                        desc_part = desc_part[:m_qr.start()].strip()
                    else:
                        # Check columns: desc ... qty ... rate
                        cols = re.split(r"\s{2,}|\t", desc_part)
                        if len(cols) >= 3 and re.match(r"^\d+(?:\.\d+)?$", cols[-2].strip()) and re.match(r"^[0-9,]+(?:\.\d{2})?$", cols[-1].strip()):
                            qty_val = float(cols[-2].strip())
                            rate_val = normalize_amount(cols[-1].strip())
                            desc_part = " ".join(cols[:-2]).strip()
                        elif len(cols) >= 2 and re.match(r"^\d+(?:\.\d+)?$", cols[-1].strip()):
                            qty_val = float(cols[-1].strip())
                            desc_part = " ".join(cols[:-1]).strip()

                    line_items.append(
                        BillLineItem(
                            no=idx_val,
                            description=desc_part.strip(" -:,"),
                            qty=qty_val,
                            rate=rate_val,
                            amount=num_amt,
                        )
                    )
                    continue

        # Pattern B: Unnumbered line with columns ending in amount
        cols = re.split(r"\s{2,}|\t", line)
        if len(cols) >= 2:
            last_val = normalize_amount(cols[-1])
            if last_val is not None:
                desc_col = cols[0].strip()
                if not any(k in desc_col.lower() for k in ["total", "advance", "balance", "due"]):
                    line_items.append(
                        BillLineItem(
                            no=item_counter,
                            description=desc_col,
                            qty=1.0,
                            rate=last_val,
                            amount=last_val,
                        )
                    )
                    item_counter += 1

    # Deduplicate line items if needed
    fields.line_items = line_items

    # 6. Payments extraction
    payments: List[BillPaymentItem] = []
    m_pay = re.finditer(
        r"(?:Paid|Payment|Receipt)\s*(?:via|by|mode)?\s*([A-Za-z\s]+)?\s*[:\-]?\s*(?:INR|Rs\.?|₹)?\s*([0-9,]+(?:\.\d{2})?)",
        text,
        re.IGNORECASE,
    )
    for p in m_pay:
        p_mode = p.group(1).strip() if p.group(1) else "UPI/Card/Cash"
        p_amt = normalize_amount(p.group(2))
        if p_amt:
            payments.append(BillPaymentItem(date=fields.bill_date, amount=p_amt, mode=p_mode))

    fields.payments = payments

    # 7. Verification and arithmetic checks
    line_amounts = [item.amount for item in fields.line_items if item.amount is not None]
    payment_amounts = [p.amount for p in fields.payments if p.amount is not None]

    computed_total, totals_match, val_warnings = validate_bill_totals(
        line_item_amounts=line_amounts,
        gross_total=fields.gross_total,
        advance_paid=fields.advance_paid,
        payment_amounts=payment_amounts,
        balance_due=fields.balance_due,
    )

    fields.computed_total = computed_total
    fields.totals_match = totals_match
    warnings.extend(val_warnings)

    if not fields.line_items:
        warnings.append(f"No line items could be parsed from {bill_subtype}.")
    if fields.gross_total is None and fields.computed_total is not None:
        fields.gross_total = fields.computed_total

    return fields, warnings
