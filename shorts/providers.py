"""
The TTS backends. One interface, four implementations, chosen by config.

The pipeline does not care who makes the audio, so this is the only file that knows.
Each provider takes a line of text and a voice id and returns encoded audio; tts.py
does everything else — phrasing, per-beat timing, joining, caching.

Why more than one:

  elevenlabs  The best-sounding of the four, and the reason this started. Blocked
              on a free account behind a shared office IP, which is not something
              code can fix.
  kokoro      Kokoro-82M through onnxruntime: local, offline, no key, no quota, and
              close enough to the cloud tiers that it is the sensible default now
              that ElevenLabs is unavailable. Costs a one-off ~330MB download.
  google      The cloud quality target that is reachable for free. Neural2 and
              Chirp3-HD are genuinely natural, the free tier is ~1M characters a
              month, and the REST endpoint takes a plain API key — no
              service-account JSON.
  piper       The floor. Also local and free, a clear step below Kokoro, but far
              smaller and quicker to install — worth keeping for CI and for anyone
              who does not want a 330MB model on disk.

A provider reports its own availability rather than being probed from outside, so
"why is there no voice" always has a specific answer.
"""
from __future__ import annotations

import base64, json, subprocess, tempfile, threading, time
from pathlib import Path

import requests

from . import config


class AccountBlocked(RuntimeError):
    """
    The account cannot synthesise at all — not this request, any request.

    Distinct from a per-request failure because the response is different: there is
    no point trying the next beat, or the next of twenty-five shorts. Seen in the
    wild as ElevenLabs' HTTP 401 "detected_unusual_activity", returned when it has
    disabled Free Tier synthesis for an account. The key stays valid and read-only
    endpoints keep working, which is exactly why it is confusing without this.
    """


class Provider:
    """What tts.py needs from a backend."""

    name = "abstract"
    #: Extension of the audio this provider returns, so chunks land on disk correctly.
    suffix = ".mp3"

    def available(self) -> tuple[bool, str]:
        raise NotImplementedError

    def resolve(self) -> dict[str, str]:
        """speaker -> voice id. Called once per run, never per beat."""
        raise NotImplementedError

    def voices(self) -> list[str]:
        """Human-readable voice names, for --check."""
        return []

    def installed(self) -> tuple[bool, str]:
        """
        Can this provider run AT ALL, ignoring which voices are configured?

        Separate from available() because a caller supplying its own reference
        clips — the voice studio previewing an upload — needs to know the engine
        works, not whether a voice has been chosen. Defaults to available(), which
        is right for every provider whose voices come from an account rather than
        from a file the caller is holding.
        """
        return self.available()

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        raise NotImplementedError


# --------------------------------------------------------------------- elevenlabs

_EL_BASE = "https://api.elevenlabs.io/v1"
_BLOCKED_MARKERS = ("detected_unusual_activity", "free tier access has been disabled",
                    "quota_exceeded")

# Stock voices that ship with every account, used when the library cannot be read.
_EL_FALLBACK = {"interviewer": "pNInz6obpgDQGcFmaJgB",    # Adam
                "student":     "EXAVITQu4vr4xnSDxMaL"}    # Sarah


