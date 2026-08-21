"""
The only place that talks to the LLM. One function, JSON in, validated model out.

Two things worth knowing about Sonnet 5 and newer:
  - Adaptive thinking is on by default. Do NOT pass temperature/top_p — they are
    rejected. Pass thinking={"type":"disabled"} to turn it off.
  - Ask for raw JSON in the system prompt and strip fences defensively anyway.

WHY THINKING IS OFF BY DEFAULT HERE
Measured on the real script prompt, same model, same input:

    thinking on   30.5s   2734 output tokens
    thinking off   8.9s    544 output tokens

Same schema, same graders passing. Adaptive thinking is worth paying for when the
model has to reason its way to an answer; filling in a fixed JSON shape from a
source section is not that task, and it was costing 3.4x the wall clock and 5x
the tokens for output the graders scored no better.

It was also the cause of a 500. Thinking tokens are drawn from max_tokens, so a
long deliberation on a 2000-token budget spent the whole allowance before the
text block began — leaving stop_reason="max_tokens" and an EMPTY text block. That
surfaced as "no JSON found in model output:" with nothing after the colon, which
is what took down /api/scripts. Both halves are fixed: thinking is off, and an
empty response is now retried on a bigger budget instead of being fed back to
the model as an empty assistant turn.

Pass think=True on a call that genuinely needs deliberation (the judge does).

REASONING CONTROL IS NOT PORTABLE — see _reasoning() below. "Thinking off" is an
Anthropic spelling, and two of the three families this project now runs on answer
it differently. Never hand-write thinking={...} at a call site; ask _reasoning().
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


# Families that refuse to have reasoning turned off. OpenRouter answers
# thinking={"type":"disabled"} for these with a hard 400:
#     "Reasoning is mandatory for this endpoint and cannot be disabled."
# Matched on the model string because the gateway prefixes it ("openai/gpt-5-mini").
_REASONING_MANDATORY = ("gpt-5", "o1", "o3", "o4")

# The floor to ask for when reasoning cannot be switched off. Measured on
# gpt-5-mini through OpenRouter, same trivial prompt: no thinking field at all
# spent 314 output tokens, an explicit small budget spent 200. Reasoning we are
# forced to buy should at least be bought in the smallest size sold.
MIN_REASONING_TOKENS = 1024


def _reasoning(model: str, think: bool) -> dict:
    """
    The reasoning kwargs for one model, given whether this call wants to deliberate.

    Three behaviours, discovered by asking the gateway rather than by reading docs:

      anthropic/*   thinking={"type":"disabled"} works and is the big win the module
                    docstring measures — 3.4x wall clock, 5x tokens.
      openai/gpt-5* REJECTS disabling with a 400. Reasoning is mandatory, so the
                    cheapest legal request is an explicit minimum budget.
      google/*      accepts disabling, and it matters: 38 output tokens disabled
                    against 194 with reasoning on, for the same one-line answer.

    think=True sends nothing and lets the provider deliberate as it sees fit, which
    is what the judge wants on every family.
    """
    if think:
        return {}
    if any(m in model for m in _REASONING_MANDATORY):
        return {"thinking": {"type": "enabled", "budget_tokens": MIN_REASONING_TOKENS}}
    return {"thinking": {"type": "disabled"}}


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


def call(system: str, user: str, model: str | None = None, max_tokens: int = 4000,
         think: bool = False, label: str = "llm"):
    """One raw message call. Thinking off unless asked for — see module docstring."""
    model = model or config.MODEL_GENERATOR
    resp = client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user}], **_reasoning(model, think),
    )
    usage.record(label, model, resp)
    return resp


def text_of(resp) -> str:
    return "".join(b.text for b in resp.content if b.type == "text")


def ask_json(
    system: str,
    user: str,
    model_cls: Type[T],
    model: str | None = None,
    max_tokens: int = 4000,
    retries: int = 2,
    label: str = "llm",
    think: bool = False,
) -> T:
    """
    Call the model, parse JSON, validate against a pydantic class.

    On a validation error it retries and shows the model its own mistake — which
    fixes malformed output far more often than a blind retry.

    An EMPTY response is handled separately from an invalid one. Showing the model
    an empty assistant turn and asking it to "fix the JSON" teaches it nothing and
    burns the remaining attempts on the same truncation; the budget is what was
    wrong, so the budget is what changes.
    """
    if config.STUB:
        from .stubs import fake
        return fake(model_cls, system, user)

    model = model or config.MODEL_GENERATOR
    system = system + "\n\nReturn ONLY raw JSON. No prose, no markdown fences."
    messages = [{"role": "user", "content": user}]
    budget = max_tokens
    last_err = None

    for attempt in range(retries + 1):
        resp = client().messages.create(
            model=model, max_tokens=budget, system=system, messages=messages,
            **_reasoning(model, think),
        )
        usage.record(label, model, resp)
        raw = "".join(b.text for b in resp.content if b.type == "text")

        if not raw.strip():
            # No text at all. Either the budget went entirely on thinking tokens or
            # the gateway returned an empty completion. Both are retried on a
            # bigger budget with the original prompt, not on a corrective turn.
            last_err = ValueError(
                f"empty response (stop_reason={resp.stop_reason}, "
                f"output_tokens={resp.usage.output_tokens}, budget={budget})")
            budget = min(budget * 2, 16000)
            messages = [{"role": "user", "content": user}]
            time.sleep(1)
            continue

        try:
            return model_cls(**json.loads(_extract_json(raw)))
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = e
            if resp.stop_reason == "max_tokens":
                budget = min(budget * 2, 16000)      # truncated mid-JSON
            messages = [
                {"role": "user", "content": user},
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content":
                    f"That failed validation:\n\n{e}\n\nReturn corrected JSON only."},
            ]
            time.sleep(1)

    raise RuntimeError(f"model produced invalid JSON after {retries + 1} attempts: {last_err}")
