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


#: The answer is 2 or 3 parts, not 3 to 5.
#:
#: Five points is not a thing anybody remembers off a phone screen. Reviewers kept
#: asking the same question about these shorts — "which of these five was the
#: answer?" — and the honest reply was that three of them were context. A short
#: that lands ONE idea and one consequence is recallable a week later; a short that
#: lands five lands none of them, and takes twice as long doing it.
#:
#: Two is now allowed, and often right: a question whose answer is a mechanism plus
#: its consequence needs exactly two beats, and the third was always the weakest —
#: a restatement, or a claim propped up by a quote that did not quite support it.
MIN_ANSWERS = 2
MAX_ANSWERS = 3

#: And each part is shorter: 32 words is two sentences read fast, which is a wall
#: of text against a single diagram.
MAX_ANSWER_WORDS = 24


def check_dialogue_shape(script: Script) -> GraderResult:
    """
    One question, then the answer in 2 or 3 short parts.

    A single continuous answer was tried and rejected in review: it read as a wall
    of text, left one diagram on screen for ~40 seconds, and gave the model enough
    rope to drift off the source. Splitting the answer gives each idea its own
    visual and keeps every spoken chunk short.

    The upper bound came DOWN from five, which is the more important half of this
    grader now — see MAX_ANSWERS. Splitting far enough is easy; stopping is not.
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

# Maths and notation break a purely lexical check. A source that writes "2^3 = 8"
# or "11" is faithfully narrated as "two cubed equals eight" and "eleven" — the
# claim is identical, the characters are not, and every spelled-out number counted
# as invented. Normalising number words to digits makes the two sides comparable.
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
    "hundred": "100", "thousand": "1000",
    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
    "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
}

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
    # reading notation aloud: "2^2" becomes "two squared", "=" becomes "equals".
    # These describe the symbols, they do not add claims.
    "squared","cubed","power","powers","times","plus","minus","equals","equal",
    "stands","place","value","values","left","onwards",
    # spoken-answer filler. A student answering out loud opens with "Nope, ..." or
    # "Yeah, so ..."; none of it is a claim about the material.
    "nope","yeah","yep","okay","sure","hey","listen","anyway","honestly","literally",
    "total","include","includes","including","fall","falls","short","shorter","scale",
    "scales","whole","full","half","part","parts","kind","sort","lot","bunch","stuff",
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
        word = _NUMBER_WORDS.get(word, word)
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


# Measured, not guessed. Across the real runs so far: scripts a human accepted
# scored 41-97%, and the known-fabricated fixture scores 7%. 0.55 was rejecting
# faithful scripts on maths material at 41-46% while leaving a 48-point gap above
# the hallucination. 0.45 keeps a 6x margin over the fabricated case and stops
# failing honest ones. E006/E007 are the pair that guard this number.
DEFAULT_MIN_OVERLAP = 0.45


def check_grounding(script: Script, source_text: str,
                    min_overlap: float = DEFAULT_MIN_OVERLAP,
                    doc_text: str | None = None) -> GraderResult:
    """
    Cheap faithfulness proxy. Catches wholesale invention, not subtle errors — the
    LLM judge is what checks meaning.

    Graded against the whole reading material when it is available, not only the
    one section. A section is often a few sentences, so a 95-word answer must add
    connective language and use vocabulary the material established elsewhere; run
    after run that scored 30-46% and blocked faithful scripts. The document is the
    right yardstick for "did you invent this", because a term defined in section
    1.1 is not a fabrication when section 1.3 uses it. Staying on-topic for the
    section is a different question, and it belongs to the judge.

    `source_text` is still counted first so the section remains the primary
    reference; doc_text only rescues words the material genuinely contains.
    """
    src = set(_stems(source_text))
    if doc_text:
        src |= set(_stems(doc_text))
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


# ----------------------------------------------------------------- source quotes
#
# Grounding above is a word-overlap proxy: it catches a script that invented a
# whole topic, but it cannot catch a script that uses the section's vocabulary to
# state something the section never said. That is the failure that actually
# reaches a learner — a confident, on-topic, wrong answer.
#
# So every answer beat carries the span of the section it is a restatement of, and
# this grader checks that the span is really there. A model cannot cite a sentence
# that does not exist without the citation failing, and the failure comes back as
# retry feedback naming the beat, so the next attempt is anchored rather than
# scolded. Deterministic, free, and it runs before anything is paid for.

_QUOTE_NOISE = re.compile(r"[^a-z0-9]+")
MIN_QUOTE_WORDS = 4


def _flatten(text: str) -> str:
    """Collapse to bare alphanumerics so punctuation and whitespace cannot bite.

    The model retypes a quote with a straight apostrophe where the source had a
    curly one, or joins a line-wrapped sentence with a single space. Those are
    faithful citations and must not be reported as invented, so both sides are
    reduced to letters and digits before comparing.
    """
    return _QUOTE_NOISE.sub(" ", text.lower()).strip()


# ---------------------------------------------------------------------- refusals
#
# The instruction to stay inside the source is strong, and it should be. But a
# model handed a section that cannot answer its topic obeys that instruction by
# refusing — "the section I have only talks about the p element", "I can't really
# answer that from what I've got here" — and a refusal is a worse short than a
# wrong one, because it teaches nothing and reads as broken.
#
# A refusal is a bug upstream (a topic paired with the wrong section) surfacing
# downstream, so this grader exists to stop it reaching a human and to send the
# retry loop the one instruction that fixes it: find the answer in the material.
#
# Matching is deliberately narrow — the meta-framing, not the words. A script may
# legitimately say "the browser does not display it"; only a script talking ABOUT
# its own source material trips this.
_REFUSAL = re.compile(
    r"""(
      \b(can|could|cannot|can't|cant)\s*(not)?\s*(really\s+)?(answer|tell|say|explain|help)
    | \bi\s+(don't|do\s+not|doesn't)\s+have\b
    | \b(the|this|my)\s+(section|source|material|document|text|passage)\s+
        (i\s+have\s+)?(only|just|doesn't|does\s+not|never|didn't)\b
    | \b(not|isn't|aren't|never)\s+(covered|mentioned|discussed|explained|stated|given)\b
    | \b(doesn't|does\s+not|don't)\s+(cover|mention|discuss|explain|say|state|include)\b
    | \bfrom\s+what\s+i(\s+have|'ve|\s+was)\b
    | \b(no|not\s+enough)\s+(information|detail|details|context)\b
    | \b(outside|beyond)\s+(the\s+)?(scope|section|source|material)\b
    | \bnot\s+in\s+the\s+(source|section|material)\b
    )""",
    re.I | re.X,
)


def check_no_refusal(script: Script) -> GraderResult:
    """No beat may talk about the source material instead of teaching."""
    hits = []
    for i, beat in enumerate(script.beats):
        for field, text in (("line", beat.line), ("on_screen", beat.on_screen)):
            if m := _REFUSAL.search(text or ""):
                hits.append(f'beat {i} {field}: "{m.group(0).strip()}"')

    if hits:
        return GraderResult("no_refusal", False,
            "the script refuses to answer instead of teaching — " + "; ".join(hits[:3]) +
            ". The answer IS in the reading material: find the part that answers this "
            "question, quote it, and explain it. Never mention the source material, "
            "the section, or what you do or do not have.",
            {"hits": hits})
    return GraderResult("no_refusal", True, "answers the question directly")


def check_source_quotes(script: Script, source_text: str,
                        doc_text: str | None = None) -> GraderResult:
    """
    Every answer beat must quote a span that actually occurs in the material.

    Checked against the whole document when it is available, not only the cited
    section. A question can legitimately need one sentence from a neighbouring
    section — "what is the difference between X and Y" often does — and rejecting
    that quote would push the model toward refusing rather than answering. The
    guarantee that matters is unchanged: the sentence must exist in the material
    the user supplied. Whether the short stayed on-topic for its section is the
    judge's question, not this one's.
    """
    haystack = _flatten(source_text)
    if doc_text:
        haystack += "  " + _flatten(doc_text)
    answers = [(i, b) for i, b in enumerate(script.beats) if b.speaker == "student"]
    if not answers:
        return GraderResult("source_quotes", False, "no answer beats to check")

    missing, thin = [], []
    for i, beat in answers:
        quote = (beat.source_quote or "").strip()
        if not quote:
            missing.append(f"beat {i} has no source_quote")
            continue
        flat = _flatten(quote)
        if len(flat.split()) < MIN_QUOTE_WORDS:
            thin.append(f"beat {i} quote is only {len(flat.split())} words")
            continue
        if flat not in haystack:
            missing.append(f'beat {i} quotes "{quote[:70]}" which is not in the material')

    problems = missing + thin
    if problems:
        return GraderResult("source_quotes", False,
            "; ".join(problems[:4]) +
            ". Copy the sentence out of the reading material character for character. "
            "The full quote is compared, so do not add words to it or run two "
            "separated sentences together.",
            {"problems": problems})

    # One sentence propping up three beats. Whether a citation actually SUPPORTS its
    # line is a meaning question and belongs to the judge, but this much is
    # countable, and it is the shape the padded shorts had: an answer stretched to
    # fill the length floor, with the extra beats citing whatever was nearest.
    # Distinct evidence per beat is what a real explanation looks like.
    #
    # One repeat is allowed, because a closing takeaway legitimately lands on the
    # same sentence an earlier beat introduced.
    quotes = {_flatten(b.source_quote or "") for _, b in answers}
    needed = max(2, len(answers) - 1)
    if len(quotes) < needed:
        return GraderResult("source_quotes", False,
            f"{len(answers)} answer beats rest on only {len(quotes)} distinct "
            f"sentence(s) from the material — that is one idea stretched to fill "
            f"the time. Either give each beat its own supporting sentence, or use "
            f"fewer beats and make the answer shorter.",
            {"distinct": len(quotes), "beats": len(answers)})

    return GraderResult("source_quotes", True,
                        f"{len(answers)} answer beats, {len(quotes)} distinct "
                        f"citations, all verbatim")


def check_answers_its_section(script: Script, section_text: str) -> GraderResult:
    """
    At least one answer beat must quote the section the topic was filed under.

    write_script is given the whole document so that a topic whose answer lives in a
    summary elsewhere can still be answered instead of refused. The cost of that is
    drift: with everything in view, a short can wander off and answer something
    adjacent to what its question asked. This is the anchor — the short may draw on
    the whole material, but it has to be ABOUT its own section.
    """
    section = _flatten(section_text)
    answers = [b for b in script.beats if b.speaker == "student"]
    anchored = [b for b in answers
                if b.source_quote and _flatten(b.source_quote) in section]

    if not anchored:
        return GraderResult("on_topic", False,
            "no answer beat quotes the section this short is filed under — the "
            "answer has drifted onto neighbouring material. At least one beat must "
            "come from the section itself, or the question is the wrong question "
            "for this section.")
    return GraderResult("on_topic", True,
                        f"{len(anchored)} of {len(answers)} beats quote its own section")


# -------------------------------------------------------------------- svg defects
#
# A model drawing SVG cannot see its own output, and the failures that follow from
# that are always the same three, all of them visible from the markup alone:
#
#   1. Overflowing text. SVG has no line wrapping, so a 27-character label in a
#      200px box simply spills across the drawing. Character count against the
#      font size catches it without rendering anything.
#   2. Rotated labels. A transform on a <text> reliably comes out overlapping and
#      unreadable at phone size.
#   3. Coordinates outside the viewBox, which are silently clipped.
#
# Cheap enough to run on every frame, and specific enough to hand back as retry
# feedback — which is what render_diagrams does with it.

_TEXT_EL = re.compile(r"<text\b([^>]*)>(.*?)</text>", re.S | re.I)
_RECT_EL = re.compile(r"<rect\b([^>]*)/?>", re.I)
_FONT_SIZE = re.compile(r'font-size\s*=\s*"?(\d+(?:\.\d+)?)', re.I)
_ANCHOR = re.compile(r'text-anchor\s*=\s*"?(\w+)', re.I)
_XY = re.compile(r'\b(x|y)\s*=\s*"?(-?\d+(?:\.\d+)?)', re.I)

VIEWBOX = 1080
CHAR_WIDTH_RATIO = 0.55        # rough advance width of Inter at a given font-size

# What actually makes a label unreadable is its WIDTH IN PIXELS, not its character
# count. A raw character cap flags a 39-character caption set at 34px — 729px on a
# 1080 canvas, perfectly legible — while missing a 20-character heading at 80px
# that runs off both edges. Measure the width and the same rule covers both.
MAX_TEXT_WIDTH = VIEWBOX - 80


def _attr(attrs: str, name: str) -> float | None:
    m = re.search(rf'\b{name}\s*=\s*"?(-?\d+(?:\.\d+)?)', attrs, re.I)
    return float(m.group(1)) if m else None


def _text_box(attrs: str, label: str) -> tuple[float, float, float, float] | None:
    """Estimated bounding box of a <text>, as (x0, y0, x1, y1)."""
    x, y = _attr(attrs, "x"), _attr(attrs, "y")
    if x is None or y is None:
        return None
    size = float(m.group(1)) if (m := _FONT_SIZE.search(attrs)) else 40.0
    width = len(label) * size * CHAR_WIDTH_RATIO
    anchor = (m.group(1).lower() if (m := _ANCHOR.search(attrs)) else "start")
    x0 = x - width / 2 if anchor == "middle" else x - width if anchor == "end" else x
    # y is the baseline, not the top.
    return x0, y - size * 0.8, x0 + width, y + size * 0.2


#: Shapes above which a frame is too busy for a phone, four seconds, once, with
#: someone talking over it. The SVG brief asks for 3-6; this is the point at which
#: a redraw is worth spending, not the target — a frame at 7 is fine, one at 13 is
#: a wall of boxes. Only the redraw loop uses it, so it costs one extra attempt and
#: never fails a frame outright.
#: Down from 8. The redraw loop reports "N shapes — too busy" and the model thins
#: the frame out, so this number is the actual lever on how busy a diagram is. At 8
#: the frames that came back were still schematics of five or six equal parts; the
#: complaint they generate is "too complex to understand", and the fix is upstream
#: of any label tweak.
MAX_SHAPES = 6

#: How far past its own box a label must reach before it counts as spilling.
#:
#: A RATIO, not a pixel margin, and that matters. The first version demanded 12px
#: of clear space per side, which fired on "Single" at an estimated 158px inside a
#: 180px box — a 22px margin, perfectly fine on screen. Text widths here are
#: ESTIMATED from character counts (see CHAR_WIDTH_RATIO) and carry maybe 10% of
#: error, so any threshold tighter than that error bar reports noise. And noise is
#: expensive: every false positive burns one of the three redraw attempts that a
#: genuinely broken frame needed.
#:
#: At 1.05 the check fires on real spills — a 131px label in an 80px box — and stays
#: quiet on the merely snug ones.
LABEL_SPILL_RATIO = 1.05

_SHAPE_EL = re.compile(r"<(rect|circle|ellipse|polygon|polyline|path|line)\b", re.I)


def svg_problems(svg: str, max_width: float = MAX_TEXT_WIDTH,
                 collisions: bool = False, max_shapes: int | None = None) -> list[str]:
    """
    Everything wrong with one generated frame, as instructions to fix it.

    `collisions` adds label-over-box detection. It is off by default because it
    estimates text widths from character counts and so has false positives, and
    check_svg_quality gates a paid judge call — a frame failed by a guess is worse
    than a frame with one tight label. The redraw loop in visuals.py turns it on,
    where a false positive costs one extra attempt and nothing else.
    """
    problems: list[str] = []
    texts = []

    if max_shapes is not None:
        drawn = len(_SHAPE_EL.findall(svg or ""))
        if drawn > max_shapes:
            problems.append(
                f"this frame draws {drawn} shapes — too busy for a phone screen at "
                f"4 seconds. Cut it to {max_shapes} or fewer: keep the objects the "
                f"narration actually names, drop the decoration, the extra "
                f"containers and any second mechanism shown for context")

    for attrs, body in _TEXT_EL.findall(svg or ""):
        label = re.sub(r"<[^>]+>", "", body)
        label = re.sub(r"\s+", " ", label).strip()
        if not label:
            continue

        if re.search(r"\b(transform|rotate)\s*=", attrs, re.I):
            problems.append(f'"{label[:30]}" is rotated — draw all text horizontally')

        size = float(m.group(1)) if (m := _FONT_SIZE.search(attrs)) else 40.0
        width = len(label) * size * CHAR_WIDTH_RATIO
        if width > max_width:
            problems.append(
                f'"{label[:40]}" is {len(label)} chars at font-size {size:.0f}, about '
                f'{width:.0f}px wide — wider than the {max_width:.0f}px canvas allows. '
                f'Split it into separate <text> lines, or shorten it')

        for axis, value in _XY.findall(attrs):
            v = float(value)
            if v < 0 or v > VIEWBOX:
                problems.append(f'"{label[:30]}" has {axis}={value}, outside the '
                                f'0-{VIEWBOX} viewBox — it will be clipped')
                break

        if collisions and (box := _text_box(attrs, label)):
            texts.append((label, box))

    if collisions:
        problems += _collisions(svg, texts)

    # Deduplicate but keep the order they were found in.
    return list(dict.fromkeys(problems))


def _collisions(svg: str, texts: list) -> list[str]:
    """
    Labels that sit on top of a box they do not belong to.

    This is the defect left over once the text fits and nothing is rotated: an
    arrow label dropped into a gap too narrow for it, printing across the box next
    door. Invisible in the markup, obvious on screen, and the model cannot see it.
    """
    boxes = []
    for attrs in _RECT_EL.findall(svg or ""):
        x, y = _attr(attrs, "x"), _attr(attrs, "y")
        w, h = _attr(attrs, "width"), _attr(attrs, "height")
        if None in (x, y, w, h):
            continue
        if w * h > 0.6 * VIEWBOX * VIEWBOX:
            continue            # a panel or background, not a node
        boxes.append((x, y, x + w, y + h))

    out = []
    for label, (tx0, ty0, tx1, ty1) in texts:
        cx, cy = (tx0 + tx1) / 2, (ty0 + ty1) / 2
        for bx0, by0, bx1, by1 in boxes:
            overlaps = tx0 < bx1 and tx1 > bx0 and ty0 < by1 and ty1 > by0
            inside = bx0 <= cx <= bx1 and by0 <= cy <= by1
            if overlaps and not inside:
                out.append(
                    f'the label "{label[:28]}" is printed across the box at '
                    f'({bx0:.0f},{by0:.0f}) it does not belong to — move it into the '
                    f'clear, or widen the gap it sits in')
                break

            # A label centred in its OWN box but wider than it. This is the defect
            # the "not inside" test above cannot see, and it is the one that keeps
            # shipping: "Free" centred in a 90px box renders 30px past both its
            # edges and collides with whatever is next to it. The frame reads as
            # sloppy for a reason the model has no way to notice, since the markup
            # is perfectly well-formed.
            if inside and (tx1 - tx0) > (bx1 - bx0) * LABEL_SPILL_RATIO:
                out.append(
                    f'the label "{label[:28]}" is about {tx1 - tx0:.0f}px wide but its '
                    f'box is only {bx1 - bx0:.0f}px — it spills out over both edges. '
                    f'Widen the box to at least {(tx1 - tx0) * 1.2:.0f}px, shorten the '
                    f'label, or split it across two <text> lines')
                break

    # Two labels on the same spot. Same defect, different pair: it happens where a
    # caption and an arrow label both aim for the gap under the diagram, and it is
    # just as unreadable as a label over a box.
    for i, (label_a, a) in enumerate(texts):
        for label_b, b in texts[i + 1:]:
            if a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]:
                out.append(
                    f'the labels "{label_a[:24]}" and "{label_b[:24]}" are printed on '
                    f'top of each other — move one of them, or drop it')
    return out


#: A frame may introduce this share of label vocabulary that is in neither the
#: narration nor the source. Not zero: a diagram legitimately carries structural
#: words nobody says out loud ("start", "yes", "step 1", axis names), and a frame
#: is allowed a little labelling of its own.
MAX_FOREIGN_LABEL_SHARE = 0.4

#: Words a diagram may always use, whether or not anyone says them. Structural
#: scaffolding, not content.
_DIAGRAM_SCAFFOLD = {
    "yes", "no", "start", "end", "step", "then", "before", "after", "input",
    "output", "true", "false", "bit", "bits", "byte", "bytes", "key", "value",
    "one", "two", "three", "four", "five", "zero", "total", "each", "per",
}

#: XML entity names, which survive tag-stripping as bare words and are not content.
_ENTITY_NAMES = {"gt", "lt", "amp", "quot", "apos", "nbsp"}

#: A label token that carries no topical meaning: a number, a hex literal, or a
#: short identifier built from a letter-stem plus an index — b0, f12, bit3, h2, x.
#:
#: These dominate a good technical diagram. The SVG brief explicitly asks for them
#: ("anchor abstract things to something countable: number the rows, mark the
#: positions, draw the actual bits"), so counting them as vocabulary the narration
#: failed to introduce marks the best frames as the worst. Measured before this
#: filter existed: 21 of 26 real units "failed", almost entirely on 0, 1, b0, f0.
_IDENTIFIER = re.compile(r"""^(?:
      \d+                 # 1, 1011, 4096
    | 0x[0-9a-f]+         # 0x0a
    | [a-z]+\d+           # b0, f12, bit3, h2, frame5, page0
    | \d+[a-z]{1,3}       # 4kb, 2mb, 32bit — a quantity, not a subject
    | [a-z]               # a single letter used as a variable
)$""", re.X)


def _is_topical(word: str) -> bool:
    """Does this label token say anything about the subject matter?"""
    return not (_IDENTIFIER.match(word) or word in _ENTITY_NAMES)


def check_diagram_matches_narration(unit: ShortUnit) -> GraderResult:
    """
    Every diagram's labels should come from what is being said, or from the source.

    The complaint this exists for: diagrams that are technically well-drawn but are
    about something adjacent to the narration — the voice explains one thing and the
    picture labels another. The drawing model is given the narration AND the whole
    source section, and the section is much longer, so a frame can drift onto a
    neighbouring idea and still look plausible on its own.

    Deliberately vocabulary-based rather than semantic. It cannot tell a subtly
    wrong diagram from a right one; it catches the frame that is about different
    NOUNS than the beat it plays under, which is the failure that actually shows up.
    A semantic check is the judge's job and costs a model call.
    """
    # The WHOLE script's vocabulary, not just the beat this frame plays under.
    #
    # The visuals are deliberately one composition that builds, so frame 1 draws
    # objects beat 4 will name and every frame carries the shared scaffolding. Scoped
    # per-beat this flagged "frame" and "fault" as foreign to a page-fault short,
    # because that frame belongs to the interviewer's question and the words arrive
    # two beats later. What is being caught is a diagram about a DIFFERENT SUBJECT,
    # and the subject is the short, not the beat.
    allowed = set(_stems(
        " ".join(b.line for b in unit.beats)
        + " " + " ".join(b.on_screen for b in unit.beats)
        + " " + " ".join(b.source_quote or "" for b in unit.beats)
        + " " + unit.question
    )) | {_stem(w) for w in _DIAGRAM_SCAFFOLD}
    # The visual SPEC is deliberately NOT in here. It comes from the same model
    # chain as the drawing, so a frame that faithfully renders a spec which itself
    # wandered off the narration would score perfectly — which is the exact defect
    # this grader exists to find. Measure the picture against what is SAID.

    offenders: list[str] = []
    checked = 0

    for ref, visual in (unit.visuals or {}).items():
        if not visual.svg:
            continue

        labels = " ".join(
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", body)).strip()
            for _attrs, body in _TEXT_EL.findall(visual.svg))
        drawn = {stem: word for stem, word in _stems(labels).items()
                 if _is_topical(word)}
        if not drawn:
            continue          # a frame of pure numbers and bit labels is fine

        checked += 1
        foreign = [word for stem, word in drawn.items() if not _grounded(stem, allowed)]
        share = len(foreign) / len(drawn)
        if share > MAX_FOREIGN_LABEL_SHARE:
            offenders.append(f"{ref}: {share:.0%} of label words are in neither the "
                             f"narration nor the source ({', '.join(sorted(foreign)[:6])})")

    if not checked:
        return GraderResult("diagram_matches_narration", True, "no rendered diagrams")
    if offenders:
        return GraderResult("diagram_matches_narration", False,
                            "; ".join(offenders[:3]))
    return GraderResult("diagram_matches_narration", True,
                        f"{checked} diagram(s) labelled from the narration and source")


def check_svg_quality(unit: ShortUnit) -> GraderResult:
    """Frames whose markup shows text that cannot render legibly."""
    bad: dict[str, list[str]] = {}
    for ref, visual in unit.visuals.items():
        if visual.type == "diagram" and visual.svg:
            found = svg_problems(visual.svg)
            if found:
                bad[ref] = found

    if bad:
        first = "; ".join(f"{ref}: {probs[0]}" for ref, probs in list(bad.items())[:3])
        return GraderResult("svg_quality", False,
                            f"{len(bad)} frame(s) with unreadable text — {first}",
                            {"frames": bad})
    return GraderResult("svg_quality", True, "all frames render legibly")


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


SCRIPT_GRADERS = [check_timing, check_overlays, check_dialogue_shape, check_no_refusal]
UNIT_GRADERS   = [check_visuals_resolved, check_technical_beats_use_diagrams,
                  check_svg_quality, check_diagram_matches_narration]


def run_script_graders(script: Script, source_text: str | None = None,
                       doc_text: str | None = None) -> list[GraderResult]:
    results = [g(script) for g in SCRIPT_GRADERS]
    if source_text:
        results.append(check_source_quotes(script, source_text, doc_text=doc_text))
        results.append(check_answers_its_section(script, source_text))
        results.append(check_grounding(script, source_text, doc_text=doc_text))
    return results


def all_passed(results: list[GraderResult]) -> bool:
    return all(r.passed for r in results)