class ElevenLabs(Provider):
    name = "elevenlabs"
    suffix = ".mp3"

    def _headers(self) -> dict:
        return {"xi-api-key": config.ELEVENLABS_API_KEY,
                "Content-Type": "application/json"}

    def available(self) -> tuple[bool, str]:
        if not config.ELEVENLABS_API_KEY:
            return False, "ELEVENLABS_API_KEY not set in .env"
        return True, f"ready ({config.ELEVENLABS_MODEL})"

    def settings(self, speaker: str) -> dict:
        """
        Delivery for one speaker.

        stability is the counter-intuitive one: LOW is more human. High stability
        makes the model hedge toward a flat, even read; lowering it lets pitch and
        pace move within a sentence, which is what conversation does. The
        interviewer is asking, so a touch quicker and more expressive; the student is
        explaining, so steadier. Identical settings for both is what made the old
        browser version sound like one person reading both halves.
        """
        asking = speaker == "interviewer"
        clamp = lambda v, lo, hi: round(max(lo, min(hi, v)), 3)
        return {
            "stability": clamp(config.VOICE_STABILITY + (0.0 if asking else 0.08), 0, 1),
            "similarity_boost": clamp(config.VOICE_SIMILARITY, 0, 1),
            "style": clamp(config.VOICE_STYLE + (0.08 if asking else 0.0), 0, 1),
            "use_speaker_boost": config.VOICE_SPEAKER_BOOST,
            "speed": clamp(config.VOICE_SPEED * (1.03 if asking else 0.98), 0.7, 1.2),
        }

    def voices(self) -> list[str]:
        r = requests.get(f"{_EL_BASE}/voices", headers=self._headers(), timeout=60)
        if not r.ok:
            raise RuntimeError(f"ElevenLabs {r.status_code} listing voices: {r.text[:200]}")
        return [f"{v['name']}  [{v['voice_id']}]" for v in r.json().get("voices", [])]

    def resolve(self) -> dict[str, str]:
        chosen = {"interviewer": config.VOICE_INTERVIEWER,
                  "student": config.VOICE_STUDENT}
        if all(chosen.values()):
            return chosen
        try:
            r = requests.get(f"{_EL_BASE}/voices", headers=self._headers(), timeout=60)
            r.raise_for_status()
            picked = _pick_contrasting(r.json().get("voices", []))
        except Exception as e:
            print(f"  ! could not list ElevenLabs voices ({type(e).__name__}: {e}) "
                  f"— using stock ids")
            picked = dict(_EL_FALLBACK)
        return {k: v or picked[k] for k, v in chosen.items()}

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        r = requests.post(
            f"{_EL_BASE}/text-to-speech/{voice_id}/with-timestamps",
            headers=self._headers(), timeout=180,
            json={"text": text, "model_id": config.ELEVENLABS_MODEL,
                  "voice_settings": self.settings(speaker)},
        )
        if not r.ok:
            body = r.text[:400]
            if r.status_code in (401, 403) and any(m in body.lower() for m in _BLOCKED_MARKERS):
                raise AccountBlocked(
                    f"ElevenLabs will not synthesise for this account "
                    f"({r.status_code}). The key itself is fine — reading voices "
                    f"works. {body}")
            raise RuntimeError(f"ElevenLabs {r.status_code} for voice {voice_id} "
                               f"(model {config.ELEVENLABS_MODEL}): {body}")
        return base64.b64decode(r.json()["audio_base64"])


def _pick_contrasting(voices: list[dict]) -> dict[str, str]:
    """One voice per speaker, different genders where the library says so."""
    def gender(v: dict) -> str:
        return ((v.get("labels") or {}).get("gender") or "").lower()

    male = [v for v in voices if gender(v) == "male"]
    female = [v for v in voices if gender(v) == "female"]
    if male and female:
        return {"interviewer": male[0]["voice_id"], "student": female[0]["voice_id"]}
    if len(voices) >= 2:
        return {"interviewer": voices[0]["voice_id"], "student": voices[1]["voice_id"]}
    if voices:
        return {k: voices[0]["voice_id"] for k in ("interviewer", "student")}
    return dict(_EL_FALLBACK)


# ------------------------------------------------------------------------- google

_G_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"


