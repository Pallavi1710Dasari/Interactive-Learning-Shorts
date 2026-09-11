"""
Code graders. Deterministic, free, instant. These run BEFORE any paid step.

Every grader takes an object and returns a GraderResult. Never raise — a grader
that crashes tells you nothing; a grader that returns passed=False with a reason
tells you what to fix.
"""
import html, re
from math import ceil
from dataclasses import dataclass, field
from .schema import (
    Script, ShortUnit, Section, QuestionSelection, QuestionFraming, QuestionWorkflow,
    TeachingApproach, VisualStrategy, MIN_SECONDS, MAX_SECONDS, HARD_MAX_SECONDS,
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


def check_timing(script: Script, max_seconds: int | None = None) -> GraderResult:
    """
    The single most valuable check in the pipeline. Runs in microseconds.

    `max_seconds` defaults to MAX_SECONDS (45) so every existing caller — the eval
    harness, smoke_test, any check_timing(script) written before this param existed
    — is byte-identical. run_script_graders is the one caller that passes a wider
    ceiling, and only when checks.duration_budget says the section's own reading
    earned it. See schema.HARD_MAX_SECONDS for what "wider" is bounded by and why.
    """
    ceiling = MAX_SECONDS if max_seconds is None else max_seconds
    secs = script.estimated_seconds
    if secs < MIN_SECONDS:
        return GraderResult("timing", False,
            f"too short: {secs}s ({script.word_count} words). Need >= {MIN_SECONDS}s "
            f"(~{int(MIN_SECONDS * WORDS_PER_SECOND)} words).",
            {"seconds": secs, "words": script.word_count})
    if secs > ceiling:
        return GraderResult("timing", False,
            f"too long: {secs}s ({script.word_count} words). Need <= {ceiling}s "
            f"(~{int(ceiling * WORDS_PER_SECOND)} words).",
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
#: Raised from 2-3 alongside the 35-50s window in schema.py. The count went up;
#: the SIZE of a beat deliberately did not — see MAX_ANSWER_WORDS below.
#:
#: The note this replaces said five points is what made shorts unmemorable, and
#: that still holds for five points of NEW MECHANISM. What 4-5 buys at the wider
#: window is not five claims, it is the same two or three claims plus the parts
#: that make them stick: a worked example, a misconception named and corrected,
#: and a closing takeaway. Those are not additional ideas competing for the
#: viewer's memory — they are the same idea, landed three more ways.
#:
#: Six is still refused. Past five the short becomes a list again whatever the
#: beats contain, and that is the failure the cut to 3 was fixing.
MIN_ANSWERS = 4
MAX_ANSWERS = 5

#: UNCHANGED AT 24, AND THIS IS THE LOAD-BEARING CONSTANT OF THE WHOLE RAISE.
#:
#: 32 words is two sentences read fast, which is a wall of text against a single
#: diagram. The window went from 28s to 50s without touching this, which forces
#: the extra time into MORE BEATS rather than longer ones — every beat stays one
#: idea with one picture. Raising this to let 4 beats fill 50s would give back
#: exactly the wall of text that splitting the answer exists to prevent.
MAX_ANSWER_WORDS = 24

#: THE ONE, NARROW, GATED EXCEPTION TO THE CONSTANT ABOVE.
#:
#: Deliberately short of the 32-word "wall of text" line the comment above draws
#: — 30, not 32 — and deliberately not a blanket raise: `run_script_graders`
#: only reaches for this when `duration_budget` has already decided, from the
#: SAME material-richness signal, that this section earns the wider duration
#: window (see checks.duration_budget and schema.HARD_MAX_SECONDS). A thin
#: section still gets 24, exactly as before.
#:
#: WHY A WORD BUDGET AT ALL, WHEN THE DURATION ALREADY WIDENED. Extra seconds
#: bought extra BEATS (schema.HARD_MAX_SECONDS's own arithmetic is built on a
#: 5th beat, not longer ones), and that is right for a section with a genuine
#: 5th distinct thing to say. It is the wrong shape for a section whose extra
#: material is a single step that needs one more clause to explain WHY it is
#: true rather than a whole new beat's worth of content — forcing that into a
#: 6th beat is exactly the "becomes a list again" failure MAX_ANSWERS exists to
#: prevent, and forcing it into 24 words is the "citation with no room left to
#: explain it" defect this whole change is trying to fix. Six extra words is a
#: single short clause, not a second sentence — "...which is why X" — not room
#: for a second wall of text.
MAX_ANSWER_WORDS_EXTENDED = 30


def check_dialogue_shape(script: Script, max_answer_words: int | None = None) -> GraderResult:
    """
    One question, then the answer in 2 or 3 short parts.

    A single continuous answer was tried and rejected in review: it read as a wall
    of text, left one diagram on screen for ~40 seconds, and gave the model enough
    rope to drift off the source. Splitting the answer gives each idea its own
    visual and keeps every spoken chunk short.

    The upper bound came down from five and has now gone back to five, for a
    different reason than it first had it — see MAX_ANSWERS. Splitting far enough
    is easy; stopping is not, and the stop is now enforced by MAX_ANSWER_WORDS
    holding at 24 rather than by a tight beat count.

    `max_answer_words` defaults to MAX_ANSWER_WORDS, so every existing caller is
    unaffected. `run_script_graders` is the one caller that passes
    MAX_ANSWER_WORDS_EXTENDED, and only when duration_budget already decided this
    section's material earns it — see that constant's own comment.
    """
    cap = MAX_ANSWER_WORDS if max_answer_words is None else max_answer_words
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
                  if b.speaker == "student" and len(b.line.split()) > cap]
    if long_beats:
        worst = ", ".join(f"beat {i}: {n} words" for i, n in long_beats)
        return GraderResult("dialogue_shape", False,
            f"{len(long_beats)} answer beat(s) over {cap} words ({worst}) — "
            "keep each one to a single idea")

    return GraderResult("dialogue_shape", True, f"{answers} answer beats, all concise")


def check_qa_sentence_form(script: Script) -> GraderResult:
    """
    The question is phrased as ONE question, and every answer beat is a whole
    sentence — not "simple" or "memorable", which no free check can judge, but the
    structural floor those actually need: a fragment can't be simple to read and a
    stapled-together double question can't be memorable, because there's no ONE
    thing to remember. See SYSTEM in select.py and script.py for the prose rules
    this can't enforce in code.

    Three narrow, structural failures, each one a script that reads as unfinished
    rather than as a sentence a student could hold in their mind:

      script.question has no "?" — select.py's SYSTEM already bans yes/no
      questions and demands What/Why/How/Which/When/Where, but nothing stopped
      the topic string itself surviving into the short as a bare noun phrase
      ("The reason paging beats contiguous allocation") instead of a question.

      script.question has MORE than one "?" — two questions stapled into one
      turns "one concept per short" (select.py's own rule) into two, and a viewer
      cannot tell which one the answer is actually answering.

      a student beat's line does not end in ".", "!" or "?" — the line just
      trails off, which is a sentence fragment however short and on-topic it is.
    """
    problems: list[str] = []

    question = script.question.strip()
    marks = question.count("?")
    if marks == 0:
        problems.append(f'question is not phrased as a question: "{question}"')
    elif marks > 1:
        problems.append(
            f'question contains {marks} "?"s — that is two questions stapled '
            f'together, not one: "{question}"')

    for i, b in enumerate(script.beats):
        if b.speaker != "student":
            continue
        line = b.line.strip()
        if not line.endswith((".", "!", "?")):
            problems.append(f'beat {i} trails off with no terminal punctuation: "{line}"')

    if problems:
        return GraderResult("qa_sentence_form", False, "; ".join(problems),
                            {"problems": problems})
    return GraderResult("qa_sentence_form", True,
                        "question is a single question and every beat is a complete sentence")


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
    # "failure"/"fail" is the real case this was missing: the suffix table had no
    # rule for it, so "failure" fell through to the generic e-strip below and
    # stemmed to "failur" — five of six letters, but _grounded's prefix-match
    # requires BOTH sides to be >=5 characters, and "fail" is four. Confirmed on a
    # real script: it said "fail at any step" and check_follows_teaching_sequence
    # reported "failure" as never mentioned, because "failur" vs "fail" never
    # cleared the length floor to be compared at all.
    ("ure", ""),
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

#: A CODE QUOTE IS EXEMPT FROM THE WORD FLOOR, and leaving it out made a whole
#: class of short unbuildable.
#:
#: _flatten strips every non-alphanumeric before counting, which is right for prose
#: — it is what lets a curly apostrophe or a line-wrapped sentence still match. On a
#: line of code it is destructive: `font-family: "Roboto";` counts as THREE words,
#: `color: blue;` as two, `input()` as ONE. And `font-family: "Roboto";` is not a
#: hypothetical — it is the example SCRIPT_SYSTEM gives the model of a GOOD citation.
#:
#: So the brief said "quote the line of code", the grader said "at least 4 words",
#: and a beat citing a short code line could satisfy neither. All three retries
#: failed with `source_quotes: beat 1 quote is only 1 words`, the reviewer saw a red
#: chip on a script whose citation was perfect, and no rewording could fix it.
#:
#: The floor exists to reject a bare word — "binary", "False" — offered as evidence.
#: A code line is the opposite of that: it is the most specific citation the
#: material can offer. So code is judged on length instead, and still has to be
#: found in the section like every other quote.
MIN_QUOTE_CHARS = 6
#: `:` and CamelCase are in here for a reason that took a real failure to find.
#: `SyntaxError: invalid syntax` is three words, is the literal output the material
#: prints, and is exactly what a beat about syntax errors should cite — and it was
#: rejected as "a fragment, not a sentence" because the marks below only looked for
#: brackets and semicolons. An error message, a dict key, a `label:` — all are the
#: document's own literal text rather than a sentence about it. A colon in real
#: prose almost always sits in a clause long enough to clear the word floor before
#: this is ever consulted.
_CODE_MARKS = re.compile(
    r"[{}()\[\];=<>/\\]|::|--|:\s|\w+\.\w+|[a-z][A-Z]|^\s*[.#@]\w")


def _is_code_quote(raw: str) -> bool:
    """Does this quote read as a line of code rather than a sentence of prose?"""
    text = raw.strip()
    if len(text) < MIN_QUOTE_CHARS:
        return False
    return bool(_CODE_MARKS.search(text))


def _is_whole_sentence(raw: str) -> bool:
    """
    Is this a COMPLETE sentence, however short?

    THE SECOND HALF OF THE SAME BUG. Exempting code from the word floor fixed
    `input()` and left this: a floor of four words rejects

        "HTTP is stateless."
        "Paging removes fragmentation."

    which are three words each after _flatten strips the full stop, and which are
    exactly the sentence a beat should be citing. The reviewer got
    `source_quotes: beat 2 quote is only 3 words` on a citation that was perfect,
    with no way to satisfy it — the material simply does not contain a longer way
    of saying it.

    A terminal full stop is what separates a short SENTENCE from a short FRAGMENT,
    and the fragment is the thing the floor was built to catch: "the browser window"
    and "a valid bit" are three words with no stop and cite nothing. Two words is
    the floor even here, so a stray "It." is still refused.

    The quote must still be found verbatim in the section — that check is untouched
    and is what actually establishes the citation. This only decides whether a short
    quote is allowed to try.
    """
    text = raw.strip()
    return text.endswith((".", "!", "?")) and len(_flatten(text).split()) >= 2


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

    Checked against THE SECTION, not the whole document. This is the change, and it
    is the one that cost the most to leave un-made.

    It used to accept a quote from anywhere in the material, reasoning that a
    question like "what is the difference between X and Y" legitimately needs a
    sentence from a neighbouring section, and that rejecting it would push the model
    toward refusing rather than answering. That reasoning is sound and the cost of
    it was not visible from here — it was visible in the judge's verdicts, on four
    of fifteen shipped shorts, all scoring faithfulness 2 of 5:

      "beat 2 introduces a specific value ('A' = 65) and a claim about character
       encoding that does not appear anywhere in the source section"
      "Beat 3 introduces a concrete example ('GET /index.html', 'session key') that
       does not appear anywhere in the source section"
      "the cited code block is not part of this section and says nothing about
       metadata or links"

    Every one of those passed this grader, because the sentence existed SOMEWHERE.
    A learner watching the reel is being taught a fact the section they just read
    does not contain, cited to a section they were not shown — which is worse than
    an uncited claim, because it looks checked.

    `doc_text` is still taken, and still read: a quote found in the document but not
    in the section gets a DIFFERENT message, one that tells the model it went to the
    wrong place rather than that it made the sentence up. The retry loop acts on
    that distinction, and the two failures need opposite fixes.
    """
    haystack = _flatten(source_text)
    elsewhere = _flatten(doc_text) if doc_text else ""
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
        if (len(flat.split()) < MIN_QUOTE_WORDS
                and not _is_code_quote(quote)
                and not _is_whole_sentence(quote)):
            # THE QUOTE IS IN THE MESSAGE. Without it the reviewer was told a word
            # count and left to guess which of four beats it meant and what it had
            # said — and the model was asked to fix a string it could not see.
            thin.append(f'beat {i} quote is only {len(flat.split())} words: '
                        f'"{quote[:60]}" — a fragment, not a sentence. Quote the '
                        f'whole sentence it came from, ending at its full stop')
            continue
        if flat not in haystack:
            if elsewhere and flat in elsewhere:
                # Real sentence, wrong section. Say which, because "not in the
                # material" would send the model looking for a better copy of a
                # quote that was already copied correctly.
                missing.append(
                    f'beat {i} quotes "{quote[:70]}" — that sentence is in the '
                    f"document but NOT in this short's own section, so the beat is "
                    f"teaching material the viewer was not shown")
            else:
                missing.append(f'beat {i} quotes "{quote[:70]}" which is not in the material')

    problems = missing + thin
    if problems:
        return GraderResult("source_quotes", False,
            "; ".join(problems[:4]) +
            ". Every beat must rest on a sentence from THIS SHORT'S SECTION, copied "
            "character for character. The full quote is compared, so do not add "
            "words to it or run two separated sentences together.",
            {"problems": problems})

    # One sentence propping up three beats. Whether a citation actually SUPPORTS its
    # line is a meaning question and belongs to the judge, but this much is
    # countable, and it is the shape the padded shorts had: an answer stretched to
    # fill the length floor, with the extra beats citing whatever was nearest.
    # Distinct evidence per beat is what a real explanation looks like.
    #
    # One repeat is allowed, because a closing takeaway legitimately lands on the
    # same sentence an earlier beat introduced.
    #
    # `max(1, ...)`, NOT `max(2, ...)`, and the difference is the whole rule at the
    # smallest size. The floor of 2 made the sentence above false for a two-beat
    # answer: it needed 2 distinct quotes from 2 beats, which is zero repeats — the
    # one thing the comment says is allowed. And the failure was unescapable, because
    # the advice it printed ("or use fewer beats") means going to ONE answer beat,
    # which check_dialogue_shape rejects. A short whose section carries one strong
    # sentence had nothing it could do but fail:
    #
    #   source_quotes: 2 answer beats rest on only 1 distinct sentence(s)
    #
    # The padding this exists to catch is four beats propped on one sentence, and
    # `len(answers) - 1` still catches exactly that. Two beats sharing a citation on
    # a sixteen-second short is a question answered in two parts, not filler.
    quotes = {_flatten(b.source_quote or "") for _, b in answers}
    needed = max(1, len(answers) - 1)
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
    EVERY answer beat must quote the section the topic was filed under.

    It used to be "at least one", which is a much weaker claim than it reads as: a
    three-beat short with one anchored beat and two from elsewhere passed, and that
    is precisely the shape the drifting shorts had. One beat holds the short to its
    topic while the other two teach whatever the model found interesting nearby.

    Measured on the fifteen units in output/, this grader passed all fifteen while
    the judge scored four of them faithfulness 2 of 5 for exactly this — beats cited
    to sections the viewer never read. The anchor was doing its job and its job was
    too small.

    So the rule is now the one a learner would assume was already true: a short about
    section 3.3 is answered out of section 3.3. Every beat, not one.

    THE COST, STATED PLAINLY, because it is a real trade and not a free win. A topic
    whose section genuinely cannot support a full answer now fails three attempts and
    is dropped instead of being padded from a neighbouring section. That is the
    intended behaviour — these reels teach students, and a short that is wrong is
    worse than a short that does not exist — but it does mean fewer shorts per
    document, and the fix for a topic worth keeping is to file it under the section
    that actually answers it.
    """
    section = _flatten(section_text)
    answers = [b for b in script.beats if b.speaker == "student"]
    if not answers:
        return GraderResult("on_topic", False, "no answer beats to check")

    strays = [i for i, b in enumerate(script.beats)
              if b.speaker == "student"
              and not (b.source_quote and _flatten(b.source_quote) in section)]

    if strays:
        return GraderResult("on_topic", False,
            f"{len(strays)} of {len(answers)} answer beat(s) — {strays} — are not "
            f"supported by this short's own section. Every beat must rest on a "
            f"sentence from the section the short is filed under; a fact from "
            f"elsewhere in the document is a fact the viewer was never shown. "
            f"Either answer from this section alone, or answer the narrower "
            f"question this section does support.",
            {"strays": strays, "answers": len(answers)})
    return GraderResult("on_topic", True,
                        f"all {len(answers)} answer beats quote its own section")


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
        # UNESCAPE BEFORE MEASURING. The width test multiplies character count by a
        # font size, and character count has to mean GLYPHS — what a reader sees —
        # not the length of the XML entities encoding them. Unescaped, every code
        # frame containing HTML or a comparison was over-measured: `&lt;h1` counted
        # as six characters for three, `=&gt;` as five for two, so a wrapped and
        # perfectly legible JSX line was still reported as 68 chars "wider than the
        # canvas allows". The frame was fine; the ruler was wrong.
        label = html.unescape(label)
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


#: Fenced code blocks and inline `code` spans in the reading material.
_CODE_BLOCK = re.compile(r"```.*?```|~~~.*?~~~", re.S)
_CODE_SPAN = re.compile(r"`([^`\n]+)`")


def literal_vocabulary(source_text: str) -> set[str]:
    """
    Stems of every word the material shows inside CODE, as opposed to prose.

    This is the narrow door through which a frame may use a word nobody in the short
    says out loud, and it is narrow on purpose. `code` frames copy the document's own
    snippet verbatim — `.main-heading { font-family: "Roboto"; }` — which is the most
    strongly grounded a label can possibly be: it is not a claim about the material,
    it IS the material. But the narration will not have said "main-heading" or
    "Roboto", so measured against speech alone the best frame in the pipeline scores
    as the most drifted one.

    Only code counts. The material's PROSE stays foreign, because a noun lifted from
    a paragraph nobody mentions is exactly the drift check_diagram_matches_narration
    exists to catch — and letting the whole section in would retire the grader.
    """
    if not source_text:
        return set()
    fenced = " ".join(_CODE_BLOCK.findall(source_text))
    inline = " ".join(_CODE_SPAN.findall(source_text))
    # Split on anything that is not a word character, so CSS and markup fall apart
    # into the identifiers a label would be built from: font-family -> font, family.
    return set(_stems(re.sub(r"[^\w]+", " ", f"{fenced} {inline}")))


def _chrome_vocabulary() -> set[str]:
    """
    Stems of the fixed words render()'s own UI chrome prints — the legend and the
    arriving/leaving phase chip — so this grader never mistakes them for diagram
    content that ought to be grounded in the narration.

    THE BUG THIS FIXES. This grader reads every <text> element straight out of the
    rendered SVG string, with no idea which of them came from the Frame's own
    schema (a Cell's label, say) and which are chrome render() adds on top — so
    "Focus" and "Context" from the legend, and "ARRIVING" from the phase chip,
    showed up as label words with nothing to ground them, on EVERY frame the
    legend or phase chip appears on. A real run flagged 43% of one frame's labels
    as foreign, and every one of the foreign words was the legend, not the
    diagram.

    Imported from layout.py rather than duplicated, so the two cannot drift apart
    — if _ROLE_WORDS ever gains a role or the phase chip's vocabulary changes,
    this follows it automatically instead of silently falling out of date.
    """
    from .skills.layout import _ROLE_WORDS
    words = set(_ROLE_WORDS.values()) | {"arriving", "leaving"}
    out: set[str] = set()
    for phrase in words:
        out |= set(_stems(phrase))
    return out


def check_diagram_matches_narration(unit: ShortUnit,
                                    source_text: str | None = None) -> GraderResult:
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
    )) | {_stem(w) for w in _DIAGRAM_SCAFFOLD} | literal_vocabulary(source_text or "") \
        | _chrome_vocabulary()
    # The visual SPEC is deliberately NOT in here. It comes from the same model
    # chain as the drawing, so a frame that faithfully renders a spec which itself
    # wandered off the narration would score perfectly — which is the exact defect
    # this grader exists to find. Measure the picture against what is SAID.
    #
    # ANALOGY_CAPTION IS THE ONE DELIBERATE EXCEPTION, and it is exempted here
    # rather than left to fail and explained away. schema.Frame.analogy_caption
    # is a STATED comparison — "like a stack of plates" — brought TO the lesson
    # to make an abstract container concrete, the same as a real photo of a CPU
    # needs no citation to depict a CPU correctly. It is rendered as on-screen
    # text (so a viewer can read the comparison), which means this grader would
    # otherwise see "plates", "dispenser", "rolodex" as foreign nouns and flag
    # the very template built to introduce them. Only the caption's own words
    # are added — analogy_technical's labels get no such exemption and are
    # checked exactly like any other panel's.
    allowed |= set(_stems(" ".join(
        v.frame.analogy_caption or "" for v in unit.visuals.values()
        if v.frame is not None)))

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


#: Templates whose entire content is words. "stat" is one figure and a caption
#: naming it, which is legitimately a picture of a number; "takeaway" is a sentence
#: set large, which is not a picture of anything.
_TEXT_ONLY_TEMPLATES = {"takeaway"}

#: A label this long stopped being a label. Diagram labels are nouns and values —
#: "Page 2", "Backing store", 'font-family: "Roboto";' — and a box holding more
#: words than this is holding a clause, which means the frame is a slide.
#: `code_lines` are exempt: they are lines of real code, as long as the document
#: wrote them.
MAX_LABEL_WORDS = 5

#: ONLY TOKENS WITH LETTERS IN THEM COUNT TOWARD THAT LIMIT.
#:
#: The first version split on whitespace and counted everything, which failed a
#: perfectly good label: a frame about integer ranges was drawing
#: "...-3, -2, -1, 0, 1, 2, 3,..." and got reported as "label is a sentence". It is
#: the opposite of a sentence — it is the most concrete thing on the frame, and the
#: kind of label the SVG brief explicitly asks for ("anchor abstract things to
#: something countable"). A number sequence is long because enumerating is the
#: point, not because prose crept in.
_HAS_LETTER = re.compile(r"[A-Za-z]")


def _prose_words(label: str) -> list[str]:
    return [w for w in str(label).split() if _HAS_LETTER.search(w)]

#: How much of a beat's spoken line a frame may reproduce before the frame is just
#: that line in a box. Measured as the share of the line's content words that turn
#: up in the frame's labels.
MAX_NARRATION_ECHO = 0.6

#: What share of a short's frames have to be different PICTURES, for
#: check_frames_progress. 0.6 = three of five, four of six.
#:
#: Not 1.0: two beats legitimately sharing a picture is a held composition, and the
#: honest way to write it (one visual_ref across both beats) is already collapsed
#: before this counts. Not 0.5 either — half is exactly the alternating shape this
#: is meant to catch, so the threshold has to sit above it.
MIN_PROGRESS_SHARE = 0.6


def _frame_labels(frame) -> list[str]:
    """Every word a frame puts on screen, EXCEPT its code lines and its title."""
    out: list[str] = []
    for cell in list(frame.cells) + list(frame.left) + list(frame.right) \
            + list(frame.parts) + list(frame.steps):
        out.append(cell.label)
    for row in frame.rows:
        out.extend(row.cells)
    for panel in frame.panels:
        out.append(panel.title)
        out.extend(item.label for item in panel.items)
    # analogy's RIGHT panel is a Panel too (the section's own mechanism), and it
    # is scanned exactly like the loop above — it is graded on the ordinary
    # rule, unlike analogy_caption below, which is deliberately NOT collected
    # here: that field is a stated comparison ("like a stack of plates"), not a
    # claim about the material, and _frame_labels feeds the "is this label a
    # sentence echoing the narration" checks that a stated analogy is supposed
    # to fail differently — see check_diagram_matches_narration's own exemption
    # for analogy_caption.
    if frame.analogy_technical is not None:
        out.append(frame.analogy_technical.title)
        out.extend(item.label for item in frame.analogy_technical.items)
    # A STORE'S SLOTS ARE LABELS TOO, and leaving them out would have made every
    # `state` frame look empty to _near_same, _only_grew, frames_progress and
    # frames_are_visual — so a stack whose contents changed on every beat would
    # have counted as the same picture five times.
    #
    # An EMPTY slot contributes nothing here on purpose: it is drawn, and it is
    # meaningful, but it puts no word on screen and this function is defined as
    # the words.
    if frame.store is not None:
        out.extend(slot.label for slot in frame.store.slots)
        out.extend(filter(None, [frame.store.label, frame.store.pointer]))
    if frame.graph is not None:
        out.append(frame.graph.root.label)
        for br in frame.graph.branches:
            out.append(br.node.label)
            if br.edge_label:
                out.append(br.edge_label)
    out.extend(filter(None, [frame.cells_title, frame.left_title, frame.right_title,
                             frame.value, frame.caption, frame.note]))
    return [str(x) for x in out if str(x).strip()]


def _only_grew(a, b) -> bool:
    """
    Is `b` just `a` with something appended — the same picture, one item longer?

    THE HOLE THIS CLOSES, and it is the one the reviewer actually complained about.
    _near_same bails out at `len(la) != len(lb)`, so ADDING an element counted as a
    developed picture. Measured on a shipped HTTP short, the three frames were:

        icons: Browser, Server
        icons: Browser, HTTP, Server
        icons: Browser, HTTP, Server, Developer

    Every transition "changed the picture" by that test, so frames_develop passed —
    and what plays is one row of pictograms with a fourth pictogram arriving. The
    viewer has seen the composition by beat 1; beats 2 and 3 add a box to it. That
    is the "same visual for every point" complaint, scoring a pass.

    GROWTH IS NOT FORBIDDEN, it is just not sufficient ON ITS OWN. A short whose
    every transition is an append is a single slide revealed in pieces. One append
    among real changes is fine, and the caller only fails a short where growth (or
    a moved accent) is the ONLY thing that ever happens.

    Requires the same template and the same drawn pictograms in order, with `a`'s
    labels appearing in `b` in the same order — an append or an insert, with nothing
    removed and nothing replaced. A frame that REPLACES an element is a real change
    and is deliberately not matched here.
    """
    if a.template != b.template:
        return False
    ga, gb = [g.icon for g in a.glyphs], [g.icon for g in b.glyphs]
    la, lb = _frame_labels(a), _frame_labels(b)
    if (len(ga), len(la)) == (len(gb), len(lb)):
        return False                      # same size — that is _near_same's job
    if len(ga) > len(gb) or len(la) > len(lb):
        return False                      # b is smaller: something was removed
    return _is_subsequence(ga, gb) and _is_subsequence(
        [_norm_label(x) for x in la], [_norm_label(x) for x in lb])


def _norm_label(text: str) -> frozenset:
    """A label as the stem set a viewer reads, so a parenthetical is not a change."""
    return frozenset(_stems(str(text))) or frozenset([str(text).strip().lower()])


