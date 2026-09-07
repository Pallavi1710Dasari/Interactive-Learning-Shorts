"""SKILL 2 — dialogue-script. Topic + source span in, interview beats out.

This is the highest-leverage prompt in the project. Everything downstream inherits
its quality. Tune it against the eval set, not by vibes.
"""
from ..schema import (Script, Topic, Section, SectionUnderstanding,
                      MIN_SECONDS, MAX_SECONDS, WORDS_PER_SECOND)
from ..llm import ask_json
from .. import revision

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)   # 87
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)   # 125
#: THERE IS DELIBERATELY NO SINGLE TARGET IN THE BRIEF ANY MORE.
#:
#: This was 56, then 112, and both were wrong in the same way: a figure in the
#: prompt is read as the length to reach, so the model writes to the number rather
#: than to the concept. At 112 (the 35-50s maximum) that meant padding pressure on
#: every short; at 56 it meant stopping early on a rich one.
#:
#: The brief now states BANDS and lets the concept pick one — see LENGTH below.
#: This constant survives only as the midpoint other modules may want, and nothing
#: in the prompt tells the model to aim at it.
TARGET_WORDS = (MIN_WORDS + MAX_WORDS) // 2   # 87

SYSTEM = f"""You write SHORT interview-style video scripts that teach ONE concept.

FORMAT
Beat 1: the interviewer asks ONE question.
Beats 2-6: the student answers in 4 or 5 SHORT parts. FIVE IS THE MAXIMUM.
Every beat after the first is the student. No follow-up question.

Each answer beat is ONE idea with ONE picture, and stays at or under 24 words.
That cap does not move. Four or five beats is how this fills 45 seconds — NOT
four or five longer beats. If a beat needs more than 24 words, it is two beats or
it is padded.

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

TWO OR THREE PARTS. NOT ONE, NOT FOUR, NOT FIVE.

NEVER ONE. A single answer beat is rejected outright, every time, and it is the
failure this section gets wrong most: the bound below is as hard as the bound above.
One beat leaves one diagram on screen for the whole short and gives the viewer
nothing that develops. If the section really only supports one sentence of answer,
do not pad it into two — NARROW THE QUESTION in beat 1 until the section supports
two distinct things to say, each resting on its own sentence.
Five-point answers are what these shorts are being fixed from. Nobody watching a
phone remembers point four, and by the time you have written it you have buried the
one sentence that mattered under context nobody asked for. If a beat is a
restatement, a recap, or a "so in summary", DELETE IT.

But do not cut the beat that answers the question in order to hit a beat count. A
complete answer beats a tidy non-answer every time.

LENGTH — THE CONCEPT DECIDES, NOT A TARGET
Total spoken words across ALL beats: {MIN_WORDS} minimum, {MAX_WORDS} maximum.
Speech runs 150 words per minute, so this IS the video length.

THERE IS NO NUMBER TO HIT INSIDE THAT RANGE. The window is wide because concepts
differ, and where a short lands says something true about its concept:

  {MIN_WORDS}-75 words   ~25-30s  A concise but complete concept. The idea, how it
                       works, and what follows from it — with nothing left out and
                       nothing added. THIS IS A FINISHED SHORT, NOT A SHORT ONE.
  75-95 words   ~30-38s  The normal case: a mechanism and its consequence, walked
                       through step by step.
  95-{MAX_WORDS} words  ~38-45s  A richer concept — one whose section also gives you a
                       worked example to walk through, or a misconception worth
                       correcting, or both.

Read the plan, write what the concept needs, and let it land where it lands. Do
not check your word count against the top of the range and go looking for
something to add: that is the padding this brief spends most of its length
forbidding, and it has been the defect in three of the four length settings this
format has had.

BEING AT THE BOTTOM OF THE RANGE IS NOT A FAULT TO FIX. A four-beat answer of
15-18 words a beat comes to about 70 words, and that is a normal, good, finished
short — it reads tightly and says everything. It is explicitly allowed. If you
find yourself wanting a fifth beat only because four felt short, you have found
the padding instinct, not a missing beat.

THE ONLY REASON TO ADD A BEAT IS THAT THE PLAN HAS SOMETHING IN IT YOU HAVE NOT
SAID — the next teaching step, the example it told you to use, the misconception
it told you to correct. If the plan is fully delivered in four beats, you are
done. If it is fully delivered in four beats and you are under {MIN_WORDS} words,
you are still done — say so by writing it, and let the length gate reject it.
That is a topic too thin for the format, and the fix belongs to select, not to
your sentences.

WHAT THE EXTRA TIME IS FOR IS NOT YOUR DECISION — IT IS IN THE PLAN.
The CONTENT UNDERSTANDING below carries a teaching_sequence, an example decision
and a misconception decision, all read off THIS section before you were called.
Those blocks are the authority on what fills the window, and each is spelled out
further down under "THE EXAMPLE" and "THE MISCONCEPTION". Read them; do not
re-derive them, and do not add an example or a correction the plan did not ask
for. A worked example is the most effective thing a short can contain and a
corrected expectation is the most memorable — which is exactly why the decision
to use one is made by the step that read the section, not by the step under
pressure to fill 45 seconds.

THE LAST BEAT MUST CARRY THE IDEA ITSELF. This is measured, not a matter of feel:
the final beat is checked for how much of the objective's own vocabulary it
contains, and a beat that lands on a supporting detail instead fails it — which
has been the single most common reason a real run was rejected.

Normally the plan does this for you, because a well-ordered teaching_sequence ends
ON the objective. When it does not — when the last planned step is a detail rather
than the idea — END ON THE IDEA ANYWAY. That is allowed and expected: the sequence
check accepts a short that lands on the objective instead of on the final step. The
plan orders the explanation; you decide where to stop.

What this is NOT is a licence to add a summarising beat after the explanation:

THERE IS NO CLOSING TAKEAWAY BEAT. DO NOT ADD ONE. This is the one instruction
here most likely to feel wrong, so here is the evidence: the last thing a viewer
hears should indeed be the idea itself, but that is the JOB OF THE FINAL TEACHING
STEP, not of a beat added after it. A beat that names the idea again once it has
already been explained is a recap, and a recap:

  - is what the "so in summary" ban above already forbids;
  - fails check_beats_develop, which measures how much of a beat is new against
    every earlier beat and rejects one that is mostly not;
  - and is a bug this pipeline has actually shipped. The frozen case reads
    "So doctype, html, head, and body together form the structure every document
    follows" as beat 4, against a beat 1 that had already said exactly that. It
    passed every other grader.

So end ON the last step of the teaching_sequence, which IS the objective — the
short arrives at the idea rather than summarising its way back to it. If the
final step feels like it needs a sentence after it to make the point land, the
sequence was in the wrong order, not one beat short.

So the honest ways to fill the window are: the teaching_sequence walked properly
with one idea per beat, an example if the plan says to use one, and a correction
if the plan says there is one. Nothing else. Specifically still banned: a
restatement, a "so in summary" that adds nothing, context nobody asked for, and a
beat whose citation does not really support it.

IF THE PLAN DOES NOT GIVE YOU ENOUGH TO FILL THE WINDOW, WRITE IT SHORTER and let
the length grader reject it. That failure is recoverable — the topic goes back to
select, which is the step that is supposed to catch a section too thin for 45
seconds. A padded short that passes every grader is not recoverable, because
nothing downstream can see it.

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

CONTENT UNDERSTANDING — WHAT TO EXPLAIN. NOT SOMETHING YOU MAY QUOTE.
Some runs hand you a CONTENT UNDERSTANDING block above the section. An earlier step
read the same section and worked out what it teaches: the one idea, the order the
points have to build in, the section's own concrete examples, what a learner gets
wrong, and what the section does NOT answer.

Use it, and use it for exactly one thing: deciding WHAT to say and in WHAT ORDER.
It is the reason a script stops being the section's sentences in the section's
order. Aim beat 1 at a listed confusion. Name one of the listed concrete examples.

"THE OPENING" DECIDES BEAT 1. WRITE THE SENTENCE; DO NOT RE-DECIDE THE APPROACH.
When that block appears it says how this short starts, chosen with the section in
view. It gives you the SUBSTANCE of beat 1 — you still write the question, in the
8-to-16 words THE QUESTION asks for.

  QUESTION  Ask the planned question, in a learner's words.
  PROBLEM   Beat 1 puts the difficulty in front of the viewer, and the answer beats
            resolve it. The problem is the section's, not one you thought of.
  SURPRISE  Beat 1 aims at the thing that will not be predicted. It has to be a
            real surprise the section states — if it needs a claim the section
            does not make to be surprising, it is not one.
  DIRECT    No hook. Ask plainly about the thing and start explaining in beat 2.
            This is a decision, not a gap: do NOT manufacture a stake, a scenario
            or a "have you ever wondered" to warm the viewer up. For a definition
            or a plain mechanism the concept IS the strongest opening, and seconds
            spent warming up are seconds the explanation does not get.

THE HOOK IS ONE BEAT AND IT IS SHORT. This whole short is 12 to 28 seconds. An
opening that takes two sentences to set a scene has eaten the explanation. Beat 1
hooks and beat 2 is already teaching — the first answer beat must land on the idea
itself, not on more setup.

NO MANUFACTURED INTEREST, EVER, under any of the four. No invented statistic,
scenario, stake or comparison, and none of this language: "you won't believe",
"most people get this wrong", "nobody tells you", "the secret to", "this changes
everything", "X% of developers". It promises what the material does not contain,
it is the clearest possible signal that a short is padding, and it is checked and
rejected. An honest undramatic opening beats a dishonest exciting one every time.

AND THE HOOK MUST ARRIVE SOMEWHERE. It hands over to the concept named in the
block — normally the one idea. A hook that is interesting and then goes somewhere
else has spent the viewer's attention on a different short.

"HOW TO BUILD THE EXPLANATION" IS THE SPINE OF YOUR ANSWER BEATS.
When that block is present it gives the order a beginner needs, and each step says
why it is there and what the learner should have at the end of it. Follow it:
  * Take the steps in the order given. The order is the point — it was chosen for
    this concept, and step 2 usually cannot be understood before step 1.
  * ONE STEP PER BEAT is the normal mapping, and the step's `learner ends up` is
    what that beat has to deliver. If a step is small enough to share a beat with
    the next one, merge them — you have 2 or 3 answer beats and the sequence may
    have more steps than that.
  * The LAST step is where the answer lands, so the last beat delivers it. That is
    the same rule as THE LAST BEAT MUST ANSWER THE QUESTION above, and the sequence
    is telling you which sentence that is.
  * A step you cannot support from the section is a step you DROP, and you make
    beat 1 ask the narrower question the remaining steps answer. Do not keep a step
    alive by inventing a sentence for it.
The sequence is a plan for explaining, never wording. Do not read a step's fields
aloud: "purpose" and "learner ends up" are notes to you about why a beat exists,
and a beat that narrates its own purpose is the "so in summary" beat this brief
already deletes.

"THE EXAMPLE" IS A DECISION THAT HAS ALREADY BEEN MADE. FOLLOW IT.
When that block appears it says whether this short is built on a worked case, and
BE CONCRETE above tells you why one matters. It has three forms:

  REQUIRED   The idea does not land without it. Work the named example into an
             answer beat — the beat that carries the step it belongs to, or the one
             beside it. This is not "mention it in passing": the beat should show
             the example DOING the thing, so a learner sees the takeaway named in
             the block rather than hearing a noun go by.
  HELPFUL    Use it if the beats have room. If using it would cost you the beat
             that answers the question, leave it out — brevity wins, and nothing
             fails for its absence.
  NOT NEEDED The section shows nothing concrete worth building on, and this is a
             verdict, not an oversight. Explain it in general terms. DO NOT reach
             for an example you know from outside, DO NOT make up a value, a
             number, a file name or a line of code to sound specific, and do not
             treat a general answer as second-best. Here it is the right answer.

Copy the named example from the section EXACTLY — the real selector, the real
value, the real figure, character for character. Do not tidy it, do not generalise
it into a placeholder, and do not substitute one you find neater. An invented
literal is caught and the script is rejected.

NONE OF THIS RELAXES THE SOURCE RULES. The example still has to be found in THE
SECTION, the beat that uses it still needs its own source_quote copied from THE
SECTION, and the example block is guidance like the rest of the CONTENT
UNDERSTANDING — it is not a citation and may not be quoted as one.

"THE MISCONCEPTION" IS ALSO ALREADY DECIDED. DO NOT SECOND-GUESS IT.
This brief says a question aimed at a misconception is the best kind, and that is
still true — but WHICH misconception, or whether there is one at all, is not your
call. The block says:

  REQUIRED   The section exists partly to correct this. Clear it up INSIDE the
             explanation, at the step it belongs to — the beat that explains the
             idea is the beat that says what it is not. Prefer not to give it a
             beat of its own: the reason is no longer that there is no room (a
             four or five beat answer has some), it is that a correction wedged
             between two steps interrupts the very explanation it is supposed to
             sharpen. A beat of its own is acceptable only when the plan's
             relates_to_step puts it at the END of the sequence, where it
             interrupts nothing.
  HELPFUL    Clarify it only if it costs you nothing. If making room means losing
             the beat that answers the question, drop the clarification — nothing
             fails for its absence.
  NONE TO CORRECT  There is nothing here worth correcting, and that is a finding,
             not a gap. Do NOT invent a belief so you have something to fix, do
             NOT open with "a common mistake is..." or "you might think...", and do
             NOT add a myth-busting beat. Just explain the idea.

AND THE RULE THAT OVERRIDES ALL THREE: NEVER STATE THE WRONG BELIEF ON ITS OWN.
A viewer hears sentences, not intentions. A beat that says the mistaken thing and
leaves it hanging has taught it — the next beat correcting it arrives after the
damage. So the error and the truth go in the SAME breath:

  BAD   "A page fault means the program has crashed."
        "Actually the OS just loads the page and carries on."
        ^ Beat 1 is a false sentence, said in the video, in the student's voice.
  GOOD  "A page fault is not a crash — it is a trap that tells the OS to load the
         missing page."
        ^ One beat. The belief and its correction are inseparable.

THE SECTION IS THE ONLY AUTHORITY FOR THE CORRECTION. What is "actually true" is
what THIS SECTION says is true, not what you know. The correction still needs its
own source_quote copied from the section like every other claim, and if you cannot
find the sentence behind it, do not make the correction.

Now the part that matters more, because getting it wrong is worse than not having
the block at all:

- IT IS NOT A SOURCE. Every word of it is GENERATED TEXT — including the lines
  under "WHERE THAT CAME FROM", which are grounding information telling you where a
  point came from. They are NOT a pre-approved citation list.
- NEVER copy anything out of the CONTENT UNDERSTANDING block into a source_quote.
  Quotes are copied from THE SECTION and are checked against THE SECTION by exact
  match. A quote that exists only in the understanding block will not be found and
  the script is rejected. Even where the understanding quotes the section
  correctly, go and copy the sentence out of the section itself.
- IT CANNOT LICENSE A FACT THE SECTION DOES NOT STATE. If it points at something
  and you cannot find the sentence for it in the section, DROP IT. Never invent
  around it, never fill in the step it skipped. The section wins over the
  understanding every single time, and so does saying less.
- "WHAT THIS SECTION DOES NOT ANSWER" is a list of places to STAY OUT OF. Do not
  ask about them in beat 1, and do not drift into them in an answer beat. They are
  named precisely because they are what this section is most likely to be padded
  with — they sound like they belong and they are not on the page.

If there is no CONTENT UNDERSTANDING block, nothing changes: read the section and
write the script.

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
                 current: Script | None = None, document: str | None = None,
                 understanding: SectionUnderstanding | None = None) -> Script:
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

    `understanding` is skills/understanding.understand()'s reading of the SAME
    section, and it is OPTIONAL in the strong sense: every call site that predates
    it still works, and a caller that omits it gets byte-identical behaviour to
    before, because the block is only added to the prompt when one is passed and
    its brief is non-empty.

    It is GUIDANCE — what to explain, in what order, aimed at which confusion, and
    which of the section's own examples to name. It is NOT evidence. It is generated
    text, no part of it may be copied into a source_quote, and check_source_quotes
    still matches every quote against the section alone, so a script that leans on
    the understanding instead of the section fails exactly as it did before. The
    brief says all of that to the model too, under CONTENT UNDERSTANDING.

    PASS THE SAME ONE ON EVERY RETRY. The three-attempt loops in run.py, server.py
    and rescript.py read the section once, before the loop, and hand the result to
    each attempt — a grader complaining about beat 3 has not changed what the
    section teaches, so re-reading it would buy a second opinion on a settled
    question at the price of another call.
    """
    user = f"""TOPIC: {topic.topic}
WHY IT MATTERS: {topic.why_it_matters}
SHORT_ID: {topic.id}
"""

    # THE SELECTION STEP'S OWN EVIDENCE, kept distinct from anything generated.
    #
    # select.py already made the model prove this question is answerable by copying
    # the sentence that answers it out of the material, and drop_unanswerable
    # verified that span really occurs there. That is the one piece of REAL text
    # attached to a topic, and the CONTENT UNDERSTANDING block below must never be
    # read as a replacement for it: one is a verbatim span of the material, the
    # other is a model's description of it.
    #
    # It is offered as a starting point, not as a pre-cleared citation. It is
    # matched against the WHOLE document in select.drop_unanswerable — deliberately,
    # see the note there — so it can legitimately come from a neighbouring section,
    # and check_source_quotes matches against THIS section alone. Telling the model
    # it may quote this blind would manufacture exactly the cross-section citation
    # this brief exists to stamp out, hence the instruction to go and find it.
    if topic.answer_quote:
        user += f"""
THE SENTENCE THE SELECTION STEP FOUND THAT ANSWERS THIS — real, copied from the material
{topic.answer_quote}

This is a verbatim span of the reading material, not generated text, and it is the
best clue you have about what the answer is. Look for it in THE SECTION below. If
it is there, it is the natural anchor for your first answer beat and you may copy
it out of the section as that beat's source_quote. If it is NOT in the section, it
came from elsewhere in the document: use it to understand what is being asked, and
then answer from the section's own sentences instead.
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

    # BETWEEN THE CONTEXT AND THE SOURCE, in that order and on purpose. The full
    # material is context, this is guidance, and the section is the only thing a
    # claim may come from — so the section is what the model reads LAST, directly
    # above the instruction to write. Putting the understanding after the section
    # would leave a block of generated prose as the final thing in view at the
    # moment the model starts choosing sentences to quote.
    #
    # `as_brief()` returns "" when the reading came back empty. An empty heading
    # with nothing under it reads to a model as "there is nothing to explain here",
    # which is a claim nobody made, so in that case the prompt is left exactly as it
    # was before this step existed.
    if understanding is not None:
        brief = understanding.as_brief()
        if brief:
            user += f"""
