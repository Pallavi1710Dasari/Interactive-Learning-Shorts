"""SKILL — motion scenes (RESTYLE_TO_MOTION_REELS.md phase 3). REEL_STYLE=motion only.

WHERE THIS SITS. The script (approved at the shot-list gate) says what is
SAID. This step says what is SHOWN: for every shot, a field colour, the
transition into it, objects from the phase 2 library (web/src/motion/
library.json) and timeline actions, each cued on a word of the shot's
captions. It never places anything — motion_scenes.layout_scene does — and
it never draws — the player does.

THE PROMPT IS BUILT FROM THE LIBRARY AND THE GRADERS' OWN NUMBERS (object
heights, region sizes, the 2.5 s cadence, which beats may be coral or mint),
and every shot comes with its own budget — so the first attempt can be right.
The first real reel (what_state_means__motion) failed 8 of 11 shots on its
first attempt with a prompt that never said the hook must open with the
language mark, never gave a single height, and let a brief ask for "two phone
mocks side by side", which the library cannot draw.

THE LOOP. One call writes every scene; transitions are then made legal for
the fields in sequence (motion_scenes.fix_transitions — mechanical, never
worth a model call); the free scene graders check them; a failing scene gets
a REPAIR call for only the failing shots, with the reasons; passing ones are
kept. What the repair budget cannot fix falls back to motion_scenes'
default mapping — and THE FALLBACK NEVER CAUSES A FAILURE: the hook and the
payoff fall back together (their defaults mirror each other), any shot the
mix breaks falls back too, and the last resort is every default, which the
graders accept by construction. Every attempt — the scenes, the reasons,
the fallbacks — is recorded for output/<short_id>/scenes_attempts.json.

Under SHORTS_STUB=1 the call's answer IS the default mapping (shorts/stubs.py).
"""
import json
import math

from .. import checks, config
from .. import motion_library as lib
from ..llm import ask_json
from ..motion_scenes import (FAILURE_BEATS, MAX_PLACED, MAX_STILL_SECONDS, SUCCESS_BEATS,
                             default_scenes, fix_transitions, scene_problems)
from ..schema import MotionScenesDraft, MotionScript, motion_plain_text

