# Learning-Shorts — Architecture Overview

*Read-only analysis of the current codebase, produced for planning the next phase of development. No files were modified to produce this document.*

---

## 1. Overall Project Purpose

**Problem it solves:** Turns a piece of reading material (a markdown document — course notes, a technical explainer) into a set of short (25–45s), vertical, two-voice "interview" videos that teach one concept each, complete with an auto-generated animated diagram per beat and synthesized narration.

**Input → processing → output:**

```
Markdown reading material (a doc with ## / ### headings)
   → parsed into Sections
   → LLM selects the most important, answerable Topics
   → LLM writes a source-grounded interviewer/student dialogue Script per topic
   → LLM designs a visual "strategy," then a per-beat diagram spec, rendered by local template code into SVG
   → TTS renders the dialogue into a recorded audio track (word/beat-level timings)
   → deterministic graders + two LLM judges (text judge, vision judge) score everything
   → a human approves/rejects/edits via a terminal CLI or a browser review UI
   → an approved ShortUnit is rendered to an MP4 by headless-Chromium-photographing the actual React player
   → shorts are served through a vertical scrolling feed (mobile-reel style)
```

There is **no agent framework** — this is explicitly called out in the project's own README: `shorts/run.py` is a plain-Python for-loop with two retry loops in it. Every step is a Python function that takes and returns a `pydantic` model from `shorts/schema.py`.

---

## 2. Complete Pipeline Flow

Two orchestrators exist over the same skill modules: `shorts/run.py` (CLI, batch) and `shorts/server.py` (FastAPI, used by the web UI — same logic, request-shaped and more concurrent). Both call the same underlying skills.

