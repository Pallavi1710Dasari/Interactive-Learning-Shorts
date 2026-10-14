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
import { CAMERA, cameraAt, cursorAt, framingOf, project, typedChars } from "./camera";
import { BOARD, placement, teach, toStage } from "./cast/teach";
import { buildSkin } from "./characters/skins/config";
import { CHANNELS, type Pose } from "./characters/rig/channels";
import { FACE, SHAPES, armPrograms, visemes } from "./vrm/pose3d";
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

// ---------------------------------------------------------- camera, cursor, teaching (2026-10-13)
{
  // the camera framing is motion_camera.framing: the rect whole, the zoom in range, the layer covering the viewport
  const vp: [number, number, number, number] = [0, 150, 1080, 1154];
  for (const [rect, zoom] of [[[110, 442, 150, 90], 1.7], [[60, 455, 779, 102], 1.4], [[10, 160, 1000, 900], 1.8]] as [[number, number, number, number], number][]) {
    const f = framingOf(rect, zoom, vp);
    if (f.s === 1) continue;           // too big to zoom on: the camera stays wide (the director drops such a cue)
    const [x, y] = project(f, vp, rect[0], rect[1]);
    const [x1, y1] = project(f, vp, rect[0] + rect[2], rect[1] + rect[3]);
    check(x >= vp[0] + CAMERA.margin - 1 && y >= vp[1] + CAMERA.margin - 1 && x1 <= vp[0] + vp[2] - CAMERA.margin + 1
          && y1 <= vp[1] + vp[3] - CAMERA.margin + 1, `camera cuts off ${rect} at ${f.s.toFixed(2)}`);
    check(f.s >= 1 && f.s <= zoom + 1e-9, `camera zoom ${f.s} for ${rect}`);
    const [cx0, cy0] = project(f, vp, vp[0], vp[1]);
    const [cx1, cy1] = project(f, vp, vp[0] + vp[2], vp[1] + vp[3]);
    check(cx0 <= vp[0] + 1e-6 && cy0 <= vp[1] + 1e-6 && cx1 >= vp[0] + vp[2] - 1e-6 && cy1 >= vp[1] + vp[3] - 1e-6,
          `the zoomed layer leaves an empty edge for ${rect}`);
  }
  // same numbers as Python (shorts/motion_camera_test.py pins the same case): the focus is
  // clamped right of the token so the zoomed layer leaves no empty edge on the left
  const f = framingOf([110, 442, 150, 90], 1.7, vp);
  check(Math.abs(f.s - 1.7) < 1e-9 && Math.abs(f.fx - 317.65) < 0.02 && Math.abs(f.fy - 489.41) < 0.02, `framing ${JSON.stringify(f)}`);
  // a cue eases in, holds, eases out; wide before and after
  const cue = { t0: 10, t1: 13, target: "o1", part: 1, rect: [110, 442, 150, 90] as [number, number, number, number], zoom: 1.7, viewport: vp };
  check(cameraAt([cue], vp, 9.9).s === 1 && cameraAt([cue], vp, 14).s === 1, "the camera is wide outside its cue");
  check(cameraAt([cue], vp, 11.5).s > 1.69, `the camera holds its zoom (${cameraAt([cue], vp, 11.5).s})`);
  // the cursor: arrives under its target and presses on the cue word; types to the end by t_end
  const cur = [{ t: 5, do: "click" as const, target: "o1", part: 1, rect: [100, 400, 200, 80] as [number, number, number, number] }];
  const at = cursorAt(cur, 5)!;
  check(Math.abs(at.x - (100 + 200 * 0.58)) < 1 && Math.abs(at.y - 486) < 1, `cursor rests at ${at.x},${at.y}`);
  check(cursorAt(cur, 5.08)!.press > 0 && cursorAt(cur, 5.3)!.ripple > 0, "the cursor presses and ripples");
  check(cursorAt(cur, 0) === null, "the cursor is hidden before it is needed");
  const typing = { t: 1, do: "type" as const, target: "o1", part: 1, rect: [0, 0, 10, 10] as [number, number, number, number], text: "cart = 1", t_end: 2 };
  check(typedChars(typing, 0.9) === 0 && typedChars(typing, 2) === 8 && typedChars(typing, 1.5) === 4, "typing pace");

  // teaching: an aim points the finger at its target; a held count keeps the arm up
  const track = { role: "MENTOR", preset: "cs", config: defaultPreset("cs"), side: "right" as const, seed: 3, cues: [] as never[] };
  const place = placement(BOARD.explainer);
  const skin = buildSkin(defaultPreset("cs"));
  const base = { ...CHANNELS } as unknown as Pose;
  const rect = [60, 300, 300, 120];
  const aimed = teach(base, { ...track, cues: [{ t: 1, kind: "aim", name: "", side: "L", until: 3, rect, target: "o1", full: false, cue: "" }] as never[] },
                      place, skin, 2, null).pose as unknown as Record<string, number>;
  const [tx, ty] = toStage(false, rect[0] + rect[2] / 2, rect[1] + rect[3] / 2);
  const px = place.left + (200 - (skin.shoulderHalf - 6)) * place.scale, py = place.top + 205 * place.scale;
  // the screen-left arm hangs along +y and turns by the shoulder angle (minus the elbow's share)
  const ang = ((aimed.shoulderL - aimed.elbowL * 0.55) * Math.PI) / 180;
  const dir = [-Math.sin(ang), Math.cos(ang)];
  const want = [tx - px, ty - py];
  const cos = (dir[0] * want[0] + dir[1] * want[1]) / Math.hypot(want[0], want[1]);
  check(cos > 0.995, `the aim misses its target (cos ${cos.toFixed(3)})`);
  const counted = (n: number) => teach(base, { ...track, cues: [
    { t: 1, kind: "count", name: "two", side: "L", until: 2.2, cue: "" }, { t: 2.05, kind: "count", name: "one", side: "L", until: 3.5, cue: "" }] as never[] },
    place, skin, n, null).pose as unknown as Record<string, number>;
  for (const tt of [1.5, 2.0, 2.1, 2.5, 3.0]) check(counted(tt).elbowL < -100, `the counting arm drops between counts at ${tt}s (${counted(tt).elbowL})`);
  check(counted(1.6).fL2 < 0.2 && counted(3.0).fL2 > 0.8, "the fingers change between counts");
  const jaw = teach({ ...base, mouthOpen: 0.6 } as Pose, { ...track, env: { t0: 0, fps: 30, v: [0, 0, 1, 1, 0, 0] } } as never, place, skin, 2 / 30, null).pose as unknown as Record<string, number>;
  const shut = teach({ ...base, mouthOpen: 0.6 } as Pose, { ...track, env: { t0: 0, fps: 30, v: [0, 0, 1, 1, 0, 0] } } as never, place, skin, 4.5 / 30, null).pose as unknown as Record<string, number>;
  check(jaw.mouthOpen > shut.mouthOpen * 1.5, "the jaw follows the voice's loudness");
  console.log("  camera framing, cursor, aims, held counts and the voice's jaw checked");
}

