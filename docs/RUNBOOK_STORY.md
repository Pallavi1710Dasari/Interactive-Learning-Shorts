# Story Reel Runbook

A plain-language guide to building one "story mode" reel — a short, illustrated
scene (not a talking-head explainer) — from a markdown document, using
`python -m shorts.story_reel`. You do not need to read any other file in this
repo to follow this guide, but you do need a terminal open in the project
folder with its Python virtual environment active (`source venv/bin/activate`).

---

## 1. One-time setup

Do this once per machine, not once per reel.

### 1a. API keys

Copy `.env.example` to `.env` if you have not already, then fill in:

- **`ANTHROPIC_API_KEY`** — required. Every text step (picking the metaphor,
  writing the shots, judging both) goes through this. If your key is actually
  an OpenRouter key, that still works: also set `ANTHROPIC_BASE_URL` to your
  gateway's URL, and `ANTHROPIC_API_KEY` to the same key.
- **Image key** — you need ONE of these, matching `IMAGE_PROVIDER` in `.env`:
  - `GEMINI_API_KEY` (the default, `IMAGE_PROVIDER=gemini`) — this is what
    actually draws the frames, and is the only provider that can look at a
    reference sheet to keep a character's face consistent shot to shot.
  - `CF_ACCOUNT_ID` + `CF_API_TOKEN` (`IMAGE_PROVIDER=cloudflare`) — free, but
    cannot take a reference image, so character consistency will suffer.

The runner checks these for you and refuses to start with a clear message if
one is missing — see §2.

### 1b. tesseract (optional, but recommended)

This is a free, local tool that checks a generated frame for accidental text
(nobody asked for a word to appear on a drawing, and it sometimes does). It is
**not required** — the runner just skips that one check and warns you if it's
missing. To install it: `sudo apt-get install tesseract-ocr` (Debian/Ubuntu),
`brew install tesseract` (Mac), or download it for Windows. Then re-run the
reel — no code change needed.

### 1c. Your logo

Put a PNG at `assets/brand/logo.png`. Any size works — it's scaled to about
14% of the frame width automatically. If you skip this, every reel shows a
plain grey circle in its place instead, which is a fine placeholder for
testing but not something you want in a published reel.

### 1d. Your handle

Set `BRAND_HANDLE` in `.env` to your real social handle, e.g.
`BRAND_HANDLE=@your_real_handle`. Until you do, every reel's "Follow" card and
watermark shows the placeholder `@learnthesimpleway` — the runner warns you
about this every time, on purpose, so it's hard to publish by accident.

### 1e. Cast sheets

Three of the four characters (Rahul, Riya, System — the Narrator is a voice
only, never drawn) need one approved reference image each, so every shot of
them looks like the same character. **You do not have to do this by hand
ahead of time** — if any are missing, the runner offers to build them for you
the first time you run a reel (see §5 below). If you'd rather do it once,
up front, for every future reel: `python -m shorts.cast_sheets --candidates 3
--character rahul --yes`, look at the 3 candidates it writes under
`output/cast_candidates/`, then `python -m shorts.cast_sheets --approve
rahul <number>`. Repeat for `riya` and `system` (Riya and System will
automatically use Rahul's approved sheet as a style reference, so approve him
first).

### 1f. Voice choice

