# plain_variable_no_rerender__motion: script-stage fixes (2026-10-12)

The real reel `plain_variable_no_rerender__motion` stopped at the script stage.
All three Opus scripts failed only `motion_captions_match_speech`. The reel was
also written as a fix_story although the reviewer had kept walkthrough.

## 1. Caption matcher: code operators

**Symptom**

    s03: caption word '0`.' does not match the narration at 'equals zero. Your click'
    s08: caption word '0`'  does not match the narration at 'equals zero creates it'

**Cause.** The caption `` `let count = 0` `` is split on spaces into
`` `let ``, `count`, `=` and `` 0` ``. `_motion_key` keeps only letters and
digits, so `=` became an empty key and the matcher skipped it. The narration's
"equals" was then compared with `` 0` `` and failed. The trailing backtick and
full stop were not the cause: s08 has no punctuation and failed the same way.

**Fix** (`shorts/checks.py`, `_motion_key`). Operators now key as the words
they are spoken as:

| caption | spoken |
|---|---|
| `=` | equals |
| `+` | plus |
| `+=` | plus equals |
| `==` | double equals |
| `===` | triple equals |

`=>`, `!=`, `<=`, `>=` and `-` are left out on purpose. People say them in
different ways, and a lone `-` is usually a prose dash. A real mismatch, such as
"equals one" spoken for `= 0` or "is zero" for `= 0`, still fails.

`motion_voice.caption_speech` uses the same key, so voice timing gives each
caption its spoken "equals" too.

## 2. Template gate: Enter didn't pin the template

**Cause.** The reel's `setup.json` has `"template": "walkthrough",
"template_source": "default"`. When the reviewer pressed Enter at
`template [walkthrough]`, `_decide_template` saved the source as `"default"`, the
same as `--yes`. `template_pin` read that as "not chosen", so the theme step
looked at every theme and picked `under_the_hood`, which is a **fix_story**
theme. The script stage takes its template from the theme, so the reel became
a fix_story.

**Fix** (`shorts/motion_reel.py`, `_decide_template`). At an interactive prompt,
Enter and a typed template now both save `"reviewer"`, which pins the template.
Only `--yes` or a non-interactive run, where no prompt was shown, leaves the
choice to the theme.

## Tests

`SHORTS_STUB=1 python -m shorts.motion_plain_variable_fixes_test` runs 13 tests.
On the unfixed code, the two caption tests fail with the real run's error text
word for word, and the Enter test fails too.

The run didn't save its rejected drafts, so the test captions are rebuilt from
the grader messages. s03 is the fixture's s03 with the code kept as code. s08's
sentence is the shortest one that produces its message.

Full stub suite: all 55 `shorts/*_test.py` modules pass. `evals.run_evals`:
211 passed, 0 failed, 12 skipped.

---

# Round 2: walkthrough checks vs. prompt (2026-10-12)

The walkthrough run failed 4 times (reel total $0.99). The checks were wrong,
not the scripts. The rejected drafts weren't saved, so
`evals/fixtures/motion/plain_variable_walkthrough_script.json` rebuilds one from
the error text. **With the checks as they were before this round, it fails exactly
the reported checks. Now it passes all 19 graders**, using the reel's own split
(main 7.2 + 7.4, supporting 7.1 + 7.3) and its approved teaching approach.

| # | Check | Was | Now |
|---|---|---|---|
| 1 | `motion_hook_curiosity` (walkthrough) | only "How does / What happens when / Where does / What does" | any curiosity question opening with why / what / how / where / when / which, matched as a whole word, so "However..." still fails. The answer line after the question is still required, because the prompt asks for it. |
| 2 | `motion_caption_sentences` | "Step one. Counter runs.", the prompt's own card format, counted as 2 sentences | on a `chapter_card`, a leading "Step one." / "Step 1:" / "Chapter two." label isn't counted as a sentence. Two real sentences still fail. |
| 3 | `walkthrough_running_example`, `walkthrough_main_source` | the literal "let count = 0, inside Counter" matched as one string, and "zero" was never turned into 0 inside long text | matched part by part ("let count = 0" and "Counter"), with code against speech keyed the same way as the caption check. A different example (`= 5`, `total`/`Cart`) still fails. |
| 4 | `walkthrough_main_source` titles | every title word, "you" and "notices" included, had to be in the main section | stopwords and pronouns are ignored and words are matched by stem. A word fails only when the main section lacks it and a **supporting** section has it, which means the step was borrowed. A title with no main-section word fails. E174 (double hash) still fails as before. |

The walkthrough prompt and hook-fix prompt now list the same hook openers the
check accepts, and say the step label isn't a sentence.
`test_the_prompt_offers_the_hooks_the_check_accepts` holds the two in sync.

## Rejected drafts (`shorts/motion_repair.py`)

- **Saved.** Every rejected draft (full attempt, hook fix, or failed repair) is
  written to `output/<id>/rejected/<time>_<kind>.json` with its failures.
- **Reused for free.** Before its money gate, the script stage regrades saved
  drafts for the same template, theme and section. If one passes, it's used
  with no call, and the shot-list gate still asks you to approve it.
- **Repaired in code.** When every failure is mechanical (`motion_caption_sentences`,
  `motion_captions_match_speech`), captions are re-cut: a two-sentence caption is
  split, and plain-word captions are rebuilt from their speech with the
  highlights kept. Captions that show code are never rebuilt. The result is
  regraded by every grader before it's used.

## Tests

- `SHORTS_STUB=1 python -m shorts.motion_walkthrough_agreement_test`: 26 tests.
- Eval `E225`: the fixture passes every grader.
- All 56 stub test modules pass. Evals: 212 passed, 0 failed, 12 skipped
  (the paid judge cases).

## Also noticed, not changed

`shorts/checks.py` defines `_stem` twice (around lines 664 and 8550). The second
definition replaces the first for every caller, so `_stems` and `_grounded` run
with the second one (the old chapter-title stemmer), while `_STOP_STEMS` was
built with the first one. The new title check uses its own `_title_stem` so it doesn't depend on this.
Fixing it could change grounding results, so it's left for you to decide.
