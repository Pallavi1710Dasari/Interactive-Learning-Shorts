"""
Turning a written beat into text a TTS engine reads like a person.

This is the Python half of web/src/speech.ts, and it keeps the same clause-based
splitting. What changes is what the splitting is FOR. In the browser, each clause
became its own utterance, because the Web Speech API gives you no other way to
control phrasing. ElevenLabs infers prosody from the text itself, so fragmenting
the audio there would be worse, not better — you would get four separately-intoned
pieces glued together instead of one continuous, breathing sentence.

So the clause boundaries are used to place PUNCTUATION instead. A comma at a clause
boundary is a short breath; an ellipsis is a beat of thought before a contrast or a
conclusion. One request per beat, phrased from the inside.

Notation is spoken out for the same reason it is in the browser: "2^3" read
literally is "two caret three", which is neither what the diagram shows nor what a
teacher would say.
"""
import re

# Written notation -> what a person would say. Longest patterns first.
SPOKEN: list[tuple[str, str]] = [
    (r"(\d+)\s*\^\s*(\d+)", r"\1 to the power of \2"),
    (r"\b2\s*\^\s*n\b", "two to the power of n"),
    (r"(\d+)\s*\*\s*(\d+)", r"\1 times \2"),
    (r"\s*->\s*", " leads to "),
    (r"\s*=>\s*", " gives "),
    (r"\s*!=\s*", " is not equal to "),
    (r"\s*>=\s*", " is at least "),
    (r"\s*<=\s*", " is at most "),
    (r"\s*=\s*", " equals "),
    (r"\be\.g\.\s*", "for example, "),
    (r"\bi\.e\.\s*", "that is, "),
    (r"\betc\.", "and so on."),
    (r"\bvs\.?\s", "versus "),
    (r"\s*&\s*", " and "),
]

# Words that open a clause worth breathing before. Kept in step with speech.ts.
#
# Multi-word connectives come FIRST, because the alternation is ordered and a bare
# "though" would otherwise match inside "even though" — splitting the phrase as
# "different things, even, though ..." and putting a breath in the middle of a
# conjunction. Bare "though" is deliberately absent: on its own it is nearly always
# part of "even though" or trailing ("..., though"), and neither wants a break.
_CONNECTIVE = r"(?:even though|and then|but|so|because|which|instead|while|whereas)"

MAX_PHRASE_WORDS = 12
MIN_PHRASE_WORDS = 4

# A conclusion or a contrast lands better after a moment of thought. ElevenLabs
# reads "..." as exactly that pause.
_THINKING = re.compile(rf"^(so|but|instead|and so|which means)\b", re.I)


def _strip_markup(text: str) -> str:
    """Backticks, asterisks and angle-bracket tags are for the eye, not the ear."""
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]*)\*", r"\1", text)
    return text


def for_speech(text: str) -> str:
    """Expand notation and drop markup, leaving words a voice can read."""
    out = _strip_markup(text)
    for pattern, replacement in SPOKEN:
        out = re.sub(pattern, replacement, out, flags=re.I)
    # An em dash is a spoken pause. Left as a dash the engine runs through it.
    out = re.sub(r"\s*[—–]\s*", ", ", out)
    return re.sub(r"\s+", " ", out).strip()


def phrases(line: str) -> list[str]:
    """
    Split one spoken line into clause-length phrases.

    Sentence ends first, then clause boundaries, and only over-long leftovers are
    broken at a comma — splitting every comma turns the line into a staccato list,
    which trades one unnatural reading for another.
    """
    spoken = for_speech(line)
    sentences = re.findall(r"[^.!?]+[.!?]*", spoken) or [spoken]

    out: list[str] = []
    for sentence in sentences:
        s = sentence.strip()
        if not s:
            continue
        if _words(s) <= MAX_PHRASE_WORDS:
            out.append(s)
            continue
        parts = [p.strip() for p in
                 re.split(rf",\s*|\s+(?={_CONNECTIVE}\b)", s, flags=re.I) if p.strip()]
        for part in parts:
            if out and _words(part) < MIN_PHRASE_WORDS:
                out[-1] = f"{out[-1]}, {part}"
            else:
                out.append(part)
    return out


def conversational(line: str) -> str:
    """
    One beat, repunctuated so ElevenLabs phrases it the way a person would.

    Rebuilt from the clause phrases: each is joined with a comma, and a phrase that
    opens on a conclusion or a contrast gets an ellipsis before it instead — the
    small hesitation before "so..." or "but..." is most of what makes a read sound
    like thinking rather than reciting.

    Punctuation is only ever ATTACHED to a word, never inserted as a free-standing
    token. Beat boundaries come from tts.py's own per-beat timings now, but the word
    timings are still zipped against the spoken text, and a stray " ... " token
    would shift every word after it by one.
    """
    parts = phrases(line)
    if not parts:
        return for_speech(line)

    out = parts[0].rstrip(" ,")
    for part in parts[1:]:
        nxt = part.lstrip(" ,")
        if _ends_sentence(out):
            joiner = " "
        elif _THINKING.match(nxt):
            joiner = "... "
        else:
            joiner = ", "
        out = f"{out}{joiner}{nxt}".rstrip(" ,")

    if not _ends_sentence(out):
        out += "."
    return re.sub(r"\s+", " ", out).strip()


def _ends_sentence(text: str) -> bool:
    return bool(re.search(r"[.!?]$", text.strip()))


def _words(text: str) -> int:
    return len(text.strip().split())