SYSTEM_MOTION_SCENES = """You design the SCENES of a short vertical teaching reel, one scene per shot.
The script is final: what is said, and the captions, are fixed. You decide what is SHOWN, using
ONLY the object kinds in the LIBRARY below. Every scene is checked by code; a scene that breaks a
rule is rejected, so follow the rules exactly.

A SCENE is:
  field       the background colour: navy (hook, drama, closing), blue (big ideas, chapter
              openers), paper (detail and diagrams — the default), yellow (one emphasis
              moment per reel at most).
  transition  how the shot arrives: "cut" when the field stays the same; when the field
              changes, one of iris, bar_wipe, double_bar_wipe, diagonal_stripes, stack_rise —
              never the same one twice in a row. type_scatter may only leave the hook.
              (Transitions are corrected automatically to fit your fields; choose fields well.)
  label       optional tracked-caps section label ("THE SETUP", "WHY IT FAILS"), <= 30 chars.
  objects     what is on screen, each with an id ("o1", "o2", ...) and the props its kind
              takes — nothing else.
  actions     the timeline: {"at": cue, "do": action, "target": object id, "value"?, "tone"?}.

THE FRAME — objects stack TOP TO BOTTOM, one column, centred, each full width
- There is NO side-by-side layout, no columns, no positions, and no phone, device, browser,
  screenshot, image or person. When a brief asks for two things side by side (before/after,
  two phones, two counters), STACK them: two entity_cards — the failing one first (tone bad),
  the working one second (tone ok) — or ONE token_row / lookup_table that compares them.
  Never invent a kind or a prop; translate the brief into the library.
- The objects must FIT their region (gaps included; heights below):
__REGIONS__
  Add the heights before you add an object. At most __MAX_PLACED__ placed objects.
- A full-frame object (title_card, end_card, takeaway_list, recap_grid, chapter_card,
  code_map) is the whole shot ALONE — no other object beside it.
- A connector joins two NEIGHBOURING placed objects (adjacent in your list) by id.

THE HOOK AND THE PAYOFF
- The hook's FIRST object is identity_title (no props): the language mark. ONLY the hook has
  one. It is 270 tall, so plan the rest of the hook in what is left.
- The hook shows the failure in coral (tone "bad"). The payoff MIRRORS it: the SAME object
  kinds as the hook (identity_title aside), on the SAME field, the failure now a success
  (tone "ok", and no coral anywhere in the payoff). (walkthrough: the result shot shows the
  running example's final state in a token_row.)

CUES
- "at" is "start" or 1-3 consecutive words COPIED from this shot's captions, as spoken: plain
  words, without the <b> tags (a code word without its backticks is fine). Cues are matched in
  order, so list actions in the order the words are spoken; the same cue twice in a row means
  both happen together.
- Something visibly changes at least every __STILL__ seconds (about every 6 spoken words);
  karaoke caption progress does not count. Each shot below says how many changes it needs:
  enter, state, pulse, highlight, type, count actions — each on the word being spoken.

COLOUR MEANINGS ARE FIXED
- tone "bad" (coral) only where something FAILS: __FAIL__.
- tone "ok" (mint) only where something WORKS: __OK__.
- Every other beat uses neither. At most one stamp per reel, on a failure beat.

TEXT
- Text on screen comes from the script: its highlights, code, icons, takeaways, chapter
  titles. Never invent a fact, a number or a name.
- Keep every string within its "max"; kinetic_title wraps at about 18 characters a line,
  at most 3 lines; code_window at most 3 lines of 30 characters.

LIBRARY (kind [layout] height: props — "?" optional, (max N) characters; actions it accepts):
__LIBRARY__

EXAMPLE (a solo fix_story hook and its payoff; a two-speaker reel would use less height):
{"shots": [
 {"id": "s01", "scene": {"field": "navy", "transition": "cut", "label": "",
   "objects": [{"id": "o1", "kind": "identity_title", "props": {}},
               {"id": "o2", "kind": "entity_card", "props": {"label": "Plain variable", "value": "0", "tone": "bad"}},
               {"id": "o3", "kind": "status_pill", "props": {"text": "Stuck at zero", "tone": "bad", "icon": "alert"}}],
   "actions": [{"at": "start", "do": "enter", "target": "o1"},
               {"at": "click", "do": "enter", "target": "o2"},
               {"at": "stuck at zero", "do": "enter", "target": "o3"}]}},
 {"id": "s09", "scene": {"field": "navy", "transition": "iris", "label": "",
   "objects": [{"id": "o1", "kind": "entity_card", "props": {"label": "State", "value": "0", "tone": "ok"}},
               {"id": "o2", "kind": "status_pill", "props": {"text": "Climbs", "tone": "ok", "icon": "check"}}],
   "actions": [{"at": "start", "do": "enter", "target": "o1"},
               {"at": "climbs", "do": "state", "target": "o1", "value": "3", "tone": "ok"},
               {"at": "climbs", "do": "enter", "target": "o2"}]}}]}
(In the hook, identity_title 270 + gap 48 + entity_card 330 + gap 48 + status_pill 80 = 776,
which fits the solo region's 1000.)

Return JSON: {"shots": [{"id": "s01", "scene": {"field": "...", "transition": "...",
"label": "...", "objects": [{"id": "o1", "kind": "...", "props": {...}}],
"actions": [{"at": "start", "do": "enter", "target": "o1"}]}}, ...]}"""

SYSTEM_MOTION_SCENES_REPAIR = SYSTEM_MOTION_SCENES.replace(
    "You design the SCENES of a short vertical teaching reel, one scene per shot.",
    "You are REPAIRING some scenes of a short vertical teaching reel. Every other scene "
    "is final.") + ("\n\nFix every reason given for each shot — read the numbers in them "
                    "(heights, seconds, words). Return ONLY the shots you are asked to repair.")


