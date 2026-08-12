"""
Code graders. Deterministic, free, instant. These run BEFORE any paid step.

Every grader takes an object and returns a GraderResult. Never raise — a grader
that crashes tells you nothing; a grader that returns passed=False with a reason
tells you what to fix.
"""
import re
from dataclasses import dataclass, field
from .schema import (
    Script, ShortUnit, MIN_SECONDS, MAX_SECONDS,
    MAX_OVERLAY_WORDS, WORDS_PER_SECOND,
)


@dataclass
class GraderResult:
    name: str
    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)

    def __str__(self):
        mark = "PASS" if self.passed else "FAIL"
        return f"[{mark}] {self.name}" + (f" — {self.reason}" if self.reason else "")


def check_timing(script: Script) -> GraderResult:
    """The single most valuable check in the pipeline. Runs in microseconds."""
    secs = script.estimated_seconds
    if secs < MIN_SECONDS:
        return GraderResult("timing", False,
            f"too short: {secs}s ({script.word_count} words). Need >= {MIN_SECONDS}s "
            f"(~{int(MIN_SECONDS * WORDS_PER_SECOND)} words).",
            {"seconds": secs, "words": script.word_count})
    if secs > MAX_SECONDS:
        return GraderResult("timing", False,
            f"too long: {secs}s ({script.word_count} words). Need <= {MAX_SECONDS}s "
            f"(~{int(MAX_SECONDS * WORDS_PER_SECOND)} words).",
            {"seconds": secs, "words": script.word_count})
    return GraderResult("timing", True, f"{secs}s ({script.word_count} words)",
                        {"seconds": secs, "words": script.word_count})


def check_overlays(script: Script) -> GraderResult:
    """On-screen text must be readable at a glance on a phone."""
    bad = [(i, b.on_screen, len(b.on_screen.split()))
           for i, b in enumerate(script.beats) if len(b.on_screen.split()) > MAX_OVERLAY_WORDS]
    if bad:
        worst = ", ".join(f"beat {i}: {n} words" for i, _, n in bad)
        return GraderResult("overlays", False,
            f"{len(bad)} overlay(s) over {MAX_OVERLAY_WORDS} words ({worst})",
            {"offenders": bad})
    return GraderResult("overlays", True, f"all {len(script.beats)} overlays within limit")


MIN_ANSWERS = 3
MAX_ANSWERS = 5
MAX_ANSWER_WORDS = 32


def check_dialogue_shape(script: Script) -> GraderResult:
    """
    One question, then the answer in 3 to 5 short parts.

    A single continuous answer was tried and rejected in review: it read as a wall
    of text, left one diagram on screen for ~40 seconds, and gave the model enough
    rope to drift off the source. Splitting the answer gives each idea its own
    visual and keeps every spoken chunk short.
    """
    speakers = [b.speaker for b in script.beats]
    if speakers[0] != "interviewer":
        return GraderResult("dialogue_shape", False, "first beat is not the interviewer")
    if speakers.count("interviewer") != 1:
        return GraderResult("dialogue_shape", False,
            f"{speakers.count('interviewer')} interviewer beats — ask exactly one question")

    answers = speakers.count("student")
    if answers < MIN_ANSWERS:
        return GraderResult("dialogue_shape", False,
            f"only {answers} answer beat(s) — split the answer into at least {MIN_ANSWERS} "
            "so each idea gets its own visual")
    if answers > MAX_ANSWERS:
        return GraderResult("dialogue_shape", False,
            f"{answers} answer beats is too choppy — use at most {MAX_ANSWERS}")

    # A "split" answer with one giant beat is still a wall of text.
    long_beats = [(i, len(b.line.split())) for i, b in enumerate(script.beats)
                  if b.speaker == "student" and len(b.line.split()) > MAX_ANSWER_WORDS]
    if long_beats:
        worst = ", ".join(f"beat {i}: {n} words" for i, n in long_beats)
        return GraderResult("dialogue_shape", False,
            f"{len(long_beats)} answer beat(s) over {MAX_ANSWER_WORDS} words ({worst}) — "
            "keep each one to a single idea")

    return GraderResult("dialogue_shape", True, f"{answers} answer beats, all concise")


