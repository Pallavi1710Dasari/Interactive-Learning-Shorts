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
import { FIELD_NAMES, FIELDS, C, SAFE } from "./tokens";
import { leadColor, planTransitions, ROTATION } from "./transitions";
import { formatNumber, scanSchedule } from "./animations";
import { evenWords, sentenceAt } from "./KaraokeCaption";
import { IdentitySting, IdentityTitle, LanguageBadge, SpeakerBadge, toneOn } from "./identity/Identity";
import { allIdentities, contrastRatio } from "./identity/IdentitySheet";
import { contrastChecks } from "./identity/contrast";
import { MotionFrame, chatAt, shotIndexAt, speakerAt } from "./scene/MotionStage";
import type { MotionPlan } from "./scene/types";
import demoInterviewJson from "../../public/motion-demo/interview.json";
import demoClassicJson from "../../public/motion-demo/classic.json";
import demoWalkJson from "../../public/motion-demo/walkthrough.json";
import demoPeerJson from "../../public/motion-demo/peer_discussion.json";
import demoMentorOsJson from "../../public/motion-demo/mentor_os.json";
import demoInterviewCssJson from "../../public/motion-demo/interview_css.json";
import demoClassicOsJson from "../../public/motion-demo/classic_os.json";
import demoCharactersJson from "../../public/motion-demo/interview_characters.json";
import demoJavaCharactersJson from "../../public/motion-demo/interview_java_characters.json";
import demoNarratorJson from "../../public/motion-demo/classic_os_characters.json";
import { Character } from "./characters/rig/Character";
import type { CharacterConfig } from "./characters/skins/config";
import { CharacterDesigner } from "./cast/CharacterDesigner";
import { LANGUAGES, OPTIONS, PRESET_IDS, defaultPreset, identityOf } from "./cast/presets";
import { ACTIONS, EXPRESSIONS } from "./characters/actions";
import { buildPerformance, poseOf } from "./cast/performance";
import { STAGE, performanceFor, skinFor } from "./cast/ReelCharacters";
import { FULL_KINDS } from "./scene/objects";
import { CharacterSheet } from "./cast/CharacterSheet";
import { bubbleHeight } from "./identity/Identity";
import library from "./library.json";

const demoInterview = demoInterviewJson as unknown as MotionPlan;
const demoClassic = demoClassicJson as unknown as MotionPlan;
const demoWalk = demoWalkJson as unknown as MotionPlan;
const DEMOS = {
  interview: demoInterview, peer_discussion: demoPeerJson, mentor_os: demoMentorOsJson, interview_css: demoInterviewCssJson,
  interview_characters: demoCharactersJson, interview_java_characters: demoJavaCharactersJson,
  classic_os_characters: demoNarratorJson, classic: demoClassic, classic_os: demoClassicOsJson, walkthrough: demoWalk,
} as unknown as Record<string, MotionPlan>;

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

// --------------------------------------- 4 (phase 3 badges): identities
// Every identity's symbol, corner badge, hook mark and sting: pure in t, no
// CSS animation; the sting and the speaking badge move; each tone reaches
// 3:1 on its fields (the same rule shorts/motion_identities.py enforces).
for (const { key, spec } of allIdentities()) {
  for (const f of FIELD_NAMES) {
    const tone = toneOn(spec, f);
    check(contrastRatio(tone, FIELDS[f]) >= 3 - 1e-6, `identity ${key}: ${tone} is ${contrastRatio(tone, FIELDS[f]).toFixed(2)}:1 on ${f}`);
    const badge = renderToStaticMarkup(<LanguageBadge spec={spec} field={f} right={54} top={96} />);
    check(badge === renderToStaticMarkup(<LanguageBadge spec={spec} field={f} right={54} top={96} />), `badge ${key}: not pure`);
  }
  const sting = [0.1, 0.4, 0.7].map((t) => renderToStaticMarkup(<IdentitySting spec={spec} t={t} />));
  check(new Set(sting).size === 3, `sting ${key}: does not move`);
  const mark = [0.1, 0.5, 1.2].map((t) => renderToStaticMarkup(<IdentityTitle spec={spec} label="Interview" field="navy" x={60} y={300} t={t} />));
  check(new Set(mark).size >= 2, `hook mark ${key}: does not build in`);
  for (const m of [...sting, ...mark]) check(!/animation\s*:|transition\s*:|@keyframes/.test(m), `identity ${key}: uses a CSS animation`);
  const member = { role: "CANDIDATE", side: "right" as const, label: "Candidate", voice_slot: "", identity: spec };
  const talk = [0.2, 0.5, 0.8].map((t) => renderToStaticMarkup(<SpeakerBadge member={member} field="paper" active t={t} />));
  check(new Set(talk).size >= 2, `speaker badge ${key}: the active badge does not move`);
  const still = [0.2, 0.5, 0.8].map((t) => renderToStaticMarkup(<SpeakerBadge member={member} field="paper" active={false} t={t} />));
  check(new Set(still).size === 1, `speaker badge ${key}: the listener's badge moves`);
}
// small text 4.5:1, large symbols and titles 3:1 — the same functions the player draws with
{
  const rows = contrastChecks(allIdentities());
  for (const r of rows) check(r.ratio >= r.min, `${r.element} (${r.who}, ${r.field}): ${r.fg} on ${r.bg} is ${r.ratio.toFixed(2)}:1, needs ${r.min}:1`);
  check(rows.filter((r) => r.element === "role label / speaker tag").length === allIdentities().length * FIELD_NAMES.length, "the role-label checks cover every identity on every field");
  check(allIdentities().every(({ spec }) => !!spec.text_on_dark && !!spec.text_on_light), "every identity has 4.5:1 text tones");
  const ivRow = renderToStaticMarkup(<MotionFrame plan={demoInterview} t={demoInterview.shots[3].start + 0.5} />);
  check(!/opacity:\s*0\.3/.test(ivRow), "bubble words are dimmed by colour, never by transparency");
  console.log(`  ${rows.length} contrast checks (small text 4.5:1, large 3:1)`);
}
console.log(`  ${allIdentities().length} identities checked on every field`);

