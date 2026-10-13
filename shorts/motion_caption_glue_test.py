"""
Captions glued a code symbol to the word before it: "The `=` sign" was shown
as "The= sign" and "The `[ ]` on the right" as "The[] on the right"
(motion_timeline.caption_words joined every word without letters). A symbol
is now a word of its own, and the spoken word that names it ("brackets" for
`[ ]`) is its time — before, the caption's later words each took the time of
the spoken word before theirs ("on" lit on "brackets").

    SHORTS_STUB=1 python -m shorts.motion_caption_glue_test
"""
import os
if os.environ.get("SHORTS_STUB", "").strip().lower() not in ("1", "true", "yes"):
    raise SystemExit("run this with SHORTS_STUB=1 — it never spends real API calls")

from pathlib import Path

from shorts.testing import isolate_output
isolate_output()

from shorts import config, motion_voice
from shorts.checks import _motion_key
from shorts.motion_timeline import caption_words
from shorts.schema import CaptionChunk, MotionScript, MotionShot

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "evals/fixtures/motion"


def _shot(speech: str, *captions: str) -> MotionShot:
    return MotionShot(id="s01", beat="code_map", speech=speech,
                      captions=[CaptionChunk(text=c, speaker=None) for c in captions])


def test_symbols_are_words_of_their_own():
    assert [w for w, _ in caption_words("The `=` sign ties the tag.")] == ["The", "`=`", "sign", "ties", "the", "tag."]
    assert [w for w, _ in caption_words("The `[ ]` on the right")] == ["The", "`[", "]`", "on", "the", "right"]
    # sentence punctuation the tags split off still joins its word
    assert [w for w, _ in caption_words("It is <b>useState</b>.")] == ["It", "is", "useState."]
    assert [w for w, _ in caption_words("one <b>tag</b>, two")] == ["one", "tag,", "two"]


def test_a_symbol_takes_the_spoken_word_that_names_it():
    shot = _shot("The brackets on the right build the list.", "The `[ ]` on the right build the list.")
    assert motion_voice.shown_to_spoken(shot) == [[(0, 1), (1, 2), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8)]]
    # an operator the narration says as a word keeps its own word
    shot = _shot("The equals sign ties it.", "The `=` sign ties it.")
    assert motion_voice.shown_to_spoken(shot) == [[(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]]
    # a symbol nobody says takes no spoken word
    shot = _shot("Call it with x.", "Call `it()` with x.")
    assert motion_voice.shown_to_spoken(shot) == [[(0, 1), (1, 2), (2, 3), (3, 4)]]


def test_every_fixture_caption_lines_up_with_its_speech():
    """Every shown word of every golden script stands for spoken words that
    spell it (the real reel's s07 had two that did not)."""
    bad, total = [], 0
    for f in sorted(FIX.glob("*.json")):
        try:
            script = MotionScript.model_validate_json(f.read_text())
        except Exception:
            continue
        for sh in script.shots:
            for cap, said, rng in zip(sh.captions, motion_voice.caption_speech(sh), motion_voice.shown_to_spoken(sh)):
                spoken = said.split()
                for (w, _), (a, b) in zip(caption_words(cap.text), rng):
                    k = _motion_key(w)
                    total += 1
                    got = "".join(_motion_key(x) for x in spoken[a:b])
                    if k and got != k and got.replace("of", "") != k.replace("of", ""):
                        bad.append((f.name, sh.id, w, spoken[a:b]))
    assert total > 2000 and not bad, bad[:10]


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"running {len(tests)} caption glue tests")
    for t in tests:
        print(f"- {t.__name__}")
        t()
    assert str(config.OUTPUT_DIR) != str(ROOT / "output")
    print("\nALL CAPTION GLUE TESTS PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
