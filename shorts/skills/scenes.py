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

SHOW IT, DON'T WRITE IT — THE MOST IMPORTANT RULE
The viewer is a beginner with zero knowledge, and may watch WITH THE SOUND OFF. They must
understand what is happening from the picture alone: show the idea HAPPENING, by the right
action, never by putting the sentence on screen.
- Every shot acts something out: at least one tap, state (a value changes), travel (something
  moves from step to step), reset (a box wiped back), reveal (the fix appears), type or count.
  Things only appearing is not enough.
- At least half the shots use an ACTION OBJECT:
    app_screen  what the USER sees — a tiny app: a finger taps its button, the number on it
                changes (or stays and shakes: tone bad). Clicks, buttons, forms, screens, carts.
    memory_box  what the COMPUTER keeps — a labelled box with a value: a new value drops in
                (state), or the box is wiped back to its start (reset). Variables, state, cache.
    flow        a PROCESS — 2-4 steps in a row, something travels through them, each lights up.
                Requests, pipelines, cause -> effect, input -> output.
    compare     WRONG vs RIGHT side by side (✗ / ✓); reveal the right side on the word that
                names the fix. A mistake and its fix, before and after.
    cycle       something that REPEATS — 3-4 steps on a loop, a dot goes round. Re-renders,
                loops, lifecycles.
  Pick the one whose MOTION matches the sentence: a click is a tap, "it resets" is a reset,
  "then it sends it to" is a travel, "instead of X, use Y" is a compare reveal.
- Words on screen are LABELS: 1-3 words each, at most 12 words in a whole shot (code aside).
  The captions already carry the sentence; never repeat it on screen as text.
- code_window and code_map ONLY on a shot whose script has code. Material without code never
  gets a code picture. Their lines are REAL code only: never a comment used as a label
  ("# cart: the variable") — a code_map's parts already point a callout at each token.
- A system_panel slot reads name -> value: slot_name is the NAME in the code ("cart"), slot_value
  is what it holds or points to ('["milk", "bread"]'); never a role word like "tag" as the name.
- Labels use the shot's own words (its highlights, its code names, the thing it names).

A SCENE is:
  field       the background colour: navy (hook, drama, closing), blue (big ideas, chapter
              openers), paper (detail and diagrams — the default), yellow (one emphasis
              moment per reel at most).
  transition  how the shot arrives: "cut" when the field stays the same; when the field
              changes, one of iris, bar_wipe, double_bar_wipe, diagonal_stripes, stack_rise —
              never the same one twice in a row. type_scatter may only leave the hook.
              (Transitions are corrected automatically to fit your fields; choose fields well.)
  label       optional tracked-caps section label ("THE SETUP", "WHY IT FAILS"), <= 30 chars.
  avatars     optional, only for reels with on-screen presenters: "on" or "off" for this
              shot, or "" for the default — on for the hook, the main idea, the aha, a
              student's question, the recap and the end card; off for code, code maps,
              flows, memory panels and tables, so the visual gets the whole frame. A shot
              showing code, a code map, a flow, a panel or a table is always drawn without them.
  objects     what is on screen, each with an id ("o1", "o2", ...) and the props its kind
              takes — nothing else.
  actions     the timeline: {"at": cue, "do": action, "target": object id, "value"?, "tone"?}.

THE FRAME — objects stack TOP TO BOTTOM, one column, centred, each full width
- There is NO free layout, no columns, no positions, no images and no people. Two things
  side by side are ONE compare object; a screen is ONE app_screen. Never invent a kind or a
  prop; translate the brief into the library.
- The objects must FIT their region (gaps included; heights below):
__REGIONS__
  Add the heights before you add an object. At most __MAX_PLACED__ placed objects.
- A full-frame object (title_card, end_card, takeaway_list, recap_grid, chapter_card,
  code_map) is the whole shot ALONE — no other object beside it.
- A connector joins two NEIGHBOURING placed objects (adjacent in your list) by id.

THE HOOK AND THE PAYOFF
- The hook ACTS OUT the problem (an app_screen tap that changes nothing, a memory_box whose
  value is wrong...). It may open with identity_title (no props, 270 tall: the language mark)
  if that still fits; the corner badge names the language anyway. ONLY the hook may have one.
