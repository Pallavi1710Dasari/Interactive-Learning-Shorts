"""Central config. Reads .env once so no other module touches os.environ."""
import json
import os
from dataclasses import dataclass
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

#: How many times review.regenerate may call the LLM to refine ONE candidate
#: question, before it refuses and the human has to approve or reject what
#: they have. THE LOOP PROTECTION Step 3 was asked for: without a cap, a
#: reviewer who keeps disliking the wording could keep spending regeneration
#: calls indefinitely on a single question that was never going to satisfy
#: them, which is the same unbounded-retry failure MAX_SCRIPT_RETRIES already
#: guards against one stage later. Configurable because "how many tries is
#: reasonable" is a judgement call, not a fact this file can derive.
MAX_QUESTION_REGENERATIONS = int(os.getenv("MAX_QUESTION_REGENERATIONS", "3"))

#: The same loop protection, one stage later, for
#: review.regenerate_teaching_approach — a SEPARATE counter and a SEPARATE
#: limit from MAX_QUESTION_REGENERATIONS above, on purpose. A reviewer
#: unhappy with the TEACHING DEVICE ("code is not necessary for this
#: concept") is a different complaint from one unhappy with the QUESTION's
#: own wording, and the two budgets must not share a counter — see
#: schema.TeachingApproachRegenerationAttempt's own note on why the two
#: regeneration flows are kept logically separate.
MAX_TEACHING_APPROACH_REGENERATIONS = int(
    os.getenv("MAX_TEACHING_APPROACH_REGENERATIONS", "3"))

#: THE SAME LOOP PROTECTION, ONE STAGE LATER STILL, for
#: review.regenerate_visual_plan — a SEPARATE counter and a SEPARATE limit
#: from both MAX_QUESTION_REGENERATIONS and
#: MAX_TEACHING_APPROACH_REGENERATIONS above, for the same reason those two
#: are kept apart from each other: a reviewer unhappy with the VISUAL PLAN
#: ("beat 2 shows code, that was never the approach") is a different
#: complaint from one about the question's wording or the teaching device,
#: and the three budgets must not share a counter — see
#: schema.VisualStrategyRegenerationAttempt's own note.
MAX_VISUAL_PLAN_REGENERATIONS = int(
    os.getenv("MAX_VISUAL_PLAN_REGENERATIONS", "3"))

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

#: Redesign a frame whose animation_relevance is under this, out of 10.
#:
#: THE AXIS THAT WAS SCORED AND NEVER GATED. judge_frames has always asked for
#: this — the rubric's own bands are 9-10 "the motion IS the concept", 5-6 "a
#: sensible build order that does not itself explain anything", 0-3 "parts
#: appearing in an arbitrary order, or motion on a frame whose concept has
#: nothing moving in it" — but VisualScore.failures() never read it, so a
#: frame scoring 0-3 here shipped exactly like a 9. The bar sits at 4, not 7
#: like VISION_MIN_CLARITY: the 5-6 band is an honest, legitimate score for a
#: concept the rubric itself says "does not need motion and is not penalised
#: for arriving quietly" (a `structure` beat, say), and gating there would
#: send every correctly-static frame back for a redesign it does not need.
#: 0-3 is reserved for the rubric's own bad cases — arbitrary motion, or a
#: process/data_movement/cause_effect beat that needed motion and got none —
#: which is what this threshold is for.
VISION_MIN_ANIMATION_RELEVANCE = _i("VISION_MIN_ANIMATION_RELEVANCE", 4)

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
        return json.loads(VOICE_SETTINGS.read_text(encoding="utf-8"))
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

# THE BUILD-LEVEL CAP ON WAITING FOR A RECORDED TRACK, in /api/finalize —
# separate from CHATTERBOX_SYNTH_TIMEOUT above, which is a per-beat ceiling
# the PROVIDER enforces on itself. A local CPU-only provider (Chatterbox
# with no GPU) can legitimately take several minutes once model load and
# several beats are added up, and a build must not block the whole HTTP
# response on that indefinitely — past this many seconds, the short ships
# without its recorded track (the browser voice narrates instead, at zero
# cost — see FinalizeIn.do_voice) while synthesis keeps running in the
# background; a later rebuild's cache check (see voice._from_cache) picks
# up the finished recording for free once it lands.
VOICE_BUILD_TIMEOUT = _f_late("VOICE_BUILD_TIMEOUT", 240.0)

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