// ----------------------------------------- 5 (phase 3): the full-reel stage
// The demo plans (web/public/motion-demo, from shorts/motion_demo.py): every
// shot at its start, middle and end — pure in t, no CSS animation, frames
// change through the reel, and the two-speaker logic says who talks.
for (const [name, plan] of Object.entries(DEMOS)) {
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
const ivIndex = demoInterview.shots.indexOf(ivShot);
const chat = chatAt(demoInterview, ivIndex, (cand.start + cand.end) / 2);
check(chat[chat.length - 1] === cand, "the chat's newest bubble is the caption being spoken");
check(chat.every((c) => c.start <= (cand.start + cand.end) / 2 + 0.25), "the chat shows only captions that have started");
check(demoInterview.cast.length === 2 && demoInterview.cast[0].side === "left" && demoInterview.cast[0].identity.id === "host",
      "the host is on the left");
check(!!demoInterview.identity && demoInterview.shots[0].objects.some((o) => o.kind === "identity_title"),
      "the hook shows the language mark");
console.log(`  ${Object.keys(DEMOS).length} demo plans rendered at every shot's start, middle and end`);

// ------------------------------- 6: the optional animated characters
// The rig (web/src/motion/characters, SOURCE.md) with our presets
// (shorts/motion_character_presets.yaml → cast/presets.generated.json): the
// director's vocabulary exists in the rig; every preset and every designer
// option renders; as many characters as speakers (host + language character,
// or one narrator); the layer is pure in t; the mouth follows the word
// timings; gestures move the arms; and the characters keep to their own
// region — never over the scene objects, the chat or the captions.
const LIB = library as unknown as {
  frame: { duo: { bottom: number }; chat: { bottom: number }; h: number };
  characters: { gestures: Record<string, unknown>; present: Record<string, string>; expressions: Record<string, string>;
                narrator_explain: string[] };
};
{
  const g = LIB.characters.gestures as { explain: string[]; count: Record<string, string> } & Record<string, unknown>;
  const names = [...g.explain.filter((n) => n !== "presentToward"), ...Object.values(g.count), ...Object.values(LIB.characters.present),
                 ...LIB.characters.narrator_explain, ...["why", "how", "yes", "no", "agree", "end"].map((k) => g[k] as string)];
  for (const n of names) check(!!ACTIONS[n], `the reel director names a gesture the rig lacks: ${n}`);
  for (const n of Object.values(LIB.characters.expressions)) check(!!EXPRESSIONS[n], `the reel director names an expression the rig lacks: ${n}`);

  // presets: every language has one, each a different person, each wearing its colour; every designer option draws
  const rest = poseOf(buildPerformance({ role: null, seed: 1, cues: [] }, []), 0.5);
  const drawn = new Set<string>();
  for (const id of PRESET_IDS) {
    const cfg = defaultPreset(id);
    check(!!cfg, `no default preset for ${id}`);
    const m = renderToStaticMarkup(<Character pose={rest} skin={skinFor(cfg)} width={200} />).replace(/ch-[a-z]+-[^"')]+/g, "id");
    drawn.add(m);
    const ident = identityOf(id);
    if (ident && id !== "host") check(cfg.outfit.topColor.toUpperCase() === ident.colour.toUpperCase(), `${id} does not wear its signature colour`);
  }
  check(drawn.size === PRESET_IDS.length, `every preset is a different person (${drawn.size} distinct of ${PRESET_IDS.length})`);
  for (const l of LANGUAGES) check(PRESET_IDS.includes(l), `language ${l} has no preset`);
  const base = defaultPreset("react");
  const variants: CharacterConfig[] = [
    ...OPTIONS.skinTone.map((v) => ({ ...base, skinTone: v as CharacterConfig["skinTone"] })),
    ...OPTIONS.hairStyle.map((v) => ({ ...base, hair: { ...base.hair, style: v as CharacterConfig["hair"]["style"] } })),
    ...OPTIONS.hairColor.map((v) => ({ ...base, hair: { ...base.hair, color: v as CharacterConfig["hair"]["color"] } })),
    ...OPTIONS.top.map((v) => ({ ...base, outfit: { ...base.outfit, top: v as CharacterConfig["outfit"]["top"] } })),
    ...OPTIONS.bottom.map((v) => ({ ...base, outfit: { ...base.outfit, bottom: v as CharacterConfig["outfit"]["bottom"] } })),
    ...OPTIONS.glasses.map((v) => ({ ...base, accessories: { glasses: v as "none" } })),
    ...OPTIONS.beard.map((v) => ({ ...base, accessories: { beard: v as "none" } })),
    ...OPTIONS.flags.map((k) => ({ ...base, accessories: { [k]: true } })),
    ...(["jaw", "brows", "eyes", "mouth"] as const).flatMap((k) => OPTIONS[k].map((v) => ({ ...base, face: { ...base.face, [k]: v } }))),
    ...OPTIONS.gender.map((v) => ({ ...base, gender: v as "male" })), ...OPTIONS.art.map((v) => ({ ...base, art: v as "soft" })),
  ];
  for (const v of variants) {
    try { renderToStaticMarkup(<Character pose={rest} skin={skinFor(v)} width={120} />); }
    catch (err) { check(false, `a designer option does not draw: ${JSON.stringify(v).slice(0, 120)}: ${err}`); }
  }

  // as many characters as speakers, the right people on the right sides
  const want: Record<string, [string, string][]> = {
    interview_characters: [["host", "left"], ["react", "right"]],
    interview_java_characters: [["host", "left"], ["java", "right"]],
    classic_os_characters: [["os", "center"]],
  };
  for (const [name, plan] of Object.entries(DEMOS)) {
    const got = (plan.characters ?? []).map((c) => [c.preset, c.side]);
    check(JSON.stringify(got) === JSON.stringify(want[name] ?? []), `${name}: characters ${JSON.stringify(got)}`);
    check((plan.characters ?? []).length <= Math.max(1, plan.cast.length), `${name}: more characters than speakers`);
    for (const tr of plan.characters ?? []) for (const c of tr.cues)
      check(!!(c.kind === "gesture" ? ACTIONS[c.name] : EXPRESSIONS[c.name]), `${name}: a cue names nothing in the rig: ${c.name}`);
  }

  const plan = DEMOS.interview_characters;
  // pure: the same t gives the same pose, after any jump
  const lines = plan.shots.flatMap((s) => s.captions.map((c) => ({ speaker: c.speaker, words: c.words })));
  const perf = buildPerformance(plan.characters[1], lines);
  const at = JSON.stringify(poseOf(perf, 21.3));
  poseOf(perf, 60); poseOf(perf, 2);
  check(JSON.stringify(poseOf(perf, 21.3)) === at, "a character's pose is pure in t");
  const fresh = buildPerformance(plan.characters[1], lines);
  check(JSON.stringify(poseOf(fresh, 21.3)) === at, "two performances of the same track agree");

  // lip-sync: the speaker's mouth moves inside their words; the listener's stays shut
  const mean = (a: number[]) => a.reduce((s, x) => s + x, 0) / Math.max(1, a.length);
  const mids = (p: MotionPlan, r: string | null) => p.shots.flatMap((s) => s.captions).filter((c) => (c.speaker ?? null) === r)
    .flatMap((c) => c.words).filter((w) => w.end - w.start > 0.15).map((w) => (w.start + w.end) / 2).slice(0, 40);
  const open = (p: MotionPlan, i: number, ts: number[]) => ts.map((t) => poseOf(performanceFor(p, p.characters[i]), t).mouthOpen);
  const role = (i: number) => plan.characters[i].role;
  const speaking = open(plan, 1, mids(plan, role(1)));
  const listening = open(plan, 1, mids(plan, role(0)));
  check(mean(speaking) > 0.2, `the answering character's mouth moves while speaking (mean open ${mean(speaking).toFixed(2)})`);
  check(Math.max(...listening) < 0.12, `the answering character's mouth stays shut while the host speaks (max ${Math.max(...listening).toFixed(2)})`);
  check(mean(open(plan, 0, mids(plan, role(0)))) > 0.2, "the host's mouth moves while speaking");
  check(new Set(speaking.map((v) => v.toFixed(1))).size >= 4, "the mouth makes different shapes, not one flap");
  const narr = DEMOS.classic_os_characters;
  check(mean(open(narr, 0, mids(narr, null))) > 0.2, "the narrator's mouth moves with the narration");

  // gestures move the arms
  const cue = plan.characters[1].cues.find((c) => c.kind === "gesture" && /^(handsSpread|point|pointUp|okSign|present)/.test(c.name))!;
  const ans = performanceFor(plan, plan.characters[1]);
  const before = poseOf(ans, cue.t - 0.4), during = poseOf(ans, cue.t + 0.7);
  const moved = Math.max(...(["shoulderL", "shoulderR", "elbowL", "elbowR"] as const).map((k) => Math.abs(during[k] - before[k])));
  check(moved > 10, `a gesture (${cue.name} on "${cue.cue}") moves an arm (${moved.toFixed(1)} degrees)`);

  // the layer: in its own region, only on the shots the plan says
  check(STAGE.top >= LIB.frame.duo.bottom && STAGE.bottom < STAGE.chat_top && STAGE.chat_top < LIB.frame.chat.bottom,
        "the characters' region sits between the scene objects and the chat");
  check(STAGE.bottom < SAFE.captionTop, "the characters' region ends above the one-narrator captions");
  const room = LIB.frame.chat.bottom - STAGE.chat_top;
  for (const name of Object.keys(want)) {
    const p = DEMOS[name];
    if (p.cast.length) for (const s of p.shots) for (const c of s.captions)
      check(bubbleHeight(c.words.map((w) => w.text).join(" ")) <= room, `${name}: a bubble taller than the chat region: "${c.text}"`);
    for (const s of p.shots) {
      const m = renderToStaticMarkup(<MotionFrame plan={p} t={(s.start + s.end) / 2} />);
      const full = s.objects.some((o) => FULL_KINDS.has(o.kind));
      const has = m.includes('data-part="characters"');
      check(has === !!s.characters, `${name} ${s.id}: characters ${has ? "drawn" : "missing"} but the plan says ${s.characters}`);
      if (full) check(!has, `${name} ${s.id}: characters over a full-frame card`);
      if (!s.characters) continue;
      for (const [preset] of want[name]) check(m.includes(`data-character="${preset}"`), `${name} ${s.id}: ${preset} not drawn`);
      check((m.match(/data-character="/g) ?? []).length === want[name].length, `${name} ${s.id}: more characters than speakers`);
      if (p.cast.length) check(m.includes('data-part="chat"'), `${name} ${s.id}: the chat is clipped to its region`);
      check((m.match(/data-part="backdrop"/g) ?? []).length === want[name].length, `${name} ${s.id}: a soft backdrop behind each character`);
      for (const o of s.objects) if (o.box && o.box.h) check(o.box.y + o.box.h <= STAGE.top, `${name} ${s.id}: ${o.kind} reaches into the characters' region`);
    }
  }
  const plain = renderToStaticMarkup(<MotionFrame plan={demoInterview} t={20} />);
  check(!plain.includes('data-part="characters"') && !plain.includes('data-part="chat"'), "a plan without characters draws none and keeps the old chat");

  // the review pages: every language's character, every expression and gesture; the designer's controls
  const sheet = renderToStaticMarkup(<CharacterSheet />);
  for (const id of PRESET_IDS) check(sheet.includes(`data-preset="${id}"`), `#motion/characters lacks the ${id} character`);
  for (const n of Object.keys(EXPRESSIONS)) check(sheet.includes(`data-item="expression:${n}"`), `#motion/characters lacks expression ${n}`);
  for (const n of Object.keys(ACTIONS)) check(sheet.includes(`data-item="gesture:${n}"`), `#motion/characters lacks gesture ${n}`);
  const designer = renderToStaticMarkup(<CharacterDesigner />);
  for (const c of ["name", "gender", "art", "skinTone", "hairStyle", "hairColor", "jaw", "brows", "eyes", "mouth", "top", "topColor",
                   "bottom", "bottomColor", "shoeColor", "accentColor", "glasses", "beard", ...OPTIONS.flags])
    check(designer.includes(`data-control="${c}"`), `the designer has no ${c} control`);
  check(designer.includes('data-action="save"') && designer.includes('data-action="reset"'), "the designer saves and resets");
  for (const id of PRESET_IDS) check(designer.includes(`data-preset="${id}"`), `the designer cannot pick ${id}`);
  console.log(`  characters: ${PRESET_IDS.length} presets, ${variants.length} designer options, ${Object.keys(EXPRESSIONS).length} expressions, ${Object.keys(ACTIONS).length} gestures; one-vs-two, lip-sync, purity and regions checked`);
}

if (failures) {
  console.log(`\n${failures} MOTION CHECK(S) FAILED.`);
  process.exit(1);
}
console.log("\nALL MOTION CHECKS PASSED.");
