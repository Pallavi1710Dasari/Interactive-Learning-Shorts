// Checks for the motion library, run with:
//
//     node web/scripts/test-motion.mjs
//
// (esbuild bundles this file, then plain node runs it — the web side has no
// test framework, and .tsx cannot run under node's type stripping.)
//
// 1. PURE IN t: every gallery entry, rendered twice at the same t, gives the
//    same markup; and no markup ever contains a CSS animation or transition,
//    the two ways a frame could depend on wall-clock time instead of t.
// 2. IT MOVES: every transition and animation renders differently across its
//    duration (a component stuck on one frame would pass check 1).
// 3. Rules: transitions rotate and never repeat back to back; lead colours are
//    field colours, never coral or mint; count_up groups digits correctly.

import { renderToStaticMarkup } from "react-dom/server";
import { ENTRIES } from "./gallery/catalog";
import { FIELD_NAMES, FIELDS, C } from "./tokens";
import { leadColor, planTransitions, ROTATION } from "./transitions";
import { formatNumber, scanSchedule } from "./animations";
import { evenWords, sentenceAt } from "./KaraokeCaption";
import { Avatar, mouthOpen } from "./avatars/Avatar";
import { allAvatars } from "./avatars/AvatarSheet";
import { MotionFrame, avatarState, shotIndexAt, speakerAt } from "./scene/MotionStage";
import type { MotionPlan } from "./scene/types";
import demoInterviewJson from "../../public/motion-demo/interview.json";
import demoClassicJson from "../../public/motion-demo/classic.json";
import demoWalkJson from "../../public/motion-demo/walkthrough.json";

const demoInterview = demoInterviewJson as unknown as MotionPlan;
const demoClassic = demoClassicJson as unknown as MotionPlan;
const demoWalk = demoWalkJson as unknown as MotionPlan;

let failures = 0;
function check(ok: boolean, msg: string) {
  if (!ok) { failures++; console.log(`  FAIL ${msg}`); }
}

// ---------------------------------------------------------------- 1 + 2
for (const e of ENTRIES) {
  const ts = [0, e.dur * 0.25, e.dur * 0.5, e.dur * 0.75, e.dur];
  let marks: string[];
  try { marks = ts.map((t) => renderToStaticMarkup(<>{e.render(t, e.field)}</>)); }
  catch (err) { check(false, `${e.id}: throws: ${err}`); continue; }
  ts.forEach((t, i) => {
    const again = renderToStaticMarkup(<>{e.render(t, e.field)}</>);
    check(again === marks[i], `${e.id}: two renders at t=${t.toFixed(2)} differ — not pure in t`);
    check(!/animation\s*:|transition\s*:|@keyframes/.test(marks[i]), `${e.id}: uses a CSS animation or transition`);
  });
  if (e.group === "Transitions" || e.group === "Animations" || e.group === "Chapter card") {
    check(new Set(marks).size >= 3, `${e.id}: fewer than 3 distinct frames across its ${e.dur}s — does it move?`);
  }
  if (e.both) {
    for (const f of FIELD_NAMES) {
      try { renderToStaticMarkup(<>{e.render(e.dur, f)}</>); }
      catch (err) { check(false, `${e.id}: throws on the ${f} field: ${err}`); }
    }
  }
}
console.log(`  ${ENTRIES.length} gallery entries rendered at 5 times each`);

// --------------------------------------------------------------------- 3
const plan = planTransitions(12);
check(plan.every((k, i) => i === 0 || k !== plan[i - 1]), "planTransitions repeats a transition back to back");
check(new Set(plan).size === ROTATION.length, "planTransitions does not use every transition");
for (const a of FIELD_NAMES) for (const b of FIELD_NAMES) {
  if (a === b) continue;
  const lead = leadColor(a, b);
  check((Object.values(FIELDS) as string[]).includes(lead), `lead colour ${lead} (${a}->${b}) is not a field colour`);
  check(lead !== C.coral && lead !== C.mint, `lead colour ${a}->${b} is coral or mint`);
  check(lead !== FIELDS[a] && lead !== FIELDS[b], `lead colour ${a}->${b} matches one of the two fields`);
}
check(formatNumber(120000, "indian") === "1,20,000", `indian grouping: ${formatNumber(120000, "indian")}`);
check(formatNumber(120000, "intl") === "120,000", `intl grouping: ${formatNumber(120000, "intl")}`);
check(formatNumber(768, "indian") === "768", "small numbers are not grouped");
const sched = scanSchedule("Tokenization", [{ len: 2, label: "To" }, { len: 3, label: "ken" }, { len: 7, label: "ization" }]);
check(sched[0].steps === 10 && sched[1].steps === 7 && sched[2].steps === 0, `scan steps ${sched.map((s) => s.steps)}`);
check(sched.every((s, i) => i === 0 || s.start > sched[i - 1].end), "scan pieces overlap in time");
const sentence = evenWords("Every model has a <b>vocabulary</b>.", 1, 3);
check(sentence.words.length === 5 && sentence.words[4].hl && !sentence.words[0].hl, "evenWords highlights");
check(sentenceAt([sentence], 0.5) === null && sentenceAt([sentence], 1.2) === sentence, "sentenceAt");

