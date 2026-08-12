"""
The only place that talks to the LLM. One function, JSON in, validated model out.

Two things worth knowing about Sonnet 5 and newer:
  - Adaptive thinking is on by default. Do NOT pass temperature/top_p — they are
    rejected. Use `effort` (low/medium/high/xhigh/max) if you need control.
  - Ask for raw JSON in the system prompt and strip fences defensively anyway.
"""
import json, re, time
from typing import TypeVar, Type
from pydantic import BaseModel, ValidationError
import anthropic

from . import config, usage

T = TypeVar("T", bound=BaseModel)

_client = None
def client() -> anthropic.Anthropic:
    """
    One client, built for whichever endpoint the key belongs to.

    A first-party Anthropic key (sk-ant-...) authenticates with x-api-key. A
    gateway like OpenRouter wants the same key as `Authorization: Bearer`, which
    is what the SDK's auth_token argument sends. Passing both makes the API
    reject the request, so it is strictly one or the other.
    """
    global _client
    if _client is None:
        key = config.ANTHROPIC_API_KEY
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY missing — copy .env.example to .env")

        if config.ANTHROPIC_BASE_URL:
            _client = anthropic.Anthropic(auth_token=key, base_url=config.ANTHROPIC_BASE_URL)
        else:
            _client = anthropic.Anthropic(api_key=key)
    return _client


def _extract_json(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, re.S)
    if fenced:
        text = fenced.group(1).strip()
    start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    if start == -1:
        raise ValueError(f"no JSON found in model output: {text[:200]}")
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start:end + 1]


def ask_json(
    system: str,
    user: str,
    model_cls: Type[T],
    model: str | None = None,
    max_tokens: int = 4000,
    retries: int = 2,
    label: str = "llm",
) -> T:
    """
    Call the model, parse JSON, validate against a pydantic class.

    On a validation error it retries and shows the model its own mistake — which
    fixes malformed output far more often than a blind retry.
    """
    if config.STUB:
        from .stubs import fake
        return fake(model_cls, system, user)

    model = model or config.MODEL_GENERATOR
    messages = [{"role": "user", "content": user}]
    last_err = None

    for attempt in range(retries + 1):
        resp = client().messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system + "\n\nReturn ONLY raw JSON. No prose, no markdown fences.",
            messages=messages,
        )
        usage.record(label, model, resp)
        raw = "".join(b.text for b in resp.content if b.type == "text")
        try:
            return model_cls(**json.loads(_extract_json(raw)))
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = e
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content":
                    f"That failed validation:\n\n{e}\n\nReturn corrected JSON only."},
            ]
            time.sleep(1)

    raise RuntimeError(f"model produced invalid JSON after {retries + 1} attempts: {last_err}")
