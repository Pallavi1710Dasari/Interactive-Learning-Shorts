"""
Provider-agnostic image generation — RESTYLE_TO_STORY_REELS.md Step 3.

Turns one shot's prompt (+ optional reference images, e.g. character sheets,
for visual consistency across shots) into a rendered 1080x1920 PNG frame.
Every provider implements the SAME interface — ImageProvider.generate(prompt,
refs, size, seed) -> bytes — so swapping GEMINI_API_KEY for Cloudflare
credentials, or running under SHORTS_STUB=1, changes nothing about how a
caller uses this module: call render_frame(), get a Path back.

    render_frame(short_id="t_useState", shot_id="s0_reaction",
                 prompt="Rahul chalks a 5 on the whiteboard...")
    -> Path("output/t_useState/frames/shot_s0_reaction.png")

WHY A SEPARATE render_frame() ON TOP OF ImageProvider.generate(). The 4-arg
interface (prompt, refs, size, seed) is what every provider implements and
is deliberately minimal — it knows nothing about caching, per-reel budgets,
or where a frame lives on disk, the same way llm.ask_json() knows nothing
about which pipeline step is calling it. render_frame() is the orchestration
layer: cache lookup (never calls a provider on a hit), the
IMAGE_MAX_CALLS_PER_REEL guard, DRY_RUN_IMAGES, crop/resize to a uniform
size, usage.py logging, and the output path. One place for all of that
instead of every provider re-implementing it slightly differently.
"""
import base64
import hashlib
import json
import time
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from . import config, usage

FRAME_SIZE = (1080, 1920)

#: HTTP statuses worth retrying — the caller's own request was fine, the
#: service just needs a moment (rate limit) or is having a bad minute.
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3

#: RESTYLE_TO_STORY_REELS.md Step 9 Fixes round 10: a real run had shot 1
#: fail 3 SEPARATE times on the identical prompt, with 2 different error
#: shapes ("NSFW content" code 8007, then "no image in response" twice) —
#: neither is an HTTP-transient status _post_with_retry already covers (both
#: come back as a 200 with a refusal-shaped BODY, an application-level
#: refusal, not a network blip), so MAX_RETRIES/_post_with_retry never saw
#: them and generate_bytes() raised on the very first attempt. A refusal
#: like this is not necessarily deterministic — the same prompt sampled
#: again can succeed, the same way a flaky test sometimes passes on rerun —
#: so this is a SEPARATE, higher-level retry around the whole
#: provider.generate() call, independent of story_frames.py's own judge-
#: triggered regeneration (which re-prompts after a TECHNICALLY SUCCESSFUL
#: but low-quality image; this retries when the provider never returned an
#: image AT ALL). A flat short delay, not exponential backoff — this is not
#: rate-limiting, there is nothing to back off from, just a hope that
#: resampling the same prompt lands differently.
MAX_GENERATION_RETRIES = 3
GENERATION_RETRY_DELAY_SECONDS = 3.0


class ImageGenError(RuntimeError):
    """
    Raised for anything render_frame() will not silently paper over: a
    content-policy refusal, an empty response, a missing API key, or
    transient errors that outlasted every retry. Always carries the shot_id
    in its message (render_frame() adds it if the raising provider didn't)
    — Step 3's own "do not silently skip" rule. A caller building a whole
    reel's frames should let this propagate and stop the reel, not catch it
    per shot and continue with a hole in the sequence.
    """


class ImageProvider(ABC):
    """One real or fake image backend. `name` and `model` are what
    render_frame()'s cache key and usage.py's log line identify the call by."""
    name: str = "provider"
    model: str = ""

    @abstractmethod
    def generate(self, prompt: str, refs: list[Path] | None = None,
                size: tuple[int, int] = FRAME_SIZE, seed: int | None = None,
                shot_id: str = "") -> bytes:
        """
        Return raw image bytes — WHATEVER size/aspect the provider actually
        returned; render_frame() crops/resizes to `size` centrally, so a
        provider does not need to get that exactly right. Raise
        ImageGenError on refusal / empty response / exhausted retries.

        `shot_id` IS NOT PART OF THE CORE 4-ARG INTERFACE (prompt, refs,
        size, seed) real providers act on — Gemini/Cloudflare ignore it
        entirely, it plays no role in what image comes back. It exists only
        because StubImageProvider's own spec ("writes ... a PNG with the
        shot_id drawn on it") needs a label to draw, and giving every
        provider the same signature (rather than a stub-only special case in
        render_frame()) keeps the interface uniform. Defaults to "" so a
        caller that has no shot_id yet still gets a valid call.
        """