# STEP 5 (continuous narration). Silence before a beat whose own
# Beat.continues_previous is True — the same spoken thought as the beat
# before it, kept as a separate beat only because it needs its own visual.
# Short enough not to read as a second answer starting, long enough that the
# concat join at tts._join's beat boundary does not run two words together —
# roughly a comma's worth of pause, not a full stop's. Still nonzero: a hard
# 0 risks an audible click at the join on some providers' trailing samples,
# and this is silence either way, never speech.
VOICE_CONTINUATION_GAP = _f("VOICE_CONTINUATION_GAP", 0.12)

OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# --------------------------------------------------------------------- theme
#
# Which visual theme layout.py draws with, and web/src/styles.css dresses the
# player in. Two values today:
#
#   "paper"  the original — a light card on a green/teal starfield.
#   "neon"   glowing strokes on black, in the idiom of the animated CS explainers
#            the reviewer pointed at (bugCoder's stack push/pop short).
#
# DEFAULT IS NOW "neon". Compared side by side on a real rendered frame, "paper"
# reads as a soft, filled, pastel flashcard — solid light-blue boxes on cream —
# and "neon" reads as the professional technical-explainer look this project is
# aiming for: dark ground, glowing outlines, no fill doing the work a shape and
# a line should. Same composition, same shapes, same everything decided
# upstream — this is a rendering-only change, and the one the reviewer's own
# reference was pointing at before the switch ever existed.
#
# This is a SWITCH, not a rewrite: both palettes live side by side in
# layout.THEMES, so `REEL_THEME=paper python -m shorts.redraw` puts every diagram
# back exactly as it was. Nothing about the narration, timing or voice changes
# with it — the theme only decides colour, glow and the ground they sit on.
REEL_THEME = os.getenv("REEL_THEME", "neon").strip().lower()


# --------------------------------------------------------------------- reel style
#
# See RESTYLE_TO_STORY_REELS.md. Two values:
#
#   "explainer"  the original — single-narrator, SVG-diagram pipeline (skills/
#                script.py's SYSTEM_EXPLAINER, skills/visuals.py, layout.py). Unchanged.
#   "story"      illustrated character-story reels: skills/script.py's SYSTEM_STORY,
#                a metaphor mapping stage before any shot is written, a fixed CAST.
#
# A SWITCH, not a rewrite — same shape as REEL_THEME above. DEFAULT IS "explainer":
# every existing shipped reel, and every run that does not set REEL_STYLE, gets
# byte-identical behaviour to before this existed. Nothing in run.py branches on
# this until a caller explicitly asks for "story".
REEL_STYLE = os.getenv("REEL_STYLE", "explainer").strip().lower()

# The story mode's fixed cast — name -> a short visual/personality descriptor the
# story prompt (and, later, an illustrator) reads. Deliberately small and fixed
# rather than invented per reel: a feed whose cast changes every short cannot
# hold a consistent visual style, the same reason TTS already fixes one
# VOICE_INTERVIEWER/VOICE_STUDENT pair rather than casting a new voice per short.
#
# FOUR ROLES, NEVER MORE. Rahul and Riya are the two acting characters; System
# is the personified technology of the reel — ONE visual design across every
# short, with only a chest badge changing to name it ("React", "the OS", "the
# Database") at runtime (see schema.ConceptMappingSet.system_name, filled per
# reel, never hardcoded here). Narrator is voice-only and never drawn — the
# storyteller who carries the story forward between what the other three do.
# Keeping System's design fixed and only re-badging it is what lets a feed of
# reels about completely different technologies still look like one show.
#
# Override with a JSON object, e.g. CAST='{"Rahul": "...", "Riya": "..."}'.
_CAST_DEFAULT = {
    "Rahul": "curious learner in his mid-20s — gets things wrong first, reacts big",
    "Riya": "calm mentor — speaks in one short sentence, never lectures",
    "System": "the personified technology of the reel, a keeper/guard/librarian "
              "figure — one fixed visual design; only a chest badge names it "
              "per reel (see ConceptMappingSet.system_name)",
    "Narrator": "voice only, never drawn — the storyteller who carries the flow",
}
try:
    CAST: dict[str, str] = json.loads(os.getenv("CAST", "")) if os.getenv("CAST") else _CAST_DEFAULT
except (json.JSONDecodeError, TypeError):
    CAST = _CAST_DEFAULT