def _is_subsequence(small: list, big: list) -> bool:
    """Does `small` appear inside `big` in order, allowing gaps?"""
    it = iter(big)
    return all(any(x == y for y in it) for x in small)


def check_frames_progress(unit: ShortUnit) -> GraderResult:
    """
    Across a short, does the COMPOSITION move through different states?

    THE COMPLAINT THIS EXISTS FOR: "for a theory topic it giving the same visual for
    all the points so it looks not good and repetitive". Six of the 32 units in
    output/ were one shape end to end and every one of them passed every design
    grader there was.

    THIS REPLACES check_frames_vary_template, WHICH MEASURED THE WRONG THING.
    That grader answered the complaint by counting distinct TEMPLATES and failing a
    short built from one. Template count is a proxy for repetitiveness and it is a
    bad one in both directions:

      * It failed a short that is genuinely good. The reel this was rewritten for
        holds ONE two-column `compare` scaffold under a constant title and replaces
        what is in the columns on every beat — Target element, then Scoreboard, then
        the three score components, then the two actual scores, then the winner lit
        and the loser dimmed. Five `compare` frames, five different pictures, one
        idea developed. The old grader called that "one layout repeated".
      * It would pass a short that is genuinely bad. Four `icons` rows and one
        `stat` card is two templates and still four rows of pictograms.

    A persistent scaffold whose contents change is not repetition — it is how a
    diagram teaches a process, a comparison or a data structure, and it is what the
    educational reels this project is modelled on actually do. So the question asked
    here is the one the complaint is really about: HOW MANY DIFFERENT PICTURES DOES
    THE VIEWER SEE, whatever template they are drawn in.

    TEMPLATE IS DELIBERATELY NOT CONSULTED. Changing template is neither necessary
    nor sufficient for visual storytelling, and rewarding it produced shorts that
    switched layout to satisfy a counter while saying the same thing twice.

    WHAT THIS DOES NOT DO IS DUPLICATE frames_develop, and the division matters
    because two graders measuring one thing is how thresholds drift apart. That one
    is about PAIRS — does each transition change the picture. This is about the
    WHOLE SHORT — how many distinct pictures there are in total. A short can pass
    pair by pair and still cycle between two states; it can fail one pair and still
    take the viewer somewhere over five beats.

    Held to shorts with three or more distinct frames: two frames of one picture is
    a held composition, which frames_develop reasons about properly.
    """
    refs: list[str] = []
    for beat in unit.beats:
        if not refs or refs[-1] != beat.visual_ref:
            refs.append(beat.visual_ref)
    frames = [unit.visuals[r].frame for r in refs
              if r in unit.visuals and unit.visuals[r].frame is not None]
    if len(frames) < 3:
        return GraderResult("frames_progress", True,
                            f"{len(frames)} frame(s) — too few to call repetitive")

    # WHAT THE VIEWER SEES, and the content half is separated from the accent half
    # on purpose. A frame is what it DRAWS (its labels and pictograms) plus where
    # the accent sits. Two frames with the same labels and a different accent are
    # the same picture with the highlight moved — which is a real thing a beat may
    # do, and is not a new picture.
    contents = [(f.template, tuple(_frame_labels(f)), tuple(g.icon for g in f.glyphs),
                 _slot_states(f))
                for f in frames]
    states = [(c, _roles(f)) for c, f in zip(contents, frames)]

    distinct_content = len(set(contents))
    distinct_states = len(set(states))

    if distinct_content < 2:
        return GraderResult("frames_progress", False,
            f"all {len(frames)} frames draw the same thing "
            f"({frames[0].template}: {', '.join(_frame_labels(frames[0])[:4]) or 'no labels'})"
            f" — only the accent moves, so the viewer reads the whole picture in the "
            f"first two seconds and then watches a highlight slide over it for the "
            f"rest of the short. Change what is DRAWN between beats: replace a "
            f"label, swap the elements, show the next state of the thing.",
            {"frames": len(frames), "distinct_content": distinct_content,
             "distinct_states": distinct_states})

    # More than one picture, but not many: a composition that alternates between two
    # states across five beats is still a short with two pictures in it.
    #
    # MIN_PROGRESS_SHARE of the frames, rather than a flat count, because the defect
    # scales with length — two pictures across three frames is a build, two across
    # six is a loop.
    needed = max(2, ceil(len(frames) * MIN_PROGRESS_SHARE))
    if distinct_content < needed:
        return GraderResult("frames_progress", False,
            f"{len(frames)} frames but only {distinct_content} different picture(s) — "
            f"the composition cycles rather than develops, so beats share a picture "
            f"with a beat the viewer has already seen. At this length it needs at "
            f"least {needed}.",
            {"frames": len(frames), "distinct_content": distinct_content,
             "distinct_states": distinct_states})

    return GraderResult("frames_progress", True,
        f"{distinct_content} different picture(s) across {len(frames)} frames"
        + (f", {distinct_states} counting the accent" if distinct_states > distinct_content else "")
        + f" ({len(set(f.template for f in frames))} template(s), which is not what is measured)",
        {"frames": len(frames), "distinct_content": distinct_content,
         "distinct_states": distinct_states})


def check_template_data_present(unit: ShortUnit) -> GraderResult:
    """
    A frame whose template needs a specific structured field actually has one.

    THE FAILURE THIS CATCHES, found on the first real generation with `graph`:
    the design step chose template="graph" for every frame of a dependency
    explanation, and `frame.graph` was None on all five — the model picked the
    right ENUM value without also filling the field it names. Both fields are
    `Optional[...] = None`, so a JSON reply that simply omits the key validates
    cleanly and silently defaults to empty; nothing raised, nothing warned. The
    renderer then falls back to an empty container (`frame.store or Store()`,
    `frame.graph or Graph()`), so every such frame drew the same blank shape, and
    the FIRST symptom anyone saw was two graders later: frames_develop reporting
    the frames as byte-identical, with no way to tell "the model drew nothing"
    from "the model genuinely repeated itself".

    So this checks the one thing that actually went wrong, directly, rather than
    waiting for its downstream symptom. Free — it reads the Frame, no model call.
    """
    empty: list[str] = []
    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None:
            continue
        if frame.template == "state":
            if frame.store is None or not frame.store.slots:
                empty.append(f"{ref}: template is \'state\' but store has no slots")
        elif frame.template == "graph":
            if frame.graph is None or (
                    not frame.graph.root.label and not frame.graph.branches):
                empty.append(f"{ref}: template is \'graph\' but graph has no "
                             f"root and no branches")
    if empty:
        return GraderResult("template_data_present", False,
            "; ".join(empty[:3]) +
            ". Choosing this template is not enough — fill the field it names, "
            "or the frame renders as an empty container/graph with nothing in it.",
            {"empty": empty})
    return GraderResult("template_data_present", True,
                        "every state/graph frame has real content")


def check_frames_are_visual(unit: ShortUnit) -> GraderResult:
    """
    A frame has to be a PICTURE of the idea, not the sentence about it in a box.

    THE COMPLAINT THIS EXISTS FOR, in the words it arrived in: "most of the visuals
    are just text not the visuals and the text is also just as the voice
    background." Measured on the units in output/ at the time, that was three
    separate defects and every short had at least two of them:

      1. Every short ended on a "takeaway" frame — one spoken sentence set large.
      2. 6 of 11 frames carried a `note` line, and what was in it was the narration:
         "Student: Contiguous allocation forces one unbroken block per process."
      3. `bar` frames whose cells WERE the beats: ["font-family?", "Import font
         CSS", "Which typeface"] — the dialogue laid out as rectangles.

    None of the three could fail a check. svg_problems only asks whether text is
    legible, and a slide of the voiceover is perfectly legible. Nothing measured
    whether a frame drew anything. So this does, from the Frame rather than the
    markup, because the Frame is where the defect is decided.

    Three separate failures, all of them structural and none of them a judgement
    call — which is what keeps this free and keeps it out of the judge's way.
    """
    text_cards: list[str] = []
    sentences: list[str] = []
    echoes: list[str] = []

    # Every beat's spoken line, to compare a frame's labels against. A frame plays
    # under one beat, but the composition is shared across all of them, so a label
    # echoing ANY beat of this short is the same defect.
    spoken = {ref: [] for ref in unit.visuals}
    for beat in unit.beats:
        if beat.visual_ref in spoken:
            spoken[beat.visual_ref].append(beat.line)

    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None:
            continue

        if frame.template in _TEXT_ONLY_TEMPLATES:
            text_cards.append(f"{ref} is a {frame.template!r} card — a sentence, not a diagram")
            continue

        labels = _frame_labels(frame)
        long = [lab for lab in labels if len(_prose_words(lab)) > MAX_LABEL_WORDS]
        if long:
            sentences.append(f"{ref}: label is a sentence — {long[0][:60]!r}")

        # Does the frame reproduce what is being said? Content words only, so
        # "the", "a", "of" cannot carry a frame over the threshold on their own.
        #
        # LITERALS ARE EXCLUDED FROM THE COMPARISON, and that is the difference
        # between this grader's defect and its opposite. What it exists to catch is
        # a frame that prints the SENTENCE:
        #
        #   label: "Contiguous allocation forces one unbroken block per process"
        #
        # What it was also catching is a worked-example frame doing its job. From a
        # real reel, the beat "So `#nav .item a` counts to 1,1,1, while
        # `.item .link a` counts to 0,2,1" against a frame whose columns are headed
        # `#nav .item a` and `.item .link a` and whose cells read 1 ID, 1 Class,
        # 1 Type / 0 IDs, 2 Classes, 1 Type. 86% echo, and every shared word is a
        # selector or a number — the exact literals the picture has to show for the
        # example to be worked at all. Drawing them is not reciting the sentence;
        # it is the only way to draw that sentence's subject.
        #
        # So the echo is measured on the PROSE the beat uses to frame its literals.
        # A frame that also prints "counts to" and "while" is still caught, because
        # those are prose. skills/visuals.py is told the same thing in words.
        drawn = set(_stems(" ".join(labels)))
        for line in spoken.get(ref, []):
            literal_stems: set[str] = set()
            for span in _literals(line):
                literal_stems |= set(_stems(span))
            # And a NUMERAL is never prose, whether or not _literals caught it as a
            # span. Its digit pattern deliberately needs three characters, so "36px"
            # is a literal and the "1,1,1" in "counts to 1,1,1" is three separate
            # one-character stems that survive into the prose set — where they then
            # match the 1 ID / 1 Class / 1 Type the frame has to draw. Any stem
            # carrying a digit comes out.
            said = {t for t in (set(_stems(line)) - literal_stems)
                    if not any(ch.isdigit() for ch in t)}
            if len(said) < 4:
                continue
            share = len(said & drawn) / len(said)
            if share > MAX_NARRATION_ECHO:
                echoes.append(f"{ref}: {share:.0%} of the spoken line's PROSE is printed "
                              f"in the frame — draw the subject, not the sentence "
                              f"(literals the beat names are not counted)")
                break

    # A "stat" FRAME WHOSE VALUE IS NOT A VALUE IS A WORD ON A CARD.
    #
    # From a reel built on a computing-systems document, and it is the worst frame
    # this pipeline has produced since the takeaway card was removed:
    #
    #     template "stat", title "What is being asked",
    #     value "Computing system", caption "Computing system"
    #
    # The same two words, printed twice, under a title saying a question is being
    # asked. It is the opening frame of the short, so a viewer's first two seconds
    # are spent reading one noun three times.
    #
    # `stat` exists for "4 GB" — a FIGURE that is the whole content of a beat. Used
    # for a bare noun it is the takeaway card wearing a different template name, and
    # the brief's own words for it were "a frame whose whole content is a figure".
    # So: a stat frame must carry a digit, and its caption must add something its
    # value and title do not already say.
    filler_stats: list[str] = []
    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None or frame.template != "stat":
            continue
        value = str(frame.value or "").strip()
        caption = str(frame.caption or "").strip()
        title = str(frame.title or "").strip()
        if not any(ch.isdigit() for ch in value):
            filler_stats.append(
                f"{ref}: a 'stat' frame whose value is {value!r} — not a figure. "
                f"This template is for a number that IS the beat ('4 GB'); a bare "
                f"noun set large is a word on a card. Draw the thing instead")
        elif caption.lower() in (value.lower(), title.lower()) or not caption:
            filler_stats.append(
                f"{ref}: 'stat' caption {caption!r} repeats its own value/title — "
                f"the caption must NAME the figure ('addressable bytes'), not echo it")

    # A TABLE WHOSE ROWS REPEAT ITS OWN HEADERS IS NOT A LOOKUP.
    #
    # Found by the judge, not by anything here: "rows repeat the column headers as
    # cell values ('Page number', 'Frame number', 'Valid bit' in every row), so it
    # draws no actual lookup". Structurally it is a well-formed table and every
    # label is on-vocabulary, so nothing failed it. What is on screen is a header
    # row printed four times — the shape of a page table with none of its content,
    # which teaches nothing about the thing it is a picture of.
    empty_tables: list[str] = []
    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None or frame.template != "table" or not frame.rows:
            continue
        heads = [h.strip().lower() for h in frame.columns]
        if not heads:
            continue
        echoing = sum(1 for row in frame.rows
                      if [c.strip().lower() for c in row.cells][:len(heads)] == heads)
        if echoing == len(frame.rows):
            empty_tables.append(f"{ref}: every row repeats the column headers "
                                f"({', '.join(frame.columns[:3])}) — the table shows "
                                f"no values, so it draws no lookup")

    problems = text_cards + sentences + echoes + filler_stats + empty_tables
    if problems:
        return GraderResult("frames_are_visual", False, "; ".join(problems[:3]),
                            {"problems": problems})
    return GraderResult("frames_are_visual", True,
                        "no frame is a slide of its own narration")


#: Words whose presence in a glyph label means the label names TYPOGRAPHY, which is
#: the one subject the `text` pictogram — a capital A — is an honest drawing of.
_TYPE_WORDS = {"font", "fonts", "typeface", "typefaces", "text", "type", "family",
               "serif", "italic", "bold", "weight", "letter", "letters", "character",
               "characters", "heading", "paragraph", "word", "words", "caption",
               "label", "style", "styling"}


def check_icons_are_pictures(unit: ShortUnit) -> GraderResult:
    """
    An `icons` glyph must be a PICTURE OF ITS LABEL, not the nearest shape to hand.

    THE COMPLAINT THIS EXISTS FOR: "if any image not able to display then it simply
    showing A". There is no failed image. `text` is a real pictogram and it draws a
    capital A, which is the right picture for a font and a wrong one for everything
    else — and the model was reaching for it whenever a label named something
    abstract, because nothing on the list was a picture of that thing.

    Measured across fifteen shipped shorts: `text` used 11 times, `box` 6 times. A
    capital A labelled "HTTP". A capital A labelled "Authentication". An empty box
    labelled "Printer". Every one of those is a confident visual claim about what
    the thing IS, made to a learner who believes a picture faster than a sentence.

    Two failures, both structural:

      `box` at all — it is the renderer's do-not-know fallback, so a frame that asks
            for it is asking to draw nothing. It is no longer offered in the brief;
            this catches it being named anyway.
      `text` on a label that is not about type — the capital A is only true of
            typography. `font`, `typeface`, `bold`, `heading` keep it; `HTTP`,
            `Authentication`, `Network` do not.

    Fixing the vocabulary was the other half of this: layout.PICTOGRAMS gained
    server, network, cloud, globe, lock, key, shield, user, printer, clock, list,
    folder, database and gear, so the label that used to have no picture now has
    one. A grader without those additions would only have converted a bad drawing
    into a rejected short.
    """
    from .skills.layout import LITERAL_ICONS

    problems: list[str] = []
    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None or not frame.glyphs:
            continue
        for glyph in frame.glyphs:
            if glyph.icon not in LITERAL_ICONS:
                continue
            label = str(glyph.label or "").strip()
            if glyph.icon == "box":
                problems.append(
                    f'{ref}: glyph "{label}" uses icon "box", which draws an empty '
                    f"rectangle — pick a pictogram of the thing, or use a template "
                    f"built for claims rather than for objects")
                continue
            # "text" draws a capital A. Honest for type, a mis-claim for anything else.
            if not (set(_stems(label)) & {_stem(w) for w in _TYPE_WORDS}):
                problems.append(
                    f'{ref}: glyph "{label}" uses icon "text", which draws a CAPITAL '
                    f'A — that says "{label}" is typography. Use a pictogram of what '
                    f"it actually is, or draw what it acts on instead")

    if problems:
        return GraderResult("icons_are_pictures", False, "; ".join(problems[:3]),
                            {"problems": problems})
    return GraderResult("icons_are_pictures", True,
                        "every pictogram draws the thing its label names")


def _frame_fingerprint(frame) -> tuple:
    """Everything a frame draws EXCEPT which element is emphasised.

    Two frames with the same fingerprint are the same picture; if their roles also
    match they are the same frame twice, and if only the roles differ they are one
    slide with the accent moved.
    """
    return (
        frame.template,
        tuple(_frame_labels(frame)),
        tuple(str(c.label) for c in frame.code_lines),
        tuple(g.icon for g in frame.glyphs),
        tuple((s.text, s.label, s.font, s.scale, s.weight, s.italic, s.decoration)
              for s in frame.samples),
    )


def _near_same(a, b) -> bool:
    """
    Are these two frames the same picture, allowing for a cosmetic label edit?

    THE HOLE THIS CLOSES. _frame_fingerprint compares labels EXACTLY, so a frame
    passed as "developed" if a single word changed anywhere in it. Measured on a
    freshly built operating-system reel, whose beats 1 and 3 were:

        icons: Users, Applications, Operating System, Hardware
        icons: Users, Applications, Operating System, Hardware (CPU, I/O, RAM)

    Identical drawing, identical roles, identical everything a viewer perceives —
    four pictograms in the same order with the same one lit. The parenthetical made
    the fingerprints differ, so the short passed a grader written to catch precisely
    this, and the reviewer's complaint came back word for word: "if visuals present
    also its showing same visuals again and again which feel bore".

    So the comparison is now on the STRUCTURE a viewer sees — template, the drawn
    pictograms, the count of elements, and the label STEMS — rather than on label
    text. Two frames whose labels differ only by an added qualifier, a pluralisation
    or a parenthetical are the same picture, because that is what they look like.
    """
    if a.template != b.template:
        return False
    if tuple(g.icon for g in a.glyphs) != tuple(g.icon for g in b.glyphs):
        return False
    # A SLOT'S STATE IS PART OF THE PICTURE, not part of the accent. `resting`
    # draws the item inside the container; `arriving` and `leaving` draw it OUTSIDE
    # with an arrow. So two frames with identical slot labels can be entirely
    # different drawings, and comparing labels alone called them the same one.
    #
    # Measured on a real stack short: frame 1 showed A, B, C with B leaving from
    # the middle, and frame 3 showed A, B, C all resting. Same labels, and the
    # `returns` check reported frame 3 as "the same picture as frame 1", so a short
    # that had just demonstrated an invalid pop and then shown the settled stack
    # was failed for revisiting where it started.
    if _slot_states(a) != _slot_states(b):
        return False
    la, lb = _frame_labels(a), _frame_labels(b)
    if len(la) != len(lb):
        return False
    # Stem-set overlap per label: "Hardware" vs "Hardware (CPU, I/O, RAM)" shares
    # its whole first stem set, so it reads as the same box with a note added.
    for x, y in zip(la, lb):
        sx, sy = set(_stems(x)), set(_stems(y))
        if not sx or not sy:
            if x.strip().lower() != y.strip().lower():
                return False
            continue
        if not (sx <= sy or sy <= sx):
            return False
    ca = (tuple(str(c.label) for c in a.code_lines),
          tuple((s.text, s.font, s.scale, s.weight, s.italic, s.decoration) for s in a.samples))
    cb = (tuple(str(c.label) for c in b.code_lines),
          tuple((s.text, s.font, s.scale, s.weight, s.italic, s.decoration) for s in b.samples))
    return ca == cb


def check_frames_develop(unit: ShortUnit) -> GraderResult:
    """
    Across a short, the picture has to actually CHANGE, not just move its highlight.

    THE COMPLAINT THIS EXISTS FOR: "for all the slides its just getting the same
    slide visual and it just highlighting the text". Exactly right, and it was the
    documented design — SPEC_SYSTEM asked for one composition with the accent moving
    between beats, on the reasoning that a viewer remembers one assembled diagram
    better than four unrelated ones.

    That reasoning holds for a diagram that ASSEMBLES. It does not hold for one that
    merely recolours. A seven-line code panel with line 3 lit, then line 2, then
    line 3 again is a single still image on screen for the whole video: everything
    readable is read in the first two seconds and then nothing happens for twelve.
    The build was supposed to pace the explanation and instead it removed the reason
    to keep watching.

    So EVERY transition must change what is on screen, not just what is amber. The
    first cut of this grader only failed a short where ALL transitions were
    roles-only, on the theory that spending one beat of three on a moved accent is
    fine. Measured against real output that was too loose: the shape that came back
    was "same code panel, accent moved, then one real picture at the end", which
    still opens on a static slide for the first two thirds of the video — the exact
    thing being complained about, now scoring a pass.

    A beat with nothing new to show does not need a frame of its own. Two beats can
    share one visual_ref, which holds the picture still and is honest about it; what
    is not allowed is two frames pretending to be different pictures.

    This reports, it does not gate — no retry loop hangs off it, so tightening it
    costs nothing but a warning that tells the truth.
    """
    # In BEAT order, deduplicated: consecutive beats deliberately sharing one
    # visual_ref are one frame held across two lines, which is a pacing choice
    # rather than a repeated picture.
    refs: list[str] = []
    for beat in unit.beats:
        if not refs or refs[-1] != beat.visual_ref:
            refs.append(beat.visual_ref)

    frames = [unit.visuals[r].frame for r in refs
              if r in unit.visuals and unit.visuals[r].frame is not None]
    if len(frames) < 2:
        return GraderResult("frames_develop", True, "single frame, nothing to compare")

    identical, roles_only, grew, total = [], 0, 0, 0
    for a, b in zip(frames, frames[1:]):
        total += 1
        # _near_same, not fingerprint equality: a label with a parenthetical added
        # is the same picture, and comparing label text exactly let that through.
        if not _near_same(a, b):
            # AN APPEND IS NOT A NEW PICTURE EITHER. See _only_grew: the shipped
            # HTTP short grew Browser+Server into Browser+HTTP+Server into
            # Browser+HTTP+Server+Developer and passed every transition, because
            # each one "changed". Counted separately from roles_only so the failure
            # message can say which of the two shapes it actually is.
            if _only_grew(a, b):
                grew += 1
            continue
        roles_only += 1
        if _roles(a) == _roles(b):
            identical.append(b.template)

    # A FRAME THAT RETURNS TO AN EARLIER ONE HAS NOT DEVELOPED EITHER.
    #
    # The consecutive check above misses the shape a freshly built operating-system
    # reel actually had: frame 1 and frame 3 the same four pictograms, frame 2
    # different. Every ADJACENT pair changes, so it passed — and the short still
    # ends where it started, which is the complaint ("showing same visuals again and
    # again which feel bore"). A composition that builds does not revisit; if beat 3
    # genuinely wants beat 1's picture back, it should share beat 1's visual_ref and
    # be honest that the picture is being held.
    returns: list[str] = []
    for i in range(len(frames)):
        for j in range(i + 2, len(frames)):
            if _near_same(frames[i], frames[j]):
                returns.append(f"frame {j + 1} is the same picture as frame {i + 1} "
                               f"({frames[j].template}) — the composition returns to "
                               f"where it started instead of building")

    if identical:
        return GraderResult("frames_develop", False,
                            f"{len(identical)} consecutive frame(s) are byte-identical "
                            f"({', '.join(identical[:3])}) — the same picture twice")
    if returns:
        return GraderResult("frames_develop", False, "; ".join(returns[:2]),
                            {"problems": returns})
    # A MOVED ACCENT MAY BE A MINORITY OF THE TRANSITIONS, NOT MOST OF THEM.
    #
    # This used to fail on ANY roles-only transition, and that was too strict for a
    # reason worth writing down. The reel this was loosened for holds a two-column
    # `compare` scaffold and replaces its contents on every beat; its LAST
    # transition keeps the two scores on screen and re-roles them — the winning
    # column to hero, the losing one to lost, the tied rows to quiet. That is the
    # climax of the short. Nothing new is drawn because nothing new is needed: the
    # picture has been assembled and the final beat delivers the verdict ON it, and
    # dimming the loser is the verdict. Failing that is failing the payoff.
    #
    # But the shape this grader was written for is still a defect, and it is a
    # MAJORITY shape: "same code panel, accent moved, then one real picture at the
    # end" opens on a static slide for two thirds of the video. So the rule is
    # proportional rather than absolute.
    #
    # A THIRD, and the arithmetic is what picks it rather than roundness:
    #   2 transitions, 1 roles-only  -> 3 > 2, FAILS. Half a short is not a payoff.
    #   3 transitions, 1 roles-only  -> 3 = 3, passes. Two real changes carry it.
    #   4 transitions, 1 roles-only  -> 3 < 4, passes. The reel above.
    #   3 transitions, 2 roles-only  -> 6 > 3, FAILS. The shape complained about.
    if roles_only * 3 > total:
        return GraderResult("frames_develop", False,
                            f"{roles_only} of {total} frame transition(s) only move the "
                            f"accent on the same picture — the viewer sees one static "
                            f"slide with a highlight sliding over it. One such beat is "
                            f"allowed as a payoff on an assembled picture; this many is "
                            f"the short standing still.")
    # EVERY transition an append means the whole short is one composition revealed
    # in pieces — nothing is ever replaced, so beat 1 already showed the shape. One
    # append among real changes is a legitimate build and is not failed here.
    if grew and grew == total:
        return GraderResult("frames_develop", False,
                            f"all {total} transition(s) only ADD to the previous frame "
                            f"— the picture never changes, it only grows, so the viewer "
                            f"has seen the whole composition by the first beat. Replace "
                            f"something, or give a beat a different kind of picture")
    return GraderResult("frames_develop", True,
                        f"all {total} transition(s) change the picture"
                        + (f" ({grew} by adding to it)" if grew else ""))


def _unique_frames(unit: ShortUnit) -> list:
    """Frames in beat order, deduplicated exactly like check_frames_develop's own
    walk — consecutive beats sharing one visual_ref are one held picture, not a
    repeat to compare against itself.
    """
    refs: list[str] = []
    for beat in unit.beats:
        if not refs or refs[-1] != beat.visual_ref:
            refs.append(beat.visual_ref)
    return [unit.visuals[r].frame for r in refs
            if r in unit.visuals and unit.visuals[r].frame is not None]


def _store_labels(frame, states: tuple[str, ...] | None = None) -> set[str]:
    """Labels currently occupying a slot, optionally restricted to given states."""
    store = getattr(frame, "store", None)
    if store is None:
        return set()
    return {slot.label for slot in store.slots
            if slot.label and (states is None or slot.state in states)}