def _height_text(kind: str, spec: dict) -> str:
    if "height" in spec:
        return str(spec["height"])
    if kind == "kinetic_title":
        k = lib.library()["kinetic"]
        return f"{k['size'] * k['line_height']:.0f} per line"
    if kind == "code_window":
        return "174 + 120 per line"
    if kind == "lookup_table":
        return "78 per row (+1 header) + 24"
    return "full frame" if spec["layout"] == "full" else "0"


def _library_block() -> str:
    lines = []
    for kind, spec in lib.object_kinds().items():
        props = ", ".join(f"{k}: {v}" + (f" (max {spec['max'][k]})" if k in spec.get("max", {}) else "")
                          for k, v in spec["props"].items()) or "no props"
        lines.append(f"  {kind} [{spec['layout']}] {_height_text(kind, spec)}: {props}; "
                     f"actions {', '.join(spec['actions'])}")
    lines.append("  types: tone = " + " | ".join(lib.tones()) + "; icon = one of "
                 + ", ".join(sorted(lib.icon_names())) + "; rows = [{icon, line, sub}]; "
                 "icons = [{name, label, tone}]; parts = [{code, icon, label}]; "
                 "table = [[key, value], ...]")
    lines.append("  actions: " + "; ".join(f"{k} — {v}" for k, v in lib.library()["actions"].items()))
    return "\n".join(lines)


def _regions_block() -> str:
    f = lib.library()["frame"]
    solo, duo = f["solo"]["bottom"] - f["solo"]["top"], f["duo"]["bottom"] - f["duo"]["top"]
    return (f"    one-narrator reel: {solo} tall (the captions are below it)\n"
            f"    two-speaker reel:  {duo} tall (the chat — badges and bubbles — is below it)\n"
            f"    gap between objects {f['gap']}; {f['connector_gap']} where a connector joins them")


def system_prompt(repair: bool = False) -> str:
    return ((SYSTEM_MOTION_SCENES_REPAIR if repair else SYSTEM_MOTION_SCENES)
            .replace("__LIBRARY__", _library_block())
            .replace("__REGIONS__", _regions_block())
            .replace("__MAX_PLACED__", str(MAX_PLACED))
            .replace("__STILL__", f"{MAX_STILL_SECONDS:g}")
            .replace("__FAIL__", ", ".join(sorted(FAILURE_BEATS)))
            .replace("__OK__", ", ".join(sorted(SUCCESS_BEATS))))


def _budget(script: MotionScript) -> dict[str, str]:
    """Per shot: its region and height, how long it runs and how many visible
    changes that needs, and which colours its beat allows."""
    from ..motion_timeline import shot_timings
    f = lib.library()["frame"]
    duo = bool(script.speakers)
    region = f["duo" if duo else "solo"]
    height = region["bottom"] - region["top"]
    out = {}
    for s, c in zip(script.shots, shot_timings(script)):
        secs = c.end - c.start
        changes = max(1, math.ceil(secs / MAX_STILL_SECONDS))
        tones = ("coral and mint" if s.beat in FAILURE_BEATS and s.beat in SUCCESS_BEATS
                 else "coral (bad) allowed, no mint" if s.beat in FAILURE_BEATS
                 else "mint (ok) allowed, no coral" if s.beat in SUCCESS_BEATS
                 else "neither coral nor mint")
        extra = "; FIRST object identity_title" if s.beat == "hook" else ""
        extra += "; mirror the hook's kinds and field, now ok" if s.beat == "payoff" else ""
        out[s.id] = (f"~{secs:.1f}s, needs >= {changes} visible changes; placed objects fit "
                     f"{height} ({'two-speaker' if duo else 'one-narrator'} region); "
                     f"colours: {tones}{extra}")
    return out


