"""Grader verdicts in, a revision brief for the script step out. No model call.

WHY THIS EXISTS
The retry feedback was one line per failed grader, joined with newlines:

    - source_quotes: beat 2 quotes "..." which is not in the section
    - follows_sequence: the answer covers 1 of 3 planned steps...
    - learning_outcome: this short does not yet teach what it set out to teach...

Three things are wrong with that, and they get worse as graders are added. It is
UNORDERED, so a citation failure and an overlay-length nit arrive with equal
weight and the model fixes whichever it reads last. It is REDUNDANT, because
learning_outcome exists to summarise the others and restates them. And it says
nothing about what was RIGHT — so an attempt that fixed the cited beat routinely
rewrote the opening that was already working, and the next attempt failed on the
opening instead. Retries chased each other around the script.

WHAT THIS CHANGES AND WHAT IT DOES NOT
It reorganises verdicts that have already been computed. No grader is re-run, no
plan is re-read, no model is called, and the retry count is untouched — this is
the same three attempts carrying a better-shaped complaint.

THE THREE SECTIONS ARE THREE DIFFERENT JOBS. "What is wrong" is a diagnosis a
human can scan. "What to fix" is the instruction. "What to preserve" is the part
that was missing entirely, and it is phrased as FUNCTION rather than wording —
"the opening is grounded and leads into the topic" invites a better sentence that
still does that, where "keep this sentence" would freeze a line that may have to
move when the beat beside it changes.
"""
from dataclasses import dataclass, field

#: Present in every routed block, and the flag skills/script.py keys on to render
#: it verbatim instead of wrapping it in the old "WHAT MUST CHANGE" header. Callers
#: that still pass a plain string — the judge-repair path, a human reviewer's note —
#: are unaffected, which is the point.
MARKER = "REVISION TARGETS"

#: Revision areas, in the order they are worked on. THIS ORDER IS THE PRIORITY RULE.
#:
#: grounding first and teaching_flow second, because those two are the difference
#: between a short that is wrong and a short that is unpolished. A beat citing a
#: sentence from another section, or an explanation that never reaches the idea, is
#: a defect a viewer is harmed by; an overlay two words too long is not. Sorting the
#: complaint puts the correctness failures where a model reads them first and makes
#: "fix this one first" something the prompt can actually say.
AREA_ORDER = ("grounding", "teaching_flow", "opening", "example", "confusion", "other")

#: What each area is, in one line, for the diagnosis section.
AREA_SUMMARY = {
    "grounding":     "the short states things its own section does not support",
    "teaching_flow": "the explanation does not get a learner to the core idea",
    "opening":       "the opening does not set up what the short teaches",
    "example":       "the worked example is missing, misplaced, or invented",
    "confusion":     "the misconception is mishandled",
    "other":         "a hard script rule is broken",
}

#: What each area is doing RIGHT when its graders pass. Deliberately about the job,
#: never about the sentences — see the module docstring.
AREA_PRESERVED = {
    "grounding":     "every beat rests on a sentence copied from this section",
    "teaching_flow": "the answer follows the planned progression and reaches the core idea",
    "opening":       "the opening is grounded in the section and leads into the topic",
    "example":       "the required example is used where it belongs",
    "confusion":     "the misconception is corrected without ever being stated as fact",
    "other":         "length, overlay text and dialogue shape are within limits",
}

#: Grader name -> revision area. Anything not listed lands in "other", which is
#: deliberate: a grader added later shows up in the block as an unclassified script
#: rule rather than silently vanishing from the feedback.
GRADER_AREA = {
    "source_quotes":     "grounding",
    "grounding":         "grounding",
    "on_topic":          "grounding",
    "follows_sequence":  "teaching_flow",
    "reaches_objective": "teaching_flow",
    # Repetition is a flow failure, not a style nit: a beat that says the previous
    # beat again is a beat the explanation did not advance through, so it belongs
    # beside coverage and order rather than down in "other" with overlay length.
    "no_repetition":     "teaching_flow",
    "opening_hook":      "opening",
    "question_grounded": "opening",
    "uses_example":      "example",
    "handles_confusion": "confusion",
    "timing":            "other",
    "overlays":          "other",
    "dialogue_shape":    "other",
    "no_refusal":        "other",
}

