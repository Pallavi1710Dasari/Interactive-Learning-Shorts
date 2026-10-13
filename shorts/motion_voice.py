"""
Motion narration (RESTYLE_TO_MOTION_REELS.md phase 3). REEL_STYLE=motion only.

ONE CLIP PER CAPTION. A caption is one spoken sentence and, in a two-speaker
reel, has one speaker — so a caption is the unit that gets a voice. Each is
synthesized by Chatterbox (local, free) from its speaker's VOICE SLOT
(shorts/motion_identities.yaml, voices belong to identities): the narrator's
slot for a one-narrator reel; for a two-speaker one, the host's slot and the
shared character voice of the reel's language. Two speakers, two slots, two
voices.

A slot's reference clip is voices/motion/<slot>.wav. Until those are
recorded, a slot falls back to the clips the project already has — the host
and the narrator to the interviewer clip, a language character to the
student clip (Chatterbox's own voice settings) — and every fallback is
logged and recorded in the manifest, so a reel never silently speaks in a
voice nobody chose.

Every clip is recorded with the local Chatterbox voice — free, so a stub-mode
test reel speaks too. Only with MOTION_VOICE=silent (the automated tests) is
each clip silence of the estimated length.

The clips are then laid on the reel's clock (motion_timeline.shot_timings,
with each caption's MEASURED length) and mixed to one track,
output/<short_id>/audio/reel.wav, normalised to -14 LUFS.
"""
import hashlib
import io
import json
import subprocess
import wave
from pathlib import Path

import numpy as np

from . import config
from .schema import MOTION_WORDS_PER_SECOND, MotionScript, MotionShot, motion_plain_text

SAMPLE_RATE = 24000
TARGET_LUFS = -14.0
CACHE_DIR = config.OUTPUT_DIR / ".motion_audio_cache"
SLOT_DIR = config.VOICE_DIR / "motion"


# ============================================================ who speaks what

def speaker_slots(script: MotionScript) -> dict[str | None, str]:
    """caption speaker role (None for the narrator) -> voice slot."""
    from .motion_identities import narrator_slot
    slots: dict[str | None, str] = {None: narrator_slot()}
    for sp in script.speakers:
        slots[sp.role] = sp.voice_slot
    return slots


#: The voices a reviewer can pick per speaker (the Characters step): the
#: project's recordings in voices/ (interviewer, student) and any
#: voices/motion/<name>.wav. id -> (path, label).
AUDIO_SUFFIXES = (".wav", ".ogg", ".webm", ".mp3", ".m4a", ".flac")


def available_voices() -> dict[str, tuple[str, str]]:
    """Every voice clip a speaker can use: voices/interviewer.* and
    voices/student.* (what the "your voice" panel records or keeps, in any
    audio format) and voices/motion/<name>.*. id -> (path, label)."""
    root = SLOT_DIR.parent
    out: dict[str, tuple[str, str]] = {}
    names = {"interviewer": "Voice 1 · interviewer clip", "student": "Voice 2 · student clip"}
    files = [f for d in (root, SLOT_DIR) for f in sorted(d.glob("*")) if f.suffix.lower() in AUDIO_SUFFIXES]
    # the newest file wins when the panel kept a new recording in another format
    for f in sorted(files, key=lambda f: f.stat().st_mtime, reverse=True):
        vid = f.stem
        if vid not in out:
            out[vid] = (str(f), names.get(vid, vid.replace("_", " ").title()))
    return dict(sorted(out.items()))


def slot_reference(slot: str) -> tuple[str | None, str]:
    """The reference clip for a voice slot, and where it came from:
    voices/motion/<slot>.wav when it exists, else the project's existing
    Chatterbox clips (host and narrator: the interviewer clip; a language
    character: the student clip), else none (Chatterbox's built-in voice)."""
    own = SLOT_DIR / f"{slot}.wav"
    if own.exists():
        return str(own), "slot"
    try:
        from .providers import _REGISTRY
        clips = _REGISTRY["chatterbox"].resolve()
    except Exception:
        clips = {}
    from .motion_identities import registry
    voices = registry().voices
    asking = slot in (voices["narrator"], voices["host"])
    fallback = clips.get("interviewer" if asking else "student")
    if fallback and Path(fallback).exists():
        return fallback, f"fallback: {'interviewer' if asking else 'student'} clip"
    return None, "fallback: chatterbox built-in voice"


