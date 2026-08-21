"""Central config. Reads .env once so no other module touches os.environ."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

def _req(key: str) -> str:
    v = os.getenv(key)
    if not v or v.startswith("sk-ant-xxx") or v.endswith("_here"):
        raise RuntimeError(f"{key} is missing from .env — copy .env.example to .env and fill it in")
    return v

ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")

# SHORTS_STUB=1 replaces every LLM call with a canned answer built from the source
# doc. No key, no network, no cost. Use it to prove the plumbing end to end before
# you pay for anything. See shorts/stubs.py.
STUB = os.getenv("SHORTS_STUB", "").strip().lower() in ("1", "true", "yes")

# Set to route through an Anthropic-compatible gateway (e.g. OpenRouter).
# Empty means talk to api.anthropic.com directly.
ANTHROPIC_BASE_URL  = os.getenv("ANTHROPIC_BASE_URL", "").strip()

# Model IDs are gateway-specific. First-party Anthropic uses "claude-sonnet-5";
# OpenRouter uses "anthropic/claude-sonnet-5". Set them in .env, not here.
#
# The generator and the judge should come from DIFFERENT families. A judge scoring
# its own family's output grades itself generously, and the judge here exists to
# catch exactly the kind of fabrication a generator is blind to in its own writing.
#
# Reasoning cannot be switched off on the gpt-5 family — see llm._reasoning. That
# is handled, not worked around, but it does mean a gpt-5 generator has an output
# token floor the Anthropic models do not.
MODEL_GENERATOR = os.getenv("MODEL_GENERATOR", "claude-sonnet-5")
MODEL_JUDGE     = os.getenv("MODEL_JUDGE", "claude-opus-5")
MODEL_CHEAP     = os.getenv("MODEL_CHEAP", "claude-haiku-4-5")

# Drawing the SVGs is its own model, because it is a different kind of work and it
# dominates the bill: four or five calls per short against one for the script.
#
# It is also the step that needs reasoning least. The visual spec has already
# decided what the frame contains; this call turns a written spec into coordinates,
# which is formatting, not deliberation — the same argument llm.py makes for
# switching thinking off generally. Measured on one identical frame:
#
#     openai/gpt-5-mini              3915 output tokens   7 shapes   0 problems   37s
#     google/gemini-3.1-flash-lite    868 output tokens   6 shapes   0 problems    3s
#
# Same quality by every check available, 4.5x fewer tokens and 12x faster, because
# gpt-5 cannot have reasoning turned off and spends ~3300 tokens deliberating over
# a box layout. Defaults to the generator so this is opt-in, not a surprise.
MODEL_DIAGRAM   = os.getenv("MODEL_DIAGRAM", "").strip() or MODEL_GENERATOR

# ------------------------------------------------------------------ neural voice
#
# Voice ids are OPTIONAL. Leaving them blank makes voice.py pick two contrasting
# voices from the account's own library at startup, which is one less thing to
# copy-paste wrong — a mistyped voice id is a 404 per beat, and it used to be the
# most common way this step failed.
VOICE_INTERVIEWER = os.getenv("VOICE_INTERVIEWER", "").strip()
VOICE_STUDENT     = os.getenv("VOICE_STUDENT", "").strip()

# Which backend speaks. "auto" takes the best one whose credentials are present —
# elevenlabs, kokoro, google, then piper — so adding a key upgrades the voice without
# any other change. Naming one explicitly fails loudly if it is not usable, which is
# what you want: asking for ElevenLabs and silently getting Piper is worse than an
# error. See shorts/providers.py.
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "auto").strip()

# --- google cloud tts (plain API key, no service-account JSON needed)
GOOGLE_TTS_API_KEY = os.getenv("GOOGLE_TTS_API_KEY", "").strip()
# Neural2 voices are the natural-sounding tier and are inside the monthly free
# allowance. D is male, F is female — two speakers that read as two people.
GOOGLE_VOICE_INTERVIEWER = os.getenv("GOOGLE_VOICE_INTERVIEWER", "en-US-Neural2-D").strip()
GOOGLE_VOICE_STUDENT     = os.getenv("GOOGLE_VOICE_STUDENT", "en-US-Neural2-F").strip()

# --- kokoro (local, offline, free — Kokoro-82M via onnxruntime)
#
# Two files, ~330MB together, fetched once into KOKORO_DATA_DIR. Voice ids encode
# accent and gender in their prefix: a=American, b=British, f=female, m=male,
# h=Hindi. The student does most of the explaining, so it gets af_heart, the
# best-graded voice in the pack; the interviewer gets a male voice so the two read
# as two people. `python -m shorts.voice --check` prints every voice.
#
# Either id may be a BLEND — "af_bella:0.6+hf_beta:0.4" — because a Kokoro voice is
# a style tensor and the average of two is a coherent third. See providers._blend;
# it is how you reach an accent with no voice of its own in the pack.
KOKORO_DATA_DIR = os.getenv("KOKORO_DATA_DIR", str(ROOT / "output" / "kokoro-voices")).strip()
KOKORO_VOICE_INTERVIEWER = os.getenv("KOKORO_VOICE_INTERVIEWER", "am_michael").strip()
KOKORO_VOICE_STUDENT     = os.getenv("KOKORO_VOICE_STUDENT", "af_heart").strip()
# Drives espeak's phonemisation, so it must match the accent of the chosen voices.
KOKORO_LANG = os.getenv("KOKORO_LANG", "en-us").strip()

# --- piper (local, offline, free)
PIPER_DATA_DIR = os.getenv("PIPER_DATA_DIR", str(ROOT / "output" / "piper-voices")).strip()
PIPER_VOICE_INTERVIEWER = os.getenv("PIPER_VOICE_INTERVIEWER", "en_US-ryan-medium").strip()
PIPER_VOICE_STUDENT     = os.getenv("PIPER_VOICE_STUDENT", "en_US-lessac-medium").strip()

# eleven_multilingual_v2 is the most natural of the generally-available models and
# the right default here: narration is generated once at build time and cached, so
# a slower model costs nothing at watch time. Switch to eleven_flash_v2_5 if you are
# regenerating constantly and want the turnaround.
ELEVENLABS_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()

def _f(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, "") or default)
    except ValueError:
        return default

# Delivery. These are the knobs that decide whether it sounds like a person.
#
# stability is the counter-intuitive one: LOW is more human. High stability makes
# the model hedge toward a flat, even read; lowering it lets pitch and pace move
# within a sentence, which is what conversational speech actually does. Too low and
# it becomes unstable across a long line, so the two speakers sit either side of
# the middle rather than at an extreme.
VOICE_STABILITY   = _f("VOICE_STABILITY", 0.40)
VOICE_SIMILARITY  = _f("VOICE_SIMILARITY", 0.80)
VOICE_STYLE       = _f("VOICE_STYLE", 0.35)   # expressiveness; >0.5 starts to emote
VOICE_SPEED       = _f("VOICE_SPEED", 1.0)
VOICE_SPEAKER_BOOST = os.getenv("VOICE_SPEAKER_BOOST", "1").strip() not in ("0", "false", "no")

# Silence inserted between beats, in seconds. A beat change is also a diagram
# change, so this doubles as the viewer's beat to look at the new picture.
VOICE_BEAT_GAP = _f("VOICE_BEAT_GAP", 0.45)

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
