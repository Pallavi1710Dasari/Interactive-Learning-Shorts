"""
A stub motion script for ANY material, template and theme (SHORTS_STUB=1).

The stub used to answer the motion script call only from a golden fixture
whose concept the material teaches AND whose template and theme were the ones
asked for. Anything else raised NotImplementedError — so a stub run on a
user's own upload ("What is a dynamic web application?", mentor_student,
2026-10-12) stopped with an error at the shot list, though nothing was wrong
but the stub. Stub mode exists so a whole reel can be made for free on any
material; it must not dead-end there.

The golden fixtures still win when one fits (their tests depend on them). For
everything else this builds a draft mechanically from the selected section:
the concept is the section's most-used code name (or bold term), the code
map shows its real lines, a few of the section's own short plain sentences
carry the explanation, and the rest is plain stub wording. Every line obeys
the same rules the real writer is graded by — beats, speakers, word budgets,
caption sentences, plain words, numbers — so the free graders pass it, and
the reel goes on to scenes, voice, timing and the player. The wording is
placeholder text, which a stub reel always is.
"""
from __future__ import annotations

import re
from collections import Counter

from . import checks
from .schema import MOTION_WALKTHROUGH_CLOSING, MOTION_WALKTHROUGH_OPENING

#: Icons every stub recap uses (all in the scene library).
_ICONS = (("refresh", "The problem"), ("memory", "The reason"), ("bolt", "The fix"))


# ================================================================ material

def material_of(user: str) -> str:
    """The selected section's text from the script prompt's MATERIAL block."""
    m = re.search(r"\nMATERIAL \(.*?\):\n(.*?)(?=\n(?:SUPPORTING|CORE IDEA|KEY POINTS|THE APPROVED"
                  r"|RULED OUT|SERIES)|\Z)", user, re.S)
    return (m.group(1) if m else user).strip()


def _code_blocks(text: str) -> list[str]:
    return re.findall(r"```[^\n]*\n(.*?)```", text, re.S)


