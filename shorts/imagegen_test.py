"""
RESTYLE_TO_STORY_REELS.md Step 3 Part 1: unit tests for shorts/imagegen.py.

No API key, no network, no real provider calls — Gemini/Cloudflare providers
are exercised via a fake `requests.post` (monkeypatched), and every "does it
work at all" test uses StubImageProvider. Zero cost, same as every other
*_test.py in this project.

    SHORTS_STUB=1 python -m shorts.imagegen_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import io
import json
import tempfile
import uuid
from pathlib import Path

from PIL import Image

from shorts import config, imagegen, usage


def _tmp_ref_png(tag: str = "ref") -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / f"{tag}.png"
    Image.new("RGB", (200, 300), (10, 20, 30)).save(p)
    return p


def _fresh_reel_id(name: str) -> str:
    """A short_id namespaced per test, and its output/ dirs cleaned first,
    so tests don't see each other's cached frames or leftover state."""
    imagegen.reset_call_count(name)
    for sub in ("frames",):
        d = config.OUTPUT_DIR / name / sub
        if d.exists():
            for f in d.glob("*"):
                f.unlink()
    prompts_path = config.OUTPUT_DIR / name / "image_prompts.json"
    prompts_path.unlink(missing_ok=True)
    return name


# ============================================================ 1. stub provider

def test_stub_provider_writes_a_1080x1920_png():
    short_id = _fresh_reel_id("t_stub_basic")
    path = imagegen.render_frame(short_id, "s0", "Rahul writes on the whiteboard")
    assert path.exists()
    assert path == config.OUTPUT_DIR / short_id / "frames" / "shot_s0.png"
    img = Image.open(path)
    assert img.size == (1080, 1920)
    print(f"   ok — StubImageProvider writes a real 1080x1920 PNG at {path}")


def test_stub_provider_draws_the_shot_id():
    """
    Can't OCR the PNG in a unit test, so this checks what we CAN check
    mechanically: two different shot_ids for the SAME prompt produce two
    DIFFERENT raw images from StubImageProvider.generate() (the shot_id text
    is actually part of the pixels).

    Calls StubImageProvider directly, NOT through render_frame() — the cache
    key is sha256(provider + model + prompt + ref hashes + seed), Step 3's
    own spec, deliberately WITHOUT shot_id (two shots that end up with the
    identical prompt/refs/seed against a REAL provider really do produce the
    same image, and reusing the cached one is the whole point of caching by
    content). Going through render_frame() here would hit that same cache
    entry twice and correctly return identical bytes; that would be a cache
    bug if it were checking render_frame's behavior, not this one.
    """
    provider = imagegen.StubImageProvider()
    raw1 = provider.generate("the same prompt text", shot_id="alpha")
    raw2 = provider.generate("the same prompt text", shot_id="beta")
    assert raw1 != raw2
    print("   ok — StubImageProvider.generate()'s output differs by shot_id "
          "even when the prompt is identical (the shot_id is drawn into the "
          "pixels) — checked directly, not through render_frame()'s cache, "
          "since shot_id is deliberately not part of the cache key")


# =============================================================== 2. caching

def test_cache_hit_never_calls_the_provider():
    calls = []

    class CountingStub(imagegen.StubImageProvider):
        def generate(self, *a, **kw):
            calls.append(1)
            return super().generate(*a, **kw)

    short_id = _fresh_reel_id("t_cache_hit")
    provider = CountingStub()
    prompt = f"cacheable prompt {uuid.uuid4().hex}"
    p1 = imagegen.render_frame(short_id, "s0", prompt, provider=provider)
    assert len(calls) == 1
    p2 = imagegen.render_frame(short_id, "s0", prompt, provider=provider)
    assert len(calls) == 1, "a second identical call must be a cache hit, not a 2nd call"
    assert Path(p1).read_bytes() == Path(p2).read_bytes()
    print("   ok — an identical (provider, model, prompt, refs, seed) call "
          "is served from output/.image_cache/ and never reaches the "
          "provider a second time")


def test_different_prompt_is_a_cache_miss():
    calls = []

    class CountingStub(imagegen.StubImageProvider):
        def generate(self, *a, **kw):
            calls.append(1)
            return super().generate(*a, **kw)

    short_id = _fresh_reel_id("t_cache_miss")
    provider = CountingStub()
    tag = uuid.uuid4().hex
    imagegen.render_frame(short_id, "s0", f"prompt A {tag}", provider=provider)
    imagegen.render_frame(short_id, "s1", f"prompt B {tag}", provider=provider)
    assert len(calls) == 2
    print("   ok — a different prompt is a cache miss and does call the provider")


# ========================================================== 3. crop/resize

def test_crop_and_resize_produces_exactly_1080x1920():
    for src_size in [(1024, 1024), (1920, 1080), (500, 2000), (1080, 1920)]:
        img = Image.new("RGB", src_size, (1, 2, 3))
        fitted = imagegen._fit(img, imagegen.FRAME_SIZE)
        assert fitted.size == (1080, 1920), (src_size, fitted.size)
    print("   ok — _fit() centre-crops/resizes a square, landscape, tall, "
          "and already-correct source image to exactly 1080x1920 in every case")


# ================================================ 4. IMAGE_MAX_CALLS_PER_REEL

def test_image_max_calls_per_reel_is_enforced():
    short_id = _fresh_reel_id("t_budget")
    original = config.IMAGE_MAX_CALLS_PER_REEL
    config.IMAGE_MAX_CALLS_PER_REEL = 2
    tag = uuid.uuid4().hex
    try:
        imagegen.render_frame(short_id, "s0", f"prompt 0 {tag}")
        imagegen.render_frame(short_id, "s1", f"prompt 1 {tag}")
        try:
            imagegen.render_frame(short_id, "s2", f"prompt 2 {tag}")
            assert False, "expected ImageGenError once the budget is exceeded"
        except imagegen.ImageGenError as e:
            assert "IMAGE_MAX_CALLS_PER_REEL" in str(e)
            assert "s2" in str(e)
            print(f"   ok — the 3rd real call for one reel raises and stops "
                 f"the reel once IMAGE_MAX_CALLS_PER_REEL is exceeded: {e}")
    finally:
        config.IMAGE_MAX_CALLS_PER_REEL = original


def test_cache_hits_do_not_count_against_the_budget():
    short_id = _fresh_reel_id("t_budget_cache")
    original = config.IMAGE_MAX_CALLS_PER_REEL
    config.IMAGE_MAX_CALLS_PER_REEL = 1
    try:
        prompt = f"same prompt {uuid.uuid4().hex}"
        imagegen.render_frame(short_id, "s0", prompt)
        # Same (short_id irrelevant to the key) prompt/provider/model/seed —
        # a cache hit, must not consume the 1-call budget a 2nd time.
        imagegen.render_frame(short_id, "s0", prompt)
        print("   ok — a cache hit does not count against "
              "IMAGE_MAX_CALLS_PER_REEL")
    finally:
        config.IMAGE_MAX_CALLS_PER_REEL = original


# ===================================================== 5. DRY_RUN_IMAGES

def test_dry_run_writes_prompts_json_and_calls_no_provider():
    calls = []

    class CountingStub(imagegen.StubImageProvider):
        def generate(self, *a, **kw):
            calls.append(1)
            return super().generate(*a, **kw)

    short_id = _fresh_reel_id("t_dry_run")
    original = config.DRY_RUN_IMAGES
    config.DRY_RUN_IMAGES = True
    try:
        p1 = imagegen.render_frame(short_id, "s0", "dry run prompt one",
                                   provider=CountingStub())
        p2 = imagegen.render_frame(short_id, "s1", "dry run prompt two",
                                   provider=CountingStub(), seed=7)
    finally:
        config.DRY_RUN_IMAGES = original

    assert len(calls) == 0, "DRY_RUN_IMAGES must never call a provider"
    assert not p1.exists() and not p2.exists(), "no PNG should be written under dry-run"

    prompts_path = config.OUTPUT_DIR / short_id / "image_prompts.json"
    assert prompts_path.exists()
    entries = json.loads(prompts_path.read_text(encoding="utf-8"))
    by_shot = {e["shot_id"]: e for e in entries}
    assert by_shot["s0"]["prompt"] == "dry run prompt one"
    assert by_shot["s1"]["prompt"] == "dry run prompt two"
    assert by_shot["s1"]["seed"] == 7
    print(f"   ok — DRY_RUN_IMAGES writes every shot's prompt to {prompts_path} "
         f"and calls zero providers")


# ======================================== 6. missing credentials / provider errors

def test_missing_gemini_api_key_fails_with_a_clear_message():
    original = config.GEMINI_API_KEY
    config.GEMINI_API_KEY = ""
    try:
        try:
            imagegen.GeminiImageProvider()
            assert False, "expected ImageGenError"
        except imagegen.ImageGenError as e:
            assert "GEMINI_API_KEY" in str(e)
            print(f"   ok — GeminiImageProvider() with no GEMINI_API_KEY fails "
                 f"immediately with a clear, actionable message: {e}")
    finally:
        config.GEMINI_API_KEY = original


def test_missing_cloudflare_credentials_fails_with_a_clear_message():
    orig_id, orig_token = config.CF_ACCOUNT_ID, config.CF_API_TOKEN
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""
    try:
        try:
            imagegen.CloudflareImageProvider()
            assert False, "expected ImageGenError"
        except imagegen.ImageGenError as e:
            assert "CF_ACCOUNT_ID" in str(e)
            print(f"   ok — CloudflareImageProvider() with no credentials fails "
                 f"with a clear message: {e}")
    finally:
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = orig_id, orig_token


def test_api_key_never_appears_in_error_messages():
    config.GEMINI_API_KEY = "sk-super-secret-value-should-never-leak"
    try:
        provider = imagegen.GeminiImageProvider()
        try:
            # No network reachable to a bogus host — this raises, and the
            # error text must not contain the key either way.
            provider.generate("prompt", refs=None, size=(1080, 1920), seed=None)
        except Exception as e:
            assert "sk-super-secret-value-should-never-leak" not in str(e)
            print("   ok — the API key never appears in a raised error's message")
    finally:
        config.GEMINI_API_KEY = ""


class _FakeResponse:
    def __init__(self, status_code, json_body=None, text="", headers=None, content=b""):
        self.status_code = status_code
        self._json = json_body
        self.text = text
        self.headers = headers or {}
        self.content = content

    def json(self):
        if self._json is None:
            raise ValueError("no json body")
        return self._json


def test_retry_and_backoff_on_mocked_429_then_succeeds():
    import shorts.imagegen as ig
    calls = {"n": 0}
    sleeps = []

    def fake_post(url, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return _FakeResponse(429, text="rate limited")
        image_b64 = __import__("base64").b64encode(b"\x89PNG-not-real-but-nonempty").decode()
        return _FakeResponse(200, json_body={
            "candidates": [{"content": {"parts": [
                {"inlineData": {"mimeType": "image/png", "data": image_b64}}]}}]})

    original_post, original_sleep = ig.requests.post, ig.time.sleep
    ig.requests.post = fake_post
    ig.time.sleep = lambda s: sleeps.append(s)
    config.GEMINI_API_KEY = "fake-key-for-this-test"
    try:
        provider = ig.GeminiImageProvider()
        raw = provider.generate("a prompt", refs=None, size=(1080, 1920), seed=None)
        assert raw == b"\x89PNG-not-real-but-nonempty"
        assert calls["n"] == 3, calls
        assert len(sleeps) == 2, sleeps   # backed off twice, then succeeded
        print(f"   ok — 2 mocked HTTP 429s are retried with backoff "
             f"({sleeps}) before the 3rd attempt succeeds")
    finally:
        ig.requests.post = original_post
        ig.time.sleep = original_sleep
        config.GEMINI_API_KEY = ""


def test_clear_error_on_mocked_content_policy_refusal():
    import shorts.imagegen as ig

    def fake_post(url, **kwargs):
        return _FakeResponse(200, json_body={
            "candidates": [],
            "promptFeedback": {"blockReason": "SAFETY"},
        })

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.GEMINI_API_KEY = "fake-key-for-this-test"
    try:
        provider = ig.GeminiImageProvider()
        try:
            provider.generate("a prompt", refs=None, size=(1080, 1920), seed=None)
            assert False, "expected ImageGenError on a refusal"
        except ig.ImageGenError as e:
            assert "SAFETY" in str(e)
            print(f"   ok — a content-policy refusal (blockReason, no image) "
                 f"raises a clear ImageGenError, not a silent skip: {e}")
    finally:
        ig.requests.post = original_post
        config.GEMINI_API_KEY = ""


def test_retries_exhausted_raises_after_max_retries():
    import shorts.imagegen as ig
    calls = {"n": 0}

    def fake_post(url, **kwargs):
        calls["n"] += 1
        return _FakeResponse(503, text="down for maintenance")

    original_post, original_sleep = ig.requests.post, ig.time.sleep
    ig.requests.post = fake_post
    ig.time.sleep = lambda s: None
    config.GEMINI_API_KEY = "fake-key-for-this-test"
    try:
        provider = ig.GeminiImageProvider()
        try:
            provider.generate("a prompt", refs=None, size=(1080, 1920), seed=None)
            assert False, "expected ImageGenError once retries are exhausted"
        except ig.ImageGenError as e:
            assert calls["n"] == ig.MAX_RETRIES + 1, calls
            print(f"   ok — a persistent 503 is retried {ig.MAX_RETRIES} times "
                 f"then raises: {e}")
    finally:
        ig.requests.post = original_post
        ig.time.sleep = original_sleep
        config.GEMINI_API_KEY = ""


# ============================ 6a. Cloudflare response parsing (round 11)
#
# STEP 9 FIXES ROUND 11: a real, DETERMINISTIC (not flaky) 3/3 "no image in
# response" failure on shot 1, reproduced by calling this exact endpoint
# directly with the exact prompt OUTSIDE the pipeline, turned out to be a
# genuine SUCCESS every time — HTTP 200, content-type application/json,
# body {"result": {"image": "<base64>"}}. CloudflareImageProvider.generate()
# only ever handled a raw image/* content-type as success; every response
# that came back as JSON (which, it turns out, is EVERY response — no
# Accept header was ever sent asking for raw bytes) was misread as a
# refusal, forever, no matter how many times it was retried, because the
# bug was in this parsing, not anything Cloudflare rejected. None of the
# 3 tests above ever exercised this path at all — the round-10 retry tests
# mock a generic ImageGenError with matching TEXT, not the real provider
# class, so this genuine gap went untested until now.

def test_cloudflare_parses_the_real_json_plus_base64_success_response():
    import shorts.imagegen as ig
    import base64
    real_png_bytes = b"\x89PNG-fake-but-nonempty-image-bytes"

    def fake_post(url, **kwargs):
        return _FakeResponse(200, json_body={
            "result": {"image": base64.b64encode(real_png_bytes).decode()}},
            headers={"content-type": "application/json"})

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "fake-account", "fake-token"
    try:
        provider = ig.CloudflareImageProvider()
        raw = provider.generate("a prompt", refs=None, size=(1080, 1920), seed=None)
        assert raw == real_png_bytes, raw
        print("   ok — the REAL Workers AI success shape (JSON, "
             "{'result': {'image': '<base64>'}}) is now correctly decoded, "
             "not misread as a refusal")
    finally:
        ig.requests.post = original_post
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""


def test_cloudflare_still_accepts_raw_image_bytes_response():
    """Defensive/future-proofing regression guard: if Cloudflare (or a
    future model) ever DOES return raw bytes with an image/* content-type,
    that path must still work — this is not a replacement for the
    original handling, it's in addition to it."""
    import shorts.imagegen as ig
    real_png_bytes = b"\x89PNG-fake-but-nonempty-image-bytes"

    def fake_post(url, **kwargs):
        return _FakeResponse(200, content=real_png_bytes,
                             headers={"content-type": "image/png"})

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "fake-account", "fake-token"
    try:
        provider = ig.CloudflareImageProvider()
        raw = provider.generate("a prompt", refs=None, size=(1080, 1920), seed=None)
        assert raw == real_png_bytes, raw
        print("   ok — a raw image/* content-type response still returns "
             "resp.content directly, unchanged")
    finally:
        ig.requests.post = original_post
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""


def test_cloudflare_genuine_refusal_still_raises_clearly():
    """A GENUINE refusal ({"success": false, "errors": [...]}, no
    result.image at all) must still raise, with the real error detail —
    the round-11 fix only adds the missing success path, it must not turn
    a real failure into a silent false positive."""
    import shorts.imagegen as ig

    def fake_post(url, **kwargs):
        return _FakeResponse(200, json_body={
            "success": False,
            "errors": [{"code": 8007, "message": "Input prompt contains NSFW content"}]},
            headers={"content-type": "application/json"})

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "fake-account", "fake-token"
    try:
        provider = ig.CloudflareImageProvider()
        try:
            provider.generate("a prompt", refs=None, size=(1080, 1920), seed=None)
            assert False, "expected ImageGenError on a genuine refusal"
        except ig.ImageGenError as e:
            assert "8007" in str(e) or "NSFW" in str(e)
            print(f"   ok — a genuine refusal ({{'success': false, 'errors': "
                 f"[...]}}) still raises clearly, not silently treated as "
                 f"success: {e}")
    finally:
        ig.requests.post = original_post
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""


def test_cloudflare_never_sends_seed_in_the_request_body():
    """
    STEP 9 FIXES ROUND 12: a real judge-triggered retry (story_frames.py's
    own "attempt 1 has no seed, attempt N>1 uses seed=N" rule, entirely
    unrelated to round 10/11's fixes) sent {"prompt": ..., "seed": 2} and
    Cloudflare rejected the WHOLE request with HTTP 400 — "Additional or
    unevaluated properties '/seed' at '/' not allowed" — confirmed live,
    directly against the endpoint, outside this pipeline: the identical
    prompt WITH seed got a 400, the same prompt WITHOUT it got a 200.
    This model's request schema has no seed property at all. Confirms the
    outgoing request body never includes 'seed', no matter what the
    caller passes — dropping it does not break retry-as-cache-miss, since
    imagegen._cache_key hashes `seed` independently of what any given
    provider does with it (see the class's own docstring)."""
    import shorts.imagegen as ig
    import base64
    captured = {}

    def fake_post(url, **kwargs):
        captured["body"] = kwargs.get("json")
        image_b64 = base64.b64encode(b"\x89PNG-fake-but-nonempty").decode()
        return _FakeResponse(200, json_body={"result": {"image": image_b64}},
                             headers={"content-type": "application/json"})

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "fake-account", "fake-token"
    try:
        provider = ig.CloudflareImageProvider()
        provider.generate("a prompt", refs=None, size=(1080, 1920), seed=2)
        assert captured["body"] == {"prompt": "a prompt"}, captured["body"]
        print(f"   ok — CloudflareImageProvider never puts 'seed' in the outgoing "
             f"request body, even when a caller passes one (a retry attempt "
             f"always would): {captured['body']}")
    finally:
        ig.requests.post = original_post
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""


def test_cloudflare_request_body_never_exceeds_the_live_verified_allowlist():
    """
    STEP 9 FIXES ROUND 13: Cloudflare's OWN docs page for this model lists
    `seed` as accepted — but a live, reproducible test directly against
    the real endpoint proved the opposite (see imagegen.
    _CLOUDFLARE_ACCEPTED_FIELDS's own note). This test is driven off that
    LIVE-VERIFIED allowlist, not the (here, wrong) documentation, and
    fails the moment the request body would ever contain a field outside
    it — a general guard against this whole CLASS of bug recurring (any
    future field, not just seed specifically — see the narrower, exact-
    regression test above for that one)."""
    import shorts.imagegen as ig
    import base64
    captured = {}

    def fake_post(url, **kwargs):
        captured["body"] = kwargs.get("json")
        image_b64 = base64.b64encode(b"\x89PNG-fake-but-nonempty").decode()
        return _FakeResponse(200, json_body={"result": {"image": image_b64}},
                             headers={"content-type": "application/json"})

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "fake-account", "fake-token"
    try:
        provider = ig.CloudflareImageProvider()
        # seed=2 is exactly what a real retry sends — asking for the field
        # this allowlist is specifically here to keep out.
        provider.generate("a prompt", refs=None, size=(1080, 1920), seed=2)
        sent_fields = set(captured["body"].keys())
        assert sent_fields <= ig._CLOUDFLARE_ACCEPTED_FIELDS, (
            f"request body {captured['body']} has field(s) outside the "
            f"live-verified allowlist {ig._CLOUDFLARE_ACCEPTED_FIELDS}: "
            f"{sent_fields - ig._CLOUDFLARE_ACCEPTED_FIELDS}")
        print(f"   ok — the Cloudflare request body {captured['body']} never "
             f"exceeds the live-verified accepted-field allowlist "
             f"{ig._CLOUDFLARE_ACCEPTED_FIELDS}, even asking for seed")
    finally:
        ig.requests.post = original_post
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""


def test_cloudflare_candidate_variation_still_works_without_a_seed():
    """
    STEP 9 FIXES ROUND 13, item 2: cast_sheets.py generates several
    CANDIDATES from the identical prompt, relying on a per-candidate
    seed=i to make each one a genuine cache miss (see its own comment) —
    but since Cloudflare now never receives that seed, the actual
    variation between candidates has to come from the MODEL's own
    sampling, not a caller-supplied seed. Confirmed live (see the chat
    reply), reproduced here with a fake that mimics genuinely stochastic
    output: two identical-prompt calls with no seed forwarded must still
    be free to return different bytes — this test asserts the provider
    doesn't itself introduce any accidental determinism (e.g. by
    memoizing on prompt alone) that would make that impossible."""
    import shorts.imagegen as ig
    import base64
    call_count = {"n": 0}

    def fake_post(url, **kwargs):
        call_count["n"] += 1
        # A real stochastic model returns different bytes per call with no
        # seed — this fake mimics that by varying its own fake payload.
        raw = f"fake-image-bytes-{call_count['n']}".encode()
        return _FakeResponse(200, json_body={"result": {"image": base64.b64encode(raw).decode()}},
                             headers={"content-type": "application/json"})

    original_post = ig.requests.post
    ig.requests.post = fake_post
    config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "fake-account", "fake-token"
    try:
        provider = ig.CloudflareImageProvider()
        candidate_1 = provider.generate("identical candidate prompt", refs=None,
                                        size=(1080, 1920), seed=1)
        candidate_2 = provider.generate("identical candidate prompt", refs=None,
                                        size=(1080, 1920), seed=2)
        assert candidate_1 != candidate_2, (
            "two candidates must be free to come back different even though "
            "neither call forwards its seed to Cloudflare")
        assert call_count["n"] == 2, (
            "each candidate must be a REAL, separate network call, not served "
            "from some seed-unaware memoization inside the provider itself")
        print("   ok — two cast-sheet candidates (seed=1, seed=2 at the "
             "caller level) each make a real, separate Cloudflare call and "
             "can come back different, even though neither seed ever "
             "reaches the request body")
    finally:
        ig.requests.post = original_post
        config.CF_ACCOUNT_ID, config.CF_API_TOKEN = "", ""


# ============================== 6b. generation-level retry (round 10)
#
# STEP 9 FIXES ROUND 10: a real run had shot 1 fail 3 separate times on the
# IDENTICAL prompt with 2 different error shapes — "AiError: Input prompt
# contains NSFW content" (code 8007), then "cloudflare refused or returned
# no image: no image in response" twice. Neither is an HTTP-transient
# status _post_with_retry (tested above) already covers — both come back
# as an application-level REFUSAL, not a network blip — so MAX_RETRIES
# never saw them and generate_bytes() raised on the very first attempt.
# These tests exercise the NEW, separate retry layer around the whole
# provider.generate() call, independent of story_frames.py's own judge-
# triggered regeneration.

def test_generate_bytes_retries_a_refusal_then_succeeds():
    import shorts.imagegen as ig
    calls = {"n": 0}
    sleeps = []

    class FlakyProvider(ig.StubImageProvider):
        def generate(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ig.ImageGenError(
                    "cloudflare refused or returned no image: no image in response")
            return super().generate(*a, **kw)

    original_sleep = ig.time.sleep
    ig.time.sleep = lambda s: sleeps.append(s)
    short_id = _fresh_reel_id("t_gen_retry_succeeds")
    try:
        png = ig.generate_bytes(short_id, "s0", f"prompt {uuid.uuid4().hex}",
                                provider=FlakyProvider())
    finally:
        ig.time.sleep = original_sleep

    assert png is not None
    assert calls["n"] == 3, calls
    assert sleeps == [ig.GENERATION_RETRY_DELAY_SECONDS] * 2, sleeps
    print(f"   ok — 2 mocked refusal-shaped ImageGenErrors (the exact real-run "
         f"symptom) are retried, a flat {ig.GENERATION_RETRY_DELAY_SECONDS}s "
         f"delay each time (not exponential backoff: {sleeps}), before the "
         f"3rd attempt succeeds")


def test_generate_bytes_raises_after_max_generation_retries():
    import shorts.imagegen as ig
    calls = {"n": 0}

    class AlwaysFailsProvider(ig.StubImageProvider):
        def generate(self, *a, **kw):
            calls["n"] += 1
            raise ig.ImageGenError(
                "cloudflare refused or returned no image: no image in response")

    original_sleep = ig.time.sleep
    ig.time.sleep = lambda s: None
    short_id = _fresh_reel_id("t_gen_retry_exhaust")
    msg = None
    try:
        try:
            ig.generate_bytes(short_id, "s1", f"prompt {uuid.uuid4().hex}",
                              provider=AlwaysFailsProvider())
            assert False, "expected ImageGenError once generation retries are exhausted"
        except ig.ImageGenError as e:
            msg = str(e)
    finally:
        ig.time.sleep = original_sleep

    assert calls["n"] == ig.MAX_GENERATION_RETRIES, calls
    assert "s1" in msg
    assert f"after {ig.MAX_GENERATION_RETRIES} attempts" in msg
    print(f"   ok — a persistently refusing provider is retried "
         f"{ig.MAX_GENERATION_RETRIES} times (not forever — one bad shot "
         f"cannot hang the whole reel) then raises, naming both the shot "
         f"and the attempt count: {msg}")


def test_generate_bytes_budget_exceeded_mid_retry_is_not_retried():
    """Each retry attempt is a REAL call, budgeted individually (see
    generate_bytes's own note) — a reel that runs out of budget partway
    through a shot's retries must stop cleanly on the next attempt, not
    silently exceed IMAGE_MAX_CALLS_PER_REEL, and the budget error itself
    must never be retried."""
    import shorts.imagegen as ig
    calls = {"n": 0}

    class AlwaysFailsProvider(ig.StubImageProvider):
        def generate(self, *a, **kw):
            calls["n"] += 1
            raise ig.ImageGenError(
                "cloudflare refused or returned no image: no image in response")

    short_id = _fresh_reel_id("t_gen_retry_budget")
    original_budget = config.IMAGE_MAX_CALLS_PER_REEL
    config.IMAGE_MAX_CALLS_PER_REEL = 2
    original_sleep = ig.time.sleep
    ig.time.sleep = lambda s: None
    msg = None
    try:
        try:
            ig.generate_bytes(short_id, "s2", f"prompt {uuid.uuid4().hex}",
                              provider=AlwaysFailsProvider())
            assert False, "expected ImageGenError"
        except ig.ImageGenError as e:
            msg = str(e)
    finally:
        config.IMAGE_MAX_CALLS_PER_REEL = original_budget
        ig.time.sleep = original_sleep

    assert calls["n"] == 2, (
        f"must stop retrying once the budget itself is exhausted, not spend "
        f"a 3rd call past a 2-call budget: {calls}")
    assert "IMAGE_MAX_CALLS_PER_REEL" in msg
    print(f"   ok — each generation retry attempt is budgeted individually — "
         f"a 2-call budget stops after 2 real attempts (not "
         f"MAX_GENERATION_RETRIES={ig.MAX_GENERATION_RETRIES}), and the "
         f"budget error itself is never retried: {msg}")


# ================================================ 7. reference images + usage.py

def test_reference_images_change_the_cache_key():
    calls = []

    class CountingStub(imagegen.StubImageProvider):
        def generate(self, *a, **kw):
            calls.append(1)
            return super().generate(*a, **kw)

    ref = _tmp_ref_png()
    short_id = _fresh_reel_id("t_refs")
    provider = CountingStub()
    prompt = f"a prompt {uuid.uuid4().hex}"
    imagegen.render_frame(short_id, "s0", prompt, refs=None, provider=provider)
    imagegen.render_frame(short_id, "s0", prompt, refs=[ref], provider=provider)
    assert len(calls) == 2, (
        "adding a reference image must be a cache MISS against the no-refs call")
    print("   ok — reference images are part of the cache key (a call with "
          "refs is not served from a no-refs cache entry, or vice versa)")


def test_generate_call_is_logged_through_usage():
    short_id = _fresh_reel_id("t_usage_log")
    cursor = usage.mark()
    imagegen.render_frame(short_id, "s0", "a logged prompt")
    totals = usage.since(cursor)
    assert totals["calls"] >= 1
    assert "image:stub" in totals["by_label"], totals["by_label"]
    print(f"   ok — render_frame logs through usage.py: {totals['by_label']}")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} imagegen tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL IMAGEGEN TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