# --------------------------------------------------------------------- grounding
#
# The first real pipeline run abandoned 2 of 5 topics and forced 6 retries, and
# almost every word grounding called "invented" was a false positive of one of
# three kinds. All three are fixed below, and none of them relax what the grader
# is actually for — catching wholesale invention:
#
#   1. Punctuation. Splitting on whitespace and stripping only .,;:()"'?! left
#      em-dash compounds intact, so "crash—when" and "entry—is" were single
#      tokens that could never match anything. Tokenising on non-alphanumerics
#      fixes those and contractions ("isn't" -> "isn", "t") for free.
#   2. Word form. The source says "concatenates", "indexes", "bit", "double",
#      "cache"; scripts naturally say "concatenation", "index", "bits",
#      "doubling", "cached". Light stemming makes those match.
#   3. Discourse words. "actually", "already", "instead", "matter", "mean" are
#      not factual claims, but they are longer than 3 characters and were absent
#      from the stop list, so they counted as invented content and dragged the
#      score down.
#
# Deliberately still flagged: genuine paraphrase that leaves the source's
# vocabulary ("crash", "error", "arithmetic", "lookup"). Those are the signal.

_TOKEN = re.compile(r"[a-z0-9]+")

# Contractions were leaking through as invented content words. Splitting on
# non-alphanumerics turns "doesn't" into "doesn" + "t"; "t" is dropped by the
# length filter but "doesn" survives it and matches nothing in the source, so the
# grader reported it as a fabricated claim. Same for aren/wasn/weren/haven/didn.
# Strip the contraction instead, leaving the real word ("does", "are", "was").
_CONTRACTION = re.compile(r"n[’']t\b|[’'](s|re|ve|ll|d|m)\b", re.I)

# Longest first — "ations" must be tried before "ation", and both before "s".
_SUFFIXES = (
    ("ations", "at"), ("ation", "at"),
    ("ions", ""), ("ion", ""),
    ("ings", ""), ("ing", ""),
    ("ies", "y"), ("ied", "y"),
    ("es", ""), ("ed", ""), ("ly", ""), ("s", ""),
)

_STOP_WORDS = {
    # original set
    "the","a","an","is","are","was","were","be","been","to","of","in","on","for","and",
    "or","but","that","this","it","its","as","with","by","from","at","which","when",
    "so","if","then","than","can","will","would","not","no","do","does","you","your",
    "we","they","their","there","what","how","why","because","into","each","every",
    # discourse and filler words surfaced by the first real run
    "about","above","actually","after","again","all","already","also","always","another",
    "any","anything","being","below","best","better","big","bigger","both","come","comes",
    "could","did","different","difference","doing","done","during","else","end","ends",
    "enough","even","ever","exactly","few","first","fix","fixes","full","fully","get",
    "gets","getting","give","gives","going","good","had","has","have","having","help",
    "here","however","instead","just","keep","kept","know","less","let","like","little",
    "look","looks","made","make","makes","many","match","matter","may","mean","means",
    "might","more","most","much","must","need","needs","never","new","next","now","off",
    "often","once","only","other","others","our","out","over","own","put","quite","rather",
    "really","right","same","say","says","see","seen","should","simply","since","some",
    "something","still","such","sure","take","takes","tell","them","these","thing","things",
    "think","those","though","through","thus","together","too","took","under","until","up",
    "upon","use","used","uses","using","very","want","way","well","went","where","whether",
    "while","who","with","within","without","work","works","yet",
    # hedges and meta words a spoken script naturally uses; none is a factual claim
    "basically","certainly","clearly","directly","effectively","essentially","extra",
    "fairly","generally","indeed","largely","likely","maybe","mostly","obviously",
    "overall","partly","perhaps","possible","possibly","pretty","probably","roughly",
    "takeaway","therefore","truly","typically","ultimately","usually","independently",
}