Nothing to do here unless you want to. By default the runner speaks every
character with **Chatterbox** (a voice-cloning engine, more expressive) if a
reference clip exists for that character, and falls back to **Kokoro** (a
fixed-catalogue engine, always available, no setup) automatically and
silently if it doesn't — you'll see a line like `voice: no chatterbox
reference clip configured for Riya — falling back to kokoro` when that
happens, which is informational, not an error. To give every character a
real cloned voice instead of Kokoro's stock one: `python -m shorts.voice_refs
--from-kokoro` seeds a starting clip for each character from Kokoro itself
(free, local, ~1 minute); replace any of the four files it writes under
`assets/voices/` with a real recording later if you want an even better
clone — the runner never overwrites one you've already got unless you pass
`--force`.

---

## 2. Running a reel

```
python -m shorts.story_reel path/to/your_document.md
```

That's it for a single, interactive run — the runner will:

1. Print a **prerequisite checklist**. If anything from §1 is missing in a
   way that would actually stop the reel (a missing API key), it stops right
   here with an `X` next to the problem and does not spend anything. Anything
   it can work around (missing cast sheets, missing voice clips, missing
   logo, the placeholder handle, missing tesseract) prints as a `!` warning
   and the run continues.
2. Offer to build any missing cast sheet (§1e) if needed.
3. Walk through 8 stages, one at a time: **setup → mapping → shots → sample
   → frames → audio → render → report**. Four of them (mapping, shots,
   sample, frames) cost real money and **pause** before spending it, showing
   you exactly what it's about to cost and asking `[y/N]`. After the money is
   spent, most of those same four stages pause AGAIN to show you what came
   back (the chosen metaphor, the full script, the sample frames, the final
   frames) and ask you to approve before moving on.
4. If you say `N` at any pause, the run **stops cleanly** — nothing after
   that point happened, and (for mapping/shots/sample) even that stage's own
   output is discarded, not just left half-done. Nothing is lost from
   earlier, already-approved stages.

### Running it again (resuming)

Every stage's output is saved to disk under `output/<short_id>/` the moment
you approve it. To pick back up where you left off:

```
python -m shorts.story_reel path/to/your_document.md --topic <short_id>
```

The `short_id` is printed right after the setup stage the first time
(`=== setup complete: short_id=... ===`) — copy it from there. The runner
loads every stage you already approved straight from disk (no re-spending)
and resumes the pause loop at the first stage that isn't done yet.

If you said `N` at a pause, that stage's own work was discarded (see above),
so resuming shows you that SAME pause again — it recomputes it (mapping and
shots recompute for real, i.e. spend again; sample/frames usually don't,
because identical prompts are a free cache hit).

### Running it unattended (`--yes`)

```
python -m shorts.story_reel path/to/your_document.md --yes
```

Every pause is answered "yes" automatically — every pre-flight cost summary
still prints (so you have a record of what was spent), but nothing waits for
you. Use this once you trust a document to produce good reels without
watching every stage, or in a script/cron job. It still refuses to start at
all if a real prerequisite (an API key) is missing, and it still refuses to
start a stage that would blow the per-reel budget (see §7).

### Jumping to or redoing a specific stage

- `--from <stage>` starts the stage loop AT that stage, trusting everything
  before it is already done without even checking. Use this if you know
  exactly where you left off and want to skip the (harmless, but slightly
  slower) disk checks. Needs `--topic <short_id>`.
- `--force-stage <stage>` redoes that ONE stage from scratch — spending money
  again if it's one of the four money stages — even though its output
  already exists, and every stage after it too (since their inputs would
  otherwise be stale). Use this if you want to try a different mapping, or
  regenerate the whole shot list, without starting the entire reel over.

Stage names, in order: `setup`, `mapping`, `shots`, `sample`, `frames`,
`audio`, `render`, `report`.

---

## 3. What each pause shows, and what to look for

**Mapping** — the ONE central metaphor the whole reel is built around (e.g.
"a counter that keeps resetting"), plus the 3 candidate metaphors that were
scored and why this one won, plus the hook line the reel opens on, plus every
"technical rule → story beat" mapping entry. **Look for**: does the metaphor
actually behave like the rule, with nothing extra implied? Is the hook line
something you'd actually stop scrolling for?

**Shots** — the entire reel read aloud as plain text, one line per shot
(`Speaker: line`), plus the total runtime and every automated check's
verdict. **Look for**: does it read naturally, not like an interview? Is the
runtime in the 60–80s range? Are all the checks `PASS`?

**Sample** — 5 representative frames (one wide shot, one close-up, etc.),
each with its pass/fail judge score. This is your cheap early warning before
paying for all ~25. **Look for**: does the character actually look like the
approved cast sheet? Does the art style match?

**Frames** — how many of the (typically ~23) image shots passed vs. need
review, with the list of any that need review. If any do, you get a menu:
`approve` (ship them as-is), `rejudge <shot_id>` (re-run the free+paid checks
on the SAME already-generated pixels — useful if you changed the rubric, or
just want a second opinion), `regenerate <shot_id>` (pay for a fresh image of
just that one shot), or `stop`.

**Report** — printed at the very end, and also saved to
`output/<short_id>/run_report.json` — see §6.

---

## 4. Redoing one shot

If a specific shot's frame looks wrong after the frames stage (or even
later — you noticed it in the finished MP4), you have two ways to fix it:

- **From the frames pause itself**, while it's on screen: type
  `regenerate <shot_id>` (e.g. `regenerate s0_reveal_close`).
- **After the fact**, once everything's already finished: run
  `python -m shorts.story_frames <short_id> --rejudge <shot_id>` to re-check
  an existing frame for free, or re-run
  `python -m shorts.story_reel <doc> --topic <short_id> --force-stage frames`
  to redo the WHOLE frames stage (this also re-spends on every shot that
  doesn't hit the cache, not just the one you care about — prefer the
  frames-pause `regenerate` option for a single shot).

Either way, once you're happy with the frame, re-run the reel from `render`
onward (`--from render`, or just `--force-stage render`) to bake it into a
fresh MP4.

---

## 5. Where outputs are

Everything for one reel lives under `output/<short_id>/`, plus two files
next to it:

```
output/<short_id>.mapping.json      the approved metaphor mapping
output/<short_id>.story.json        the approved shot-by-shot script
output/<short_id>/setup.json        which topic/section this reel is about
output/<short_id>/frames/           every generated PNG + judge.json
output/<short_id>/image_prompts.json  the exact prompt sent for every shot
output/<short_id>/sample.done       marker: the sample stage was approved
output/<short_id>/frames.done       marker: the frames stage was approved
output/<short_id>/timings.json      real measured per-shot/per-word timing
output/<short_id>/audio/mix.wav     the final mixed narration track
output/<short_id>/reel_STORY.mp4    the finished video (named reel_STORY.mp4,
                                     not reel.mp4, so it's unmistakable from
                                     an explainer-mode reel at a glance)
