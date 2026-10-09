"""SKILL — motion scenes (RESTYLE_TO_MOTION_REELS.md phase 3). REEL_STYLE=motion only.

WHERE THIS SITS. The script (approved at the shot-list gate) says what is
SAID. This step says what is SHOWN: for every shot, a field colour, the
transition into it, objects from the phase 2 library (web/src/motion/
library.json) and timeline actions, each cued on a word of the shot's
captions. It never places anything — motion_scenes.layout_scene does — and
it never draws — the player does.

THE LOOP (the motion counterpart of revision.py's narrow repair). One call
writes every scene; the free scene graders check them; a failing scene gets
a REPAIR call for only the failing shots, with the reasons, and the passing
ones are kept as they are. A shot that still fails after the repair budget
falls back to motion_scenes.default_scene — the deterministic mapping from
the script's own words — and the fallback is logged, so a scenes stage never
leaves a shot undrawable.

Under SHORTS_STUB=1 the call's answer IS the default mapping (shorts/stubs.py).
"""
import json

from .. import checks, config
from .. import motion_library as lib
from ..llm import ask_json
from ..motion_scenes import default_scene, default_scenes, scene_problems
from ..schema import MotionScenesDraft, MotionScript, motion_plain_text

SYSTEM_MOTION_SCENES = """You design the SCENES of a short vertical teaching reel, one scene per shot.
The script is final: what is said, and the captions, are fixed. You decide what is SHOWN.

A SCENE is:
  field       the background colour: navy (hook, drama, closing), blue (big ideas, chapter
              openers), paper (detail and diagrams — the default), yellow (one emphasis
              moment per reel at most).
  transition  how the shot arrives: "cut" when the field stays the same; when the field
              changes, one of iris, bar_wipe, double_bar_wipe, diagonal_stripes, stack_rise —
              never the same one twice in a row. type_scatter may only leave the hook.
  label       optional tracked-caps section label ("THE SETUP", "WHY IT FAILS"), <= 30 chars.
  objects     what is on screen, from the LIBRARY below only, each with an id ("o1", ...).
              At most 4 placed objects. A full-frame object (title_card, end_card,
              takeaway_list, recap_grid, chapter_card, code_map) is the whole shot alone.
              You never give positions: objects stack top to bottom in the order you list
              them. A connector joins two NEIGHBOURING placed objects by id.
  actions     the timeline: {"at": cue, "do": action, "target": object id, "value"?, "tone"?}.
              "at" is "start" or 1-3 words COPIED from this shot's captions. Cues are read in
              order, so list actions in the order the words are spoken; the same cue twice
              in a row means both happen together.

THE RULES
- Build up in speaking order: label, then the object, then its state change, then the
  result — each on the word that names it.
- Something visibly changes at least every 2.5 seconds (about every 6 spoken words).
  Karaoke caption progress does not count. Use highlight / pulse / state actions on the
  word being spoken.
- Colour meanings are fixed: tone "bad" (coral) only where something FAILS (hook, setup,
  break_1, break_2; a walkthrough chapter's NO), tone "ok" (mint) only where something
  WORKS (fix_idea onwards; a walkthrough chapter's YES, result, takeaway). At most one
  stamp per reel, and only on a failure beat.
- The payoff MIRRORS the hook: the same objects on the same field, the failure now a
  success. (walkthrough: the result shows the running example's final state.)
- Text on screen comes from the script: its highlights, code, icons, takeaways, chapter
  titles. Never invent a fact, a number or a name.
- Keep every string within its "max" length; kinetic_title text wraps to at most 3 lines
  of about 18 characters.
- In a two-speaker reel the two avatars stand at the bottom of the frame; the objects
  must fit above them (keep it to 2-3 short objects).

LIBRARY (kind: props; actions it accepts):
__LIBRARY__

Return JSON: {"shots": [{"id": "s01", "scene": {"field": "...", "transition": "...",
"label": "...", "objects": [{"id": "o1", "kind": "...", "props": {...}}],
"actions": [{"at": "start", "do": "enter", "target": "o1"}]}}, ...]}"""

