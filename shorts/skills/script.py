"""SKILL 2 — dialogue-script. Topic + source span in, interview beats out.

This is the highest-leverage prompt in the project. Everything downstream inherits
its quality. Tune it against the eval set, not by vibes.
"""
from ..schema import (Script, Topic, Section, SectionUnderstanding, QuestionWorkflow,
                      QuestionFraming, TeachingApproach,
                      MIN_SECONDS, MAX_SECONDS, WORDS_PER_SECOND)
from ..llm import ask_json
from .. import revision, checks

MIN_WORDS = int(MIN_SECONDS * WORDS_PER_SECOND)   # 62
MAX_WORDS = int(MAX_SECONDS * WORDS_PER_SECOND)   # 112
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
That cap does not move BY DEFAULT. Four or five beats is how this fills 45
seconds — NOT four or five longer beats. If a beat needs more than 24 words, it
is two beats or it is padded — UNLESS a block further down names a higher,
per-call cap for a section that earned it (see THIS SECTION EARNS A WIDER
WINDOW THAN USUAL below the material, when it appears); that block is the only
thing that ever moves this number, and it says by how much.

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
- NAME THE MECHANISM, NOT THE WORKED EXAMPLE. A section that teaches a general
  idea through one concrete case tempts the question into naming the case: "how
  does one loop turn an array of orders into receipt rows?" is a caption for a
  screenshot, not a question — a learner who watched this could not answer "how
  do you render a list from an array" in an interview, because that transferable
  version was never asked. Ask the general version ("how does a loop turn an
  array into a list of rendered elements?") and put the example's real values —
  copied verbatim — in the ANSWER, where they are evidence, not in the question,
  where they make it unrecognisable outside this one document. This applies
  whether writing fresh or regenerating from a reviewer's note: a note asking to
  "make it clearer" or "be more specific" is about the ANSWER'S wording, not a
  license to re-anchor the question on the example either.

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

EVERY BEAT IS ONE COMPLETE SENTENCE A TOTAL BEGINNER COULD READ ONCE AND KEEP
The bar is not "technically correct", it is "a person meeting this concept for
the first time understands it on one pass and could say it back in an
interview". That rules out two habits that read fine to someone who already
knows the material:

  BAD   "Contiguous allocation requiring one unbroken block leads to unusable
         gaps as processes of varying sizes are allocated and freed over time."
        ^ One sentence stapling the mechanism, the cause and the consequence
          together — a run-on, not a beat. By the second clause the listener
          has lost the first.
  GOOD  "Contiguous allocation needs one unbroken block of memory."
        "As processes come and go, free memory ends up as scattered gaps too
         small to use."

Prefer the everyday word over the technical synonym whenever a plain one says
the same thing — "the process is paused" over "the process is suspended
pending completion of the I/O operation". Jargon the material itself
introduces (page table, frame, TLB) stays; jargon you reach for instead of a
word the listener already owns does not.

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

HOW TO TALK ABOUT CODE, A TAG OR ANY SYNTAX
The `line` field is SPOKEN ALOUD by a text-to-speech voice. Two failures come from
forgetting that, and both have shipped:

1. NARRATING SYNTAX INSTEAD OF EXPLAINING IT. A beat that walks through a snippet
   character by character — "open angle bracket, i, m, g" or "const, space, s,
   equals, 2" — is reading, not teaching, and it is exactly the note this brief
   exists to fix: a viewer who wanted the CONCEPT gets a transcription of the
   syntax instead.
     BAD   "You write `const s = 2`, with const, then a space, then s, then an
            equals sign, then 2."
     GOOD  "Writing `const` fixes that value for good — try to reassign it and
            the code refuses to run."
   Say what the code DOES or what it MEANS, the way you would explain it to
   someone who cannot see the screen, not what characters make it up. The exact
   characters are what `on_screen` and the diagram are for.

2. LITERAL SYNTAX IN A SPOKEN SENTENCE, WHICH A VOICE CANNOT READ RIGHT. A shipped
   line said `<img>` needs no `</img>` — spoken aloud, "img" comes out as a
   mispronounced syllable, not the word "image", because a voice reads letters it
   does not recognise as a word literally rather than expanding them. The same
   thing happens to any tag or identifier that is not itself a pronounceable word:
   `<a>`, `<li>`, `<br>`, `href`, `id`.
     BAD   "Notice there's no separate `</img>` anywhere."
     GOOD  "Notice there's no separate closing tag at all."
   So: in `line`, refer to a tag or attribute by what a person would actually SAY
   ("the image tag", "the anchor tag", "a closing tag"), never by writing its
   punctuation-bearing syntax inline. The exact syntax still belongs in
   `source_quote` (which is read by a grader, not a voice) and belongs on screen —
   `on_screen` and the frame the visual step draws may show `<img />` character for
   character. Keep the literal form there and the spoken sense in `line`.

This is the order of work, and it is not optional: find the quote, then say it
simply. Writing the line first and hunting for a quote afterwards is how wrong
answers get made.

TEACH THE CONCEPT — EXPLAIN IT, DO NOT ONLY RESTATE IT
A good teacher does not just read the page back to a student. Where the material
states a rule or a behaviour without spelling out WHY it holds or WHAT is
happening internally, you may explain that, in your own words — WHEN it is a
direct, standard consequence of what the material DOES state, not a fact you are
bringing in to prop it up. "Paging splits memory into frames" is the sentence;
"...so a process no longer needs one unbroken run of memory, which is what
external fragmentation was costing it" is the reason the sentence matters, and a
short that only ever gives the first has taught a fact instead of a mechanism.
Most of this reasoning should already be sitting in CONTENT UNDERSTANDING's
`why it is needed` / `learner ends up` lines when one is present — write those
out, do not re-derive your own.

THE LINE, EXACTLY WHERE IT IS: you may REASON from what the material states to
make its own claim clearer or to connect two things it separately says. You may
NEVER introduce a fact the material does not support to do it — a number, a name,
a version, a benchmark, a comparison to something it never mentions — however
true it is elsewhere. The test for any sentence you are about to add: could a
careful reader of THIS SECTION ALONE follow you to it, using only what the
section says? If getting there needs something only someone who already knew the
wider topic would know, it does not belong in this short — narrow the question
instead of reaching for it.

- Never add a fact the material does not state — no version numbers, vendor names,
  benchmarks, dates, statistics, or "typically it's around..." figures.
- Use the material's OWN example. If it demonstrates with 1011, explain with 1011;
  do not substitute a number you find neater.
- Never contradict the material, and never "correct" it.
- Padding with an unrelated outside fact is still the worst failure mode in this
  project. Explaining more of the material's OWN mechanism is not that — inventing
  a different one to explain it with is.

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


#: STEP 8 — one paragraph of concrete guidance per TeachingApproachKind, added
#: to the prompt ONLY when write_script is given an `approach` (see
#: write_script_for_workflow below). Each one is the SAME device-specific rule
#: the workflow spec itself states — process_demonstration walks a sequence,
#: comparison holds two things up together, analogy supports rather than
#: replaces the real explanation, and so on. Keyed by the exact
#: TeachingApproachKind string, so a typo here would simply fail to match
#: rather than silently applying the wrong guidance.
_APPROACH_GUIDANCE: dict[str, str] = {
    "process_demonstration": (
        "Walk the process as a sequence: the INITIAL STATE, the ACTION or "
        "CHANGE that happens, and the RESULTING STATE. Beats should follow "
        "that order — show the mechanism happening, step by step, rather "
        "than describing it as a static fact."
    ),
    "comparison": (
        "Hold the two things being compared up against each other explicitly. "
        "State what the two sides share and, at least as clearly, what "
        "actually differs — the difference IS the concept, so do not explain "
        "one side and leave the other implied."
    ),
    "analogy": (
        "Use the analogy to make the concept easier to picture, but the "
        "analogy SUPPORTS the explanation — it does not replace it. At least "
        "one beat must still explain the actual technical concept in its own "
        "terms; do not end the script having only described the analogy."
    ),
    "real_world_example": (
        "Ground the explanation in the real-world case, but connect it back "
        "EXPLICITLY to the technical concept — name the concept itself, not "
        "only the example, so a viewer leaves knowing what to call it."
    ),
    "conceptual_visual": (
        "Narrate the STRUCTURE or the STATE CHANGE — what contains what, what "
        "points to what, what changes — so the explanation supports a picture "
        "of relationships and state. Do not reach for code or syntax here "
        "unless the approved approach below is itself `code`; this device is "
        "structural, not a code walkthrough."
    ),
    "code": (
        "The code IS the concept here, so show and explain it directly — name "
        "the actual syntax, the actual keyword, the actual line from the "
        "section. This is the one approach where walking real code is the "
        "right way to teach, because the learning objective is the code "
        "itself."
    ),
    "direct_explanation": (
        "Explain the concept plainly and directly, concept-first. Do not "
        "force an analogy, a comparison, a demonstration or a code "
        "walkthrough onto it — a clear, well-ordered explanation is the "
        "complete answer here, not a placeholder for something more "
        "elaborate."
    ),
}


def write_script(topic: Topic, section: Section, feedback: str | None = None,
                 current: Script | None = None, document: str | None = None,
                 understanding: SectionUnderstanding | None = None,
                 framing: QuestionFraming | None = None,
                 approach: TeachingApproach | None = None) -> Script:
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

    `framing` AND `approach` ARE STEP 8's ADDITION, and BOTH OPTIONAL — every
    existing call site (run.py, server.py, rescript.py) omits them and gets
    BYTE-IDENTICAL behaviour to before, the same contract `understanding`
    already has one level up. Passed together (see write_script_for_workflow,
    the gated entry point that always supplies both from an approved
    QuestionWorkflow), they add ONE more guidance block to the SAME prompt and
    the SAME call — never a second LLM call to translate them into
    instructions first. `topic.topic` is still what beat 1 is built from; the
    caller that wants the TEACHING question asked (framing.teaching_question,
    which may differ from the plain approved question) passes a `topic`
    already carrying it — this function does not re-derive that choice.
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

    # STEP 8: THE APPROVED TEACHING PLAN. GUIDANCE, LIKE CONTENT UNDERSTANDING
    # ABOVE IT — never a source of claims, never something to quote. Placed
    # directly after it and before the section for the same reason: this is
    # the LAST and MOST SPECIFIC instruction about HOW to answer before the
    # model reads the one thing it may answer FROM.
    #
    # Both `framing` and `approach` are handed in TOGETHER by
    # write_script_for_workflow, or not at all by every existing caller — see
    # this function's own docstring.
    if framing is not None and approach is not None:
        user += f"""
THE APPROVED TEACHING PLAN — a human approved both of these before this
script was written. You are not re-deciding either one; follow them.
"""
        if framing.source_question and framing.source_question != topic.topic:
            user += f"ORIGINALLY APPROVED QUESTION: {framing.source_question}\n"
        if framing.framing_rationale:
            user += f"WHY IT WAS FRAMED THIS WAY: {framing.framing_rationale}\n"
        user += f"THIS QUESTION'S ROLE IN THE REEL: {framing.role}\n"

        approach_line = approach.primary
        if approach.combined_with:
            approach_line += f", combined with {', '.join(approach.combined_with)}"
        user += f"""
THE APPROVED TEACHING APPROACH — how the answer beats must teach this: {approach_line}
{_APPROACH_GUIDANCE.get(approach.primary, "")}
"""
        for extra in approach.combined_with:
            guidance = _APPROACH_GUIDANCE.get(extra)
            if guidance:
                user += f"ALSO, for the combined approach ({extra}): {guidance}\n"
        if approach.rationale:
            user += f"WHY THIS APPROACH WAS CHOSEN: {approach.rationale}\n"

        user += """
DO NOT OVERRIDE THE APPROVED APPROACH. In particular, do not reach for
showing code merely because the section happens to contain some, or because
that feels like the easiest way to fill the beats — use code only if the
approved approach above IS `code`. Everything else in this brief (grounding,
citations, length, one-idea-per-beat) still applies exactly as it always has;
the approved plan says WHAT DEVICE to teach with, not a license to relax any
other rule.
"""

    # ONLY WHEN THE READING ITSELF EARNED IT. checks.duration_budget reads the
    # exact same understanding and returns the ordinary (25, 45) unless the plan
    # holds a genuine 5th thing to say beyond MIN_PLAN_MATERIAL — see its
    # docstring. Silent otherwise: the brief's own LENGTH section above already
    # states 45 as the ceiling, and repeating that here for the common case would
    # just be noise on every call.
    _, max_seconds = checks.duration_budget(understanding)
    if max_seconds > MAX_SECONDS:
        max_words = int(max_seconds * WORDS_PER_SECOND)
        user += f"""
THIS SECTION EARNS A WIDER WINDOW THAN USUAL.
The CONTENT UNDERSTANDING above holds enough distinct material — beyond the usual
four things to say — to support more than the ordinary short. For THIS short
only, the ceiling in LENGTH above is raised from {MAX_WORDS} words (45s) to
{max_words} words (~{max_seconds}s), and EACH ANSWER BEAT may run up to
{checks.MAX_ANSWER_WORDS_EXTENDED} words instead of the usual {checks.MAX_ANSWER_WORDS}.
FIVE IS STILL THE MAXIMUM number of answer beats — this is extra room, not a
sixth beat.

THE EXTRA ROOM HAS TWO HONEST USES, AND ONLY TWO:
  1. A genuine 5th answer beat, if the plan's teaching_sequence, example or
     misconception has a distinct thing left to say that four beats did not
     cover — the beat is still its own idea, at or under
     {checks.MAX_ANSWER_WORDS_EXTENDED} words.
  2. A short clause of REASONING added to a beat that already has its citation —
     the "...which is why X" or "...so that Y" that turns a cited fact into an
     explained one. See TEACH THE CONCEPT above: this is where that reasoning
     is meant to spend its extra words, when the plan's own `purpose` or
     `explanation_goal` carries it.
Neither use is "make an existing sentence longer because you can." If four
beats at the ordinary length already say everything, four short beats is still
the finished short — this section qualifying for more room is not an
instruction to use all of it.
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


def write_script_for_workflow(workflow: QuestionWorkflow, section: Section,
                              feedback: str | None = None, current: Script | None = None,
                              document: str | None = None,
                              understanding: SectionUnderstanding | None = None,
                              ) -> QuestionWorkflow:
    """
    Step 8's entry point: write a script for a FULLY APPROVED workflow — using
    its framing and its approved teaching approach, not merely its original
    Topic — and attach the result to workflow.script.

    THE ONE GATE, THE SAME SHAPE AS frame_workflow AND
    choose_teaching_approach_for_workflow ONE AND TWO STAGES EARLIER:
      - workflow.approved_topic must be set (question approved — not pending,
        rejected, or mid-regeneration)
      - workflow.framing must exist
      - workflow.approved_teaching_approach must be set (not merely chosen —
        APPROVED: not pending, not a regeneration still awaiting review)
    All three raise ValueError, checked BEFORE any LLM call, so a workflow
    that fails any of them spends nothing.

    A NEW ENTRY POINT, write_script UNCHANGED. write_script(topic, ...) still
    works exactly as it always has for every existing caller (run.py,
    server.py, rescript.py) — this function is additive, not a replacement.
    It is a THIN WRAPPER: it gates, builds ONE Topic carrying the TEACHING
    question (see below), and calls write_script itself with `framing` and
    `approach` supplied — the SAME single call, never a second one to
    translate them first.

    THE TEACHING QUESTION DRIVES THE SCRIPT, NOT THE RAW APPROVED QUESTION.
    workflow.approved_topic.topic is the human-approved question text, but
    framing.teaching_question is the human-approved decision about HOW that
    question should actually be ASKED on screen — reframed for a clearer
    teaching flow, or identical to the approved question when no reframe was
    needed (framing.py's own contract). This function asks the TEACHING
    question in beat 1 by building a Topic whose `.topic` is
    framing.teaching_question, everything else (id, why_it_matters,
    answer_quote, concept) carried over from approved_topic unchanged — and
    the original approved question is still shown to the model, for context,
    inside the teaching-plan block write_script builds when `framing` is
    supplied. See write_script's own "THE APPROVED TEACHING PLAN".

    ONLY workflow.script IS WRITTEN. selection, question_approval, framing,
    teaching_approach, teaching_approach_approval and visual_strategy all pass
    through model_copy untouched.
    """
    topic = workflow.approved_topic
    if topic is None:
        raise ValueError(
            f"cannot write a script for {workflow.selection.topic.id}: "
            f"question_approval.status={workflow.question_approval.status!r}, "
            f"not 'approved'")
    if workflow.framing is None:
        raise ValueError(
            f"cannot write a script for {workflow.selection.topic.id}: "
            f"this workflow has no framing")
    approach = workflow.approved_teaching_approach
    if approach is None:
        raise ValueError(
            f"cannot write a script for {workflow.selection.topic.id}: "
            f"teaching_approach_approval.status="
            f"{workflow.teaching_approach_approval.status!r}, not 'approved'")

    framing = workflow.framing
    teaching_topic = topic.model_copy(update={"topic": framing.teaching_question})

    script = write_script(teaching_topic, section, feedback=feedback, current=current,
                          document=document, understanding=understanding,
                          framing=framing, approach=approach)
    return workflow.model_copy(update={"script": script})