// ---------------------------------------------------------- the studio design (2026-10-13)
{
  const classic = demoClassicJson as unknown as MotionPlan;
  const at = classic.shots[2].start + 1;
  const before = renderToStaticMarkup(<MotionFrame plan={classic} t={at} />);
  const coral = C.coral;
  for (const palette of ["chalkboard", "paper", "terminal_amber", "deep_teal", "plum_gold", "midnight"]) {
    const studioPlan = { ...classic, rev: 3, design: palette === "midnight" ? "midnight_lab" : "studio", palette } as MotionPlan;
    const a = renderToStaticMarkup(<MotionFrame plan={studioPlan} t={at} />);
    const b = renderToStaticMarkup(<MotionFrame plan={studioPlan} t={at} />);
    check(a === b, `the ${palette} frame is not pure in t`);
    check(a !== before, `the ${palette} palette changes nothing`);
    check(!/animation|transition:/.test(a), `the ${palette} frame has a CSS animation or transition`);
  }
  const after = renderToStaticMarkup(<MotionFrame plan={classic} t={at} />);
  check(after === before && C.coral === coral, "a palette leaks into a reel drawn after it (old reels must not change)");
  console.log("  studio: 6 palettes drawn pure, and an old reel drawn after them is unchanged");
}

// ---------------------------------------------------------- 3D avatars (vrm/pose3d.ts)
{
  const pose = { ...CHANNELS, mouthOpen: 0.8, mouthWide: 0.6, pucker: 0.1 } as unknown as Pose;
  const shut = visemes(pose, 1, false);
  check(Object.values(shut).every((v) => v === 0), "a 3D mouth moves while its character is not speaking");
  const open = visemes(pose, 1, true);
  check(open.aa > 0.2 && Object.values(open).every((v) => v >= 0 && v <= 1), `3D visemes ${JSON.stringify(open)}`);
  check(visemes(pose, 0, true).aa < open.aa, "the 3D jaw does not follow the voice's loudness");
  // professional: never more than a light smile, whatever the director cues
  for (const name of Object.keys(FACE)) check((FACE[name].happy ?? 0) <= 0.25, `the 3D "${name}" face smiles too much`);
  const tr = { role: "MENTOR", preset: "cs", config: {} as never, side: "right" as const, seed: 1, cues: [
    { t: 1, kind: "count", name: "two", side: "L", until: 3, cue: "" },
    { t: 4, kind: "aim", name: "", side: "L", until: 6, rect: [100, 300, 200, 100], target: "o1", full: false, cue: "" },
    { t: 7, kind: "gesture", name: "handsSpread", cue: "" },
    { t: 7.2, kind: "gesture", name: "nod", cue: "" },
  ] as never[] };
  const at = (t: number) => armPrograms(tr as never, t, [{ start: 7.5, end: 7.8 }], "right", () => [0, 0]);
  check(at(2).right.length === 1 && at(2).right[0].shape.fingers.join() === "0,0,1,1", "the held count of two is not on the board-side arm");
  check(at(5).right.some((p) => p.aim) && at(5).left.length === 0, "the point is not on the board-side arm");
  check(at(7.6).left.length === 1 && at(7.6).right.length === 1 && at(7.6).left[0].beat > 0, "explaining is not both palms, with a beat on the word");
  check(at(9.5).left.length === 0 && at(9.5).right.length === 0, "a gesture does not return to rest");
  check(SHAPES.point.fingers.join() === "0,1,1,1" && SHAPES.point.thumb > 0.8, "the point is not index out, the others curled, thumb tucked");
  console.log("  3D avatars: mouth, quiet face, held count, point, explain beats and rest checked");
}

if (failures) {
  console.log(`\n${failures} MOTION CHECK(S) FAILED.`);
  process.exit(1);
}
console.log("\nALL MOTION CHECKS PASSED.");
