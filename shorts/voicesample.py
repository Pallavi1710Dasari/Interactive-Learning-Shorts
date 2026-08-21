"""
Render the same short in several voices, side by side, and build a page to judge them.

    python -m shorts.voicesample                       # every candidate that works
    python -m shorts.voicesample --short <short_id>     # use a specific unit's script
    python -m shorts.voicesample --only google          # one provider

Writes output/voice-samples/<label>/audio.mp3 per candidate plus an index.html that
plays them one after another, and serves at /voice-samples/ while the server is up.

Why a separate module: choosing a voice is a listening decision, and the only honest
way to make it is the same words in each candidate, back to back. Nothing here writes
to a unit or changes what the pipeline uses — picking a winner means setting
TTS_PROVIDER and the voice ids in .env afterwards.
"""
import json
import shutil
from pathlib import Path

from .schema import Script, ShortUnit
from . import config, providers, tts

SAMPLES = config.OUTPUT_DIR / "voice-samples"

# The Google tiers worth comparing. Neural2 is the natural-sounding workhorse inside
# the free allowance; Chirp 3: HD is the newest and most lifelike, and rejects the
# pitch parameter, which providers.Google already handles. Two contrasting speakers
# each, because a single voice reading both halves is what we are trying to escape.
GOOGLE_CANDIDATES = [
    ("google-neural2", "en-US-Neural2-D", "en-US-Neural2-F"),
    ("google-neural2-alt", "en-US-Neural2-J", "en-US-Neural2-H"),
    ("google-studio", "en-US-Studio-Q", "en-US-Studio-O"),
    ("google-chirp3-hd", "en-US-Chirp3-HD-Charon", "en-US-Chirp3-HD-Aoede"),
    ("google-chirp3-hd-alt", "en-US-Chirp3-HD-Puck", "en-US-Chirp3-HD-Kore"),
    # Indian English, the properly-trained kind. B and D are male, A and C female.
    # Confirm the ids against your own project before trusting them — Google's
    # catalogue moves, and `python -m shorts.voicesample --list-google en-IN` prints
    # exactly what your key can see.
    ("google-en-in-neural2", "en-IN-Neural2-B", "en-IN-Neural2-A"),
    ("google-en-in-neural2-alt", "en-IN-Neural2-D", "en-IN-Neural2-C"),
    ("google-en-in-wavenet", "en-IN-Wavenet-B", "en-IN-Wavenet-A"),
]

# Kokoro ships 54 voices and rendering all of them would bury the page, so these are
# the American English pairs worth a listen. af_heart is the best-graded voice in the
# pack, which is why it leads and why it is the default student.
KOKORO_CANDIDATES = [
    ("kokoro-michael-heart", "am_michael", "af_heart"),
    ("kokoro-fenrir-bella", "am_fenrir", "af_bella"),
    ("kokoro-puck-nicole", "am_puck", "af_nicole"),
    ("kokoro-british", "bm_george", "bf_emma"),
    # Kokoro has no en-IN voices. These are its HINDI voice embeddings reading
    # English phonemes (KOKORO_LANG stays en-us), which is a hack rather than a
    # feature — the accent carries over from the voice, but the model was never
    # trained on Indian English, so judge it by ear before shipping it. Google's
    # real en-IN voices below are the supported way to get this.
    ("kokoro-hindi-omega-alpha", "hm_omega", "hf_alpha"),
    ("kokoro-hindi-psi-beta", "hm_psi", "hf_beta"),
    # Blends of the two pairs above, walking from mostly-American to mostly-Hindi.
    # A Kokoro voice is a style tensor, so the average of two is a real third voice
    # (see providers._blend). The point is the ratio: the Hindi end smears English
    # stops and the American end brings an accent, and somewhere between them is a
    # clear read with the colour you want. Which one that is, is an ear decision.
    ("kokoro-mix-25", "am_fenrir:0.75+hm_psi:0.25", "af_bella:0.75+hf_beta:0.25"),
    ("kokoro-mix-40", "am_fenrir:0.6+hm_psi:0.4", "af_bella:0.6+hf_beta:0.4"),
    ("kokoro-mix-50", "am_fenrir+hm_psi", "af_bella+hf_beta"),
    ("kokoro-mix-65", "am_fenrir:0.35+hm_psi:0.65", "af_bella:0.35+hf_beta:0.65"),
]

# Phonemisation is chosen per-render rather than per-voice, so these ride on
# KOKORO_LANG instead of the voice column. en-gb resolves several consonants
# differently from en-us and is worth trying against the muddy-"t" complaint —
# espeak has no en-IN, so this is the only other English phonology available.
KOKORO_LANG_VARIANTS = [
    ("kokoro-mix-40-engb", "en-gb", "am_fenrir:0.6+hm_psi:0.4", "af_bella:0.6+hf_beta:0.4"),
    ("kokoro-hindi-psi-beta-engb", "en-gb", "hm_psi", "hf_beta"),
]