// ------------------------------------------------- 4 (phase 3): avatars
// Every avatar in every state: pure in t, no CSS animation, and talking
// actually moves (the mouth and the head) while idle stays nearly still.
for (const { key, spec } of allAvatars()) {
  for (const state of ["idle", "talking", "reacting"] as const) {
    const frames = [0.2, 0.55, 0.9, 1.3].map((t) => renderToStaticMarkup(<Avatar spec={spec} state={state} t={t} since={t} />));
    frames.forEach((m, i) => {
      const again = renderToStaticMarkup(<Avatar spec={spec} state={state} t={[0.2, 0.55, 0.9, 1.3][i]} since={[0.2, 0.55, 0.9, 1.3][i]} />);
      check(again === m, `avatar ${key} ${state}: not pure in t`);
      check(!/animation\s*:|transition\s*:|@keyframes/.test(m), `avatar ${key} ${state}: uses a CSS animation`);
    });
    if (state === "talking") check(new Set(frames).size >= 3, `avatar ${key} talking: does not move`);
  }
  const idle = renderToStaticMarkup(<Avatar spec={spec} state="idle" t={1} />);
  const react = renderToStaticMarkup(<Avatar spec={spec} state="reacting" t={1} since={0.5} />);
  check(idle !== react, `avatar ${key}: reacting looks like idle`);
}
check(mouthOpen(0.5, 3) >= 0 && mouthOpen(0.5, 3) <= 1, "mouthOpen out of range");
console.log(`  ${allAvatars().length} avatars x 3 states rendered`);

// ----------------------------------------- 5 (phase 3): the full-reel stage
// The demo plans (web/public/motion-demo, from shorts/motion_demo.py): every
// shot at its start, middle and end — pure in t, no CSS animation, frames
// change through the reel, and the two-speaker logic says who talks.
for (const [name, plan] of Object.entries({ interview: demoInterview, classic: demoClassic, walkthrough: demoWalk }) as [string, MotionPlan][]) {
  const seen = new Set<string>();
  for (const shot of plan.shots) {
    for (const t of [shot.start + 0.01, (shot.start + shot.end) / 2, shot.end - 0.02]) {
      let m: string;
      try { m = renderToStaticMarkup(<MotionFrame plan={plan} t={t} />); }
      catch (err) { check(false, `${name} ${shot.id} at ${t.toFixed(2)}: throws: ${err}`); continue; }
      check(m === renderToStaticMarkup(<MotionFrame plan={plan} t={t} />), `${name} ${shot.id}: not pure in t`);
      check(!/animation\s*:|transition\s*:|@keyframes/.test(m), `${name} ${shot.id}: uses a CSS animation`);
      seen.add(m);
    }
    check(shotIndexAt(plan, shot.start + 0.01) === plan.shots.indexOf(shot), `${name}: shotIndexAt ${shot.id}`);
  }
  check(seen.size >= plan.shots.length * 2, `${name}: the reel barely changes (${seen.size} distinct frames)`);
}
const ivShot = demoInterview.shots.find((s) => s.captions.some((c) => c.speaker === "CANDIDATE"))!;
const cand = ivShot.captions.find((c) => c.speaker === "CANDIDATE")!;
check(speakerAt(ivShot, (cand.start + cand.end) / 2) === "CANDIDATE", "speakerAt");
check(avatarState(ivShot, "CANDIDATE", (cand.start + cand.end) / 2).state === "talking", "the speaker talks");
check(avatarState(ivShot, "INTERVIEWER", (cand.start + cand.end) / 2).state !== "talking", "the listener is not talking");
const q = demoInterview.shots.flatMap((s) => s.captions.map((c) => ({ s, c })))
  .find(({ c }) => c.speaker === "INTERVIEWER" && /\?\s*$/.test(c.text.replace(/<\/?b>/g, "")))!;
check(avatarState(q.s, "CANDIDATE", q.c.end + 0.2).state === "reacting", "the listener reacts to a question");
console.log("  3 demo plans rendered at every shot's start, middle and end");

if (failures) {
  console.log(`\n${failures} MOTION CHECK(S) FAILED.`);
  process.exit(1);
}
console.log("\nALL MOTION CHECKS PASSED.");
