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

# THE JUDGE MUST NOT BE WEAKER THAN THE GENERATOR, and this is the one setting
# people get wrong. Grading a claim against a source is the hardest reasoning in
# this pipeline — harder than writing the script, because it means holding the
# document and the claim side by side and deciding whether one really establishes
# the other. It is also the only step whose failure is invisible: a weak judge does
# not produce bad output, it produces APPROVAL, and approval reads exactly like
# quality.
#
# Measured on this project with MODEL_JUDGE set to a flash-lite tier: 7 judged
# units, 6 of them a straight 5/5/5, and zero problems reported across all of them
# — while the free code graders in checks.py were failing most of the same units on
# real defects. It had never once disagreed with anything. See judge_health() below;
# it warns rather than overrides, because the model choice is yours.
MODEL_JUDGE     = os.getenv("MODEL_JUDGE", "claude-opus-5")

# The model that DESIGNS the visuals — skills/visuals.spec_visuals.
#
# THIS WAS DEAD CONFIG AND THE ADVICE ON IT WAS BACKWARDS. It used to name the model
# that drew raw SVG, one call per frame, and the note here recommended the cheapest
# fast model on the grounds that "turning a written spec into coordinates is
# formatting, not deliberation". Both halves stopped being true when templates
# landed: drawing is now local and free (skills/layout.py), so the call it referred
# to does not exist, and for a while nothing read this constant at all — only
# /api/health did, which meant the health endpoint advertised a "diagram" model that
# was never invoked.
#
# What is left is the opposite kind of work. One call per short now has to choose a
# template from eleven, copy code out of the material verbatim, map each selector to
# the value the document gives IT, keep every label off the narration, and make each
# frame differ from the last. That is deliberation, and it is where the accuracy
# complaints land when it is underpowered — a cheap model here produces frames that
# are confidently wrong rather than frames that are ugly.
#
# So: same tier as the generator or better. Defaults to the generator.
MODEL_DIAGRAM   = os.getenv("MODEL_DIAGRAM", "").strip() or MODEL_GENERATOR

# The model that decides WHAT THE VIEWER SHOULD SEE, before any template is picked
# — skills/strategy.spec_strategy.
#
# This step is new and it exists because the old pipeline had no answer to the
# question. spec_visuals went from a spoken sentence straight to a template name,
# which means "what should someone see to understand this?" was never asked out
# loud; it was answered implicitly, as a side effect of picking a shape, and the
# frames that came out scored 9/10 on correctness and 4/10 on educational clarity.
#
# It is the most open-ended call here — no fixed vocabulary to fill in, just a
# judgement about teaching — so it wants the same tier as the design step or
# better. Defaults to MODEL_DIAGRAM.
MODEL_STRATEGIST = os.getenv("MODEL_STRATEGIST", "").strip() or MODEL_DIAGRAM

# The model that LOOKS AT THE RENDERED FRAMES — skills/vision.judge_frames.
#
# MUST BE MULTIMODAL. It is handed PNGs, and a text-only model behind this setting
# fails at the gateway rather than degrading, which is the right way round: a
# vision judge that silently stopped looking would approve everything, and that is
# the exact failure MODEL_JUDGE's note below spends a paragraph on.
#
# Same reasoning as MODEL_JUDGE for the tier, and then some. Deciding whether a
# picture teaches is harder than deciding whether a sentence is grounded, and it is
# the only gate in this pipeline that can catch a frame which is correct, on
# vocabulary, well-formed and still communicates nothing. Defaults to MODEL_JUDGE.
MODEL_VISION_JUDGE = os.getenv("MODEL_VISION_JUDGE", "").strip() or MODEL_JUDGE

#: Whether the vision judge runs at all. On by default; set VISION_JUDGE=0 to skip
#: the rasterise-and-look pass and keep the free structural graders only.
#:
#: It is also skipped automatically when there is no Chromium to rasterise with,
#: so turning it off is about cost rather than about compatibility.
VISION_JUDGE = os.getenv("VISION_JUDGE", "1").strip().lower() not in ("0", "false", "no")


def _i(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, "") or default)
    except ValueError:
        return default