def check_state_item_transitions_visible(unit: ShortUnit) -> GraderResult:
    """
    An insert must be SEEN arriving; a remove must be SEEN leaving and gone.

    THE GAP THIS CLOSES. Slot.state (resting/arriving/leaving) and layout.py's
    renderer already exist specifically so a push or a pop is a picture rather
    than a relabelled box — but nothing before this compared one state frame
    to the next to confirm the fields were actually used that way. A design
    step can add a new label straight into "resting" (the item simply exists
    now, with no arriving frame ever drawn) or drop a label with no slot ever
    marked "leaving" for it, and every existing grader passes both: the
    template is right (check_frames_match_strategy), the physical form is
    right (check_physical_form_matches_template), and the picture did change
    (check_frames_develop) — it just changed by teleportation instead of by
    the motion the renderer exists to draw.

    THREE RULES, walking consecutive DISTINCT `state` frames in beat order:

      INSERTION MUST BE SEEN. A label present in this frame that was not
      present in ANY state in the previous frame is new — and if it is not
      marked "arriving" in THIS frame, it appeared with no arrival drawn.

      REMOVAL MUST BE SEEN. A label present in the previous frame that is
      gone from this one is removed — and unless one of the two frames marked
      it "leaving", it vanished with no departure drawn.

      A DEPARTURE MUST FINISH. A label marked "leaving" in one frame must not
      still be present, in any state, in the NEXT one — "leaving" that never
      actually leaves is a removal that never completes.

    Only ever compares a `state` frame to the state frame next to it — a
    beat's own frame paired with a different template's neighbour has nothing
    to compare, so those pairs are skipped rather than treated as a violation.
    """
    frames = [f for f in _unique_frames(unit) if f.template == "state" and f.store]
    if len(frames) < 2:
        return GraderResult("state_item_transitions_visible", True,
                            "fewer than two state frames — nothing to compare")

    problems = []
    for i in range(len(frames) - 1):
        prev, curr = frames[i], frames[i + 1]
        prev_all = _store_labels(prev)
        curr_all = _store_labels(curr)
        curr_arriving = _store_labels(curr, ("arriving",))
        prev_leaving = _store_labels(prev, ("leaving",))
        curr_leaving = _store_labels(curr, ("leaving",))

        for label in curr_all - prev_all:
            if label not in curr_arriving:
                problems.append(
                    f"'{label}' appears in the container with no frame showing it "
                    f"arriving — the insertion is invisible, not a frame this "
                    f"pipeline drew an entrance for")

        for label in prev_all - curr_all:
            if label not in prev_leaving and label not in curr_leaving:
                problems.append(
                    f"'{label}' is gone from the container with no frame marking "
                    f"it leaving — the removal is invisible, it simply stopped "
                    f"being drawn")

        for label in prev_leaving:
            if label in curr_all:
                problems.append(
                    f"'{label}' was marked leaving and is still in the container "
                    f"on the next frame — the departure never completes")

    if problems:
        return GraderResult("state_item_transitions_visible", False, "; ".join(problems[:4]),
                            {"problems": problems})
    return GraderResult("state_item_transitions_visible", True,
                        f"{len(frames)} state frame(s), every insertion and removal is shown")


def check_state_pointer_moves_are_shown(unit: ShortUnit) -> GraderResult:
    """
    A retargeted pointer must actually retarget, and a moved pointer must be
    marked so the renderer can show it moving.

    Store.pointer_at_previous exists for exactly one reason — see its own
    docstring — "the literal 'a pointer disconnecting and reconnecting' the
    product brief asked for". Two ways that promise goes unfulfilled, and
    nothing before this caught either:

      SET BUT UNCHANGED. pointer_at_previous is filled in with the SAME value
      as pointer_at — a retarget that asks for no animation, which the field's
      own docstring already names as the thing not to do. Structurally valid,
      renders as a pointer that never appears to move.

      MOVED BUT UNMARKED. The pointer's target genuinely differs from the
      previous state frame's, but pointer_at_previous was left empty — the
      pointer will render already arrived at its new slot with no frame
      showing it leaving the old one, the same silent teleport
      check_state_item_transitions_visible catches for an item, here for the
      index that names one.

    Skipped for a container whose pointer is absent (`-1`, or `None`) on
    either side of the comparison — there is nothing to retarget.
    """
    frames = [f for f in _unique_frames(unit) if f.template == "state" and f.store]
    problems = []

    for f in frames:
        s = f.store
        if s.pointer_at is not None and s.pointer_at_previous is not None \
                and s.pointer_at == s.pointer_at_previous:
            problems.append(
                "pointer_at_previous is set to the same slot as pointer_at — "
                "that asks for no movement, so either the pointer did not "
                "actually move this beat (leave pointer_at_previous out) or "
                "the previous position was written wrong")

    for i in range(len(frames) - 1):
        prev, curr = frames[i].store, frames[i + 1].store
        if prev.pointer_at is None or curr.pointer_at is None:
            continue
        if prev.pointer_at == curr.pointer_at:
            continue
        if curr.pointer_at_previous is None:
            problems.append(
                f"the pointer moved from slot {prev.pointer_at} to slot "
                f"{curr.pointer_at} between frames but pointer_at_previous was "
                f"not set on the new frame — the move renders as already "
                f"arrived, with no disconnect-and-reconnect shown")

    if problems:
        return GraderResult("state_pointer_moves_are_shown", False, "; ".join(problems[:4]),
                            {"problems": problems})
    return GraderResult("state_pointer_moves_are_shown", True,
                        "every pointer retarget is marked so it renders as movement")


def check_flow_traversal_progresses(unit: ShortUnit) -> GraderResult:
    """
    A traversal must visibly ADVANCE — the same chain, a different node lit.

    THE GAP. Rule 6/8 already say a process or a data movement must be drawn
    happening rather than named, and check_motion_concept_not_static catches a
    whole short that never leaves a static template — but nothing checks the
    one shape a `flow` traversal specifically takes: the SAME nodes, in the
    SAME order, beat after beat, with only the hero moving along them. That
    is the correct drawing of "follow the pointer node by node" — a fresh set
    of boxes every beat would be a different claim — so it must not regress:
    two consecutive `flow` frames over the identical chain with the hero on
    the SAME node, or moved backwards, is a traversal that is not going
    anywhere on screen while the narration says it is.

    Only checked when consecutive `flow` frames draw the SAME steps in the
    SAME order — a beat that genuinely redraws a different or reordered chain
    is a different picture, already covered by check_frames_develop, and not
    what this asks about.
    """
    frames = [f for f in _unique_frames(unit) if f.template == "flow" and f.steps]
    if len(frames) < 2:
        return GraderResult("flow_traversal_progresses", True,
                            "fewer than two flow frames — nothing to compare")

    problems = []
    for i in range(len(frames) - 1):
        prev, curr = frames[i], frames[i + 1]
        prev_labels = [c.label for c in prev.steps]
        curr_labels = [c.label for c in curr.steps]
        if prev_labels != curr_labels:
            continue  # a different chain — not this check's question

        def _hero_index(steps):
            for idx, c in enumerate(steps):
                if c.role == "hero":
                    return idx
            return None

        prev_hero, curr_hero = _hero_index(prev.steps), _hero_index(curr.steps)
        if prev_hero is None or curr_hero is None:
            continue
        if curr_hero <= prev_hero:
            problems.append(
                f"the same {len(curr_labels)}-node chain is drawn again with the "
                f"hero at node {curr_hero} after being at node {prev_hero} — a "
                f"traversal must move to a LATER node each frame, not hold "
                f"still or move backwards")

    if problems:
        return GraderResult("flow_traversal_progresses", False, "; ".join(problems[:4]),
                            {"problems": problems})
    return GraderResult("flow_traversal_progresses", True,
                        f"{len(frames)} flow frame(s), the traversal advances each time")


def _slot_states(frame) -> tuple:
    """Which of a store's slots are resting, arriving or leaving.

    Separate from _roles because these are two different questions and the frame
    comparisons need them apart: a role says which element is ACCENTED, a state
    says where the element is DRAWN. Changing an accent is not a new picture;
    moving an item out of the container is.
    """
    store = getattr(frame, "store", None)
    if store is None:
        return ()
    return tuple((slot.label, slot.state) for slot in store.slots)


def _roles(frame) -> tuple:
    """Which element is emphasised, across every template that has elements."""
    return (
        tuple(c.role for c in frame.cells + frame.left + frame.right
              + frame.parts + frame.steps + frame.code_lines),
        tuple(r.role for r in frame.rows),
        tuple((p.role, tuple(i.role for i in p.items)) for p in frame.panels),
        # analogy's right-hand Panel, same shape as the panels tuple above —
        # its LEFT side (a photo) carries no role, so it is not part of this.
        ((frame.analogy_technical.role,
          tuple(i.role for i in frame.analogy_technical.items))
         if frame.analogy_technical is not None else ()),
        tuple(g.role for g in frame.glyphs),
        tuple(s.role for s in frame.samples),
        # A store's roles AND its slot states. The state belongs here rather than
        # with the labels because a frame whose only change is that the top item is
        # now leaving HAS changed what the viewer sees, and _roles is what
        # frames_develop compares when the labels are equal.
        tuple((sl.role, sl.state) for sl in (frame.store.slots if frame.store else ())),
        # A graph's root and its branches — same reasoning as a store's slots:
        # which node is lit is part of the picture, so two frames differing only
        # in which branch is the hero are different pictures, not the same one
        # with an accent moved.
        ((frame.graph.root.role,) if frame.graph else ())
        + tuple(br.node.role for br in (frame.graph.branches if frame.graph else ())),
    )


#: What a `preview` sample actually RENDERS. Its label is a claim about the effect;
#: this is the effect. If two samples have the same tuple they look identical, and
#: any label that says otherwise is a caption the picture does not support.
def _sample_render(sample) -> tuple:
    from .skills.layout import _colour, _font_stack
    return (_font_stack(sample.font), sample.scale, sample.weight, sample.italic,
            sample.decoration, _colour(sample.color), _colour(sample.background))


def check_samples_differ(unit: ShortUnit) -> GraderResult:
    """
    A `preview` frame that claims two things look different must SHOW them different.

    THE COMPLAINT THIS EXISTS FOR: a CSS colour short whose frame put "Main heading"
    over the caption "blue" and "Paragraph" over the caption "grey", and rendered
    both in the same near-black ink. The reading material really does say
    `.main-heading { color: blue; }` and `.paragraph { color: grey; }`, the labels
    were right, and the picture still told the viewer that blue and grey are the same
    colour. Watched back, the note taken was "it says main heading is blue but the
    paragraph is blue" — which is exactly what was on screen.

    The cause was a missing field: Sample had nowhere to put a colour, so the model
    put it in the label and the renderer had nothing to draw. That field now exists,
    and this grader is the part that keeps the class of bug from coming back for the
    NEXT property nobody thought of. It does not know what any style means. It only
    asks whether two samples that are captioned differently actually render
    differently — which is checkable, free, and catches every future version of
    "the template cannot express what it is being asked to show".

    Also catches the plain mislabel: a sample captioned with a colour word that
    renders in a different colour.
    """
    problems: list[str] = []

    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None or not frame.samples:
            continue

        seen: dict[tuple, str] = {}
        for sample in frame.samples:
            render = _sample_render(sample)
            label = (sample.label or "").strip()
            twin = seen.get(render)
            if twin is not None and twin.lower() != label.lower():
                problems.append(
                    f"{ref}: samples captioned {twin!r} and {label!r} render "
                    f"identically — the frame claims a difference it does not show")
            seen.setdefault(render, label)

            # A caption that names a colour has to be the colour that is drawn.
            named = _colour_word(label)
            if named and _sample_render(sample)[5] not in (named, None):
                problems.append(f"{ref}: sample captioned {label!r} is drawn in "
                                f"{sample.color!r}")
            elif named and sample.color is None:
                problems.append(f"{ref}: sample captioned {label!r} sets no color, so "
                                f"it renders in the default ink")

            # A caption that repeats the sample's own words says nothing. The label
            # names the STYLE; the text is already on screen, larger.
            if label and label.strip().lower() == (sample.text or "").strip().lower():
                problems.append(f"{ref}: sample caption {label!r} just repeats the "
                                f"sample's own text — caption the style instead")

        # COLOUR IS ALL OR NOTHING WITHIN A FRAME, and this is the rule that caught
        # the real regression. Told that a caption naming a colour must draw that
        # colour, the model's next answer removed the colour from the CAPTIONS
        # instead of adding it to the drawing: two samples labelled "Main heading"
        # and "Paragraph", one blue, one left to default. The material gives a colour
        # for BOTH selectors, so the uncoloured one renders near-black and the frame
        # still tells the viewer that `.paragraph` is black.
        #
        # An unset colour is not neutral — it is a colour, the palette ink, and in a
        # frame that is about colour it reads as a deliberate one. So if any sample
        # states its colour, all of them must.
        coloured = [s for s in frame.samples if _sample_render(s)[5]]
        if coloured and len(coloured) != len(frame.samples):
            bare = [s.label or s.text for s in frame.samples if not _sample_render(s)[5]]
            problems.append(
                f"{ref}: {len(coloured)} of {len(frame.samples)} samples set a color, so "
                f"{bare[:2]} render in the default ink and read as black — give every "
                f"sample in a colour frame its own color")

    if problems:
        return GraderResult("samples_differ", False, "; ".join(problems[:3]),
                            {"problems": problems})
    return GraderResult("samples_differ", True, "preview samples render as captioned")


def _colour_word(label: str) -> str | None:
    """The CSS colour a caption names, if it names exactly one and nothing else."""
    from .skills.layout import CSS_COLOURS
    words = [w for w in re.split(r"[^a-zA-Z#0-9]+", label or "") if w]
    hits = [w.lower() for w in words if w.lower() in CSS_COLOURS]
    # "blue" and "color: blue" both count; "blue vs grey" names two and is a
    # heading for the frame rather than a claim about this one sample.
    return hits[0] if len(hits) == 1 else None


def check_code_frames_quote_source(unit: ShortUnit,
                                   source_text: str | None = None) -> GraderResult:
    """
    Every line of a `code` frame has to occur in the reading material.

    The `code` template was introduced on the argument that it is "grounded by
    construction" — the lines are copied out of the document, so they cannot drift.
    That was an argument about intent, and nothing enforced it. A model asked for the
    document's snippet will happily supply a plausible one, and a plausible CSS rule
    is indistinguishable from a real one to everybody except the document.

    So it is checked, the same way check_source_quotes checks a beat's citation: by
    substring, after flattening whitespace. Free, and not arguable.

    Structural lines are exempt — a bare `}` or `{` is punctuation, not a claim — and
    so is any line the renderer would have elided, since a line the model shortened
    to `@import url("...");` is honest about being shortened.
    """
    if not source_text:
        return GraderResult("code_quotes_source", True, "no source to check against")

    flat_source = _flatten(source_text)
    offenders: list[str] = []
    checked = 0

    for ref, visual in (unit.visuals or {}).items():
        frame = visual.frame
        if frame is None or frame.template != "code":
            continue
        for line in frame.code_lines:
            text = str(line.label).strip()
            # Punctuation-only lines, and lines the model elided on purpose.
            if len(text) < 4 or not re.search(r"[A-Za-z0-9]", text) or "..." in text or "…" in text:
                continue
            checked += 1
            if _flatten(text) not in flat_source:
                offenders.append(f"{ref}: {text[:60]!r} is not in the material")

    if offenders:
        return GraderResult("code_quotes_source", False, "; ".join(offenders[:3]),
                            {"problems": offenders})
    return GraderResult("code_quotes_source", True,
                        f"{checked} code line(s) quoted from the material")


#: Which templates honestly express which kind of claim.
#:
#: This table is the enforceable half of the educational visual rules. Rules 6 to
#: 10 are all of the form "if the concept describes X, the visual must do Y", and
#: until the strategist existed there was no field saying what X was — so they were
#: advice in a prompt and nothing more. With `relationship` written down per beat,
#: most of them become a set membership test that costs nothing.
#:
#: DELIBERATELY PERMISSIVE. Each entry lists every template that can honestly carry
#: that relationship, not the single best one, because picking the best is a
#: judgement and this is a gate. "code" is in almost every row on purpose: the
#: material's own snippet is a legitimate picture of nearly any claim the material
#: makes, and rejecting it would push the designer off the most grounded frame it
#: can draw. What this catches is the flat contradiction — a hierarchy drawn as a
#: row, a comparison split across two beats, a process drawn as a still table.
_RELATIONSHIP_TEMPLATES = {
    # Rule 6: the stages, in order, with the movement between them drawn.
    # "state" is here and FIRST in intent: a process whose stages are states of one
    # container — pushing, popping, filling, draining — is drawn by showing the
    # container in those states, not by a row of boxes naming them.
    #
    # "analogy" too, for the concept-introducing beat rather than the operation
    # beat: "how does a stack work" is a process in the sense that push/pop is
    # ordered, but the FIRST beat of such a short is usually "what IS a stack",
    # which has no stage to animate yet — a real-world analogy plus the still
    # structure is the honest picture for that one beat, and `state` takes over
    # once there is a push or a pop to show happening.
    "process":       {"state", "flow", "icons", "code", "cause_effect", "analogy"},
    # Rule 7: BOTH STATES AT ONCE. A `bar` or a `stat` shows one.
    #
    # "state" satisfies that rule when the two things compared are PLACES IN ONE
    # CONTAINER, which is a real and common case rather than a loophole: "the top
    # slot is reachable and the ones below it are not" is one container with one
    # slot in hero and the rest in quiet, both on screen, no cut in between. A
    # `compare` frame would draw the same stack twice to say it.
    #
    # "graph" for the same reason: "the driver can fail and the scheduler still
    # works" is a comparison between two branches of ONE dependency graph, not two
    # unrelated things — reusing the graph already on screen and marking one
    # branch hero, the other lost, is the SAME persistent-scaffold principle
    # `state` earns its place for, and switching to a fresh `compare` panel here
    # would break the composition the beats before it built.
    "comparison":    {"compare", "preview", "table", "code", "state", "graph"},
    # Rule 8: the thing that moves, where it starts, where it lands. A `state`
    # frame draws exactly that when the destination is a place in a container.
    # `graph` when there are SEVERAL distinct destinations from one source — data
    # fanning out to more than one place, which "cause_effect" (one arrow) and
    # "state" (one container) cannot show at once.
    # "analogy" for the same concept-introduction reason as "process" above: a
    # cache holding a value is data movement in the mature sense (a lookup
    # arrives, a value comes back), but the beat that first names the container
    # is honestly drawn as the borrowed real-world object beside the container's
    # still shape.
    "data_movement": {"state", "icons", "mapping", "flow", "cause_effect", "graph",
                      "analogy"},
    # Rule 9: spatial hierarchy. A row of peers is the thing being rejected.
    # `graph` too: a root with children IS a (shallow) hierarchy, and it is the
    # right shape whenever the children are DISTINCT NAMED THINGS rather than
    # nested levels — "the OS depends on the scheduler and the driver" is a graph,
    # "level 1 contains level 2 contains level 3" is `hierarchy` itself.
    "hierarchy":     {"hierarchy", "split", "code", "graph"},
    # Rule 10: cause and effect both on screen, direction drawn.
    "cause_effect":  {"cause_effect", "flow", "compare", "code"},
    # `state` earns a place here for the STILL case: a container with its slots and
    # its index, nothing moving, is a picture of how the thing is arranged.
    #
    # `flow` earns its place for the same reason as `state`: some structures ARE a
    # chain, and a chain's static arrangement — link, link, link — is honestly
    # drawn top-to-bottom with connectors, which is what `flow` does whether or
    # not anything is depicted as moving between beats. Found on a real short: the
    # strategist called the opening beat of a promise-chain explanation
    # "structure" (it introduces the shape, nothing has happened yet) while the
    # design step drew it as `flow` (a chain is inherently sequential) — both
    # readings are honest, and the mismatch was the allow-list being narrower than
    # the two correct answers it was choosing between.
    #
    # `graph` for the same reason again: one root with several named parts IS a
    # structure — "the kernel is made of the scheduler, the driver and the
    # filesystem" is one thing and what it is composed of, not a process.
    #
    # `analogy` earns its place here MOST NATURALLY of the three rows it is in:
    # analogy_technical is a Panel — a still stack of named boxes, no motion,
    # no arriving or leaving slot — so a beat naming a container's STRUCTURE
    # ("a stack holds items on top of each other") is exactly what this
    # template draws honestly, without borrowing a claim of movement it cannot
    # show. See skills/strategy.py rule 13.
    "structure":     {"split", "bar", "table", "mapping", "code", "hierarchy",
                      "icons", "state", "flow", "graph", "analogy"},
    "effect":        {"preview", "code", "compare"},
    "quantity":      {"stat", "bar", "table"},
}


def check_frames_match_strategy(unit: ShortUnit) -> GraderResult:
    """
    A frame must be drawn in a shape that can carry the claim it was planned for.

    THE RULE THIS ENFORCES, AND WHY IT COULD NOT BE ENFORCED BEFORE. The reviewer's
    rules 6 to 10 all condition on the KIND of concept — animate a process, show a
    comparison's two states simultaneously, use spatial hierarchy for a hierarchy.
    Every one of them was unenforceable, not because it was hard to check but
    because nothing in the pipeline had ever decided which kind a beat was. The
    design step went from a sentence straight to a template name, so the
    relationship existed only as an unstated premise inside a choice.

    skills/strategy.py writes it down. Once it is written down, "this beat is a
    hierarchy and it was drawn as a row of equal boxes" is a set membership test.

    The single most valuable case is `comparison`. Rule 7 says show both states
    simultaneously, and the way that rule gets broken is not a bad drawing — it is
    a short that gives beat 2 the "before" and beat 3 the "after", each drawn
    perfectly. Every existing grader passes that: the frames differ, the templates
    vary, the labels are grounded. And the viewer never sees the two side by side,
    so they never see the difference, which was the entire point of the beat.

    Skipped silently for any frame with no strategy — units built before the
    strategist existed, and the eval harness, must still grade cleanly.
    """
    offenders = []
    checked = 0
    for ref, visual in unit.visuals.items():
        plan, frame = visual.strategy, visual.frame
        if plan is None or frame is None:
            continue
        allowed = _RELATIONSHIP_TEMPLATES.get(plan.relationship)
        if not allowed:
            continue
        checked += 1
        if frame.template not in allowed:
            offenders.append(
                f"[{ref}] was planned as a '{plan.relationship}' claim and drawn as "
                f"'{frame.template}', which cannot show it — use one of "
                f"{', '.join(sorted(allowed))}")

    if not checked:
        return GraderResult("frames_match_strategy", True, "no strategy to check against")
    if offenders:
        return GraderResult("frames_match_strategy", False, "; ".join(offenders))
    return GraderResult("frames_match_strategy", True,
                        f"{checked} frame(s) drawn in a shape that carries their claim")


#: THE TIE-BREAKER `_RELATIONSHIP_TEMPLATES` CANNOT GIVE. `relationship` alone
#: allows both "state" and "flow" for a `process` claim, because both CAN show
#: something happening — but a stack (single_container) and a linked list
#: (linked_nodes) are both `process` and only one of them is a container with
#: contiguous slots. `physical_form` is the fact that tells them apart, and this
#: is the set membership test for it, the same shape as _RELATIONSHIP_TEMPLATES
#: one level down: within whatever `relationship` already allowed, which of
#: those shapes can actually carry THIS physical form.
#:
#: "code" is in every row for the same reason it is in every row above: the
#: material's own snippet is a legitimate, grounded picture of nearly any claim,
#: and rejecting it would push the designer off the most grounded frame
#: available.
_PHYSICAL_FORM_TEMPLATES = {
    "single_container": {"state", "code"},
    "linked_nodes":      {"flow", "graph", "code"},
    "nested_levels":     {"hierarchy", "code"},
    "flat_parts":        {"graph", "split", "bar", "table", "code"},
    "two_sides":         {"compare", "state", "graph", "code"},
    "single_object":      {"state", "cause_effect", "preview", "stat", "icons",
                           "analogy", "code"},
}


def check_physical_form_matches_template(unit: ShortUnit) -> GraderResult:
    """
    A frame must be drawn in the shape its own PHYSICAL FORM actually has.

    THE GAP THIS CLOSES. check_frames_match_strategy enforces `relationship` —
    the KIND of claim — and stops there, because relationship alone allows both
    "state" and "flow" for a `process` claim: both templates CAN show something
    happening, so neither is a relationship violation. But a stack filling up
    and a linked list growing are both `process`, and drawing a linked list as
    "state" (slots inside one bordered container) claims something false about
    it — that it is one contiguous thing, which a linked list specifically is
    not. That distinction lived entirely in visuals.py's prose before
    `physical_form` existed, with nothing downstream able to tell whether the
    design step had actually followed it.

    Skipped silently, exactly like check_frames_match_strategy, for any frame
    with no strategy or whose physical_form is "not_applicable" (the default) —
    units built before this field existed, or a beat whose claim genuinely
    is not shaped like any of the physical forms, must still grade cleanly.
    """
    offenders = []
    checked = 0
    for ref, visual in unit.visuals.items():
        plan, frame = visual.strategy, visual.frame
        if plan is None or frame is None:
            continue
        form = getattr(plan, "physical_form", "not_applicable")
        if form == "not_applicable":
            continue
        allowed = _PHYSICAL_FORM_TEMPLATES.get(form)
        if not allowed:
            continue
        checked += 1
        if frame.template not in allowed:
            offenders.append(
                f"[{ref}] has physical_form '{form}' and was drawn as "
                f"'{frame.template}', which cannot show it — use one of "
                f"{', '.join(sorted(allowed))}")

    if not checked:
        return GraderResult("physical_form_matches_template", True,
                            "no physical_form to check against")
    if offenders:
        return GraderResult("physical_form_matches_template", False, "; ".join(offenders))
    return GraderResult("physical_form_matches_template", True,
                        f"{checked} frame(s) drawn in the shape their physical form requires")


def _label_matches(anchor: str, candidate: str) -> bool:
    """Loose match between two short labels — same call, same response, so a
    real match differs at most by capitalisation, an article, or a trailing
    word, never by vocabulary. Stem-overlap rather than exact equality for
    exactly that tolerance, and nothing looser: one side's stems must be a
    full subset of the other's, not merely intersecting.
    """
    a, b = set(_stems(anchor)), set(_stems(candidate))
    if not a or not b:
        return False
    return a <= b or b <= a


