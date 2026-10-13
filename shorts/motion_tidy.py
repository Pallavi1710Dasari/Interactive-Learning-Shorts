"""
Deterministic clean-ups of a motion reel's scenes, run by the timing stage
before the plan is written (so they apply to every new reel, and to a saved
reel when its plan is rebuilt). Nothing here calls a model.

  - the CTA's end card gets word-cued actions over its whole length: Follow
    pressed on "follow", the Up next card on "next", the hashtags one per
    word after it, a final settle on the last word;
  - on the REAL audio clock, any stretch that would hold still longer than
    the cadence limit gets an action cued on a word spoken there.

Each function returns what it changed as plain notes for the timing report.
"""
import re

from .schema import MotionSceneAction, MotionScript, MotionShot


# ============================================================ the CTA

def _words(shot: MotionShot) -> list[str]:
    from .motion_timeline import caption_words
    return [re.sub(r"[^\w'@#-]", "", w) for c in shot.captions for w, _ in caption_words(c.text)]


def cta_actions(shot: MotionShot, n_tags: int) -> list[MotionSceneAction]:
    """The end card's timeline, every step on a spoken word: the card at the
    start, Follow pressed on "follow", the Up next card on "next", each
    hashtag on the next word after it, and a settle on the last word."""
    from .motion_scenes import _key
    words = _words(shot)
    keys = [_key(w) for w in words]
    oid = shot.scene.objects[0].id
    acts = [MotionSceneAction(at="start", do="enter", target=oid)]
    used: list[int] = []

    def cue_at(i: int) -> str:
        # one word, made unique going forward by taking the next words too
        for n in (1, 2, 3):
            phrase = " ".join(w for w in words[i:i + n] if w)
            k = [_key(x) for x in phrase.split()]
            first = next((j for j in range((used[-1] + 1) if used else 0, len(keys) - len(k) + 1)
                          if keys[j:j + len(k)] == k), None)
            # the same words as the action before would happen WITH it (resolve_cues)
            same = [_key(x) for x in acts[-1].at.split()] == k
            if first == i and not same:
                return phrase
        return ""

    def add(i: int, do: str, value: str | None = None) -> None:
        if i is None or i < 0 or i >= len(words) or (used and i <= used[-1]):
            return
        cue = cue_at(i)
        if cue:
            acts.append(MotionSceneAction(at=cue, do=do, target=oid, value=value))
            used.append(i)

    follow = next((i for i, k in enumerate(keys) if k.startswith("follow")), None)
    nxt = next((i for i, k in enumerate(keys) if k == "next" and (follow is None or i > follow)), None)
    if follow is None:
        follow = 0 if keys else None
    add(follow, "tap")
    if nxt is None and follow is not None:
        nxt = min(len(keys) - 1, follow + 2)
    add(nxt, "reveal")
    after = [i for i in range((nxt if nxt is not None else 0) + 1, len(keys) - 1) if len(keys[i]) >= 3]
    for j, i in enumerate(after[:n_tags]):
        add(i, "highlight", str(j + 1))
    add(len(keys) - 1, "pulse")
    return acts


def cue_cta(script: MotionScript, n_tags: int) -> tuple[MotionScript, list[str]]:
    shots, notes = [], []
    for sh in script.shots:
        sc = sh.scene
        if sh.beat == "cta" and sc is not None and len(sc.objects) == 1 and sc.objects[0].kind == "end_card":
            acts = cta_actions(sh, n_tags)
            sh = sh.model_copy(update={"scene": sc.model_copy(update={"actions": acts})})
            notes.append(f"{sh.id}: end card cued on its words — "
                         + ", ".join(f"{a.do}@{a.at}" for a in acts[1:]))
        shots.append(sh)
    return script.model_copy(update={"shots": shots}), notes


# ============================================================ all of it

def tidy(script: MotionScript, n_tags: int = 4) -> tuple[MotionScript, list[str]]:
    """Every clean-up above that needs no audio."""
    return cue_cta(script, n_tags)


def fill_cadence(script: MotionScript, clocks) -> tuple[MotionScript, list[str]]:
    """On the real clock: every shot that would hold still past the cadence
    limit gets actions cued on words spoken in the still stretch."""
    from .motion_scenes import MAX_STILL_SECONDS, fill_cadence_on_clock, longest_still
    shots, notes = [], []
    for sh, clock in zip(script.shots, clocks):
        if sh.scene is not None:
            gap, _ = longest_still(sh, clock)
            if gap > MAX_STILL_SECONDS:
                new = fill_cadence_on_clock(sh, clock)
                after, at = longest_still(new, clock)
                added = len(new.scene.actions) - len(sh.scene.actions)
                if added:
                    notes.append(f"{sh.id}: {added} word-cued action(s) added — still "
                                 f"{gap:.1f}s -> {after:.1f}s")
                sh = new
        shots.append(sh)
    return script.model_copy(update={"shots": shots}), notes
