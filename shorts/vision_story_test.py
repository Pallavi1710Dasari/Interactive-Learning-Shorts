"""
RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #2/#3: unit tests for
StoryFrameJudge's stricter pass rule and skills.vision.judge_story_frame's
rate limiting / backoff.

No API key, no network — the pass-rule tests build StoryFrameJudge objects
directly; the throttle/backoff tests monkeypatch llm.ask_json with a fake
that raises a mocked 429 a controlled number of times.

    SHORTS_STUB=1 python -m shorts.vision_story_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import time

from shorts import config
from shorts.schema import StoryFrameJudge
from shorts.skills import vision


def _judge(**overrides) -> StoryFrameJudge:
    base = dict(character_match=5, no_text=5, action_visible=5,
               emotion_readable=5, style_match=5)
    base.update(overrides)
    return StoryFrameJudge(**base)


# ==================================================== Part 0 #2 — pass rule

def test_all_perfect_scores_pass():
    j = _judge()
    assert j.passed
    print("   ok — every axis at 5 passes")


def test_no_text_below_5_fails_even_if_everything_else_is_perfect():
    j = _judge(no_text=4)
    assert not j.passed
    print(f"   ok — no_text=4 (not a perfect 5) fails on its own, even with "
         f"character_match={j.character_match} and every other axis at 5")


def test_character_match_3_fails_even_though_old_rule_would_pass():
    """The Step 6 rule (every axis >= 3) would have passed this; Step 7's
    stricter character_match >= 4 must not."""
    j = _judge(character_match=3)
    assert not j.passed
    print(f"   ok — character_match=3 fails under the new >= 4 rule "
         f"(would have passed Step 6's old >= 3 rule): {j.model_dump()}")


def test_character_match_4_passes():
    j = _judge(character_match=4)
    assert j.passed
    print("   ok — character_match=4 (the new floor, not a perfect 5) passes")


def test_other_axes_still_only_need_3():
    j = _judge(action_visible=3, emotion_readable=3, style_match=3)
    assert j.passed
    print("   ok — action_visible/emotion_readable/style_match at the plain "
          "3 floor still pass (only no_text and character_match got stricter)")


def test_setting_match_below_3_fails_when_scored():
    j = _judge(setting_match=2)
    assert not j.passed
    print(f"   ok — a scored setting_match below 3 still fails: {j.model_dump()}")


def test_setting_match_omitted_does_not_count_against_pass():
    j = _judge(setting_match=None)
    assert j.passed
    print("   ok — an omitted setting_match (first wide shot) is not held "
          "against the pass verdict")


# ============================================ Part 0 #3 — throttle + backoff

class _FakeRateLimitError(Exception):
    """Stands in for anthropic.RateLimitError / any 429-carrying exception —
    _is_rate_limited() only inspects status_code, not the exception type."""
    def __init__(self):
        super().__init__("rate limited")
        self.status_code = 429


def test_is_rate_limited_detects_status_code_429():
    assert vision._is_rate_limited(_FakeRateLimitError())
    print("   ok — an exception carrying status_code=429 is detected as rate-limited")


def test_is_rate_limited_false_for_an_ordinary_error():
    assert not vision._is_rate_limited(ValueError("something else broke"))
    print("   ok — an ordinary exception is NOT treated as rate-limited "
          "(would retry forever on real bugs otherwise)")


def test_judge_retries_on_429_then_succeeds():
    """judge_story_frame itself, with llm.ask_json mocked to fail with a
    429 twice then succeed — proves the retry loop actually calls ask_json
    again rather than giving up on the first rate limit."""
    from shorts.schema import Shot
    calls = {"n": 0}
    sleeps = []

    def fake_ask_json(*a, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _FakeRateLimitError()
        return _judge()

    original_ask_json = vision.ask_json
    original_sleep = time.sleep
    original_stub = config.STUB
    vision.ask_json = fake_ask_json
    time.sleep = lambda s: sleeps.append(s)
    config.STUB = False   # _throttle_judge_rpm is a no-op under STUB — force the real path
    try:
        shot = Shot(shot_id="t", characters=["Rahul"], action="a", emotion="happy")
        result = vision.judge_story_frame(__file__, shot, cast_refs=[])
    finally:
        vision.ask_json = original_ask_json
        time.sleep = original_sleep
        config.STUB = original_stub

    assert calls["n"] == 3, calls
    assert result.passed
    # 2 rate-limit backoff sleeps (1s, 2s) — the throttle's own inter-call
    # spacing sleep is separate and only fires when JUDGE_RPM would be
    # exceeded, which a mocked instant retry loop does trigger too; only
    # check that AT LEAST the 2 backoff sleeps happened.
    backoff_sleeps = [s for s in sleeps if s in (1, 2)]
    assert len(backoff_sleeps) >= 2, sleeps
    print(f"   ok — 2 mocked HTTP 429s are retried with backoff before the "
         f"3rd attempt succeeds (calls={calls['n']}, sleeps={sleeps})")


def test_judge_never_fails_a_reel_over_persistent_rate_limiting_within_budget():
    """Within JUDGE_MAX_RETRIES, a persistent 429 is still retried, not
    raised immediately — "never fail a reel because of rate limiting" is
    honored up to the retry budget."""
    from shorts.schema import Shot
    calls = {"n": 0}

    def fake_ask_json(*a, **kw):
        calls["n"] += 1
        if calls["n"] <= vision.JUDGE_MAX_RETRIES:   # succeeds on the LAST allowed attempt
            raise _FakeRateLimitError()
        return _judge()

    original_ask_json = vision.ask_json
    original_sleep = time.sleep
    original_stub = config.STUB
    vision.ask_json = fake_ask_json
    time.sleep = lambda s: None
    config.STUB = False
    try:
        shot = Shot(shot_id="t", characters=["Rahul"], action="a", emotion="happy")
        result = vision.judge_story_frame(__file__, shot, cast_refs=[])
    finally:
        vision.ask_json = original_ask_json
        time.sleep = original_sleep
        config.STUB = original_stub

    assert calls["n"] == vision.JUDGE_MAX_RETRIES + 1
    assert result.passed
    print(f"   ok — {vision.JUDGE_MAX_RETRIES} consecutive 429s are all retried "
         f"(never raised early) and the call succeeds on the final allowed attempt")


def test_throttle_is_a_noop_under_stub():
    """_throttle_judge_rpm must never sleep under SHORTS_STUB=1 — a
    mandatory inter-call delay before every stub judge call would make the
    whole test suite minutes slower for a rate limit that doesn't apply."""
    slept = []
    original_sleep = time.sleep
    time.sleep = lambda s: slept.append(s)
    try:
        assert config.STUB, "this test must run under SHORTS_STUB=1"
        vision._last_judge_call[0] = time.monotonic()   # simulate a call just now
        vision._throttle_judge_rpm()
        vision._throttle_judge_rpm()
    finally:
        time.sleep = original_sleep
    assert not slept
    print("   ok — _throttle_judge_rpm never sleeps under SHORTS_STUB=1, "
          "even called back to back")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} vision_story tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL VISION_STORY TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