def _script_block(script: MotionScript, only: list[str] | None = None) -> str:
    parts = [f"TEMPLATE: {script.template}", f"THEME: {script.theme or 'base'}",
             f"CONCEPT: {script.concept_name}", f"PROMISE: {script.promise}",
             f"SERIES: {script.series}", f"NEXT TOPIC: {script.next_topic or '(none)'}",
             f"TWO SPEAKERS: {'yes — ' + ', '.join(sp.role for sp in script.speakers) if script.speakers else 'no'}"]
    if script.icon_vocabulary:
        parts.append("ICONS: " + ", ".join(f"{i.name} ({i.label})" for i in script.icon_vocabulary))
    if script.takeaways:
        parts.append("TAKEAWAYS: " + json.dumps([t.model_dump() for t in script.takeaways]))
    if script.chapters:
        parts.append("CHAPTERS: " + json.dumps([c.model_dump() for c in script.chapters]))
    if script.running_example:
        parts.append("RUNNING EXAMPLE: " + json.dumps(script.running_example.model_dump()))
    budget = _budget(script)
    parts.append("\nSHOTS:")
    for s in script.shots:
        if only and s.id not in only:
            continue
        parts.append(f"- {s.id} {s.beat}" + (f" (chapter {s.chapter})" if s.chapter else ""))
        parts.append(f"    budget: {budget[s.id]}")
        for c in s.captions:
            who = f"{c.speaker}: " if c.speaker else ""
            parts.append(f"    caption: {who}{c.text}")
            parts.append(f"      cue words: {motion_plain_text(c.text)}")
        if s.code:
            parts.append(f"    code: {s.code}")
        if s.example:
            parts.append(f"    example state: {s.example}")
        parts.append(f"    brief: {s.visual}")
    data = script.model_dump(exclude={"shots": {"__all__": {"scene", "estimated_seconds"}},
                                      "estimated_seconds": True})
    parts.append("\nSCRIPT (JSON, the same script — exact captions for cues):\n"
                 + json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(parts)


def _apply(script: MotionScript, draft: MotionScenesDraft) -> MotionScript:
    by_id = {s.id: s.scene for s in draft.shots}
    out = script.model_copy(update={"shots": [
        s.model_copy(update={"scene": by_id.get(s.id, s.scene)}) for s in script.shots]})
    return fix_transitions(out)


def _failing_shots(script: MotionScript, results) -> dict[str, list[str]]:
    """shot id -> reasons, for every shot a scene grader named. A failure
    naming no shot (the stamp count) is put on every shot with a stamp."""
    duo = bool(script.speakers)
    out: dict[str, list[str]] = {}
    for s in script.shots:
        found = scene_problems(s, duo=duo)
        if found:
            out[s.id] = found
    for r in results:
        if r.passed:
            continue
        for sid in r.details.get("shots", []) if r.details else []:
            reason = f"{r.name}: {r.reason}"
            if reason not in out.setdefault(sid, []):
                out[sid].append(reason)
        if not (r.details or {}).get("shots"):
            for s in script.shots:
                if s.scene and any(o.kind == "stamp" for o in s.scene.objects):
                    out.setdefault(s.id, []).append(r.reason)
    return out


def _record(attempts: list | None, kind: str, script: MotionScript, results, failing: dict,
            fallback: list[str] | None = None) -> None:
    if attempts is None:
        return
    attempts.append({
        "attempt": kind,
        "failing": failing,
        "graders": [{"name": r.name, "passed": r.passed, "reason": r.reason} for r in results],
        "fallback": fallback or [],
        "scenes": {s.id: s.scene.model_dump() if s.scene else None for s in script.shots},
    })


def fall_back(script: MotionScript, failing: list[str], log=print) -> tuple[MotionScript, list, list[str]]:
    """Replace failing shots by their default scenes so that the result PASSES:
    the hook and the payoff fall back together (their defaults mirror each
    other); a shot the mix breaks (a transition, the mirror) falls back too;
    the last resort is every default, which passes by construction. Returns
    (script, results, the shots that fell back)."""
    defaults = default_scenes(script)
    ids = [s.id for s in script.shots]
    pair = {s.id for s in script.shots if s.beat in ("hook", "payoff")}
    chosen = set(failing)
    for _ in range(len(ids) + 1):
        if chosen & pair:
            chosen |= pair
        out = fix_transitions(script.model_copy(update={"shots": [
            s.model_copy(update={"scene": defaults[i]}) if s.id in chosen else s
            for i, s in enumerate(script.shots)]}))
        results = checks.run_motion_scene_graders(out)
        still = set(_failing_shots(out, results))
        if not still:
            return out, results, [i for i in ids if i in chosen]
        new = still - chosen
        if not new:
            break
        chosen |= new
    log("  scenes: the mixed fallback still fails — using every default scene")
    out = script.model_copy(update={"shots": [s.model_copy(update={"scene": defaults[i]})
                                              for i, s in enumerate(script.shots)]})
    return out, checks.run_motion_scene_graders(out), ids


def write_motion_scenes(script: MotionScript, log=print,
                        attempts: list | None = None) -> tuple[MotionScript, list]:
    """Every shot's scene, graded. Returns (the script with scenes, the scene
    grader results). Never returns a shot without a drawable scene, and a
    fallback never leaves a grader failing. `attempts` (a list) receives every
    attempt's scenes, per-shot reasons and fallbacks."""
    draft = ask_json(system_prompt(), _script_block(script), MotionScenesDraft,
                     max_tokens=12000, label="motion_scenes")
    out = _apply(script, draft)
    results = checks.run_motion_scene_graders(out)
    failing = _failing_shots(out, results)
    _record(attempts, "first", out, results, failing)
    for attempt in range(config.MAX_MOTION_SCENE_RETRIES):
        if not failing:
            return out, results
        log(f"  scenes: {len(failing)} of {len(out.shots)} shot(s) failing — repair {attempt + 1}:")
        for sid, why in failing.items():
            log(f"    {sid}: {'; '.join(why)[:300]}")
        reasons = "\n".join(f"- {sid}: {'; '.join(r)}" for sid, r in failing.items())
        user = (_script_block(out, only=list(failing)) + "\n\nTHE CURRENT SCENES OF THESE SHOTS "
                "FAILED REVIEW:\n" + reasons + "\n\nTHE CURRENT SCENES:\n" +
                json.dumps({s.id: s.scene.model_dump() if s.scene else None
                            for s in out.shots if s.id in failing}))
        fix = ask_json(system_prompt(repair=True), user, MotionScenesDraft, max_tokens=6000,
                       label="motion_scenes_repair")
        out = _apply(out, fix)
        results = checks.run_motion_scene_graders(out)
        failing = _failing_shots(out, results)
        _record(attempts, f"repair {attempt + 1}", out, results, failing)
    if failing:
        for sid, why in failing.items():
            log(f"    {sid}: {'; '.join(why)[:300]}")
        out, results, fell = fall_back(out, list(failing), log)
        log(f"  scenes: {', '.join(failing)} still failing after {config.MAX_MOTION_SCENE_RETRIES} "
            f"repair(s) — default scene for {', '.join(fell)} (motion_scenes.default_scene)")
        _record(attempts, "fallback", out, results, _failing_shots(out, results), fell)
    return out, results


def stub_scenes(user: str) -> dict:
    """The stub answer (shorts/stubs.py): the default mapping of the script in
    the prompt's SCRIPT (JSON) block — for every shot, or only the shots a
    repair prompt lists."""
    blob = user.split("SCRIPT (JSON, the same script — exact captions for cues):\n", 1)[1]
    script = MotionScript.model_validate_json(blob.split("\n\nTHE CURRENT SCENES", 1)[0].strip())
    head = user.split("\nSHOTS:\n", 1)[1].split("\nSCRIPT (JSON", 1)[0]
    only = [line.split()[1] for line in head.splitlines() if line.startswith("- s")]
    scenes = default_scenes(script)
    return {"shots": [{"id": s.id, "scene": sc.model_dump()} for s, sc in zip(script.shots, scenes)
                      if s.id in only]}