def check_anchor_matches_structure(unit: ShortUnit) -> GraderResult:
    """
    A claimed PRIMARY position must be where the structure actually put it.

    THE GAP THIS CLOSES, AND WHY NOTHING BEFORE IT COULD. layout.py's
    positioning is deterministic — levels[0] always renders at the top,
    steps[0] always renders first, the slot at store.pointer_at always
    renders wherever the pointer points — but that is a promise about the
    RENDERER, not about the DATA handed to it. A hierarchy frame with
    `levels` written [child, parent] instead of [parent, child] renders
    perfectly correctly BY THE RENDERER'S OWN RULES and wrongly for the
    concept: the child ends up on top, drawn exactly as confidently as a
    correct frame would be. Every existing structural grader passes it — two
    real levels, properly nested, one clearly on top. None of them can tell
    WHICH one belongs there, because nothing before `anchor_label` said what
    the intended answer was.

    This is the one check that reads that stated answer and confirms the
    frame agrees with it:

      hierarchy   anchor_label must match levels[0].label — the parent
                  actually rendered on top.
      flow        anchor_label must match steps[0].label — the flow actually
                  starts where it was meant to.
      state       anchor_label must match the label AT store.slots[pointer_at]
                  — the pointer actually lands on the item it was meant to
                  indicate, not merely on some valid slot.

    ANCHOR_LABEL IS REQUIRED, NOT OPTIONAL, ON AN ELIGIBLE FRAME — measured,
    not assumed. It shipped optional first, on the reasoning that most frames
    would offer one anyway; two real builds later, EVERY eligible frame in
    both — a stack's pointer confidently aimed at C, a linked list's flow
    confidently starting at head — came back with an empty anchor_label, and
    this check passed all of them as "nothing to check" while the exact
    defect it exists for (a confidently-wrong pointer, a reversed flow) was
    free to ship undetected. An optional field the model has no reason to
    reach for is a field that does not exist in practice. So a frame is
    "eligible" when there IS a primary position to name — hierarchy with 2+
    levels, flow with 2+ steps, or state with pointer_at resolving to a
    slot that actually holds something — and an eligible frame that leaves
    anchor_label blank fails this check exactly as if it had named the wrong
    label, because from here the two are indistinguishable in effect: a
    claim nobody can verify.

    Skipped silently — same contract as every other strategy-shaped check in
    this file — for a frame with no frame, an ineligible frame (a single
    level, a single step, no resolvable pointer), or a template this check
    does not cover.
    """
    offenders = []
    checked = 0
    for ref, visual in unit.visuals.items():
        frame = visual.frame
        if frame is None:
            continue
        anchor = (getattr(frame, "anchor_label", "") or "").strip()

        if frame.template == "hierarchy":
            levels = frame.levels or []
            if len(levels) < 2:
                continue
            checked += 1
            if not anchor:
                offenders.append(
                    f"[{ref}] has {len(levels)} levels and no anchor_label — name "
                    f"which one is the parent (must render on top, levels[0]) so "
                    f"the order can be checked")
            elif not _label_matches(anchor, levels[0].label):
                offenders.append(
                    f"[{ref}] claims '{anchor}' as the parent (must render on top, "
                    f"levels[0]), but levels[0] is '{levels[0].label}' — the levels "
                    f"list has the parent and child in the wrong order")

        elif frame.template == "flow":
            steps = frame.steps or []
            if len(steps) < 2:
                continue
            checked += 1
            if not anchor:
                offenders.append(
                    f"[{ref}] has {len(steps)} steps and no anchor_label — name "
                    f"which one is the source (must render first, steps[0]) so "
                    f"the direction can be checked")
            elif not _label_matches(anchor, steps[0].label):
                offenders.append(
                    f"[{ref}] claims '{anchor}' as the source (must render first, "
                    f"steps[0]), but steps[0] is '{steps[0].label}' — the flow's "
                    f"direction is reversed")

        elif frame.template == "state":
            store = frame.store
            if store is None or not store.slots:
                continue
            idx = store.pointer_at
            if idx is None or not (0 <= idx < len(store.slots)):
                # A pointer past the end or on an empty container is a real,
                # meaningful state (see Store.pointer_at's own docstring), and
                # there is no slot for anchor_label to name — not eligible.
                continue
            actual = store.slots[idx].label
            if not actual:
                # The pointer targets a real, in-range slot that is itself
                # empty (e.g. an index sitting one past the last pushed item)
                # — a valid state with nothing to name, not eligible.
                continue
            checked += 1
            if not anchor:
                offenders.append(
                    f"[{ref}] has pointer_at naming a filled slot ('{actual}') and "
                    f"no anchor_label — name what the pointer should be indicating "
                    f"so the target can be checked")
            elif not _label_matches(anchor, actual):
                offenders.append(
                    f"[{ref}] claims the pointer should indicate '{anchor}', but "
                    f"pointer_at names slot {idx}, which holds '{actual}' — the "
                    f"pointer is aimed at the wrong slot")

    if not checked:
        return GraderResult("anchor_matches_structure", True, "no eligible frame to check")
    if offenders:
        return GraderResult("anchor_matches_structure", False, "; ".join(offenders))
    return GraderResult("anchor_matches_structure", True,
                        f"{checked} frame(s) have their claimed anchor where the structure puts it")


#: Terms that make "code" a legitimate picture of a SPECIFIC beat: its own
#: must_see/concept is about the code's syntax, a keyword, a property, a
#: selector, a declaration — the thing on screen IS the code, not a stand-in for
#: some other relationship the material happened to include a snippet for.
#:
#: Deliberately generous (a real syntax-teaching beat should say one of these
#: words naturally) rather than an exhaustive allow-list — false negatives here
#: just mean check_code_not_overused stays silent, which is the safe failure
#: direction for a heuristic keyword match.
_CODE_OBJECTIVE_WORDS = (
    "syntax", "keyword", "property", "selector", "declaration", "statement",
    "attribute", "signature", "parameter", "operator", "written as", "line of code",
)


def check_code_not_overused(unit: ShortUnit) -> GraderResult:
    """
    The 'code' template is the material's own snippet, and _RELATIONSHIP_TEMPLATES
    allows it in almost every row for exactly that reason — see the comment above
    it. That is a deliberate, correct choice for the ONE beat whose claim really
    is the code. It is a defect the same choice makes easy to fall into for every
    OTHER beat too: a process, a comparison, a hierarchy all have a code snippet
    sitting right there in the section, and reaching for it every time is how a
    short about a mechanism ends up as four screenshots of the same file — visual
    variety, not visual thinking.

    What this catches: MORE THAN ONE frame in the same unit drawn as 'code', where
    NONE of them has a strategy whose must_see/concept says the beat is actually
    about the code itself (see _CODE_OBJECTIVE_WORDS). One code frame is never
    flagged — the single most grounded picture of a beat is not overuse. Two or
    more where AT LEAST ONE names a code-specific objective are not flagged either:
    a short with a "here is the property" beat and a separate "here is the value
    syntax" beat can legitimately want two. It is "the design step defaulted to
    code every time because it had no better idea" this exists to catch, and that
    reads as ALL of them lacking a reason, not some of them.

    Skipped, not failed, when there is no strategy to read at all (a unit built
    before the strategist existed, or the eval harness) — the same rule
    check_frames_match_strategy uses just above.
    """
    code_refs = [ref for ref, v in unit.visuals.items()
                 if v.frame is not None and v.frame.template == "code"]
    if len(code_refs) <= 1:
        return GraderResult("code_not_overused", True,
                            f"{len(code_refs)} code frame(s) — not overused")

    justified = []
    for ref in code_refs:
        plan = unit.visuals[ref].strategy
        if plan is None:
            continue
        text = f"{plan.concept} {plan.must_see}".lower()
        if any(word in text for word in _CODE_OBJECTIVE_WORDS):
            justified.append(ref)

    if not any(unit.visuals[ref].strategy is not None for ref in code_refs):
        return GraderResult("code_not_overused", True,
                            "no strategy to check against", {"skipped": True})

    if not justified:
        return GraderResult("code_not_overused", False,
            f"{len(code_refs)} frames ({', '.join(code_refs)}) all use the 'code' "
            f"template and none of their strategies names code syntax, a keyword, a "
            f"property or a selector as the thing to see — code is being used as the "
            f"default picture rather than drawn for the beats whose claim actually is "
            f"the code. Draw each beat's own relationship instead (see "
            f"_RELATIONSHIP_TEMPLATES for what else can carry it).",
            {"code_refs": code_refs})
    return GraderResult("code_not_overused", True,
        f"{len(code_refs)} code frame(s), {len(justified)} justified by their own strategy")


def _frame_role_collections(frame) -> list[tuple[str, list[str]]]:
    """
    Every role-bearing group in a Frame, named — a row, a column, one card's items.

    Pulled out of check_one_hero_per_frame so check_ends_on_answer can ask "does
    this frame have a hero ANYWHERE" without re-deriving, template shape by
    template shape, the same list check_one_hero_per_frame already had to learn
    (a Frame's hero can live in cells, glyphs, panels, store.slots, or graph
    nodes, and a second grader guessing at that list independently is exactly
    how the two quietly drift apart the next time a template gains a field).
    """
    collections: list[tuple[str, list[str]]] = [
        ("cells", [c.role for c in frame.cells]),
        ("left column", [c.role for c in frame.left]),
        ("right column", [c.role for c in frame.right]),
        ("parts", [c.role for c in frame.parts]),
        ("steps", [c.role for c in frame.steps]),
        ("code lines", [c.role for c in frame.code_lines]),
        ("samples", [c.role for c in frame.samples]),
        ("glyphs", [c.role for c in frame.glyphs]),
        ("levels", [c.role for c in frame.levels]),
        ("rows", [r.role for r in frame.rows]),
        ("panels", [p.role for p in frame.panels]),
        ("cause/effect", [c.role for c in (frame.cause, frame.effect)
                          if c is not None]),
        # OCCUPIED slots only. An empty slot carries "plain" by default and is
        # not a candidate for the accent, so counting them would make a store
        # with two items and four empty places look like it has plenty of
        # unaccented elements when in fact both of its items are lit.
        ("slots", [sl.role for sl in (frame.store.slots if frame.store else ())
                   if sl.label]),
        # Root and branches together, one group — a graph makes ONE claim
        # about how its parts relate, and that claim can legitimately need
        # two lit ends (the root AND the one branch its beat is about), the
        # same reasoning check_one_hero_per_frame already applies to a
        # mapping's two columns.
        ("graph nodes",
         ([frame.graph.root.role] if frame.graph else [])
         + [br.node.role for br in (frame.graph.branches if frame.graph else ())]),
    ]
    for i, panel in enumerate(frame.panels, 1):
        collections.append((f"panel {i} items", [c.role for c in panel.items]))
    # analogy's right-hand Panel — the LEFT side is a photo and carries no role
    # at all, so it is never a candidate for "no element marked hero" the way
    # a compare panel's items are.
    if frame.analogy_technical is not None:
        collections.append(("analogy panel items",
                            [c.role for c in frame.analogy_technical.items]))
    return collections


def check_one_hero_per_frame(unit: ShortUnit) -> GraderResult:
    """
    Every frame needs a focus, and no single row of a frame may have two.

    "A composition of equal parts has no focus" is stated in the brief and was
    never checked. Both ways of breaking it are bad in the same way: a frame with
    the accent on three things asks the viewer to look at three things at once,
    which is the same as asking them to look at nothing, and a frame with no accent
    leaves them scanning. Measured across the 38 units in output/, a quarter of all
    frames had no hero at all.

    ONE HERO PER COLLECTION, NOT ONE PER FRAME, and the difference is a real design
    the first version of this grader was wrong about. A `mapping` frame draws two
    columns and highlights a CORRESPONDENCE across them:

        left:  [Page 0 quiet, Page 1 HERO, Page 2 quiet]
        right: [Frame 5 quiet, Frame 9 HERO, Frame 2 quiet]

    That is two hero elements and exactly one focus — "page 1 lives in frame 9" is
    a single claim that needs both of its ends lit, and dimming either one draws an
    arrow from a highlighted box to an unremarkable one. The same is true of a
    `compare` frame accenting the recommended card and the one item inside it that
    makes the case.

    So the rule is applied WITHIN each list, where it is unambiguous: two heroes in
    one row of cells really are two accents competing, because there is no
    relationship between them for the pair to express.
    """
    offenders = []
    for ref, visual in unit.visuals.items():
        frame = visual.frame
        if frame is None:
            continue

        # Each entry is one collection that is laid out as a unit — a row, a
        # column, the items inside one card. Heroes are counted inside each.
        populated = [(n, roles) for n, roles in _frame_role_collections(frame) if roles]
        # `stat` and `takeaway` draw one thing and hard-code it as the focus, so
        # they carry no roles at all and cannot be judged this way.
        if not populated:
            continue

        # ALL of a group being hero, not merely SEVERAL. Measured across output/,
        # "several" caught a pattern that is right far more often than it is wrong:
        #
        #     cells: [P1 quiet, P1 quiet, Free HERO, P2 quiet, Free HERO, Free HERO]
        #
        # Three heroes and one focus — "the free space is scattered" is a claim
        # about a CATEGORY of cells, and lighting only one of the three gaps would
        # state it falsely. The accent is doing exactly its job.
        #
        # What is never right is a group where EVERY element is the hero:
        #
        #     steps: [1. Access Page Table HERO, 2. Access Data HERO]
        #
        # An accent that is universal is not an accent. There is no contrast left
        # for the eye to find, so the frame reads as uniformly loud, and that is
        # the same defect as having no hero at all wearing brighter paint.
        # Two or more elements, because a one-element group is trivially "all".
        drowned = [n for n, roles in populated
                   if len(roles) > 1 and all(r == "hero" for r in roles)]
        if drowned:
            offenders.append(
                f"[{ref}] marks EVERY element of its {', '.join(drowned)} as hero — an "
                f"accent on everything is an accent on nothing. Light the one element "
                f"this beat is about and let the rest carry 'plain'.")
            continue
        if not any("hero" in roles for _, roles in populated):
            offenders.append(
                f"[{ref}] ({frame.template}) has no element marked hero — nothing is "
                f"emphasised, so the viewer has nowhere to look first. Mark the one "
                f"thing this beat is about.")

    if offenders:
        return GraderResult("one_hero_per_frame", False, "; ".join(offenders))
    return GraderResult("one_hero_per_frame", True, "every frame has a single focus")


def check_ends_on_answer(unit: ShortUnit) -> GraderResult:
    """
    The short's LAST frame must visually land on the answer, not trail off.

    schema.Script.starts_with_interviewer already guarantees the OPEN is right —
    beat 0 is always the question. Nothing guaranteed the CLOSE was: a short
    could walk through every step of a mechanism and end on a frame that is
    still describing the process rather than emphasising the resolved answer,
    which reads as the video stopping mid-thought rather than concluding.

    Reuses _frame_role_collections rather than re-deriving "where can a hero
    live on this template" a third time — check_one_hero_per_frame already
    had to learn that once, and a second, independently-drifting copy of the
    same enumeration is how a new template (a Store, a Graph) quietly becomes
    invisible to one grader and not the other.

    `stat` and `takeaway` are exempted for the same reason
    check_one_hero_per_frame skips them: both hard-code their own emphasis in
    the renderer (layout._stat and layout._takeaway both emit a hard-coded
    data-role="focus") and carry no Cell/Glyph/Slot roles at all, so "no
    element marked hero" is true of every takeaway frame ever built and would
    fail the very template whose entire job is landing the last line — the
    fixture for this failure mode would be indistinguishable from the fixture
    for the short thing working exactly as designed.
    """
    last_beat = unit.beats[-1]
    visual = unit.visuals.get(last_beat.visual_ref)
    frame = visual.frame if visual else None
    if frame is None:
        return GraderResult("ends_on_answer", True,
            f"[{last_beat.visual_ref}] has no rendered frame to check (e.g. a raw image)")

    populated = [(n, roles) for n, roles in _frame_role_collections(frame) if roles]
    if not populated:
        return GraderResult("ends_on_answer", True,
            f"[{last_beat.visual_ref}] ({frame.template}) hard-codes its own focus")

    if not any("hero" in roles for _, roles in populated):
        return GraderResult("ends_on_answer", False,
            f"short ends on [{last_beat.visual_ref}] ({frame.template}) with no element "
            f"marked hero — the short trails off on a neutral frame instead of landing "
            f"on the answer")
    return GraderResult("ends_on_answer", True,
                        "the final frame visually lands on the answer")


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


#: Templates that never move: no arriving/leaving slot, no travelling payload, no
#: cause-to-effect arrow. Held for every beat of a short, this is the complaint in
#: its own words — "boxes, comparisons, two labels, an arrow" — measured, not
#: guessed: tallied across all 262 frames in 64 real units, icons+compare+bar
#: alone were 48.5% of every frame this pipeline had ever drawn.
_STATIC_TEMPLATES = {"icons", "compare", "bar", "table", "split", "mapping"}

#: Relationships that genuinely have movement or direction — rules 6, 8 and 10 of
#: EDUCATIONAL_VISUAL_RULES. Deliberately NOT "comparison", "structure" or
#: "effect": those are legitimately still, and commit 909bab9 already chose to
#: grade a picture's CONTENT over its TEMPLATE for exactly that reason — a short
#: that holds one scaffold because its concept is a one-time comparison is the
#: right shape, not the defect this grader exists to catch.
_MOTION_RELATIONSHIPS = {"process", "data_movement", "cause_effect"}


def check_motion_concept_not_static(unit: ShortUnit) -> GraderResult:
    """
    A short the strategist itself called a process, a data movement or a cause
    and effect must show at least one of those beats HAPPENING — not hold one
    static template for its entire length.

    THE GAP 909bab9 LEFT OPEN, ON PURPOSE, AND STILL OPEN. That commit is right
    that "did the picture's CONTENT change" is the question for a recoloured
    repost, and check_frames_develop / check_frames_progress both grade exactly
    that, correctly. Neither one asks whether the TEMPLATE itself ever left the
    static shelf: `icons`/`compare`/`bar`/`table`/`split`/`mapping` can all
    develop their CONTENT beat to beat — a fifth pictogram arrives, a losing
    column dims — and still never draw a container changing, a payload
    travelling, or a cause reaching its effect. That passes every existing
    grader and still reads, to a human watching it, as one static shape holding
    still for the length of the video.

    CONFIRMED REAL, not hypothetical: output/sync_vs_async.json is `compare`x3
    end to end for a short about a SEQUENCE of events, and output/
    kernel_dependencies.json is `graph`x5 for a short with an actual dependency
    CHAIN in it — neither one ever shows anything moving, and both hold one
    template throughout.

    NOT A SECOND check_frames_progress. That grader owns "does the picture
    change" and this must not re-fight that battle — a short can pass this and
    still be repetitive, and vice versa. This asks a narrower question: were
    ALL of its frames static AND did the strategist's own plan call at least one
    beat a kind of claim that needs motion to be honest. A short the strategist
    called structure/comparison/effect throughout and drew on one static
    scaffold is exactly what 909bab9 protects, and this grader passes it —
    see the false-positive fixture.

    Skipped, not failed, when there is nothing to compare: no rendered frames,
    or no strategy recorded for any beat (a unit built or loaded before the
    strategist existed).
    """
    refs = list(dict.fromkeys(b.visual_ref for b in unit.beats))
    templates: list[str] = []
    relationships: list[str] = []
    for ref in refs:
        visual = unit.visuals.get(ref)
        if visual is None or visual.frame is None:
            continue
        templates.append(visual.frame.template)
        if visual.strategy is not None:
            relationships.append(visual.strategy.relationship)

    if not templates:
        return GraderResult("motion_concept_not_static", True, "no rendered frames to check")

    if not all(t in _STATIC_TEMPLATES for t in templates):
        return GraderResult("motion_concept_not_static", True,
            "at least one frame is not held to a static, non-motion template")

    moving = sorted({r for r in relationships if r in _MOTION_RELATIONSHIPS})
    if not moving:
        return GraderResult("motion_concept_not_static", True,
            "every frame is static, but the strategist never called this concept "
            "a process, a data movement or a cause and effect — a genuinely still "
            "concept held on one scaffold is not a defect")

    return GraderResult("motion_concept_not_static", False,
        f"every one of {len(templates)} frame(s) is drawn in a static template "
        f"({', '.join(sorted(set(templates)))}), but the strategist called "
        f"{len(moving)} of its beat(s) {', '.join(moving)} — the concept has "
        f"movement or direction on the page and the short showed none of it. Use "
        f"`state` for a container changing, `flow`/`cause_effect` for a sequence "
        f"or a trigger, or `analogy` for the beat that introduces the container.",
        {"templates": templates, "relationships": relationships})


#: The specific family check_motion_concept_not_static's own docstring names as
#: "static" in the no-movement sense, minus "icons" — a pictogram is a drawn
#: picture of a real thing, not text sitting in a rounded rectangle, and does
#: not read as the "sticky note" vocabulary this check is about. What is left
#: — bar, table, split, mapping, compare — is exactly the shape family that
#: looks identical regardless of the concept behind it: a row or a grid of
#: rounded boxes, holding words.
_BOX_TEMPLATES = {"bar", "table", "split", "mapping", "compare"}

#: Below this share of a reel's frames, the box family is a legitimate choice
#: for some of the beats and not the whole reel's personality.
_MAX_BOX_SHARE = 0.5


def check_generic_boxes_not_overused(unit: ShortUnit) -> GraderResult:
    """
    A reel should not read as the same rounded-box template wearing different
    words, when the beats behind it are not all making the same kind of claim.

    THE COMPLAINT THIS EXISTS FOR: a reel that is individually correct on every
    structural grader — right template family for each relationship
    (check_frames_match_strategy), right physical form (check_physical_form_
    matches_template), each frame distinct from its neighbours (check_frames_
    develop) — and still reads as generic and juvenile, because MOST of its
    frames are `bar`/`table`/`split`/`mapping`/`compare`: rows and grids of
    rounded rectangles holding text, the visual vocabulary of a presentation
    slide rather than a technical explainer. None of the existing graders ask
    this question, because each of them grades ONE frame or ONE transition
    against ONE rule, never the reel's overall visual personality.

    NOT A DUPLICATE OF check_motion_concept_not_static. That check asks whether
    a reel calling itself a process ever shows movement — narrow, and about
    correctness. This asks whether the reel LOOKS like it reached for the
    nearest box every time, which is a maturity question and applies whether
    or not any beat needed motion. A reel that is genuinely, entirely a set of
    comparisons is not this defect (see the gate below); a reel with a
    hierarchy, a container and a process all flattened into `table` because
    that was easiest is.

    THE GATE THAT KEEPS THIS FROM FIRING ON A GENUINE ALL-COMPARISON REEL: it
    only fails when the beats drawn in the box family are not all the SAME
    relationship. A short whose entire question is "how do these three
    approaches compare" and draws `compare` five times in a row is one
    consistent, correct choice, not five generic ones — see the false-positive
    fixture. What this catches is DIFFERENT concepts — a hierarchy, a
    container, a plain structure — all landing on the box family anyway.

    Skipped when there is no strategy recorded for any beat (a unit built
    before the strategist existed) — there is no relationship to check
    diversity against, so nothing here is asserted.
    """
    refs = list(dict.fromkeys(b.visual_ref for b in unit.beats))
    templates: list[str] = []
    box_relationships: list[str] = []
    has_strategy = False
    for ref in refs:
        visual = unit.visuals.get(ref)
        if visual is None or visual.frame is None:
            continue
        templates.append(visual.frame.template)
        if visual.strategy is not None:
            has_strategy = True
            if visual.frame.template in _BOX_TEMPLATES:
                box_relationships.append(visual.strategy.relationship)

    if not templates or not has_strategy:
        return GraderResult("generic_boxes_not_overused", True,
                            "no strategy to check diversity against")

    box_count = sum(1 for t in templates if t in _BOX_TEMPLATES)
    if box_count / len(templates) <= _MAX_BOX_SHARE:
        return GraderResult("generic_boxes_not_overused", True,
            f"{box_count} of {len(templates)} frame(s) use a generic box template "
            f"— not the majority of the reel")

    if len(set(box_relationships)) <= 1:
        return GraderResult("generic_boxes_not_overused", True,
            f"{box_count} of {len(templates)} frame(s) use a generic box template, "
            f"but they are all the same kind of claim ({box_relationships[0]!r}) "
            f"— a consistent choice, not a default")

    return GraderResult("generic_boxes_not_overused", False,
        f"{box_count} of {len(templates)} frame(s) ({', '.join(sorted(set(t for t in templates if t in _BOX_TEMPLATES)))}) "
        f"are drawn in a generic rounded-box template, covering "
        f"{len(set(box_relationships))} different kinds of claim "
        f"({', '.join(sorted(set(box_relationships)))}) — the reel reads as one "
        f"box template wearing different words rather than a picture chosen for "
        f"each concept. Give at least the beats whose relationship is process, "
        f"data_movement, cause_effect or hierarchy their own shape — see the "
        f"template mapping in visuals.py's SPEC_SYSTEM.",
        {"box_count": box_count, "total": len(templates),
         "relationships": sorted(set(box_relationships))})


# ------------------------------------------------------- the teaching sequence
#
# WHY THIS IS GRADED AT ALL. The teaching sequence is the one part of the content
# understanding that the script brief is told to FOLLOW rather than merely consult
# — it is offered as the spine for the beats. That makes a bad one worse than none:
# a sequence that wandered onto a neighbouring topic, or that was written as a
# generic hook/problem/takeaway shape with the section's nouns dropped in, steers
# the script wrong with the authority of a plan.
#
# Everything here is deterministic and free, and it runs on the reply to the ONE
# understanding call — nothing is re-asked. A sequence that fails is dropped and
# the rest of the reading is kept; see skills/understanding.understand().

#: A sequence longer than this is not "the smallest sequence a beginner needs".
#:
#: DERIVED FROM MAX_ANSWERS, NOT RESTATED — and it was restated, which is the bug
#: this fixes. The rationale was always relational: the script has a fixed number
#: of answer beats, so a sequence longer than that plans an explanation the short
#: cannot deliver, and the beats would have to drop steps silently, by whichever
#: ones the model found hardest to say. One step over the beat count is the useful
#: slack, because a step can be a setup that shares a beat with the one after it.
#:
#: Written as a literal 4, that reasoning was true only while MAX_ANSWERS was 3.
#: When the window went to 35-50s and MAX_ANSWERS became 5, the literal silently
#: became a cap BELOW what the script can now deliver — it would have rejected a
#: five-step plan that four or five beats carry comfortably, and the failure would
#: have looked like a bad reading rather than a stale constant.
MAX_TEACHING_STEPS = MAX_ANSWERS + 1

#: How much of a step's `concept` must be vocabulary the rest of the understanding
#: already uses. Stems, not words, and prefix-matched by _grounded, so "translate"
#: covers "translation" — this is asking "is this the same subject", not "is this
#: the same phrasing". Below 0.5 a concept is mostly words that appear nowhere else
#: in the reading, which is what a step borrowed from general knowledge looks like.
MIN_CONCEPT_OVERLAP = 0.5


#: A GFM table's OWN separator row — dashes and colons between pipes, nothing
#: else — matched by content rather than position, so it is found the same way
#: whether the table has two columns or six, spaces around the dashes or not.
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _table_rows(text: str) -> tuple[list[str], str]:
    """
    Pull every markdown table out of `text`, returning its DATA rows as candidate
    citable spans — never the header, never the `---` separator — plus the text
    with those table lines removed, so the paragraph splitter below never has to
    look at one.

    WHY THIS EXISTS. A table is one of the most natural shapes for exactly the
    content this checker exists to protect — a step trace, a before/after
    comparison, a lookup of cases to outcomes — and before this, one had no
    reliable representation here at all. Fed through the prose path instead: a
    table has no sentence-ending punctuation, so a header and its separator glue
    into one line that _is_whole_sentence always refuses; and the separator row's
    own dashes (`---`) happen to satisfy _is_code_quote's "looks like code"
    pattern, so a four-row reduce() trace registered as ONE misleading span —
    not because any row said anything, but because a run of dashes looks like
    the `--` operator. A table walking through four real steps read as one fact,
    or as the WRONG fact (a separator row, mistaken for content).

    A table is recognised by its separator, not its own syntax alone — a line
    that starts a table has a `|`, and the line right after it matches
    _TABLE_SEPARATOR — so a table missing conventional leading/trailing pipes is
    still found, and a stray `|` in ordinary prose (which never has a dashes-only
    line right after it) is not mistaken for one.
    """
    lines = text.splitlines()
    keep = [True] * len(lines)
    rows: list[str] = []
    i = 0
    while i < len(lines) - 1:
        if "|" in lines[i] and _TABLE_SEPARATOR.match(lines[i + 1]):
            keep[i] = keep[i + 1] = False          # the header, then its separator
            j = i + 2
            while j < len(lines) and "|" in lines[j] and not _TABLE_SEPARATOR.match(lines[j]):
                keep[j] = False
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                content = _flatten(" ".join(cells))
                # At least two real cells, or a lone `| note |` row is a stray pipe
                # in prose rather than tabular data, and enough flattened text to
                # clear the same bar _is_code_quote holds a bare quote to.
                if sum(1 for c in cells if c) >= 2 and len(content) >= MIN_QUOTE_CHARS:
                    rows.append(lines[j].strip())
                j += 1
            i = j
        else:
            i += 1
    remaining = "\n".join(line for line, kept in zip(lines, keep) if kept)
    return rows, remaining


