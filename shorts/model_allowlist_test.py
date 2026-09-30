"""
RESTYLE_TO_STORY_REELS.md Step 8 Part 0 #2: story mode must never call any
model other than MODEL_GENERATOR, MODEL_STORY_JUDGE, MODEL_STORY_VISION_JUDGE
(text/vision LLM calls) and IMAGE_MODEL (image generation) — in particular,
NEVER MODEL_DIAGRAM / MODEL_STRATEGIST (explainer mode's diagram-design
models, e.g. gemini-3.1-pro-preview in this deployment's own .env).

This runs the REAL story pipeline (plan_story_mapping -> judge gate ->
write_story_shots -> audit_story -> the vision judge), with ask_json
monkeypatched at each of the three call sites (skills.script, skills.audit,
skills.vision — each holds its own `from ..llm import ask_json` reference,
so all three need patching independently) to RECORD the resolved model
(`model or config.MODEL_GENERATOR`, the same resolution llm.ask_json itself
does) before handing back a stub canned response via shorts.stubs.fake — so
this test is free and makes no network call, while still exercising the
real call sites, not a hand-picked guess at where they are.

    SHORTS_STUB=1 python -m shorts.model_allowlist_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

import tempfile
from pathlib import Path

from shorts import config, imagegen
from shorts.parse import parse_markdown
from shorts.schema import Section, Shot, Topic
from shorts.skills import audit, script, vision
from shorts.skills.understanding import understanding_for
from shorts.stubs import fake

ALLOWED_STORY_MODELS = {
    config.MODEL_GENERATOR,
    config.MODEL_STORY_JUDGE,
    config.MODEL_STORY_VISION_JUDGE,
}

SOURCE = (
    "A plain variable does not survive a re-render — it is recreated from "
    "scratch every time the component function runs. useState instead keeps "
    "its value in a slot React owns, outside the function body, so the value "
    "read on the next render is the one written on the last one."
)


def _sections():
    doc = ("# Stub Session\n\n"
          "## 1.1 Why the count never updates\n"
          f"{SOURCE}\n\n"
          "## 1.2 How useState creates and updates state\n"
          f"{SOURCE}\n")
    with tempfile.TemporaryDirectory() as d:
        doc_path = Path(d) / "stub_doc.md"
        doc_path.write_text(doc, encoding="utf-8")
        return parse_markdown(str(doc_path))


def _recorder(tag, calls):
    def recorder(system, user, model_cls, model=None, max_tokens=4000,
                retries=2, label="llm", think=False, images=None):
        effective = model or config.MODEL_GENERATOR
        calls.append((tag, label, effective))
        return fake(model_cls, system, user)
    return recorder


def test_story_pipeline_never_calls_a_model_outside_the_allowlist():
    calls: list[tuple[str, str, str]] = []
    original = {"script": script.ask_json, "audit": audit.ask_json,
               "vision": vision.ask_json}
    script.ask_json = _recorder("script", calls)
    audit.ask_json = _recorder("audit", calls)
    vision.ask_json = _recorder("vision", calls)
    try:
        section = _sections()[1]
        topic = Topic(id="allowlist_check", topic="How does useState remember a value?",
                     why_it_matters="test", source_section_id=section.section_id,
                     difficulty="medium")
        understanding = understanding_for(section, source_text=section.text)

        mapping = script.plan_story_mapping(topic, section, understanding=understanding,
                                            source_text=section.text)
        assert mapping is not None, "stub mapping must pass check_mapping/check_hook/judge"

        story = script.write_story_shots(mapping, topic, section, understanding=understanding,
                                         source_text=section.text, session_id="s1")

        results, report = audit.audit_story(story, section.text,
                                            technical_term=story.technical_term)
        assert not [r for r in results if not r.passed]
        assert report is not None and report.passed

        shot = Shot(shot_id="t", characters=["Rahul"], action="a", emotion="happy")
        vision.judge_story_frame(__file__, shot, cast_refs=[])
    finally:
        script.ask_json = original["script"]
        audit.ask_json = original["audit"]
        vision.ask_json = original["vision"]

    assert calls, "no ask_json call was recorded at all — the pipeline didn't run"
    labels = [f"{tag}.{label}" for tag, label, _ in calls]
    disallowed = [(tag, label, model) for tag, label, model in calls
                 if model not in ALLOWED_STORY_MODELS]
    assert not disallowed, (
        f"story mode called a model outside the allow-list "
        f"{ALLOWED_STORY_MODELS}: {disallowed}")

    banned = {config.MODEL_DIAGRAM, config.MODEL_STRATEGIST} - ALLOWED_STORY_MODELS
    used = {model for _, _, model in calls}
    hit_banned = used & banned
    assert not hit_banned, (
        f"story mode called MODEL_DIAGRAM/MODEL_STRATEGIST "
        f"({config.MODEL_DIAGRAM!r}/{config.MODEL_STRATEGIST!r}): {hit_banned}")

    print(f"   ok — the full story pipeline (mapping -> judge gate -> shots -> "
         f"audit_story -> vision judge) made {len(calls)} model call(s), every "
         f"one inside the allow-list, none hitting MODEL_DIAGRAM "
         f"({config.MODEL_DIAGRAM!r}) or MODEL_STRATEGIST "
         f"({config.MODEL_STRATEGIST!r}): {labels}")


def test_default_image_provider_resolves_to_image_model_not_a_diagram_model():
    original_key = config.GEMINI_API_KEY
    config.GEMINI_API_KEY = "test-key-construction-only-no-network-call"
    try:
        provider = imagegen.GeminiImageProvider()
    finally:
        config.GEMINI_API_KEY = original_key

    assert provider.model == config.IMAGE_MODEL
    assert provider.model not in (config.MODEL_DIAGRAM, config.MODEL_STRATEGIST,
                                  config.MODEL_GENERATOR, config.MODEL_STORY_JUDGE,
                                  config.MODEL_STORY_VISION_JUDGE)
    print(f"   ok — the default (no explicit model=) GeminiImageProvider resolves "
         f"to config.IMAGE_MODEL ({config.IMAGE_MODEL!r}), never a text/diagram model")


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} model_allowlist tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    print("\nALL MODEL_ALLOWLIST TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
