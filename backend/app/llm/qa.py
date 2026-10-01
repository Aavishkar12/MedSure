"""Grounded Q&A: answers come only from the case's own documents, and every source quote is checked."""

import json
import re
from typing import Optional

from pydantic import BaseModel, ValidationError

from .client import complete_json

MAX_CONTEXT_CHARS = 40_000
NOT_FOUND = "I couldn't find that in your uploaded documents. Your doctor or the hospital can answer this."

SYSTEM = """You answer a family's questions about a patient's own hospital documents.
Rules:
- Answer ONLY from the documents below. Do not add facts from outside medical knowledge.
- If the documents do not contain the answer, set grounded to false and leave sources empty.
- Never diagnose, predict outcomes, or advise on treatment or doses. If asked what to do, say what
  the documents say and suggest asking the treating doctor.
- Plain everyday language, one to four short sentences.
- Give at least one source: the document_id, the page from the nearest [Page N] marker above the
  quote (null if there is none), and a quote copied word-for-word from the document, 20 words at most.
Reply with a single JSON object:
{"answer": string, "grounded": boolean, "sources": [{"document_id": integer, "page": integer or null, "quote": string}]}"""


class Source(BaseModel):
    document_id: int
    page: Optional[int] = None
    quote: str = ""


class QAResult(BaseModel):
    answer: str = ""
    grounded: bool = False
    sources: list[Source] = []


def _norm(text: str) -> str:
    for dash in "‐‑‒–—":
        text = text.replace(dash, "-")
    for quote in "“”‘’\"'":
        text = text.replace(quote, "")
    return " ".join(text.split()).casefold().strip(" .…")


def answer_question(question: str, docs: list[dict]) -> dict:
    """docs: [{"id", "doc_type", "text"}]. Returns {"answer", "grounded", "sources"}."""
    not_found = {"answer": NOT_FOUND, "grounded": False, "sources": []}
    if not docs:
        return not_found
    context = "\n\n".join(f"=== Document {d['id']} ({d['doc_type']}) ===\n{d['text']}" for d in docs)
    try:
        raw = complete_json(SYSTEM, f"{context[:MAX_CONTEXT_CHARS]}\n\nQuestion: {question}")
        result = QAResult.model_validate(raw)
    except (ValidationError, json.JSONDecodeError):
        return not_found

    # Keep only sources whose quote really appears in that document, and take the page from where it was found.
    texts = {d["id"]: _norm(d["text"]) for d in docs}
    sources = []
    for s in result.sources:
        position = _find(s.quote, texts.get(s.document_id, ""))
        if position is None:
            continue
        pages = re.findall(r"\[page (\d+)\]", texts[s.document_id][:position])
        s.page = int(pages[-1]) if pages else None
        sources.append(s.model_dump())
    if not result.grounded or not result.answer or not sources:
        return not_found
    answer = result.answer.replace(" ", " ").replace(" ", " ")
    return {"answer": answer, "grounded": True, "sources": sources}


def _find(quote: str, text: str) -> int | None:
    """Position of the quote in the text. A quote shortened with "..." must match on every piece."""
    pieces = [p for p in (_norm(p) for p in re.split(r"\.{3,}|…", quote)) if len(p) >= 4]
    if not pieces or not text or any(p not in text for p in pieces):
        return None
    return text.find(pieces[-1])