# --------------------------------------------------------- cast VISUAL definitions
#
# RESTYLE_TO_STORY_REELS.md Step 4. CAST above is what SYSTEM_STORY reads to
# write the STORY (personality, role) — CAST_LOOK is the separate, parallel
# thing shorts/style.py and shorts/cast_sheets.py read to DRAW it (physical
# appearance). Kept apart on purpose: a character's personality and its
# visual design are different concerns that happen to share a name, and
# folding "look" into CAST's own string would make every existing caller of
# CAST (the narrative prompts) carry image-generation prose they never use.
#
# Narrator has no entry — it is never drawn (see CAST's own note), so there
# is nothing here for it to look like.
_CAST_LOOK_DEFAULT = {
    "Rahul": "young, messy hair tuft on top, slightly oversized round eyes, "
             "energetic poses",
    "Riya": "ponytail, calm half-smile, upright confident posture",
    "System": "taller keeper figure, neat cap, small blank rounded badge on the "
              "chest (badge has an ICON only — no letters; the topic name is "
              "spoken, never drawn)",
}
try:
    CAST_LOOK: dict[str, str] = (json.loads(os.getenv("CAST_LOOK", ""))
                                 if os.getenv("CAST_LOOK") else _CAST_LOOK_DEFAULT)
except (json.JSONDecodeError, TypeError):
    CAST_LOOK = _CAST_LOOK_DEFAULT

#: The fixed pose for the CTA screen's mascot — Rahul, thumbs up. Same
#: character, same pose, every reel, so the sign-off reads as one consistent
#: brand beat across the whole feed rather than a new pose invented per short.
MASCOT_POSE = os.getenv(
    "MASCOT_POSE",
    "Rahul, big genuine smile, thumbs up with one hand raised, looking straight "
    "at the camera")

#: Where an APPROVED cast sheet lives — <name>.png, lowercased (see
#: cast_sheets.py's own _approved_path). A shared constant, not a path
#: literal duplicated in both cast_sheets.py and skills/visuals.py's
#: cast_refs_for_shot (Step 5) — the two need to agree on where a sheet is
#: without skills/visuals.py importing the CLI module that owns it.
CAST_ASSETS_DIR = ROOT / "assets" / "cast"

#: Where a per-character Chatterbox reference clip lives — <name>.wav,
#: lowercased. RESTYLE_TO_STORY_REELS.md Step 8 Part 1 — shorts/voice_refs.py
#: writes one here per CAST role, synthesized from that character's own
#: mapped Kokoro voice, so a fresh checkout has SOMETHING to clone from day
#: one; a human recording a real line later just overwrites the file (with
#: --force — voice_refs.py never overwrites by default). See
#: _CAST_CHATTERBOX_VOICE_DEFAULT below for the "wire these into
#: CAST_CHATTERBOX_VOICE" auto-discovery this directory exists to enable.
CAST_VOICE_DIR = ROOT / "assets" / "voices"


# --------------------------------------------------------------------- brand
#
#: `style` is the one-line illustration description every shot prompt has
#: always carried (unchanged from before this dataclass existed — __str__
#: returns it, so f"{config.BRAND}" keeps working everywhere it already did).
#: `bg`/`accent_1`/`accent_2` are Step 4's addition: shorts/style.py's
#: STYLE_BIBLE reads these instead of hard-coding colors, so a brand refresh
#: is a .env edit, not a prompt-string edit.
@dataclass(frozen=True)
class _Brand:
    style: str
    bg: str
    accent_1: str
    accent_2: str

    def __str__(self) -> str:
        return self.style


BRAND = _Brand(
    style=os.getenv(
        "BRAND_STYLE",
        "warm, hand-drawn line art; one flat accent colour per short; no photorealism"),
    bg=os.getenv("BRAND_BG", "#F7F3EA"),           # off-white paper
    accent_1=os.getenv("BRAND_ACCENT_1", "#6B4EFF"),  # purple
    accent_2=os.getenv("BRAND_ACCENT_2", "#FFC738"),  # warm yellow
)

#: The handle spoken in every story reel's closing call-to-action shot — see
#: skills.script.SYSTEM_STORY_SHOTS's STRUCTURE section ("Follow {handle} to
#: learn {topic} the simple way."). A placeholder until a real account
#: exists; override once one does.
BRAND_HANDLE = os.getenv("BRAND_HANDLE", "@learnthesimpleway").strip()


# --------------------------------------------------------------- image generation
#
# shorts/imagegen.py — RESTYLE_TO_STORY_REELS.md Step 3. Turns one shot's
# prompt (+ optional reference images, e.g. character sheets) into a rendered
# frame. "gemini" is the default because it is the only provider here that
# takes reference images alongside the prompt — story mode's fixed cast (see
# CAST above) needs that for visual consistency across shots; "cloudflare"
# and "stub" do not.
IMAGE_PROVIDER = os.getenv("IMAGE_PROVIDER", "gemini").strip().lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