| Stage | Module | What happens |
|---|---|---|
| 0. Parse | `shorts/parse.py` | Markdown → `list[Section]`, each with a stable `section_id`, `title`, `text`, line span. Handles heading-numbering collisions (parent-qualification + occurrence suffixes). |
| 1. Select topics | `shorts/skills/select.py` | LLM ranks/picks `Topic`s (question, `answer_quote`, `importance`, `difficulty`) from the sections, plus free deterministic passes that drop unanswerable/duplicate/unsupported topics. |
| 1b. Understand the section | `shorts/skills/understanding.py` | One LLM call per section producing a `SectionUnderstanding` (core idea, teaching sequence, hook/example/confusion decisions, what the section *can't* answer) — cached per section. |
| 2. Write the script | `shorts/skills/script.py` | LLM writes a `Script` (interviewer beat + 4–5 student beats, each ≤24 words, each carrying a verbatim `source_quote`). Retried up to 3× by the caller (`run.py`/`server.py`) using grader feedback (`shorts/revision.py`). |
| 3. Plan the visual strategy | `shorts/skills/strategy.py` | LLM decides, per beat, *what a viewer must see* (`relationship`, `physical_form`, `must_see`, `focus`) — before any drawing shape is chosen. |
| 4. Design + render diagrams | `shorts/skills/visuals.py` + `shorts/skills/layout.py` | LLM (`spec_visuals`) picks one of 15 Frame templates per beat and fills in structured fields (never coordinates); `layout.py` (100% local, no LLM) computes every coordinate/label-fit and emits SVG, tagged with `data-enter`/`data-role`/`data-slide` for frontend animation. Looped up to `DESIGN_ATTEMPTS` (default 2) with a vision-judge-in-the-loop redesign gate. |
| 5. Voice | `shorts/voice.py` → `shorts/tts.py` → `shorts/providers.py` | Synthesizes each beat separately (so duration is measured, never estimated), normalizes audio, joins with silence gaps, records per-beat spans. Runs **concurrently** with visual design. |
| 6. Audit | `shorts/skills/audit.py` | Runs all free `checks.py` graders first; only if they pass does it spend an LLM judge call (`judge_script`) scoring faithfulness/clarity/pace/diagram-correctness/question-answered. |
| 7. Human gate | `shorts/review.py` (terminal) / `web/src/StepReview.tsx` (browser) | A human approves/rejects/edits before anything renders to video. |
| 8. Render | `shorts/video.py` | Headless Chromium screenshots the real React player (`web/src/CaptureStage.tsx` → `ReelStage.tsx`) frame-by-frame at 30fps, muxed with the recorded audio via ffmpeg. Cached, keyed on a fingerprint of the renderer + built frontend. |
| 9. Serve | `shorts/feed.py` / `shorts/server.py` `/api/shorts` | Produces the feed payload (timeline, captions, judge scores) the web app's vertical scroll consumes. |

---

## 3. Agents / LLM Stages

Every LLM call in the project funnels through **`shorts/llm.py::ask_json`** — the single point of contact with the model provider (Anthropic-compatible). It handles JSON-schema validation + retry-with-correction, per-model-family "disable thinking" handling (`_reasoning()`), prompt caching, and `SHORTS_STUB=1` short-circuiting to `shorts/stubs.py`.

| # | Stage | File | LLM call? | Model var | Input | Output |
|---|---|---|---|---|---|---|
| 1 | Topic selection | `skills/select.py::select_topics` | Yes (2 calls: rank + "screen") | `MODEL_GENERATOR` | `list[Section]` | `TopicList` |
| 1b | Section understanding | `skills/understanding.py::understand` | Yes (1 call, cached) | `MODEL_GENERATOR` | `Section` (+doc) | `SectionUnderstanding` |
| 2 | Script writing | `skills/script.py::write_script` | Yes (1/attempt, ≤3) | `MODEL_GENERATOR` | `Topic`+`Section`+`SectionUnderstanding`+feedback | `Script` |
| 3 | Visual strategy | `skills/strategy.py::plan_strategy` | Yes (1/plan) | `MODEL_STRATEGIST` (→`MODEL_DIAGRAM`→`MODEL_GENERATOR`) | `Script`+`Section`+`SectionUnderstanding` | `VisualStrategy` |
| 4a | Visual spec (template choice) | `skills/visuals.py::spec_visuals` | Yes (1/design attempt, ≤`DESIGN_ATTEMPTS`) | `MODEL_DIAGRAM` (→`MODEL_GENERATOR`) | `Script`+`Section`+`VisualStrategy` | `dict[str, Visual]` (with `Frame`) |
| 4b | Diagram rendering | `skills/layout.py::render` | **No — deterministic** | — | `Frame` | SVG string |
| 4c | Curated photos | `skills/photos.py` | **No — static lookup** | — | subject name | cached image bytes |
| 5 | Vision judge | `skills/vision.py::judge_frames` | Yes (1/design attempt, multimodal) | `MODEL_VISION_JUDGE` (→`MODEL_JUDGE`) | rendered PNGs + strategy + script | `dict[ref, VisualScore]` + composition problems |
| 6 | Text/content judge | `skills/audit.py::judge_script` | Yes (1, gated on free graders passing) | `MODEL_JUDGE` | `Script`+source+`ShortUnit` | `EvalReport` |
| — | Section-richness screen | `skills/select.py` (`drop_unsupported`) | Optional 1 batched call (`SCREEN_QUESTIONS`) | `MODEL_GENERATOR` | candidate topics | pass/drop |

Standalone re-trigger tools (not part of the main build loop): `shorts/redraw.py` (free re-render by default; paid `--redesign`/`--judge`), `shorts/rescript.py` (paid script rewrite with never-regress comparison), `shorts/revision.py` (pure feedback formatting, no LLM call).

---

## 4. Models

Four configurable **roles**, set in `.env` (`shorts/config.py`), each defaulting to fall back onto the previous:

| Role | Env var | Default | Used for |
|---|---|---|---|
| Generator | `MODEL_GENERATOR` | `claude-sonnet-5` | topic selection, understanding, script writing |
| Diagram designer | `MODEL_DIAGRAM` | → generator | `spec_visuals` (template + content choice per frame) |
| Strategist | `MODEL_STRATEGIST` | → diagram → generator | `plan_strategy` (what a viewer must see) |
| Judge | `MODEL_JUDGE` | `claude-opus-5` | `judge_script` — **must be a different family from the generator** |
| Vision judge | `MODEL_VISION_JUDGE` | → judge | `judge_frames` — **must be multimodal** |

`config.model_warnings()` actively detects and warns about dangerous misconfigurations: judge on a light/fast tier, judge == generator, diagram designer on a light tier, vision judge == diagram designer. The rationale documented at length in `config.py`: a weak judge doesn't fail loudly, it *approves everything*, which is indistinguishable from quality unless you go looking.

Two portability knobs baked into `llm.py`: adaptive "thinking" is off by default everywhere except the two judges (`think=True`), with per-family handling since Anthropic can disable it, `gpt-5*` cannot (asks for minimum budget instead), and Gemini's `-pro` variants can't either.

---

## 5. Skills / Modules

```
shorts/
├─ parse.py          markdown → Section[]  (no LLM)
├─ schema.py          the data contract — every pydantic model in the pipeline
├─ llm.py             the only model-calling function (ask_json)
├─ config.py           .env → constants, model roles, warnings
├─ checks.py           ~45 deterministic graders (the "code graders")
├─ revision.py         formats grader failures into retry feedback (no LLM)
├─ stubs.py            SHORTS_STUB=1 offline fake-LLM responses
├─ run.py              CLI orchestrator (build_one, main)
├─ server.py           FastAPI orchestrator + API for the web UI
├─ review.py           terminal human-approval CLI
├─ redraw.py / rescript.py   standalone re-trigger tools over on-disk units
├─ audit.py             offline structural audit report over on-disk units (distinct from skills/audit.py)
├─ feed.py              produces the reel-feed JSON shape (timeline, captions)
├─ video.py             headless-Chromium MP4 renderer
├─ voice.py             build-time TTS orchestration (cache, provider fallback chain)
├─ tts.py               provider-agnostic synth mechanics (per-beat synth, normalize, join, measure)
├─ speech.py            text → speakable text / clause-based phrasing
├─ providers.py         5 TTS backends (elevenlabs, kokoro, google, piper, chatterbox)
├─ chatterbox_worker.py resident subprocess for voice cloning (separate venv)
├─ voicesample.py       standalone voice A/B comparison tool
├─ usage.py             token/cost ledger
├─ smoke_test.py        5 offline sanity checks
└─ skills/
   ├─ select.py         Skill 1 — topic selection (LLM)
   ├─ understanding.py  Skill 1b — section comprehension (LLM, cached)
   ├─ script.py         Skill 2 — dialogue script (LLM)
   ├─ strategy.py       Skill 3 — visual strategy / "what must be seen" (LLM)
   ├─ visuals.py         Skill 4 — template choice + orchestrates design/redesign loop (LLM + local)
   ├─ layout.py          pure SVG renderer from structured Frame (no LLM)
   ├─ photos.py          curated real-photo lookup for hardware/analogy frames (no LLM)
   ├─ vision.py          Skill 5a — multimodal vision judge (LLM)
   └─ audit.py           Skill 5 — free graders + LLM text judge (judge_script)
```

**Connection chain:** `parse → select → understanding → script ⇄ (checks + revision, retry loop) → strategy → visuals(spec_visuals ⇄ layout ⇄ vision, redesign loop) → voice (parallel) → audit(checks + judge_script) → ShortUnit JSON → review → video → feed`.

---

## 6. Script and Content Generation

**Topic/question selection** (`skills/select.py`): the model ranks candidate topics 1–5 against a rubric, must supply a **verbatim `answer_quote`** proving the topic is answerable, and applies a "depth test" (must have a mechanism + consequence + example + correctable misconception) so thin sections are rejected even if superficially important. Deterministic passes then drop unanswerable topics (quote doesn't actually occur in the doc), near-duplicate concepts, and yes/no-phrased questions.

**Script generation** (`skills/script.py::write_script`, "the highest-leverage prompt in the project"): produces one interviewer beat + 4–5 student beats (≤24 words each, `checks.MAX_ANSWER_WORDS`). Every claim must carry a `source_quote` copied verbatim from the **section only** (not the whole doc — a documented fix for beats that cited material outside their own section). The `SectionUnderstanding.as_brief()` block governs *what to say and in what order*, never grounding — grounding is always separately re-checked against raw section text. A length window (25–45s, `MIN_SECONDS`/`MAX_SECONDS` in `schema.py`) is intentionally wide with no single target — the concept decides where in the band it lands, and a documented four-iteration history (30–60 → 18–45 → 12–28 → 35–50 → 25–45) records why each earlier setting was wrong.

**Question framing:** happens in two places — `select.py` writes the initial question (banned from being yes/no, scored for importance), and `run.py::_realign_topic`/`server.py`'s equivalent rewrites the question (reusing `write_script` itself) if `checks.check_topic_matches_understanding` detects the topic has drifted from what the section's own reading (`SectionUnderstanding.core_idea`) actually established.

---

## 7. Visual Generation

Visual generation is **split into three separate concerns** specifically because an earlier single-step version conflated them and produced frames that were "visual_correctness 9/10, educational_clarity 4/10":

1. **What must be seen** (`strategy.py::plan_strategy`) — decided from the script/section alone, in words (`must_see`, `why_visual`, `focus`), *before* any drawing shape is picked. Also decides `relationship` (process/comparison/data_movement/hierarchy/cause_effect/structure/effect/quantity) and `physical_form` (single_container/linked_nodes/nested_levels/flat_parts/two_sides/single_object) — two independent axes that together disambiguate, e.g., a stack (`process` + `single_container`) from a linked list (`process` + `linked_nodes`), which need opposite templates.
2. **How to draw it** (`visuals.py::spec_visuals`) — the model picks one of 15 templates (`bar, mapping, split, flow, table, stat, code, compare, preview, icons, hierarchy, cause_effect, state, graph, analogy` — `takeaway` is legacy-only) and fills in template-specific structured fields (never raw coordinates).
3. **Actually drawing it** (`skills/layout.py::render`) — 100% local/deterministic. Computes every coordinate, fits every label into a reserved, disjoint rectangle (structurally impossible for labels to overlap), applies the active theme (`paper` vs `neon`, `REEL_THEME`), and stamps `data-enter`/`data-role`/`data-slide` attributes the frontend reads to animate builds/motion.

The design loop (`design_visuals`) runs up to `DESIGN_ATTEMPTS` (default 2) rounds: spec → render → free structural graders → (only if clean) paid vision judge (`judge_frames`, one call scoring the **whole short's frame sequence at once**, since some defects — like "the same picture four times" — are only visible across frames). The best-scoring attempt is kept, not the last one. A repeat failure specifically on `concept_communication` triggers a re-plan of the *strategy*, not just another drawing attempt.

On the frontend, the rendering layer is a **display/animation layer only** — `ReelStage.tsx`/`AnimatedSvg.tsx` never recompute geometry; they inject the server-produced SVG, crop/scale it for framing, and animate declaratively-tagged elements via the Web Animations API (chosen specifically because it exposes a settable `currentTime`, which is what makes frame-exact MP4 capture possible).

---

## 8. Evaluation and Rubrics

Two layers: **deterministic graders** (`shorts/checks.py`, ~45 functions, free/instant, never raise) and **two LLM judges** (text + vision), plus a golden/fixture eval harness (`evals/`).

| Area | Representative graders (in `checks.py`) |
|---|---|
| Length/timing | `check_timing`, `check_overlays` |
| Dialogue shape | `check_dialogue_shape`, `check_qa_sentence_form` |
| Grounding / faithfulness proxy | `check_grounding` (word-overlap), `check_source_quotes` (verbatim substring), `check_answers_its_section`, `check_no_refusal`, `check_question_grounded` |
| Repetition/development | `check_beats_develop` (script), `check_frames_develop`/`check_frames_progress` (visuals) |
| Teaching-plan quality (on `SectionUnderstanding`) | `check_teaching_sequence`, `check_example_plan`, `check_confusion_plan`, `check_hook_plan`, `check_plan_depth`, `check_duration_budget` |
| Script-vs-plan compliance | `check_follows_teaching_sequence`, `check_uses_planned_example`, `check_handles_confusion`, `check_opening_follows_hook`, `check_reaches_objective`, `check_learning_outcome` (veto layer) |
| Section pre-gate (before any LLM call) | `check_section_richness` |
| Diagram/SVG structural quality | `svg_problems` (overflow, rotated text, out-of-viewbox, collisions), `check_svg_quality`, `check_visuals_resolved` |
| Diagram/narration alignment | `check_diagram_matches_narration`, `check_code_frames_quote_source` |
| State/motion correctness | `check_state_item_transitions_visible`, `check_state_pointer_moves_are_shown`, `check_flow_traversal_progresses` |
| Frame honesty/composition | `check_frames_are_visual`, `check_icons_are_pictures`, `check_samples_differ`, `check_one_hero_per_frame`, `check_ends_on_answer`, `check_generic_boxes_not_overused`, `check_code_not_overused` |
| Strategy/structure alignment | `check_frames_match_strategy`, `check_physical_form_matches_template`, `check_anchor_matches_structure` |
| Topic/understanding reconciliation | `check_topic_matches_understanding` |

**LLM judges:** `skills/audit.py::judge_script` (text — faithfulness/clarity/pace/diagram_correct/question_answered, `EvalReport`, gated to only run if free graders already pass), `skills/vision.py::judge_frames` (multimodal — visual_correctness/educational_clarity/text_dependency/animation_relevance/concept_communication per frame plus composition-level problems, `VisualScore`).

**When they run:** free graders run inline, every attempt, in the retry loops (script retries in `write_script`'s caller, design retries in `design_visuals`). The text judge runs once per finalized script (optionally also at review time via `JUDGE_AT_REVIEW=1`). The vision judge runs once per design attempt, gated behind the free graders.

**Eval harness** (`evals/cases.yaml` + `evals/run_evals.py`): 128 frozen cases across 9 case types (`code_grader`, `unit_grader`, `content_grader`, `understanding_grader`, `topic_grader`, `revision`, `llm_judge`, `vision_judge`, `golden`), each with a mandatory `why` field explaining the regression it guards against. Free cases run via `python -m evals.run_evals`; paid ones (`llm_judge`, `vision_judge`, most `golden`) require `--judge`. Every grader/registry in `run_evals.py` imports the production function from `checks.py` directly — no reimplementation.

---

## 9. Human-in-the-Loop

The pipeline is **not fully automatic** — there are two deliberate manual gates, plus an optional third:

1. **Topic gate** (optional, `--gate-topics` in `run.py`, or implicit in the web flow's step 2): a human can edit the selected topic list before any script is written.
2. **Script/visual review** (mandatory before rendering): `shorts/review.py` (terminal — print beats/visuals/judge scores, approve/reject/skip) or `web/src/StepReview.tsx` (browser — same idea, plus free-text-note-driven regeneration of just the question/answer/script, and a "held/quarantined" surface for judge-failed shorts with a "publish anyway" override via `/api/release`). **Nothing renders to video until `status="approved"`.**
3. **Voice choice** (`web/src/VoiceLab.tsx` / `python -m shorts.voicesample`): a human listens and picks/clones a narration voice; this never happens automatically.

The judge (`EvalReport.passed`) can also **quarantine** a short (`status="needs_review"`) independent of human review — it stays on disk, out of the public feed, until a human either fixes it or overrides via `/api/release`.

---

## 10. APIs and User Flow

`shorts/server.py` (FastAPI) routes, grouped by step:

| Step | Routes |
|---|---|
| 1. Material | `POST /api/material` |
| 2. Script + review | `POST /api/script`, `POST /api/scripts` (batched, concurrent), `POST /api/regenerate` |
| 3. Visuals/finalize | `POST /api/finalize`, `POST /api/revisual`, `POST /api/release` |
| Rendering | `POST /api/video/{id}` (async job), `GET /api/video/{id}/status`, `GET /api/video/{id}` (blob) |
| Feed | `GET /api/shorts`, `GET /api/audio/{id}` |
| Voice studio | `GET/POST /api/voice*` (state, speak, job status, adopt, keep, reset) |
| Ops | `GET /api/usage`, `POST /api/usage/reset`, `GET /api/health` |

**User flow (web):** paste/upload material → review suggested topics/scripts (approve, reject, edit with a free-text note, per beat) → click Build (`/api/finalize`, the expensive step — visuals + voice + judge, all overlapped) → review any held/quarantined shorts → watch the approved feed → optionally download an MP4 (which triggers/awaits an async render job).

---

## 11. Current Architecture Summary (text diagram)

```
┌─────────────┐     ┌──────────────────────────────────────────────────────────────┐
│  content/*.md│───▶│                     shorts/parse.py                          │
└─────────────┘     └──────────────────────────┬───────────────────────────────────┘
                                                │ Section[]
                     ┌──────────────────────────▼───────────────────────────────────┐
                     │  skills/select.py  (LLM: MODEL_GENERATOR)  →  TopicList       │
                     └──────────────────────────┬───────────────────────────────────┘
                                                │ Topic + Section
                     ┌──────────────────────────▼───────────────────────────────────┐
                     │ skills/understanding.py (LLM, cached) → SectionUnderstanding  │
                     └──────────────────────────┬───────────────────────────────────┘
                                                │
              ┌─────────────────────────────────▼─────────────────────────────────┐
              │  skills/script.py (LLM) ⇄ checks.py (free) ⇄ revision.py           │◀── retry ≤3
              │                         →  Script                                 │
              └─────────────────────────────────┬─────────────────────────────────┘
                              ┌──────────────────┴───────────────────┐
                              ▼ (parallel)                            ▼
              ┌───────────────────────────┐          ┌──────────────────────────────────┐
              │ voice.py→tts.py→providers │          │ skills/strategy.py (LLM)          │
              │  (5 backends, cached)      │          │   → VisualStrategy               │
              │   → Audio                  │          └───────────────┬───────────────────┘
              └───────────────────────────┘                          ▼
                                              ┌────────────────────────────────────────────┐
                                              │ skills/visuals.py (LLM: spec_visuals)       │
                                              │   ⇄ skills/layout.py (local render)         │◀── retry ≤DESIGN_ATTEMPTS
                                              │   ⇄ skills/vision.py (LLM, multimodal judge)│
                                              │   → dict[ref, Visual]                      │
                                              └───────────────────┬──────────────────────────┘
                                                                  ▼
                                    ┌──────────────────────────────────────────────┐
                                    │ skills/audit.py: checks.py (free) → judge_script (LLM) │
                                    │   → EvalReport, ShortUnit.status              │
                                    └───────────────────┬──────────────────────────┘
                                                        ▼
                                        output/<short_id>.json  (ShortUnit)
                                                        │
                     ┌──────────────────────────────────┼──────────────────────────────────┐
                     ▼                                  ▼                                  ▼
        review.py (terminal)              web/src/StepReview.tsx               video.py (headless Chromium
        approve/reject/skip                approve/regenerate/release              screenshots ReelStage.tsx
                                                                                    via CaptureStage.tsx route)
                     └──────────────────────────────────┼──────────────────────────────────┘
                                                        ▼
                                        feed.py / server.py `/api/shorts`
                                                        ▼
                                web (Vite/React): App.tsx → Reel.tsx/ReelStage.tsx
                                   (vertical scroll feed, IntersectionObserver-driven)
```

---

## 12. Strengths and Gaps

**Well implemented:**
- **Grounding discipline** — verbatim `source_quote`/`answer_quote` fields checked by substring match turn "is this true?" into a free, unambiguous string test at multiple pipeline points (topic, per-beat, per-frame-code).
- **Separation of "what to show" from "how to draw it"** — the strategy→spec→layout split, with `layout.py` being fully deterministic, structurally prevents the label-overlap class of bugs and makes diagram generation cheap to re-run without another LLM call (`redraw.py`).
- **Judge independence discipline** — enforced and *actively warned about* in code (`config.model_warnings()`): judge ≠ generator family, vision judge must be multimodal, diagram designer must not be a light tier.
- **Cost-aware engineering throughout** — free checks always run before paid calls (`check_section_richness` before `understanding_for`, free graders before the paid judge, structural graders before the vision judge); `usage.py` tracks every call; `DESIGN_ATTEMPTS`/thresholds were set from measured cost data, not guesses.
- **Single source of truth for rendering** — the React player is screenshotted directly rather than duplicated in a separate renderer, so the MP4 can't drift from what a reviewer watched.
- **A real (if lightweight) eval suite** — 128 frozen regression cases with mandatory rationale, importing production grader functions directly.
- **Human-in-the-loop is a hard gate, not a suggestion** — nothing renders to video without `status="approved"`, and the judge can independently quarantine.

**Gaps / missing capabilities (as observed, not yet acted on):**
- **No database** — the entire system is JSON files in `output/`, coordinated by several *slightly inconsistent* `SIDECARS`-like exclusion lists across `feed.py`, `review.py`, and `audit.py`. This will not scale past a single-operator workflow.
- **In-memory job state** (`_RENDERS`, `_VOICE_JOBS` in `server.py`) is lost on server restart — no durable job queue.
- **`understanding: Optional[SectionUnderstanding]` and `vision_scores` on `ShortUnit` are recorded but consumed by nothing** — explicitly noted in `schema.py` as write-only fields, a ready-made hook for a future "why is this reel weak" diagnostic feature that isn't built yet.
- **No authentication/authorization** on the API (deliberately `127.0.0.1`-only by default) — fine for local use, blocking for any multi-user or hosted deployment.
- **Theme/color duplication across three files** (`layout.py`, `raster.py`, `styles.css`) is a documented manual-sync liability.
- **`web/src/InterviewScene.tsx`** appears to be dead/superseded code (not imported by `ReelStage.tsx`, its CSS classes are hidden in a later design pass) — worth confirming with the project owner before any cleanup.
- **No fine-tuning, no learner-feedback loop wired back into generation yet** — the README describes this as future work (few-shot examples from high-completion shorts, prompt fixes from drop-off patterns), but nothing in the code currently closes that loop automatically.
- **Repair-on-judge-failure is off by default** (`REPAIR_FAILED_SHORTS=0`) — a failed short is quarantined, not automatically retried, because a full repair costs roughly a second build and isn't guaranteed to help.

**Where the architecture already supports change without a rewrite:**
- Adding a new visual template means: extend `Frame`'s `Literal` + fields in `schema.py`, add a `_render` function in `layout.py`, add spec guidance in `visuals.py`'s system prompt, and add a `checks.py` grader — no orchestration changes needed.
- Adding a new TTS provider means implementing the `Provider` interface in `providers.py` and adding it to `_PREFERENCE` — `voice.py`/`tts.py` need no changes.
- Swapping models per role is a `.env` change only (`config.py`'s role-based indirection).
- The grader/eval system is additive by design (`GRADER_AREA` table in `revision.py`, registries in `run_evals.py`) — new graders slot in without touching the retry-loop mechanics.

---

## Current State Summary (for handoff to another architect/AI)

**Learning-shorts** is a plain-Python, no-framework "agentic" pipeline that turns a markdown reading document into short, source-grounded, two-voice educational videos with auto-generated animated diagrams. The system has **7 LLM-powered stages** (topic selection, section understanding, script writing, visual strategy, visual spec, vision judge, text judge) unified behind one model-calling function (`shorts/llm.py::ask_json`), all operating on a strict `pydantic` data contract (`shorts/schema.py`). Diagram *drawing* itself is 100% deterministic local code (`shorts/skills/layout.py`) — the LLM only ever chooses a template and supplies content, never coordinates, which structurally eliminates the overlapping-label class of bugs that plagued earlier raw-SVG generation.

Quality is enforced by **~45 free deterministic graders** (`shorts/checks.py`) covering length, grounding (verbatim-quote substring matching), teaching-plan structure, diagram/narration alignment, and motion correctness, backed by a **128-case golden/fixture eval suite** (`evals/`). Two LLM judges — a text judge and a multimodal vision judge, both configured to be a *different, stronger* model family from the generator — gate final approval; a misconfigured judge is explicitly detected and warned about because it "fails silently as blanket approval."

The pipeline is **not autonomous end-to-end**: a human must approve scripts/visuals before anything renders to video (terminal CLI `shorts/review.py` or browser UI `web/src/StepReview.tsx`), and a human separately chooses/clones the narration voice. Rendering reuses the exact live React player (`web/src/ReelStage.tsx`) via headless-Chromium screenshot capture rather than a separate video-composition system, guaranteeing what's watched and what's exported never diverge.

Architecturally the system is single-operator-scale: JSON files on disk are the only datastore, job state is in-memory (lost on restart), and there's no auth. The data model already carries some write-only fields (`understanding`, `vision_scores` on `ShortUnit`) anticipating future diagnostic/feedback features that aren't wired up yet, and the README documents an intended (not yet built) feedback loop from learner drop-off data back into prompt tuning. Extension points are clean for: new diagram templates, new TTS providers, new/swapped models per role, and new graders — all additive without touching orchestration. The main technical-debt items worth a decision before further build-out are: unifying the several near-duplicate file-exclusion lists (`SIDECARS`), moving job state to something durable, and resolving whether `web/src/InterviewScene.tsx` (currently unreferenced) is dead code or a shelved feature.
