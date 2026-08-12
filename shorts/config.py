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
MODEL_GENERATOR = os.getenv("MODEL_GENERATOR", "claude-sonnet-5")
MODEL_JUDGE     = os.getenv("MODEL_JUDGE", "claude-opus-5")
MODEL_CHEAP     = os.getenv("MODEL_CHEAP", "claude-haiku-4-5")

VOICE_INTERVIEWER = os.getenv("VOICE_INTERVIEWER", "")
VOICE_STUDENT     = os.getenv("VOICE_STUDENT", "")

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