#: gemini-3.1-flash-lite-image ("Nano Banana 2 Lite") — RESTYLE_TO_STORY_
#: REELS.md Step 8 Part 0 #3: the DEFAULT day-to-day image model, chosen for
#: cost (see IMAGE_LITE_COST_PER_CALL below) over IMAGE_MODEL_FULL's higher
#: per-image price. Two one-setting ways back to something else: set
#: IMAGE_MODEL=gemini-3.1-flash-image (IMAGE_MODEL_FULL's own id) for the
#: pricier/higher-quality model, or IMAGE_PROVIDER=cloudflare for the free
#: fallback. Model id and price CONFIRMED AGAINST ai.google.dev/gemini-api/
#: docs/pricing on 2026-09-29: "Equivalent to ... $0.0336 per 1K resolution
#: image". A CONFIG SETTING, not a literal in imagegen.py, so a future model
#: rename is a .env edit, not a code change.
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-lite-image").strip()
IMAGE_LITE_COST_PER_CALL = _f_late("IMAGE_LITE_COST_PER_CALL", 0.0336)

#: gemini-3.1-flash-image ("Nano Banana 2") — Google's higher-quality,
#: pricier general-purpose image generation/editing model. NOT the day-to-
#: day default any more (see IMAGE_MODEL above) — kept as its own fixed
#: constant so cast_sheets.py's --compare mode (Step 4 Part 4) always
#: compares this exact model against IMAGE_MODEL_LITE, regardless of
#: whatever IMAGE_MODEL is currently set to. CONFIRMED AGAINST THE OFFICIAL
#: DOCS ON 2026-09-29 — ai.google.dev/gemini-api/docs/generate-content/
#: image-generation and firebase.google.com/docs/ai-logic/generate-images-
#: gemini both name it as the current versatile image model, and both show
#: `generateContent` with `generationConfig.responseModalities: ["IMAGE"]`
#: as the request shape imagegen.py's GeminiImageProvider uses.
IMAGE_MODEL_FULL = os.getenv("IMAGE_MODEL_FULL", "gemini-3.1-flash-image").strip()

#: $/image at IMAGE_SIZE's "1K" tier, STANDARD (non-batch) pricing — Google's
#: own pricing page (ai.google.dev/gemini-api/docs/pricing, read 2026-09-29):
#: "Equivalent to ... $0.067 per 1K image". The Gemini API reports no
#: per-call cost the way OpenRouter does for text (see usage.py's own note on
#: that), so this is what usage.record_image marks estimated=True against —
#: a real bill may differ if Google's price moves.
IMAGE_COST_PER_CALL = _f_late("IMAGE_COST_PER_CALL", 0.067)

#: gemini-3.1-flash-lite-image ("Nano Banana 2 Lite") — kept as its own name
#: (identical id to IMAGE_MODEL's own default) so estimate_cost() and
#: cast_sheets.py's --compare mode can name "the lite model" explicitly
#: without assuming IMAGE_MODEL hasn't been overridden. NO GEMINI IMAGE
#: MODEL HAS A FREE TIER as of the pricing read above — every image model's
#: Free Tier row on that page (2.5/3.1/3.1-lite/3-pro) reads "Not available";
#: there is nothing free to prefer here (cloudflare is the free fallback).
IMAGE_MODEL_LITE = os.getenv("IMAGE_MODEL_LITE", "gemini-3.1-flash-lite-image").strip()

# --- cloudflare workers ai (fallback, optional)
CF_ACCOUNT_ID = os.getenv("CF_ACCOUNT_ID", "").strip()
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "").strip()
#: @cf/black-forest-labs/flux-1-schnell — Workers AI's fast text-to-image
#: model (developers.cloudflare.com/workers-ai/models/flux-1-schnell/, read
#: 2026-09-29). Cloudflare is the FALLBACK provider here and this model does
#: not take reference images the way Gemini does.
CF_IMAGE_MODEL = os.getenv("CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell").strip()
CF_IMAGE_COST_PER_CALL = _f_late("CF_IMAGE_COST_PER_CALL", 0.0)   # Workers AI free-tier eligible

#: Hard ceiling on REAL (non-cache-hit, non-dry-run) image calls for ONE
#: reel — the runaway-cost guard: a bug that keeps regenerating a frame, or a
#: shot list far longer than expected, stops here instead of quietly running
#: up a bill.
#:
#: STEP 6'S FLAT 40 WAS THE WRONG SHAPE, RESTYLE_TO_STORY_REELS.md Step 7
#: Part 0 #1's own fix: a flat number is either too tight for a long `--all`
#: run (23 shots x 2 attempts already needs 46) or too loose for a small
#: `--sample` one, where it stops mattering as a guard at all. The REAL
#: shape of "how many calls could this reel legitimately need" is
#: (image shots x STORY_FRAME_ATTEMPTS) + 1 mascot + a little headroom —
#: computed PER REEL by story_frames.py by calling default_image_budget()
#: below and handing the result to imagegen.set_reel_budget(). This
#: constant is kept as the FALLBACK a caller with no shot count in hand
#: still gets (imagegen.py itself has no notion of "how many shots"), and
#: as the HARD OVERRIDE when IMAGE_MAX_CALLS_PER_REEL is set explicitly in
#: the environment — see IMAGE_MAX_CALLS_PER_REEL_IS_EXPLICIT below, which
#: is what lets story_frames.py tell "the user set this on purpose" apart
#: from "nobody set anything, use the computed default".
IMAGE_MAX_CALLS_PER_REEL_IS_EXPLICIT = os.getenv("IMAGE_MAX_CALLS_PER_REEL") is not None
IMAGE_MAX_CALLS_PER_REEL = _i("IMAGE_MAX_CALLS_PER_REEL", 40)