def _hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


class StubImageProvider(ImageProvider):
    """
    SHORTS_STUB=1's provider. No network, ever.

    DRAWN TO ACTUALLY PASS shorts/frame_checks.py's pre-checks (Step 6), not
    just to look different per shot — stubs.py's own module docstring rule
    ("a stub run should go green end to end; if it doesn't, the bug is in
    your code, not in a prompt") applies here too. A flat hash-derived
    colour (what this used to draw) is near-blank and off-palette by
    construction, which made check_not_blank/check_palette fail on every
    single stub frame — not a real defect, just a stub that couldn't have
    passed a check that didn't exist yet when it was written. So: BRAND.bg
    background, a black-outlined accent shape and the shot_id label, both
    kept inside the MIDDLE safe zone (never the top 12%/bottom 18% — see
    style.py's own composition rule) so check_safe_zones passes too. The
    shape/color are still derived from the prompt's hash, so two different
    prompts still render visibly differently for eyeballing a batch.
    """
    name = "stub"
    model = "stub"

    def generate(self, prompt, refs=None, size=FRAME_SIZE, seed=None, shot_id="") -> bytes:
        from . import config as _config
        w, h = size
        digest = hashlib.sha256(prompt.encode("utf-8")).digest()

        bg = _hex_to_rgb(_config.BRAND.bg)
        accent = _hex_to_rgb(_config.BRAND.accent_1 if digest[0] % 2 else _config.BRAND.accent_2)
        img = Image.new("RGB", size, bg)
        draw = ImageDraw.Draw(img)

        top = round(h * 0.12)
        bottom = h - round(h * 0.18)
        cx = w // 2 + (digest[1] % 41 - 20)   # a little horizontal jitter per prompt
        cy = (top + bottom) // 2
        r = min(w, bottom - top) // 5
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=accent, outline=(0, 0, 0), width=8)
        draw.rectangle([w * 0.15, top + (bottom - top) * 0.15,
                       w * 0.85, bottom - (bottom - top) * 0.15],
                      outline=(0, 0, 0), width=6)

        label = shot_id or "shot"
        try:
            font = ImageFont.load_default(size=48)
        except TypeError:
            # Older Pillow: load_default() takes no `size` kwarg.
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((w - tw) / 2, cy + r + 30), label, fill=(0, 0, 0), font=font)

        return _png_bytes(img)


def _png_bytes(img: Image.Image) -> bytes:
    import io
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


class _Transient(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body}")
        self.status = status


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    """
    POST with up to MAX_RETRIES retries, exponential backoff (1s, 2s, 4s),
    on a transient status (_TRANSIENT_STATUS) only — a 4xx that isn't 429
    (a bad request, a content-policy rejection surfaced as an HTTP error)
    is the CALLER's mistake or the model's refusal, not a blip, and is
    raised immediately rather than retried 3 times for nothing.
    """
    last: _Transient | None = None
    for attempt in range(MAX_RETRIES + 1):
        resp = requests.post(url, **kwargs)
        if resp.status_code not in _TRANSIENT_STATUS:
            return resp
        last = _Transient(resp.status_code, resp.text[:300])
        if attempt < MAX_RETRIES:
            time.sleep(2 ** attempt)
    raise ImageGenError(f"transient error after {MAX_RETRIES} retries: {last}")


