"""
Text to speech with word-level timestamps.

Word timings are NOT optional. They are how the video knows when to swap the
on-screen text. Verify your provider's current endpoint in their docs before
trusting this module — TTS APIs change often.

This uses ElevenLabs' with-timestamps endpoint. Swap the implementation freely;
keep the synthesize() signature so nothing downstream changes.
"""
import base64, json
from pathlib import Path
import requests

from .schema import Script, Audio, WordTiming
from . import config

API = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"


def _synth_one(text: str, voice_id: str) -> tuple[bytes, list[dict]]:
    r = requests.post(
        API.format(voice=voice_id),
        headers={"xi-api-key": config.ELEVENLABS_API_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_turbo_v2_5"},
        timeout=120,
    )
    r.raise_for_status()
    data = r.json()
    audio = base64.b64decode(data["audio_base64"])
    return audio, data.get("alignment", {})


def _chars_to_words(text: str, alignment: dict, offset: float) -> tuple[list[WordTiming], float]:
    """ElevenLabs returns per-character timings. Collapse them into words."""
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])
    words, cur, cur_start = [], "", None

    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append(WordTiming(word=cur, start=cur_start + offset, end=e + offset))
                cur, cur_start = "", None
        else:
            if not cur:
                cur_start = s
            cur += ch
    if cur:
        words.append(WordTiming(word=cur, start=cur_start + offset, end=ends[-1] + offset))

    total = (ends[-1] if ends else 0.0)
    return words, total


def synthesize(script: Script, out_dir: Path | None = None, gap: float = 0.35) -> Audio:
    """
    Render every beat with the right voice, concatenate, return one Audio with
    timings that are absolute across the whole short.
    """
    out_dir = out_dir or config.OUTPUT_DIR / script.short_id
    out_dir.mkdir(parents=True, exist_ok=True)

    voices = {"interviewer": config.VOICE_INTERVIEWER, "student": config.VOICE_STUDENT}
    parts, all_words, cursor = [], [], 0.0

    for i, beat in enumerate(script.beats):
        audio_bytes, alignment = _synth_one(beat.line, voices[beat.speaker])
        chunk = out_dir / f"beat_{i:02d}.mp3"
        chunk.write_bytes(audio_bytes)
        words, dur = _chars_to_words(beat.line, alignment, cursor)
        all_words += words
        parts.append(str(chunk))
        cursor += dur + gap

    combined = out_dir / "audio.mp3"
    _concat(parts, combined, gap)
    (out_dir / "timings.json").write_text(
        json.dumps([w.model_dump() for w in all_words], indent=2))

    return Audio(file=str(combined), duration_seconds=round(cursor, 2), word_timings=all_words)


def _concat(parts: list[str], out: Path, gap: float):
    """Concatenate with silence between beats. Requires ffmpeg on PATH."""
    import subprocess, tempfile
    silence = out.parent / "_gap.mp3"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
                    f"anullsrc=r=44100:cl=mono","-t",str(gap),str(silence)],
                   check=True, capture_output=True)
    seq = []
    for p in parts:
        seq += [p, str(silence)]
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        for p in seq[:-1]:
            f.write(f"file '{p}'\n")
        listfile = f.name
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",listfile,
                    "-c","copy",str(out)], check=True, capture_output=True)
