"""SKILL 5 — eval-audit. Code graders run first (free), then the LLM judge (paid)."""
from ..schema import Script, ShortUnit, EvalReport
from ..llm import ask_json
from .. import config, checks

JUDGE_SYSTEM = """You grade a teaching video script against its source material. You are the
last automated gate before a human reviewer, so be strict and specific.

Score 1-5 on each axis.

faithfulness
  5 Every claim is stated in or directly implied by the source section.
  4 Every claim traces to the source; one rewording is looser than ideal.
  3 One claim is plausible but not actually present in the section.
  2 Multiple claims are not in the section, OR a specific number, version, vendor
    name, date, or statistic appears that the source does not contain.
  1 Substantially about something the section does not cover.

clarity
  5 A learner who has not read the doc understands on first listen.
  4 Clear; one sentence could be tighter.
  3 Understandable but needs a re-listen.
  2 Jargon used before it is defined.
  1 Confusing or self-contradictory.

pace
  5 Beats evenly sized, none over ~12 seconds of speech (~30 words).
  4 Slightly uneven but watchable.
  3 One beat noticeably long.
  2 Wildly uneven.
  1 Effectively a monologue.

diagram_correct: true only if every on_screen label matches what is being said at
that moment and nothing contradicts the source. If there are no diagrams, true.

In `problems`, list each specific defect as an actionable instruction, e.g.
"beat 3 states pages are 4KB; the source never gives a page size". Empty if clean.

Output JSON: {"faithfulness":n,"clarity":n,"pace":n,"diagram_correct":bool,"problems":["..."]}"""


def judge_script(script: Script, source_text: str) -> EvalReport:
    beats = "\n".join(
        f"{i}. [{b.speaker}] {b.line}\n   on_screen: {b.on_screen}"
        for i, b in enumerate(script.beats)
    )
    user = f"""SOURCE SECTION (the only permitted source of truth)
---
{source_text}
---

SCRIPT
Question: {script.question}
Estimated length: {script.estimated_seconds}s ({script.word_count} words)

{beats}

Grade it."""
    return ask_json(JUDGE_SYSTEM, user, EvalReport,
                    model=config.MODEL_JUDGE, max_tokens=1500, label="judge")


def audit(script: Script, source_text: str, unit: ShortUnit | None = None):
    """Full audit: code graders, then the judge only if the cheap checks passed."""
    results = checks.run_script_graders(script, source_text)
    if unit:
        results += [g(unit) for g in checks.UNIT_GRADERS]

    if not checks.all_passed(results):
        return results, None                      # don't pay for a judge on known-bad output

    return results, judge_script(script, source_text)