#: Whether a short the judge fails gets one automatic repair attempt. OFF by default.
#:
#: THE REPAIR IS A SECOND FULL BUILD. It rewrites the script, redesigns every frame
#: around the new words, and re-judges — one script call, up to DESIGN_ATTEMPTS
#: visual calls, a vision call and a judge call. So a short that fails the judge used
#: to cost roughly twice a short that passed, and the result is DISCARDED unless it
#: scores strictly better. Observed on closure_definition: the repair came back
#: f=4 against the original's f=5, was correctly thrown away, and the whole second
#: build was paid for.
#:
#: It is off rather than on because the cheaper defences arrived after it: the
#: supportability screen kills unanswerable questions for $0.008 before any of this,
#: and a held short can now be watched and published by hand. Turn it back on with
#: REPAIR_FAILED_SHORTS=1 when getting a short over the bar matters more than the
#: second build it costs.
REPAIR_FAILED_SHORTS = os.getenv("REPAIR_FAILED_SHORTS", "0").strip().lower() in ("1", "true", "yes")

#: Score a drafted script with the LLM judge DURING REVIEW, not only at finalize.
#:
#: WHY THIS IS WORTH A CALL. The deterministic graders answer "is this well
#: formed" — the right length, cited, in order, not repeating itself, reaching its
#: objective. They cannot answer "is this true", because that means holding a claim
#: and a source side by side, which is the one job in this pipeline that needs a
#: model. So a reviewer looking at eight green chips is being told the script is
#: WELL BUILT, and reading that as WELL BUILT AND CORRECT is the obvious mistake to
#: make. The judge already existed and already knew the answer; it just ran after
#: the human had approved, which is the wrong side of the decision.
#:
#: WHAT IT COSTS. One judge call per drafted script, and only for scripts that pass
#: the free graders first — there is nothing to ask about a script already known to
#: be broken. That is roughly a cent a short on top of the draft.
#:
#: Set JUDGE_AT_REVIEW=0 to go back to judging only at finalize.
JUDGE_AT_REVIEW = os.getenv("JUDGE_AT_REVIEW", "1").strip().lower() in ("1", "true", "yes")

#: Whether the supportability screen makes its one model call. On by default.
#:
#: The free half of the screen always runs; this only governs the batched model call
#: that catches a question the material mentions but never settles. Set
#: SCREEN_QUESTIONS=0 to skip it — one call cheaper per build, and back to finding
#: out at the judge, after the diagrams are drawn and paid for.
SCREEN_QUESTIONS = os.getenv("SCREEN_QUESTIONS", "1").strip().lower() not in ("0", "false", "no")

#: How many times the visual step may redesign a short's frames before giving up.
#:
#: MEASURED, NOT GUESSED: across 44 shorts this pipeline spent 266 visual_spec calls
#: — six per short — and 58% of its total bill, because every grader failure bought
#: another full redesign and the repair pass then bought another round of them. Three
#: attempts is generous for a model that has already been told what it got wrong; the
#: second attempt fixes most of what the first got wrong, and the third mostly buys
#: a differently-flawed frame at full price. Raise it when tuning the brief, where
#: you want the loop to work hard; leave it low for ordinary builds.
DESIGN_ATTEMPTS = max(1, _i("DESIGN_ATTEMPTS", 2))

#: Redesign a frame whose educational_clarity is under this, out of 10.
#:
#: 7 is the reviewer's own number ("if educational_clarity < 7: regenerate"). It is
#: the gate because it is the axis that was failing — 4/10 measured — and because
#: it is the one a redesign can actually move. Raising it toward 9 spends every
#: attempt on most shorts; the judge's own scores across a batch are the thing to
#: read before changing it, which is why they are written onto every Visual.
VISION_MIN_CLARITY = _i("VISION_MIN_CLARITY", 7)

#: Redesign a frame whose text_dependency is OVER this, out of 10. HIGH IS BAD here
#: — it measures how much of the frame has to be READ rather than seen.
#:
#: Gated alongside clarity rather than instead of it because the two fail
#: separately. A wall of words scores low on clarity and high on this one, but a
#: frame can also be perfectly clear BECAUSE it is a sentence — clarity 8,
#: text_dependency 9 — and that frame passes a clarity-only gate while being
#: precisely the defect the whole brief is about ("the visuals are just text, and
#: the text is just the narration").
VISION_MAX_TEXT_DEPENDENCY = _i("VISION_MAX_TEXT_DEPENDENCY", 5)

#: Tier words that mark a light/fast model. Matched as WHOLE SEGMENTS of the model
#: id, not as substrings — "gemini" contains "mini", so a plain `in` test called
#: google/gemini-2.5-pro a light tier and printed a warning telling the user their
#: strongest available design model was underpowered. Any Gemini would have tripped
#: it. Segments come from splitting on /, - and . so "gpt-5-mini" -> {gpt,5,mini}
#: still matches and "gemini-2.5-pro" -> {gemini,2,5,pro} no longer does.
_LIGHT_TIER = ("lite", "nano", "mini", "flash", "haiku", "small", "8b", "3b", "1b")