- The hook shows the failure in coral (tone "bad"). The payoff MIRRORS it: the SAME object
  kinds as the hook (identity_title aside), on the SAME field, the failure now a success
  (tone "ok", and no coral anywhere in the payoff). The payoff must SHOW the fix working —
  a tap that now counts, a reset, a reveal, a travel — not the hook's object with a new
  label: a shot that only relabels an earlier object is dropped from the reel. (walkthrough: the result shot shows the
  running example's final state in a token_row.)

CUES
- "at" is "start" or 1-3 consecutive words COPIED from this shot's captions, as spoken: plain
  words, without the <b> tags (a code word without its backticks is fine). Cues are matched in
  order, so list actions in the order the words are spoken; the same cue twice in a row means
  both happen together.
- Something visibly changes at least every __STILL__ seconds (about every 6 spoken words);
  karaoke caption progress does not count. Each shot below says how many changes it needs:
  enter, state, pulse, highlight, type, count actions — each on the word being spoken.

VARIETY AND MATCH
- Never give two shots in a row the same main objects (status_pill, connector and stamp
  aside): if one shot is an entity_card, the next is something else.
- No object kind may be the main object of more than 3 shots. Use the WHOLE library — the
  action objects first (app_screen, memory_box, flow, compare, cycle), then big_counter,
  lookup_table, system_panel, token_row, code_window — pick what best SHOWS this sentence.
- Each shot shows what its narration says: the words on its objects come from that shot's
  own captions (its highlights, its code, its numbers). One clear focus per shot.

CAMERA AND CURSOR (optional — the camera and cursor already follow code, memory slots, app
screens and the CTA by themselves)
- "focus" on any object zooms the camera onto it (value: the part — a code_map part, a
  code_window line) on the cue word and holds while it is talked about. Use it for the ONE
  thing a sentence is about, at most once per sentence; never on every shot.
- "click" on any object makes the cursor glide there and click on the cue word (a button, a
  token, a name). A code_window's "type" is typed by the cursor letter by letter.

COLOUR MEANINGS ARE FIXED
- tone "bad" (coral) only where something FAILS: __FAIL__.
- tone "ok" (mint) only where something WORKS: __OK__.
- Every other beat uses neither. At most one stamp per reel, on a failure beat.

TEXT
- Text on screen comes from the script: its highlights, code, icons, takeaways, chapter
  titles. Never invent a fact, a number or a name.
- Keep every string within its "max"; kinetic_title wraps at about 18 characters a line,
  at most 3 lines; code_window at most 3 lines of 30 characters.
- Write kinetic_title text in normal sentence case ("Why does useState
  remember?"), never in capitals: the player sets the case for the reel's design.

LIBRARY (kind [layout] height: props — "?" optional, (max N) characters; actions it accepts):
__LIBRARY__

EXAMPLE (a solo fix_story hook, a fix and its payoff; a two-speaker reel has 600 of height):
{"shots": [
 {"id": "s01", "scene": {"field": "navy", "transition": "cut", "label": "",
   "objects": [{"id": "o1", "kind": "kinetic_title", "props": {"text": "Why does your like button stay stuck?"}},
               {"id": "o2", "kind": "app_screen", "props": {"title": "App", "button": "Like", "label": "Likes", "value": "0"}}],
   "actions": [{"at": "start", "do": "enter", "target": "o1"},
               {"at": "start", "do": "enter", "target": "o2"},
               {"at": "click", "do": "tap", "target": "o2"},
               {"at": "stuck at zero", "do": "state", "target": "o2", "value": "0", "tone": "bad"}]}},
 {"id": "s06", "scene": {"field": "blue", "transition": "iris", "label": "THE FIX",
   "objects": [{"id": "o1", "kind": "compare", "props": {"left": "Plain variable", "right": "useState",
                                                          "left_icon": "x", "right_icon": "memory"}}],
   "actions": [{"at": "start", "do": "enter", "target": "o1"},
               {"at": "useState", "do": "reveal", "target": "o1"}]}},
 {"id": "s09", "scene": {"field": "navy", "transition": "bar_wipe", "label": "",
   "objects": [{"id": "o1", "kind": "kinetic_title", "props": {"text": "Now every tap counts"}},
               {"id": "o2", "kind": "app_screen", "props": {"title": "App", "button": "Like", "label": "Likes", "value": "0"}}],
   "actions": [{"at": "start", "do": "enter", "target": "o1"},
               {"at": "start", "do": "enter", "target": "o2"},
               {"at": "tap", "do": "tap", "target": "o2"},
               {"at": "climbs", "do": "state", "target": "o2", "value": "1", "tone": "ok"}]}}]}
(In the hook, kinetic_title 2 lines 213 + gap 60 + app_screen 560 = 833, which fits the solo
region's 1000.)

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
                     f"actions {', '.join(spec['actions'])}"
                     + (f"\n      — {spec['_use']}" if spec.get("_use") else ""))
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
    # a video draws every visual onto its board: the one-narrator region
    duo = bool(script.speakers) and getattr(script, "format", "reel") != "video"
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
        extra = "; act the problem out (an action object going wrong)" if s.beat == "hook" else ""
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
        if s.code_focus:
            parts.append(f"    code focus: line {', '.join(map(str, s.code_focus))} "
                         f"({' / '.join(repr(s.code[n - 1]) for n in s.code_focus if 0 < n <= len(s.code))}) "
                         f"— the line this shot explains: light it")
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
    video = getattr(script, "format", "reel") == "video"
    duo = bool(script.speakers) and not video
    out: dict[str, list[str]] = {}
    for s in script.shots:
        found = scene_problems(s, duo=duo, video=video)
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


#: A video's scenes are asked in batches of at most this many shots (whole
#: chapters kept together), so one answer never outgrows its output budget.
VIDEO_SCENE_BATCH = 14
#: A video's repair round sends at most this many batches; shots past them
#: keep their scenes for the next round (or the fallback). It bounds the
#: spend the scenes gate planned for (motion_reel.scenes_plan).
VIDEO_REPAIR_BATCHES = 2


def _video_rules() -> str:
    """What every scenes call of a VIDEO is told on top of the reel's rules
    (2026-10-23: the explanation must be understood in one watch, the code
    walked line by line, and no one picture repeated through a chapter)."""
    return "\n".join([
        "VIDEO RULES (on top of the rules above):",
        "- The picture TEACHES: a student watching once, with nothing else open, must see "
        "what each sentence means. Show the step HAPPENING (a value dropping into a "
        "memory_box, something travelling a flow, a compare reveal), not its words.",
        "- The running example as a token_row is the main object of AT MOST ONE shot per "
        "chapter. Its other shots show what the step DOES to it with another kind.",
        f"- Every shot is drawn on the one-narrator region (1000 tall), speakers or not. A "
        f"code_window may show up to {checks.MOTION_VIDEO['MOTION_MAX_CODE_LINES']} lines "
        f"(174 + 120 per line) of up to {checks.MOTION_VIDEO['MOTION_MAX_CODE_CHARS']} characters: "
        f"always the shot's code exactly as the script gives it.",
        "- A LINE-BY-LINE CODE WALK: a shot with a \"code focus\" shows its whole code in a "
        "code_window (all of its lines, unchanged) and highlights the focus line at "
        "\"start\" ({\"at\": \"start\", \"do\": \"highlight\", \"target\": <the window>, "
        "\"value\": \"<line>\"}), and any later highlight in the shot names that same line. "
        "Only the first shot of a walk types the code; the next ones just enter. Under the "
        "window, when it fits, show what the line DOES: a memory_box getting its value, a "
        "status_pill with what it prints. Consecutive shots of one walk may all show the "
        "code_window: the lit line moving is the picture.",
    ])


def _batch_note(script: MotionScript, only: list[str], done: MotionScript | None = None) -> str:
    """What a batch call is told: answer ONLY its own shots (it sees the whole
    script for context), and what the shot just before them shows, so the
    first one is not a repeat of it."""
    ids = [s.id for s in script.shots]
    lines = [f"THIS CALL: design the scenes of ONLY these {len(only)} shots: {', '.join(only)}. "
             f"Return exactly those shots and no others — the other shots are designed in "
             f"other calls. This is a long-form LANDSCAPE video ({len(ids)} shots): vary the "
             f"object kinds from shot to shot, as you would across a reel. The rule \"no kind is "
             f"the main object of more than 3 shots\" holds in every 11 shots in a row, and a "
             f"video may use one stamp per chapter."]
    i = ids.index(only[0])
    prev = (done or script).shots[i - 1] if i > 0 else None
    if prev is not None and prev.scene is not None:
        kinds = ", ".join(o.kind for o in prev.scene.objects) or "nothing"
        lines.append(f"The shot before this batch ({prev.id}) shows: {kinds} on {prev.scene.field} — "
                     f"the first shot here must show something else.")
    return "\n".join(lines)


def scene_batches(script: MotionScript) -> list[list[str]]:
    """The shot ids each scenes call covers: every shot in one call for a reel;
    for a video, consecutive runs of at most VIDEO_SCENE_BATCH shots that break
    at a chapter card (a chapter longer than the batch is split on its own)."""
    ids = [s.id for s in script.shots]
    if getattr(script, "format", "reel") != "video":
        return [ids]
    groups: list[list[str]] = []
    for s in script.shots:
        if not groups or s.beat == "chapter_card" or s.beat == "result":
            groups.append([])
        groups[-1].append(s.id)
    out: list[list[str]] = []
    for g in groups:
        while len(g) > VIDEO_SCENE_BATCH:
            out.append(g[:VIDEO_SCENE_BATCH])
            g = g[VIDEO_SCENE_BATCH:]
        if out and len(out[-1]) + len(g) <= VIDEO_SCENE_BATCH:
            out[-1] = out[-1] + g
        else:
            out.append(g)
    return out


def write_motion_scenes(script: MotionScript, log=print,
                        attempts: list | None = None, note: str = "") -> tuple[MotionScript, list]:
    """Every shot's scene, graded. Returns (the script with scenes, the scene
    grader results). Never returns a shot without a drawable scene, and a
    fallback never leaves a grader failing. `attempts` (a list) receives every
    attempt's scenes, per-shot reasons and fallbacks. `note`: the reviewer's
    words when the scenes are redrawn from the reels feed ("redraw")."""
    out = script
    batches = scene_batches(script)
    for n, only in enumerate(batches, 1):
        block = _script_block(script, only=only if len(batches) > 1 else None)
        if len(batches) > 1:
            block = _batch_note(script, only, out) + "\n\n" + block
        if getattr(script, "format", "reel") == "video":
            block = _video_rules() + "\n\n" + block
        if note.strip():
            # first, before the script (whatever reads the script reads to the end)
            block = ("REVIEWER'S NOTE — the scenes are being redrawn because of this; answer it "
                     "while keeping every rule:\n" + note.strip() + "\n\n" + block)
        if len(batches) > 1:
            log(f"  scenes: batch {n} of {len(batches)} ({only[0]}-{only[-1]})")
        draft = ask_json(system_prompt(), block, MotionScenesDraft,
                         max_tokens=12000, label="motion_scenes")
        if len(batches) > 1:
            # a shot outside this batch is another call's to design
            draft = draft.model_copy(update={"shots": [s for s in draft.shots if s.id in only]})
        out = _apply(out, draft)
    results = checks.run_motion_scene_graders(out)
    failing = _failing_shots(out, results)
    _record(attempts, "first", out, results, failing)
    for attempt in range(config.MAX_MOTION_SCENE_RETRIES):
        if not failing:
            return out, results
        log(f"  scenes: {len(failing)} of {len(out.shots)} shot(s) failing — repair {attempt + 1}:")
        for sid, why in failing.items():
            log(f"    {sid}: {'; '.join(why)[:300]}")
        ids = list(failing)
        video = getattr(script, "format", "reel") == "video"
        # a video's repairs go in batches too (a long video may have many failing shots)
        groups = ([ids[k:k + VIDEO_SCENE_BATCH] for k in range(0, len(ids), VIDEO_SCENE_BATCH)]
                  [:VIDEO_REPAIR_BATCHES] if video else [ids])
        for group in groups:
            reasons = "\n".join(f"- {sid}: {'; '.join(failing[sid])}" for sid in group)
            user = ((_video_rules() + "\n\n" if video else "")
                    + _script_block(out, only=group) + "\n\nTHE CURRENT SCENES OF THESE SHOTS "
                    "FAILED REVIEW:\n" + reasons + "\n\nTHE CURRENT SCENES:\n" +
                    json.dumps({s.id: s.scene.model_dump() if s.scene else None
                                for s in out.shots if s.id in group}))
            fix = ask_json(system_prompt(repair=True), user, MotionScenesDraft,
                           max_tokens=12000 if video else 6000, label="motion_scenes_repair")
            if video:
                fix = fix.model_copy(update={"shots": [s for s in fix.shots if s.id in group]})
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
