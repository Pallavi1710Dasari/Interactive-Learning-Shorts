# Interactive Learning Shorts — Build Guide

Work through this in order. **Every step ends with a command you run and a result you check.** If a step's check fails, fix it before moving on. Do not skip ahead to video rendering — the people who skip ahead are the people who never finish.

Total realistic time for Part A through Part F: **2–3 focused days.**

---

## Part 0 — Installations

### 0.1 Python

You need Python 3.11 or newer.

```bash
python3 --version
```

If it prints 3.11 or higher, skip to 0.2. Otherwise install it — on Windows use [python.org](https://python.org) and **check "Add Python to PATH"** during install; on macOS use `brew install python@3.12`; on Ubuntu use `sudo apt install python3.12 python3.12-venv`.

### 0.2 Node.js

The web app (Vite + React) needs Node 18+. It is the player, and the video
renderer photographs it, so this is not optional.

```bash
node --version
```

If missing, install from [nodejs.org](https://nodejs.org) (LTS version).

### 0.3 FFmpeg

Used to stitch the audio beats together and to encode the MP4.

```bash
ffmpeg -version
```

**You can skip this one.** If there is no ffmpeg on PATH, both the audio path and
the renderer fall back to the static build in the `imageio-ffmpeg` wheel, which
`requirements.txt` already installs. Install it system-wide only if you want your
own build: `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Ubuntu), or
[ffmpeg.org](https://ffmpeg.org/download.html) and add it to PATH (Windows).

### 0.4 The project

```bash
cd learning-shorts
python3 -m venv venv
```

A **virtual environment** is a private copy of Python for this project only, so its packages can't break your other projects. Activate it:

```bash
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows
```

Your prompt now starts with `(venv)`. **You must activate it every time you open a new terminal.** If a command fails with "module not found," this is almost always why.

```bash
pip install -r requirements.txt
```

### 0.5 API keys

Get an Anthropic key at [console.anthropic.com](https://console.anthropic.com) → API Keys. Get an ElevenLabs key at [elevenlabs.io](https://elevenlabs.io) → Profile → API Keys, and copy two different **voice IDs** from their Voices page (one for the interviewer, one for the student).

```bash
cp .env.example .env
```

Open `.env` and fill in the real values. `.env` is in `.gitignore` — **never commit it.**

### 0.6 Checkpoint

```bash
python -m shorts.smoke_test
```

This runs offline. No API key needed, no cost. You should see five numbered steps and `ALL OFFLINE CHECKS PASSED`. If you see that, your schema, parser, and graders are wired correctly and you can start spending money with confidence.

### 0.7 The free end-to-end run

`SHORTS_STUB=1` swaps every LLM call for a canned answer built out of the source
doc's own sentences (see `shorts/stubs.py`). It costs nothing and needs no keys:

```bash
SHORTS_STUB=1 python -m shorts.run content/session_18_paging.md --limit 1 --no-tts --no-svg
```

Every grader should pass, because the stub scripts are assembled from real source
text and trimmed to fit the word budget. **If a stub run fails, the bug is in your
code, not in a prompt** — which is the whole reason it exists. Do this before Part A.

---

## Part A — Understand the shape before you write anything

Nine files matter. Read them in this order, it takes 20 minutes and saves you a day:

| File | What it is |
|---|---|
| `shorts/schema.py` | **Read this first.** The data contract. Every step consumes one of these models and produces another. |
| `shorts/parse.py` | Markdown → `Section` objects with line numbers |
| `shorts/checks.py` | The code graders. Free, instant, deterministic. |
| `shorts/llm.py` | The only file that calls the API. **Read the docstring** — it explains why adaptive thinking is off by default. |
| `shorts/skills/select.py` | Skill 1 — pick the topics |
| `shorts/skills/script.py` | Skill 2 — write the dialogue. **Highest-leverage prompt in the project.** |
| `shorts/skills/visuals.py` | Skills 3 & 4 — spec visuals, generate SVG |
| `shorts/skills/audit.py` | Skill 5 — code graders, then the LLM judge |
| `shorts/run.py` | The orchestrator. Plain Python. ~120 lines. No framework. |

The thing to internalise: **there is no agent framework here.** `run.py` is a for-loop with two retry loops inside it. That is what people mean by "agentic pipeline" 90% of the time. Add LangGraph only when you need durable state and interrupts, which is V1.5.

---

## Part B — Eval sets (do this BEFORE writing prompts)

This is the part people skip and then regret. Read this section twice.

### B.1 What an eval case actually is

An eval case is **a frozen failure plus the assertion that it must never come back.** That's it. It has four parts:

```yaml
- id: E004
  name: Overlay text longer than 8 words is rejected
  why: "Reviewer found on-screen text spilling off a phone screen in short 3."
  type: code_grader
  grader: overlays
  fixture: evals/fixtures/overlay_too_wordy.json
  expect:
    passed: false
    reason_contains: "over 8 words"
```

The `why` field is not documentation — it's the most important field. Six months from now someone will look at a failing case and want to delete it. The `why` is what stops them.

### B.2 The three kinds of case

**Code grader cases** — deterministic. Free, run in milliseconds, run them constantly. These cover anything countable: word budgets, overlay length, beat counts, schema shape, missing references. **About 70% of your eval set should be this kind**, because 70% of LLM failures are countable.

The two most valuable ones here are countable in a way that is not obvious:

- `source_quotes` — every answer beat carries the sentence of the section it
  restates, and the grader checks that sentence really occurs there. It turns "is
  this grounded?" from a judgement call into a substring test. This is what catches
  the failure `grounding` cannot see: a confident, on-topic, wrong answer built out
  of the material's own vocabulary. E012/E013 are the pair that guard it.
- `svg_quality` — a diagram model cannot see what it drew, so it cannot notice a
  label that overflows its box, a rotated caption, or two labels printed on top of
  each other. All three are visible in the markup, so they are checked for free and
  handed back as a redraw instruction.

**LLM judge cases** — need meaning. "Is this faithful to the source?" can't be counted. Costs an API call per case, so run these before merging, not on every save.

**Golden cases** — a known-good output frozen as a regression guard. "Skill 1 must still select sections 3.2 and 3.3 from session 18." Catches silent drift when you edit a prompt.

### B.3 The rule most people get wrong

**For every case that asserts a failure, write a case that asserts a success.**

Look at the eval set: E001 says "too long is rejected," and E003 says "correct length is accepted." E006 says "invented content is caught," and E007 says "grounded content passes."

Without the second kind, the cheapest way to make your evals green is to make your grader reject everything. You will do this accidentally. The pairs are what stop you.

### B.4 How to seed the first set when you have no failures yet

You have no production failures on day one, so **manufacture them.** Generate 10 scripts with a deliberately vague prompt, read all 10, and write down every way they were wrong. That list *is* your eval set. The six fixtures in `evals/fixtures/` came from exactly this exercise:

| Fixture | The failure it freezes |
|---|---|
| `too_long.json` | Model ignored the word budget — 246 words, 98 seconds |
| `too_short.json` | Model over-corrected after a prompt tightening — 16 words |
| `overlay_too_wordy.json` | 15-word on-screen text, unreadable on a phone |
| `monologue.json` | One giant student beat, so visuals never change |
| `hallucinated.json` | Invented Linux page sizes and a fake Google benchmark |
| `good_page_fault.json` | The known-good baseline every "should pass" case uses |

Five to ten cases is the right size to start. Do not try to write forty.

### B.5 Run it

```bash
python -m evals.run_evals
```

Free and offline — code graders only:

```
 PASS E001   A rambling script is rejected for length      too long: 98.4s (246 words). Need <= 45s
 PASS E002   A thin script is rejected for being too short too short: 6.4s (16 words). Need >= 18s
 PASS E003   A well-sized script passes the timing gate    38.0s (95 words)
 PASS E004   Overlay text longer than 8 words is rejected  2 overlay(s) over 8 words
 PASS E005   A single-paragraph answer is rejected         only 1 student beat(s)
 PASS E006   Content invented outside the source is caught only 4% of content words appear in source
 PASS E007   A grounded script passes the grounding check  72% content-word overlap with source
7 passed, 0 failed, 3 skipped
```

With the paid judge cases:

```bash
python -m evals.run_evals --judge
python -m evals.run_evals --only E008        # one case while debugging
```

### B.6 A real bug this eval set already caught

When I first wrote `schema.py`, `Beat.on_screen` had a validator rejecting overlays over 8 words. Case E004 then failed — not because the grader was broken, but because the fixture **couldn't even load**. Pydantic threw a `ValidationError` before `check_overlays` ever ran.

The lesson, now a comment in `schema.py`:

> **The schema's job is "can this be represented." The grader's job is "is this good."**

If your schema rejects bad LLM output, you get an exception instead of a diagnosis, you can't write an eval case for the failure, and you can't feed the reason back to the model for a retry. Keep validation that *enforces quality* in graders. Keep validation that *enforces structure* in the schema.

### B.7 The loop that makes this compound

```
something looks wrong in output
  -> save the exact bad output as a fixture
  -> write a case asserting it must fail
  -> confirm the case FAILS (proving it reproduces the bug)
  -> fix the prompt or the grader
  -> confirm the case PASSES
  -> never think about that bug again
```

Confirming the case fails first is the step everyone skips. A case that passes before you fix anything is testing nothing.

---

## Part C — Build the pipeline, one step at a time

### C.1 Parse (no AI, no cost)

```bash
python -m shorts.parse content/session_18_paging.md
```

```
3.1      Why paging exists                     lines 3-10   418 chars
3.2      Address translation and the page table lines 11-17 355 chars
3.3      The page fault path                   lines 18-24  345 chars
```

Now run it on **your real reading material.** Your OS-course docs use section IDs already, which is why the parser keys on them. If your headings are formatted differently, this is the one file you'll need to adjust — the regex is at the top of `parse.py`.

**Section ids are guaranteed unique, and that matters more than it sounds.** Every
later step names a section by id, so two sections sharing one means a topic can be
handed the wrong source text — and a topic handed the wrong source text produces a
short that refuses to answer or invents. A real HTML doc did exactly this:

```
## 1. Basic Structure   ## 2. Heading Element   ## 3. Paragraph Element
### 1. What is HTML?    ### 2. How do you...    ### 3. What are header and headings?
```

The FAQ subsections restart their numbering, so `### 3` collided with `## 3`. Skill 1
correctly picked the head-vs-headings question and cited section 3; the writer was
handed the paragraph-element section and, obeying the stay-inside-the-source rule,
correctly refused to answer. So: a numbered subsection under a numbered section is
qualified by its parent (`4` + `3` → `4.3`), and anything still colliding gets an
occurrence suffix (`3` → `3-2`). Expect to see ids like `3-2` on documents with an
FAQ; that is the parser keeping them apart, not a bug.

Two guards sit behind it, because a mis-citation is always possible: `write_script`
is given the **whole** document alongside its section, so an answer that lives in a
summary elsewhere is still findable; and `check_no_refusal` rejects any script that
talks about its source instead of teaching (E014/E015).

### C.2 Skill 1 — topic selection (first paid call, ~1 cent)

```bash
python -c "
from shorts.parse import parse_markdown
from shorts.skills.select import select_topics
for t in select_topics(parse_markdown('content/session_18_paging.md')).topics:
    print(f'[{t.source_section_id}] {t.id}: {t.topic}')
"
```

**Do not move on until the topic list is good.** Everything downstream inherits these choices. If a topic is too big for 25 seconds, the fix is in `select.py`'s SYSTEM prompt, not further down the pipeline.

### C.3 Skill 2 — the dialogue script

The heart of the project. Read `shorts/skills/script.py` closely — the whole word-budget doctrine lives in that prompt.

```bash
python -m shorts.run content/session_18_paging.md --limit 1 --no-tts --no-svg
```

You'll see the retry loop working:

```
=== os_s18_page_fault — What happens on a page fault?
    [FAIL] timing — too long: 71.2s (178 words). Need <= 45s (~112 words).
    retry 1/3
    [PASS] timing — 25.6s (64 words)
    [PASS] overlays — all 5 overlays within limit
    [PASS] dialogue_shape — 4 student beats
    [PASS] grounding — 68% content-word overlap with source
    script ok: 25.6s, 64 words
```

That failed-then-passed sequence is the agentic part of the system. Note what it cost: one extra text call, because the timing check ran before voice and rendering.

**Now generate 10 and read all 10.** This is the highest-value hour in the whole project. Every flaw you spot becomes a fixture in `evals/fixtures/` and a case in `cases.yaml`.

### C.4 Visuals

```bash
python -m shorts.run content/session_18_paging.md --limit 1 --no-tts
```

Open the generated SVG and check it. For a page table diagram, verify the valid bit is actually shown as clear if the narration says it's clear. **This is the same diagram QA you already do on slides** — the difference is you can fix the prompt once instead of fixing every diagram by hand.

### C.5 Voice

Verify your TTS provider returns **word-level timestamps** before writing any sync code. Without them everything after this is guesswork.

```bash
python -c "
import json
from shorts.schema import Script
from shorts.tts import synthesize
s = Script(**json.load(open('evals/fixtures/good_page_fault.json')))
a = synthesize(s)
print(f'{a.duration_seconds}s, {len(a.word_timings)} word timings')
print(a.word_timings[:5])
"
```

Compare `duration_seconds` against the script's `estimated_seconds`. If your estimate was 38s and reality is 52s, your words-per-minute constant is wrong for your chosen voice — **change `WORDS_PER_MINUTE` in `schema.py` to match measured reality.** Do this once, early, with real audio. Every timing check downstream depends on it.

### C.6 Full pipeline

```bash
python -m shorts.run content/session_18_paging.md --topics 5
```

Writes one JSON per short into `output/`, plus `manifest.json`.

### C.7 The human gate

```bash
python -m shorts.review
```

Prints each short as text — beats, overlays, visual specs, judge scores — and asks approve / reject / skip. **You are reading a script, not watching a video.** Twenty seconds per short. Nothing renders until status is `approved`.

---

## Part D — Render

**The player in the browser is the design.** There is no separate composition to
keep in sync: `web/src/ReelStage.tsx` is the picture, the player and the renderer
both draw it, and the renderer photographs that page one frame at a time. So an MP4
and the reel you watched cannot drift apart.

For look-and-feel work, edit the player and watch it live:

```bash
cd web && npm run dev        # :5173, proxies the API to :8000
```

Rendering needs two things to be true first — the renderer photographs the **built**
app, and a page has to be served to be photographed:

```bash
cd web && npm run build
python -m shorts.server      # leave running in its own terminal
```

Then, from the project root:

```bash
python -m shorts.video <short_id>
```

Output lands in `output/<short_id>/reel.mp4`. It is cached, and rebuilt only when
the MP4 is missing, when the unit JSON is newer than the video, or when you pass
`--force`. The flags worth knowing: `--fps` (default 30), `--workers` (browsers
capturing in parallel, default 3), `--base-url` (default `http://127.0.0.1:8000`).

**Budget about six seconds of wall clock per second of video** — a 12s short takes
roughly 72s, a 22s short about 130s. That is the price of thirty real frames per
second instead of one still per beat, and it is paid once per short. The download
button in the web UI runs this exact code and blocks for exactly as long, so
pre-rendering from the terminal is usually the nicer way to wait.

---

## Part E — The feed

A vertical scrolling feed is about 40 lines of React. The two pieces that matter:

- `scroll-snap-type: y mandatory` on the container and `scroll-snap-align: start` on each item, which gives you the reels snap for free
- `IntersectionObserver` to play the video that's in view and pause the others

For feedback capture, log four things per view: **watch percentage, the timestamp where they dropped off, whether they rewatched, and a "confusing" tap.** The drop-off timestamp is the valuable one — it points at the exact sentence that lost them.

---

## Part F — Closing the loop

Once shorts are in front of learners, feedback improves generation in two concrete ways. Neither is fine-tuning:

**Few-shot examples.** Take the shorts with the highest completion rate and paste 2–3 of them into `script.py`'s prompt as examples. This is the single highest-return change you can make and it takes ten minutes.

**Prompt fixes from failure patterns.** If drop-off consistently clusters at beat 4, your scripts are too long in practice regardless of what the word count says — lower `MAX_SECONDS`. Every pattern becomes a rule in the prompt and a case in the eval set.

Consider fine-tuning only after several hundred human-reviewed examples, and probably not even then.

---

## Command reference

```bash
source venv/bin/activate                              # every new terminal

python -m shorts.smoke_test                           # offline, free — run first
python -m evals.run_evals                             # code graders, free
python -m evals.run_evals --judge                      # + LLM judge, costs money
python -m evals.run_evals --only E004                  # one case

python -m shorts.parse <doc.md>                        # inspect parsing
SHORTS_STUB=1 python -m shorts.run <doc.md> --limit 1 --no-tts --no-svg   # free, no key
python -m shorts.run <doc.md> --limit 1 --no-tts --no-svg   # cheapest paid test
python -m shorts.run <doc.md> --gate-topics            # stop after topic selection
python -m shorts.run <doc.md> --topics-file output/topics.json   # resume from approved list
python -m shorts.run <doc.md> --topics 5               # full pipeline
python -m shorts.review                                # human gate
python -m shorts.video <short_id>                      # approved unit -> mp4

cd web && npm run dev                                  # live preview of the player
```

---

## Order of operations, compressed

1. Installs, then `smoke_test` passes
2. Read `schema.py`
3. **Write the eval set before tuning any prompt**
4. Parser works on your real docs
5. Skill 1 gives topics you'd actually approve
6. Skill 2 + the timing check — generate 10, read all 10, add fixtures
7. Measure real audio duration, fix `WORDS_PER_MINUTE`
8. One ugly MP4 end to end
9. Then, and only then, make it look good

## Length: short on purpose

The window is **18–45 seconds**, target ~26s (about 65 words), in `schema.py`. It
was 30–60, and the floor was actively making shorts worse: a question whose honest
answer is three sentences had to be inflated to 75 words to clear it, and the extra
beat was always the weakest — a restatement, or a claim propped up by a citation
that did not really support it. E016 freezes one of those padded scripts.

Two graders keep the pressure off:

- `source_quotes` also requires **distinct** evidence per beat (one repeat allowed,
  for a closing takeaway). Three beats resting on one sentence is padding, and that
  is countable even though "does this quote support this claim" is not.
- `on_topic` requires at least one beat to quote the section the short is filed
  under. `write_script` gets the whole document so it can answer instead of refuse,
  and this is what stops it wandering onto adjacent material (E017/E018).

If a topic genuinely cannot be answered in 45 seconds it is too big for one short,
and the fix belongs in `select.py`, not in the length window.

## Which model runs where

Four roles, set in `.env`, and they should not all be the same model:

| role | env var | what it does |
|---|---|---|
| generator | `MODEL_GENERATOR` | topic selection and script writing |
| diagram | `MODEL_DIAGRAM` | the SVG calls — 4-5 per short, the biggest line on the bill |
| judge | `MODEL_JUDGE` | scores faithfulness; must be a DIFFERENT family from the generator |
| cheap | `MODEL_CHEAP` | throwaway calls |

**The judge belongs to another family.** A model scoring its own family's writing
marks it generously, and catching fabrication is the entire reason that call exists.

**The diagram model should be one that can turn reasoning off.** By the time the
SVG call runs, the visual spec has already decided what the frame contains — the
call is formatting, not deliberation. On one identical frame:

```
openai/gpt-5-mini              3915 output tokens   7 shapes   0 defects   37s
google/gemini-3.1-flash-lite    868 output tokens   6 shapes   0 defects    3s
```

Same quality by every check available, for a fifth of the tokens and a twelfth of
the wall clock, because the gpt-5 family cannot be told to stop reasoning and
spends ~3300 tokens laying out boxes.

## Two knobs that decide speed and cost

**Adaptive thinking, and why it is not portable.** `shorts/llm.py` sends
`thinking: disabled` on every call except the judge. Measured on the real script
prompt: **30.5s and 2734 output tokens with thinking on, 8.9s and 544 without**,
with the graders scoring the output no differently. Thinking earns its keep when
the model has to reason to an answer; filling a fixed JSON shape from a source
section is not that. It was also a bug — thinking tokens come out of `max_tokens`,
so a long deliberation on a 2000-token budget spent the whole allowance before the
text block started and the response came back empty, which surfaced as a 500 on
`/api/scripts`.

"Thinking off" is an Anthropic spelling and the families answer it differently, so
never hand-write `thinking={...}` at a call site — ask `llm._reasoning(model, think)`:

| family | disabling reasoning |
|---|---|
| `anthropic/*` | works, and is the big win above |
| `openai/gpt-5*` | **400 error** — "Reasoning is mandatory and cannot be disabled". Asks for the smallest budget instead |
| `google/*` | works, and matters: 38 output tokens against 194 on the same one-line answer |

Turn it back on for a call by passing `think=True` to `ask_json`.

**What runs concurrently.** `/api/finalize` starts the judge and the voice before
drawing the diagrams and collects them afterwards, because neither depends on the
pictures. Their latency is absorbed rather than added, which is why a short with 5
diagrams plus an Opus judge finalises in about 30s instead of 60.

## The voice

**A recorded track is the narrator**, rendered once at build time and cached in
`output/<short_id>/`, so watching is instant and a re-watch costs nothing.

Four backends, in `shorts/providers.py`. `TTS_PROVIDER=auto` takes the best one
whose credentials actually work, so adding a key upgrades the voice and nothing else
changes:

| provider | needs | notes |
|---|---|---|
| `elevenlabs` | API key | Best sounding. Paid beyond a small free tier. |
| `kokoro` | nothing | Kokoro-82M on onnxruntime. Local, offline, free, no quota, and close enough to the cloud tiers to be the sensible default. One-off ~330MB model download. |
| `google` | API key | Very close, ~1M free chars/month, plain API key — no service-account JSON. |
| `piper` | nothing | The floor. Also local and free, a clear step below Kokoro, but much smaller — worth keeping for CI and for anyone who does not want 330MB on disk. |

With everything blank you get Kokoro, which needs no signup at all.

Kokoro is deliberately the ONNX build rather than the official `kokoro` package: that
one depends on torch, several gigabytes for an eighty-two-million-parameter model.
`kokoro-onnx` reuses onnxruntime and bundles espeak inside the wheel, so there is
nothing to `apt install`. Voice ids encode accent and gender in the prefix —
`a`=American, `b`=British, `f`=female, `m`=male, `h`=Hindi — and `--check` lists all 54.

**Kokoro voices can be blended**, which is how this project gets an accent the pack
has no voice for. A Kokoro voice is not a model, it is a `(510, 1, 256)` style tensor
conditioning a shared one, so a weighted average of two is a coherent third voice:

```bash
KOKORO_VOICE_STUDENT=af_bella+hf_beta            # equal parts
KOKORO_VOICE_STUDENT=af_bella:0.6+hf_beta:0.4    # weighted
```

Kokoro ships no Indian English. The Hindi voices reading English smear the stops —
a muddy "t" — and the American ones read as American; 60/40 between them lands close
to Indian English with clean articulation, and the ratio is a continuous dial rather
than a choice between two ends. Blending is interpolation, not a trained accent, so
it degrades near an even split on voices this far apart; render a ladder and pick by
ear with `python -m shorts.voicesample --only kokoro`. For properly-trained Indian
English, Google's `en-IN` voices are in the candidate list and need only a key.

Phonemisation is separate from voice, via `KOKORO_LANG`. espeak has no `en-IN`, so
`en-gb` is the only other English phonology available and is worth an A/B when
consonants sound wrong.

```bash
python -m shorts.voice --check          # every provider, and whether it can really speak
python -m shorts.voice --all            # backfill every unit
python -m shorts.voice <id> --force     # re-record one after tuning
python -m shorts.voice --all --provider google
```

### Choosing a voice

```bash
python -m shorts.voicesample            # same short, every candidate voice
python -m shorts.voicesample --only google --force
```

Renders the same real short in each candidate — Neural2, Studio, Chirp 3: HD, Piper,
ElevenLabs — and writes a page at `/voice-samples/` that plays them back to back with
the words underneath. Choosing a voice is a listening decision and the only honest way
to make it is the same sentences in each candidate; a voice that sounds fine reading a
marketing line can fall apart on "the MMU raises a page fault trap". It writes nothing
into a unit and changes nothing about what the pipeline uses — set `TTS_PROVIDER` and
the voice ids in `.env` once you have picked.

Google's tiers do not take the same parameters, and getting it wrong is a hard 400
rather than a warning: **Chirp 3: HD rejects `pitch`** outright, being a different
synthesis stack from Neural2/WaveNet/Studio. So the pitch separation between the two
speakers is applied where it exists and omitted where it does not, and an unexpected
rejection of any tuning field retries flat rather than losing the audio.

`--check` **synthesises a dozen characters per provider** rather than just looking at
credentials. That distinction is not academic: a valid ElevenLabs key on a free
account behind a shared office IP lists voices, reports a subscription, and returns
401 `detected_unusual_activity` for every synthesis. It reported "configured: True"
right up until the first real beat failed. Under `auto`, a provider that refuses is
remembered and the next one takes over.

Three things do the work of making it sound like a person rather than a reader:

- **Clause-based phrasing.** `shorts/speech.py` splits each beat at clause
  boundaries and repunctuates it — a comma is a breath, an ellipsis is the beat of
  thought before a "so..." or a "but...". ElevenLabs infers prosody from
  punctuation, so where those fall *is* the phrasing. It also speaks notation out,
  because `2^3` read literally is "two caret three". This is the same splitting the
  browser version used, repurposed: there each clause became its own utterance,
  because the Web Speech API gives you no other handle on phrasing.
- **Low stability.** The counter-intuitive knob: high stability makes the model
  hedge toward a flat, even read. `VOICE_STABILITY` defaults to 0.40 so pitch and
  pace move inside a sentence, which is what conversation does.
- **Per-speaker delivery.** The interviewer is asking, so slightly quicker and more
  expressive; the student is explaining, so steadier. Same settings for both is what
  made the old browser version sound like one person reading both halves.

Voice ids are **optional** for every provider — ElevenLabs picks two contrasting
voices from your library on first use and prints them; the others have sensible
defaults. A mistyped id is a 404 on every beat, and it was the most common way this
failed.

`window.speechSynthesis` is still in `web/src/speech.ts` but is now only the
**fallback**, for a unit with no recorded track. No provider working at all
downgrades to it rather than losing a short you have already paid for and approved.

**Beat timings are measured, not requested.** The first version asked ElevenLabs for
character-level alignments, which tied the pipeline to one vendor's optional response
field — Google returns nothing of the kind and Piper has no concept of it. Each beat
is synthesised separately, so its duration is just the length of its own audio, which
every provider gives you free. Those measured spans live in `Audio.beat_spans` and
are what the player cuts on; `word_timings` is now an even spread within each beat and
is explicitly labelled an approximation, so don't build anything load-bearing on it.

Joining the beats needs ffmpeg; `imageio-ffmpeg` is in `requirements.txt` and ships a
static binary inside the venv, so no `sudo` install is required. Every chunk is
normalised to 44.1kHz mono before joining, because Piper returns 22kHz WAV and the
cloud providers 44.1kHz MP3 — concatenating those unnormalised gives you a file whose
later beats play at the wrong speed.

## Three things that will bite you

**The words-per-minute constant.** 150 is an estimate. Measure it against your actual voice in step C.5 and correct it. Every timing gate depends on this number.

**Character consistency.** Generate the interviewer and student illustrations **once**, approve them, commit them as static assets. Do not generate characters per short — image models cannot hold a character across ten videos.

**Rendering in a web request.** It takes minutes. It must be a background job with a status row in a database. Design for this before you build the feed, not after.