def _is_light_tier(model: str) -> bool:
    """Is this model id a light/fast tier, by whole-segment match?"""
    import re
    segments = {s for s in re.split(r"[/\-.:]+", model.lower()) if s}
    return bool(segments & set(_LIGHT_TIER))


def model_warnings() -> list[str]:
    """Every model setting that is likely to be doing quiet damage.

    Deliberately advisory. There is no way to rank arbitrary gateway model strings,
    and overriding somebody's explicit choice would be worse than saying nothing.
    What IS detectable is a small number of configurations whose failure mode is
    silence rather than an error.
    """
    out = [w for w in (_judge_warning(), _diagram_warning(), _vision_warning()) if w]
    return out


def judge_health() -> str | None:
    """Back-compat alias for the judge warning alone."""
    return _judge_warning()


def _diagram_warning() -> str | None:
    """MODEL_DIAGRAM on a light tier, now that it means something again.

    Worth its own warning because of how the setting changed under people's feet.
    It used to name the model that turned a finished spec into SVG coordinates, and
    for that job the cheapest fast model genuinely was the right answer — the note
    above this used to recommend exactly that, with timings. Then templates made
    drawing local, nothing read the constant at all, and it sat in .env as a stale
    value that did nothing.

    Wiring it to spec_visuals gives it teeth again, pointed at completely different
    work: designing every frame of the short. A value chosen for the old meaning is
    now silently downgrading the hardest call in the pipeline, and the symptom is
    frames that are confidently wrong — which reads as a prompt problem, not a
    config one.
    """
    diagram, gen = MODEL_DIAGRAM.lower(), MODEL_GENERATOR.lower()
    if diagram == gen:
        return None
    if _is_light_tier(diagram) and diagram != gen:
        return (f"MODEL_DIAGRAM ({MODEL_DIAGRAM}) is a light/fast tier. It no longer "
                f"means 'draw this spec as coordinates' — since templates landed it "
                f"DESIGNS every frame: picking a template, copying code out of the "
                f"material verbatim, and matching each value to the selector the "
                f"document gives it. Underpowered there produces accurate-looking "
                f"frames that are wrong. Unset it to follow MODEL_GENERATOR "
                f"({MODEL_GENERATOR}), or raise it.")
    return None


def _vision_warning() -> str | None:
    """MODEL_VISION_JUDGE on a light tier, or aimed at the model it is grading.

    Same failure shape as the text judge and worse consequences. This gate exists
    to catch frames that every cheap check already approved, so when it approves
    too, nothing else is left — and a light multimodal model asked "does this
    picture teach the concept" answers yes to almost any tidy diagram.
    """
    vision, designer = MODEL_VISION_JUDGE.lower(), MODEL_DIAGRAM.lower()
    if _is_light_tier(vision):
        return (f"MODEL_VISION_JUDGE ({MODEL_VISION_JUDGE}) is a light/fast tier. It "
                f"is the last gate in the pipeline and the only one that can see a "
                f"frame — a weak one here does not fail loudly, it scores every tidy "
                f"diagram 8/10 and the visuals stop improving. Point it at a frontier "
                f"multimodal model.")
    if vision == designer:
        return (f"MODEL_VISION_JUDGE and MODEL_DIAGRAM are both {MODEL_DIAGRAM} — the "
                f"model that designed the frame is grading the frame, and it scores "
                f"its own composition generously. Use a different family.")
    return None


def _judge_warning() -> str | None:
    judge, gen = MODEL_JUDGE.lower(), MODEL_GENERATOR.lower()
    # ABSOLUTE, not relative to the generator. The first version of this only warned
    # when the judge was lighter than the generator, which stayed silent on the exact
    # configuration that prompted writing it — a flash-lite judge behind a gpt-5-mini
    # generator, where both are light tiers so neither is "lighter". But the judge is
    # not competing with the generator, it is doing a harder job than the generator:
    # writing a grounded script is easier than deciding whether someone else's script
    # is grounded. A light model is not up to the second task at any generator size.
    if _is_light_tier(judge):
        return (f"MODEL_JUDGE ({MODEL_JUDGE}) is a light/fast tier. Grading a claim "
                f"against its source is the hardest step here, and a judge that "
                f"cannot do it does not fail loudly — it approves everything, and "
                f"5/5/5 from it means nothing. Point MODEL_JUDGE at a frontier "
                f"model; it is one call per short.")
    if judge == gen:
        return (f"MODEL_JUDGE and MODEL_GENERATOR are both {MODEL_GENERATOR} — a model "
                f"grading its own output scores itself generously. Use a different "
                f"family for the judge.")
    return None