class GeminiImageProvider(ImageProvider):
    """
    Google's Gemini image generation/editing API — the default provider,
    and the only one here that takes reference images alongside the prompt
    (story mode's fixed cast needs that for visual consistency — see
    config.CAST). Model id, request shape and pricing were confirmed
    against ai.google.dev's own docs on 2026-09-29, not recalled from
    memory — see config.IMAGE_MODEL's own note for the pages read.
    """
    name = "gemini"

    def __init__(self, model: str | None = None):
        #: `model` override exists for cast_sheets.py's --compare mode
        #: (Step 4 Part 4), which needs a second Gemini provider instance
        #: pointed at IMAGE_MODEL_LITE side by side with the default
        #: IMAGE_MODEL one. Every other caller leaves this None.
        self.model = model or config.IMAGE_MODEL
        if not config.GEMINI_API_KEY:
            raise ImageGenError(
                "GEMINI_API_KEY is missing from .env — required for "
                "IMAGE_PROVIDER=gemini. Set it, or switch IMAGE_PROVIDER to "
                "'cloudflare' or 'stub'.")

    def generate(self, prompt, refs=None, size=FRAME_SIZE, seed=None, shot_id="") -> bytes:
        parts = [{"text": prompt}]
        for ref in (refs or []):
            ref = Path(ref)
            mime = "image/png" if ref.suffix.lower() == ".png" else "image/jpeg"
            parts.append({"inlineData": {"mimeType": mime,
                                        "data": base64.b64encode(ref.read_bytes()).decode()}})

        generation_config = {
            "responseModalities": ["IMAGE"],
            # PORTRAIT_9x16 is the closest documented aspect enum to this
            # project's 1080x1920 frame; render_frame()'s own crop/resize
            # step is what actually guarantees the exact size regardless of
            # what the model returns, so an imprecise enum match here is not
            # load-bearing.
            "imageConfig": {"aspectRatio": "PORTRAIT_9x16", "imageSize": "1K"},
        }
        if seed is not None:
            # Best-effort: the docs read for this step did not confirm seed
            # support on the image-output path. Harmless to send — an
            # unrecognised field in generationConfig is ignored, not a
            # request-format error — and it is what the caller asked for.
            generation_config["seed"] = seed

        body = {"contents": [{"parts": parts}], "generationConfig": generation_config}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

        resp = _post_with_retry(
            url, headers={"x-goog-api-key": config.GEMINI_API_KEY,
                         "Content-Type": "application/json"},
            json=body, timeout=120)

        if resp.status_code >= 400:
            raise ImageGenError(f"gemini returned HTTP {resp.status_code}: "
                                f"{resp.text[:300]}")

        data = resp.json()
        for cand in data.get("candidates", []):
            for part in cand.get("content", {}).get("parts", []):
                inline = part.get("inlineData")
                if inline and inline.get("data"):
                    return base64.b64decode(inline["data"])

        reason = (data.get("promptFeedback", {}).get("blockReason")
                 or (data.get("candidates", [{}])[0].get("finishReason")
                     if data.get("candidates") else None)
                 or "no image in response")
        raise ImageGenError(f"gemini refused or returned no image: {reason}")


#: RESTYLE_TO_STORY_REELS.md Step 9 Fixes round 13: Cloudflare's OWN docs
#: page for this model (developers.cloudflare.com/workers-ai/models/
#: flux-1-schnell/, re-read 2026-09-30) LISTS `seed` as an accepted,
#: optional parameter ("used for reproducibility") — but a live,
#: reproducible test run directly against the REST endpoint this provider
#: actually calls (POST .../ai/run/{model}) proved the opposite: the
#: IDENTICAL prompt WITH `seed` in the body gets HTTP 400 ("Additional or
#: unevaluated properties '/seed' at '/' not allowed"), WITHOUT it gets
#: HTTP 200. The documentation and the live account-level REST API
#: disagree here (maybe a stale doc, maybe a binding-vs-REST-API
#: difference — the "why" doesn't change what to send). This allowlist is
#: therefore driven by the LIVE, REPRODUCIBLE result, not the vendor's own
#: docs, because that is what actually determines whether a real call
#: succeeds. Only `prompt` is confirmed-accepted; anything else this
#: provider might ever be asked to forward (seed today, conceivably
#: `steps` — also documented, never requested by any caller here — or
#: something else tomorrow) must be verified live the same way and added
#: here explicitly before it can reach the request body at all.
_CLOUDFLARE_ACCEPTED_FIELDS = {"prompt"}


