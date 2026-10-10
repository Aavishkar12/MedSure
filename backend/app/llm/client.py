"""Thin, text-only Groq wrapper. Everything provider-specific lives here."""

import json

from groq import APIError, Groq, RateLimitError

from ..config import settings

_client: Groq | None = None


def _groq() -> Groq:
    global _client
    if _client is None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def _messages(system: str, user: str) -> list[dict]:
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


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


def complete_json(system: str, user: str) -> dict:
    """One call that returns a JSON object. The system prompt must describe the schema."""
    return json.loads(
        _chat(
            model=settings.groq_text_model,
            messages=_messages(system, user),
            response_format={"type": "json_object"},
            temperature=0,
        )
    )


def complete_text(system: str, user: str) -> str:
    return _chat(model=settings.groq_text_model, messages=_messages(system, user), temperature=0.2)