SYSTEM_MOTION_SCENES_REPAIR = SYSTEM_MOTION_SCENES.replace(
    "You design the SCENES of a short vertical teaching reel, one scene per shot.",
    "You are REPAIRING some scenes of a short vertical teaching reel. Every other scene "
    "is final.") + "\n\nReturn ONLY the shots you are asked to repair."


def _library_block() -> str:
    lines = []
    for kind, spec in lib.object_kinds().items():
        props = ", ".join(f"{k}: {v}" + (f" (max {spec['max'][k]})" if k in spec.get("max", {}) else "")
                          for k, v in spec["props"].items())
        lines.append(f"  {kind} [{spec['layout']}]: {props}; actions {', '.join(spec['actions'])}")
    lines.append("  types: tone = " + " | ".join(lib.tones()) + "; icon = one of "
                 + ", ".join(sorted(lib.icon_names())) + "; rows = [{icon, line, sub}]; "
                 "icons = [{name, label, tone}]; parts = [{code, icon, label}]; "
                 "table = [[key, value], ...]")
    lines.append("  actions: " + "; ".join(f"{k} — {v}" for k, v in lib.library()["actions"].items()))
    return "\n".join(lines)


def system_prompt(repair: bool = False) -> str:
    return (SYSTEM_MOTION_SCENES_REPAIR if repair else SYSTEM_MOTION_SCENES).replace(
        "__LIBRARY__", _library_block())


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
    parts.append("\nSHOTS:")
    for s in script.shots:
        if only and s.id not in only:
            continue
        parts.append(f"- {s.id} {s.beat}" + (f" (chapter {s.chapter})" if s.chapter else ""))
        for c in s.captions:
            who = f"{c.speaker}: " if c.speaker else ""
            parts.append(f"    caption: {who}{c.text}")
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
    return script.model_copy(update={"shots": [
        s.model_copy(update={"scene": by_id.get(s.id, s.scene)}) for s in script.shots]})


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
            out.setdefault(sid, []).append(r.reason)
        if not (r.details or {}).get("shots"):
            for s in script.shots:
                if s.scene and any(o.kind == "stamp" for o in s.scene.objects):
                    out.setdefault(s.id, []).append(r.reason)
    return out


def write_motion_scenes(script: MotionScript, log=print) -> tuple[MotionScript, list]:
    """Every shot's scene, graded. Returns (the script with scenes, the scene
    grader results). Never returns a shot without a drawable scene: what the
    repair budget cannot fix falls back to the default mapping, logged."""
    draft = ask_json(system_prompt(), _script_block(script), MotionScenesDraft,
                     max_tokens=12000, label="motion_scenes")
    out = _apply(script, draft)
    results = checks.run_motion_scene_graders(out)
    for attempt in range(config.MAX_MOTION_SCENE_RETRIES):
        failing = _failing_shots(out, results)
        if not failing:
            return out, results
        reasons = "\n".join(f"- {sid}: {'; '.join(r)}" for sid, r in failing.items())
        log(f"  scenes: repairing {', '.join(failing)} (attempt {attempt + 1})")
        user = (_script_block(out, only=list(failing)) + "\n\nTHE CURRENT SCENES OF THESE SHOTS "
                "FAILED REVIEW:\n" + reasons + "\n\nTHE CURRENT SCENES:\n" +
                json.dumps({s.id: s.scene.model_dump() if s.scene else None
                            for s in out.shots if s.id in failing}))
        fix = ask_json(system_prompt(repair=True), user, MotionScenesDraft, max_tokens=6000,
                       label="motion_scenes_repair")
        out = _apply(out, fix)
        results = checks.run_motion_scene_graders(out)
    failing = _failing_shots(out, results)
    if failing:
        log(f"  scenes: {', '.join(failing)} still failing after {config.MAX_MOTION_SCENE_RETRIES} "
            f"repair(s) — using the default scene for each (motion_scenes.default_scene)")
        defaults = default_scenes(out)
        out = out.model_copy(update={"shots": [
            s.model_copy(update={"scene": defaults[i]}) if s.id in failing else s
            for i, s in enumerate(out.shots)]})
        results = checks.run_motion_scene_graders(out)
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