class CloudflareImageProvider(ImageProvider):
    """
    Workers AI's flux-1-schnell — the FALLBACK provider (config.CF_IMAGE_MODEL's
    own note has the docs page read for this). No reference-image support:
    `refs` is accepted for interface uniformity and silently ignored, since
    this model has no documented image-input parameter to put them in.

    `seed` IS ALSO ACCEPTED-BUT-IGNORED — see _CLOUDFLARE_ACCEPTED_FIELDS's
    own note for why (a real retry, story_frames.py's own attempt-2-uses-
    seed=N rule, sent `{"prompt": ..., "seed": 2}` and Cloudflare rejected
    the WHOLE request with HTTP 400). Dropping it does NOT break retry-as-
    cache-miss — imagegen._cache_key still hashes `seed` regardless of what
    any given PROVIDER does with it (cast_sheets.py relies on exactly this
    for its own per-candidate seed=i — confirmed live: two identical-prompt
    Cloudflare calls with no seed at all still come back as two genuinely
    different images, this model's own internal sampling providing the
    variation instead) — so a retry, or a cast-sheet candidate, is still a
    fresh network call every time, it just can't ask Cloudflare for a
    SPECIFIC sample, only a fresh stochastic one, since this endpoint has
    no working seed control to ask for in the first place.
    """
    name = "cloudflare"

    def __init__(self):
        self.model = config.CF_IMAGE_MODEL
        if not (config.CF_ACCOUNT_ID and config.CF_API_TOKEN):
            raise ImageGenError(
                "CF_ACCOUNT_ID / CF_API_TOKEN are missing from .env — required for "
                "IMAGE_PROVIDER=cloudflare. Set both, or switch IMAGE_PROVIDER to "
                "'gemini' or 'stub'.")

    def generate(self, prompt, refs=None, size=FRAME_SIZE, seed=None, shot_id="") -> bytes:
        url = (f"https://api.cloudflare.com/client/v4/accounts/"
              f"{config.CF_ACCOUNT_ID}/ai/run/{self.model}")
        # EVERY field this call might conceivably send, filtered down to
        # only what _CLOUDFLARE_ACCEPTED_FIELDS confirms this endpoint
        # actually accepts — `seed` is a candidate here, not simply
        # omitted, so a future param addition goes through this SAME
        # filter rather than needing its own repeated guard.
        candidate_fields = {"prompt": prompt, "seed": seed}
        body = {k: v for k, v in candidate_fields.items()
               if v is not None and k in _CLOUDFLARE_ACCEPTED_FIELDS}

        resp = _post_with_retry(
            url, headers={"Authorization": f"Bearer {config.CF_API_TOKEN}"},
            json=body, timeout=120)

        if resp.status_code >= 400:
            raise ImageGenError(f"cloudflare returned HTTP {resp.status_code}: "
                                f"{resp.text[:300]}")

        content_type = resp.headers.get("content-type", "")
        if content_type.startswith("image/"):
            return resp.content

        # STEP 9 FIXES ROUND 11: a real, deterministic (not flaky) 3/3
        # "no image in response" failure on shot 1, reproduced by calling
        # this exact endpoint directly with the exact prompt OUTSIDE this
        # pipeline, turned out to be a genuine SUCCESS every time —
        # HTTP 200, content-type application/json, body
        # {"result": {"image": "<base64-encoded image bytes>"}}. This is
        # Workers AI's own documented default response shape (no Accept
        # header was ever sent to ask for raw bytes instead), which this
        # code never handled — every successful call that didn't happen
        # to come back with an image/* content-type was misread as a
        # refusal and raised as one, forever, no matter how many times it
        # was retried, because the bug was in this parsing, not in
        # anything Cloudflare rejected. The other shots in that same reel
        # never hit this because their identical prompts were already
        # cached from an earlier successful call — shot 1's prompt had
        # just changed (round 10's establishing-shot reword), which was
        # the ONLY reason it was forced to make a fresh network call and
        # expose this.
        try:
            data = resp.json()
        except ValueError:
            raise ImageGenError("cloudflare returned no image and an unparseable body")
        image_b64 = (data.get("result") or {}).get("image")
        if image_b64:
            return base64.b64decode(image_b64)

        # A GENUINE refusal/failure: {"success": false, "errors": [...]}.
        errors = data.get("errors") or [{"message": "no image in response"}]
        raise ImageGenError(f"cloudflare refused or returned no image: {errors}")


def select_provider() -> ImageProvider:
    if config.STUB or config.IMAGE_PROVIDER == "stub":
        return StubImageProvider()
    if config.IMAGE_PROVIDER == "gemini":
        return GeminiImageProvider()
    if config.IMAGE_PROVIDER == "cloudflare":
        return CloudflareImageProvider()
    raise ValueError(f"unknown IMAGE_PROVIDER {config.IMAGE_PROVIDER!r} — "
                     f"must be 'gemini', 'cloudflare', or 'stub'")