def _citable_spans(section_text: str) -> list[str]:
    """
    Distinct verbatim spans of a section that could honestly support ONE beat's
    citation — counted the same way check_source_quotes decides a citation is real
    enough to try, but computed from the raw section text, with no model call.

    THE GAP THIS CLOSES. check_plan_depth asks whether the READING found enough
    conceptual signal (a teaching sequence, an example, a misconception), and nothing
    asks whether the SECTION ITSELF has enough actual sentences to cite that many
    times. The two can disagree: understand() read a 30-word section — two bullet
    points and a code fence, "HTML elements like `<img />` are called void elements
    because they don't require an end tag" is the only real sentence in it — as a
    3-step teaching sequence plus a required example, which is TRUE as a reading of
    the concept and says nothing about whether the section has four distinct
    sentences to cite. It does not: it has one sentence and one code line, and
    check_source_quotes needs `MIN_ANSWERS - 1` = 3 distinct citations. The script
    that came back cited that one sentence in two beats and invented prose to fill
    the rest, and grounding, source_quotes, reaches_objective and learning_outcome
    all failed on the same real section — three paid script attempts and a paid
    understanding call spent on material that could never have satisfied the
    citation rule, which this checks for a fraction of a cent and zero model calls.

    Fenced code blocks are pulled out and split into lines first, because a code
    citation is exempt from the word floor (see check_source_quotes / _is_code_quote)
    and a section's most citable content is often its code rather than its prose —
    exactly the case here, where the fence is the second span this finds. Markdown
    tables are pulled out the same way, for the same reason — see _table_rows.
    """
    fenced = re.findall(r"```.*?```", section_text, flags=re.S)
    prose = re.sub(r"```.*?```", " ", section_text, flags=re.S)
    table_rows, prose = _table_rows(prose)

    # Split on blank lines too, not just sentence punctuation: bullet-note material
    # like this section separates its points with a blank line rather than a full
    # stop ("* **HTML Image Element Syntax**:" has no terminal punctuation at all),
    # and without this a heading-style bullet ran on into the next one as a single
    # messy "sentence" in the diagnostic message, even though the span COUNT it
    # produced was already correct.
    paragraphs = re.split(r"\n\s*\n", prose)
    sentences = [s for para in paragraphs
                for s in re.split(r"(?<=[.!?])\s+", " ".join(para.split()))
                if s.strip()]
    # A COMPLETE SENTENCE OR A LINE OF CODE, NOT ANY FOUR-WORD FRAGMENT. This is
    # deliberately STRICTER than check_source_quotes' own letter, which accepts any
    # >=MIN_QUOTE_WORDS verbatim substring whether or not it ends in punctuation —
    # verified directly: it accepts "* **HTML Image Element Syntax**:" as a valid
    # citation, because it is four real words copied from the section. That is
    # correct as a citation-verbatim check and wrong as a measure of whether the
    # section has something to SAY: a heading fragment supports no claim, and no
    # well-written beat would rest on one. Requiring a real sentence or a code line
    # is a closer proxy for "can this be honestly cited" than the grader's own
    # floor is, even though it means this and check_source_quotes can disagree at
    # the margin — better to warn early on a borderline section than to pass one
    # that only clears the letter of the rule.
    spans = [s for s in sentences if _is_whole_sentence(s) or _is_code_quote(s)]

    for block in fenced:
        for line in block.strip("`").splitlines():
            line = line.strip()
            if line and line.lower() not in ("html", "css", "js", "python",
                                             "javascript", "json", "bash", "sh"):
                if _is_code_quote(line):
                    spans.append(line)

    spans.extend(table_rows)

    # Deduplicated by flattened text: the same sentence quoted by two different
    # spans (a heading repeating a body sentence, say) is one piece of evidence,
    # not two, and counting it twice would understate how thin the section is.
    seen, out = set(), []
    for span in spans:
        key = _flatten(span)
        if key and key not in seen:
            seen.add(key)
            out.append(span)
    return out


def check_section_richness(section_text: str, min_answers: int = MIN_ANSWERS) -> GraderResult:
    """
    Before anything is written or even read: does this section have enough
    DISTINCT SENTENCES to cite, whatever it turns out to teach?

    Free and instant — string splitting on the raw section text, no model call —
    which is the point: it is meant to run before understanding_for and before
    write_script, so a section that cannot possibly satisfy check_source_quotes'
    distinctness rule is never handed to either. See _citable_spans for the real
    example that motivated this.

    Deliberately NOT a substitute for check_plan_depth. That one asks whether the
    CONCEPT is rich enough to fill 4-5 beats without restating; this asks whether
    the TEXT has enough sentences to cite that many times honestly. A section can
    pass one and fail the other, and both are real ways a script goes wrong.
    """
    needed = max(1, min_answers - 1)
    spans = _citable_spans(section_text)
    if len(spans) < needed:
        shown = "; ".join(f'{s[:60]!r}' for s in spans[:3]) or "none"
        return GraderResult("section_richness", False,
            f"only {len(spans)} distinct citable sentence(s) in this section "
            f"({shown}), need {needed} for a {min_answers}-beat script. Every beat "
            f"needs its own supporting sentence or this becomes one idea stretched "
            f"across several beats — merge this section with a neighbouring one, or "
            f"add explanatory prose to it, before generating a short from it.",
            {"spans": len(spans), "needed": needed})
    return GraderResult("section_richness", True,
        f"{len(spans)} distinct citable sentence(s), needs {needed}",
        {"spans": len(spans), "needed": needed})


def check_teaching_sequence(understanding, section_text: str | None = None) -> GraderResult:
    """
    Is this teaching sequence usable as the spine of a short?

    Four questions, in the order they are worth asking:

      1. IS THERE ONE, and is it short enough to be a plan for the script's own
         beat budget (MAX_TEACHING_STEPS, derived from MAX_ANSWERS) rather than a
         syllabus.
      2. IS EVERY STEP COMPLETE. The schema already rejects a blank field, so this
         catches what a plain string cannot: a `purpose` that repeats the concept
         verbatim, which is the field going through the motions.
      3. IS IT ON THE OBJECTIVE. The sequence exists to reach core_idea. A sequence
         no step of which touches the stated idea is a plan for a different short.
      4. ARE ITS CONCEPTS THE SECTION'S. Checked against the understanding's own
         vocabulary — core_idea, key_points, concrete_examples, source_evidence —
         and against the section itself when the caller has it. This is the rule
         that stops the sequence becoming a second source of claims: a step naming
         something nothing else in the reading mentions was not read off the page.

    Never raises, like every grader here — a malformed understanding returns
    passed=False with a reason rather than taking down the step that called it.
    """
    steps = list(getattr(understanding, "teaching_sequence", None) or [])

    if not steps:
        return GraderResult("teaching_sequence", False,
            "no teaching sequence — the reading says what the section contains but "
            "not the order a beginner has to meet it in", {"steps": 0})

    if len(steps) > MAX_TEACHING_STEPS:
        return GraderResult("teaching_sequence", False,
            f"{len(steps)} steps, over the {MAX_TEACHING_STEPS} allowed. A short is "
            f"2-3 answer beats, so this plans more than it can deliver — cut it to "
            f"the steps a beginner cannot do without.", {"steps": len(steps)})

    # 2. Complete, and not padded to look complete.
    incomplete = []
    for i, step in enumerate(steps, 1):
        concept = (getattr(step, "concept", "") or "").strip()
        purpose = (getattr(step, "purpose", "") or "").strip()
        goal = (getattr(step, "explanation_goal", "") or "").strip()
        missing = [n for n, v in (("concept", concept), ("purpose", purpose),
                                  ("explanation_goal", goal)) if not v]
        if missing:
            incomplete.append(f"step {i} is missing {', '.join(missing)}")
        elif purpose.lower() == concept.lower() or goal.lower() == concept.lower():
            incomplete.append(f"step {i} restates its concept instead of saying "
                              f"why the step is needed or what the learner ends up with")
    if incomplete:
        return GraderResult("teaching_sequence", False, "; ".join(incomplete),
                            {"steps": len(steps), "incomplete": incomplete})

    # 3 and 4 both compare stems, so build the reference vocabularies once.
    objective = set(_stems(getattr(understanding, "core_idea", "") or ""))
    own_text = " ".join([
        getattr(understanding, "core_idea", "") or "",
        " ".join(getattr(understanding, "key_points", None) or []),
        " ".join(getattr(understanding, "concrete_examples", None) or []),
        " ".join(getattr(understanding, "source_evidence", None) or []),
    ])
    vocabulary = set(_stems(own_text))
    if section_text:
        vocabulary |= set(_stems(section_text))

    # 3. On the objective. Asked of the SEQUENCE, not of each step: a step that
    #    introduces a prerequisite legitimately shares no words with the idea it
    #    builds toward — "page number and offset" does not mention translation.
    #    What would be wrong is a whole sequence that never arrives.
    if objective:
        reached = [s for s in steps
                   if any(_grounded(stem, objective)
                          for stem in _stems(f"{s.concept} {s.explanation_goal}"))]
        if not reached:
            return GraderResult("teaching_sequence", False,
                f"no step reaches the stated objective ({getattr(understanding, 'core_idea', '')[:80]!r}) "
                f"— the sequence plans a different explanation from the one this "
                f"section is for", {"steps": len(steps), "reached": 0})

    # 4. Built from the section's own concepts.
    if vocabulary:
        drifted = []
        for i, step in enumerate(steps, 1):
            stems = {s: w for s, w in _stems(step.concept).items() if len(s) > 3}
            if not stems:
                # No content words at all — "the next part", "step two".
                drifted.append(f"step {i} ({step.concept!r}) names no concept")
                continue
            unknown = sorted(stems[s] for s in stems if not _grounded(s, vocabulary))
            if 1 - (len(unknown) / len(stems)) < MIN_CONCEPT_OVERLAP:
                drifted.append(f"step {i} ({step.concept!r}) is not in the section's "
                               f"vocabulary: {unknown[:6]}")
        if drifted:
            return GraderResult("teaching_sequence", False, "; ".join(drifted),
                                {"steps": len(steps), "drifted": drifted})

    # NO LANDING CHECK HERE, AND IT WAS TRIED. Read this before adding one.
    #
    # A real run returned a four-step sequence whose last step was a detail, the
    # script followed it, and check_reaches_objective failed. The obvious fix was
    # to reject such a sequence here, so the plan could not steer the script into a
    # wall — and it made things WORSE, measurably, on the next run.
    #
    # Two reasons. The threshold is a cliff: the sequence that got quarantined
    # carried 19% of the objective in its final step against a 20% floor, which is
    # a coin-toss difference for a plan that was otherwise good. And quarantining
    # is the wrong lever anyway — dropping the sequence removes the SPINE, so the
    # script then has no plan at all and ends wherever its last sentence lands. The
    # failure it was supposed to prevent got more likely, not less.
    #
    # Landing the objective is the SCRIPT's job, and skills/script.py now says so
    # outright: the final beat must carry the idea, and follows_sequence explicitly
    # permits ending on the objective instead of on the final planned step. The
    # plan orders the explanation; the script decides where to stop.
    return GraderResult("teaching_sequence", True,
        f"{len(steps)} step(s), complete, on the objective, from the section's own concepts",
        {"steps": len(steps)})


# ------------------------------------- did the script actually follow the plan?
#
# check_teaching_sequence above asks whether the PLAN is any good. This asks
# whether the SCRIPT took it — the two are separate questions and a short can fail
# either one alone. A plan can be perfect and ignored, which is the failure this
# grader exists for: the sequence goes into the brief as guidance, and guidance
# that nothing checks is a suggestion.
#
# THE BIAS IS TOWARD PASSING, deliberately and throughout. Every failure here
# spends another script call, and a grader that fires on a script a human would
# have accepted is worse than no grader at all — it burns the retry budget that
# the real graders (timing, source_quotes) need, and the third attempt is the one
# that ships. So each rule below is written to catch a script that plainly did
# something else, not to enforce the plan to the letter:
#
#   * coverage asks for HALF the steps, not all of them. Dropping a step the
#     section cannot support is correct behaviour that the script brief explicitly
#     asks for, and merging two steps into one beat is normal — the sequence may
#     have four steps and the script has 2-3 answer beats to say them in.
#   * order fails only on an INVERSION, and only between steps it can locate
#     unambiguously. Ties pass, because a merged beat covers two steps at once.
#   * focus is a gross-drift threshold, not a similarity score. The brief lets the
#     script answer a NARROWER question than the topic asked, so a faithful script
#     can legitimately touch half the objective and no more.
#   * landing accepts EITHER the last step or the objective, since a narrowed
#     question lands on the objective without reaching the final step.
#
# Deterministic and free, on _stems/_grounded like every other grader here — no
# judge, no call. A failure is phrased as an instruction because it goes straight
# back to the script step as retry feedback; see run_script_graders.

#: How much of one step's concept has to turn up in the narration before that step
#: counts as covered. Stems, prefix-matched by _grounded, so "translation" covers
#: "translate" and a beat need not use the plan's phrasing — the plan is written in
#: note form ("Frame plus offset") and the beat is written to be spoken aloud.
MIN_STEP_COVERAGE = 0.5

#: The share of the sequence that must survive into the script. Half, because the
#: sequence is a plan for explaining and the script is what fits in 4-5 beats: a
#: three-step plan delivered as two beats has done the job, and failing it would be
#: failing the brief's own instruction to merge and to drop what the section cannot
#: support. Below half the script is not following this plan, it is using it as a
#: word list.
MIN_SEQUENCE_COVERAGE = 0.5

#: How much of the objective's own vocabulary the narration has to share before the
#: short counts as being about it. Low on purpose — see the note above about the
#: narrower question, which is the brief's prescribed escape hatch for a thin
#: section and which lands an honest script at roughly 40%. This number is set to
#: catch a script about something else, and nothing finer.
MIN_OBJECTIVE_FOCUS = 0.3


def _covered_steps(steps, beat_stems: list[set], all_stems: set):
    """Which beat, if any, first carries each step. Returns [(i, step, beat_idx)].

    MATCHED ON WHAT MAKES A STEP DIFFERENT FROM ITS NEIGHBOURS, not on its whole
    concept, and this is the difference between a working grader and one that
    passes everything. Steps in a sequence share vocabulary by construction —
    "Page number and offset", "Page table lookup" and "Frame number concatenated
    with the offset" have `page`, `number` and `offset` between them — so a single
    beat saying "a logical address splits into a page number and an offset"
    satisfies two thirds of the LAST step's words without going anywhere near it.
    Measured on exactly that script: it scored 2 of 3 steps covered and passed a
    coverage floor it should have failed.

    So a step is looked for by its DISTINCTIVE stems — the ones no other step's
    concept uses. A step whose every word is shared (the first step above owns
    nothing: `page` belongs to step 2, `number` and `offset` to step 3) has none,
    and falls back to its full concept, which is the lenient reading and the right
    one: there is no evidence available to fail it on.

    beat_idx is None when the step cannot be pinned to one beat — the same
    no-distinctive-stems case. Those steps still count for COVERAGE and are left
    out of the ORDER check, because locating them is guesswork and an order
    failure built on a guess costs a real script call.
    """
    concept_stems = [set(s for s in _stems(getattr(st, "concept", "") or "")
                         if len(s) > 3) for st in steps]

    located = []
    for i, (step, stems) in enumerate(zip(steps, concept_stems)):
        if not stems:
            continue

        others = set().union(*(c for j, c in enumerate(concept_stems) if j != i)) \
            if len(concept_stems) > 1 else set()
        distinctive = stems - others
        # What this step is judged on: its own words where it has any.
        marks = distinctive or stems

        hit = {s for s in marks if _grounded(s, all_stems)}
        if len(hit) / len(marks) < MIN_STEP_COVERAGE:
            continue                      # not covered at all

        where = None
        if distinctive:
            # A SINGLE SHARED WORD IS NOT ENOUGH WHEN THE STEP HAS MORE TO GO ON.
            #
            # Found on a real short about hash tables. Step 3, "Storing with the
            # computed index", has exactly one distinctive stem: "stor". Beat 1 was
            # a scene-setting opener — "A hash table STORES values under keys, in
            # buckets..." — a sentence about hash tables in general, not about
            # storing AT a computed index specifically. One coincidental verb was
            # enough to credit the step to a beat that never explained it, and the
            # false credit then read as an ORDER INVERSION once the step actually
            # explained (in a later beat) looked like a repeat.
            #
            # The fix asks for one more piece of corroborating evidence when there
            # is any to ask for: a step's OTHER concept words (the ones it shares
            # with a neighbour, so they were excluded from `distinctive`) still
            # narrow down which beat is really talking about THIS step rather than
            # a different one that happens to use the same word. "Storing with the
            # computed index" also carries "computed" and "index" — words a beat
            # about hash TABLES IN GENERAL has no reason to use, and a beat about
            # the storing MECHANISM does. Requiring at least one of them alongside
            # the distinctive word is what tells a generic mention of "stores"
            # apart from the step actually being explained.
            #
            # Skipped when a step's own concept has nothing left to ask for — its
            # distinctive stem(s) already cover its full concept (a two-word phrase
            # like "Keys and buckets" where nothing is shared with a neighbour) —
            # because there is no more signal available and falling back to the
            # single-word match is the same risk this field always carried.
            other_marks = stems - distinctive
            for b, bstems in enumerate(beat_stems):
                if not any(_grounded(s, bstems) for s in distinctive):
                    continue
                if other_marks and not any(_grounded(s, bstems) for s in other_marks):
                    continue
                where = b
                break
        located.append((i, step, where))
    return located


def check_follows_teaching_sequence(script: Script, understanding=None,
                                    source_text: str | None = None) -> GraderResult:
    """
    Did this script take the teaching sequence it was given?

    Four rules, and a script has to break one plainly to fail:

      COVERAGE   at least half the steps show up in the narration, matched on stems
                 rather than on phrases. A step the section could not support is
                 meant to be dropped, so this is a floor, never a checklist.
      ORDER      of the steps that can be located unambiguously, none appears before
                 a step that was planned earlier. Ties pass — that is a merged beat.
      FOCUS      the narration shares enough of core_idea's vocabulary to be about
                 the objective at all.
      LANDING    the last answer beat reaches the final step OR the objective. This
                 is the same rule the script brief spends a page on — the short must
                 not stop one sentence before the answer — asked against the plan.

    Skips clean, passing, when there is no understanding or its sequence is empty
    (absent, or quarantined by check_teaching_sequence). Never raises.
    """
    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    if not steps:
        return GraderResult("follows_sequence", True,
            "no teaching sequence — skipped", {"steps": 0, "skipped": True})

    answers = [b for b in script.beats if b.speaker == "student"]
    if not answers:
        return GraderResult("follows_sequence", False,
            "no student beats to compare against the teaching sequence")

    beat_stems = [set(_stems(b.line)) for b in answers]
    all_stems = set().union(*beat_stems) if beat_stems else set()

    located = _covered_steps(steps, beat_stems, all_stems)
    covered = {i for i, _, _ in located}

    # --- COVERAGE -----------------------------------------------------------
    need = max(1, round(len(steps) * MIN_SEQUENCE_COVERAGE))
    if len(covered) < need:
        missing = [f"step {i + 1} ({s.concept!r})"
                   for i, s in enumerate(steps) if i not in covered]
        return GraderResult("follows_sequence", False,
            f"the answer covers {len(covered)} of {len(steps)} planned steps, and needs "
            f"at least {need}. Not reached: {'; '.join(missing)}. Build the answer "
            f"beats along the teaching sequence — or, if the section cannot support "
            f"a step, drop it AND narrow the question in beat 1 to match what is left.",
            {"covered": sorted(covered), "needed": need, "steps": len(steps)})

    # --- ORDER --------------------------------------------------------------
    placed = [(i, s, b) for i, s, b in located if b is not None]
    inversions = []
    for a in range(len(placed)):
        for b in range(a + 1, len(placed)):
            (i1, s1, beat1), (i2, s2, beat2) = placed[a], placed[b]
            if beat2 < beat1:            # a later step spoken before an earlier one
                inversions.append(
                    f"step {i2 + 1} ({s2.concept!r}) is explained in beat {beat2 + 1}, "
                    f"before step {i1 + 1} ({s1.concept!r}) in beat {beat1 + 1}")
    if inversions:
        return GraderResult("follows_sequence", False,
            f"the answer runs the teaching sequence out of order: {'; '.join(inversions[:3])}. "
            f"The order is the plan — a beginner cannot follow a later step before the "
            f"one it rests on. Reorder the beats to match the sequence.",
            {"inversions": inversions})

    # --- FOCUS --------------------------------------------------------------
    #
    # THE QUESTION'S OWN WORDS COUNT TOO, and this is scoped narrowly to FOCUS
    # alone — COVERAGE and ORDER above stay read against student beats only,
    # because those ask whether the ANSWER walks the plan, which is specifically
    # about the speaker who is supposed to be doing that walking.
    #
    # FOCUS asks a different question: is this SHORT about its objective at all. A
    # viewer hears the interviewer's question immediately before the answer, and a
    # word the question already put in play does not need to be repeated to be
    # understood — "How does a promise CHAIN move..." then an answer that walks
    # the mechanism without saying "chain" again has not gone anywhere else, the
    # topic was set one breath earlier. Scoring that against student beats alone
    # measured a stricter question than the one this check is supposed to ask.
    question_stems = set()
    if script.beats and script.beats[0].speaker == "interviewer":
        question_stems = set(_stems(script.beats[0].line))
    focus_stems = all_stems | question_stems

    objective = {s: w for s, w in _stems(getattr(understanding, "core_idea", "") or "").items()
                 if len(s) > 3}
    if objective:
        hit = [s for s in objective if _grounded(s, focus_stems)]
        focus = len(hit) / len(objective)
        if focus < MIN_OBJECTIVE_FOCUS:
            absent = sorted(objective[s] for s in objective if s not in hit)
            return GraderResult("follows_sequence", False,
                f"the answer touches only {focus:.0%} of the objective's own vocabulary "
                f"— it is not about {getattr(understanding, 'core_idea', '')[:70]!r}. "
                f"Never mentioned: {absent[:8]}. Rewrite the answer so it explains that "
                f"idea, and make beat 1 ask about it.",
                {"focus": focus, "absent": absent})

    # --- LANDING ------------------------------------------------------------
    #
    # EITHER target is a pass, and the OR is load-bearing rather than lenient. The
    # brief tells the script to narrow the question when the section is thin, and a
    # narrowed short lands on the objective without ever reaching the plan's final
    # step. Demanding the final step would fail the brief's own escape hatch.
    last = set(_stems(answers[-1].line))
    final_step = steps[-1]
    targets = {s for s in _stems(f"{final_step.concept} {final_step.explanation_goal}")
               if len(s) > 3}
    targets |= set(objective)
    if targets:
        reached = [s for s in targets if _grounded(s, last)]
        if not reached:
            return GraderResult("follows_sequence", False,
                f"the last beat does not land the answer: it reaches neither the final "
                f"planned step ({final_step.concept!r}) nor the objective. The short stops "
                f"before it has said the thing it exists to say — make the last beat "
                f"deliver {final_step.explanation_goal!r}.",
                {"final_step": final_step.concept})

    return GraderResult("follows_sequence", True,
        f"{len(covered)}/{len(steps)} planned step(s), in order, landing on the objective",
        {"covered": sorted(covered), "steps": len(steps)})


# --------------------------------------------------------------- the example plan
#
# Two graders, because there are two separable failures and conflating them makes
# both unfixable: check_example_plan asks whether the READING chose a real example
# (and runs once, on the understanding), check_uses_planned_example asks whether
# the SCRIPT used it (and runs on every attempt, feeding the retry loop).
#
# The rule underneath both is the one this project keeps relearning: an example is
# only worth anything if it came off the page. A generalised example — "a font
# name" for `font-family: "Roboto"` — teaches less than the specific one and reads
# as if the material said it. An invented one is a fabrication with a concrete
# number attached, which is the most convincing kind.

#: How much of an example's wording has to survive into a beat before the beat
#: counts as having used it. Stems, so "frame numbers" matches "frame number", and
#: NOT length-filtered the way the other checks are: examples are short and their
#: load-bearing word is often three letters — "valid bit", "the i bit", "36px".
MIN_EXAMPLE_USE = 0.6

#: And "examples are short" above has to be ENFORCED, because a real run showed it
#: is an assumption rather than a fact. The reading returned this as its example:
#:
#:   "A selector written `#nav .item a` therefore scores 1 id, 1 class and 1 type,
#:    which is conventionally written 1,1,1."
#:
#: — the whole sentence, not the literal inside it. MIN_EXAMPLE_USE then wanted 60%
#: of a twenty-word sentence's stems inside a single beat that is capped at
#: MAX_ANSWER_WORDS and also has its own point to make. No script could satisfy
#: that, so uses_example failed every attempt on a plan that was otherwise right.
#:
#: Half a beat is the cap: the beat needs the other half for the sentence that
#: frames the example. Over it, check_example_plan drops the plan rather than
#: handing the writer an instruction it cannot carry out — the script then explains
#: in general terms, which is a worse short but a shippable one.
MAX_EXAMPLE_WORDS = MAX_ANSWER_WORDS // 2

#: How far from its own teaching step an example may land. 1 = the beat carrying
#: that step, or either neighbour. An example exists to make one idea concrete; two
#: beats away it is decoration, and the learner has already moved on.
MAX_EXAMPLE_DISTANCE = 1

#: Spans in narration that are example-SHAPED: a literal a script would only say if
#: it were showing something concrete. Used to catch an invented example when the
#: reading said there was none to use.
#:
#: Digits need three characters, and that leniency is deliberate. "2" and "8" turn
#: up in honest narration constantly ("splits into 2 parts") without being examples,
#: and a false failure here costs a real script call — see the bias note on
#: check_follows_teaching_sequence. "1011", "36px" and "3.2" are caught; a bare
#: small integer is not.
_LITERAL_PATTERNS = (
    re.compile(r"`([^`]+)`"),                            # `input()`, `color: blue;`
    # A DECLARATION, NOT EVERY COLON IN EVERY SENTENCE. The property side must be
    # hyphenated (font-family, background-size) or an assignment with `=`, because
    # the bare `word: word` form this used to be matched ordinary prose:
    #
    #   "It counts three things separately: id selectors, then classes"  -> 'separately: id'
    #   "Two things matter here: order and specificity"                  -> 'here: order'
    #
    # Both were then reported as invented examples and the script was rejected, on
    # narration that named nothing concrete at all. A real run lost three script
    # calls to the first one.
    #
    # Single-word CSS properties (color, display, margin) are still caught by the
    # backtick pattern above, which is how a script ought to be writing them, and
    # missing an unbackticked one is the right way to be wrong here — the module
    # already says a false failure costs a real script call.
    re.compile(r"\b([A-Za-z_][\w-]*-[\w-]*\s*:\s*[^\s,.;]+)"),  # font-family: "Roboto"
    re.compile(r"\b([A-Za-z_][\w-]*\s*=\s*[^\s,.;]+)"),          # x = 5
    re.compile(r"\b([A-Za-z_][\w.]*\(\))"),              # input(), len()
    # NO TRAILING \b: a word boundary cannot hold after a non-word character, so
    # "40%" — a fabricated statistic, the single most important literal to catch —
    # matched nothing at all while "1011" matched fine. Trailing punctuation is
    # stripped by _literals instead.
    re.compile(r"\b(\d[\w.%-]{2,})"),                    # 1011, 36px, 3.2, 40%
)


def _literals(text: str) -> list[str]:
    """Example-shaped spans in a piece of narration, deduplicated, in order."""
    found: list[str] = []
    for pattern in _LITERAL_PATTERNS:
        for m in pattern.finditer(text):
            span = m.group(1).strip().strip(".,;")
            if span and span not in found:
                found.append(span)
    return found