#: label -> phonemisation language, for the handful of rows that override it.
KOKORO_LANG_FOR = {label: lang for label, lang, _, _ in KOKORO_LANG_VARIANTS}

PIPER_CANDIDATES = [
    ("piper-ryan-lessac", "en_US-ryan-medium", "en_US-lessac-medium"),
]

ELEVEN_CANDIDATES = [
    ("elevenlabs-default", "", ""),        # empty means "resolve from the library"
]


def candidates(only: str | None) -> list[tuple[str, str, str, str]]:
    """(label, provider name, interviewer voice, student voice)."""
    rows: list[tuple[str, str, str, str]] = []
    for label, a, b in ELEVEN_CANDIDATES:
        rows.append((label, "elevenlabs", a, b))
    for label, a, b in KOKORO_CANDIDATES:
        rows.append((label, "kokoro", a, b))
    for label, _lang, a, b in KOKORO_LANG_VARIANTS:
        rows.append((label, "kokoro", a, b))
    for label, a, b in GOOGLE_CANDIDATES:
        rows.append((label, "google", a, b))
    for label, a, b in PIPER_CANDIDATES:
        rows.append((label, "piper", a, b))
    if only:
        rows = [r for r in rows if r[1] == only or r[0].startswith(only)]
    return rows


def sample_script(short_id: str | None) -> Script:
    """
    The words every candidate says.

    A real unit by default, because a voice that sounds fine on a marketing sentence
    can fall apart on "the MMU raises a page fault trap". Falls back to a built-in
    script so this works on a fresh checkout with nothing in output/.
    """
    if short_id:
        path = config.OUTPUT_DIR / f"{short_id}.json"
        if not path.exists():
            raise SystemExit(f"no unit {short_id!r} in output/")
        unit = ShortUnit(**json.loads(path.read_text()))
        return Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)

    from . import feed
    for candidate in config.OUTPUT_DIR.glob("*.json"):
        if candidate.name in feed.SIDECARS:
            continue
        try:
            unit = ShortUnit(**json.loads(candidate.read_text()))
        except Exception:
            continue
        return Script(short_id=unit.short_id, question=unit.question, beats=unit.beats)

    return Script(short_id="sample", question="Why does a page fault happen?", beats=[
        {"speaker": "interviewer", "line": "Isn't a page fault just a crash?",
         "on_screen": "page fault = crash?", "visual_ref": "v1"},
        {"speaker": "student",
         "line": "No, it's a normal event. The MMU raises a trap and hands control to the OS.",
         "on_screen": "MMU raises a trap", "visual_ref": "v2"},
        {"speaker": "student",
         "line": "The OS finds the page, picks a free frame, and restarts the instruction.",
         "on_screen": "OS loads the page", "visual_ref": "v3"},
    ])


def render(script: Script, only: str | None = None, force: bool = False) -> list[dict]:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    for label, provider_name, interviewer, student in candidates(only):
        provider = providers.get(provider_name)
        ok, why = provider.available()
        if not ok:
            print(f"  - {label:22} skipped — {why}")
            results.append({"label": label, "provider": provider_name, "ok": False,
                            "reason": why})
            continue

        # Voice ids are pushed onto config because that is where the providers read
        # them from; restored afterwards so sampling never leaves the process
        # configured differently than it found it.
        saved = (config.VOICE_INTERVIEWER, config.VOICE_STUDENT,
                 config.GOOGLE_VOICE_INTERVIEWER, config.GOOGLE_VOICE_STUDENT,
                 config.PIPER_VOICE_INTERVIEWER, config.PIPER_VOICE_STUDENT,
                 config.KOKORO_VOICE_INTERVIEWER, config.KOKORO_VOICE_STUDENT,
                 config.KOKORO_LANG)
        if provider_name == "elevenlabs" and interviewer:
            config.VOICE_INTERVIEWER, config.VOICE_STUDENT = interviewer, student
        elif provider_name == "kokoro":
            config.KOKORO_VOICE_INTERVIEWER, config.KOKORO_VOICE_STUDENT = interviewer, student
            config.KOKORO_LANG = KOKORO_LANG_FOR.get(label, config.KOKORO_LANG)
        elif provider_name == "google":
            config.GOOGLE_VOICE_INTERVIEWER, config.GOOGLE_VOICE_STUDENT = interviewer, student
        elif provider_name == "piper":
            config.PIPER_VOICE_INTERVIEWER, config.PIPER_VOICE_STUDENT = interviewer, student

        out = SAMPLES / label
        try:
            if force and out.exists():
                shutil.rmtree(out)
            if (out / "audio.mp3").exists():
                print(f"  = {label:22} already rendered")
                audio = None
            else:
                print(f"  · {label:22} rendering…")
                audio = tts.synthesize(script, out_dir=out, provider=provider)
            results.append({
                "label": label, "provider": provider_name, "ok": True,
                "interviewer": interviewer or "(resolved)",
                "student": student or "(resolved)",
                "seconds": audio.duration_seconds if audio else None,
                "url": f"/voice-samples/{label}/audio.mp3",
            })
        except providers.AccountBlocked as e:
            print(f"  ! {label:22} blocked — {str(e)[:120]}")
            results.append({"label": label, "provider": provider_name, "ok": False,
                            "reason": str(e)[:300]})
        except Exception as e:
            print(f"  ! {label:22} {type(e).__name__}: {str(e)[:160]}")
            results.append({"label": label, "provider": provider_name, "ok": False,
                            "reason": f"{type(e).__name__}: {e}"[:300]})
        finally:
            (config.VOICE_INTERVIEWER, config.VOICE_STUDENT,
             config.GOOGLE_VOICE_INTERVIEWER, config.GOOGLE_VOICE_STUDENT,
             config.PIPER_VOICE_INTERVIEWER, config.PIPER_VOICE_STUDENT,
             config.KOKORO_VOICE_INTERVIEWER, config.KOKORO_VOICE_STUDENT,
             config.KOKORO_LANG) = saved

    (SAMPLES / "results.json").write_text(json.dumps(results, indent=2))
    return results


