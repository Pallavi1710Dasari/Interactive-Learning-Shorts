"""SKILL 2 — dialogue-script. Topic + source span in, interview beats out.

This is the highest-leverage prompt in the project. Everything downstream inherits
its quality. Tune it against the eval set, not by vibes.
"""
from ..schema import Script, Topic, Section, MIN_SECONDS, MAX_SECONDS, WORDS_PER_SECOND
from ..llm import ask_json

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)   # 75
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)   # 150
TARGET_WORDS = 110

SYSTEM = f"""You write 30-60 second interview-style video scripts that teach ONE concept.

FORMAT
Beat 1: the interviewer asks ONE question.
Beats 2-5: the student answers in 3 to 4 SHORT parts (5 parts maximum).
Every beat after the first is the student. No follow-up question.

HARD WORD BUDGET
Total spoken words across ALL beats: {MIN_WORDS} minimum, {MAX_WORDS} maximum,
{TARGET_WORDS} is the target. Speech runs 150 words per minute, so this IS the
video length. Count your words before you answer. A script outside the budget is
discarded — being UNDER {MIN_WORDS} fails just as hard as being over {MAX_WORDS}.

THE QUESTION (beat 1)
- 8 to 20 words. Ask the thing a learner actually wonders, not a textbook prompt.
- Best when it targets a misconception, so the answer corrects a wrong prediction.

EACH ANSWER BEAT
- ONE idea only. 15 to 28 spoken words. NEVER more than 32 — a longer beat is
  rejected outright, because the diagram on screen has to change with the idea.
- Reads as speech, not prose. No "furthermore", no "it should be noted".
- Builds on the beat before it. The last beat lands the takeaway.
- Together the beats must flow as one continuous explanation, not four
  disconnected facts — someone reads the whole thing aloud in one take.

on_screen (the text burned onto the video)
- MAXIMUM 8 WORDS. This is a hard limit; longer text does not fit a phone screen.
- Not a transcript of the line. The label a slide would carry.
- Title case off; sentence case.

visual_ref
- A short snake_case id you invent, e.g. "d_page_table_miss".
- A DIFFERENT ref per beat, unless two consecutive beats really share one visual.

FAITHFULNESS — the hardest rule
Every claim must appear in, or follow directly from, the source section provided.
Do not add version numbers, vendor names, benchmarks, dates, or statistics that
are not in the source. If the section does not contain something you need,
write around it. Inventing a plausible detail is the worst failure mode.

Output JSON — one interviewer beat then 3-4 student beats:
{{"short_id":"...","question":"...","beats":[{{"speaker":"interviewer|student",
"line":"spoken words","on_screen":"<=8 words","visual_ref":"snake_case"}}]}}"""


def write_script(topic: Topic, section: Section, feedback: str | None = None) -> Script:
    user = f"""TOPIC: {topic.topic}
WHY IT MATTERS: {topic.why_it_matters}
SHORT_ID: {topic.id}

SOURCE SECTION [{section.section_id}] {section.title}
---
{section.text}
---

Write the script. Stay inside the source section."""

    if feedback:
        user += f"\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED:\n{feedback}\nFix exactly this and try again."

    return ask_json(SYSTEM, user, Script, max_tokens=2000, label="script")