def _in_section(span: str, section_text: str) -> bool:
    """Is this span really on the page? Flattened, like check_source_quotes.

    Two ways to be supported, and the second is not a loophole: a verbatim
    substring is the strong form, and failing that EVERY content stem of the span
    has to occur in the section. That second form is what lets "frame numbers"
    count as the section's "frame number" while still failing anything the section
    never mentions — the bar is all of it, not most of it.
    """
    if not span.strip():
        return False
    if _flatten(span) and _flatten(span) in _flatten(section_text):
        return True
    stems = set(_stems(span))
    if not stems:
        return False
    src = set(_stems(section_text))
    return all(_grounded(s, src) for s in stems)


def check_example_plan(understanding, section_text: str | None = None) -> GraderResult:
    """
    Did the reading choose a REAL example, or reach for a plausible one?

    Runs once, on the understanding, next to check_teaching_sequence and with the
    same consequence: a plan that fails is dropped and the rest of the reading is
    kept. Skips clean when there is no plan at all.

    `not_needed` is always valid and is checked no further — that is the point of
    having it. Everything below applies to a plan that claims an example exists.
    """
    plan = getattr(understanding, "example_plan", None)
    if plan is None:
        return GraderResult("example_plan", True, "no example plan — skipped",
                            {"skipped": True})

    need = getattr(plan, "need", "not_needed")
    if need == "not_needed":
        return GraderResult("example_plan", True,
            "no example needed — the section shows nothing concrete", {"need": need})

    example = (getattr(plan, "example", "") or "").strip()
    if not example:
        return GraderResult("example_plan", False,
            f"marked {need} but names no example", {"need": need})

    # THE RULE THIS FIELD EXISTS FOR. An example that is not on the page is not an
    # example, it is an invention wearing a specific number.
    if section_text and not _in_section(example, section_text):
        return GraderResult("example_plan", False,
            f"the example {example[:60]!r} is not in the section — it was invented or "
            f"brought in from outside", {"need": need, "example": example})

    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    supports = getattr(plan, "supports_step", None)
    if supports is not None and steps and not 1 <= supports <= len(steps):
        return GraderResult("example_plan", False,
            f"supports_step {supports} is outside the {len(steps)}-step teaching sequence",
            {"need": need, "supports_step": supports})

    if not (getattr(plan, "learner_takeaway", "") or "").strip():
        return GraderResult("example_plan", False,
            f"marked {need} with no learner_takeaway — nobody decided what the "
            f"example is for", {"need": need})

    # USABLE INSIDE ONE BEAT, or it is not a usable plan — see MAX_EXAMPLE_WORDS.
    # Last of the checks deliberately: a too-long example is the least serious
    # fault here (the example is real and on the page, it was just handed over
    # wrapped in its sentence), so everything that indicates a fabrication gets to
    # report first.
    n = len(example.split())
    if n > MAX_EXAMPLE_WORDS:
        return GraderResult("example_plan", False,
            f"the example is {n} words — {example[:60]!r} — which is the sentence "
            f"around the example rather than the example. A beat is at most "
            f"{MAX_ANSWER_WORDS} words and has its own point to make, so this "
            f"cannot be used inside one and check_uses_planned_example would reject "
            f"every script that tried. Name the literal itself, under "
            f"{MAX_EXAMPLE_WORDS} words.",
            {"need": need, "words": n, "example": example[:60]})

    return GraderResult("example_plan", True,
        f"{need} example {example[:40]!r}, grounded in the section",
        {"need": need, "example": example})


def check_uses_planned_example(script: Script, understanding=None,
                               section_text: str | None = None) -> GraderResult:
    """
    Did the script use the example it was told to, where it was told to?

    Five rules, and only two of them can fail a script outright:

      REQUIRED    the planned example must appear in an answer beat. This is the
                  whole point of the field: `required` means the idea does not land
                  without the worked case, so a script that skipped it did not
                  explain the thing.
      HELPFUL     absence is reported and PASSES. "Use it if the beats have room" is
                  not a rule, and failing it would spend a script call arguing with
                  the brief's own instruction to stay brief.
      NOT_NEEDED  no example is required, and none may be invented (below).
      PLACEMENT   when the example is used AND its teaching step can be located, the
                  two must be within one beat of each other. Both conditions are
                  needed before this can fail — an unlocatable step is not evidence.
      NO INVENTION  a literal the section does not contain fails, whatever the plan
                  says. This is the one rule that runs even with no example plan and
                  no understanding, because "the script made up a value" is wrong
                  independently of whether anybody planned an example.

    Never raises. Skips clean when there is nothing to check.
    """
    answers = [b for b in script.beats if b.speaker == "student"]
    plan = getattr(understanding, "example_plan", None)
    need = getattr(plan, "need", None) if plan is not None else None
    example = ((getattr(plan, "example", "") or "").strip() if plan is not None else "")

    # --- NO INVENTION -------------------------------------------------------
    #
    # First, because it applies with or without a plan. A literal that IS the
    # planned example is allowed by construction — check_example_plan already
    # proved that one is on the page.
    if section_text:
        invented = []
        for beat in script.beats:
            for span in _literals(beat.line):
                if not _in_section(span, section_text):
                    invented.append(span)
        if invented:
            hint = ("The reading found no example worth using in this section, so there "
                    "is nothing concrete to name here — explain it in general terms "
                    "instead." if need == "not_needed" else
                    "Use the section's own example, copied exactly, or none at all.")
            return GraderResult("uses_example", False,
                f"the script states {sorted(set(invented))[:5]}, which the section does "
                f"not contain — that is an invented example. {hint}",
                {"invented": sorted(set(invented))})

    if plan is None:
        return GraderResult("uses_example", True, "no example plan — skipped",
                            {"skipped": True})
    if need == "not_needed":
        return GraderResult("uses_example", True,
                            "no example needed, and none invented", {"need": need})
    if not example:
        return GraderResult("uses_example", True,
                            f"marked {need} but the plan names no example — skipped",
                            {"need": need, "skipped": True})

    # --- WAS IT USED --------------------------------------------------------
    #
    # Stems, not the literal string. The plan is written in note form ("Frame plus
    # offset") and a beat is written to be spoken, so demanding the exact phrase
    # would fail scripts that used the example perfectly well.
    want = set(_stems(example))
    used_in = None
    if want:
        for i, beat in enumerate(answers):
            have = set(_stems(beat.line))
            hit = [s for s in want if _grounded(s, have)]
            if len(hit) / len(want) >= MIN_EXAMPLE_USE:
                used_in = i
                break

    if used_in is None:
        if need == "helpful":
            return GraderResult("uses_example", True,
                f"the helpful example {example[:40]!r} was not used — allowed, the "
                f"beats are tight", {"need": need, "used": False})
        return GraderResult("uses_example", False,
            f"the answer never uses the required example {example[:60]!r}. This section "
            f"does not explain without it — work it into an answer beat so the learner "
            f"sees {(getattr(plan, 'learner_takeaway', '') or 'what it demonstrates')!r}, "
            f"copying it from the section exactly.",
            {"need": need, "used": False, "example": example})

    # --- PLACEMENT ----------------------------------------------------------
    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    supports = getattr(plan, "supports_step", None)
    if steps and supports and 1 <= supports <= len(steps):
        beat_stems = [set(_stems(b.line)) for b in answers]
        all_stems = set().union(*beat_stems) if beat_stems else set()
        located = {i: b for i, _, b in _covered_steps(steps, beat_stems, all_stems)}
        target = located.get(supports - 1)
        if target is not None and abs(used_in - target) > MAX_EXAMPLE_DISTANCE:
            step = steps[supports - 1]
            return GraderResult("uses_example", False,
                f"the example {example[:40]!r} is used in beat {used_in + 1}, but it belongs "
                f"to step {supports} ({step.concept!r}), which is explained in beat "
                f"{target + 1}. An example that far from the idea it makes concrete is "
                f"decoration — move it next to that step.",
                {"need": need, "used_in": used_in + 1, "step_in": target + 1})

    return GraderResult("uses_example", True,
        f"{need} example {example[:40]!r} used in beat {used_in + 1}",
        {"need": need, "used_in": used_in + 1})


# ------------------------------------------------------------- the confusion plan
#
# Same two-grader split as the example plan: check_confusion_plan asks whether the
# READING chose a real misconception with a real correction, check_handles_confusion
# asks what the SCRIPT did about it.
#
# WHAT CAN AND CANNOT BE CHECKED WITHOUT A JUDGE, said plainly because the limit
# matters. "Does this beat contradict the correct understanding?" is a semantic
# question and nothing here can answer it — that is the judge's job, and this step
# is forbidden a model call. What IS decidable is ASSERTION: whether the script
# states the wrong belief's own distinctive content with nothing anywhere near it
# marking it as wrong. That is the failure worth catching anyway, because it is the
# one that actively teaches the error — a short that says "a page fault means the
# program crashed" and never negates it has done more damage than one that skipped
# the correction. So the rules below are about polarity and assertion, not meaning,
# and they are deliberately narrow: every one of them can only fire on evidence
# that is actually in the text.

#: How much of the correction has to survive into a beat before the clarification
#: counts as delivered. Lower than the example threshold because a correction is a
#: whole sentence and a beat says it in fewer words — "Each page table entry
#: carries a valid bit indicating whether the page is currently resident" landing
#: as "each entry carries a valid bit saying whether the page is resident" is
#: 6 stems of 11, and that is a delivered clarification.
MIN_CLARIFICATION_USE = 0.4

#: How much of the confusion has to be ABOUT this section before the plan is
#: believed. A misconception is not in the section — that is what makes it a
#: misconception — so it cannot be grounded like a claim. It can be required to be
#: on this subject, which is what stops one arriving from general knowledge.
MIN_CONFUSION_TOPICALITY = 0.5

#: Words that mark a belief as wrong, contrasted, or corrected.
#:
#: DELIBERATELY WIDE, including plain "but" and "however". A narrow list would fail
#: honest scripts that negate the belief in wording this does not predict, and each
#: such failure spends a real script call. Wide means the rule only fires when
#: NOTHING in the sentence marks the claim as false, which is the case worth failing.
#:
#: "nothing" was in this list and had to come out. It is not a correction marker —
#: "the program has crashed, so nothing more runs" is an assertion of the error
#: with an intensifier, and matching on it let the plainest possible statement of
#: the misconception through the rule built to catch it.
_NEGATION = re.compile(
    r"\b(not|never|no|isn'?t|aren'?t|wasn'?t|doesn'?t|don'?t|didn'?t|"
    r"cannot|can'?t|won'?t|rather|instead|actually|but|however|though|although|"
    r"despite|unlike|contrary|false|wrong|myth|misconception|mistake|"
    r"misleading|does\s+not|is\s+not)\b", re.I)

#: Wording that ATTRIBUTES a belief rather than asserting it — "you would expect
#: the program has crashed" puts the claim in someone else's mouth, which is a
#: legitimate way to raise a misconception before knocking it down.
#:
#: Separate from _NEGATION because it means something different: negation says the
#: claim is false, attribution says the claim is someone's. Either one is enough to
#: show the beat is not teaching the error as fact, which is all this rule asks.
_ATTRIBUTION = re.compile(
    r"\b((you|people|students|learners|beginners|we)\s+(might|would|may|could)?\s*"
    r"(think|thought|believe|assume|expect|imagine)|"
    r"seems?\s+(like|to)|sounds?\s+like|looks?\s+like|appears?\s+to)\b", re.I)

#: Framing that announces a misconception is being discussed. Used ONLY under
#: not_needed, where the reading decided there is nothing to correct and a script
#: doing this anyway has manufactured one.
_MISCONCEPTION_FRAMING = re.compile(
    r"\b(a\s+common\s+(mistake|misconception|error)|commonly\s+(believed|assumed)|"
    r"(most\s+|many\s+|a\s+lot\s+of\s+)?(people|students|learners|beginners)\s+"
    r"(think|believe|assume|expect)|you\s+might\s+(think|assume|expect)|"
    r"(it'?s|it\s+is)\s+(easy|tempting)\s+to\s+(think|assume)|contrary\s+to)\b", re.I)


def _distinctive(text: str, against: str) -> set:
    """Content stems of `text` that `against` does not also use.

    The confusion and its correction are about the same thing and therefore share
    most of their words — "a page fault means the program crashed" against "a page
    fault is a normal trap the OS services" overlaps on the whole subject. What
    separates them is the handful of stems only one of them has, and those are the
    only ones that can tell a beat stating the error from a beat stating the truth.
    """
    return set(_stems(text)) - set(_stems(against))


def check_confusion_plan(understanding, section_text: str | None = None) -> GraderResult:
    """
    Did the reading pick a real misconception, with a correction that is on the page?

    Runs once, on the understanding, beside check_teaching_sequence and
    check_example_plan, with the same consequence — a failing plan is dropped and
    the rest of the reading kept. `not_needed` is always valid and checked no
    further; that is the whole point of it existing.
    """
    plan = getattr(understanding, "confusion_plan", None)
    if plan is None:
        return GraderResult("confusion_plan", True, "no confusion plan — skipped",
                            {"skipped": True})

    need = getattr(plan, "need", "not_needed")
    if need == "not_needed":
        return GraderResult("confusion_plan", True,
            "no misconception to correct — the short just explains", {"need": need})

    confusion = (getattr(plan, "confusion", "") or "").strip()
    correction = (getattr(plan, "correct_understanding", "") or "").strip()

    if not confusion:
        return GraderResult("confusion_plan", False,
            f"marked {need} but names no confusion", {"need": need})
    if not correction:
        return GraderResult("confusion_plan", False,
            f"marked {need} with no correct_understanding — a misconception with no "
            f"correction is just an error handed to the viewer", {"need": need})

    if section_text:
        # THE CORRECTION IS A CLAIM, so it is checked like one.
        if not _in_section(correction, section_text):
            return GraderResult("confusion_plan", False,
                f"the correction {correction[:60]!r} is not supported by the section — "
                f"a clarification the material does not make is an invention",
                {"need": need, "correction": correction})

        # THE CONFUSION IS NOT A CLAIM, so it is checked for topicality only.
        stems = set(_stems(confusion))
        if stems:
            src = set(_stems(section_text))
            on_topic = [s for s in stems if _grounded(s, src)]
            share = len(on_topic) / len(stems)
            if share < MIN_CONFUSION_TOPICALITY:
                return GraderResult("confusion_plan", False,
                    f"the confusion {confusion[:60]!r} is only {share:.0%} in the section's "
                    f"vocabulary — it is a misconception about something else, brought in "
                    f"from outside", {"need": need, "topicality": share})

    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    relates = getattr(plan, "relates_to_step", None)
    if relates is not None and steps and not 1 <= relates <= len(steps):
        return GraderResult("confusion_plan", False,
            f"relates_to_step {relates} is outside the {len(steps)}-step teaching sequence",
            {"need": need, "relates_to_step": relates})

    if not (getattr(plan, "learner_takeaway", "") or "").strip():
        return GraderResult("confusion_plan", False,
            f"marked {need} with no learner_takeaway — nobody decided what correcting "
            f"it achieves", {"need": need})

    return GraderResult("confusion_plan", True,
        f"{need}: {confusion[:40]!r}, corrected from the section",
        {"need": need, "confusion": confusion})


def check_handles_confusion(script: Script, understanding=None,
                            section_text: str | None = None) -> GraderResult:
    """
    Did the script correct the planned misconception — or accidentally teach it?

    Rules, in the order they can fail:

      ASSERTED AS FACT   a beat states the confusion's own distinctive content and
                         nothing IN THAT BEAT negates it, attributes it to someone,
                         or carries the correction. Judged per beat and not across
                         neighbours, because a false sentence said in beat 2 and
                         fixed in beat 3 has still been said. This is the worst
                         outcome available and it fails under EVERY need, including
                         not_needed — teaching the error is wrong whoever planned
                         what.
      MANUFACTURED       under not_needed only: the script opens a "common mistake"
                         with framing language when the reading said there was
                         nothing to correct.
      REQUIRED MISSING   the correction does not reach any answer beat.
      HELPFUL MISSING    reported, and PASSES.

    On "does the clarification CONTRADICT the correction" — see the note above this
    function. Contradiction in general needs a judge and this step has none, so what
    is enforced is the decidable half: a beat carrying the wrong belief must carry
    the correction or a marker that it is wrong. A beat that flatly reverses the
    correction's polarity lands in exactly that case and fails there.

    Never raises. Skips clean when there is nothing to check.
    """
    plan = getattr(understanding, "confusion_plan", None)
    if plan is None:
        return GraderResult("handles_confusion", True, "no confusion plan — skipped",
                            {"skipped": True})

    need = getattr(plan, "need", "not_needed")
    confusion = (getattr(plan, "confusion", "") or "").strip()
    correction = (getattr(plan, "correct_understanding", "") or "").strip()
    answers = [b for b in script.beats if b.speaker == "student"]

    # --- ASSERTED AS FACT ---------------------------------------------------
    if confusion and correction:
        wrong_marks = _distinctive(confusion, correction)
        right_marks = _distinctive(correction, confusion)
        if wrong_marks:
            for i, beat in enumerate(answers):
                have = set(_stems(beat.line))
                hit = [s for s in wrong_marks if _grounded(s, have)]
                if len(hit) / len(wrong_marks) < MIN_CLARIFICATION_USE:
                    continue                      # this beat is not about the error

                # THIS BEAT, not the neighbourhood. That was the first cut and it
                # was wrong: it passed a script that stated the falsehood flatly in
                # beat 2 and corrected it in beat 3, which is precisely the pattern
                # the script brief calls BAD. A viewer hears sentences in order. By
                # the time the correction arrives the false one has been said, in
                # the student's voice, and the beat carrying it was a beat.
                #
                # Three ways for the beat to be innocent, and all three are visible
                # in its own text: it negates the claim, it attributes the claim to
                # someone, or it carries the correction alongside.
                if _NEGATION.search(beat.line) or _ATTRIBUTION.search(beat.line):
                    continue
                if right_marks and any(_grounded(s, have) for s in right_marks):
                    continue

                return GraderResult("handles_confusion", False,
                    f"beat {i + 1} states the misconception as if it were true: {beat.line!r}. "
                    f"The section says: {correction[:110]!r}. Never say the wrong belief on "
                    f"its own, not even to correct it in the next beat — the viewer has "
                    f"already heard it. Say what is actually true in the same breath.",
                    {"need": need, "beat": i + 1, "confusion": confusion})

    # --- MANUFACTURED -------------------------------------------------------
    if need == "not_needed":
        for i, beat in enumerate(script.beats):
            m = _MISCONCEPTION_FRAMING.search(beat.line)
            if m:
                return GraderResult("handles_confusion", False,
                    f"beat {i + 1} opens a misconception ({m.group(0)!r}) that nothing asked "
                    f"for — the reading found nothing here worth correcting. Cut it and use "
                    f"the beat to explain the idea instead.",
                    {"need": need, "beat": i + 1, "framing": m.group(0)})
        return GraderResult("handles_confusion", True,
            "no misconception needed, and none introduced", {"need": need})

    if not confusion or not correction:
        return GraderResult("handles_confusion", True,
            f"marked {need} but the plan is incomplete — skipped",
            {"need": need, "skipped": True})

    # --- WAS THE CORRECTION DELIVERED --------------------------------------
    want = set(_stems(correction))
    delivered = None
    if want:
        for i, beat in enumerate(answers):
            have = set(_stems(beat.line))
            hit = [s for s in want if _grounded(s, have)]
            if len(hit) / len(want) >= MIN_CLARIFICATION_USE:
                delivered = i
                break

    if delivered is None:
        if need == "helpful":
            return GraderResult("handles_confusion", True,
                f"the helpful clarification was not made — allowed, a short need not "
                f"spend a beat on it", {"need": need, "clarified": False})
        return GraderResult("handles_confusion", False,
            f"the answer never clarifies the required misconception ({confusion[:60]!r}). "
            f"The section says {correction[:80]!r} — work that into the beat that explains "
            f"it, so the learner ends up knowing "
            f"{(getattr(plan, 'learner_takeaway', '') or 'what is actually true')!r}. "
            f"Do not add a separate 'common mistake' beat; correct it inside the explanation.",
            {"need": need, "clarified": False, "confusion": confusion})

    return GraderResult("handles_confusion", True,
        f"{need} misconception clarified in beat {delivered + 1}",
        {"need": need, "clarified_in": delivered + 1})


# ------------------------------------------------------------------- the opening
#
# Beat 1 is where a short is won or thrown away, and it is also where every bad
# short-form instinct lives — the manufactured stake, the invented figure, the
# "most people get this wrong" resting on nothing. The brief has always forbidden
# those in prose; these two graders are what makes the ban decidable.
#
# The split is the same as the last three plans: check_hook_plan asks whether the
# READING chose an opening the section can carry, check_opening_follows_hook asks
# whether the SCRIPT opened that way.

#: How much of the planned hook's vocabulary should turn up in the opening beat.
#: LOW, and deliberately so: the plan states the hook as an idea and the script
#: writes the sentence, so demanding phrase overlap would be demanding the exact
#: phrase matching this step forbids. A third of the content words is enough to
#: show the opening is about the planned thing rather than about something else.
MIN_HOOK_ECHO = 0.3

#: How much of the objective has to be in reach of the opening — beat 1 plus the
#: first answer beat. Lower still, because an opening legitimately approaches the
#: objective obliquely (a problem hook names the problem, not the solution). This
#: only fails an opening that hands over to nothing.
MIN_HOOK_LEADS_IN = 0.2

#: How much of a problem or surprise hook must be grounded in the section. Not the
#: 100% that _in_section demands of an example: a hook is a paraphrase by nature —
#: it says the section's situation in a viewer's words — so a stem or two of
#: connective vocabulary is expected. 80% still fails anything with a fact in it
#: that the section does not have.
MIN_HOOK_GROUNDING = 0.8

#: The same question asked of the SCRIPT'S OPENING BEAT, and the answer has to be
#: very different. The plan paraphrases the section; beat 1 is a spoken question in
#: a learner's voice, and it is SUPPOSED to use everyday words the section does not.
#: "If memory is free but split up, why can't a process use it?" is a faithful
#: opening for a section that says "divided" rather than "split", and holding it to
#: the plan's 80% failed it — which is exactly the phrase matching this grader is
#: forbidden to do.
#:
#: This number exists to catch an opening about a DIFFERENT TOPIC. The unrelated
#: disk-scheduling opening scores 0%; honest reworded openings score 65-75%. 0.5
#: separates those with room on both sides, and nothing finer is being claimed.
MIN_OPENING_GROUNDING = 0.5

#: Engagement language that promises what the material does not contain. Rejected
#: wherever it appears, under every hook kind including none at all — this is not a
#: matter of following the plan, it is the one thing a short must never open with.
_CLICKBAIT = re.compile(
    r"(you\s+won'?t\s+believe|"
    r"(most|all|almost\s+all)\s+(people|developers|students|engineers)\s+get\s+"
    r"(this|it)\s+wrong|everyone\s+gets\s+(this|it)\s+wrong|"
    r"(nobody|no\s+one)\s+(tells|teaches)\s+you|"
    r"blow\s+your\s+mind|mind[\s-]?blowing|will\s+shock\s+you|"
    r"the\s+secret\s+(to|of|behind)|what\s+(they|nobody)\s+"
    r"(don'?t|doesn'?t)\s+want\s+you\s+to\s+know|"
    r"\d{1,3}\s*%\s+of\s+(people|developers|students|engineers)|"
    r"here'?s\s+the\s+trick|this\s+changes\s+everything|"
    r"you'?re\s+doing\s+(it|this)\s+wrong)", re.I)


def _grounded_share(text: str, source_text: str) -> float:
    """What fraction of `text`'s content stems the source also uses. 1.0 if empty."""
    stems = set(_stems(text))
    if not stems:
        return 1.0
    src = set(_stems(source_text))
    return len([s for s in stems if _grounded(s, src)]) / len(stems)


def check_hook_plan(understanding, section_text: str | None = None) -> GraderResult:
    """
    Can the section actually carry the opening the reading chose?

    Runs once, on the understanding, and a failing plan is dropped like the others.
    `direct` is always valid and checked no further — that is what makes it a real
    option rather than a fallback nobody picks.

    GROUNDED DIFFERENTLY BY KIND, because the kinds are different sorts of thing:
    a `problem` or a `surprise` is a CLAIM about the material and is checked as
    one; a `question` is not a claim, so it is checked for being about this section
    rather than for being true.
    """
    plan = getattr(understanding, "hook_plan", None)
    if plan is None:
        return GraderResult("hook_plan", True, "no hook plan — skipped", {"skipped": True})

    kind = getattr(plan, "kind", "direct")
    if kind == "direct":
        return GraderResult("hook_plan", True,
            "direct opening — the concept is its own hook", {"kind": kind})

    hook = (getattr(plan, "hook", "") or "").strip()
    if not hook:
        return GraderResult("hook_plan", False,
            f"a {kind} hook with nothing to open on", {"kind": kind})

    clickbait = _CLICKBAIT.search(hook)
    if clickbait:
        return GraderResult("hook_plan", False,
            f"the hook is engagement language, not content: {clickbait.group(0)!r}. "
            f"A hook has to be something the section says", {"kind": kind})

    if section_text:
        share = _grounded_share(hook, section_text)
        if kind in ("problem", "surprise"):
            # A claim, so it is held to the bar a claim is held to.
            if share < MIN_HOOK_GROUNDING:
                return GraderResult("hook_plan", False,
                    f"the {kind} hook {hook[:60]!r} is only {share:.0%} in the section — "
                    f"a {kind} the material does not establish is an invention, and it is "
                    f"the first thing the viewer hears", {"kind": kind, "grounding": share})
        elif share < MIN_CONFUSION_TOPICALITY:
            # A question is not a claim; it only has to be about this section.
            return GraderResult("hook_plan", False,
                f"the question hook {hook[:60]!r} is only {share:.0%} in the section's "
                f"vocabulary — it opens on a different topic",
                {"kind": kind, "grounding": share})

    if not (getattr(plan, "why_it_matters", "") or "").strip():
        return GraderResult("hook_plan", False,
            f"a {kind} hook with no reason a learner should care", {"kind": kind})

    leads = (getattr(plan, "leads_into", "") or "").strip()
    if not leads:
        return GraderResult("hook_plan", False,
            f"a {kind} hook that hands over to nothing — say which concept it leads into",
            {"kind": kind})

    # AND IT HAS TO LEAD SOMEWHERE IN PARTICULAR. A hook can be grounded, sharp and
    # about a different part of the material; that is a hook for another short.
    objective = (getattr(understanding, "core_idea", "") or "").strip()
    if objective and _grounded_share(leads, objective) < MIN_HOOK_LEADS_IN:
        return GraderResult("hook_plan", False,
            f"the hook leads into {leads[:60]!r}, which is not the objective "
            f"({objective[:60]!r}) — it opens a different topic",
            {"kind": kind, "leads_into": leads})

    return GraderResult("hook_plan", True,
        f"{kind} hook, grounded, leading into the objective", {"kind": kind})


