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

Remotion needs Node 18+.

```bash
node --version
```

If missing, install from [nodejs.org](https://nodejs.org) (LTS version).

### 0.3 FFmpeg

Used to stitch the audio beats together.

```bash
ffmpeg -version
```

If missing: `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Ubuntu), or download from [ffmpeg.org](https://ffmpeg.org/download.html) and add it to PATH (Windows).

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
| `shorts/llm.py` | The only file that calls the API |
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
 PASS E001   A rambling script is rejected for length      too long: 98.4s (246 words). Need <= 60s
 PASS E002   A thin script is rejected for being too short too short: 6.4s (16 words). Need >= 30s
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

### C.2 Skill 1 — topic selection (first paid call, ~1 cent)

```bash
python -c "
from shorts.parse import parse_markdown
from shorts.skills.select import select_topics
for t in select_topics(parse_markdown('content/session_18_paging.md')).topics:
    print(f'[{t.source_section_id}] {t.id}: {t.topic}')
"
```

**Do not move on until the topic list is good.** Everything downstream inherits these choices. If a topic is too big for 45 seconds, the fix is in `select.py`'s SYSTEM prompt, not further down the pipeline.

### C.3 Skill 2 — the dialogue script

The heart of the project. Read `shorts/skills/script.py` closely — the whole word-budget doctrine lives in that prompt.

```bash
python -m shorts.run content/session_18_paging.md --limit 1 --no-tts --no-svg
```

You'll see the retry loop working:

```
=== os_s18_page_fault — What happens on a page fault?
    [FAIL] timing — too long: 71.2s (178 words). Need <= 60s (~150 words).
    retry 1/3
    [PASS] timing — 44.0s (110 words)
    [PASS] overlays — all 5 overlays within limit
    [PASS] dialogue_shape — 4 student beats
    [PASS] grounding — 68% content-word overlap with source
    script ok: 44.0s, 110 words
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

```bash
cd render
npm install
npx remotion studio
```

The studio opens in a browser with a live preview. Edit `src/Short.tsx` and it hot-reloads — this is where you'll spend time on look and feel.

To render an approved short, from the project root:

```bash
python -m shorts.render <short_id>
```

That copies the props, copies the audio into `render/public/` if the unit has any,
and shells out to Remotion. It **refuses to render anything whose status is not
`approved`** — pass `--force` only when you're debugging the renderer itself. Output
lands in `render/out/<short_id>.mp4`.

**Expect the first render to look bad.** That is fine and expected. Getting one ugly MP4 out is the milestone; polish comes after. Rendering takes minutes, which is exactly why the human gate sits upstream of it.

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
python -m shorts.render <short_id>                     # approved unit -> mp4

cd render && npx remotion studio                       # live preview
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

## Three things that will bite you

**The words-per-minute constant.** 150 is an estimate. Measure it against your actual voice in step C.5 and correct it. Every timing gate depends on this number.

**Character consistency.** Generate the interviewer and student illustrations **once**, approve them, commit them as static assets. Do not generate characters per short — image models cannot hold a character across ten videos.

**Rendering in a web request.** It takes minutes. It must be a background job with a status row in a database. Design for this before you build the feed, not after.