#: Extra calls above the bare (shots x attempts) + mascot arithmetic —
#: covers a --rejudge-triggered re-render, an off-by-one in shot counting,
#: or a caller who nudges STORY_FRAME_ATTEMPTS up after the budget was
#: already computed once earlier in a session.
IMAGE_CALLS_HEADROOM = _i("IMAGE_CALLS_HEADROOM", 5)


def default_image_budget(n_image_shots: int, attempts: int | None = None,
                         has_mascot: bool = True) -> int:
    """(image shots x attempts) + 1 mascot + headroom — RESTYLE_TO_STORY_
    REELS.md Step 7 Part 0 #1's cap formula, verbatim. story_frames.py calls
    this once per reel and passes the result to imagegen.set_reel_budget();
    IMAGE_MAX_CALLS_PER_REEL_IS_EXPLICIT is what tells it whether to bother
    (an explicit override always wins over this computed default)."""
    attempts = max(1, STORY_FRAME_ATTEMPTS if attempts is None else attempts)
    return n_image_shots * attempts + (1 if has_mascot else 0) + IMAGE_CALLS_HEADROOM


#: RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #3 — the judge is rate-limited to
#: at most this many calls per minute, with backoff-and-retry (never a hard
#: failure) on a 429. 10 is conservative for a free-tier model
#: (MODEL_STORY_VISION_JUDGE's own note on gemini-3.8-flash's free tier) —
#: raise it once real quota limits are known, not guessed.
JUDGE_RPM = _i("JUDGE_RPM", 10)

#: RESTYLE_TO_STORY_REELS.md Step 7 Part 0 #4 — shorts/frame_checks.py's OCR
#: pre-check. A word below this confidence (pytesseract's own 0-100 scale,
#: from image_to_data) is treated as noise, not real text — a stick-figure
#: line or a stray artifact OCRs as low-confidence garbage far more often
#: than real drawn text does.
TEXT_CHECK_MIN_CONFIDENCE = _i("TEXT_CHECK_MIN_CONFIDENCE", 60)
#: A "word" (letters only, digits handled separately against ALLOWED GLYPHS)
#: shorter than this many letters is also treated as noise — a single
#: stray letter-shaped OCR misread (common on thick clean outlines) is not
#: "text in the frame" the way an actual word is.
TEXT_CHECK_MIN_WORD_LENGTH = _i("TEXT_CHECK_MIN_WORD_LENGTH", 2)

#: Build every shot's prompt and write it to <short_id>/image_prompts.json
#: WITHOUT calling any provider — reviewing exactly what would be sent, at
#: zero cost, before paying for a single frame.
DRY_RUN_IMAGES = os.getenv("DRY_RUN_IMAGES", "").strip().lower() in ("1", "true", "yes")

#: RESTYLE_TO_STORY_REELS.md Step 6 — skills.vision.judge_story_frame's model.
#:
#: gemini-3.8-flash — CONFIRMED AGAINST ai.google.dev/gemini-api/docs/pricing
#: on 2026-09-29, not recalled from memory: it is the newest Flash model on
#: that page, multimodal (accepts image input, needed to look at a rendered
#: frame), and one of the few rows on the whole page whose Free Tier reads
#: "Free of charge" rather than "Not available".
#:
#: THAT FREE TIER IS GOOGLE'S OWN DIRECT API — IT DOES NOT APPLY HERE (STEP
#: 9 FIXES ROUND 14). Calls go through llm.ask_json, which routes through
#: OpenRouter (see PLAIN MODEL ID note below), a paid reseller that bills
#: its own real rate regardless of what the underlying model costs through
#: Google directly. A real sample stage showed exactly this: $0.0000
#: estimated, $0.0430 actual. usage.PRICES now has a real, regression-
#: fitted entry for this model (from actual billed OpenRouter calls) — see
#: that table's own note — so preflight estimates for it are no longer
#: silently zero.
#:
#: PLAIN MODEL ID, matching MODEL_GENERATOR/MODEL_JUDGE's own convention
#: elsewhere in this file (see MODEL_GENERATOR's comment on gateway-specific
#: ids) — calls still go through llm.ask_json, the same Anthropic-compatible
#: gateway every other judge in this project uses; on OpenRouter this needs
#: the "google/" prefix (e.g. "google/gemini-3.8-flash"), set via .env, the
#: same way MODEL_JUDGE needs "anthropic/" there.
MODEL_STORY_VISION_JUDGE = os.getenv("MODEL_STORY_VISION_JUDGE", "").strip() or "gemini-3.8-flash"