output/<short_id>/run_report.json   spend + NEEDS_REVIEW summary (see §6)
output/<short_id>/preflight.json    every pre-flight estimate this reel showed
```

---

## 6. Reading `run_report.json`

```json
{
  "short_id": "how_usestate_remembers_a_value",
  "total_cost": 0.94,
  "total_calls": 34,
  "by_stage": {
    "setup":   {"cost": 0.01, "calls": 2},
    "mapping": {"cost": 0.03, "calls": 2},
    "shots":   {"cost": 0.07, "calls": 1},
    "sample":  {"cost": 0.17, "calls": 6},
    "frames":  {"cost": 0.67, "calls": 21},
    "audio":   {"cost": 0.00, "calls": 0},
    "render":  {"cost": 0.00, "calls": 0}
  },
  "by_model": {
    "claude-sonnet-5": {"calls": 5, "cost": 0.11},
    "gemini-3.1-flash-lite-image": {"calls": 27, "cost": 0.91}
  },
  "needs_review": [],
  "reel_mp4": "/full/path/to/output/.../reel_STORY.mp4"
}
```

- **`total_cost`** — what this ENTIRE reel actually cost, in real dollars,
  measured from the provider's own reported usage where it reports one
  (OpenRouter's per-call cost) and a price-table estimate otherwise. Not a
  worst-case guess — this is what you were actually billed (or would have
  been, outside stub mode).
- **`by_stage`** — the same total, broken down by which of the 8 stages spent
  it, so you can see where a reel's cost is actually going (usually: frames).
- **`by_model`** — the same total again, broken down by which underlying
  model/engine it went to instead — useful for comparing, say, the lite vs.
  full image model across many reels.
- **`needs_review`** — every shot_id that never got a clean `PASS`, even
  after retries, and shipped anyway as the best attempt available. Worth a
  manual look before you publish.
- **`reel_mp4`** — the finished video's path, for convenience.

## 7. `MAX_REEL_USD`

A hard ceiling on what one reel is allowed to cost, checked against real
spend (not a guess) before every money stage starts. Default `$2.00`; change
it in `.env` (`MAX_REEL_USD=3.00`). If a stage's own worst-case estimate
would push the reel's running total past this, the runner refuses to even
start that stage — no call is made, and it tells you exactly how close you
were. This is a per-reel cap, not a lifetime one; run `python -c
"from shorts import usage; print(usage.totals())"` any time to see this
project's own all-time total instead.

## 8. Typical cost per stage, per image model

Rough, typical-case numbers for a ~23-shot reel (not the worst-case pre-flight
estimate the runner itself always shows, which assumes every single shot
needs every retry) — actual numbers vary with how many regenerate attempts a
reel actually needs:

| Stage | Default (`gemini-3.1-flash-lite-image`) | Full quality (`gemini-3.1-flash-image`) | Cloudflare (free) |
|---|---|---|---|
| setup | ~$0.01 (topic selection + one reading of the material) | same | same |
| mapping | ~$0.03 (1 mapping call + 1 judge call, typically) | same | same |
| shots | ~$0.07 (1 call) | same | same |
| sample (5 shots) | ~$0.17 | ~$0.34 | $0.00 |
| frames (~20 unique, after reuse) | ~$0.67 | ~$1.34 | $0.00 |
| audio | $0.00 (local Kokoro/Chatterbox) | $0.00 | $0.00 |
| render | $0.00 (local Chrome capture + ffmpeg) | $0.00 | $0.00 |
| **typical total** | **~$0.95** | **~$1.62** | **~$0.11** |

The vision judge (`gemini-3.8-flash`) is free-tier and costs $0 either way —
it's not what drives the difference above; the image-generation model is.
Cloudflare has no per-image cost but also cannot take a reference image, so
expect noticeably less consistent character art in exchange for the $0.
