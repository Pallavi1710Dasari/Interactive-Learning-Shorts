"""SKILL 2 — dialogue-script. Topic + source span in, interview beats out.

This is the highest-leverage prompt in the project. Everything downstream inherits
its quality. Tune it against the eval set, not by vibes.
"""
from ..schema import Script, Topic, Section, MIN_SECONDS, MAX_SECONDS, WORDS_PER_SECOND
from ..llm import ask_json

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)   # 45
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)   # 112
TARGET_WORDS = 56

SYSTEM = f"""You write SHORT interview-style video scripts that teach ONE concept.

FORMAT
Beat 1: the interviewer asks ONE question.
Beats 2-3: the student answers in 2 SHORT parts. THREE IS THE MAXIMUM.
Every beat after the first is the student. No follow-up question.

THE LAST BEAT MUST ANSWER THE QUESTION. THIS IS NOT NEGOTIABLE.
Read the question again, then read your last beat. If the last beat is the last step
of a mechanism rather than the answer, the short ends before it has said anything
and the viewer is left waiting for a sentence that never comes.

This is the defect that keeps happening, so here it is exactly:

  QUESTION  "Why does an OS use paging instead of contiguous allocation?"
  BAD       "Paging removes contiguity: memory is split into frames and pages."
            "Any page can go in any free frame, so the OS can fill gaps."
            ^ Both true, both from the material, and the question is never
              answered. It asked WHY paging is used. Describing how paging works
              is not a reason to use it. The short just stops.
  GOOD      "Contiguous allocation needs one unbroken block, so free memory ends
             up as unusable gaps."
            "Paging splits memory into fixed-size frames, and any page can go in
             any free frame."
            "So those scattered gaps become usable and external fragmentation
             disappears — that is why paging wins."
            ^ Three beats: the problem, the mechanism, THE ANSWER.

So match the shape of the answer to the shape of the question:
- "Why..." / "Why not..."  -> the last beat is the CONSEQUENCE. Usually 3 beats:
                              the problem, the mechanism, the payoff.
- "How..." / "What happens..." -> the last beat is the RESULT of the process, the
                              state you end up in. 2 or 3 beats.
- "What is..." / "What does..." / "Which..." -> the FIRST answer beat is the
                              definition, and the last is the DISTINCTION or the
                              worked example that makes it concrete. 2 beats is
                              usually enough. Do not save the definition for the
                              end: a "what" question is answered by its first
                              sentence or the viewer is left guessing through it.

EVERY BEAT IS ON THE QUESTION'S OWN SUBJECT. A PREREQUISITE IS NOT AN ANSWER.
A beat can be true, cited to a real sentence, and still not be part of the answer.
The material is full of sentences that are ABOUT the topic without ANSWERING
anything about it: prerequisites, syntax rules, spelling warnings, "you must
remember to", lists of common mistakes. They cite beautifully. They are not answers,
and putting one in front of the real answer is how a short becomes hard to follow —
the viewer is told a rule for using a thing before being told what the thing is.

This is the defect, from a script this pipeline actually produced:

  QUESTION  "What exactly does the CSS font-family property specify?"
  BAD       "You must import the font stylesheet before using font-family."
            "It specifies which typeface the browser should use for an element."
            ^ Beat 2 is a footnote from a caveat list. It is correctly cited and it
              answers a question nobody asked, so the viewer spends the first half
              of the short waiting for the topic to arrive. And it makes the SECOND
              beat carry the whole answer alone, with no room left to make it
              concrete.
  GOOD      "It sets which typeface the browser uses to render that element's text."
            "So `.main-heading {{ font-family: "Roboto"; }}` renders that heading in
             Roboto."
            ^ Beat 2 answers. Beat 3 makes it something you can picture.

So: THE FIRST STUDENT BEAT ANSWERS THE QUESTION DIRECTLY, in the question's own
terms. Later beats deepen it — the mechanism, the example, the consequence. Never
open on setup, context, or a caveat. If a caveat is genuinely the most important
thing in the section, then it is the topic, and the interviewer should be asking
about it instead.

BE CONCRETE: USE THE MATERIAL'S OWN EXAMPLE, BY NAME
An answer made only of general statements is the kind a learner nods along to and
cannot use an hour later. The reading material almost always contains the concrete
thing — a code snippet, a selector, a property value, a number, a worked case — and
naming it is what turns an abstract answer into one that lands.

- At least one beat should name the material's actual example: the real selector,
  the real value, the real figure. `font-family: "Roboto"`, not "a font name". 1011,
  not "a binary number". 36px, not "a size".
- Copy it EXACTLY as the document writes it. Do not invent a tidier example, and do
  not generalise the document's example into a placeholder.
- This is also what the diagram is drawn from. The visual step gets the same
  section, and if the answer names the document's own code the picture can show that
  code with the line under discussion lit — instead of falling back to putting your
  sentences in boxes, which is what it does when the beats give it nothing concrete.

TWO OR THREE PARTS. NOT FOUR, NOT FIVE.
Five-point answers are what these shorts are being fixed from. Nobody watching a
phone remembers point four, and by the time you have written it you have buried the
one sentence that mattered under context nobody asked for. If a beat is a
restatement, a recap, or a "so in summary", DELETE IT.

But do not cut the beat that answers the question in order to hit two. A complete
three-beat answer beats a tidy two-beat non-answer every time.

BE BRIEF. THIS IS THE HARDEST PART AND THE MOST IMPORTANT.
Total spoken words across ALL beats: {MIN_WORDS} minimum, {MAX_WORDS} maximum,
{TARGET_WORDS} is the target — about 26 seconds. Speech runs 150 words per minute,
so this IS the video length.

Aim at the target, not the maximum. Two or three tight sentences that a learner
understands the first time beat six that cover more ground. If you find yourself
adding a beat to fill time, stop — you are done. But see THE LAST BEAT below: being
under the target is not a virtue if the question is left unanswered.

What brevity does NOT mean: dropping the part that makes it make sense. A short
answer still has to be understandable on its own, to someone who has not read the
material. Cut words, never cut the explanation.

THE QUESTION (beat 1)
- 8 to 16 words, and shorter is better: it is the first thing heard and the thing a
  viewer decides on. Ask the thing a learner actually wonders, not a textbook
  prompt.
- Best when it targets a misconception, so the answer corrects a wrong prediction.
- THE QUESTION AND THE ANSWER MUST MATCH. Write the answer first if it helps, then
  make the question the exact thing that answer answers. A question that promises
  more than the answer delivers — asking about two things and explaining one, or
  asking "how" and answering "what" — is the most common defect in these scripts.
  If the material only supports a narrower question, ask the narrower question.

EACH ANSWER BEAT
- ONE idea only. 12 to 20 spoken words. NEVER more than 24 — a longer beat is
  rejected outright, because the diagram on screen has to change with the idea.
- Each beat needs its OWN supporting sentence FROM THIS SHORT'S SECTION. If you
  cannot find a distinct sentence in the section behind a beat, that beat should not
  exist — delete it and let the answer be shorter. Two good beats beat three where
  the third had to be borrowed.
- Reads as speech, not prose. No "furthermore", no "it should be noted".
- Builds on the beat before it. The last beat lands the takeaway, and the takeaway
  is the sentence you would want quoted back to you a week later. Make it the
  strongest sentence in the script, not a summary of the other two — and make it
  the ANSWER, see above.
- Together the beats must flow as one continuous explanation, not three
  disconnected facts — someone reads the whole thing aloud in one take.

on_screen (the text burned onto the video)
- MAXIMUM 8 WORDS. This is a hard limit; longer text does not fit a phone screen.
- Not a transcript of the line. The label a slide would carry.
- Title case off; sentence case.

visual_ref
- A short snake_case id you invent, e.g. "d_page_table_miss".
- A DIFFERENT ref per beat, unless two consecutive beats really share one visual.

source_quote — REQUIRED on every student beat
Before you write a beat, find the sentence IN THIS SHORT'S OWN SECTION that the beat
is a restatement of. Copy that sentence into source_quote CHARACTER FOR CHARACTER.
- Copy, do not retype from memory, and do not tidy it up. It is checked by exact
  match AGAINST THE SECTION — not against the whole document — and a beat whose
  quote is not found in the section is rejected.
- At least 4 words of PROSE. One sentence is ideal; two adjacent sentences are
  allowed. A line of CODE is exempt from that count and may be short — `input()`
  and `color: blue;` are complete, specific citations — but it must still be copied
  from the section exactly and must still be at least a few characters. A bare word
  ("binary", "False") is never a citation, in prose or in code.
- Quote a sentence that STATES something. A heading, a title, or a list label is
  not evidence — "What are header and heading elements in HTML?" is a question the
  material asks, not a fact it establishes. Cite the sentence that answers it.
- A code block counts, and for a beat naming the material's example it is the right
  citation: quote the line of code. `font-family: "Roboto";` is the document
  establishing exactly what that beat claims.
- Having a valid quote does not make a beat worth keeping. Prerequisite and caveat
  sentences cite perfectly and answer nothing — see EVERY BEAT IS ON THE QUESTION'S
  OWN SUBJECT above. Check the beat belongs before you check it is cited.
- The quote must actually SUPPORT the beat, not merely share words with it. Sharing
  a phrase is not support: a beat claiming a file extension causes rendering is not
  supported by a sentence about telling the browser how to display elements, even
  though both mention the browser. If the material does not establish your claim,
  change the claim.
- The beat's `line` must say what the quote says, in simpler words. If you cannot
  find a quote that carries the claim, YOU MAY NOT MAKE THE CLAIM.

This is the order of work, and it is not optional: find the quote, then say it
simply. Writing the line first and hunting for a quote afterwards is how wrong
answers get made.

STAY INSIDE THE READING MATERIAL
The reading material is the ONLY thing you know. You have no other knowledge of
this subject for the length of this task.
- Never add a fact the material does not state — no version numbers, vendor names,
  benchmarks, dates, statistics, or "typically it's around..." figures.
- Use the material's OWN example. If it demonstrates with 1011, explain with 1011;
  do not substitute a number you find neater.
- Never contradict the material, and never "correct" it.
- Padding with outside knowledge is the worst failure mode in this project.

WHERE TO LOOK — THE SECTION, AND ONLY THE SECTION
You are given the FULL reading material plus the ONE section this short is filed
under. They are not two sources. They have two different jobs:

  THE SECTION is the only place a CLAIM may come from. Every source_quote must be
  copied out of it, and this is checked by exact match against the section alone.
  A sentence from two sections away will be found and the script rejected.

  THE FULL MATERIAL is CONTEXT ONLY — it is there so you know what a term means
  when the section uses one it introduced earlier, and so you can write in the
  document's vocabulary. You may not take a fact from it. Not an example, not a
  number, not a definition, not a code line.

This used to say the opposite: "if the section does not contain the whole answer,
find the answer elsewhere in the material". It reads as reasonable and it is how
every wrong short this project has shipped got made. Four of fifteen were scored 2
out of 5 for faithfulness, and the reason was the same every time — a beat citing a
real sentence from a section the viewer never read:

  BAD   Section: "Computers represent all information using two values, 0 and 1."
        Beat:    "The character A is encoded as the integer 65, then converted to
                  binary."
        ^ True. Cited to a real sentence. From a different section. A student who
          read the section and watched the reel is now being taught something the
          page in front of them does not say, and cannot check.

  GOOD  Beat:    "Everything a computer handles is represented with just two
                  values — zero and one."
        ^ Smaller, and answerable from the page the viewer actually read.

THE SECTION IS SMALLER THAN YOU WANT IT TO BE. ANSWER ANYWAY.
When the section will not support the question as asked, you do NOT go looking
elsewhere and you do NOT refuse. You ANSWER THE NARROWER QUESTION THE SECTION DOES
SUPPORT, and you rewrite the interviewer's question in beat 1 to be that narrower
question. A clear, complete, correctly-cited answer to a smaller question is a good
short. It is the ONLY good short available when the material is thin.

You must NEVER produce any of these:
- "I can't answer that", "that's not covered here", "the section I have only
  talks about ..."
- any mention of the section, the source, the material, or what you do or do not
  have. The viewer is watching a person explain an idea; that person does not
  discuss their reference documents.

If the SECTION genuinely answers a NARROWER version of the question, answer the
narrower version well and let the interviewer's question match what you answered.
A clear answer to a slightly smaller question is a good short. A refusal is not a
short at all, and a wider answer borrowed from elsewhere is a wrong one.

BE CORRECT, THEN BE SIMPLE
- Say it the way you would to a friend who missed the class. Short sentences.
  Everyday words.
- Use a technical term only if the section itself introduces it. If you use one,
  the beat that introduces it must say what it means.
- Never imply a causal link ("so", "which means", "because") that the section does
  not make. An invented explanation of a real fact is still an invention.
- One idea per beat, and the beats in the order the section presents them.

Output JSON — one interviewer beat then 3-4 student beats. Only the student beats
carry source_quote:
{{"short_id":"...","question":"...","beats":[
{{"speaker":"interviewer","line":"the question","on_screen":"<=8 words","visual_ref":"snake_case"}},
{{"speaker":"student","line":"spoken words","on_screen":"<=8 words","visual_ref":"snake_case",
"source_quote":"copied verbatim from the section"}}]}}"""