class Google(Provider):
    """
    Google Cloud Text-to-Speech over REST, authenticated with an API key.

    Deliberately the plain API-key REST call rather than the client library: the
    library wants Application Default Credentials or a service-account JSON, which
    is a lot of setup for one HTTP POST. Create a key in the Cloud console, restrict
    it to the Text-to-Speech API, and put it in .env.

    Delivery is shaped with speakingRate and pitch, the two knobs the API exposes.
    """

    name = "google"
    suffix = ".mp3"

    def available(self) -> tuple[bool, str]:
        if not config.GOOGLE_TTS_API_KEY:
            return False, "GOOGLE_TTS_API_KEY not set in .env"
        return True, "ready (Google Cloud TTS)"

    def resolve(self) -> dict[str, str]:
        return {"interviewer": config.GOOGLE_VOICE_INTERVIEWER,
                "student": config.GOOGLE_VOICE_STUDENT}

    def voices(self, prefer: str | None = None) -> list[str]:
        rows = [f"{v['name']}  ({v.get('ssmlGender','?')})" for v in self._catalogue()]
        if prefer:
            rows = [r for r in rows if prefer.lower() in r.lower()] or rows
        return rows

    def _catalogue(self) -> list[dict]:
        r = requests.get("https://texttospeech.googleapis.com/v1/voices",
                         params={"key": config.GOOGLE_TTS_API_KEY,
                                 "languageCode": "en-US"}, timeout=60)
        if not r.ok:
            raise RuntimeError(f"Google TTS {r.status_code} listing voices: {r.text[:200]}")
        return r.json().get("voices", [])

    def audio_config(self, voice_id: str, speaker: str) -> dict:
        """
        The audioConfig for one voice, respecting what its family supports.

        This is not uniform across Google's tiers and getting it wrong is a hard 400,
        not a warning. Chirp 3: HD voices reject `pitch` outright — they are a
        different synthesis stack from Neural2/WaveNet/Studio and expose only rate.
        So the pitch separation between the two speakers is applied where it exists
        and simply omitted where it does not, rather than sent hopefully.
        """
        asking = speaker == "interviewer"
        cfg = {
            "audioEncoding": "MP3",
            # The interviewer is asking, so slightly quicker.
            "speakingRate": round(config.VOICE_SPEED * (1.04 if asking else 0.98), 3),
            "sampleRateHertz": 44100,
        }
        if not is_chirp(voice_id):
            cfg["pitch"] = 1.0 if asking else -1.0
        return cfg

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        body = {
            "input": {"text": text},
            "voice": {"languageCode": _lang_of(voice_id), "name": voice_id},
            "audioConfig": self.audio_config(voice_id, speaker),
        }
        r = requests.post(_G_URL, params={"key": config.GOOGLE_TTS_API_KEY},
                          json=body, timeout=180)

        # One retry with a bare audioConfig if the request was rejected over a
        # tuning field. Google's voice families differ in what they accept and the
        # list moves; losing the pitch separation is a far better outcome than
        # losing the audio, and the reason is printed rather than hidden.
        if r.status_code == 400 and any(
                k in r.text.lower() for k in ("pitch", "speakingrate", "speaking_rate",
                                              "audioconfig", "sample_rate")):
            print(f"    ~ google: {voice_id} rejected the tuning fields "
                  f"({r.text[:120]}) — retrying flat")
            body["audioConfig"] = {"audioEncoding": "MP3"}
            r = requests.post(_G_URL, params={"key": config.GOOGLE_TTS_API_KEY},
                              json=body, timeout=180)

        if not r.ok:
            detail = r.text[:400]
            lowered = detail.lower()
            if r.status_code in (401, 403) and ("api key" in lowered
                                                or "permission" in lowered
                                                or "disabled" in lowered
                                                or "quota" in lowered):
                raise AccountBlocked(
                    f"Google TTS refused the key ({r.status_code}). Check the key "
                    f"allows the Text-to-Speech API, and that the API is enabled on "
                    f"the project. {detail}")
            raise RuntimeError(f"Google TTS {r.status_code} for voice {voice_id}: {detail}")
        return base64.b64decode(r.json()["audioContent"])


def is_chirp(voice_id: str) -> bool:
    """Chirp 3: HD and Chirp HD voices, which do not accept a pitch parameter."""
    return "chirp" in voice_id.lower()


def _lang_of(voice_name: str) -> str:
    """"en-US-Neural2-D" -> "en-US". Google wants both, and they must agree."""
    parts = voice_name.split("-")
    return "-".join(parts[:2]) if len(parts) >= 2 else "en-US"


# ------------------------------------------------------------------------- kokoro

_KOKORO_RELEASE = ("https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
                   "model-files-v1.0")
_KOKORO_FILES = ("kokoro-v1.0.onnx", "voices-v1.0.bin")


