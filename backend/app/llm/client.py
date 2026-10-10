"""Thin Groq wrapper. Everything provider-specific lives in this file."""

import base64
import json
import logging
import time
from pathlib import Path

from groq import APIConnectionError, APIError, AuthenticationError, Groq, RateLimitError

from ..config import settings

logger = logging.getLogger("medsure.llm")

# Groq caps images per request; keep discharge packs short or split by page.
MAX_IMAGES = 5

_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        if not settings.groq_api_key or not settings.groq_api_key.strip():
            raise LLMError("AI service is not configured. Please set GROQ_API_KEY on the server.")
        _client = Groq(api_key=settings.groq_api_key.strip())
    return _client


def file_to_text(path: str) -> str:
    """Text layer of a typed PDF with [Page N] markers. Empty for scans and images."""
    p = Path(path)
    if not p.exists() or p.suffix.lower() != ".pdf":
        return ""
    try:
        import pymupdf

        with pymupdf.open(p) as pdf:
            pages = [(i, page.get_text().strip()) for i, page in enumerate(pdf, start=1)]
        return "\n\n".join(f"[Page {i}]\n{text}" for i, text in pages if text)
    except Exception as e:
        logger.warning(f"Failed to read PDF text from {path}: {e}")
        return ""


def file_to_images(path: str) -> list[bytes]:
    """Return JPEG bytes per page. PDFs are rendered; images pass through."""
    p = Path(path)
    if not p.exists():
        return []
    if p.suffix.lower() != ".pdf":
        try:
            return [p.read_bytes()]
        except Exception as e:
            logger.warning(f"Failed to read image bytes from {path}: {e}")
            return []
    try:
        import pymupdf

        with pymupdf.open(p) as pdf:
            return [page.get_pixmap(dpi=110).tobytes("jpeg") for page in pdf][:MAX_IMAGES]
    except Exception as e:
        logger.warning(f"Failed to render PDF to images from {path}: {e}")
        return []


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


def _clean_json_markdown(text: str) -> str:
    """Strip markdown code fence if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


# Groq's free tier allows a few thousand tokens a minute, which three documents in a row exceed.
# Documents are read in the background, so waiting for the limit to reset is better than failing.
RATE_LIMIT_ATTEMPTS = 5
RATE_LIMIT_MAX_WAIT = 30.0


def _retry_after(error: RateLimitError) -> float:
    """Seconds Groq asks us to wait, from the retry-after header."""
    try:
        seconds = float(error.response.headers.get("retry-after", ""))
    except (AttributeError, TypeError, ValueError):
        seconds = 5.0
    return min(max(seconds, 1.0), RATE_LIMIT_MAX_WAIT)


def _chat(**kwargs) -> str:
    if kwargs.get("model", "").startswith("openai/gpt-oss"):  # reasoning models; keep them quick
        kwargs["reasoning_effort"] = "low"
    for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
        try:
            return _chat_once(**kwargs)
        except RateLimitError as e:
            if attempt == RATE_LIMIT_ATTEMPTS:
                logger.warning(f"Groq rate limit, giving up after {attempt} attempts: {e}")
                raise LLMError("The AI service is busy right now. Please try again in a minute.") from e
            wait = _retry_after(e)
            logger.info(f"Groq rate limit; waiting {wait:.0f}s (attempt {attempt} of {RATE_LIMIT_ATTEMPTS})")
            time.sleep(wait)
    raise LLMError("The AI service is busy right now. Please try again in a minute.")  # not reached


def _chat_once(**kwargs) -> str:
    try:
        resp = _groq().chat.completions.create(**kwargs)
        return resp.choices[0].message.content or ""
    except RateLimitError:
        raise  # _chat waits and retries
    except AuthenticationError as e:
        logger.error(f"Groq authentication error: {e}")
        raise LLMError("AI service authentication failed. Please check the backend GROQ_API_KEY configuration.") from e
    except APIConnectionError as e:
        logger.error(f"Groq connection error: {e}")
        raise LLMError("Could not connect to the AI service. Please check network connectivity.") from e
    except APIError as e:
        logger.error(f"Groq API error: {e}")
        raise LLMError("The AI service could not process this request.") from e
    except Exception as e:
        if isinstance(e, LLMError):
            raise
        logger.exception("Unexpected error in Groq chat completion")
        raise LLMError("An unexpected error occurred while communicating with the AI service.") from e


def complete_json(system: str, user: str, images: list[bytes] | None = None) -> dict:
    """One call that returns a JSON object. The system prompt must describe the schema."""
    model = settings.groq_vision_model if images else settings.groq_text_model
    raw = _chat(
        model=model,
        messages=_messages(system, user, images),
        response_format={"type": "json_object"},
        temperature=0,
    )
    cleaned = _clean_json_markdown(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse model JSON: {raw[:500]}")
        raise LLMError("AI service returned a malformed response.") from e


def complete_text(system: str, user: str) -> str:
    return _chat(model=settings.groq_text_model, messages=_messages(system, user, None), temperature=0.2)