def _stem(word: str) -> str:
    """Crude suffix stripper. Good enough to match a word to its own inflections."""
    for suffix, replacement in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            word = word[: -len(suffix)] + replacement
            break
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]          # cache/cached, double/doubling
    return word


_STOP_STEMS = {_stem(w) for w in _STOP_WORDS}


def _stems(text: str) -> dict[str, str]:
    """Map each content stem to one word that produced it, for readable reporting."""
    out: dict[str, str] = {}
    for word in _TOKEN.findall(_CONTRACTION.sub("", text.lower())):
        stem = _stem(word)
        if stem and stem not in _STOP_STEMS:
            out.setdefault(stem, word)
    return out


def _grounded(stem: str, source_stems: set[str]) -> bool:
    if stem in source_stems:
        return True
    # Stemming is crude, so allow a prefix match where both sides are long enough
    # for it to mean something ("proces" vs "process", "addres" vs "address").
    return any(
        (stem.startswith(s) or s.startswith(stem)) and min(len(stem), len(s)) >= 5
        for s in source_stems
    )


def check_grounding(script: Script, source_text: str, min_overlap: float = 0.55) -> GraderResult:
    """
    Cheap faithfulness proxy. Not a replacement for the LLM judge — it catches
    wholesale invention, not subtle errors. Compares content words in the script
    against content words in the source section, after normalising both sides.
    """
    src = set(_stems(source_text))
    spoken = {s: w for s, w in _stems(" ".join(b.line for b in script.beats)).items()
              if len(s) > 3}
    if not spoken:
        return GraderResult("grounding", False, "no content words in the script")

    unknown = sorted(spoken[s] for s in spoken if not _grounded(s, src))
    overlap = 1 - (len(unknown) / len(spoken))
    if overlap < min_overlap:
        return GraderResult("grounding", False,
            f"only {overlap:.0%} of content words appear in the source section. "
            f"Possibly invented: {unknown[:12]}",
            {"overlap": overlap, "unknown": unknown})
    return GraderResult("grounding", True, f"{overlap:.0%} content-word overlap with source",
                        {"overlap": overlap, "unknown": unknown})


def check_visuals_resolved(unit: ShortUnit) -> GraderResult:
    refs = {b.visual_ref for b in unit.beats}
    missing = refs - set(unit.visuals)
    if missing:
        return GraderResult("visuals_resolved", False, f"missing visuals: {sorted(missing)}")
    empty = [r for r in refs
             if unit.visuals[r].type == "diagram" and not (unit.visuals[r].svg or "").strip()]
    if empty:
        return GraderResult("visuals_resolved", False, f"diagram visuals with no SVG: {empty}")
    return GraderResult("visuals_resolved", True, f"{len(refs)} visuals resolved")


def check_technical_beats_use_diagrams(unit: ShortUnit) -> GraderResult:
    """Non-negotiable #4: technical content must not be rendered by an image model."""
    offenders = [v.ref for v in unit.visuals.values() if v.type == "image"
                 and any(k in v.spec.lower() for k in
                         ("table","diagram","flow","architecture","memory","register",
                          "address","frame","page","bit","cache","queue","stack","tree"))]
    if offenders:
        return GraderResult("technical_visuals", False,
            f"technical specs assigned type=image instead of diagram: {offenders}")
    return GraderResult("technical_visuals", True, "no technical content sent to an image model")


SCRIPT_GRADERS = [check_timing, check_overlays, check_dialogue_shape]
UNIT_GRADERS   = [check_visuals_resolved, check_technical_beats_use_diagrams]


def run_script_graders(script: Script, source_text: str | None = None) -> list[GraderResult]:
    results = [g(script) for g in SCRIPT_GRADERS]
    if source_text:
        results.append(check_grounding(script, source_text))
    return results


def all_passed(results: list[GraderResult]) -> bool:
    return all(r.passed for r in results)
