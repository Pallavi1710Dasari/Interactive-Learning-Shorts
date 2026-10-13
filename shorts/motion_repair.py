"""
Rejected motion scripts: saved, regraded, and repaired in code.

plain_variable_no_rerender__motion (2026-10-12) spent seven Opus script calls
on drafts the graders rejected for reasons that were the graders' own bugs,
and every draft was thrown away — so when the graders were fixed there was
nothing to regrade, and the only way on was to pay again. Now:

  - every rejected draft is saved to output/<short_id>/rejected/, with the
    failures that rejected it (save_rejected);
  - before the script stage asks for money, the saved drafts are regraded
    with today's graders, and one that passes — as it is, or after a
    mechanical repair — is used with no call at all (best_saved);
  - after a failed attempt, a failure that is only mechanical is repaired in
    code and regraded before another attempt is paid for (try_mechanical).

A repair never invents content. It only re-cuts captions the model already
wrote: one caption per spoken sentence, and plain-word captions rebuilt from
the speech they must match. Whatever it produces is regraded by every
grader, and the shot-list gate still shows it to the reviewer.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from . import checks, config
from .schema import CaptionChunk, MotionScript, motion_plain_text

#: Graders a caption re-cut can satisfy. A failure from any other grader
#: (beats, length, facts, the hook, the example) needs the writer.
MECHANICAL_GRADERS = frozenset({"motion_caption_sentences", "motion_captions_match_speech"})

Grade = Callable[[MotionScript], list]


def rejected_dir(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "rejected"


def save_rejected(script: MotionScript, results: list, kind: str = "script") -> Path:
    """Write one rejected draft and why it was rejected. `kind` is "script"
    (a full attempt), "hook_fix" (a hook-only rewrite) or "repaired" (a
    mechanical repair that still failed)."""
    folder = rejected_dir(script.short_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = folder / f"{stamp}_{kind}.json"
    path.write_text(json.dumps({
        "saved_at": stamp,
        "kind": kind,
        "template": script.template,
        "theme": script.theme,
        "source_section_id": script.source_section_id,
        "failures": [{"grader": r.name, "reason": r.reason}
                     for r in results if not r.passed],
        "script": script.model_dump(mode="json"),
    }, indent=2), encoding="utf-8")
    return path


def is_mechanical(results: list) -> bool:
    failed = [r for r in results if not r.passed]
    return bool(failed) and all(r.name in MECHANICAL_GRADERS for r in failed)


def _split_caption(c: CaptionChunk) -> list[CaptionChunk] | None:
    """One caption holding several sentences, as one caption per sentence.
    None when a split would cut a <b> highlight or a code span."""
    plain = motion_plain_text(c.text)
    if len(checks._sentences(plain)) < 2:
        return [c]
    pieces, start = [], 0
    for m in checks._MOTION_SENTENCE_END.finditer(c.text):
        piece = c.text[start:m.end()].strip()
        if piece:
            pieces.append(piece)
        start = m.end()
    tail = c.text[start:].strip()
    if tail:
        pieces.append(tail)
    for p in pieces:
        if p.count("<b>") != p.count("</b>") or p.count("`") % 2:
            return None
    return [CaptionChunk(text=p, speaker=c.speaker) for p in pieces]


def _captions_from_speech(shot) -> list[CaptionChunk] | None:
    """A shot's captions rebuilt as its speech, one caption per sentence,
    keeping each highlighted word that is still said. Only for captions of
    plain words: a caption that shows code says it differently from the
    speech, and only the writer knows which code to show."""
    words = [w for c in shot.captions for w in checks._motion_words(c.text)]
    if any(checks._is_code_token(w) or "`" in w for w in words):
        return None
    speakers = {c.speaker for c in shot.captions}
    if len(speakers) > 1:
        return None
    speaker = next(iter(speakers), None)
    highlights = [h.strip() for c in shot.captions for h in re.findall(r"<b>(.*?)</b>", c.text)]
    out = []
    for sentence in checks._sentences(shot.speech.strip()):
        text, used = sentence, 0
        for h in highlights:
            if used == checks.MOTION_MAX_HIGHLIGHTS:
                break
            m = re.search(rf"(?<![\w<]){re.escape(h)}(?!\w)", text)
            if h and m and "<b>" not in text[max(0, m.start() - 3):m.start()]:
                text = text[:m.start()] + f"<b>{h}</b>" + text[m.end():]
                used += 1
        out.append(CaptionChunk(text=text, speaker=speaker))
    return out or None


def repair(script: MotionScript, results: list) -> MotionScript | None:
    """The script with its mechanical caption failures re-cut, or None when
    there is nothing a re-cut can change."""
    failed = {r.name: r for r in results if not r.passed}
    bad_match = set(failed["motion_captions_match_speech"].details.get("shots", [])) \
        if "motion_captions_match_speech" in failed else set()
    bad_split = set(failed["motion_caption_sentences"].details.get("shots", [])) \
        if "motion_caption_sentences" in failed else set()
    changed = False
    shots = []
    for s in script.shots:
        captions = list(s.captions)
        if s.id in bad_split:
            split: list[CaptionChunk] = []
            for c in captions:
                parts = _split_caption(c)
                split.extend(parts if parts is not None else [c])
            if split != captions:
                captions, changed = split, True
        if s.id in bad_match:
            rebuilt = _captions_from_speech(s)
            if rebuilt is not None and rebuilt != captions:
                captions, changed = rebuilt, True
        shots.append(s.model_copy(update={"captions": captions}) if captions != s.captions else s)
    return script.model_copy(update={"shots": shots}) if changed else None


def try_mechanical(script: MotionScript, results: list, grade: Grade,
                   save: bool = True) -> tuple[MotionScript, list] | None:
    """When every failure is mechanical: repair, regrade, and return the
    repaired script and its results if it now passes every grader. A repair
    that still fails is saved with the rejected drafts (unless `save` is
    False: regrading drafts already on disk saves nothing new)."""
    if not is_mechanical(results):
        return None
    fixed = repair(script, results)
    if fixed is None:
        return None
    fixed_results = grade(fixed)
    if checks.all_passed(fixed_results):
        return fixed, fixed_results
    if save:
        save_rejected(fixed, fixed_results, kind="repaired")
    return None


def saved_drafts(short_id: str, template: str, theme: str | None,
                 section_id: str) -> list[tuple[Path, MotionScript]]:
    """This reel's saved rejected drafts written for the same template, theme
    and section, newest first. A draft that no longer loads is skipped."""
    folder = rejected_dir(short_id)
    if not folder.exists():
        return []
    out = []
    for path in sorted(folder.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            script = MotionScript(**data["script"])
        except Exception:
            continue
        if (script.template, script.theme, script.source_section_id) == (template, theme,
                                                                          section_id):
            out.append((path, script))
    return out


def best_saved(short_id: str, template: str, theme: str | None, section_id: str,
               grade: Grade) -> tuple[MotionScript, list, Path, bool] | None:
    """The newest saved draft that passes today's graders, as it is or after
    a mechanical repair: (script, results, the file it came from, repaired?).
    None when no saved draft passes. Free: no call is made."""
    for path, script in saved_drafts(short_id, template, theme, section_id):
        results = grade(script)
        if checks.all_passed(results):
            return script, results, path, False
        fixed = try_mechanical(script, results, grade, save=False)
        if fixed is not None:
            return fixed[0], fixed[1], path, True
    return None
