"""Bill vs policy: which billed items the insurance policy is likely to pay for, and why.

The LLM judges each line against the policy's own wording. Everything with money in it is then
recomputed here (clamping, co-pay, sum-insured cap, totals), and every policy quote it gives is
checked against the policy text, so the numbers and citations shown to the family are never the
model's arithmetic or invention. The result is an estimate; the insurer decides.
"""

import json
import logging
import re
from typing import Literal, Optional

from pydantic import BaseModel, ValidationError

from .client import complete_json
from .qa import _find, _norm

logger = logging.getLogger("medsure.coverage")

MAX_POLICY_CHARS = 20_000
DISCLAIMER = (
    "This is an estimate from your policy and bill, not a claim decision. "
    "Your insurer or TPA decides what is paid."
)
STATUSES = ("covered", "partly_covered", "not_covered", "unclear")

SYSTEM = """You help an Indian family understand which charges on a hospital bill their health
insurance policy is likely to pay. You compare each bill line with the policy.
Rules:
- Judge ONLY from the policy terms and policy text given. Do not use what policies "usually" cover.
- For every bill line return exactly one entry with its bill_item_id and a status:
  covered: the policy pays for this kind of charge and no limit in the policy cuts it.
  partly_covered: the policy pays, but a stated limit (room rent cap, sub-limit, proportionate
    deduction) means only part of it is payable. Set claimable_amount to the payable part.
  not_covered: the policy excludes it or lists it as non-payable.
  unclear: the policy does not say enough to decide.
- A line may end with its quantity and rate, e.g. "(5 x Rs 6000)" for 5 days at Rs 6,000. A per-day
  or per-unit limit applies to each unit: a Rs 4,000 per day limit on that line allows 5 x 4,000.
- claimable_amount is in rupees and never more than the line amount. Do NOT apply the co-payment or
  the sum insured; that is done separately.
- reason: one plain sentence a non-expert understands, naming the policy rule you relied on.
- policy_quote: whenever policy text is given, the exact words from it that support the decision,
  copied word for word from one sentence, at most 25 words, with no "..." and nothing added.
- notes: up to four short, plain points that affect the whole claim (waiting periods, pre-authorisation,
  claim deadline). Only what the policy text states; do not add general advice or lists of documents.
- explanation: three to five calm, plain sentences for the family on how the policy treats this bill
  and what to do next. Do not state rupee totals; they are calculated separately.
- Never promise that a claim will be approved.
Reply with a single JSON object:
{"items": [{"bill_item_id": integer, "status": "covered"|"partly_covered"|"not_covered"|"unclear",
  "claimable_amount": number, "reason": string, "policy_quote": string}],
 "notes": [string], "explanation": string}"""


class ItemJudgement(BaseModel):
    bill_item_id: int
    status: Literal["covered", "partly_covered", "not_covered", "unclear"] = "unclear"
    claimable_amount: Optional[float] = None
    reason: str = ""
    policy_quote: str = ""


class CoverageReply(BaseModel):
    items: list[ItemJudgement] = []
    notes: list[str] = []
    explanation: str = ""


def _rupees(value: float) -> str:
    """Indian digit grouping: 184350 -> Rs 1,84,350."""
    whole = int(round(value))
    s = str(abs(whole))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups) + "," + tail
    return f"Rs {'-' if whole < 0 else ''}{s}"


def _policy_terms(policy: dict) -> dict:
    """The structured terms worth sending, without empty fields."""
    keep = {k: v for k, v in policy.items() if v not in (None, "", [], {}) and k not in ("disclaimer", "source_page")}
    return keep


def _verified_quote(quote: str, policy_text: str) -> str:
    if not quote or not policy_text:
        return ""
    return quote if _find(quote, _norm(policy_text)) is not None else ""