class Kokoro(Provider):
    """
    Kokoro-82M, running locally through onnxruntime. No account, no key, no cost.

    The ONNX build rather than the official `kokoro` package on purpose: that one
    pulls in torch, which is a multi-gigabyte download for a model of eighty-two
    million parameters. kokoro-onnx reuses the onnxruntime that piper-tts already
    installed, and espeakng-loader ships the espeak binaries inside the wheel, so
    phonemisation needs no `apt install` either. The whole addition is ~10MB of
    wheels on top of what the venv already had.

    Two model files, ~330MB together, fetched once into KOKORO_DATA_DIR on first
    use — the same arrangement as Piper's voice models, and gitignored the same way.

    Measured on this machine: about 5x realtime, so a short renders in a couple of
    seconds. Quality is well clear of Piper and holds its own against the paid
    cloud tiers, which is what earns it a place above Google in the preference list.

    Only speed is tunable. There is no stability or style knob, and nothing is
    faked to look like one — VOICE_STABILITY and friends are ElevenLabs settings and
    are ignored here.
    """

    name = "kokoro"
    suffix = ".wav"          # float32 samples, packed to PCM; tts.py normalises

    _model = None

    def _files(self) -> list[Path]:
        return [Path(config.KOKORO_DATA_DIR) / f for f in _KOKORO_FILES]

    def available(self) -> tuple[bool, str]:
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False, "kokoro-onnx is not installed (pip install kokoro-onnx)"
        if any(not f.exists() for f in self._files()):
            return True, "ready (local, model downloads on first use, ~330MB)"
        return True, f"ready (local, {config.KOKORO_VOICE_STUDENT})"

    def resolve(self) -> dict[str, str]:
        return {"interviewer": config.KOKORO_VOICE_INTERVIEWER,
                "student": config.KOKORO_VOICE_STUDENT}

    def voices(self) -> list[str]:
        return self._load().get_voices()

    def _load(self):
        """
        Load the model once per process, downloading the files if they are missing.

        Deliberately not done in available(): --check asks every provider whether it
        is usable, and that question should not trigger a 330MB download for a
        provider the user was not going to pick.
        """
        if self.__class__._model is not None:
            return self.__class__._model

        from kokoro_onnx import Kokoro as _Kokoro
        directory = Path(config.KOKORO_DATA_DIR)
        directory.mkdir(parents=True, exist_ok=True)

        for name in _KOKORO_FILES:
            path = directory / name
            if path.exists() and path.stat().st_size > 0:
                continue
            print(f"  downloading kokoro {name} (once)…")
            _download(f"{_KOKORO_RELEASE}/{name}", path)

        model, voices = self._files()
        self.__class__._model = _Kokoro(str(model), str(voices))
        return self.__class__._model

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        import io, wave
        import numpy as np

        model = self._load()
        voice = _blend(model, voice_id)

        # The interviewer is asking, so slightly quicker — the same separation the
        # other providers get, and here it is the only one available.
        asking = speaker == "interviewer"
        speed = round(config.VOICE_SPEED * (1.04 if asking else 0.98), 3)
        samples, rate = model.create(text, voice=voice, speed=speed,
                                     lang=config.KOKORO_LANG)

        # Kokoro hands back float32 in [-1, 1]; WAV wants signed 16-bit PCM. Clipping
        # first because a hot sample would otherwise wrap around into loud noise.
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(pcm.tobytes())
        return buf.getvalue()


def _blend(model, spec: str):
    """
    Resolve a Kokoro voice spec to something `model.create` accepts.

    A plain name passes straight through. A spec containing "+" is a BLEND, and
    returns a style vector instead of a name:

        af_bella+hf_beta            equal parts
        af_bella:0.6+hf_beta:0.4    weighted, and weights need not sum to 1

    This works because a Kokoro voice is not a model, it is a (510, 1, 256) style
    tensor conditioning a shared one, so the average of two of them is a coherent
    third voice. It is the practical fix for the two failure modes at either end:
    the Hindi voices smear English stops (that muddy "t"), the American ones carry
    an accent you may not want, and a blend moves the dial continuously between
    them rather than making you choose an end.

    Blending across languages is interpolation, not synthesis of a real accent.
    Expect it to break down as the mix approaches an even split on voices this far
    apart — which is exactly why the ratio is configurable and worth an A/B.
    """
    import numpy as np

    terms = [t.strip() for t in spec.split("+") if t.strip()]
    if not terms:
        raise RuntimeError("kokoro: empty voice spec")

    parsed: list[tuple[str, float]] = []
    for term in terms:
        name, _, weight = term.partition(":")
        name = name.strip()
        if name not in model.get_voices():
            raise RuntimeError(f"kokoro has no voice {name!r}. Available: "
                               f"{', '.join(model.get_voices())}")
        try:
            parsed.append((name, float(weight) if weight.strip() else 1.0))
        except ValueError:
            raise RuntimeError(f"kokoro: {term!r} has a non-numeric weight") from None

    # A lone term is just that voice — its weight normalises to 1 whatever it says.
    if len(parsed) == 1:
        return parsed[0][0]          # a plain name; let kokoro look it up itself

    total = sum(w for _, w in parsed)
    if total <= 0:
        raise RuntimeError(f"kokoro: weights in {spec!r} sum to {total}, need > 0")

    mixed = sum(model.get_voice_style(n) * (w / total) for n, w in parsed)
    return mixed.astype(np.float32)


