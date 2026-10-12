"""
Reasoning ("thinking") control for motion runs, and thinking never leaking
into what the pipeline parses (shorts/llm.py, shorts/motion_models.py).

The first real motion reel died on its first call: OpenRouter answered
anthropic/claude-opus-5.5 + thinking={"type":"disabled"} with a 400 —
"Reasoning is mandatory for this endpoint and cannot be disabled." These
tests replay that with a FAKE client that behaves the same way, so nothing
here spends money or touches the network:

  - outside a motion run every request is exactly as before (explainer and
    story unchanged);
  - inside one, each model gets its motion_models.yaml setting: Opus thinking
    on with a budget added on top of max_tokens, Sonnet on too (OpenRouter
    refuses thinking off for it as well: the same 400, 2026-10-10);
  - thinking / redacted_thinking blocks and inlined <thinking> text never
    reach a parser, even when they contain braces;
  - the YAML is validated; the estimate counts thinking tokens;
  - check_models() reports OK or the exact error per model, and its dry run
    (stub mode) makes no call.

    SHORTS_STUB=1 python -m shorts.llm_reasoning_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import contextlib
import io
from types import SimpleNamespace

from shorts.testing import isolate_output
isolate_output()   # usage.json goes to a temp folder

import yaml
from pydantic import BaseModel

from shorts import config, llm, motion_models as mm

OPUS, SONNET = "anthropic/claude-opus-5.5", "anthropic/claude-sonnet-5.5"
MANDATORY = "Reasoning is mandatory for this endpoint and cannot be disabled."


class FakeBadRequest(Exception):
    pass


class FakeMessages:
    """Answers like OpenRouter did: Opus refuses thinking off. Records every request."""

    def __init__(self, answer=None):
        self.requests: list[dict] = []
        self.answer = answer

    def create(self, **kw):
        self.requests.append(kw)
        if kw["model"] == OPUS and kw.get("thinking", {}).get("type") == "disabled":
            raise FakeBadRequest(f"Error code: 400 - '{MANDATORY}'")
        t = kw.get("thinking", {})
        if t.get("type") == "enabled":
            assert t["budget_tokens"] < kw["max_tokens"], "budget_tokens must be below max_tokens"
        blocks = self.answer(kw) if self.answer else [SimpleNamespace(type="text", text='{"ok": true}')]
        return SimpleNamespace(content=blocks, stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=40, output_tokens=300, model_extra={"cost": 0.0061}))


@contextlib.contextmanager
def fake_client(answer=None, stub_off=True):
    fake = SimpleNamespace(messages=FakeMessages(answer))
    saved_client, saved_stub = llm._client, config.STUB
    llm._client = fake
    if stub_off:
        config.STUB = False         # let ask_json reach the (fake) client
    try:
        yield fake.messages
    finally:
        llm._client, config.STUB = saved_client, saved_stub


class Ok(BaseModel):
    ok: bool


# ======================================================= explainer and story

def test_outside_a_motion_run_requests_are_unchanged():
    """The explainer and story requests, exactly as before this change."""
    assert llm._MODEL_REASONING == {} and llm._LABEL_MODELS == {}
    assert llm._reasoning("claude-sonnet-5", False) == {"thinking": {"type": "disabled"}}
    assert llm._reasoning("claude-opus-5", False) == {"thinking": {"type": "disabled"}}
    assert llm._reasoning("claude-opus-5", True) == {}
    assert llm._reasoning("openai/gpt-5-mini", False) == {"thinking": {"type": "enabled", "budget_tokens": 1024}}
    assert llm._reasoning("google/gemini-3.1-pro-preview", False)["thinking"]["type"] == "enabled"
    assert llm._reasoning("google/gemini-2.5-flash", False) == {"thinking": {"type": "disabled"}}
    assert llm.thinking_budget("claude-sonnet-5") == 0
    with fake_client() as m:
        llm.ask_json("s", "u", Ok, model="claude-sonnet-5", max_tokens=4000, label="script")
    assert m.requests[0]["max_tokens"] == 4000 and m.requests[0]["thinking"] == {"type": "disabled"}
    assert m.requests[0]["model"] == "claude-sonnet-5"


def test_explainer_and_story_models_are_untouched():
    defaults = {"MODEL_GENERATOR": "claude-sonnet-5", "MODEL_JUDGE": "claude-opus-5",
                "MODEL_STORY_JUDGE": "claude-sonnet-5"}
    for name, value in defaults.items():
        if not os.environ.get(name):
            assert getattr(config, name) == value, name
    text = open(mm.PATH, encoding="utf-8").read()
    assert "MODEL_" not in yaml.safe_dump(yaml.safe_load(text))


# ============================================================== motion runs

def test_the_failure_reproduced_and_fixed():
    """Before: Opus with thinking off -> the 400. Now, in a motion run: thinking on."""
    with fake_client() as m:
        try:
            llm.ask_json("s", "u", Ok, model=OPUS, label="select", retries=0)
            raise AssertionError("the fake should refuse thinking off for Opus")
        except FakeBadRequest as e:
            assert MANDATORY in str(e)
        m.requests.clear()
        with mm.use():
            assert llm.ask_json("s", "u", Ok, label="select", max_tokens=4000).ok
        req = m.requests[0]
        assert req["model"] == OPUS
        assert req["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert req["max_tokens"] == 4000 + 1024          # thinking never takes the answer's room


def test_each_model_gets_its_own_setting_and_it_ends_with_the_run():
    with fake_client() as m:
        with mm.use():
            llm.ask_json("s", "u", Ok, label="framing", max_tokens=600)          # sonnet: on
            llm.ask_json("s", "u", Ok, label="motion_scenes", max_tokens=9000)   # opus: on
            llm.call("s", "u", model=OPUS, max_tokens=500, label="raw")
        sonnet, opus, raw = m.requests
        assert sonnet["model"] == SONNET and sonnet["thinking"] == {"type": "enabled", "budget_tokens": 1024}
        assert sonnet["max_tokens"] == 600 + 1024
        assert opus["model"] == OPUS and opus["thinking"]["type"] == "enabled" and opus["max_tokens"] == 9000 + 1024
        assert raw["max_tokens"] == 500 + 1024
    assert llm._MODEL_REASONING == {} and llm._LABEL_MODELS == {}


def test_thinking_never_reaches_the_parser():
    def answer(kw):
        return [SimpleNamespace(type="thinking", thinking='Maybe {"ok": false} ... no.', signature="x"),
                SimpleNamespace(type="redacted_thinking", data="zzz"),
                SimpleNamespace(type="reasoning", text='{"ok": false}'),
                SimpleNamespace(type="text", text='<thinking>draft {"ok": false}</thinking>\n{"ok": true}')]
    with fake_client(answer) as m:
        with mm.use():
            assert llm.ask_json("s", "u", Ok, label="select").ok is True
        resp = m.create(model=SONNET, max_tokens=10, thinking={"type": "disabled"}, system="", messages=[])
    assert llm.visible_text(resp) == '{"ok": true}'
    assert llm.text_of(resp) == '{"ok": true}'
    for tag in ("think", "reasoning", "THINKING"):
        r = SimpleNamespace(content=[SimpleNamespace(type="text", text=f"<{tag}>x {{1}}</{tag}>[1, 2]")])
        assert llm.visible_text(r) == "[1, 2]", tag


def test_the_yaml_is_validated():
    good = yaml.safe_load(mm.PATH.read_text(encoding="utf-8"))
    assert good["reasoning"][OPUS]["thinking"] == "on" and good["reasoning"][SONNET]["thinking"] == "on"

    def check(data) -> str:
        """Load `data` as the YAML — from a temp file; the real one is never written."""
        import tempfile
        from pathlib import Path
        real = mm.PATH
        tmp = Path(tempfile.mkdtemp()) / "motion_models.yaml"
        tmp.write_text(yaml.safe_dump(data), encoding="utf-8")
        mm.PATH = tmp
        mm.load.cache_clear()
        try:
            mm.load()
            return ""
        except ValueError as e:
            return str(e)
        finally:
            mm.PATH = real
            mm.load.cache_clear()

    assert "has no `reasoning` entry" in check({**good, "reasoning": {SONNET: {"thinking": "off"}}})
    assert "at least 1024" in check({**good, "reasoning": {**good["reasoning"], OPUS: {"thinking": "on", "budget": 200}}})
    assert "on or off" in check({**good, "reasoning": {**good["reasoning"], OPUS: {"thinking": "maybe"}}})
    assert check({**good, "reasoning": {**good["reasoning"], OPUS: {"thinking": True, "budget": 2048}}}) == ""
    assert mm.reasoning_for(OPUS) == {"thinking": "on", "budget": 1024}


def test_the_estimate_counts_thinking():
    rows = {r["label"]: r for r in mm.estimate("x" * 4000)}
    assert rows["select"]["thinking"] == 1024 and rows["framing"]["thinking"] == 1024   # Sonnet thinks too
    from shorts import preflight
    bare = preflight.text_cost_per_call(OPUS, 1000 + 3500, 2500)
    assert rows["select"]["per_call_worst"] > bare
    assert abs(rows["select"]["per_call_worst"] - preflight.text_cost_per_call(OPUS, 4500, 2500 + 1024)) < 1e-4
    assert rows["select"]["per_call"] < rows["select"]["per_call_worst"]   # typical uses part of the budget
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        typical, worst = mm.print_estimate(list(rows.values()))
    assert "thinking" in buf.getvalue() and 0 < typical < worst < config.MAX_REEL_USD


def test_check_models_reports_ok_or_the_exact_error():
    with fake_client(stub_off=False) as m:
        rows = mm.check_models(dry_run=True)
        assert m.requests == []                         # a dry run makes no call
    assert {r["model"] for r in rows} == {OPUS, SONNET} and all(r["status"] == "DRY RUN" for r in rows)
    assert all(r["max_cost"] < 0.05 for r in rows)

    with fake_client(stub_off=False) as m:
        rows = {r["model"]: r for r in mm.check_models(dry_run=False)}
    assert len(m.requests) == 2                          # ONE call per model
    assert rows[OPUS]["status"] == "OK" and rows[OPUS]["request"]["thinking"]["type"] == "enabled"
    assert rows[SONNET]["status"] == "OK" and rows[SONNET]["cost"] == 0.0061

    # a model that refuses its setting: the exact error comes back
    saved = mm.load()["reasoning"][OPUS]
    mm.load()["reasoning"][OPUS] = {"thinking": "off"}
    try:
        with fake_client(stub_off=False):
            rows = {r["model"]: r for r in mm.check_models(dry_run=False)}
        assert rows[OPUS]["status"] == "ERROR" and MANDATORY in rows[OPUS]["detail"]
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert mm.print_check(list(rows.values())) is False
        assert MANDATORY in buf.getvalue() and "FIX" in buf.getvalue()
    finally:
        mm.load()["reasoning"][OPUS] = saved
    assert llm._MODEL_REASONING == {}


def test_the_runner_flag_needs_no_document_and_is_a_dry_run_in_stub_mode():
    from shorts import motion_reel
    buf = io.StringIO()
    with fake_client(stub_off=False) as m, contextlib.redirect_stdout(buf):
        code = motion_reel.main(["--check-models"])
    assert code == 0 and m.requests == []
    assert "dry run: no call made" in buf.getvalue() and OPUS in buf.getvalue()


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} reasoning tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL REASONING TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