#: RESTYLE_TO_STORY_REELS.md Step 8 Part 0 #1 — skills.audit.judge_story_
#: metaphors's model (the text-only "does this metaphor actually teach the
#: rule" judge, run once per mapping entry before any shot is written — see
#: that function's own docstring). Was config.MODEL_JUDGE (claude-opus-5);
#: switched to claude-sonnet-5 for this one judge specifically because it
#: grades a small, structured, single-entry-at-a-time judgment (closer to
#: MODEL_GENERATOR's own workload than explainer mode's JUDGE_SYSTEM full-
#: script review) — explainer mode's MODEL_JUDGE stays claude-opus-5,
#: unchanged; this is a story-mode-only switch.
MODEL_STORY_JUDGE = os.getenv("MODEL_STORY_JUDGE", "").strip() or "claude-sonnet-5"

#: How many times story_frames.py's regenerate loop will re-generate ONE
#: shot's frame after a failing pre-check or judge verdict, before giving up
#: and marking it NEEDS_REVIEW — Step 6 Part 3's own budget, separate from
#: (and smaller than) IMAGE_MAX_CALLS_PER_REEL, which caps the WHOLE reel.
#: 2 is deliberately small: a frame that fails twice in a row on the same
#: prompt+FIX-text is more often a prompt problem than bad luck, and a human
#: reviewing a NEEDS_REVIEW shot is cheaper than a 3rd, 4th, 5th blind retry.
STORY_FRAME_ATTEMPTS = _i("STORY_FRAME_ATTEMPTS", 2)

#: RESTYLE_TO_STORY_REELS.md Step 8 Part 1 — shots that share characters,
#: framing, emotion AND key_prop render ONE image and copy it to every
#: other matching shot's own output path (a different shot.camera value,
#: applied as an animation at render time, is what actually distinguishes
#: them on screen — see story_frames._reuse_key). NEVER reused across a
#: "reveal" (story_beat == "reaction" — the same definition checks.
#: check_shot_rhythm already uses for the moment a shot's action changes
#: the key object's visible state), regardless of this setting. On by
#: default; STORY_IMAGE_REUSE=0 renders every shot independently, the
#: pre-Step-8 behavior.
STORY_IMAGE_REUSE = os.getenv("STORY_IMAGE_REUSE", "1").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------- story voices
#
# RESTYLE_TO_STORY_REELS.md Step 7 Part 1. Per-CHARACTER voices — a different
# shape from explainer mode's 2-slot interviewer/student
# (VOICE_INTERVIEWER/STUDENT, KOKORO_VOICE_INTERVIEWER/STUDENT, etc. above,
# all untouched by anything below). shorts/story_audio.py is the only reader.
#: RESTYLE_TO_STORY_REELS.md Step 8 Part 1 — DEFAULT SWITCHED TO chatterbox
#: (voice cloning, more expressive than Kokoro's fixed catalogue). This is
#: only the REQUESTED provider — shorts/story_voices.py's resolve_provider()
#: falls back to Kokoro automatically, per character, whenever Chatterbox is
#: not installed, has no reference clip for that character, or a real synth
#: call raises — logging which provider actually ran every time, never
#: silently. See voice_refs.py for seeding CAST_CHATTERBOX_VOICE's clips
#: from Kokoro so a fresh checkout has SOMETHING to clone before a human
#: ever records a real reference line.
TTS_PROVIDER_STORY = os.getenv("TTS_PROVIDER_STORY", "chatterbox").strip().lower()

