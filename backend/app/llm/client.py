"""Thin Groq wrapper. Everything provider-specific lives in this file."""

import base64
import json
from pathlib import Path

from groq import APIError, Groq, RateLimitError

from ..config import settings

# Groq caps images per request; keep discharge packs short or split by page.
MAX_IMAGES = 5

_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def file_to_text(path: str) -> str:
    """Text layer of a typed PDF with [Page N] markers. Empty for scans and images."""
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return ""
    import pymupdf

    with pymupdf.open(p) as pdf:
        pages =[(i, page.get_text().strip()) for i, page in enumerate(pdf, start=1)]
    return "\n\n".join(f"[Page {i}]\n{text}" for i, text in pages if text)


def file_to_images(path: str) -> list[bytes]:
    """Return JPEG bytes per page. PDFs are rendered; images pass through."""
    p = Path(path)
    if p.suffix.lower() != ".pdf":
        return [p.read_bytes()]
    import pymupdf

    with pymupdf.open(p) as pdf:
        return[page.get_pixmap(dpi=110).tobytes("jpeg") for page in pdf][:MAX_IMAGES]


def _messages(system: str, user: str, images: list[bytes] | None) -> list[dict]:
    if not images:  # text-only models reject list content
        return [{"role": "system", "content": system}, {"role": "user", "content": user}]
    content: list[dict] = [{"type": "text", "text": user}]
    for i, img in enumerate(images, start=1):
        content.append({"type": "text", "text": f"[Page {i}]"})
        url = "data:image/jpeg;base64," + base64.b64encode(img).decode()
        content.append({"type": "image_url", "image_url": {"url": url}})
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


class LLMError(RuntimeError):
    """Message is safe to show to the user."""


def _chat(**kwargs) -> str:
    if kwargs["model"].startswith("openai/gpt-oss"):  # reasoning models; keep them quick
        kwargs["reasoning_effort"] = "low"
    try:
        resp = _groq().chat.completions.create(**kwargs)
    except RateLimitError as e:
        raise LLMError("The AI service is busy right now. Please try again in a minute.") from e
    except APIError as e:
        raise LLMError("The AI service could not process this request.") from e
    return resp.choices[0].message.content or ""


def complete_json(system: str, user: str, images: list[bytes] | None = None) -> dict:
    """One call that returns a JSON object. The system prompt must describe the schema."""
    model = settings.groq_vision_model if images else settings.groq_text_model
    return json.loads(
        _chat(
            model=model,
            messages=_messages(system, user, images),
            response_format={"type": "json_object"},
            temperature=0,
        )
    )


def complete_text(system: str, user: str) -> str:
    return _chat(model=settings.groq_text_model, messages=_messages(system, user, None), temperature=0.2)