CONTENT UNDERSTANDING — GUIDANCE ONLY. NOT A SOURCE OF CLAIMS. NEVER QUOTE IT.
An earlier step read the section below and worked out what it teaches. Use it to
decide WHAT to explain and in WHAT ORDER, and nothing else. Every word of it is
generated: it cannot support a claim the section does not state, and no part of it
may be copied into a source_quote — those are copied out of THE SECTION and are
matched against THE SECTION.
=============================================================
{brief}
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

    # TWO SHAPES OF FEEDBACK, and the difference is who wrote it.
    #
    # A routed block from revision.route() already carries its own headings — what
    # is wrong, what to fix, what to preserve — and wrapping that in "WHAT MUST
    # CHANGE" would bury a three-section brief under a header that contradicts its
    # third section. It goes in verbatim.
    #
    # Everything else is still a plain string: a human reviewer's note from
    # /api/regenerate, the judge's problems in _rejudge_after_fix. Those keep the
    # wrapper they have always had, so no existing caller changes behaviour.
    #
    # Either way this only exists on a RETRY. The first-generation prompt is
    # untouched — feedback is None on attempt 1 and none of this renders.
    if feedback:
        if revision.MARKER in feedback:
            user += f"\n\n{feedback}"
        else:
            user += f"\n\nWHAT MUST CHANGE:\n{feedback}\nFix exactly this and try again."

    # 2000 was too tight: a script plus a verbatim quote per beat is a longer
    # payload than a script alone, and a truncated response comes back with no
    # text block at all (see the note in llm.py).
    return ask_json(SYSTEM, user, Script, max_tokens=4000, label="script")