def compare_bill_to_policy(bill_items: list[dict], policy: dict, policy_text: str = "", diagnosis: str = "") -> dict:
    """
    bill_items: [{"id", "description", "amount", "explanation"?}]
    policy: structured policy terms (see extract.PolicyData)
    Returns the coverage report: items, totals, notes, explanation, disclaimer.
    """
    lines = [
        {"bill_item_id": b["id"], "description": b["description"], "amount": round(float(b["amount"]), 2)}
        for b in bill_items
    ]
    user = (
        f"Policy terms (structured):\n{json.dumps(_policy_terms(policy), indent=1, default=str)}\n\n"
        f"Policy text:\n{policy_text[:MAX_POLICY_CHARS] or '(not available)'}\n\n"
        f"Diagnosis on the discharge summary: {diagnosis or '(not available)'}\n\n"
        f"Bill lines:\n{json.dumps(lines, indent=1)}"
    )
    reply = CoverageReply()
    for attempt in range(2):
        try:
            reply = CoverageReply.model_validate(complete_json(SYSTEM, user))
            break
        except (ValidationError, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Coverage reply invalid (attempt {attempt + 1}): {e}")
            user += f"\n\nYour previous reply was invalid: {str(e)[:800]}\nReturn corrected JSON only."
    return build_report(lines, reply, policy, policy_text, method="ai")


_QTY_RATE = re.compile(r"\((\d+(?:\.\d+)?) x Rs (\d+(?:\.\d+)?)\)")
_ROOM = re.compile(r"\b(room|bed|ward|boarding)\b", re.IGNORECASE)
_NOT_ROOM = re.compile(r"\b(icu|iccu|nicu|theatre|operating|operation|recovery|emergency)\b", re.IGNORECASE)


def _room_rent_cap(line: dict, policy: dict) -> Optional[tuple[float, str]]:
    """
    For a room-rent line with its days and daily rate, what a fixed per-day limit allows, with the
    reason. Worked out here rather than by the model: it is plain arithmetic and it is money.
    """
    limit = policy.get("room_rent_limit_per_day")
    desc = line["description"]
    found = _QTY_RATE.search(desc)
    if not limit or not found or not _ROOM.search(desc) or _NOT_ROOM.search(desc):
        return None
    days, rate = float(found.group(1)), float(found.group(2))
    if rate <= limit:
        return None
    allowed = round(min(line["amount"], days * limit), 2)
    reason = (
        f"Your policy pays room rent up to {_rupees(limit)} a day. {days:g} days were billed at "
        f"{_rupees(rate)} a day, so {_rupees(allowed)} of this is claimable."
    )
    return allowed, reason


def build_report(lines: list[dict], reply: CoverageReply, policy: dict, policy_text: str, method: str) -> dict:
    """Recomputes every amount from the per-line judgements and the policy's own numbers."""
    judged = {j.bill_item_id: j for j in reply.items}
    items = []
    for line in lines:
        j = judged.get(line["bill_item_id"]) or ItemJudgement(
            bill_item_id=line["bill_item_id"], reason="The policy terms did not settle this charge."
        )
        amount = line["amount"]
        if j.status == "covered":
            claimable = amount if j.claimable_amount is None or j.claimable_amount <= 0 else j.claimable_amount
        elif j.status == "partly_covered":
            claimable = j.claimable_amount or 0.0
        else:  # not_covered, unclear: nothing is counted as claimable
            claimable = 0.0
        claimable = round(min(max(claimable, 0.0), amount), 2)
        status, reason = j.status, j.reason.strip()
        capped = _room_rent_cap(line, policy)
        if capped and status in ("covered", "partly_covered"):
            claimable, reason = capped
            status = "partly_covered"
        if status == "partly_covered" and claimable >= amount:
            status = "covered"
        if status == "partly_covered" and claimable == 0:
            status = "not_covered"
        items.append({
            **line,
            "status": status,
            "claimable_amount": claimable,
            "reason": reason,
            "policy_quote": _verified_quote(j.policy_quote.strip(), policy_text),
        })

    billed = round(sum(i["amount"] for i in items), 2)
    eligible = round(sum(i["claimable_amount"] for i in items), 2)
    unclear = round(sum(i["amount"] for i in items if i["status"] == "unclear"), 2)
    copay_pct = policy.get("copay_percent") or 0.0
    copay_pct = copay_pct if 0 < copay_pct < 100 else 0.0
    copay = round(eligible * copay_pct / 100, 2)
    deductible = min(float(policy.get("deductible") or 0.0), eligible - copay)
    estimate = eligible - copay - deductible
    notes = [n.strip() for n in reply.notes if n.strip()][:4]
    sum_insured = policy.get("sum_insured")
    if sum_insured and estimate > sum_insured:
        notes.insert(0, f"The estimate is capped at your sum insured of {_rupees(sum_insured)}.")
        estimate = float(sum_insured)
    estimate = round(max(estimate, 0.0), 2)

    headline = (
        f"Of {_rupees(billed)} billed, about {_rupees(estimate)} looks claimable under your policy, "
        f"so you may have to pay about {_rupees(billed - estimate)}."
    )
    if unclear:
        headline += f" {_rupees(unclear)} is unclear from the policy; ask your insurer or TPA about it."
    if copay:
        headline += f" This includes your {copay_pct:g}% co-payment of {_rupees(copay)}."

    return {
        "method": method,
        "headline": headline,
        "explanation": reply.explanation.strip(),
        "items": items,
        "totals": {
            "billed": billed,
            "eligible": eligible,
            "copay_percent": copay_pct,
            "copay": copay,
            "deductible": round(deductible, 2),
            "estimated_claimable": estimate,
            "estimated_out_of_pocket": round(billed - estimate, 2),
            "unclear": unclear,
            "counts": {s: sum(i["status"] == s for i in items) for s in STATUSES},
        },
        "notes": notes,
        "insurer": policy.get("insurer"),
        "policy_number": policy.get("policy_number"),
        "disclaimer": DISCLAIMER,
    }


# Words that mark a charge as one Indian policies commonly list as non-payable (IRDAI list of
# consumables). Used only without the AI, and only when the policy itself lists that kind of item.
_NON_PAYABLE_HINTS = {
    "admin": ("admin", "registration", "documentation", "file", "processing"),
    "toiletr": ("toiletr", "cosmetic", "soap", "shampoo", "diaper"),
    "attendant": ("attendant", "visitor", "food", "meal", "diet"),
    "admission kit": ("admission kit", "kit"),
    "glove": ("glove", "mask", "apron"),
}


def rule_based_report(bill_items: list[dict], policy: dict, policy_text: str = "") -> dict:
    """Without the AI: marks only lines the policy's own non-payable list names; the rest is unclear."""
    lines = [
        {"bill_item_id": b["id"], "description": b["description"], "amount": round(float(b["amount"]), 2)}
        for b in bill_items
    ]
    non_payable = [n.lower() for n in (policy.get("non_payable_items") or []) + (policy.get("exclusions") or [])]
    judgements = []
    for line in lines:
        desc = line["description"].lower()
        hit = next(
            (rule for rule in non_payable
             for key, words in _NON_PAYABLE_HINTS.items()
             if key in rule and any(w in desc for w in words)),
            None,
        )
        if hit:
            judgements.append(ItemJudgement(
                bill_item_id=line["bill_item_id"], status="not_covered",
                reason=f"Your policy lists this kind of charge as not payable ({hit}).",
            ))
        else:
            judgements.append(ItemJudgement(
                bill_item_id=line["bill_item_id"], status="unclear",
                reason="Needs the AI review or your insurer to confirm.",
            ))
    reply = CoverageReply(
        items=judgements,
        explanation="AI review is not available right now, so only charges your policy names as not payable are marked. "
                    "Ask your insurer or TPA about the rest.",
    )
    return build_report(lines, reply, policy, policy_text, method="rules")