def check_opening_follows_hook(script: Script, understanding=None,
                               section_text: str | None = None) -> GraderResult:
    """
    Did the script open the way the reading planned, and honestly?

    Rules, in the order they can fail:

      CLICKBAIT      engagement language anywhere in the script. Runs with or
                     without a hook plan, because "you won't believe" is wrong
                     whoever planned what.
      UNSUPPORTED    a literal in the opening the section does not contain, or an
                     opening mostly made of vocabulary the section never uses. The
                     first sentence is the one a viewer trusts most.
      ON THE HOOK    the opening echoes the planned hook OR the objective. Either
                     is enough — a script that opened straight onto the idea has
                     not failed by skipping a `helpful`-grade flourish.
      LEADS IN       the objective is in reach of beat 1 plus the first answer beat.
                     This is what "leads into the teaching sequence" means
                     concretely: a hook that never arrives is a different topic.

      `direct` skips ON THE HOOK entirely and is never failed for the absence of a
      question, problem or surprise. It is still held to clickbait, grounding, and
      leading in — a direct opening that opens on nothing relevant is still wrong.

    No exact phrase matching anywhere: everything is stems through _grounded.
    Never raises.
    """
    beats = script.beats
    if not beats:
        return GraderResult("opening_hook", True, "no beats — skipped", {"skipped": True})

    opening = beats[0].line
    answers = [b for b in beats if b.speaker == "student"]

    # --- CLICKBAIT ----------------------------------------------------------
    for i, beat in enumerate(beats):
        m = _CLICKBAIT.search(beat.line)
        if m:
            return GraderResult("opening_hook", False,
                f"beat {i + 1} uses engagement language the material does not support: "
                f"{m.group(0)!r}. Cut it. The opening has to be something the section "
                f"actually says — a real question, a real problem, or the concept itself.",
                {"clickbait": m.group(0), "beat": i + 1})

    plan = getattr(understanding, "hook_plan", None)
    if plan is None:
        return GraderResult("opening_hook", True, "no hook plan — skipped", {"skipped": True})

    kind = getattr(plan, "kind", "direct")
    hook = (getattr(plan, "hook", "") or "").strip()
    objective = (getattr(understanding, "core_idea", "") or "").strip()

    # --- UNSUPPORTED --------------------------------------------------------
    if section_text:
        for span in _literals(opening):
            if not _in_section(span, section_text):
                return GraderResult("opening_hook", False,
                    f"the opening states {span!r}, which is not in the section — the first "
                    f"sentence of the short is inventing a detail. Open on something the "
                    f"section says.", {"invented": span})
        share = _grounded_share(opening, section_text)
        if share < MIN_OPENING_GROUNDING:
            return GraderResult("opening_hook", False,
                f"only {share:.0%} of the opening is in the section's vocabulary — it opens "
                f"on material this short is not about. Ask about the thing the section "
                f"explains.", {"grounding": share})

    # --- ON THE HOOK --------------------------------------------------------
    if kind != "direct" and hook:
        echo = max(_grounded_share_of(hook, opening),
                   _grounded_share_of(objective, opening) if objective else 0.0)
        if echo < MIN_HOOK_ECHO:
            return GraderResult("opening_hook", False,
                f"the opening does not go near the planned {kind} hook ({hook[:60]!r}) or the "
                f"objective. Beat 1 is the hook — open on that, in your own words.",
                {"kind": kind, "echo": echo})

    # --- LEADS IN -----------------------------------------------------------
    if objective:
        # THE FIRST TWO ANSWER BEATS, not one. With one, a problem-shaped
        # explanation failed for being well built: state the constraint, show what
        # it costs, then resolve it — the objective legitimately arrives in beat 3,
        # and the rule scored that 18% against a 20% bar. A hook is not
        # disconnected because the payoff takes two sentences.
        #
        # Narrowing this rule is safe now in a way it was not before
        # check_reaches_objective existed: "the short never arrives at the idea at
        # all" is that grader's job, asked of the whole answer and without a plan to
        # depend on. What is left here is the question only this grader can ask —
        # whether the OPENING hands over to the explanation or stands apart from it.
        window = " ".join([opening] + [b.line for b in answers[:2]])
        if _grounded_share_of(objective, window) < MIN_HOOK_LEADS_IN:
            return GraderResult("opening_hook", False,
                f"the opening never hands over to the objective ({objective[:70]!r}) — by the "
                f"end of the first answer beat the short has still not started explaining it. "
                f"Get to the idea immediately after the hook.",
                {"kind": kind, "objective": objective[:70]})

    return GraderResult("opening_hook", True,
        f"{kind} opening, grounded, leading into the objective", {"kind": kind})


def _grounded_share_of(text: str, within: str) -> float:
    """Fraction of `text`'s content stems that `within` also uses. 0.0 if empty.

    The mirror of _grounded_share, and separate because the empty case has to
    answer differently: "how much of the hook did the opening echo" is 0 when there
    is no hook to echo, where "how much of the hook is in the section" is 1 when
    there is nothing ungrounded to find.
    """
    stems = set(_stems(text))
    if not stems:
        return 0.0
    have = set(_stems(within))
    return len([s for s in stems if _grounded(s, have)]) / len(stems)


# ====================================================================== the outcome
#
# Everything above this line asks a technical question — is it the right length, is
# every beat cited, did it follow the plan. A short can answer all of them and
# still not teach anything, and that is not a hypothetical: the graders were built
# one at a time, each one closing the hole in front of it, and none of them was
# ever asked "so does a learner come away understanding the idea?"
#
# THIS IS AN ORCHESTRATION, NOT A NEW GRADER. Almost every requirement below is
# ALREADY decided by a grader that ran — follows_sequence knows whether the
# progression survived, uses_example and handles_confusion know whether the
# required interventions happened, opening_hook knows whether beat 1 arrives
# somewhere. Re-deriving any of that here would give two answers to one question
# and a maintenance problem the first time a threshold moves. So this reads their
# verdicts and adds exactly one thing none of them can provide: a VETO.
#
# THE VETO IS THE POINT. A short that passes every technical check and never
# reaches its core_idea must not pass, and no existing grader says so on its own:
# follows_sequence's landing rule accepts the final STEP as an alternative to the
# objective, and it skips entirely when the sequence was quarantined — which is
# precisely when a script is most likely to wander. objective_reached is asked
# directly, of the answer itself, and it holds whether or not any plan survived.
#
# UNAVAILABLE IS NOT FAILURE, and it is the rule that keeps this honest. A plan
# that was never made, or was dropped by its own validator, is missing GUIDANCE —
# it is not evidence against the script. Every requirement below defaults to
# satisfied when the thing that would judge it is absent.

#: How much of the objective's vocabulary the answer as a whole has to carry.
MIN_OBJECTIVE_COVERAGE = 0.4

#: And how much of it the LAST answer beat has to carry. Lower, because the last
#: beat is one sentence and the objective is a whole one — this asks whether the
#: short ENDS on the idea, not whether it restates it. A short whose final beat has
#: nothing of the objective in it has stopped somewhere else, which is the defect
#: the script brief opens with.
MIN_OBJECTIVE_LANDING = 0.2


@dataclass
class LearningOutcome:
    """Whether this short appears to teach the thing it set out to teach.

    Six requirements and a verdict. `problems` carries one line per failed
    requirement, written as an instruction, because it is what goes back to the
    script step as retry feedback.

    Each flag is True when the requirement is MET or when it is UNAVAILABLE — see
    the note above. `unavailable` records which ones nobody could judge, so a
    passing outcome can be read honestly rather than as six green ticks.
    """
    objective_reached: bool = True
    teaching_sequence_covered: bool = True
    required_example_satisfied: bool = True
    required_confusion_satisfied: bool = True
    opening_leads_into_learning: bool = True
    source_grounding_satisfied: bool = True

    problems: list = field(default_factory=list)
    unavailable: list = field(default_factory=list)
    details: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict:
        return {"objective_reached": self.objective_reached,
                "teaching_sequence_covered": self.teaching_sequence_covered,
                "required_example_satisfied": self.required_example_satisfied,
                "required_confusion_satisfied": self.required_confusion_satisfied,
                "opening_leads_into_learning": self.opening_leads_into_learning,
                "source_grounding_satisfied": self.source_grounding_satisfied,
                "passed": self.passed,
                "problems": list(self.problems),
                "unavailable": list(self.unavailable)}


def _verdict(results, name: str):
    for r in results or []:
        if r.name == name:
            return r
    return None


def check_reaches_objective(script: Script, understanding=None) -> GraderResult:
    """
    Does the answer actually arrive at the core idea, and END there?

    THE ONE CHECK THIS STEP HAD TO ADD, because nothing else asks it unconditionally.
    follows_sequence has a landing rule, but it accepts the final teaching STEP as
    an alternative to the objective and it does not run at all when the sequence was
    quarantined. This runs whenever there is a core_idea, plan or no plan, and it is
    the veto the whole outcome hangs on.

    Two halves, and they fail differently:
      COVERAGE  the answer as a whole carries enough of the objective's vocabulary
                to have been about it.
      LANDING   the LAST answer beat carries some of it, so the short ends on the
                idea rather than trailing off into a detail.

    Stems throughout, so no phrasing is prescribed. Skips clean with no core_idea.
    """
    objective = (getattr(understanding, "core_idea", "") or "").strip()
    if not objective:
        return GraderResult("reaches_objective", True,
            "no stated objective — skipped", {"skipped": True})

    answers = [b for b in script.beats if b.speaker == "student"]
    if not answers:
        return GraderResult("reaches_objective", False, "no answer beats at all")

    whole = " ".join(b.line for b in answers)
    coverage = _grounded_share_of(objective, whole)
    if coverage < MIN_OBJECTIVE_COVERAGE:
        return GraderResult("reaches_objective", False,
            f"the answer covers only {coverage:.0%} of the objective ({objective[:80]!r}) — "
            f"whatever else it does, it does not teach that. Rewrite the answer beats to "
            f"explain the idea itself.",
            {"coverage": coverage, "objective": objective[:80]})

    # LANDING, with one alternative: the plan's own final step.
    #
    # THE FALSE POSITIVE THIS FIXES, measured on a real run. The short below passed
    # every other grader at 29.6s and was rejected here at 17%:
    #
    #   Q  "When two CSS rules conflict, how does the browser pick a winner?"
    #   1  "It scores each selector's specificity, and the higher score wins no
    #       matter which rule was read last."
    #   2  "The score counts three things separately: ids, then classes and
    #       attributes, then types."
    #   3  "`#nav .item a` scores 1,1,1, while `.item .link a` scores 0,2,1."
    #   4  "Comparing left to right, that id makes 1,0,0 beat 0,2,1 — so extra
    #       classes never outrank an id."
    #
    # Beat 4 is the CONSEQUENCE, and the script brief demands exactly that: for a
    # "How..." question it says "the last beat is the RESULT of the process". The
    # script obeyed its brief and this rejected it, because a concrete result does
    # not echo the vocabulary of an abstract objective sentence. check_beats_develop
    # names "a consequence of it" as a legitimate thing for a later beat to
    # contribute, so the grader set disagreed with itself.
    #
    # What this check cannot tell apart is a DETAIL from a CONSEQUENCE. follows_sequence
    # can, because the plan says where the explanation ends — and it PASSED on that
    # short, landing on the final planned step. So the final step is accepted as an
    # alternative here too, exactly as it is there and for the same reason.
    #
    # THE UNCONDITIONAL GUARANTEE IS KEPT WHERE IT WAS NEEDED. This grader exists
    # because follows_sequence does not run when the sequence was quarantined; with
    # no sequence there is no alternative to fall back on and the objective is
    # required, which is the case the strictness was written for.
    landing = _grounded_share_of(objective, answers[-1].line)
    if landing < MIN_OBJECTIVE_LANDING:
        steps = list(getattr(understanding, "teaching_sequence", None) or [])
        landed_on_plan = False
        if steps:
            final = steps[-1]
            landed_on_plan = _grounded_share_of(
                f"{final.concept} {final.explanation_goal}",
                answers[-1].line) >= MIN_OBJECTIVE_LANDING
        if not landed_on_plan:
            return GraderResult("reaches_objective", False,
                f"the last beat has almost nothing of the objective in it ({landing:.0%}) "
                f"and does not land the final planned step either — the short explains "
                f"its way toward {objective[:70]!r} and then ends on a detail. Make the "
                f"final beat land the idea, or the result the plan ends on.",
                {"coverage": coverage, "landing": landing})
        return GraderResult("reaches_objective", True,
            f"the answer reaches the objective ({coverage:.0%}) and ends on the final "
            f"planned step ({steps[-1].concept!r}) rather than on the objective's own "
            f"words — allowed, the plan says that is where the explanation ends",
            {"coverage": coverage, "landing": landing, "via": "final_step"})

    return GraderResult("reaches_objective", True,
        f"the answer reaches the objective ({coverage:.0%}) and ends on it ({landing:.0%})",
        {"coverage": coverage, "landing": landing})


def evaluate_learning_outcome(script: Script, understanding=None,
                              source_text: str | None = None,
                              results=None) -> LearningOutcome:
    """
    Does this short look like it teaches its objective? Deterministic, no model.

    `results` is the list run_script_graders already produced. Passing it is the
    normal path and the reason this is cheap: every requirement except the veto is
    a verdict that has already been computed, and reading it costs nothing. When it
    is omitted the graders it needs are run here instead, so the function is usable
    on its own.

    A requirement whose grader is absent from `results` — because there was no
    source text, or no plan of that kind — is recorded as UNAVAILABLE and left
    satisfied. Absent guidance is not evidence of a bad script.
    """
    outcome = LearningOutcome()

    # --- THE VETO, computed here because nothing else asks it -----------------
    reaches = _verdict(results, "reaches_objective") or \
        check_reaches_objective(script, understanding)
    if reaches.details.get("skipped"):
        outcome.unavailable.append("objective_reached (no core_idea in the understanding)")
    elif not reaches.passed:
        outcome.objective_reached = False
        # The full message, because this is the one requirement no other grader
        # reported — everything below is cross-referenced instead of restated.
        outcome.problems.append(f"THE SHORT DOES NOT REACH ITS OBJECTIVE. {reaches.reason}")
    outcome.details["reaches_objective"] = reaches.details

    # --- THE REUSED VERDICTS -------------------------------------------------
    #
    # Named, not restated. Each of these graders is in the same feedback block the
    # script step is about to read, with its own specific instruction; repeating
    # the text here would spend prompt on saying everything twice. What this adds
    # is the stake — that the failure is a LEARNING failure and not a nit.
    reused = [
        ("teaching_sequence_covered", "follows_sequence",
         lambda: check_follows_teaching_sequence(script, understanding, source_text),
         "the explanation does not carry enough of the planned teaching progression"),
        ("required_example_satisfied", "uses_example",
         lambda: check_uses_planned_example(script, understanding, source_text),
         "a required worked example is missing or misused"),
        ("required_confusion_satisfied", "handles_confusion",
         lambda: check_handles_confusion(script, understanding, source_text),
         "a required misconception is left uncorrected, or is stated as fact"),
        ("opening_leads_into_learning", "opening_hook",
         lambda: check_opening_follows_hook(script, understanding, source_text),
         "the opening does not lead into what the short teaches"),
    ]
    for flag, name, compute, summary in reused:
        verdict = _verdict(results, name)
        if verdict is None and understanding is not None:
            verdict = compute()
        if verdict is None:
            outcome.unavailable.append(f"{flag} (no {name} verdict)")
            continue
        if verdict.details.get("skipped"):
            outcome.unavailable.append(f"{flag} (no plan — guidance unavailable)")
            continue
        if not verdict.passed:
            setattr(outcome, flag, False)
            outcome.problems.append(f"{summary} — fix `{name}` above")

    # --- GROUNDING, which is three graders answering one requirement ---------
    grounding_names = ("source_quotes", "on_topic", "grounding")
    seen = [(n, _verdict(results, n)) for n in grounding_names]
    seen = [(n, v) for n, v in seen if v is not None]
    if not seen:
        outcome.unavailable.append("source_grounding_satisfied (no source text)")
    else:
        broken = [n for n, v in seen if not v.passed]
        if broken:
            outcome.source_grounding_satisfied = False
            outcome.problems.append(
                f"the short teaches things its own section does not support — "
                f"fix {', '.join(f'`{n}`' for n in broken)} above")

    return outcome


def check_learning_outcome(script: Script, understanding=None,
                           source_text: str | None = None,
                           results=None) -> GraderResult:
    """evaluate_learning_outcome as a grader, so it rides the existing retry path.

    Deliberately LAST in the list and deliberately terse: the specific instructions
    are already in the failures it names, and this adds the sentence that says what
    those failures amount to. A short that fails only here — every technical check
    green and the objective never reached — is the case this whole step exists for,
    and then the reason carries the full explanation because nothing else did.
    """
    outcome = evaluate_learning_outcome(script, understanding, source_text, results)
    detail = outcome.as_dict()

    if outcome.passed:
        met = [k for k, v in detail.items()
               if k not in ("passed", "problems", "unavailable") and v]
        note = f", {len(outcome.unavailable)} not applicable" if outcome.unavailable else ""
        return GraderResult("learning_outcome", True,
            f"{len(met)} learning requirement(s) met{note}", detail)

    return GraderResult("learning_outcome", False,
        "this short does not yet teach what it set out to teach. "
        + " ".join(f"({i + 1}) {p}" for i, p in enumerate(outcome.problems)),
        detail)


# --------------------------------------------------------- beats that go nowhere
#
# THE HOLE THIS CLOSES, found in shipped output. Every grader in this file asks
# about ONE beat: is it the right length, is it cited, is it on the section, does
# it use the planned example. Not one of them compares a beat to the beats BESIDE
# it, so a script could say the same thing twice and score 13 out of 13. From
# output/html_doc_basic_structure.json, generated by the real pipeline:
#
#   beat 1  "This is the basic structure of any HTML document - doctype, html,
#            head, and body, always together."
#   beat 4  "So doctype, html, head, and body together form the structure every
#            document follows, no matter what."
#
# Beat 4 is beat 1 with the words moved. It is the "so in summary" beat the script
# brief explicitly says to delete, and a quarter of the video is spent on it.
#
# check_source_quotes made this WORSE rather than catching it. It demands a
# DISTINCT citation per beat, so the cheapest way to satisfy it is to keep saying
# the same thing while pointing at a different sentence — the grader asks for new
# evidence and accepts it as proof of a new idea.
#
# NOVELTY, NOT SIMILARITY, is what is measured, and the difference is the whole
# design. Two beats in a technical explanation SHOULD share most of their nouns —
# "page number", "frame", "offset" recur because the subject recurs — so scoring
# overlap would fail every honest script about one idea. What separates a
# developing explanation from a restatement is whether the later beat brings
# anything of its own: a mechanism, a consequence, an example, a conclusion. All
# of those arrive as content words that have not been said yet.

#: How much of a beat has to be new. A beat below this is mostly words the viewer
#: has already heard, in a short with four or five beats to spend.
#:
#: MEASURED, not guessed, on the six fixtures this grader was built against:
#:
#:     shipped recap beat (the real bug)      0.12   fail
#:     exact duplicate of an earlier beat     0.00   fail
#:     reworded restatement of beat 2         0.33   fail
#:     ---------------------------------------------------
#:     shared technical vocabulary            0.50   pass
#:     two adjacent but distinct steps        0.71   pass
#:     conclusion that lands the payoff       0.78   pass
#:
#: The band between 0.33 and 0.50 is empty, so 0.4 sits in the gap with room on
#: both sides. 0.3 was the first cut and it let the reworded restatement through by
#: 0.03 — on the strength of `lett`, which is what the stemmer makes of "letting":
#: a stopword that survives as a content stem because the suffix rule does not
#: collapse the double consonant. A threshold that close to the noise is not a
#: threshold, and the stemmer is not this change's to fix.
MIN_BEAT_NOVELTY = 0.4

#: And it must be restating one PARTICULAR earlier beat, not merely reusing the
#: short's shared vocabulary. Both conditions are required before failing, so a
#: beat that is thin but not a copy of anything is left alone — that is
#: check_dialogue_shape's business, not this one.
MIN_RESTATEMENT_OVERLAP = 0.5

#: Below this many content words a beat carries too little signal to judge. A
#: four-word beat can be entirely new or entirely old on the strength of one stem,
#: and failing a script on that is a coin toss with a script call as the stake.
MIN_JUDGEABLE_STEMS = 4


def check_beats_develop(script: Script) -> GraderResult:
    """
    Does every answer beat add something, or does one of them just say it again?

    Runs on every script, with or without a content understanding — repetition is
    a defect of the writing, not of any plan, so this is an unconditional script
    grader like timing and overlays.

    A beat fails only when BOTH are true:
      * it is mostly not new — under MIN_BEAT_NOVELTY of its content words are
        unheard, counted against every earlier answer beat, and
      * it is a restatement of one identifiable earlier beat, sharing at least
        MIN_RESTATEMENT_OVERLAP of its words with that one.

    Requiring both is what makes shared technical vocabulary safe. A beat that
    reuses the subject's nouns to say something new clears the first test; a beat
    that is merely brief clears the second.
    """
    answers = [b for b in script.beats if b.speaker == "student"]
    if len(answers) < 2:
        return GraderResult("no_repetition", True, "nothing to repeat")

    stems = [set(_stems(b.line)) for b in answers]
    offenders = []

    for j in range(1, len(answers)):
        mine = stems[j]
        if len(mine) < MIN_JUDGEABLE_STEMS:
            continue                       # too short to read anything into

        earlier = set().union(*stems[:j])
        fresh = [s for s in mine if not _grounded(s, earlier)]
        novelty = len(fresh) / len(mine)
        if novelty >= MIN_BEAT_NOVELTY:
            continue                       # it brought something

        # Which earlier beat is it saying again? The one it shares most with —
        # named so the retry feedback can point at a beat rather than a symptom.
        best, best_share = None, 0.0
        for i in range(j):
            if not stems[i]:
                continue
            shared = len([s for s in mine if _grounded(s, stems[i])]) / len(mine)
            if shared > best_share:
                best, best_share = i, shared

        if best is None or best_share < MIN_RESTATEMENT_OVERLAP:
            continue                       # thin, but not a copy of anything

        offenders.append({
            "beat": j + 1, "repeats": best + 1,
            "novelty": round(novelty, 2), "overlap": round(best_share, 2),
            "new_words": sorted(fresh),
            "line": answers[j].line,
        })

    if not offenders:
        return GraderResult("no_repetition", True,
            f"all {len(answers)} answer beats develop the explanation",
            {"beats": len(answers)})

    worst = offenders[0]
    detail = "; ".join(
        f"beat {o['beat']} restates beat {o['repeats']} "
        f"({o['overlap']:.0%} of its words are already there, only {o['novelty']:.0%} new"
        + (f": {o['new_words']}" if o["new_words"] else "") + ")"
        for o in offenders)

    return GraderResult("no_repetition", False,
        f"{detail}. Beat {worst['beat']} is {worst['line'][:70]!r} — the viewer has already "
        f"heard this. Either DELETE it and let the answer be shorter, or replace it with the "
        f"thing that beat should contribute: the mechanism behind what beat "
        f"{worst['repeats']} said, a consequence of it, the section's own example of it, or "
        f"the conclusion it leads to. A recap is not a beat.",
        {"offenders": offenders})


#: THE PLAN MUST BE ABLE TO FILL THE BEATS, and that is arithmetic rather than a
#: score — which is what this used to be, and why it was wrong twice over.
#:
#: It counted four booleans (>=3 steps, an example, a misconception, >=3 key
#: points) and failed below two of them. That number was picked for an 87-word
#: floor, and when the floor came down to 62 it started flagging the very shape the
#: 25-30s band exists to allow. Worse, it never asked the question that actually
#: matters: check_dialogue_shape requires MIN_ANSWERS answer beats, each one idea,
#: and none of them allowed to restate another. So a plan is deep enough exactly
#: when it holds MIN_ANSWERS things to say.
#:
#: What can fill a beat: a teaching step, a worked example the reading says to use,
#: a misconception it says to correct. Nothing else — key_points are a description
#: of the same steps, which is why counting them separately was double-counting.
#:
#: Three steps and nothing else is therefore NOT enough, and that is not a
#: contradiction of the 25-30s band: a three-thing plan asked for four beats has to
#: pad the fourth, and the band admits short shorts, not padded ones. The fix for
#: such a topic is select's gate, not a longer script.
MIN_PLAN_MATERIAL = MIN_ANSWERS


def _plan_wants(plan) -> bool:
    return getattr(plan, "need", None) in ("required", "helpful")


def plan_material(understanding) -> tuple[int, str]:
    """
    How many distinct beat-worthy things a validated reading actually holds.

    THE ONE DEFINITION OF "MATERIAL", shared by check_plan_depth (is there enough
    for MIN_PLAN_MATERIAL beats) and duration_budget (is there enough for a 5th).
    Splitting this out is not a refactor for its own sake — check_plan_depth's own
    docstring is explicit that a second definition of the same judgement is the
    defect this file keeps removing.

    Caller must already know `understanding` is not None and its teaching_sequence
    is not empty — this does not re-check either, so a caller skips this and
    reports "inconclusive" itself first (see check_plan_depth).
    """
    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    example = _plan_wants(getattr(understanding, "example_plan", None))
    confusion = _plan_wants(getattr(understanding, "confusion_plan", None))
    material = len(steps) + int(example) + int(confusion)
    made_of = (f"{len(steps)} teaching step(s)"
               + (" + a worked example" if example else "")
               + (" + a misconception to correct" if confusion else ""))
    return material, made_of


def duration_budget(understanding) -> tuple[int, int]:
    """
    (min_seconds, max_seconds) this section's own reading actually supports.

    Always (MIN_SECONDS, MAX_SECONDS) unless the reading holds MORE than
    MIN_PLAN_MATERIAL things to say — strictly more, not equal: a plan sitting
    exactly at MIN_PLAN_MATERIAL fills exactly MIN_ANSWERS beats and the 45s
    ceiling already fits that, per schema.HARD_MAX_SECONDS's own arithmetic. Only
    a plan with a genuine 5th thing to say — enough for checks.MAX_ANSWERS's fifth
    beat — earns the wider ceiling, and MAX_ANSWERS/MAX_ANSWER_WORDS are what cap
    it even then: this never asks for more beats or longer ones than those two
    constants already allow, it only stops check_timing rejecting a script that
    used them.

    Same "inconclusive" handling as check_plan_depth, for the same reason: a
    quarantined or absent reading has not earned a narrower answer OR a wider one,
    so it gets the ordinary band rather than a guess.
    """
    if understanding is None:
        return MIN_SECONDS, MAX_SECONDS
    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    if not steps:
        return MIN_SECONDS, MAX_SECONDS
    material, _ = plan_material(understanding)
    if material <= MIN_PLAN_MATERIAL:
        return MIN_SECONDS, MAX_SECONDS
    return MIN_SECONDS, HARD_MAX_SECONDS


def check_duration_budget(understanding, section_text: str | None = None) -> GraderResult:
    """
    Reports the (min, max) seconds duration_budget grants this section's own
    reading — observable rather than gating, the same way check_plan_depth grades
    the reading and leaves check_timing as the one hard gate on the script itself.

    Always passes: this is not a second opinion on whether the plan is deep
    enough (check_plan_depth already is that one), it is a report of what the
    budget came out to, so a change to duration_budget's arithmetic is caught by
    a fixture here rather than discovered later as a script mysteriously allowed
    (or refused) a length it should not have been.
    """
    min_s, max_s = duration_budget(understanding)
    extended = max_s > MAX_SECONDS
    return GraderResult("duration_budget", True,
        f"{min_s}-{max_s}s" + (" (extended)" if extended else " (ordinary)"),
        {"min_seconds": min_s, "max_seconds": max_s, "extended": extended})