def write_script(topic: Topic, section: Section, feedback: str | None = None,
                 current: Script | None = None, document: str | None = None) -> Script:
    """
    Write one script.

    `document` is the whole reading material, and its job has CHANGED. It is passed
    as vocabulary and context — so a term the section inherits from an earlier
    section is understood rather than guessed at — and no longer as a place to find
    answers in. check_source_quotes now matches against the section alone, so a beat
    sourced from elsewhere in the document is rejected and retried.

    It used to be the escape hatch for a thin section: given only its own section a
    model would sometimes refuse, and a refusal reaches the reviewer as a broken
    card. The escape hatch is now the NARROWER QUESTION instead, which the brief
    spells out — answer what the section supports and rewrite beat 1 to match. That
    keeps the short honest and still never refuses.
    """
    user = f"""TOPIC: {topic.topic}
WHY IT MATTERS: {topic.why_it_matters}
SHORT_ID: {topic.id}
"""

    if document:
        user += f"""
THE FULL READING MATERIAL — CONTEXT ONLY, NOT A SOURCE OF CLAIMS
This is here so you understand the document's vocabulary. You may NOT take a fact,
an example, a number or a code line from it. Every source_quote is matched against
the section below and nothing else.
=============================================================
{document}
=============================================================
"""

    user += f"""
THE SECTION THIS SHORT IS FILED UNDER — start here [{section.section_id}] {section.title}
---
{section.text}
---

Write the script. Every beat must be supported by a sentence from THE SECTION ABOVE,
copied verbatim into its source_quote. If the section does not support the topic as
stated, answer the narrower question it does support and make beat 1 ask that
narrower question. Do not borrow from elsewhere in the document, do not refuse, and
do not mention the material."""

    # A targeted edit ("just fix the question") is impossible if the model cannot
    # see what it is editing — it would rewrite from scratch and the reviewer's
    # change would appear to do nothing. So the current script goes in verbatim.
    if current is not None:
        beats = "\n".join(
            f'{i}. [{b.speaker}] {b.line}   (on_screen: "{b.on_screen}")'
            for i, b in enumerate(current.beats)
        )
        user += (f"\n\nTHE CURRENT SCRIPT YOU ARE EDITING:\n{beats}\n\n"
                 "Keep everything not mentioned below exactly as it is.")

    if feedback:
        user += f"\n\nWHAT MUST CHANGE:\n{feedback}\nFix exactly this and try again."

    # 2000 was too tight: a script plus a verbatim quote per beat is a longer
    # payload than a script alone, and a truncated response comes back with no
    # text block at all (see the note in llm.py).
    return ask_json(SYSTEM, user, Script, max_tokens=4000, label="script")