#: Kokoro voice id per character — CONFIRMED against THIS MACHINE'S OWN
#: installed voice catalogue (providers._REGISTRY["kokoro"].voices(), 54
#: ids — Kokoro has no fixed/hardcoded voice list to recall from memory, see
#: that method's own docstring) on 2026-09-29, not guessed:
#:   Rahul    am_puck     — young, energetic male
#:   Riya     af_heart    — calm female; already this project's own
#:                          top-graded voice (see KOKORO_VOICE_STUDENT's note)
#:   System   am_michael  — deeper, steady male; already this project's own
#:                          interviewer default
#:   Narrator bm_george   — British male, warm/storytelling register,
#:                          audibly distinct from the other three
_CAST_KOKORO_VOICE_DEFAULT = {
    "Rahul": "am_puck",
    "Riya": "af_heart",
    "System": "am_michael",
    "Narrator": "bm_george",
}
try:
    CAST_KOKORO_VOICE: dict[str, str] = (
        json.loads(os.getenv("CAST_KOKORO_VOICE", "")) if os.getenv("CAST_KOKORO_VOICE")
        else _CAST_KOKORO_VOICE_DEFAULT)
except (json.JSONDecodeError, TypeError):
    CAST_KOKORO_VOICE = _CAST_KOKORO_VOICE_DEFAULT

#: Chatterbox reference CLIP PATH per character — blank by default.
#: Chatterbox is a voice-CLONING provider (see providers.Chatterbox's own
#: docstring): there is no catalogue id to default to, only a recorded clip
#: a human supplies, the same reason CHATTERBOX_VOICE_INTERVIEWER/STUDENT
#: above default to "" too. Blank means "not configured" — story_audio.py
#: fails clearly, per character, rather than silently falling back to
#: something nobody chose.
#: AUTO-DISCOVERED from CAST_VOICE_DIR, not hardcoded blank any more —
#: RESTYLE_TO_STORY_REELS.md Step 8 Part 1's own "wire these into
#: CAST_CHATTERBOX_VOICE" rule: once voice_refs.py has written
#: assets/voices/<name>.wav for a character, every later process picks it
#: up as that character's default Chatterbox clip with no .env edit
#: needed. Still "" for a character voice_refs.py hasn't run for yet —
#: story_voices.resolve_provider falls back to Kokoro for exactly that
#: character in that case (see its own docstring).
def _default_chatterbox_voice(name: str) -> str:
    p = CAST_VOICE_DIR / f"{name.lower()}.wav"
    return str(p) if p.exists() else ""


_CAST_CHATTERBOX_VOICE_DEFAULT = {name: _default_chatterbox_voice(name)
                                  for name in ("Rahul", "Riya", "System", "Narrator")}
try:
    CAST_CHATTERBOX_VOICE: dict[str, str] = (
        json.loads(os.getenv("CAST_CHATTERBOX_VOICE", "")) if os.getenv("CAST_CHATTERBOX_VOICE")
        else _CAST_CHATTERBOX_VOICE_DEFAULT)
except (json.JSONDecodeError, TypeError):
    CAST_CHATTERBOX_VOICE = _CAST_CHATTERBOX_VOICE_DEFAULT

#: shot.emotion -> delivery knobs, one column per provider this project can
#: actually vary delivery on (Kokoro: `speed`, see providers.Kokoro.synth;
#: Chatterbox: `exaggeration`/`cfg_weight`, see providers.Chatterbox.synth
#: and CHATTERBOX_EXAGGERATION/CFG_WEIGHT's own notes on what raising/
#: lowering each one does). Step 7's own rule: shock/frustration slightly
#: FASTER, calm/relief slightly SLOWER — everything else sits close to
#: neutral, nudged toward one side or the other by feel, not measurement
#: (no real audio has been generated against this table yet).
#:
#: AN EMOTION NOT LISTED HERE (a typo, or a new one nobody's added) FALLS
#: BACK TO EMOTION_DELIVERY_DEFAULT rather than raising — reading an
#: unfamiliar emotion as neutral delivery is the safe direction, the same
#: "missed, not wrong" philosophy parse.py's own heading-matching uses.
EMOTION_DELIVERY_DEFAULT = {"kokoro_speed": 1.0, "chatterbox_exaggeration": 0.5,
                           "chatterbox_cfg_weight": 0.5}
