"""
The scene layout audit: every scene type, in every context, through the real
layout and plan code — so a layout fix can be seen on all of them at once.

    SHORTS_STUB=1 python -m shorts.motion_audit

Writes web/public/motion-audit/<context>.json (plans the player opens with
#motion-reel?src=/motion-audit/<context>.json) and index.json. Contexts:

    solo            one narrator, captions only
    narrator        one narrator with the animated character
    duo             two speakers, the chat
    duo_characters  two speakers with both characters
    lab_<context>   the same four in the Midnight Lab design (config.MOTION_DESIGN)

A scene type is a composition the scene writer produces (a hook, a code
window with its status, an entity wired to a system panel, ...). Together
they use every object kind in web/src/motion/library.json. Free: no model
call; even timing, no audio.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import motion_reel as mr
from . import motion_themes
from .motion_timeline import build_plan, shot_timings
from .schema import (CaptionChunk, MotionScene, MotionSceneAction, MotionSceneObject, MotionScript,
                     MotionShot)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "public" / "motion-audit"


def _o(i: int, kind: str, **props) -> MotionSceneObject:
    return MotionSceneObject(id=f"o{i}", kind=kind, props=props)


#: name -> (field, label, objects, actions, the two caption sentences)
SCENES: list[tuple[str, str, str, list, list, list[str]]] = [
    ("hook", "navy", "", [
        _o(1, "identity_title"),
        _o(2, "kinetic_title", text="Why does your counter stay stuck at zero?", accent=["zero"]),
        _o(3, "status_pill", text="Still 0", tone="bad", icon="alert")],
     [], ["Why does your counter stay stuck at zero?", "You click and click, but nothing changes."]),
    ("kinetic_statement", "blue", "THE IDEA", [
        _o(1, "kinetic_title", text="React only redraws when state changes", accent=["state"])],
     [], ["React only redraws when state changes.", "A plain variable never tells it to."]),
    ("code_window", "paper", "THE CODE", [
        _o(1, "code_window", file="Counter.jsx", lines=["let count = 0;", "count = count + 1;"]),
        _o(2, "status_pill", text="Plain variable", tone="warn")],
     [MotionSceneAction(at="start", do="type", target="o1")],
     ["Here is the code a beginner writes first.", "It looks fine, but the screen never updates."]),
    ("token_row", "paper", "WHY IT FAILS", [
        _o(1, "token_row", items=["click", "count + 1", "no redraw"], tones=["plain", "plain", "bad"]),
        _o(2, "status_pill", text="Screen stays at 0", tone="bad")],
     [], ["Each click changes the number in memory.", "Nothing asks React to draw it again."]),
    ("entity_stamp", "paper", "WHAT YOU SEE", [
        _o(1, "entity_card", label="<Counter />", value="0", tone="bad"),
        _o(2, "status_pill", text="Stuck", tone="bad"),
        _o(3, "stamp", text="BUG")],
     [MotionSceneAction(at="start", do="stamp", target="o3")],
     ["The screen still shows zero.", "That is the bug we need to fix."]),
    ("entity_to_panel", "blue", "HOW IT WORKS", [
        _o(1, "entity_card", label="<Counter />", value="1", tone="ok"),
        _o(2, "connector", **{"from": "o1", "to": "o3", "tone": "info"}),
        _o(3, "system_panel", title="React", status="Watching", slot_name="count", slot_value="1")],
     [], ["React keeps the value in its own memory.", "When it changes, React draws the screen again."]),
    ("trigger", "blue", "THE FIX", [
        _o(1, "trigger_chip", label="setCount(1)"),
        _o(2, "status_pill", text="Redraws", tone="ok", icon="refresh")],
     [], ["Calling the setter is the trigger.", "React runs your component again and redraws."]),
    ("icon_row", "navy", "THREE PARTS", [
        _o(1, "icon_row", icons=[{"name": "memory", "label": "Remember"}, {"name": "bolt", "label": "Trigger"},
                                 {"name": "refresh", "label": "Redraw"}])],
     [], ["There are three parts to remember.", "Keep the value, trigger the change, see the redraw."]),
    ("big_counter", "yellow", "THE RESULT", [
        _o(1, "big_counter", value="7", label="TOKENS")],
     [MotionSceneAction(at="start", do="count", target="o1")],
     ["Two words became seven small pieces.", "Each piece is called a token."]),
    ("callout", "paper", "LOOK CLOSELY", [
        _o(1, "token_row", items=["To", "##ken", "##ization"]),
        _o(2, "callout", label="##", text="means this piece joins the one before it")],
     [], ["The two hash marks are a signal.", "They mean this piece joins the one before."]),
    ("lookup_table", "paper", "THE SHELF", [
        _o(1, "lookup_table", header=["ID", "TOKEN"], rows=[["101", "[CLS]"], ["2000", "the"], ["11469", "To"],
                                                            ["11862", "##ken"], ["102", "[SEP]"]])],
     [MotionSceneAction(at="start", do="highlight", target="o1", value="3")],
     ["Every piece has a fixed number on the shelf.", "The model only ever sees those numbers."]),
    # action objects (objects/action.tsx): the idea acted out
    ("app_screen", "navy", "", [
        _o(1, "app_screen", title="App", button="Like", label="Likes", value="0")],
     [MotionSceneAction(at="start", do="tap", target="o1"),
      MotionSceneAction(at="nothing", do="state", target="o1", value="0", tone="bad")],
     ["You tap the like button.", "And nothing changes on the screen."]),
    ("memory_box", "paper", "IN MEMORY", [
        _o(1, "memory_box", name="likes", value="0")],
     [MotionSceneAction(at="one", do="state", target="o1", value="1"),
      MotionSceneAction(at="zero", do="reset", target="o1")],
     ["The box holds one after the tap.", "Then it is wiped back to zero."]),
    ("flow", "blue", "HOW IT WORKS", [
        _o(1, "flow", steps=[{"name": "tap", "label": "Tap"}, {"name": "bolt", "label": "setLikes"},
                             {"name": "refresh", "label": "Redraw"}], packet="1")],
     [MotionSceneAction(at="setter", do="travel", target="o1")],
     ["The tap calls the setter.", "React redraws with the new value."]),
    ("compare", "paper", "THE FIX", [
        _o(1, "compare", left="Plain variable", right="useState", left_icon="x", right_icon="memory",
           left_note="forgets", right_note="remembers")],
     [MotionSceneAction(at="useState", do="reveal", target="o1")],
     ["A plain variable forgets.", "But useState remembers."]),
    ("cycle", "navy", "AGAIN AND AGAIN", [
        _o(1, "cycle", steps=[{"name": "tap", "label": "Tap"}, {"name": "refresh", "label": "Render"},
                              {"name": "eye", "label": "Screen"}])],
     [MotionSceneAction(at="start", do="travel", target="o1")],
     ["Every tap starts a new render.", "And the screen shows the new value."]),
    # full-frame cards: one of each
    ("title_card", "blue", "", [
        _o(1, "title_card", title="useState", promise="Why plain variables forget",
           icons=[{"name": "refresh", "label": "Render"}, {"name": "memory", "label": "Memory"},
                  {"name": "bolt", "label": "Trigger"}])],
     [], ["React has one idea that fixes this.", "It is called state."]),
    ("code_map", "paper", "", [
        _o(1, "code_map", lines=["const [count, setCount] =", "  useState(0);"],
           parts=[{"code": "count", "icon": "memory", "label": "the value"},
                  {"code": "setCount", "icon": "bolt", "label": "updates it"}])],
     [], ["In code, use State of zero gives you two things.", "The value, and the setter that changes it."]),
    ("takeaway_list", "paper", "", [
        _o(1, "takeaway_list", rows=[{"icon": "refresh", "line": "Renders reset", "sub": "plain variables"},
                                     {"icon": "memory", "line": "State remembers", "sub": "between renders"},
                                     {"icon": "bolt", "line": "Setters redraw", "sub": "the screen"}])],
     [], ["Remember these three things.", "Plain variables reset, state remembers, setters redraw."]),
    ("chapter_card", "paper", "", [
        _o(1, "chapter_card", n=2, of=4, title="Check the shelf")],
     [], ["Step two.", "Check the shelf."]),
    ("recap_grid", "navy", "", [
        _o(1, "recap_grid", concept="Tokenization", steps=["Cut", "Check the shelf", "Add special tokens", "Swap in numbers"],
           final=["101", "11469", "102"])],
     [], ["Tokenization in four steps.", "Cut, check, add, and swap in numbers."]),
    ("end_card", "navy", "", [_o(1, "end_card", up_next="How useState remembers")],
     [], ["Follow for more.", "One idea at a time."]),
]

FULL = {"title_card", "code_map", "takeaway_list", "chapter_card", "recap_grid", "end_card"}
CONTEXTS = {"solo": (False, False, "classic"), "narrator": (False, True, "classic"),
            "duo": (True, False, "classic"), "duo_characters": (True, True, "classic"),
            "lab_solo": (False, False, "midnight_lab"), "lab_narrator": (False, True, "midnight_lab"),
            "lab_duo": (True, False, "midnight_lab"), "lab_duo_characters": (True, True, "midnight_lab")}


def _script(duo: bool, scenes: list) -> MotionScript:
    theme = motion_themes.registry().get("interview" if duo else "classic_explainer")
    speakers = motion_themes.cast_speakers(theme, "react") if duo else []
    roles = [sp.role for sp in speakers]
    shots = []
    for i, (name, field, label, objects, actions, said) in enumerate(scenes, start=1):
        who = (lambda k: roles[k % 2]) if duo else (lambda k: None)
        shots.append(MotionShot(
            id=f"s{i:02d}", beat="setup", speech=" ".join(said),
            captions=[CaptionChunk(text=t, speaker=who(k)) for k, t in enumerate(said)],
            visual=name, scene=MotionScene(field=field, transition="cut", label=label,
                                           objects=objects, actions=actions)))
    return MotionScript(template="fix_story", short_id=f"audit_{'duo' if duo else 'solo'}__motion",
                        source_section_id="1", topic="Scene layout audit", hook_question="?",
                        concept_name="useState", promise="audit", shots=shots,
                        theme=theme.id, language="react", speakers=speakers, series="@learnthesimpleway")


def build() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    index: dict = {"contexts": {}, "scenes": [s[0] for s in SCENES]}
    for ctx, (duo, chars, design) in CONTEXTS.items():
        scenes = SCENES if ctx in ("solo", "lab_solo") else [s for s in SCENES if not FULL & {o.kind for o in s[3]}]
        script = _script(duo, scenes)
        clocks = shot_timings(script)
        plan = build_plan(script, clocks, cast=mr._cast(script), tags=["#react", "#audit"],
                          characters=chars, design=design)
        data = json.loads(plan.model_dump_json())
        (OUT / f"{ctx}.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        index["contexts"][ctx] = [{"scene": s[0], "id": sh["id"], "t": round((sh["start"] + sh["end"]) / 2 + 0.6, 2),
                                   "characters": sh["characters"]}
                                  for s, sh in zip(scenes, data["shots"])]
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    return index


#: Golden scripts drawn with their free (default) scenes — the action
#: objects in use on whole reels: a UI topic, a non-UI topic, a walkthrough,
#: a two-speaker reel (web/public/motion-audit/golden_<name>.json).
GOLDENS = ("usestate_golden", "tlb_golden", "tokenization_golden", "usestate_interview_golden")


def build_goldens(design: str = "midnight_lab") -> list[str]:
    from .motion_scenes import with_default_scenes
    out = []
    for name in GOLDENS:
        d = json.loads((ROOT / "evals/fixtures/motion" / f"{name}.json").read_text(encoding="utf-8"))
        d.pop("_comment", None)
        script = with_default_scenes(MotionScript(**d))
        plan = build_plan(script, shot_timings(script), cast=mr._cast(script), tags=["#golden"],
                          characters=True, design=design)
        path = OUT / f"golden_{name.replace('_golden', '')}.json"
        path.write_text(plan.model_dump_json(indent=1), encoding="utf-8")
        out.append(path.name)
    return out


if __name__ == "__main__":
    idx = build()
    for name in build_goldens():
        print(f"{'golden':15} -> web/public/motion-audit/{name}")
    for ctx, rows in idx["contexts"].items():
        print(f"{ctx:15} {len(rows)} shots  -> web/public/motion-audit/{ctx}.json")
