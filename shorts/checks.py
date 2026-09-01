"""
Code graders. Deterministic, free, instant. These run BEFORE any paid step.

Every grader takes an object and returns a GraderResult. Never raise — a grader
that crashes tells you nothing; a grader that returns passed=False with a reason
tells you what to fix.
"""
import html, re
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
    )) | {_stem(w) for w in _DIAGRAM_SCAFFOLD} | literal_vocabulary(source_text or "")
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


def check_frames_vary_template(unit: ShortUnit) -> GraderResult:
    """
    A short may not be built from a single template.

    THE COMPLAINT THIS EXISTS FOR: "for a theory topic it giving the same visual for
    all the points so it looks not good and repetitive". Measured across the 32 units
    in output/, SIX were one template end to end — four `code` panels in a row, four
    `table` frames in a row, three `icons` rows in a row — and every one of them
    passed every design grader there was.

    WHY THIS IS A SEPARATE GRADER AND NOT PART OF frames_develop. That one asks
    whether each transition changes the picture, which is a question about PAIRS. A
    short can pass it pair by pair and still be four variations on one layout, because
    "the table gained a row" is a change and four tables is still four tables. This
    asks the question about the WHOLE short, which is the level the complaint lives
    at: the viewer is not comparing beat 3 to beat 2, they are watching one shape for
    fifteen seconds.

    Deliberately the loosest rule that catches the complaint: TWO distinct templates
    is enough to pass. The point is not to force variety for its own sake — a short
    that genuinely wants two code frames and a diagram should pass, and does. It is
    to reject the degenerate case where the model picked one layout and never
    reconsidered. `layout.py` ships ten templates; `icons` alone was 34% of every
    frame drawn, and `preview` and `stat` were under 3% each.

    Held to shorts with three or more distinct frames. Two frames of the same
    template is a held picture, which frames_develop already reasons about properly.
    """
    refs: list[str] = []
    for beat in unit.beats:
        if not refs or refs[-1] != beat.visual_ref:
            refs.append(beat.visual_ref)
    templates = [unit.visuals[r].frame.template for r in refs
                 if r in unit.visuals and unit.visuals[r].frame is not None]
    if len(templates) < 3:
        return GraderResult("frames_vary_template", True,
                            f"{len(templates)} frame(s) — too few to call repetitive")
    distinct = sorted(set(templates))
    if len(distinct) < 2:
        return GraderResult(
            "frames_vary_template", False,
            f"all {len(templates)} frames use the same template ({distinct[0]}) — "
            f"the short is one layout repeated, which reads as the same visual on "
            f"every beat. Give at least one beat a different kind of picture.")
    return GraderResult("frames_vary_template", True,
                        f"{len(distinct)} templates across {len(templates)} frames "
                        f"({', '.join(distinct)})")


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
        drawn = set(_stems(" ".join(labels)))
        for line in spoken.get(ref, []):
            said = set(_stems(line))
            if len(said) < 4:
                continue
            share = len(said & drawn) / len(said)
            if share > MAX_NARRATION_ECHO:
                echoes.append(f"{ref}: {share:.0%} of the spoken line is printed in the "
                              f"frame — draw the subject, not the sentence")
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
    if roles_only:
        return GraderResult("frames_develop", False,
                            f"{roles_only} of {total} frame transition(s) only move the "
                            f"accent on the same picture — the viewer sees one static "
                            f"slide with a highlight sliding over it")
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


def _roles(frame) -> tuple:
    """Which element is emphasised, across every template that has elements."""
    return (
        tuple(c.role for c in frame.cells + frame.left + frame.right
              + frame.parts + frame.steps + frame.code_lines),
        tuple(r.role for r in frame.rows),
        tuple((p.role, tuple(i.role for i in p.items)) for p in frame.panels),
        tuple(g.role for g in frame.glyphs),
        tuple(s.role for s in frame.samples),
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
    "process":       {"flow", "icons", "code", "cause_effect"},
    # Rule 7: BOTH STATES AT ONCE. A `bar` or a `stat` shows one.
    "comparison":    {"compare", "preview", "table", "code"},
    # Rule 8: the thing that moves, where it starts, where it lands.
    "data_movement": {"icons", "mapping", "flow", "cause_effect"},
    # Rule 9: spatial hierarchy. A row of peers is the thing being rejected.
    "hierarchy":     {"hierarchy", "split", "code"},
    # Rule 10: cause and effect both on screen, direction drawn.
    "cause_effect":  {"cause_effect", "flow", "compare", "code"},
    "structure":     {"split", "bar", "table", "mapping", "code", "hierarchy", "icons"},
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
        ]
        for i, panel in enumerate(frame.panels, 1):
            collections.append((f"panel {i} items", [c.role for c in panel.items]))

        populated = [(n, roles) for n, roles in collections if roles]
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

#: Unit graders that need only the unit.
UNIT_GRADERS   = [check_visuals_resolved, check_technical_beats_use_diagrams,
                  check_svg_quality, check_frames_are_visual, check_frames_develop,
                  check_frames_vary_template, check_frames_match_strategy,
                  check_one_hero_per_frame,
                  check_samples_differ, check_code_frames_quote_source,
                  check_icons_are_pictures, check_diagram_matches_narration]

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
                       doc_text: str | None = None) -> list[GraderResult]:
    results = [g(script) for g in SCRIPT_GRADERS]
    if source_text:
        results.append(check_source_quotes(script, source_text, doc_text=doc_text))
        results.append(check_answers_its_section(script, source_text))
        results.append(check_grounding(script, source_text, doc_text=doc_text))
    return results


def all_passed(results: list[GraderResult]) -> bool:
    return all(r.passed for r in results)