EMOTION_DELIVERY = {
    # --- faster: shock / frustration ---
    "frustrated":   {"kokoro_speed": 1.08, "chatterbox_exaggeration": 0.65, "chatterbox_cfg_weight": 0.45},
    "shock":        {"kokoro_speed": 1.10, "chatterbox_exaggeration": 0.70, "chatterbox_cfg_weight": 0.40},
    "surprised":    {"kokoro_speed": 1.08, "chatterbox_exaggeration": 0.65, "chatterbox_cfg_weight": 0.45},
    "determined":   {"kokoro_speed": 1.04, "chatterbox_exaggeration": 0.55, "chatterbox_cfg_weight": 0.50},
    "delighted":    {"kokoro_speed": 1.05, "chatterbox_exaggeration": 0.60, "chatterbox_cfg_weight": 0.45},
    # --- slower: calm / relief ---
    "calm":         {"kokoro_speed": 0.94, "chatterbox_exaggeration": 0.35, "chatterbox_cfg_weight": 0.55},
    "steady":       {"kokoro_speed": 0.97, "chatterbox_exaggeration": 0.40, "chatterbox_cfg_weight": 0.55},
    "relieved":     {"kokoro_speed": 0.95, "chatterbox_exaggeration": 0.40, "chatterbox_cfg_weight": 0.55},
    "gentle":       {"kokoro_speed": 0.92, "chatterbox_exaggeration": 0.30, "chatterbox_cfg_weight": 0.60},
    # --- close to neutral ---
    "confused":     {"kokoro_speed": 0.98, "chatterbox_exaggeration": 0.45, "chatterbox_cfg_weight": 0.50},
    "curious":      {"kokoro_speed": 1.00, "chatterbox_exaggeration": 0.50, "chatterbox_cfg_weight": 0.50},
    "firm":         {"kokoro_speed": 1.00, "chatterbox_exaggeration": 0.50, "chatterbox_cfg_weight": 0.45},
    "friendly":     {"kokoro_speed": 1.00, "chatterbox_exaggeration": 0.50, "chatterbox_cfg_weight": 0.50},
    "confident":    {"kokoro_speed": 1.00, "chatterbox_exaggeration": 0.50, "chatterbox_cfg_weight": 0.50},
    "storytelling": {"kokoro_speed": 0.98, "chatterbox_exaggeration": 0.45, "chatterbox_cfg_weight": 0.50},
    "dramatic":     {"kokoro_speed": 0.96, "chatterbox_exaggeration": 0.55, "chatterbox_cfg_weight": 0.45},
    "neutral":      dict(EMOTION_DELIVERY_DEFAULT),
}


def emotion_delivery(emotion: str) -> dict:
    """The delivery knobs for `emotion`, or EMOTION_DELIVERY_DEFAULT for
    anything not in the table above — see that dict's own note on why an
    unmapped emotion never raises."""
    return EMOTION_DELIVERY.get((emotion or "").strip().lower(), EMOTION_DELIVERY_DEFAULT)


# ----------------------------------------------------------------- story audio
#
# RESTYLE_TO_STORY_REELS.md Step 7 Part 2 — shorts/story_audio.py.
STORY_AUDIO_TARGET_LUFS = _f_late("STORY_AUDIO_TARGET_LUFS", -14.0)
#: Silence between consecutive shots in the mixed track — Step 7's own 0.1s,
#: distinct from (and much shorter than) explainer mode's VOICE_BEAT_GAP
#: (0.45s): a story's shots are a continuous scene, not beat-to-beat topic
#: changes, and cut tighter.
STORY_SHOT_AUDIO_GAP = _f_late("STORY_SHOT_AUDIO_GAP", 0.1)
#: Optional background music bed — blank means none, the ordinary case.
MUSIC_PATH = os.getenv("MUSIC_PATH", "").strip()
#: How far under speech the music is ducked while a shot's line plays.
MUSIC_DUCK_DB = _f_late("MUSIC_DUCK_DB", -18.0)
#: STORY_FRAME_ATTEMPTS-adjacent budget, but for total SPOKEN TIME: past
#: this, story_audio.py marks the reel NEEDS_REVIEW instead of shipping a
#: reel that runs long — see MAX_SECONDS/HARD_MAX_SECONDS above for the
#: same idea already applied to explainer-mode scripts.
STORY_MAX_TOTAL_SECONDS = _f_late("STORY_MAX_TOTAL_SECONDS", 80.0)

#: RESTYLE_TO_STORY_REELS.md Step 8 Part 1 — real per-word timings, via
#: faster-whisper, against the ACTUAL synthesized audio (see story_audio.
#: _whisper_words). "tiny.en" over a bigger model: this project's lines are
#: always short, always English, and the job is finding WORD BOUNDARIES in
#: audio we ourselves just generated cleanly — not open-vocabulary
#: transcription accuracy, which is where a bigger model would earn its
#: extra latency. CPU-only, int8 — no GPU assumed; both are free to change
#: per-environment via env vars.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny.en").strip()
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu").strip()
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip()


# ----------------------------------------------------------- story_reel.py
#
# RESTYLE_TO_STORY_REELS.md Step 9 — shorts/story_reel.py's own hard per-reel
# spend cap, enforced from REAL usage.py totals (not a worst-case estimate)
# before every stage that spends money: the runner refuses to even START a
# stage whose own worst-case pre-flight cost would push the reel's running
# total past this, rather than starting it and discovering the overrun mid-
# stage. A single reel's own budget, not the project's lifetime total.
MAX_REEL_USD = _f_late("MAX_REEL_USD", 2.00)