def caption_speech(shot: MotionShot) -> list[str]:
    """Each caption's SPOKEN words — the slice of shot.speech it shows. The
    captions are the speech word for word, except a code token may stand
    for several spoken words (`useState` <- "use State"), so the speech is
    consumed caption token by caption token the way
    checks.check_motion_captions_match_speech matches them."""
    from .checks import _is_code_token, _motion_key, _motion_words
    spoken = shot.speech.split()
    keys = [_motion_key(w) for w in spoken]
    out: list[str] = []
    i = 0
    for c in shot.captions:
        start = i
        for tok in _motion_words(c.text):
            key = _motion_key(tok)
            if not key:
                continue
            code = _is_code_token(tok)
            acc = ""
            while i < len(spoken) and len(acc) < len(key):
                w = keys[i]
                i += 1
                if code and w == "of" and acc and not key[len(acc):].startswith("of"):
                    continue
                acc += w
            # skip words with no letters or digits that follow ("—")
            while i < len(spoken) and not keys[i] and len(acc) >= len(key):
                i += 1
        out.append(" ".join(spoken[start:i]))
    if out and i < len(spoken):
        out[-1] = (out[-1] + " " + " ".join(spoken[i:])).strip()
    return out


def shown_to_spoken(shot: MotionShot) -> list[list[tuple[int, int]]]:
    """Per caption: for each SHOWN word (motion_timeline.caption_words), the
    range [a, b) of that caption's spoken words it stands for. How a word's
    time from the audio becomes a caption word's time."""
    from .checks import _is_code_token, _motion_key
    from .motion_timeline import caption_words
    out = []
    for cap, said in zip(shot.captions, caption_speech(shot)):
        spoken = said.split()
        keys = [_motion_key(w) for w in spoken]
        ranges = []
        i = 0
        for tok, _hl in caption_words(cap.text):
            key = _motion_key(tok)
            a = i
            if key:
                code = _is_code_token(tok)
                acc = ""
                while i < len(spoken) and len(acc) < len(key):
                    w = keys[i]
                    i += 1
                    if code and w == "of" and acc and not key[len(acc):].startswith("of"):
                        continue
                    acc += w
            ranges.append((a, max(i, a + 1) if a < len(spoken) else a))
        out.append(ranges)
    return out


# ================================================================ synthesis

def _silent(seconds: float) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(b"\x00\x00" * int(seconds * SAMPLE_RATE))
    return buf.getvalue()