def _download(url: str, dest: Path) -> None:
    """Stream a large file to disk, via a temp name so a broken run leaves nothing."""
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    tmp.replace(dest)


# -------------------------------------------------------------------------- piper

class Chatterbox(Provider):
    """
    Chatterbox, running locally, speaking in a voice YOU supply.

    THIS IS THE ONE THAT CLONES. Every other provider here has a fixed catalogue —
    you pick am_michael or en-US-Neural2-D from what the model already knows. This
    one takes a RECORDING and speaks in that voice: point
    CHATTERBOX_VOICE_STUDENT at a clip of someone talking and every student beat of
    every short is generated in their voice, zero-shot, with no training step. The
    clip is the whole configuration.

    IT RUNS IN A DIFFERENT VIRTUALENV, over a pipe. chatterbox-tts pins
    torch==2.6.0 and transformers==5.2.0, which do not belong next to this
    project's own dependencies, so it lives in venv-chatterbox/ and is driven as a
    resident subprocess — see shorts/chatterbox_worker.py for the protocol.

    THE WORKER IS STARTED ONCE AND KEPT. Loading the model costs about 158 seconds
    on CPU; a process per beat would pay that per LINE, so a four-beat short would
    spend eleven minutes loading a model it used four times. Started lazily on the
    first synth, reused for the rest of the run, and stopped with the interpreter.

    SPEED, PLAINLY: measured at roughly 3.1x slower than realtime on this CPU, so a
    twenty-second short takes about a minute. On a CUDA box it is faster than
    realtime. Kokoro is ~30x quicker and costs the same nothing; this is the trade
    you are making for a voice that is yours.
    """
    name = "chatterbox"
    suffix = ".wav"

    def __init__(self) -> None:
        self._proc = None
        self._lock = threading.Lock()
        self._info: dict = {}

    # ------------------------------------------------------------------ config
    def resolve(self) -> dict[str, str]:
        # The UI's choice wins. A clip is picked by ear, in the app; requiring a
        # .env edit afterwards to make it stick would put a text editor in the
        # middle of a listening decision. Falls back to the environment, so a
        # command-line setup keeps working untouched.
        chosen = config.voice_settings()
        return {
            "interviewer": (chosen.get("interviewer")
                            or config.CHATTERBOX_VOICE_INTERVIEWER),
            "student": (chosen.get("student")
                        or config.CHATTERBOX_VOICE_STUDENT),
        }

    def voices(self) -> list[str]:
        """The configured reference clips. There is no catalogue to list."""
        return [v for v in self.resolve().values() if v]

    def available(self) -> tuple[bool, str]:
        exe = Path(config.CHATTERBOX_PYTHON)
        if not exe.exists():
            return False, (f"no interpreter at {exe} — create it with\n"
                           f"    python3 -m venv venv-chatterbox && "
                           f"venv-chatterbox/bin/pip install chatterbox-tts")
        refs = self.resolve()
        missing = [k for k, v in refs.items() if not v]
        if missing:
            return False, ("no reference clip for " + ", ".join(missing) +
                           " — set CHATTERBOX_VOICE_INTERVIEWER and "
                           "CHATTERBOX_VOICE_STUDENT to audio files of the two "
                           "voices you want")
        for who, ref in refs.items():
            if not Path(ref).exists():
                return False, f"the {who} reference clip does not exist: {ref}"
        return True, (f"ready (local clone of "
                      f"{Path(refs['student']).name} / "
                      f"{Path(refs['interviewer']).name})")

    def installed(self) -> tuple[bool, str]:
        """Only the interpreter matters when the caller brings its own clips."""
        exe = Path(config.CHATTERBOX_PYTHON)
        if not exe.exists():
            return False, (f"no interpreter at {exe} — create it with\n"
                           f"    python3 -m venv venv-chatterbox && "
                           f"venv-chatterbox/bin/pip install chatterbox-tts")
        return True, "ready (clips supplied by the caller)"

    # ------------------------------------------------------------------ worker
    def _ensure(self):
        """Start the resident worker, or return the one already running."""
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        print("    chatterbox: loading the model (about 2-3 minutes on CPU, once)")
        proc = subprocess.Popen(
            [config.CHATTERBOX_PYTHON, "-m", "shorts.chatterbox_worker"],
            cwd=str(config.ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        ready = self._read(proc, config.CHATTERBOX_START_TIMEOUT)
        if not ready.get("ok"):
            proc.kill()
            raise RuntimeError(f"chatterbox worker: {ready.get('error', 'no reply')}")
        self._info = ready
        print(f"    chatterbox: ready on {ready.get('device')} "
              f"in {ready.get('load_seconds')}s")
        self._proc = proc
        return proc

    @staticmethod
    def _read(proc, timeout: float) -> dict:
        """One JSON line from the worker, or a dict explaining why there was none."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if not line:
                return {"ok": False, "error": "worker exited"}
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except ValueError:
                continue        # progress bars and library chatter
        return {"ok": False, "error": f"no reply within {timeout:.0f}s"}

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        if not voice_id:
            raise RuntimeError(
                f"no chatterbox reference clip for {speaker} — set "
                f"CHATTERBOX_VOICE_{speaker.upper()}")
        # One at a time: the worker is a single process with one model in it.
        with self._lock:
            proc = self._ensure()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                out = f.name
            req = {"text": text, "ref": voice_id, "out": out,
                   "exaggeration": config.CHATTERBOX_EXAGGERATION,
                   "cfg_weight": config.CHATTERBOX_CFG_WEIGHT}
            proc.stdin.write(json.dumps(req) + "\n")
            proc.stdin.flush()
            reply = self._read(proc, config.CHATTERBOX_SYNTH_TIMEOUT)
        try:
            if not reply.get("ok"):
                raise RuntimeError(f"chatterbox: {reply.get('error', 'no reply')}")
            return Path(out).read_bytes()
        finally:
            Path(out).unlink(missing_ok=True)


class Piper(Provider):
    """
    Piper, running locally on the CPU. No account, no key, no per-character cost.

    Measured on this machine: about 40x realtime, so a whole short renders in well
    under a second. Quality is a step below the cloud providers and it is fair to
    say so — but it needs nothing, works offline, and makes the voice path testable
    in CI, which neither of the others do.

    Voice models are ONNX files a few tens of megabytes each, downloaded once into
    PIPER_DATA_DIR on first use.
    """

    name = "piper"
    suffix = ".wav"          # Piper writes WAV; tts.py normalises before joining

    _loaded: dict[str, object] = {}

    def available(self) -> tuple[bool, str]:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False, "piper-tts is not installed (pip install piper-tts)"
        return True, f"ready (local, {config.PIPER_VOICE_STUDENT})"

    def resolve(self) -> dict[str, str]:
        return {"interviewer": config.PIPER_VOICE_INTERVIEWER,
                "student": config.PIPER_VOICE_STUDENT}

    def voices(self) -> list[str]:
        directory = Path(config.PIPER_DATA_DIR)
        local = sorted(p.stem for p in directory.glob("*.onnx")) if directory.exists() else []
        return local or ["(none downloaded yet — they fetch on first use)"]

    def _voice(self, model: str):
        """Load a voice model once per process, downloading it if it is missing."""
        if model in self._loaded:
            return self._loaded[model]

        from piper import PiperVoice
        directory = Path(config.PIPER_DATA_DIR)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{model}.onnx"

        if not path.exists():
            print(f"  downloading piper voice {model} (once)…")
            import subprocess, sys
            subprocess.run([sys.executable, "-m", "piper.download_voices", model,
                            "--data-dir", str(directory)],
                           check=True, capture_output=True)

        self._loaded[model] = PiperVoice.load(str(path))
        return self._loaded[model]

    def synth(self, text: str, voice_id: str, speaker: str) -> bytes:
        import io, wave
        voice = self._voice(voice_id)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            voice.synthesize_wav(text, w)
        return buf.getvalue()


# ------------------------------------------------------------------------ chooser

_REGISTRY = {p.name: p for p in (ElevenLabs(), Chatterbox(), Kokoro(),
                                 Google(), Piper())}

# Best first. "auto" walks this and takes the first that is available, so adding a
# key upgrades the voice without touching any config.
#
# Kokoro sits above Google on quality-per-hassle: it needs no key and no billing
# account, and it is at least Neural2's equal to most ears. That ordering is a
# judgement call, not a measurement — swap the two entries if you disagree, or set
# TTS_PROVIDER to settle it for a single run.
#
# Chatterbox sits second because when it IS configured it is a deliberate
# choice — it only reports available once you have pointed it at reference
# clips, so reaching it under "auto" means you asked for it. It is below
# elevenlabs on speed, not on quality: ~3x slower than realtime on CPU.
_PREFERENCE = ("elevenlabs", "chatterbox", "kokoro", "google", "piper")


# Providers that have told us, this process, that they will not synthesise at all.
#
# Holding credentials is not the same as being able to speak: ElevenLabs is
# configured here and answers every read-only endpoint, but returns 401
# detected_unusual_activity for synthesis. Without this memo, "auto" would pick it
# for every short, fail, and fall through — twenty-five pointless round trips.
_blocked: set[str] = set()


def mark_blocked(name: str) -> None:
    if name not in _blocked:
        _blocked.add(name)
        print(f"  ! {name} cannot synthesise — not trying it again this run")


def is_explicit() -> bool:
    return (config.TTS_PROVIDER or "auto").strip().lower() != "auto"


def get(name: str | None = None) -> Provider:
    """
    The provider to use.

    An explicit TTS_PROVIDER always wins, and fails loudly if it is not usable —
    silently falling back would mean asking for ElevenLabs and quietly shipping
    Piper, which is worse than an error.

    A VOICE KEPT IN THE UI OUTRANKS .env, and leaving that out made "keep these
    voices" a half-measure. Adopting wrote the clips to voices/settings.json and
    set config.TTS_PROVIDER in the SERVER'S memory — which is gone on restart, and
    was never true for any other process. So the clips were stored, chatterbox was
    ready, and the next reel was still narrated by whatever .env said. The store
    records the provider too; honour it, or the button does not mean what it says.

    `revert to .env` deletes the store, which is how you get back.
    """
    if name is None:
        chosen = config.voice_settings().get("provider")
        if chosen and chosen in _REGISTRY:
            ok, _ = _REGISTRY[chosen].available()
            if ok:
                return _REGISTRY[chosen]
    name = (name or config.TTS_PROVIDER or "auto").strip().lower()

    if name != "auto":
        if name not in _REGISTRY:
            raise RuntimeError(f"unknown TTS_PROVIDER {name!r}. "
                               f"Choose from: {', '.join(_REGISTRY)}, or auto")
        return _REGISTRY[name]

    for provider in chain():
        return provider
    return _REGISTRY["piper"]          # reports its own unavailability


def chain() -> list[Provider]:
    """
    Every provider worth trying, best first.

    One entry when TTS_PROVIDER names a provider — an explicit choice is not a
    preference to be overridden. Otherwise the available ones in preference order,
    minus any that has already proved it cannot speak, so "auto" means "the best one
    that actually works" rather than "the best one that has a key".
    """
    if is_explicit():
        return [get()]
    return [_REGISTRY[n] for n in _PREFERENCE
            if n not in _blocked and _REGISTRY[n].available()[0]]


def all_providers() -> list[Provider]:
    return [_REGISTRY[n] for n in _PREFERENCE]
