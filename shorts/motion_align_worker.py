"""
A resident FORCED-ALIGNMENT process (RESTYLE_TO_MOTION_REELS.md phase 3),
spoken to over stdin/stdout like shorts/chatterbox_worker.py, and run in the
same venv-chatterbox (it needs torch and torchaudio, which the project's own
venv does not carry):

    venv-chatterbox/bin/python -m shorts.motion_align_worker

Free and local: torchaudio's wav2vec2 English CTC model
(WAV2VEC2_ASR_BASE_960H, downloaded once by torchaudio, ~360 MB) and
torchaudio.functional.forced_align. Given audio and the words that were
SAID — we synthesized them, so the transcript is exact — it returns where
each word starts and ends in the audio. That is forced alignment to a known
transcript, not transcription: nothing is guessed about WHAT was said.

THE PROTOCOL, one JSON object per line:
    <- {"wav": "/path/clip.wav", "words": ["use", "State", "of", "zero"]}
    -> {"ok": true, "times": [[0.12, 0.31], [0.31, 0.74], null, ...]}
    -> {"ok": false, "error": "..."}
A word with no letters once normalised gets null and is interpolated by the
caller. The first line out is {"ok": true, "ready": true} once the model is
loaded.
"""
import json
import re
import sys

_ONES = ["ZERO", "ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN",
         "ELEVEN", "TWELVE", "THIRTEEN", "FOURTEEN", "FIFTEEN", "SIXTEEN", "SEVENTEEN",
         "EIGHTEEN", "NINETEEN"]
_TENS = ["", "", "TWENTY", "THIRTY", "FORTY", "FIFTY", "SIXTY", "SEVENTY", "EIGHTY", "NINETY"]


def _int_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + "HUNDRED" + ("" if n % 100 == 0 else _int_words(n % 100))
    if n < 1_000_000:
        return _int_words(n // 1000) + "THOUSAND" + ("" if n % 1000 == 0 else _int_words(n % 1000))
    return "".join(_ONES[int(d)] for d in str(n))


def normalise(word: str) -> str:
    """A spoken word as the model's letters (A-Z and '): digits read out,
    everything else dropped. "1.2" -> ONEPOINTTWO, "re-render" -> RERENDER."""
    def num(m):
        whole, _, frac = m.group(0).replace(",", "").partition(".")
        out = _int_words(int(whole)) if whole else ""
        if frac:
            out += "POINT" + "".join(_ONES[int(d)] for d in frac)
        return out
    w = re.sub(r"\d[\d,]*(?:\.\d+)?", num, word)
    return re.sub(r"[^A-Z']", "", w.upper())


def main() -> int:
    try:
        import torch
        import torchaudio
        import torchaudio.functional as F
    except Exception as e:
        print(json.dumps({"ok": False, "fatal": True, "error": f"torchaudio not importable: {e}"}),
              flush=True)
        return 1
    try:
        bundle = torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
        model = bundle.get_model().eval()
        labels = bundle.get_labels()
    except Exception as e:
        print(json.dumps({"ok": False, "fatal": True, "error": f"could not load wav2vec2: {e}"}),
              flush=True)
        return 1
    index = {c: i for i, c in enumerate(labels)}
    sep = index["|"]
    print(json.dumps({"ok": True, "ready": True, "model": "WAV2VEC2_ASR_BASE_960H"}), flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("cmd") == "ping":
                print(json.dumps({"ok": True, "ready": True}), flush=True)
                continue
            wave, rate = torchaudio.load(req["wav"])
            wave = wave.mean(dim=0, keepdim=True)
            if rate != bundle.sample_rate:
                wave = F.resample(wave, rate, bundle.sample_rate)
            units = [normalise(w) for w in req["words"]]
            keep = [i for i, u in enumerate(units) if u and all(c in index for c in u)]
            if not keep:
                print(json.dumps({"ok": True, "times": [None] * len(units)}), flush=True)
                continue
            tokens: list[int] = []
            for k, i in enumerate(keep):
                if k:
                    tokens.append(sep)
                tokens += [index[c] for c in units[i]]
            with torch.inference_mode():
                emission, _ = model(wave)
                emission = torch.log_softmax(emission, dim=-1)
            targets = torch.tensor([tokens], dtype=torch.int32)
            aligned, scores = F.forced_align(emission, targets, blank=0)
            spans = F.merge_tokens(aligned[0], scores[0].exp())
            ratio = wave.size(1) / emission.size(1) / bundle.sample_rate
            times: list = [None] * len(units)
            pos = 0
            for k, i in enumerate(keep):
                if k:
                    pos += 1                       # the "|" between words
                n = len(units[i])
                first, last = spans[pos], spans[pos + n - 1]
                times[i] = [round(first.start * ratio, 3), round(last.end * ratio, 3)]
                pos += n
            print(json.dumps({"ok": True, "times": times}), flush=True)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