def check_plan_depth(understanding, section_text: str | None = None) -> GraderResult:
    """
    Is there enough in this reading to fill 35-50 seconds without restating?

    THE ONE PLACE DEPTH IS ACTUALLY DECIDED. select.py's prompt gates on the same
    criteria, but it judges them while ranking a whole document, from one call, and
    nothing validates what it concluded. This reads the SAME question off the
    validated understanding — one section, checked against the section's own text,
    with each plan already quarantined if it did not hold up.

    It exists because of an arithmetic gap the window change opened. A 35-50s short
    is 87-125 spoken words across 4-5 beats. A section that supports two teaching
    steps, no example and no misconception has roughly two ideas in it, and the
    beats have to come from somewhere — so they come from restatement, which is the
    exact defect the 18-45s window was cut to fix.

    WHAT IT DOES NOT DO IS FAIL A SCRIPT. It grades the READING, so a failure means
    the topic was a bad choice, not that the writing went wrong. Acting on it is the
    caller's business: run.py prints it, and the length grader remains the hard gate
    on the script itself. Wiring it to drop a topic would silently shrink a deck for
    a judgement made from four booleans, which is more authority than it has earned.

    `section_text` is accepted and unused, so this fits the same registry signature
    as the other understanding graders. Deliberately unused: every claim in the
    reading has ALREADY been checked against the section by the graders that ran
    before it, so re-reading the text here would only invite this check to start
    forming its own second opinion about content — which is the duplication the
    whole reshuffle removed.

    Inconclusive, deliberately, when the sequence was quarantined: an empty
    teaching_sequence means the reading was thrown away, not that the section is
    thin, and understand() has already said so on its own line. Reporting thinness
    there would blame the section for the model's bad reading.
    """
    if understanding is None:
        return GraderResult("plan_depth", True, "no reading to judge",
                            {"conclusive": False})

    steps = list(getattr(understanding, "teaching_sequence", None) or [])
    if not steps:
        return GraderResult("plan_depth", True,
            "teaching sequence was dropped — depth cannot be judged from what is left",
            {"conclusive": False})

    material, made_of = plan_material(understanding)

    if material < MIN_PLAN_MATERIAL:
        return GraderResult("plan_depth", False,
            f"thin for a {MIN_SECONDS}-{MAX_SECONDS}s short: the plan holds "
            f"{material} thing(s) to say ({made_of}) and the script owes "
            f"{MIN_PLAN_MATERIAL} beats, each one idea and none allowed to restate "
            f"another. The spare beat has nothing to be about, so it would be filled "
            f"by restating — which check_beats_develop then rejects. This topic wants "
            f"a shorter format, or select's gate",
            {"material": material, "steps": len(steps), "conclusive": True})

    return GraderResult("plan_depth", True,
        f"{material} thing(s) to say for {MIN_PLAN_MATERIAL} beat(s): {made_of}",
        {"material": material, "steps": len(steps), "conclusive": True})


# ------------------------------------------------- topic/understanding reconciliation
#
# THE GAP THIS CLOSES. select.py ranks every topic's importance across the WHOLE
# document in one call, before any section has had a deep individual reading.
# understanding_for(section) — the one place a section's real "one thing it
# teaches" gets read out and validated against the section's own text — only
# runs later, in run.py's build_one, AFTER select.py's topic and question are
# already locked in. Nothing had ever compared the two: check_plan_depth above
# grades whether the READING found enough material, never whether the topic
# selected FROM it is the same topic the reading itself landed on. A topic can
# therefore pass importance, the yes/no filter, the duplicate-concept filter and
# check_plan_depth, and still be a question about the wrong idea in its own
# section — which is the product complaint that motivated this: "the
# questions... often do not focus on the main learning concept."
#
# DELIBERATELY BLUNT, and reusing _stems rather than inventing new fuzzy
# matching. This does not ask whether the topic is a GOOD reading of core_idea
# — that is a judgement call and belongs to a human or a paid grader — only
# whether the two are naming the same THING at all: does the topic's concept
# share even one content stem with the section's own core_idea? Two honest
# phrasings of the SAME idea always share at least one content word
# ("paging"/"fragmentation", "selector"/"specificity", "stack"/"push"), because
# both are naming the same mechanism. Zero stems in common means the topic and
# the validated reading are simply not about the same thing, however plausible
# either one reads on its own — see evals/cases.yaml's css_specificity case for
# a real instance: a topic about the !important flag, filed under the section
# that actually teaches how a specificity TIE is broken by document order.
def check_question_selection_source_title(selection: QuestionSelection,
                                          sections: list[Section]) -> GraderResult:
    """
    Does source_title actually name the section source_section_id points at?

    select.build_question_selections resolves source_title with a deterministic
    dict lookup against the parsed Section list — never from the LLM — so this is
    the check that would catch it drifting: a stale selection read back after the
    document was re-parsed with renumbered or retitled headings, or a QuestionSelection
    built by hand with the wrong title.
    """
    section_id = selection.topic.source_section_id
    section = next((s for s in sections if s.section_id == section_id), None)
    if section is None:
        return GraderResult("question_selection_source_title", False,
            f"source_section_id {section_id!r} does not match any parsed section",
            {"section_id": section_id})
    if selection.source_title != section.title:
        return GraderResult("question_selection_source_title", False,
            f"source_title {selection.source_title!r} does not match section "
            f"{section_id}'s actual title {section.title!r}",
            {"section_id": section_id, "expected": section.title,
             "got": selection.source_title})
    return GraderResult("question_selection_source_title", True,
        f"source_title matches section {section_id}'s title {section.title!r}",
        {"section_id": section_id})


def check_framing_source_matches_effective_question(workflow: QuestionWorkflow) -> GraderResult:
    """
    Does framing.source_question exactly equal the workflow's
    effective_question — the human-approved question at the moment of framing?

    skills.framing.frame_question sets source_question DETERMINISTICALLY from
    effective_question, never from the model's own output (see that module's
    _FramingOutput, which has no field for it) — this is the check that would
    catch a future regression breaking that guarantee: a refactor that let the
    model's text through, or a stale framing read back after the workflow's
    approved question changed again (a later regeneration, say) without being
    reframed.
    """
    if workflow.framing is None:
        return GraderResult("framing_source_matches_effective_question", True,
            "no framing on this workflow", {"skipped": True})
    expected = workflow.effective_question
    if workflow.framing.source_question != expected:
        return GraderResult("framing_source_matches_effective_question", False,
            f"framing.source_question {workflow.framing.source_question!r} does not "
            f"match the workflow's current effective_question {expected!r} — this "
            f"framing is stale, or was not built from this workflow",
            {"expected": expected, "got": workflow.framing.source_question})
    return GraderResult("framing_source_matches_effective_question", True,
        "framing.source_question matches effective_question", {"expected": expected})


def check_framing_stays_on_concept(framing: QuestionFraming, topic) -> GraderResult:
    """
    Does framing.teaching_question still share the topic's own concept, or did
    reframing quietly change the subject?

    THE SAME SHAPE OF CHECK AS check_topic_matches_understanding, one stage
    later: a prompt instruction ("stay on the same concept") is not a
    guarantee, so this is the free, deterministic backstop. Loose on purpose —
    stem overlap, not exact wording — because a real reframe is SUPPOSED to
    change the wording; it must only be caught when it changes the SUBJECT.
    """
    label = (topic.concept or topic.topic or "").strip()
    if not label:
        return GraderResult("framing_stays_on_concept", True,
            "topic has neither a concept nor a question to compare",
            {"conclusive": False})

    concept_stems = set(_stems(label))
    teaching_stems = set(_stems(framing.teaching_question))
    if not concept_stems or not teaching_stems:
        return GraderResult("framing_stays_on_concept", True,
            "too little text on one side to compare", {"conclusive": False})

    overlap = concept_stems & teaching_stems
    if not overlap:
        return GraderResult("framing_stays_on_concept", False,
            f"teaching_question {framing.teaching_question!r} shares no word with "
            f"the topic's own concept ({label!r}) — framing may have drifted onto "
            f"a different subject", {"conclusive": True})
    return GraderResult("framing_stays_on_concept", True,
        f"shares {', '.join(sorted(overlap)[:5])!r} with the topic's concept",
        {"overlap": sorted(overlap), "conclusive": True})


#: Phrases that justify `code` by the material's AVAILABILITY rather than by
#: the concept's NECESSITY — "the section has code" is a fact about the
#: reading, not a reason the concept itself needs code to be taught. See
#: check_teaching_approach_not_code_by_default, and
#: skills/teaching_approach.py's own "CODE IS NOT THE DEFAULT".
_CODE_AVAILABILITY_EXCUSES = (
    "contains code", "has code", "shows code", "shows a code", "is a code",
    "code example is available", "code is available", "code snippet is available",
    "programming course", "programming language course", "written in code",
    "code is present", "code is shown", "material contains", "section contains",
    "uses code",
)


def check_teaching_approach_not_code_by_default(approach: TeachingApproach) -> GraderResult:
    """
    Catches the specific failure Step 5 exists to prevent: `code` picked
    because the material HAPPENS to contain code, not because the CONCEPT
    needs code to be taught.

    DELIBERATELY NARROW. This cannot judge whether `code` is the right call —
    that needs a human, or a judge that has read the section — so it only
    catches the laziest version of the mistake: a rationale that justifies
    code by pointing at AVAILABILITY ("the section has code", "this is a
    programming course") instead of at NECESSITY (the concept IS a piece of
    syntax, or the section shows nothing but code has nothing to do with
    whether the rationale actually says why THIS concept needs it). Every
    check like this in the file is honest about that limit — see
    check_framing_stays_on_concept for the same shape of caveat one stage
    earlier.
    """
    if approach.primary != "code" and "code" not in approach.combined_with:
        return GraderResult("teaching_approach_not_code_by_default", True,
            "code was not selected", {"skipped": True})
    rationale = (approach.rationale or "").strip()
    if not rationale:
        return GraderResult("teaching_approach_not_code_by_default", False,
            "code was selected with no rationale to justify it", {"conclusive": True})
    lowered = rationale.lower()
    hit = next((p for p in _CODE_AVAILABILITY_EXCUSES if p in lowered), None)
    if hit:
        return GraderResult("teaching_approach_not_code_by_default", False,
            f"code was justified by availability ({hit!r}), not by the concept "
            f"needing code to teach it — rationale: {rationale!r}",
            {"excuse": hit})
    return GraderResult("teaching_approach_not_code_by_default", True,
        "code's rationale does not lean on a bare availability excuse")


#: Praise that could be said about any approach for any concept — the
#: generic-statement failure the brief explicitly calls out ("this approach
#: is engaging" is not a reason).
_GENERIC_APPROACH_RATIONALE_PHRASES = (
    "is engaging", "is more engaging", "is interesting", "is more interesting",
    "makes it fun", "makes it more fun", "keeps it interesting",
    "is visually appealing", "looks good", "is popular", "is a popular way",
    "is a great way", "is a good way to explain", "is the best way",
)


def check_teaching_approach_rationale_specific(approach: TeachingApproach) -> GraderResult:
    """
    Catches a rationale that praises the chosen approach in the abstract
    instead of explaining why THIS approach fits THIS concept.

    Same shape and same honesty as check_teaching_approach_not_code_by_default:
    cannot verify the rationale is actually RIGHT, only that it is not one of
    the specific generic dodges the brief names.
    """
    rationale = (approach.rationale or "").strip()
    if not rationale:
        return GraderResult("teaching_approach_rationale_specific", False,
            "no rationale was given", {"conclusive": True})
    lowered = rationale.lower()
    hit = next((p for p in _GENERIC_APPROACH_RATIONALE_PHRASES if p in lowered), None)
    if hit:
        return GraderResult("teaching_approach_rationale_specific", False,
            f"rationale leans on a generic claim ({hit!r}) instead of explaining "
            f"why this approach fits the concept: {rationale!r}", {"excuse": hit})
    return GraderResult("teaching_approach_rationale_specific", True,
        "rationale does not rely on a generic phrase")


def check_script_matches_teaching_approach(script: Script,
                                          approach: TeachingApproach) -> GraderResult:
    """
    Does the SCRIPT ITSELF — not the prompt that asked for it — agree with
    the teaching approach it was supposed to follow?

    CHECKED ON THE SCRIPT'S OWN TEXT, DELIBERATELY, not on whether
    skills.script.write_script's prompt happened to mention the approach.
    Asserting a phrase appeared in the PROMPT only proves the request was
    sent, never that it was honoured — this checks the OUTPUT, the same
    standard every other grader in this file already holds beats to.

    TWO DIRECTIONS, BOTH USING _is_code_quote — the same heuristic
    check_code_not_overused already uses one stage later, reused rather than
    reinvented:

      CODE APPROVED, NONE SHOWN. If `code` is the primary approach (or is
      combined in), at least one beat's source_quote should actually read as
      code. A script that never shows code did not follow a code-centric
      approval, whatever the prompt asked for.

      CODE NOT APPROVED, BUT DOMINATES ANYWAY. This is Step 8's own "CODE
      PROTECTION" requirement, made checkable: when `code` was NOT the
      approved device, MORE THAN HALF the answer beats citing code-like
      quotes is the failure — not any code citation at all, since the
      section may legitimately offer code as its only concrete evidence even
      under, say, conceptual_visual. One or two supporting code citations
      alongside prose ones is not the defect; code as the script's dominant
      evidence despite a non-code approval is.

    Silent (passes, `skipped`) when there are no student beats to check —
    nothing here to contradict an approach that was never exercised.
    """
    student_quotes = [b.source_quote for b in script.beats
                      if b.speaker == "student" and b.source_quote]
    if not student_quotes:
        return GraderResult("script_matches_teaching_approach", True,
            "no cited student beats to check", {"skipped": True})

    code_quotes = [q for q in student_quotes if _is_code_quote(q)]
    approved_code = approach.primary == "code" or "code" in approach.combined_with

    if approved_code and not code_quotes:
        return GraderResult("script_matches_teaching_approach", False,
            f"the approved teaching approach is {approach.primary!r} — code — but "
            f"no beat's source_quote reads as code, so the script never actually "
            f"shows the code the approach called for",
            {"approach": approach.primary})

    if not approved_code and len(code_quotes) > len(student_quotes) / 2:
        return GraderResult("script_matches_teaching_approach", False,
            f"the approved teaching approach is {approach.primary!r}, not code, "
            f"but {len(code_quotes)}/{len(student_quotes)} answer beat(s) cite "
            f"code as their evidence — code must not dominate a non-code approach",
            {"approach": approach.primary, "code_beats": len(code_quotes),
             "total_beats": len(student_quotes)})

    return GraderResult("script_matches_teaching_approach", True,
        f"consistent with the approved {approach.primary!r} approach",
        {"approach": approach.primary})


#: A backtick span, e.g. `foo()` — the one code signal _is_code_quote's own
#: heuristics (keywords, symbols, indentation) do not already cover, since a
#: single inline mention can be too short to trip those but still reads as
#: "look at this code" when it shows up in must_see/why_visual prose.
_BACKTICK_CODE = re.compile(r"`[^`]+`")


def _mentions_code(text: str) -> bool:
    """Does this beat-strategy PROSE (must_see / why_visual / concept), not a
    cited source quote, read as being ABOUT code — syntax, a snippet, a
    function body — rather than about the concept the code implements?

    Reuses _is_code_quote, the same heuristic check_code_not_overused and
    check_script_matches_teaching_approach already hold beats to, plus a
    backtick check for the short inline mentions ("call `insert()`") that
    heuristic is too strict to catch on its own.
    """
    return bool(text) and (_is_code_quote(text) or bool(_BACKTICK_CODE.search(text)))


def check_visual_strategy_matches_teaching_approach(
        strategy: VisualStrategy, approach: TeachingApproach) -> GraderResult:
    """
    Does the VISUAL STRATEGY ITSELF — not the prompt that asked for it — agree
    with the teaching approach it was supposed to visualise?

    Same standard, same reuse, as check_script_matches_teaching_approach one
    stage earlier: checked on the OUTPUT's own must_see/why_visual/concept
    text, never on whether strategy.py's prompt happened to mention the
    approach — a prompt asking for something proves the request was sent,
    never that it was honoured.

    TWO DIRECTIONS:

      CODE APPROVED, NONE SHOWN is not checked here — code being the approved
      approach does not obligate every beat to show code, only permits it;
      absence of code is never a defect on its own.

      CODE NOT APPROVED, BUT DOMINATES ANYWAY. When `code` is neither the
      primary approach nor combined in, MORE THAN HALF the beats reading as
      code-about (via _mentions_code) is the failure this exists to catch —
      the exact "code becomes the default visual" regression Step 10 was
      asked to guard against. One beat legitimately pointing at a symbol name
      is not the defect; code as the plan's dominant visual language despite
      a non-code approval is.

    Silent (passes, `skipped`) when there are no beats to check.
    """
    if not strategy.beats:
        return GraderResult("visual_strategy_matches_teaching_approach", True,
            "no beats to check", {"skipped": True})

    approved_code = approach.primary == "code" or "code" in approach.combined_with
    if approved_code:
        return GraderResult("visual_strategy_matches_teaching_approach", True,
            f"approved approach is {approach.primary!r} — code is permitted, "
            f"not required, on any given beat", {"approach": approach.primary})

    code_beats = [b for b in strategy.beats
                  if _mentions_code(b.must_see) or _mentions_code(b.why_visual)]
    if len(code_beats) > len(strategy.beats) / 2:
        return GraderResult("visual_strategy_matches_teaching_approach", False,
            f"the approved teaching approach is {approach.primary!r}, not code, "
            f"but {len(code_beats)}/{len(strategy.beats)} beat(s) describe a "
            f"code-centred visual — code must not be the default visual for a "
            f"concept that can be shown another way",
            {"approach": approach.primary, "code_beats": len(code_beats),
             "total_beats": len(strategy.beats)})

    return GraderResult("visual_strategy_matches_teaching_approach", True,
        f"consistent with the approved {approach.primary!r} approach",
        {"approach": approach.primary})


def check_visual_strategy_covers_every_beat(
        strategy: VisualStrategy, refs: list[str]) -> GraderResult:
    """
    Does every ref the script actually cites get its own visual decision —
    and is that decision a real one, not a placeholder?

    Two ways a beat can be visually absent: missing from strategy.beats
    entirely, or present with must_see/focus left blank (a strategy object
    that technically has an entry but never decided what to show). Both are
    the same failure from a viewer's seat — nothing appears — so both are
    checked here rather than only counting entries.

    `refs` is deliberately the caller's own list of the refs that matter
    (typically every ref a Script's beats cite) rather than something this
    function derives, so it says exactly what "every meaningful beat" means
    for the caller — mirroring how check_source_quotes takes the beats it
    should check rather than assuming every beat needs one.
    """
    if not refs:
        return GraderResult("visual_strategy_covers_every_beat", True,
            "no refs to check", {"skipped": True})

    by_ref = strategy.by_ref()
    missing = [r for r in refs if r not in by_ref]
    if missing:
        return GraderResult("visual_strategy_covers_every_beat", False,
            f"{len(missing)} ref(s) have no visual decision at all: {missing}",
            {"missing_refs": missing})

    empty = [r for r in refs if not by_ref[r].must_see.strip()
             or not by_ref[r].focus.strip()]
    if empty:
        return GraderResult("visual_strategy_covers_every_beat", False,
            f"{len(empty)} ref(s) have a strategy entry but no actual visual "
            f"decision (must_see or focus left blank): {empty}",
            {"empty_refs": empty})

    return GraderResult("visual_strategy_covers_every_beat", True,
        f"all {len(refs)} ref(s) have a visual decision", {"beats": len(refs)})


def check_topic_matches_understanding(topic, understanding) -> GraderResult:
    """
    Does the topic select.py handed us agree with what understanding_for(section)
    validated as THIS section's own central idea?

    `understanding` may be None or empty — the reading failed its own graders, or
    never ran — and that is inconclusive, not a failure, for the same reason
    check_plan_depth treats a quarantined reading as inconclusive rather than as
    evidence against the topic: there is nothing here to compare the topic to.

    Compared against `topic.concept` when set, falling back to `topic.topic` (the
    question itself) for a topics.json written before `concept` existed — see
    schema.Topic.concept, which is Optional for exactly that reason.
    """
    if understanding is None or not (understanding.core_idea or "").strip():
        return GraderResult("topic_matches_understanding", True,
            "no validated reading to compare against", {"conclusive": False})

    label = (topic.concept or topic.topic or "").strip()
    if not label:
        return GraderResult("topic_matches_understanding", True,
            "topic has neither a concept nor a question to compare",
            {"conclusive": False})

    topic_stems = set(_stems(label))
    idea_stems = set(_stems(understanding.core_idea))
    if not topic_stems or not idea_stems:
        return GraderResult("topic_matches_understanding", True,
            "too little text on one side to compare", {"conclusive": False})

    overlap = topic_stems & idea_stems
    if not overlap:
        return GraderResult("topic_matches_understanding", False,
            f"topic's concept {label!r} shares no word with this section's own "
            f"core idea ({understanding.core_idea!r}) — select.py picked a "
            f"different subject than understanding_for's validated reading of "
            f"the same section",
            {"topic_stems": sorted(topic_stems), "idea_stems": sorted(idea_stems),
             "conclusive": True})

    return GraderResult("topic_matches_understanding", True,
        f"shares {', '.join(sorted(overlap)[:5])!r} with the section's core idea",
        {"overlap": sorted(overlap), "conclusive": True})


def check_question_grounded(script: Script, source_text: str) -> GraderResult:
    """
    Is the interviewer's question answerable from this section, and claim-free?

    THE ONE BEAT NOTHING CHECKED. source_quote lives on student beats only, so beat
    1 — the first thing heard and the thing a viewer decides on — could say
    anything. Seen in real output: a section reading "The basic structure of any
    HTML document is as follows" produced "What's the REQUIRED basic structure...",
    and required is a claim the material never makes. Harmless there; the same hole
    lets a question promise a comparison, a reason or a guarantee the section
    cannot deliver, and then the answer beats have to either invent it or
    disappoint.

    Two rules, both already used elsewhere in this file:
      LITERALS   a value, code span or figure in the question must be in the
                 section. This is the same _literals/_in_section pair that catches
                 an invented example, applied to the beat that never had it.
      SUBJECT    enough of the question's content words come from the section that
                 it is asking about THIS page.

    Deliberately lenient on vocabulary. A question is written in a learner's words
    — "how does X work", "why do we need Y" — and demanding the section's phrasing
    would fail every well-written opening. MIN_OPENING_GROUNDING is the same floor
    check_opening_follows_hook uses, and it is set to catch a question about a
    different topic, nothing finer.

    Overlaps check_opening_follows_hook's grounding rule ON PURPOSE when a hook plan
    survived. That one is gated behind the plan and skips whenever the plan was
    absent or quarantined — which is exactly when an ungrounded question is most
    likely — so this runs unconditionally and the two agree where they meet.
    """
    if not script.beats:
        return GraderResult("question_grounded", True, "no beats", {"skipped": True})

    question = script.beats[0].line
    if not source_text:
        return GraderResult("question_grounded", True, "no source text — skipped",
                            {"skipped": True})

    for span in _literals(question):
        if not _in_section(span, source_text):
            return GraderResult("question_grounded", False,
                f"the question states {span!r}, which is not in the section. Beat 1 carries no "
                f"source_quote, so nothing else catches an invented value there — ask about "
                f"something the section actually shows.", {"invented": span})

    share = _grounded_share(question, source_text)
    if share < MIN_OPENING_GROUNDING:
        return GraderResult("question_grounded", False,
            f"only {share:.0%} of the question's content words are in the section — it asks "
            f"about something this section does not cover, so the answer will either drift or "
            f"disappoint. Ask the question THIS section answers.",
            {"grounding": share})

    return GraderResult("question_grounded", True,
        f"the question is answerable from this section ({share:.0%} shared vocabulary)",
        {"grounding": share})


SCRIPT_GRADERS = [check_timing, check_overlays, check_dialogue_shape, check_no_refusal,
                  check_beats_develop]

#: Unit graders that need only the unit.
UNIT_GRADERS   = [check_visuals_resolved, check_technical_beats_use_diagrams,
                  check_svg_quality, check_frames_are_visual, check_frames_develop,
                  check_frames_progress, check_frames_match_strategy,
                  check_physical_form_matches_template,
                  check_anchor_matches_structure,
                  check_state_item_transitions_visible,
                  check_state_pointer_moves_are_shown,
                  check_flow_traversal_progresses,
                  check_one_hero_per_frame, check_template_data_present,
                  check_samples_differ, check_code_frames_quote_source,
                  check_icons_are_pictures, check_diagram_matches_narration,
                  check_code_not_overused, check_generic_boxes_not_overused]

#: Unit graders that read the reading material as well as the unit.
_NEEDS_SOURCE = {check_diagram_matches_narration, check_code_frames_quote_source}


def run_unit_graders(unit: ShortUnit, source_text: str | None = None) -> list[GraderResult]:
    """
    Every unit grader, with the source handed to the ones that can use it.

    check_diagram_matches_narration takes the material so that a `code` frame
    copying the document's own snippet is not scored as drift — see
    literal_vocabulary. Everything else ignores the extra argument, and callers
    without a section (the eval harness) can leave it out.
    """
    return [g(unit, source_text) if g in _NEEDS_SOURCE else g(unit)
            for g in UNIT_GRADERS]


def run_script_graders(script: Script, source_text: str | None = None,
                       doc_text: str | None = None,
                       understanding=None) -> list[GraderResult]:
    """
    Every script grader, plus the ones that need something beyond the script.

    `understanding` is OPTIONAL and stays optional: a caller without one — the eval
    harness, smoke_test, audit.py — gets exactly the list it got before, and the
    sequence-alignment check is simply not among them. Passing one adds
    check_follows_teaching_sequence, which itself skips clean when the sequence is
    absent or was quarantined, so there are two independent ways for this to be a
    no-op and neither is an error.

    IT MUST BE THE SAME UNDERSTANDING ON EVERY ATTEMPT. The retry loops read the
    section once, before the loop (see skills/understanding.understanding_for), and
    hand that one object to both write_script and this function. Grading a retry
    against a freshly-read plan would move the target between attempts: the script
    would be rewritten to satisfy a sequence it was never shown.

    TIMING'S CEILING COMES FROM THE SAME `understanding`, NOT A NEW ARGUMENT. Every
    call site here already passes (or omits) `understanding` for
    check_follows_teaching_sequence's sake, so duration_budget rides along for
    free — a caller that has no understanding gets the ordinary 45s ceiling, one
    that does gets whatever duration_budget says its own reading earned. The
    per-beat word cap rides along on the SAME decision: a section that earned the
    wider duration window also earns MAX_ANSWER_WORDS_EXTENDED rather than
    MAX_ANSWER_WORDS, since both are the same "this material has more to it"
    signal — see MAX_ANSWER_WORDS_EXTENDED's own comment for why a wider window
    alone was not enough.
    """
    _, max_seconds = duration_budget(understanding)
    max_answer_words = MAX_ANSWER_WORDS_EXTENDED if max_seconds > MAX_SECONDS else MAX_ANSWER_WORDS
    results = [check_timing(script, max_seconds=max_seconds) if g is check_timing else
               check_dialogue_shape(script, max_answer_words=max_answer_words) if g is check_dialogue_shape else
               g(script)
               for g in SCRIPT_GRADERS]
    if source_text:
        results.append(check_source_quotes(script, source_text, doc_text=doc_text))
        results.append(check_answers_its_section(script, source_text))
        results.append(check_grounding(script, source_text, doc_text=doc_text))
        results.append(check_question_grounded(script, source_text))
    if understanding is not None:
        results.append(check_follows_teaching_sequence(script, understanding, source_text))
        results.append(check_uses_planned_example(script, understanding, source_text))
        results.append(check_handles_confusion(script, understanding, source_text))
        results.append(check_opening_follows_hook(script, understanding, source_text))
        results.append(check_reaches_objective(script, understanding))
        # LAST, and it reads `results` rather than recomputing them — it is an
        # orchestration of the verdicts above, so it has to come after all of them.
        results.append(check_learning_outcome(script, understanding, source_text, results))
    return results


def all_passed(results: list[GraderResult]) -> bool:
    return all(r.passed for r in results)