def pick_concept(text: str) -> str:
    """The section's concept: its most-used `code name`, else its most-used
    **bold term**, else the longest word of its first sentence."""
    code = Counter(re.sub(r"\(.*$", "", t).strip()
                   for t in re.findall(r"`([^`\n]{2,40})`", text))
    code = Counter({k: v for k, v in code.items()
                    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", k) and len(k) <= 24})
    if code:
        return code.most_common(1)[0][0]
    bold = Counter(t.strip() for t in re.findall(r"\*\*([^*\n]{2,30})\*\*", text)
                   if re.fullmatch(r"[A-Za-z][A-Za-z ]*", t.strip()) and len(t.split()) <= 2)
    if bold:
        return bold.most_common(1)[0][0]
    words = re.findall(r"[A-Za-z]{4,}", text)
    return max(words[:40], key=len) if words else "this idea"


def spoken(concept: str) -> str:
    """The concept spelled for text-to-speech: useState -> "use State"."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", concept)
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", s).split())


def shown(concept: str) -> str:
    """The concept as a caption shows it: real code in backticks."""
    return f"`{concept}`" if spoken(concept) != concept else concept


def _plain_sentences(text: str, concept: str) -> list[str]:
    """The section's own short, plain sentences: no code, no markup, no
    question, at most 14 words and none over four syllables (the concept
    aside) — lines the graders accept as both speech and caption."""
    prose = re.sub(r"```.*?```", " ", text, flags=re.S)
    out = []
    for line in prose.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "|", ">")) or "`" in line:
            continue
        line = re.sub(r"^([-*+]|\d+\.)\s+", "", line)
        line = re.sub(r"\*\*?([^*]+)\*\*?", r"\1", line)
        for s in checks._sentences(line):
            words = s.split()
            if not 5 <= len(words) <= 14 or not s.endswith("."):
                continue
            if re.search(r"[?:;()\[\]{}<>=→/\\\"“”]|\d", s):
                continue
            if any(checks._is_code_token(w) for w in words):
                continue
            if any(checks._syllables(w) > checks.MOTION_MAX_SYLLABLES
                   and checks._motion_key(w) != checks._motion_key(concept) for w in words):
                continue
            # a technical term the sentence does not explain itself would
            # fail check_motion_terms_explained
            if checks.terms_used(s) and not any(c in f" {s.lower()} " for c in checks.MOTION_DEFINER_CUES):
                continue
            if len(words) >= 10 and checks._fk_grade([s]) > checks.MOTION_MAX_SENTENCE_GRADE:
                continue                          # too hard for a beginner (reading level)
            out.append(s)
    return out


def _code_lines(text: str, concept: str) -> list[str]:
    """Up to three of the section's own code lines that use the concept,
    each short enough for a code shot."""
    lines = [ln.strip() for block in _code_blocks(text) for ln in block.splitlines()]
    fit = [ln for ln in lines if concept in ln and 0 < len(ln) <= checks.MOTION_MAX_CODE_CHARS]
    if fit:
        return fit[:checks.MOTION_MAX_CODE_LINES]
    # the material shows code (a block or an inline `span`): the code map must too
    return [concept[:checks.MOTION_MAX_CODE_CHARS]] if checks._source_has_code(text) else []


# ===================================================================== hook

def _hook_sentence(openers: tuple[str, ...], question: bool, lo: int = 8, hi: int = 10) -> str:
    """A hook opening with one of `openers`, naming a visible symptom
    ("stuck", "never", "won't"), never the concept, in `lo`-`hi` words."""
    tails = {
        "does": "your code stay stuck", "doesn't": "your code ever change",
        "do": "your changes never show", "don't": "my changes ever show",
        "is": "your code stuck", "are": "your changes stuck",
        "won't": "your code ever change", "can't": "your code ever change",
        "with": "code that never changes", "when": "your code stays stuck",
    }
    pads = ("", " on screen", " when you try it", " every time you try it")
    end = "?" if question else "."
    for opener in openers:
        tail = tails.get(opener.split()[-1], "your code stays stuck")
        for pad in pads:
            text = f"{opener} {tail}{pad}{end}"
            if lo <= len(text.split()) <= hi:
                return text[0].upper() + text[1:]
    return "Why does your code stay stuck every time you try?"


def _explain(concept: str, sp: str) -> list[str]:
    """The fix's first line: the concept named, and explained in plain words
    when it is a technical term (check_motion_terms_explained)."""
    term = checks.terms_used(sp)
    if term:
        meaning = next(iter(term.values()))["meaning"]
        return [f"{sp} means {meaning}.", "That fixes this."]
    return [f"{sp} fixes this."]


# ================================================================ fix_story

def _fix_story(text: str, concept: str, theme) -> dict:
    sp, sh = spoken(concept), shown(concept)
    mine = _plain_sentences(text, concept)
    lines = iter(mine)

    def own(fallback: str) -> str:
        return next(lines, fallback)

    if theme is not None and not theme.base:
        hook = _hook_sentence(tuple(theme.hook.openers), theme.hook.style == "question")
    else:
        hook = _hook_sentence(("why does", "why doesn't"), True)
    question = hook if hook.endswith("?") else "Why does your code stay stuck every time?"
    beats = [
        ("hook", [hook]),
        ("title", ["This is the one idea that fixes it."]),
        ("setup", ["Here is the code a beginner writes first.",
                   "It looks fine, but it does not work."]),
        ("break_1", [own("The first reason is simple."),
                     "Nothing tells the program that something changed."]),
        ("break_2", [own("There is a second reason too."),
                     "The old value is all you ever see."]),
        ("fix_idea", _explain(concept, sp) + ["It keeps the value and passes on the change."]),
        ("fix_flow", [f"With {sp}, you make the change.", own("Then the result updates right away.")]),
        # names what its screen shows: the code, or (no code) the problem and the fix
        ("code_map", [f"In code, {sp} is the part that fixes the problem."]),
        ("payoff", ["Now it works.", "The result changes the moment you act."]),
        ("recap", [f"Remember the problem, the reason, and the fix with {sp}."]),
        ("cta", ["Follow for more, one idea at a time."]),
    ]
    code = _code_lines(text, concept)
    shots = []
    for beat, said in beats:
        caps = [s.replace(sp, sh) if sp != concept else s for s in said]
        shots.append({"beat": beat, "speech": " ".join(said), "captions": caps,
                      "code": code if beat == "code_map" else [],
                      "visual": f"Stub scene for the {beat.replace('_', ' ')}."})
    return {
        "hook_question": question, "concept_name": concept,
        "promise": "One idea that fixes it",
        "icon_vocabulary": [{"name": n, "label": l} for n, l in _ICONS],
        "takeaways": [{"icon": "refresh", "line": "The problem", "sub": "it stays stuck"},
                      {"icon": "memory", "line": "The reason", "sub": "nothing tracks it"},
                      {"icon": "bolt", "line": concept, "sub": "the fix"}],
        "shots": shots, "chapters": [], "running_example": None,
    }


# ============================================================== walkthrough

def _walkthrough(text: str, concept: str) -> dict:
    sp, sh = spoken(concept), shown(concept)
    mine = _plain_sentences(text, concept)
    lines = iter(mine)

    def own(fallback: str) -> str:
        return next(lines, fallback)

    titles = [concept, f"{concept} again"]
    states = [[concept], [concept]]
    shots = [
        ("hook", ["How does this really work?", "It is simpler than it looks."], None, None),
        ("name_it", [f"This is called {sp}."], None, None),
        ("example", [f"Let's follow one example, {sp}.", "Watch what each step does to it."],
         None, states[0]),
    ]
    for n, (title, state) in enumerate(zip(titles, states), start=1):
        word = ["one", "two"][n - 1]
        shots.append(("chapter_card", [f"Step {word}. {spoken(title)}."], n, None))
        shots.append(("chapter", [own("Here is what happens first."),
                                  own("Each part has its own small job.")], n, state))
        shots.append(("chapter", [own("Then the next part takes over."),
                                  "Follow it one step at a time."], n, state))
    shots += [
        ("result", ["So the example went from start to finish, one step at a time."], None, states[-1]),
        ("takeaway", [f"So reach for {sp} when you need this to work."], None, None),
        ("recap", [f"{sp} in two steps, from the start to the finish."], None, states[-1]),
        ("cta", ["Follow for more, one idea at a time."], None, None),
    ]
    out = []
    for beat, said, chapter, example in shots:
        caps = [s.replace(sp, sh) if sp != concept else s for s in said]
        out.append({"beat": beat, "chapter": chapter, "speech": " ".join(said),
                    "captions": caps, "example": example or [], "code": [],
                    "visual": f"Stub scene for the {beat.replace('_', ' ')}."})
    return {
        "hook_question": "How does this really work?", "concept_name": concept,
        "promise": "Step by step",
        "icon_vocabulary": [], "takeaways": [],
        "running_example": {"text": concept, "items": states[0]},
        "chapters": [{"n": n, "title": t, "example_in": states[0] if n == 1 else states[n - 2],
                      "example_out": s} for n, (t, s) in enumerate(zip(titles, states), start=1)],
        "shots": out,
    }


# ================================================================== video

#: Plain stub lines for a long video's chapter shots: short, beginner-level,
#: no numbers and no technical terms, so every free grader accepts them.
_VIDEO_LINES = (
    "Here is the part that matters most.", "Take it slowly and watch each change.",
    "Each piece has its own small job.", "Then the next piece takes over from there.",
    "Look at what stays the same.", "Now look at what has changed.",
    "This is where most people get stuck.", "Keep this picture in your head.",
    "It helps to say it out loud.", "You can check it with a tiny test.",
    "The rule is short and easy to keep.", "Try it once and it will stick.",
    "Notice how the shape of it grows.", "Nothing here is magic at all.",
    "We build it up one small step at a time.", "Every step leans on the step before.",
    "So far the idea holds up well.", "Here is a small case to try.",
    "Watch the left side and then the right.", "The same idea works in a new place.",
    "A common slip is to skip this part.", "When that happens the result looks wrong.",
    "The fix is to go back one step.", "Now it works the way you want.",
    "Use it when the task fits this shape.", "Leave it out when a simple way is enough.",
    "That is the whole trick in plain words.", "Let's link this to the next part.",
)
_VIDEO_TITLES = ("The problem it solves", "The core idea", "How it starts", "How it grows",
                 "A second example", "Common mistakes")
_STEP_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")


def _video(text: str, concept: str) -> dict:
    """A stub long-form video (format "video"): the walkthrough's beats with
    six chapters of seven shots, about seven minutes spoken. The first three
    chapters carry the running example; the rest teach with their own."""
    sp, sh = spoken(concept), shown(concept)
    mine = iter(_plain_sentences(text, concept))
    pool = iter(_VIDEO_LINES * 8)

    def line() -> str:
        return next(mine, None) or next(pool)

    state = [concept]
    shots = [
        ("hook", ["How does this really work under the hood?",
                  "Once you see it, you will use it every day."], None, None),
        ("name_it", [f"This is called {sp}."], None, None),
        ("example", [f"Let's follow one example, {sp}.", "Watch what each step does to it."],
         None, state),
    ]
    chapters = []
    for n, title in enumerate(_VIDEO_TITLES, start=1):
        carries = n <= 3
        chapters.append({"n": n, "title": title, "example_in": state if carries else [],
                         "example_out": state if carries else []})
        shots.append(("chapter_card", [f"Step {_STEP_WORDS[n - 1]}. {title}."], n, None))
        for k in range(7):
            shots.append(("chapter", [line(), line(), line()], n,
                          state if carries and k in (0, 6) else None))
    shots += [
        ("result", ["So the example went from start to finish, one step at a time."], None, state),
        ("takeaway", [f"So reach for {sp} when you need this to work."], None, None),
        ("recap", [f"{sp} in six steps, from the start to the finish."], None, state),
        ("cta", ["Follow for more, one idea at a time."], None, None),
    ]
    out = []
    for beat, said, chapter, example in shots:
        caps = [x.replace(sp, sh) if sp != concept else x for x in said]
        out.append({"beat": beat, "chapter": chapter, "speech": " ".join(said),
                    "captions": caps, "example": example or [], "code": [],
                    "visual": f"Stub scene for the {beat.replace('_', ' ')}."})
    return {
        "hook_question": "How does this really work under the hood?", "concept_name": concept,
        "promise": "Step by step, in depth",
        "icon_vocabulary": [], "takeaways": [],
        "running_example": {"text": concept, "items": state},
        "chapters": chapters,
        "shots": out,
    }


def video_draft(user: str, theme_id: str | None) -> dict:
    """A MotionScriptDraft (as a dict) for a long-form video of `user`'s material."""
    from .motion_themes import registry
    theme = registry().get(theme_id) if theme_id else None
    text = material_of(user)
    body = _video(text, pick_concept(text))
    for i, x in enumerate(body["shots"], start=1):
        x["id"] = f"s{i:02d}"
    return _with_speakers(body, theme)


# ================================================================ speakers

def _with_speakers(draft: dict, theme) -> dict:
    """A two-speaker theme: every caption labelled, each beat opened by the
    first speaker its beat template names, then alternating."""
    if theme is None or not theme.two_speaker:
        for s in draft["shots"]:
            s["captions"] = [{"text": c} for c in s["captions"]]
        return draft
    beats = theme.beats if isinstance(theme.beats, dict) else {}
    for s in draft["shots"]:
        allowed = beats[s["beat"]].speakers if s["beat"] in beats else theme.roles
        s["captions"] = [{"text": c, "speaker": allowed[i % len(allowed)]}
                         for i, c in enumerate(s["captions"])]
    return draft


def draft(user: str, template: str, theme_id: str | None) -> dict:
    """A MotionScriptDraft (as a dict) for the material in `user`."""
    from .motion_themes import registry
    theme = registry().get(theme_id) if theme_id else None
    text = material_of(user)
    concept = pick_concept(text)
    body = _walkthrough(text, concept) if template == "walkthrough" else _fix_story(text, concept, theme)
    if template == "walkthrough":
        assert [s["beat"] for s in body["shots"][:3]] == list(MOTION_WALKTHROUGH_OPENING)
        assert [s["beat"] for s in body["shots"][-4:]] == list(MOTION_WALKTHROUGH_CLOSING)
    for i, s in enumerate(body["shots"], start=1):
        s["id"] = f"s{i:02d}"
    return _with_speakers(body, theme)