# ------------------------------------------------------------------- video render
#
# shorts/video.py photographs the REAL player at #capture/<id> rather than drawing
# its own page, so it needs somewhere to point a browser at. Defaults to the local
# server; override when the app is served on another port.
VIDEO_BASE_URL = os.getenv("VIDEO_BASE_URL", "http://127.0.0.1:8000").strip()


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

def _f_late(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, "") or default)
    except ValueError:
        return default


# --- chatterbox (local, offline, free — Resemble AI's Chatterbox, zero-shot cloning)
#
# THE ONE THAT TAKES YOUR OWN VOICE. Point these at a recording of a real person
# and every beat that speaker says is generated in that voice — there is no
# training step and no per-voice setup, the clip IS the configuration. That is
# what separates it from kokoro/piper, whose voices are fixed in the model.
#
# THE CLIP SETS THE CEILING. 7-20 seconds, one speaker, no music or background,
# ordinary speaking pace. A noisy reference produces a noisy voice on every short
# it is used for, and no amount of tuning below recovers it.
#
# Lives in its own virtualenv because it pins torch and transformers — see
# shorts/chatterbox_worker.py for why, and CHATTERBOX_PYTHON for where.
#: WHERE THE INTERPRETER LIVES DEPENDS ON THE OS, and hardcoding the POSIX layout
#: made this unusable on Windows. A venv puts its interpreter in bin/python on
#: Linux and macOS and in Scripts\python.exe on Windows — so the default pointed at
#: a path that can never exist there, and the voice tab reported "Chatterbox is not
#: installed" even after someone had installed it correctly.
_VENV_BIN = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
CHATTERBOX_PYTHON = os.getenv(
    "CHATTERBOX_PYTHON", str(ROOT.joinpath("venv-chatterbox", *_VENV_BIN))).strip()

#: The install line to show when it is missing, in the shell the reader is actually
#: using. Four places print this instruction and they were four copies of the POSIX
#: one; a Windows user following it verbatim gets "no such file or directory" from
#: `venv-chatterbox/bin/pip` and no clue why.
CHATTERBOX_INSTALL_HINT = (
    r"python -m venv venv-chatterbox && venv-chatterbox\Scripts\pip install chatterbox-tts"
    if os.name == "nt" else
    "python3 -m venv venv-chatterbox && venv-chatterbox/bin/pip install chatterbox-tts")
#: Voices chosen in the UI, which outrank the environment.
#:
#: A reference clip is picked by LISTENING, so it is chosen in the app rather than
#: in a file — and a choice made in the app has to survive a restart without asking
#: anyone to edit .env. This is that store: shorts/server.py writes it when someone
#: adopts a voice, and Chatterbox.resolve() reads it before falling back to the
#: environment. Absent, everything behaves exactly as it did before.
VOICE_DIR = ROOT / "voices"
VOICE_SETTINGS = VOICE_DIR / "settings.json"


def voice_settings() -> dict:
    """What the UI has chosen, or {} if it has chosen nothing."""
    try:
        import json
        return json.loads(VOICE_SETTINGS.read_text())
    except Exception:
        return {}


CHATTERBOX_VOICE_INTERVIEWER = os.getenv("CHATTERBOX_VOICE_INTERVIEWER", "").strip()
CHATTERBOX_VOICE_STUDENT     = os.getenv("CHATTERBOX_VOICE_STUDENT", "").strip()
# Expressiveness and pacing. 0.5/0.5 is the model's default; raising exaggeration
# emotes more, lowering cfg_weight slows the delivery down.
CHATTERBOX_EXAGGERATION = _f_late("CHATTERBOX_EXAGGERATION", 0.5)
CHATTERBOX_CFG_WEIGHT   = _f_late("CHATTERBOX_CFG_WEIGHT", 0.5)
# Loading the model takes ~158s on CPU, and the worker has to be given time to do
# it before the first beat is asked for.
CHATTERBOX_START_TIMEOUT = _f_late("CHATTERBOX_START_TIMEOUT", 420.0)
CHATTERBOX_SYNTH_TIMEOUT = _f_late("CHATTERBOX_SYNTH_TIMEOUT", 300.0)

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