def _fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Centre-crop to `size`'s aspect ratio, then resize to `size` exactly —
    Step 3's own "if the model returns a different aspect/size" rule."""
    target_w, target_h = size
    target_ratio = target_w / target_h
    w, h = img.size
    ratio = w / h
    if ratio > target_ratio:
        new_w = round(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    elif ratio < target_ratio:
        new_h = round(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    if img.size != size:
        img = img.resize(size, Image.LANCZOS)
    return img


def _cache_key(provider: ImageProvider, prompt: str, refs: list[Path] | None,
              size: tuple[int, int], seed: int | None) -> str:
    """sha256(provider + model + prompt + ref file hashes + seed) — Step 3's
    own cache-key spec, verbatim."""
    h = hashlib.sha256()
    h.update(provider.name.encode())
    h.update(provider.model.encode())
    h.update(prompt.encode("utf-8"))
    for ref in (refs or []):
        h.update(hashlib.sha256(Path(ref).read_bytes()).digest())
    h.update(f"{size}".encode())
    h.update(str(seed).encode())
    return h.hexdigest()


#: REAL (non-cache-hit, non-dry-run) calls made so far, this process, per
#: short_id — the budget counter. In-memory only: the guard is against a
#: runaway loop WITHIN one run, not a budget that has to survive a restart,
#: and every real caller (run.py's per-topic loop) builds one reel's frames
#: in one process.
_call_counts: dict[str, int] = {}

#: Per-reel budget OVERRIDES, set by set_reel_budget() — RESTYLE_TO_STORY_
#: REELS.md Step 7 Part 0 #1's fix. A reel with no entry here falls back to
#: config.IMAGE_MAX_CALLS_PER_REEL (the flat default, or an explicit
#: env override — see that constant's own note on IMAGE_MAX_CALLS_PER_REEL_
#: IS_EXPLICIT). This module has no notion of "how many shots" a reel has,
#: so it cannot compute the per-reel default itself; story_frames.py does
#: (config.default_image_budget) and hands the result here.
_reel_budgets: dict[str, int] = {}


def set_reel_budget(reel_id: str, max_calls: int) -> None:
    """Override IMAGE_MAX_CALLS_PER_REEL for ONE reel — story_frames.py calls
    this once, before rendering, with config.default_image_budget()'s result
    (unless config.IMAGE_MAX_CALLS_PER_REEL_IS_EXPLICIT, in which case the
    flat env override is left in force instead — see that constant)."""
    _reel_budgets[reel_id] = max_calls


def _budget_for(reel_id: str) -> int:
    return _reel_budgets.get(reel_id, config.IMAGE_MAX_CALLS_PER_REEL)


def reset_call_count(short_id: str | None = None) -> None:
    """Testing hook — clears the per-reel call counter (and any budget
    override) so tests don't leak state into each other. `None` clears
    every reel."""
    if short_id is None:
        _call_counts.clear()
        _reel_budgets.clear()
    else:
        _call_counts.pop(short_id, None)
        _reel_budgets.pop(short_id, None)


def _cache_dir() -> Path:
    d = config.OUTPUT_DIR / ".image_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dry_run_prompts_path(short_id: str) -> Path:
    d = config.OUTPUT_DIR / short_id
    d.mkdir(parents=True, exist_ok=True)
    return d / "image_prompts.json"


def _frame_path(short_id: str, shot_id: str) -> Path:
    d = config.OUTPUT_DIR / short_id / "frames"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"shot_{shot_id}.png"


def estimate_cost(provider: ImageProvider) -> float:
    """
    What ONE real call against `provider` is expected to cost — the number
    cast_sheets.py prints before asking for --yes (Step 4 Part 3/4), and what
    generate_bytes() logs through usage.record_image. A cache hit or the
    stub provider cost exactly $0.0, not an estimate of it; this function is
    only about the price of a call that actually reaches a provider.
    """
    if isinstance(provider, StubImageProvider):
        return 0.0
    if provider.name == "gemini":
        return (config.IMAGE_LITE_COST_PER_CALL if provider.model == config.IMAGE_MODEL_LITE
               else config.IMAGE_COST_PER_CALL)
    if provider.name == "cloudflare":
        return config.CF_IMAGE_COST_PER_CALL
    return 0.0


def generate_bytes(reel_id: str, item_id: str, prompt: str,
                   refs: list[Path] | None = None,
                   size: tuple[int, int] = FRAME_SIZE,
                   seed: int | None = None,
                   provider: ImageProvider | None = None) -> bytes | None:
    """
    THE reusable core every caller goes through — provider-agnostic, cached,
    budgeted, retried, logged. Returns PNG bytes already cropped/resized to
    `size`, or None under DRY_RUN_IMAGES (nothing was generated; the caller
    decides what "dry run" means for its own output — render_frame() below
    writes a prompts.json entry keyed by shot_id, cast_sheets.py writes one
    keyed by character+candidate for its own --dry-run flag instead of using
    this one at all).

    `reel_id` is the IMAGE_MAX_CALLS_PER_REEL budget key and the cache
    namespace is NOT scoped by it — the cache key (provider+model+prompt+
    refs+seed) is content-addressed on purpose, so identical prompts from
    two different reels (or a reel and a cast sheet) still share one cache
    entry. `item_id` (a shot_id, or a character/candidate label) is used
    only in error messages and the usage.py label, never in the cache key or
    the budget check.

    `provider` is normally left None (config.IMAGE_PROVIDER decides); a
    caller passes one explicitly to reuse a single instance across many
    calls, to force a specific model (cast_sheets.py's --compare), or in a
    test that wants a specific fake.
    """
    provider = provider or select_provider()
    key = _cache_key(provider, prompt, refs, size, seed)
    cache_path = _cache_dir() / f"{key}.png"

    if cache_path.exists():
        usage.record_image(f"image:{provider.name}", provider.model, 0.0, estimated=False)
        return cache_path.read_bytes()

    if config.DRY_RUN_IMAGES:
        return None

    # RESTYLE_TO_STORY_REELS.md Step 9 Fixes round 10: each attempt below is
    # a REAL provider call (budgeted and logged individually, same as any
    # other call — see the module-level MAX_GENERATION_RETRIES note), so the
    # budget is checked and incremented ONCE PER ATTEMPT, not once up front —
    # a shot that needs 2 retries to succeed has genuinely spent 3 calls,
    # and a reel that is out of budget mid-retry stops cleanly on the next
    # attempt rather than silently going over.
    last_err: ImageGenError | None = None
    for attempt in range(1, MAX_GENERATION_RETRIES + 1):
        count = _call_counts.get(reel_id, 0)
        budget = _budget_for(reel_id)
        if count >= budget:
            raise ImageGenError(
                f"{item_id}: IMAGE_MAX_CALLS_PER_REEL ({budget}) exceeded for "
                f"{reel_id!r} — stopping rather than generating an unbounded "
                f"number of images")
        _call_counts[reel_id] = count + 1

        started = time.perf_counter()
        try:
            raw = provider.generate(prompt, refs=refs, size=size, seed=seed, shot_id=item_id)
            duration = time.perf_counter() - started
            break
        except ImageGenError as e:
            last_err = e
            if attempt < MAX_GENERATION_RETRIES:
                time.sleep(GENERATION_RETRY_DELAY_SECONDS)
    else:
        raise ImageGenError(
            f"{item_id}: {last_err} (after {MAX_GENERATION_RETRIES} attempts)") from last_err

    from io import BytesIO
    img = Image.open(BytesIO(raw)).convert("RGB")
    img = _fit(img, size)
    png = _png_bytes(img)
    cache_path.write_bytes(png)

    usage.record_image(f"image:{provider.name}", provider.model, estimate_cost(provider),
                       estimated=not isinstance(provider, StubImageProvider),
                       duration_seconds=duration)
    return png


def render_frame(short_id: str, shot_id: str, prompt: str,
                 refs: list[Path] | None = None,
                 size: tuple[int, int] = FRAME_SIZE,
                 seed: int | None = None,
                 provider: ImageProvider | None = None) -> Path:
    """
    THE entry point every REEL caller uses — a thin wrapper over
    generate_bytes() that owns the reel/shot output convention:
    output/<short_id>/frames/shot_<shot_id>.png. Returns that path (or,
    under DRY_RUN_IMAGES, the path the PNG WOULD BE saved at — nothing is
    written there; the caller checks .exists() to tell the difference, and
    this wrapper is what writes this reel's image_prompts.json instead).
    """
    out_path = _frame_path(short_id, shot_id)
    provider = provider or select_provider()
    png = generate_bytes(short_id, shot_id, prompt, refs=refs, size=size, seed=seed,
                         provider=provider)
    if png is None:
        _append_dry_run_prompt(short_id, shot_id, prompt, refs, seed)
        return out_path
    out_path.write_bytes(png)
    return out_path


def _append_dry_run_prompt(short_id: str, shot_id: str, prompt: str,
                           refs: list[Path] | None, seed: int | None) -> None:
    path = _dry_run_prompts_path(short_id)
    try:
        entries = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    except (json.JSONDecodeError, OSError):
        entries = []
    entries = [e for e in entries if e.get("shot_id") != shot_id]
    entries.append({
        "shot_id": shot_id,
        "prompt": prompt,
        "refs": [str(r) for r in (refs or [])],
        "seed": seed,
    })
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