#: Graders that SUMMARISE other graders and must never contribute an instruction.
#:
#: learning_outcome reports "a required worked example is missing — fix uses_example
#: above", which is the same complaint as uses_example's own line with a layer of
#: indirection. Emitting both is how the old feedback told the model twice about one
#: problem and gave it a cross-reference to a heading that no longer existed once
#: the list was regrouped. It still decides ordering — a short that fails only the
#: objective is a teaching_flow failure — but reaches_objective carries the words.
SUMMARY_GRADERS = {"learning_outcome"}


@dataclass
class AreaFailure:
    """One revision area that failed, and the instructions to fix it."""
    area: str
    instructions: list = field(default_factory=list)

    @property
    def summary(self) -> str:
        return AREA_SUMMARY.get(self.area, self.area)


@dataclass
class RevisionPlan:
    """What to fix, what to keep, and what nobody could judge."""
    failures: list = field(default_factory=list)      # list[AreaFailure], in AREA_ORDER
    preserve: list = field(default_factory=list)      # list[(area, note)]
    unavailable: list = field(default_factory=list)   # grader names that skipped

    @property
    def failed_areas(self) -> list:
        return [f.area for f in self.failures]

    @property
    def is_empty(self) -> bool:
        return not self.failures

    def as_feedback(self) -> str:
        """The block that goes into the retry prompt. "" when nothing failed."""
        if not self.failures:
            return ""

        out = [f"{MARKER} — your previous attempt was rejected. Revise it; do not "
               f"start over.", ""]

        out.append("WHAT IS WRONG")
        for i, failure in enumerate(self.failures, 1):
            out.append(f"  {i}. {failure.area}: {failure.summary}")
        out.append("")

        out.append("WHAT TO FIX — in this order. The first ones are correctness, "
                   "not polish.")
        for failure in self.failures:
            out.append(f"  [{failure.area}]")
            out += [f"    - {line}" for line in failure.instructions]
        out.append("")

        if self.preserve:
            out.append("WHAT TO PRESERVE — these already work. Keep WHAT THEY DO. You may "
                       "reword them freely;")
            out.append("  the sentences are not the point, and a beat you fix above may "
                       "force one to change.")
            for area, note in self.preserve:
                out.append(f"  - {area}: {note}")
            out.append("")

        out.append("Change what is listed under WHAT TO FIX and nothing else.")
        return "\n".join(out)


def route(results) -> RevisionPlan:
    """Group grader verdicts into revision areas. Reads results; computes nothing.

    A grader that SKIPPED — because its plan was absent or was quarantined by its
    own validator — is recorded in `unavailable` and appears nowhere in the prompt.
    That silence is deliberate: naming the missing plan would invite the script step
    to reconstruct it, which is precisely the invention the quarantine was there to
    prevent. It writes with the guidance that survived, and is told nothing about
    the guidance that did not.
    """
    plan = RevisionPlan()
    by_area: dict = {}
    seen: set = set()          # (area, instruction) — one complaint, said once

    for result in results or []:
        if result.name in SUMMARY_GRADERS:
            continue
        if result.details.get("skipped"):
            plan.unavailable.append(result.name)
            continue

        area = GRADER_AREA.get(result.name, "other")
        if result.passed:
            continue

        instruction = f"{result.name}: {result.reason}".strip()
        key = (area, instruction)
        if key in seen:
            continue
        seen.add(key)
        by_area.setdefault(area, []).append(instruction)

    for area in AREA_ORDER:
        if area in by_area:
            plan.failures.append(AreaFailure(area=area, instructions=by_area[area]))

    # PRESERVE ONLY WHAT WAS ACTUALLY VERIFIED. An area earns a line here when at
    # least one of its graders ran and passed and none of them failed — a skipped
    # grader proves nothing, and claiming its area is in good shape would be telling
    # the model something nobody checked.
    verified: dict = {}
    for result in results or []:
        if result.name in SUMMARY_GRADERS or result.details.get("skipped"):
            continue
        area = GRADER_AREA.get(result.name, "other")
        verified[area] = verified.get(area, True) and result.passed

    for area in AREA_ORDER:
        if verified.get(area) and area not in by_area:
            plan.preserve.append((area, AREA_PRESERVED[area]))

    return plan


def feedback_for(results, prefix: str = "") -> str:
    """The routed block, optionally under a caller's own instruction.

    `prefix` is how a human reviewer's note survives a grader rejection: the note
    stays at the top where it governs, and the routed complaint follows it. Returns
    just the prefix when nothing failed, and "" when there is neither.
    """
    block = route(results).as_feedback()
    if prefix and block:
        return f"{prefix.rstrip()}\n\n{block}"
    return prefix.rstrip() if prefix else block