def build_page(script: Script, results: list[dict]) -> Path:
    """A plain page with one audio player per candidate and the words being read."""
    spoken = "".join(
        f'<p class="{b.speaker}"><b>{b.speaker}</b> {_esc(b.line)}</p>'
        for b in script.beats)

    rows = []
    for r in results:
        if r.get("ok"):
            meta = f'{_esc(r["interviewer"])} / {_esc(r["student"])}'
            secs = f' · {r["seconds"]}s' if r.get("seconds") else ""
            rows.append(
                f'<div class="row"><div class="lbl">{_esc(r["label"])}'
                f'<span>{meta}{secs}</span></div>'
                f'<audio controls preload="none" src="{r["url"]}"></audio></div>')
        else:
            rows.append(
                f'<div class="row bad"><div class="lbl">{_esc(r["label"])}'
                f'<span>{_esc(r.get("reason", "unavailable"))}</span></div></div>')

    html = f"""<!doctype html><meta charset="utf-8">
<title>Voice samples</title>
<style>
 body{{background:#0b1113;color:#e8f2ee;font:15px/1.55 Inter,system-ui,sans-serif;
       margin:0;padding:32px;max-width:860px}}
 h1{{font-size:22px;margin:0 0 4px}}
 .lede{{color:#8fa8a0;margin:0 0 26px}}
 .row{{display:flex;align-items:center;gap:16px;padding:13px 16px;margin-bottom:10px;
       background:#111a1c;border:1px solid #1e2c2e;border-radius:12px}}
 .row.bad{{opacity:.55}}
 .lbl{{flex:0 0 260px;font-weight:650}}
 .lbl span{{display:block;font-weight:400;font-size:12px;color:#7f948e;
            word-break:break-word}}
 audio{{flex:1;height:34px}}
 .script{{margin-top:30px;padding:18px 20px;background:#0f1719;border-radius:12px;
          border:1px solid #1e2c2e}}
 .script p{{margin:0 0 9px}} .script b{{color:#2fd39b;font-size:11px;
   text-transform:uppercase;letter-spacing:.08em;margin-right:8px}}
 .interviewer b{{color:#7fb2e8}}
</style>
<h1>Voice samples</h1>
<p class="lede">The same short in every candidate voice. Listen back to back — that is
the only way to choose. Nothing here is wired into the pipeline; set
<code>TTS_PROVIDER</code> and the voice ids in <code>.env</code> once you have picked.</p>
{''.join(rows)}
<div class="script"><b style="color:#8fa8a0">the words</b>{spoken}</div>
"""
    page = SAMPLES / "index.html"
    page.write_text(html, encoding="utf-8")
    return page


def _esc(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--short", help="use this unit's script (default: the first found)")
    ap.add_argument("--only", help="one provider or label prefix")
    ap.add_argument("--force", action="store_true", help="re-render existing samples")
    ap.add_argument("--list-google", metavar="PREFIX", nargs="?", const="",
                    help="print the Google voices your key can see, e.g. en-IN")
    args = ap.parse_args()

    # Google's catalogue moves and a wrong id is a hard 400 per beat, so the ids in
    # GOOGLE_CANDIDATES are worth checking against the account before a long render.
    if args.list_google is not None:
        google = providers.get("google")
        ok, why = google.available()
        if not ok:
            raise SystemExit(f"google: {why}")
        for row in google.voices(prefer=args.list_google or None):
            print(row)
        return

    script = sample_script(args.short)
    print(f"sampling with {script.short_id!r} ({len(script.beats)} beats)\n")
    results = render(script, only=args.only, force=args.force)
    page = build_page(script, results)

    ok = [r for r in results if r.get("ok")]
    print(f"\n{len(ok)}/{len(results)} rendered -> {page}")
    print("open http://localhost:8000/voice-samples/ with the server running")


if __name__ == "__main__":
    main()
