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

MODELS THAT CANNOT THINK "OFF". anthropic/claude-opus-5.5 through OpenRouter
answers thinking={"type":"disabled"} with a hard 400 ("Reasoning is mandatory
for this endpoint and cannot be disabled.") — the first real motion reel died
on its first call that way. A motion run therefore sets reasoning PER MODEL
from shorts/motion_models.yaml (set_model_reasoning(), via motion_models.use()):
on with an explicit budget, or off where the model allows it. The budget is
ADDED to the call's max_tokens, so thinking never eats the room the JSON needs.
Outside a motion run that map is empty and every request is exactly as before.

THINKING NEVER REACHES A PARSER. Only `text` blocks are read (thinking and
redacted_thinking blocks are skipped), and reasoning a gateway inlines into the
text as <thinking>/<think>/<reasoning> tags is stripped — visible_text().

REASONING CONTROL IS NOT PORTABLE — see _reasoning() below. "Thinking off" is an
Anthropic spelling, and two of the three families this project now runs on answer
it differently. Never hand-write thinking={...} at a call site; ask _reasoning().
"""
import base64, json, re, time
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
# gemini-2.5-pro is on this list and gemini-2.5-flash is NOT, which looks arbitrary
# and is not: asked to disable reasoning, pro answers with the same hard 400 as the
# gpt-5 family while flash accepts it. The docstring below used to say "google/*
# accepts disabling, and it matters" — measured on flash, generalised to the family,
# and wrong for pro. Every call to gemini-2.5-pro failed with
# "Reasoning is mandatory for this endpoint and cannot be disabled." until it was
# added here, which made the model look broken when it was the request that was.
_REASONING_MANDATORY = ("gpt-5", "o1", "o3", "o4")

#: Gemini's *-pro tiers refuse it too, and THE VERSION SEGMENT MOVES, which is why
#: this is a pattern and not two more strings in the tuple above. The tuple used to
#: carry "gemini-2.5-pro" and "gemini-3-pro" as literals, and setting
#: MODEL_DIAGRAM=google/gemini-3.1-pro-preview matched neither — "gemini-3-pro" is
#: not a substring of "gemini-3.1-pro-preview" — so every visual_spec call went out
#: asking to disable reasoning and came back 400 "Reasoning is mandatory for this
#: endpoint and cannot be disabled." The whole design step failed, and it read as a
#: broken model rather than as a stale string in this file.
#:
#: -pro is load-bearing: gemini flash ACCEPTS disabling and the saving is real
#: (38 output tokens against 194), so this must not widen to the whole family.
_REASONING_MANDATORY_RE = re.compile(r"gemini-\d+(?:\.\d+)*-pro")

# The floor to ask for when reasoning cannot be switched off. Measured on
# gpt-5-mini through OpenRouter, same trivial prompt: no thinking field at all
# spent 314 output tokens, an explicit small budget spent 200. Reasoning we are
# forced to buy should at least be bought in the smallest size sold.
MIN_REASONING_TOKENS = 1024


#: model -> {"thinking": "on"|"off", "budget": int}, set by motion_models.use()
#: for a motion run only (shorts/motion_models.yaml `reasoning`). Empty outside
#: one, so explainer and story requests are unchanged.
_MODEL_REASONING: dict[str, dict] = {}


def set_model_reasoning(mapping: dict[str, dict]) -> None:
    _MODEL_REASONING.clear()
    _MODEL_REASONING.update(mapping)


def thinking_budget(model: str) -> int:
    """Extra output tokens a configured model may spend thinking (0 if off or
    not configured). Added to max_tokens so the answer keeps its own room."""
    r = _MODEL_REASONING.get(model)
    return int(r["budget"]) if r and r.get("thinking") == "on" else 0


def _reasoning(model: str, think: bool) -> dict:
    """
    The reasoning kwargs for one model, given whether this call wants to deliberate.

    A model configured for this run (_MODEL_REASONING, a motion run) gets exactly
    its setting: thinking on with its budget, or off. Otherwise, as before:

    Three behaviours, discovered by asking the gateway rather than by reading docs:

      anthropic/*   thinking={"type":"disabled"} works and is the big win the module
                    docstring measures — 3.4x wall clock, 5x tokens.
      openai/gpt-5* REJECTS disabling with a 400. Reasoning is mandatory, so the
                    cheapest legal request is an explicit minimum budget.
      gemini flash  accepts disabling, and it matters: 38 output tokens disabled
                    against 194 with reasoning on, for the same one-line answer.
      gemini *-pro  REJECTS disabling, exactly like gpt-5. Same 400, same fix.

    think=True sends nothing and lets the provider deliberate as it sees fit, which
    is what the judge wants on every family.
    """
    configured = _MODEL_REASONING.get(model)
    if configured is not None:
        if configured.get("thinking") == "on":
            return {"thinking": {"type": "enabled", "budget_tokens": int(configured["budget"])}}
        return {"thinking": {"type": "disabled"}}
    if think:
        return {}
    if any(m in model for m in _REASONING_MANDATORY) \
            or _REASONING_MANDATORY_RE.search(model):
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


#: Families whose API accepts Anthropic-style prompt caching through this gateway.
#:
#: google/ is on this list because it was TESTED, not assumed. cache_control is an
#: Anthropic field, so the first cut of this restricted it to anthropic/* on the
#: reasoning that other providers would ignore or reject it — which would have made
#: "use Gemini for the frames" and "make it faster" mutually exclusive. Measured on
#: gemini-2.5-pro with the real 7k-token visual brief:
#:     call 1  7.80s  cache_write=6717
#:     call 2  2.76s  cache_read=6717      <- 65% faster
#: The gateway translates it. Anything not listed here still gets a plain string,
#: because a silently ignored cache is a saving we would only think we had made.
_CACHEABLE = ("anthropic/", "claude-", "google/")

#: Anthropic will not cache a block below ~1024 tokens, so asking for it on a short
#: system prompt spends a cache-write for nothing. Both briefs in this project are
#: far above the line — the visual one is ~7,200 tokens — but select.py and the
#: judge call with smaller ones.
MIN_CACHEABLE_CHARS = 4096


def _system(system: str, model: str):
    """
    The `system` argument, marked cacheable when that is worth doing.

    WHY THIS EXISTS. Nothing cached anything. The visual brief is 28,653 characters
    — roughly 7,200 tokens of fixed instructions — and it was re-sent, uncached, on
    every call: three times for a short whose frames needed two retries, on top of
    the section and the beats. The brief is byte-identical every time, which is
    exactly the case prompt caching is for, and it was being paid for in full in
    both latency and tokens on every attempt.

    This is the cheapest speed win available in the project and it costs nothing in
    quality, because the text sent is unchanged — only its cache marking differs.
    """
    if len(system) < MIN_CACHEABLE_CHARS or not any(m in model for m in _CACHEABLE):
        return system
    return [{"type": "text", "text": system,
             "cache_control": {"type": "ephemeral"}}]


#: The largest a rasterised frame is sent at. A 1080-square diagram is legible to a
#: vision model well below its native size, and every pixel is paid for on the way
#: in — see raster.PNG_WIDTH, which is where the downscale actually happens. This is
#: only the guard that stops an oversized PNG being sent by a careless caller.
MAX_IMAGE_BYTES = 4_000_000


def _content(user: str, images: list[bytes] | None):
    """The user turn, as a plain string or as image blocks followed by the text.

    IMAGES FIRST, TEXT LAST, which is not cosmetic: Anthropic's own guidance is that
    a question placed after the images it is about is answered more accurately than
    the same question placed before them. The vision judge asks the hardest question
    in this pipeline — "would a learner understand the concept from this picture
    alone" — so it gets the ordering that measures best.
    """
    if not images:
        return user
    blocks = []
    for img in images:
        if len(img) > MAX_IMAGE_BYTES:
            raise ValueError(f"image is {len(img)} bytes, over the {MAX_IMAGE_BYTES} cap "
                             f"— rasterise it smaller rather than sending it")
        blocks.append({"type": "image",
                       "source": {"type": "base64", "media_type": "image/png",
                                  "data": base64.b64encode(img).decode()}})
    return blocks + [{"type": "text", "text": user}]


def call(system: str, user: str, model: str | None = None, max_tokens: int = 4000,
         think: bool = False, label: str = "llm"):
    """One raw message call. Thinking off unless asked for — see module docstring."""
    model = model or config.MODEL_GENERATOR
    started = time.perf_counter()
    resp = client().messages.create(
        model=model, max_tokens=max_tokens + thinking_budget(model), system=_system(system, model),
        messages=[{"role": "user", "content": user}], **_reasoning(model, think),
    )
    usage.record(label, model, resp, duration_seconds=time.perf_counter() - started)
    return resp


#: Reasoning a gateway may inline into the text instead of sending as its own
#: block. Stripped whole, tags and contents.
_INLINE_REASONING = re.compile(r"<(thinking|think|reasoning)>.*?</\1>\s*", re.S | re.I)


def visible_text(resp) -> str:
    """The answer only: the `text` blocks, never thinking / redacted_thinking /
    reasoning blocks, with any inlined <thinking>…</thinking> removed."""
    text = "".join(getattr(b, "text", "") or "" for b in (resp.content or [])
                   if getattr(b, "type", None) == "text")
    return _INLINE_REASONING.sub("", text)


def text_of(resp) -> str:
    return visible_text(resp)


#: label -> model, set by motion_models.use() for a motion run only. A routed
#: label's model wins over the caller's default; anything not in the map keeps
#: its normal model, and the map is empty outside a motion run.
_LABEL_MODELS: dict[str, str] = {}


class UnroutedLabel(RuntimeError):
    """A motion-run call whose label has no route in motion_models.yaml."""


def set_label_models(mapping: dict[str, str]) -> None:
    _LABEL_MODELS.clear()
    _LABEL_MODELS.update({k: v for k, v in mapping.items() if v})


def ask_json(
    system: str,
    user: str,
    model_cls: Type[T],
    model: str | None = None,
    max_tokens: int = 4000,
    retries: int = 2,
    label: str = "llm",
    think: bool = False,
    images: list[bytes] | None = None,
) -> T:
    """
    Call the model, parse JSON, validate against a pydantic class.

    On a validation error it retries and shows the model its own mistake — which
    fixes malformed output far more often than a blind retry.

    `images` makes the call MULTIMODAL — PNG bytes, sent ahead of the text. This is
    the whole mechanism behind the educational vision judge: every other step in
    this pipeline grades a diagram by reading the JSON it was built from, which
    cannot see that a frame is legible-but-meaningless. Looking at the rendered
    pixels is the only way to ask "would a learner understand this picture", and
    that question is the one the visuals were failing.

    An EMPTY response is handled separately from an invalid one. Showing the model
    an empty assistant turn and asking it to "fix the JSON" teaches it nothing and
    burns the remaining attempts on the same truncation; the budget is what was
    wrong, so the budget is what changes.
    """
    if _LABEL_MODELS and label not in _LABEL_MODELS:
        # a motion run routes EVERY call; an unrouted label would silently use
        # config.py's model (the first real reel's `screen` ran on claude-sonnet-5)
        raise UnroutedLabel(f"motion run: LLM call {label!r} is not routed — add it to "
                            f"shorts/motion_models.yaml `steps` (nothing was sent)")
    if config.STUB:
        from .stubs import fake
        return fake(model_cls, system, user)

    model = _LABEL_MODELS.get(label) or model or config.MODEL_GENERATOR
    system = system + "\n\nReturn ONLY raw JSON. No prose, no markdown fences."
    content = _content(user, images)
    messages = [{"role": "user", "content": content}]
    budget = max_tokens
    last_err = None

    for attempt in range(retries + 1):
        started = time.perf_counter()
        resp = client().messages.create(
            model=model, max_tokens=budget + thinking_budget(model), system=_system(system, model),
            messages=messages,
            **_reasoning(model, think),
        )
        usage.record(label, model, resp, duration_seconds=time.perf_counter() - started)
        raw = visible_text(resp)

        if not raw.strip():
            # No text at all. Either the budget went entirely on thinking tokens or
            # the gateway returned an empty completion. Both are retried on a
            # bigger budget with the original prompt, not on a corrective turn.
            last_err = ValueError(
                f"empty response (stop_reason={resp.stop_reason}, "
                f"output_tokens={resp.usage.output_tokens}, budget={budget})")
            budget = min(budget * 2, 16000)
            messages = [{"role": "user", "content": content}]
            time.sleep(1)
            continue

        try:
            parsed = json.loads(_extract_json(raw))
            # A BARE LIST WHERE AN OBJECT WAS ASKED FOR. gemini-2.5-pro returned
            # `[{...}, {...}]` for VisualPlan instead of `{"visuals": [...]}`, and
            # `model_cls(**parsed)` then died with "argument after ** must be a
            # mapping" — a TypeError, not a ValidationError, so the retry-with-your-
            # own-mistake path below never ran and the whole design was lost.
            # The wrapper is unambiguous whenever the model has exactly one list
            # field, which is the shape every plan class here has.
            if isinstance(parsed, list):
                fields = [n for n, f in model_cls.model_fields.items()
                          if getattr(f.annotation, "__origin__", None) is list]
                if len(fields) == 1:
                    parsed = {fields[0]: parsed}
            return model_cls(**parsed)
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = e
            if resp.stop_reason == "max_tokens":
                budget = min(budget * 2, 16000)      # truncated mid-JSON
            messages = [
                {"role": "user", "content": content},
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content":
                    f"That failed validation:\n\n{e}\n\nReturn corrected JSON only."},
            ]
            time.sleep(1)

    raise RuntimeError(f"model produced invalid JSON after {retries + 1} attempts: {last_err}")