def _read_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Samples (mono, float32 in -1..1) and rate from WAV bytes — integer PCM
    (8/16/24/32-bit) or IEEE float (format 3, which is what Chatterbox
    writes and Python's own `wave` module cannot read)."""
    import struct
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("not a WAV file")
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            tag, ch, rate, _br, _ba, bits = struct.unpack("<HHIIHH", body[:16])
            if tag == 0xFFFE and len(body) >= 26:          # WAVE_FORMAT_EXTENSIBLE
                tag = struct.unpack("<H", body[24:26])[0]
            fmt = (tag, ch, rate, bits)
        elif cid == b"data":
            raw = body
        pos += 8 + size + (size & 1)
    if fmt is None or raw is None:
        raise ValueError("WAV has no fmt or data chunk")
    tag, ch, rate, bits = fmt
    if tag == 3:
        x = np.frombuffer(raw[: len(raw) // (bits // 8) * (bits // 8)],
                          dtype=np.float32 if bits == 32 else np.float64).astype(np.float32)
    elif tag == 1 and bits == 8:
        x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128) / 128
    elif tag == 1 and bits == 16:
        x = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2").astype(np.float32) / 32768
    elif tag == 1 and bits == 24:
        b = np.frombuffer(raw[: len(raw) // 3 * 3], dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        x = (np.where(v >= 1 << 23, v - (1 << 24), v)).astype(np.float32) / (1 << 23)
    elif tag == 1 and bits == 32:
        x = np.frombuffer(raw[: len(raw) // 4 * 4], dtype="<i4").astype(np.float32) / 2 ** 31
    else:
        raise ValueError(f"unsupported WAV format {tag} at {bits} bits")
    if ch > 1:
        x = x[: len(x) // ch * ch].reshape(-1, ch).mean(axis=1)
    return x, rate


def _pcm16(x: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def normalise_wav(data: bytes) -> bytes:
    """Any WAV the engine returns, as 16-bit mono PCM at SAMPLE_RATE — the one
    format every later step (measuring, aligning, mixing) reads."""
    x, rate = _read_wav(data)
    return _pcm16(_resample(x, rate))


def _resample(x: np.ndarray, rate: int) -> np.ndarray:
    if rate == SAMPLE_RATE or len(x) == 0:
        return x
    n = int(round(len(x) * SAMPLE_RATE / rate))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def wav_seconds(data: bytes) -> float:
    x, rate = _read_wav(data)
    return len(x) / float(rate)


def _cache_key(text: str, ref: str | None) -> str:
    stamp = ""
    if ref and Path(ref).exists():
        st = Path(ref).stat()
        stamp = f"{st.st_size}:{st.st_mtime_ns}"
    blob = json.dumps({"engine": "chatterbox", "ref": ref, "stamp": stamp, "text": text,
                       "ex": config.CHATTERBOX_EXAGGERATION, "cfg": config.CHATTERBOX_CFG_WEIGHT,
                       "stub": config.STUB}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


def synth(text: str, ref: str | None, speaker: str) -> bytes:
    """One caption's audio: Chatterbox from `ref` (cached by content), or —
    with MOTION_VOICE=silent (the tests) — silence of the estimated length."""
    if config.MOTION_SILENT:
        return _silent(max(0.6, len(text.split()) / MOTION_WORDS_PER_SECOND))
    key = _cache_key(text, ref)
    path = CACHE_DIR / f"{key}.wav"
    if path.exists():
        return path.read_bytes()
    from .providers import _REGISTRY
    cb = _REGISTRY["chatterbox"]
    ok, why = cb.installed()
    if not ok:
        raise RuntimeError(f"motion voices need Chatterbox: {why}")
    data = normalise_wav(cb.synth(text, ref or "", speaker) if ref else _synth_builtin(cb, text))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def _synth_builtin(cb, text: str) -> bytes:
    """Chatterbox with no reference clip — its built-in voice."""
    import tempfile
    with cb._lock:
        proc = cb._ensure()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out = f.name
        proc.stdin.write(json.dumps({"text": text, "ref": None, "out": out,
                                     "exaggeration": config.CHATTERBOX_EXAGGERATION,
                                     "cfg_weight": config.CHATTERBOX_CFG_WEIGHT}) + "\n")
        proc.stdin.flush()
        reply = cb._read(proc, config.CHATTERBOX_SYNTH_TIMEOUT)
    try:
        if not reply.get("ok"):
            raise RuntimeError(f"chatterbox: {reply.get('error', 'no reply')}")
        return Path(out).read_bytes()
    finally:
        Path(out).unlink(missing_ok=True)


def audio_dir(short_id: str) -> Path:
    d = config.OUTPUT_DIR / short_id / "audio"
    d.mkdir(parents=True, exist_ok=True)
    return d


def manifest_path(short_id: str) -> Path:
    return config.OUTPUT_DIR / short_id / "audio" / "manifest.json"


def voice_script(script: MotionScript, shots: list[str] | None = None, log=print,
                 progress=None, voices: dict[str, str] | None = None) -> dict:
    """Synthesize every caption (or only those of `shots`), write each clip to
    output/<id>/audio/<shot>_<n>.wav, and return the manifest: per shot, per
    caption, the file, its measured seconds, the spoken text, the speaker,
    the voice slot and the reference clip it was cloned from. `progress(done,
    total)` is told after every clip (the web UI's "clip X of N")."""
    slots = speaker_slots(script)
    used = {slots.get(c.speaker, slots[None]) for s in script.shots for c in s.captions}
    refs = {slot: slot_reference(slot) for slot in used}
    # the reviewer's pick per speaker ("narrator" for a one-narrator reel)
    have = available_voices()
    for role, vid in (voices or {}).items():
        slot = slots.get(None if role == "narrator" else role)
        if slot in refs and vid in have:
            refs[slot] = (have[vid][0], f"chosen: {have[vid][1]}")
    for slot, (ref, how) in sorted(refs.items()):
        if how != "slot":
            log(f"  voice: slot {slot} has no voices/motion/{slot}.wav yet — {how}"
                + (f" ({Path(ref).name})" if ref else ""))
    out_dir = audio_dir(script.short_id)
    manifest: dict = {"short_id": script.short_id, "engine": "stub" if config.MOTION_SILENT else "chatterbox",
                      "slots": {s: {"ref": r, "source": h} for s, (r, h) in refs.items()},
                      "shots": {}}
    total = sum(len(s.captions) for s in script.shots if not shots or s.id in shots)
    done = 0
    for shot in script.shots:
        if shots and shot.id not in shots:
            continue
        rows = []
        for n, (cap, said) in enumerate(zip(shot.captions, caption_speech(shot))):
            slot = slots.get(cap.speaker, slots[None])
            ref, _how = refs[slot]
            data = synth(said, ref, cap.speaker or "narrator")
            path = out_dir / f"{shot.id}_{n + 1}.wav"
            path.write_bytes(data)
            rows.append({"file": path.name, "seconds": round(wav_seconds(data), 3), "text": said,
                         "speaker": cap.speaker, "voice_slot": slot, "ref": ref})
            done += 1
            if progress is not None:
                progress(done, total)
        manifest["shots"][shot.id] = rows
    manifest_path(script.short_id).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_manifest(short_id: str) -> dict:
    return json.loads(manifest_path(short_id).read_text(encoding="utf-8"))


# ===================================================================== mix

def mix(script: MotionScript, manifest: dict, clocks, trims: dict | None = None) -> Path:
    """Lay every caption clip at its caption's start on the reel's clock and
    write output/<id>/audio/reel.wav (16-bit mono, 24 kHz), loudness-
    normalised to -14 LUFS when ffmpeg is available (skipped for silence).
    `trims` (motion_timeline.trim_to_speech): shot id -> per clip, the
    (from, to) seconds of it to use — its speech, without the clip's own
    leading and trailing silence."""
    total = clocks[-1].end if clocks else 0.0
    track = np.zeros(int(total * SAMPLE_RATE) + SAMPLE_RATE // 10, dtype=np.float32)
    d = audio_dir(script.short_id)
    for shot, clock in zip(script.shots, clocks):
        cuts = (trims or {}).get(shot.id) or []
        for k, (row, cap) in enumerate(zip(manifest["shots"].get(shot.id, []), clock.captions)):
            x, rate = _read_wav((d / row["file"]).read_bytes())
            x = _resample(x, rate)
            if k < len(cuts):
                a, b = cuts[k]
                x = x[int(a * SAMPLE_RATE):int(b * SAMPLE_RATE)]
            at = int(cap.start * SAMPLE_RATE)
            end = min(len(track), at + len(x))
            track[at:end] += x[:end - at]
    track = np.clip(track, -1, 1)
    raw = d / "reel_raw.wav"
    with wave.open(str(raw), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes((track * 32767).astype(np.int16).tobytes())
    final = d / "reel.wav"
    from .tts import ffmpeg_exe
    exe = ffmpeg_exe()
    if exe and not config.MOTION_SILENT and np.abs(track).max() > 0:
        r = subprocess.run([exe, "-y", "-i", str(raw), "-af",
                            f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11", "-ar", str(SAMPLE_RATE),
                            "-ac", "1", str(final)], capture_output=True)
        if r.returncode == 0:
            raw.unlink(missing_ok=True)
            return final
    raw.replace(final)
    return final
