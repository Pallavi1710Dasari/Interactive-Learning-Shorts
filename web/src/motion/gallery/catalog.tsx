// Everything the #motion-gallery shows, one entry per object, transition and
// animation. The DEMO CONTENT mirrors the reference reels so each entry can
// be compared frame by frame with web/public/reference/<ref>/ — the library
// components themselves know nothing about any topic.

import type { ReactNode } from "react";
import { Frame, Layer } from "../Stage";
import { C, FIELDS, H, W, theme, type FieldName } from "../tokens";
import { seg } from "../time";
import { ProgressSegments, SectionLabel, StepChip, CornerMark } from "../chrome";
import { KaraokeCaption, evenWords } from "../KaraokeCaption";
import {
  CodeMapCard, CodeWindow, Connector, DeviceMock, DotGrid, EndCard, EntityCard, IconTile, StatusPill,
  SystemPanel, TakeawayList, TitleCard, TriggerChip,
} from "../objects/reference";
import {
  BigCounter, Bracket, Callout, ChapterCard, CHAPTER_CARD, Chip, ChipTag, KineticTitle, LookupGrid, LookupTable,
  MatrixGrid, RecapGrid, Stamp, TextureBackground, TokenRow, rowLayout, type MatrixCell, type RowItem,
} from "../objects/editorial";
import { FieldTransition, SCATTER, TRANSITION_DUR, TypeScatter, type TransitionKind } from "../transitions";
import {
  ArrowDraw, CategoryHighlight, ChipInsert, CounterMorph, CountUp, GhostWord, GridCascade, ScanWindow, SearchType,
  SlotScroll, StaggerRows, StampSlam, TextScramble, TypeAssemble, TypewriterCursor, ZoomCell, scanSchedule,
  type GridSpec, type ScanPiece,
} from "../animations";

export type Group = "Set 1 objects" | "Set 2 objects" | "Chrome and captions" | "Transitions" | "Chapter card" | "Animations";

export interface Entry {
  id: string;
  group: Group;
  title: string;
  note: string;
  /** Seconds the entry runs; the scrubber's range. */
  dur: number;
  /** The field it plays on in the gallery. */
  field: FieldName;
  /** Objects are shown on paper AND a dark field (addendum 7, phase 2). */
  both?: boolean;
  /** The manifest id of its reference frames, when the reel has the move. */
  ref?: string;
  render: (t: number, field: FieldName) => ReactNode;
}

// --------------------------------------------------------------- demo data

const SHELF_WORDS = ("the of and to in is it you that was for on are with as his they be at one have this from or had by " +
  "word but what some we can out other were all there when up use your how said an each she which do their time if will way " +
  "about many then them write would like so these her long make thing see him two has look more day could go come did number " +
  "sound no most people my over know water than call first who may down side been now find any new work part take get place " +
  "made live where after back little only round man year came show every good me give our under name very through just form " +
  "##s ##ed ##ing ##able ##ly ##er matters ##ken ##ization dream rain train piece city").split(" ");
const SHELF: GridSpec = {
  cells: SHELF_WORDS.slice(0, 84), cols: 6, x: 60, y: 260, w: 960, cellH: 62, gap: 12,
  readable: [39, 40, 45, 46, 51, 52, 57, 58, 63, 64, 69, 70],
};
const MATTERS = SHELF_WORDS.indexOf("matters");

const SENTENCE: RowItem[] = [{ text: "Tokenization" }, { text: "matters" }, { text: "." }];
const TOKENS: RowItem[] = [{ text: "To" }, { text: "##ken" }, { text: "##ization" }, { text: "matters" }, { text: "." }];
const WITH_SPECIAL: RowItem[] = [{ text: "[CLS]", tone: "key" }, ...TOKENS, { text: "[SEP]", tone: "special" }];
const IDS: RowItem[] = ["101", "11469", "11862", "19988", "50807", "119", "102"].map((text) => ({ text }));

const ID_TABLE: [string, string][] = [
  ["0", "[PAD]"], ["100", "[UNK]"], ["101", "[CLS]"], ["102", "[SEP]"], ["103", "[MASK]"], ["119", "."],
  ["2386", "book"], ["4496", "song"], ["6685", "##ing"], ["8873", "river"], ["11062", "##ken"], ["11143", "river"],
  ["11225", "the"], ["16576", "##ed"], ["18278", "city"], ["19988", "##ization"], ["26145", "city"],
  ["38476", "data"], ["44642", "##s"], ["50807", "matters"], ["51784", "run"], ["52761", "##ed"],
];

const cap = (field: FieldName, text: string, t: number, a = 0.2, b = 2.6) =>
  <KaraokeCaption sentences={[evenWords(text, a, b)]} t={t} field={field} />;

function batch(): MatrixCell[][] {
  const row = (n: number, sep: number): MatrixCell[] => Array.from({ length: 7 }, (_, i) =>
    i === 0 ? { tone: "key" } : i === sep ? { tone: "special" } : i > sep ? { tone: "pad", text: "PAD" } : { tone: "plain" });
  return [row(7, 6), row(7, 3), row(7, 4)];
}
function mask(): MatrixCell[][] {
  return [6, 3, 4].map((sep) => Array.from({ length: 7 }, (_, i) =>
    i <= sep ? { tone: "ok" as const, text: "1" } : { tone: "bad" as const, text: "0" }));
}

// ------------------------------------------------------ scenes for transitions

function HookAnswer({ field }: { field: FieldName }) {
  return (
    <>
      <TextureBackground t={6} field={field} />
      <SectionLabel text="IT ONLY READS" x={W / 2} y={470} field={field} align="center" />
      <BigCounter value="NUMBERS." x={W / 2} y={600} size={170} field={field} framed />
    </>
  );
}
function FollowOne({ field }: { field: FieldName }) {
  return (
    <>
      <SectionLabel text="FOLLOW ONE SENTENCE" x={W / 2} y={420} field={field} align="center" accent />
      <TokenRow items={[{ text: "Tokenization" }, { text: "matters." }]} x={W / 2} y={520} field={field} size={44} center />
    </>
  );
}
function ShelfScene({ field }: { field: FieldName }) {
  return <><StepChip n={2} of={4} field={field} /><LookupGrid {...SHELF} field={field} /></>;
}
function SevenTokens({ field }: { field: FieldName }) {
  return (
    <>
      <StepChip n={3} of={4} field={field} />
      <BigCounter value="7" label="TOKENS" x={W / 2} y={520} size={300} field={field} />
      <TokenRow items={WITH_SPECIAL} x={W / 2} y={780} field={field} size={28} center />
    </>
  );
}
function BatchScene({ field }: { field: FieldName }) {
  return (
    <>
      <StepChip n={4} of={4} field={field} />
      <MatrixGrid cells={batch()} x={130} y={330} field={field} rowLabels={["S1", "S2", "S3"]} bracket label="Batch" />
      <MatrixGrid cells={mask()} x={200} y={760} field={field} label="Attention mask" cell={72} />
    </>
  );
}
const cardScene = (n: number, title: string) => ({ field }: { field: FieldName }) =>
  <ChapterCard n={n} of={4} title={title} field={field} t={1.6} />;

function transitionEntry(kind: TransitionKind, from: FieldName, to: FieldName,
                         Out: (p: { field: FieldName }) => ReactNode, In: (p: { field: FieldName }) => ReactNode,
                         title: string, note: string, origin?: [number, number]): Entry {
  return {
    id: kind, group: "Transitions", title, note, dur: TRANSITION_DUR + 0.25, field: from, ref: kind,
    render: (t) => (
      <Frame field={from}>
        <FieldTransition kind={kind} from={from} to={to} t={t} origin={origin}
                         outgoing={<Out field={from} />} incoming={<In field={to} />} />
      </Frame>
    ),
  };
}

// ----------------------------------------------------------------- entries

const Settled = 9;

export const ENTRIES: Entry[] = [
  // ---------------------------------------------------------- set 1 objects
  { id: "device_mock", group: "Set 1 objects", title: "DeviceMock", note: "Phone with a post. Taps ripple; a failed tap shakes the count coral; the liked heart is mint.",
    dur: 3, field: "paper", both: true,
    render: (t, f) => {
      const taps = [0.4, 1.2, 2.0];
      const last = taps.filter((x) => t >= x).pop();
      const liked = t >= 2.0;
      return <Frame field={f}><DotGrid field={f} />
        <DeviceMock x={W / 2} y={460} likes={liked ? 1 : 0} liked={liked} field={f}
                    tapAge={last === undefined ? 99 : t - last} failAge={last !== undefined && last < 2 ? t - last - 0.1 : 99} />
        {liked && <StatusPill x={640} y={1215} text="It works" tone="ok" icon="check" field={f} p={seg(t, 2.1, 0.4)} />}
      </Frame>;
    } },
  { id: "entity_card", group: "Set 1 objects", title: "EntityCard", note: "The thing that runs. A render pass sweeps it; the value is re-created mid-pass.",
    dur: 2.2, field: "paper", both: true,
    render: (t, f) => {
      const sweep = seg(t, 0.4, 0.85);
      const after = sweep > 0.56;
      return <Frame field={f}><DotGrid field={f} />
        <EntityCard x={90} y={600} label="<LikeButton />" value={after ? 0 : 1} valueTone={after ? "bad" : "plain"}
                    code={after ? "let likes = 0" : "let likes = 1"} codeTone={after ? "bad" : "warn"}
                    note={after ? "recreated" : "after tap"} renderCount={after ? 2 : 1}
                    sweep={t >= 0.4 && t < 1.25 ? sweep : -1} field={f} /></Frame>;
    } },
  { id: "system_panel", group: "Set 1 objects", title: "SystemPanel", note: "The thing that remembers. Empty, then holding a slot that pulses when it changes.",
    dur: 2, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><DotGrid field={f} />
      <SystemPanel x={120} y={640} title="React" status={t > 0.5 ? "Holding state" : "Idle"} statusTone={t > 0.5 ? "info" : "plain"}
                   slot={t > 0.8 ? { name: "likes", value: t > 1.4 ? 1 : 0, pulse: Math.max(0, 1 - Math.abs(t - 1.5) * 6) } : null}
                   glow={t > 0.8 ? 0.9 : 0} field={f} /></Frame> },
  { id: "connector", group: "Set 1 objects", title: "Connector", note: "A pulse travels the line; a broken connector shows an x.",
    dur: 1.6, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><DotGrid field={f} />
      <Connector points={[[300, 700], [300, 1000], [780, 1000], [780, 1300]]} field={f} pulse={seg(t, 0.2, 0.9)} />
      <Connector points={[[200, 1450], [880, 1450]]} broken field={f} /></Frame> },
  { id: "code_window", group: "Set 1 objects", title: "CodeWindow", note: "Lines pop in one at a time; the amber bar marks the line being talked about.",
    dur: 1.6, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><DotGrid field={f} />
      <CodeWindow x={66} y={630} file="LikeButton.jsx" field={f} shown={seg(t, 0.1, 0.4) + seg(t, 0.9, 0.4)} highlight={t > 0.9 ? 1 : 0}
                  lines={[[{ text: "let", color: C.codeKeyword }, { text: " likes = " }, { text: "0", color: C.amber }, { text: ";" }],
                          [{ text: "const", color: C.codeKeyword }, { text: " " }, { text: "onTap", color: C.codeFn }, { text: " = () => likes++;" }]]} /></Frame> },
  { id: "chips_and_pills", group: "Set 1 objects", title: "TriggerChip, StatusPill, IconTile", note: "The call that causes change (amber), and state pills: coral fails, mint works.",
    dur: 1.4, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><DotGrid field={f} />
      <TriggerChip x={W / 2} y={620} label="setLikes(1)" field={f} p={seg(t, 0, 0.4)} firing={Math.max(0, 1 - Math.abs(t - 1) * 4)} />
      <StatusPill x={340} y={820} text="Still 0" tone="bad" icon="x" field={f} p={seg(t, 0.2, 0.4)} />
      <StatusPill x={740} y={820} text="It works" tone="ok" icon="check" field={f} p={seg(t, 0.35, 0.4)} />
      {(["refresh", "memory", "bolt"] as const).map((n, i) =>
        <IconTile key={n} x={300 + i * 240} y={1060} size={150} icon={n} tone={(["bad", "info", "warn"] as const)[i]} field={f} p={seg(t, 0.5 + i * 0.12, 0.4)} />)}
    </Frame> },
  { id: "title_card", group: "Set 1 objects", title: "TitleCard", note: "Series pill, the concept, the promise, the icon vocabulary. Its own gradient field.",
    dur: 2.4, field: "blue",
    render: (t) => <Frame field="blue"><TitleCard series="React Hooks · Episode 1" title="useState" promise="Why plain variables forget"
      icons={[{ name: "refresh", label: "Render" }, { name: "memory", label: "Memory" }, { name: "bolt", label: "Trigger" }]} t={t} /></Frame> },
  { id: "code_map_card", group: "Set 1 objects", title: "CodeMapCard", note: "The real syntax, each part tied to what it controls.",
    dur: 2, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><DotGrid field={f} />
      <CodeMapCard field={f} t={t} active={t < 0.8 ? -1 : t < 1.4 ? 0 : 1}
        line1={[{ text: "const", color: C.codeKeyword }, { text: " [likes, setLikes]" }]}
        line2={[{ text: "  = " }, { text: "useState", color: C.codeFn }, { text: "(" }, { text: "0", color: C.amber }, { text: ");" }]}
        parts={[{ at: [7, 5], icon: "memory", tone: "info", name: "likes", desc: "the current value" },
                { at: [14, 8], icon: "bolt", tone: "warn", name: "setLikes", desc: "updates it and re-renders" }]} /></Frame> },
  { id: "takeaway_list", group: "Set 1 objects", title: "TakeawayList", note: "The fix_story recap: three rows reusing the title card's icons.",
    dur: 3, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><TakeawayList heading="Key takeaways" field={f} t={t}
      rows={[{ icon: "refresh", tone: "bad", line: "Re-renders reset", sub: "plain variables start over" },
             { icon: "memory", tone: "info", line: "useState remembers", sub: "kept between renders" },
             { icon: "bolt", tone: "warn", line: "Setters trigger", sub: "update, then re-render" }]} /></Frame> },
  { id: "end_card", group: "Set 1 objects", title: "EndCard", note: "Up next (from the document, never the LLM), Follow, series chips.",
    dur: 1.6, field: "blue",
    render: (t) => <Frame field="blue"><EndCard upNext="useEffect" t={t}
      chips={[{ label: "useState", done: true }, { label: "useEffect", done: false }, { label: "useRef", done: false }]} /></Frame> },

  // ---------------------------------------------------------- set 2 objects
  { id: "kinetic_title", group: "Set 2 objects", title: "KineticTitle", note: "Display caps, word by word, 0.12 s apart.",
    dur: 1.6, field: "navy", both: true,
    render: (t, f) => <Frame field={f}><KineticTitle field={f} t={t} x={54} y={600} size={190}
      lines={[[{ text: "How" }, { text: "does" }], [{ text: "AI", accent: true }, { text: "read" }], [{ text: "your" }, { text: "text?" }]]} /></Frame> },
  { id: "token_row", group: "Set 2 objects", title: "TokenRow, Chip, ChipTag", note: "Chips in every tone: plain, key, special (lavender), ok (mint), bad (coral border), ghost. YES/NO tags.",
    dur: 1, field: "paper", both: true,
    render: (_t, f) => {
      const xs = rowLayout(SENTENCE.map((s) => s.text), 140, 40);
      return <Frame field={f}>
        <TokenRow items={WITH_SPECIAL} x={W / 2} y={560} field={f} center />
        <TokenRow items={[{ text: "To", tone: "ok" }, { text: "##ken", tone: "ok" }, { text: "Token", tone: "bad" }, { text: "pad", tone: "ghost" }]} x={W / 2} y={740} field={f} center />
        <TokenRow items={SENTENCE} x={140} y={940} field={f} size={40} />
        <ChipTag kind="yes" x={xs[1] + 60} y={930} />
        <ChipTag kind="no" x={xs[0] + 300} y={930} />
      </Frame>;
    } },
  { id: "stamp_object", group: "Set 2 objects", title: "Stamp", note: "One strong verdict per reel, at most.",
    dur: 1, field: "navy", both: true,
    render: (_t, f) => <Frame field={f}><LookupGrid {...SHELF} field={f} state={{ dimRest: 0.5 }} /><Stamp text="Not on the shelf" x={W / 2} y={820} p={1} /></Frame> },
  { id: "lookup_grid", group: "Set 2 objects", title: "LookupGrid + SearchBar", note: "At most 12 readable cells; the rest fade to texture (addendum 5).",
    dur: 1, field: "navy", both: true,
    render: (_t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} /><LookupGrid {...SHELF} field={f} state={{ tone: (i) => (i === MATTERS ? "ok" : null) }} /></Frame> },
  { id: "lookup_table", group: "Set 2 objects", title: "LookupTable", note: "Any key → value mapping, with a highlighted row.",
    dur: 1, field: "yellow", both: true,
    render: (_t, f) => <Frame field={f}><StepChip n={4} of={4} field={f} /><LookupTable header={["ID", "TOKEN"]} rows={ID_TABLE} offset={19} x={70} y={300} w={940} field={f} />
      <TokenRow items={WITH_SPECIAL} x={W / 2} y={860} field={f} size={28} center /></Frame> },
  { id: "matrix_grid", group: "Set 2 objects", title: "MatrixGrid", note: "Batches, matrices, memory frames, bitmaps — with row labels, a bracket and a label.",
    dur: 1, field: "paper", both: true, render: (_t, f) => <Frame field={f}><BatchScene field={f} /></Frame> },
  { id: "big_counter", group: "Set 2 objects", title: "BigCounter", note: "The result of a step. Framed for count_up.",
    dur: 1, field: "blue", both: true,
    render: (_t, f) => <Frame field={f}><BigCounter value="5" label="TOKENS" x={W / 2} y={500} size={320} field={f} />
      <BigCounter value="1,20,000" label="about 1.2 lakh word pieces" x={W / 2} y={980} size={140} field={f} framed /></Frame> },
  { id: "bracket_callout", group: "Set 2 objects", title: "Bracket, Callout", note: "Labelling part of a row; a bubble pointing at one item.",
    dur: 1, field: "blue", both: true,
    render: (_t, f) => {
      const xs = rowLayout(WITH_SPECIAL.map((s) => s.text), 60, 30);
      return <Frame field={f}><TokenRow items={WITH_SPECIAL} x={60} y={900} field={f} size={30} />
        <Bracket x={xs[0]} y={990} w={130} label="SUMMARY SEAT" field={f} />
        <Callout x={60} y={560} w={560} label="REVIEW" text="“Clear, simple and fun.”" px={xs[0] + 50} py={890} field={f} tag={{ text: "GOOD", tone: "ok" }} /></Frame>;
    } },
  { id: "recap_grid", group: "Set 2 objects", title: "RecapGrid", note: "The walkthrough recap: concept, 'in N steps', numbered steps, final state.",
    dur: 1.6, field: "navy", both: true,
    render: (t, f) => <Frame field={f}><RecapGrid concept="Tokenization" steps={["Cut", "Check the shelf", "Add [CLS] + [SEP]", "Swap for IDs"]} final={IDS} field={f} t={t} /></Frame> },
  { id: "texture_background", group: "Set 2 objects", title: "TextureBackground", note: "Falling digits behind the hook only — decorative, low contrast.",
    dur: 3, field: "navy", both: true, render: (t, f) => <Frame field={f}><TextureBackground t={t} field={f} /></Frame> },

  // ----------------------------------------------------- chrome and captions
  { id: "chrome", group: "Chrome and captions", title: "StepChip, ProgressSegments, SectionLabel", note: "Step chip for walkthroughs; segments for fix_story; tracked-caps labels.",
    dur: 2, field: "paper", both: true,
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} />
      <div style={{ position: "absolute", left: 0, right: 0, top: 220 }}><ProgressSegments count={11} index={4} progress={seg(t, 0, 2)} field={f} /></div>
      <SectionLabel text="THE SHELF" x={60} y={420} field={f} /><SectionLabel text="FOLLOW ONE SENTENCE" x={W / 2} y={520} field={f} align="center" accent />
      <CornerMark text="@learnthesimpleway" field={f} /></Frame> },
  { id: "karaoke_caption", group: "Chrome and captions", title: "KaraokeCaption", note: "One sentence at a time: spoken words full ink, the rest 35 %; highlights in the field's accent.",
    dur: 2.8, field: "navy", both: true,
    render: (t, f) => <Frame field={f}>{cap(f, "Every model has a fixed list of word pieces it knows, called its <b>vocabulary</b>.", t)}</Frame> },

  // ------------------------------------------------------------ transitions
  { id: "type_scatter", group: "Transitions", title: "type_scatter (hook only)", note: "The question's words rotate and scatter with a one-frame flash; the answer punches in, coral (a failure moment).",
    dur: SCATTER.dur + 0.3, field: "navy", ref: "type_scatter",
    render: (t) => <Frame field="navy"><TypeScatter t={t} field="navy" answer="It can't."
      question={[[{ text: "How" }, { text: "does" }], [{ text: "AI", accent: true }, { text: "read" }], [{ text: "your" }, { text: "text?" }]]} />
      {cap("navy", "It can't.", t, 0.1, 0.6)}</Frame> },
  transitionEntry("iris", "navy", "blue", HookAnswer, FollowOne, "iris", "A ring grows out of the key word; the new field opens in its centre, then fills the frame.", [W / 2, 600]),
  transitionEntry("bar_wipe", "blue", "paper", FollowOne, cardScene(1, "Cut the sentence"), "bar_wipe", "A vertical lead bar sweeps left to right; the new field is revealed behind it."),
  transitionEntry("double_bar_wipe", "navy", "paper", ShelfScene, cardScene(2, "Check the word shelf"), "double_bar_wipe", "Two bars sweep right to left; the old content squeezes into slivers and blurs."),
  transitionEntry("diagonal_stripes", "blue", "yellow", SevenTokens, cardScene(4, "Swap each token for a number"), "diagonal_stripes", "Two bands at 30° — the lead colour and the new field (no coral)."),
  transitionEntry("stack_rise", "paper", "navy", BatchScene, cardScene(3, "Add special tokens"), "stack_rise", "A lead band rises with the new field under it, thinning as it reaches the top."),

  // ------------------------------------------------------------ chapter card
  { id: "chapter_card", group: "Chapter card", title: "ChapterCard entrance", note: "Number 20→100 % and 0.92→1 over 0.5 s; title types in; then the 'STEP n OF m' label; hold.",
    dur: 2.4, field: "paper", ref: "chapter_card",
    render: (t, f) => <Frame field={f}><ChapterCard n={1} of={4} title="Cut the sentence" field={f} t={t} exitAt={99} />
      {cap(f, "Step <b>one</b>. Cut the sentence.", t, 0.3, 2.2)}</Frame> },
  { id: "chip_fly_in", group: "Chapter card", title: "Chip fly-in", note: "The card's number shrinks and flies to the top-left, where it becomes the step chip.",
    dur: 1.2, field: "navy", ref: "chip_fly_in",
    render: (t, f) => {
      const tt = CHAPTER_CARD.exitAt - 0.2 + t;
      const handed = tt >= CHAPTER_CARD.exitAt + CHAPTER_CARD.fly;
      return <Frame field={f}><ChapterCard n={2} of={4} title="Check the word shelf" field={f} t={tt} />
        <StepChip n={2} of={4} field={f} p={seg(tt, CHAPTER_CARD.exitAt + CHAPTER_CARD.fly * 0.6, 0.25)} hideNumber={!handed} /></Frame>;
    } },

  // ------------------------------------------------------------- animations
  { id: "text_scramble", group: "Animations", title: "text_scramble", note: "Random characters settle letter by letter into the real word.",
    dur: 1.1, field: "blue", ref: "text_scramble",
    render: (t, f) => <Frame field={f}><BigCounter value="WORDS" x={W / 2} y={360} size={150} field={f} accent={false} />
      <ArrowDraw points={[[W / 2, 470], [W / 2, 590]]} t={1} color={theme(f).accent} />
      <TextScramble text="NUMBERS" t={t} x={W / 2} y={690} size={150} field={f} center start={0.05} dur={0.75} /></Frame> },
  { id: "type_assemble", group: "Animations", title: "type_assemble", note: "Letters slide in one by one, then the underline draws.",
    dur: 1.6, field: "blue", ref: "type_assemble",
    render: (t, f) => <Frame field={f}><SectionLabel text="THIS IS CALLED" x={W / 2} y={260} field={f} align="center" accent />
      <TypeAssemble text="Tokenization" t={t} x={W / 2} y={380} size={130} field={f} /></Frame> },
  { id: "arrow_draw", group: "Animations", title: "arrow_draw", note: "The stroke draws from start to end; the head arrives with it.",
    dur: 0.9, field: "blue", ref: "arrow_draw",
    render: (t, f) => <Frame field={f}><BigCounter value="WORDS" x={W / 2} y={360} size={150} field={f} accent={false} />
      <ArrowDraw points={[[W / 2, 470], [W / 2, 600]]} t={t} start={0.1} dur={0.45} color={theme(f).accent} /></Frame> },
  { id: "typewriter_cursor", group: "Animations", title: "typewriter_cursor", note: "A cursor types the running example; it blinks once typing stops.",
    dur: 2.4, field: "blue", ref: "typewriter_cursor",
    render: (t, f) => <Frame field={f}><SectionLabel text="FOLLOW ONE SENTENCE" x={W / 2} y={420} field={f} align="center" accent />
      <TypewriterCursor text="Tokenization matters." t={t} x={70} y={520} size={64} field={f} cps={13} mono={false} />
      {cap(f, "Let's follow <b>one</b> sentence: “Tokenization matters.”", t, 0, 2.2)}</Frame> },
  { id: "grid_cascade", group: "Animations", title: "grid_cascade", note: "Tiles flow in column by column with a slight zoom-out.",
    dur: 1.4, field: "navy", ref: "grid_cascade",
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} /><GridCascade grid={SHELF} t={t} field={f} />
      {cap(f, "Every model has a fixed list of word pieces it knows, called its <b>vocabulary</b>.", t, 0, 3)}</Frame> },
  { id: "count_up", group: "Animations", title: "count_up (14th)", note: "A framed counter rolls 0 → value, easing out, grouped as the source writes it. Its number must pass check_motion_numbers_sourced.",
    dur: 2.9, field: "navy", ref: "count_up",
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} />
      <div style={{ opacity: 0.35 }}><LookupGrid {...SHELF} field={f} /></div>
      <CountUp to={120000} t={t} y={700} field={f} label="about 1.2 lakh word pieces" />
      {cap(f, "Our model knows about <b>1.2 lakh</b> pieces.", t, 0, 2.6)}</Frame> },
  { id: "category_highlight", group: "Animations", title: "category highlight", note: "Cells light up by group while legend chips appear above the grid.",
    dur: 2.4, field: "navy", ref: "category_highlight",
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} />
      <CategoryHighlight grid={SHELF} t={t} field={f} legendY={190}
        groups={[{ name: "WHOLE WORDS", tone: "ok", cells: [39, 40, 46, 51, 58, 64, 70], at: 0.3 },
                 { name: "## PIECES", tone: "key", cells: [45, 52, 57, 63, 69], at: 1.3 }]} />
      {cap(f, "Common words are kept <b>whole</b>. Rare words are built from smaller pieces.", t, 0, 2.4)}</Frame> },
  { id: "zoom_cell", group: "Animations", title: "zoom into a cell", note: "The camera pushes into one cell; it becomes a readable chip with a state tag; the rest blurs.",
    dur: 1.4, field: "navy", ref: "zoom_cell",
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} />
      <ZoomCell grid={SHELF} index={MATTERS} tag="ON THE SHELF" t={t} field={f} />
      {cap(f, "“<b>Matters</b>” is on the shelf.", t, 0.2, 1.4)}</Frame> },
  { id: "search_type", group: "Animations", title: "search_type + scan line", note: "The bar types a query while a scan line sweeps the grid; no match turns the bar coral.",
    dur: 1.6, field: "navy", ref: "search_type",
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} /><SearchType grid={SHELF} query="Tokenization" match={null} t={t} field={f} barY={150} /></Frame> },
  { id: "stamp", group: "Animations", title: "stamp", note: "Slams in with overshoot and a tiny shake. One per reel.",
    dur: 0.9, field: "navy", ref: "stamp",
    render: (t, f) => <Frame field={f}><StepChip n={2} of={4} field={f} /><LookupGrid {...SHELF} field={f} state={{ dimRest: 0.5 }} />
      <StampSlam text="Not on the shelf" t={t - 0.1} x={W / 2} y={820} />
      {cap(f, "“Matters” is on the shelf. “<b>Tokenization</b>” is not.", t, 0, 0.9)}</Frame> },
  { id: "scan_window", group: "Animations", title: "scan_window", note: "A box with a NO tag shrinks from the right until it matches; the tag flips to YES, a connector draws, the piece drops.",
    dur: 0, field: "paper", ref: "scan_window",
    render: (t, f) => {
      const shelfItems: RowItem[] = [{ text: "To" }, { text: "##ken" }, { text: "##ization" }, { text: "matters" }, { text: "." }, { text: "##ing" }];
      const sx = rowLayout(shelfItems.map((s) => s.text), 40, 28);
      const pieces: ScanPiece[] = [
        { len: 2, label: "To", target: [sx[0] + 40, 300] }, { len: 3, label: "ken", target: [sx[1] + 60, 300] },
        { len: 7, label: "ization", target: [sx[2] + 80, 300] },
      ];
      const lit = scanSchedule("Tokenization", pieces).map((q) => t >= q.flipAt);
      return <Frame field={f}><StepChip n={2} of={4} field={f} /><SectionLabel text="THE SHELF" x={40} y={200} field={f} />
        <TokenRow items={shelfItems.map((s, i) => ({ ...s, tone: i < 3 && lit[i] ? "ok" as const : "plain" as const }))} x={40} y={240} field={f} size={28} />
        <ScanWindow word="Tokenization" pieces={pieces} t={t} x={150} y={560} size={84} field={f} resultY={820} />
        {cap(f, "It starts at the <b>front</b>, and takes the <b>longest</b> piece that fits.", t, 0, 3)}</Frame>;
    } },
  { id: "chip_insert", group: "Animations", title: "chip_insert", note: "New chips slide into the ends of a row and push the others apart.",
    dur: 1.9, field: "blue", ref: "chip_insert",
    render: (t, f) => <Frame field={f}><StepChip n={3} of={4} field={f} /><ChipInsert items={WITH_SPECIAL} inserts={[0, 6]} t={t - 0.1} x={W / 2} y={700} field={f} size={30} />
      {cap(f, "<b>[CLS]</b> goes at the front. <b>[SEP]</b> goes at the end.", t, 0, 1.9)}</Frame> },
  { id: "ghost_word", group: "Animations", title: "ghost_word", note: "A huge outlined word fades in behind the content, then out as the explanation starts.",
    dur: 2.2, field: "blue", ref: "ghost_word",
    render: (t, f) => <Frame field={f}><StepChip n={3} of={4} field={f} /><GhostWord text="Why?" t={t} y={520} field={f} />
      <TokenRow items={WITH_SPECIAL} x={W / 2} y={700} field={f} size={30} center />
      {cap(f, "Why? The model learns to gather a <b>summary</b> of the whole sentence into [CLS].", t, 0, 3)}</Frame> },
  { id: "slot_scroll", group: "Animations", title: "slot_scroll", note: "Rows scroll like a slot machine and stop on the matching row, which highlights.",
    dur: 1.5, field: "yellow", ref: "slot_scroll",
    render: (t, f) => <Frame field={f}><StepChip n={4} of={4} field={f} /><SlotScroll header={["ID", "TOKEN"]} rows={ID_TABLE} target={2} from={19} t={t} x={70} y={300} w={940} field={f} />
      <TokenRow items={WITH_SPECIAL} x={W / 2} y={860} field={f} size={28} center />
      {cap(f, "For example, <b>[CLS]</b> is 101.", t, 0, 1.4)}</Frame> },
  { id: "counter_morph", group: "Animations", title: "counter_morph", note: "A number, an arrow drawing, and the new number popping in the accent colour.",
    dur: 1.5, field: "blue", ref: "counter_morph",
    render: (t, f) => <Frame field={f}><CounterMorph from="2" to="7" fromLabel="WORDS" toLabel="TOKENS" t={t} y={420} field={f} />
      {cap(f, "So, two words became <b>seven</b> tokens.", t, 0, 1.5)}</Frame> },
  { id: "stagger_rows", group: "Animations", title: "stagger_rows", note: "Comparison rows appear one by one, 120 ms apart.",
    dur: 1.2, field: "blue", ref: "stagger_rows",
    render: (t, f) => {
      const row = (label: string, items: string[], n: string) => (
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <span style={{ width: 200, fontFamily: "'JetBrains Mono'", fontSize: 22, letterSpacing: 3, color: "rgba(255,255,255,0.8)" }}>{label}</span>
          {items.map((x) => <Chip key={x} text={x} field={f} size={30} />)}
          <span style={{ fontFamily: "var(--motion-display, 'Anton')", fontSize: 54, color: C.yellow, marginLeft: 20 }}>{n}</span>
        </div>);
      return <Frame field={f}><SectionLabel text="SAME WORD, DIFFERENT CUTS" x={W / 2} y={420} field={f} align="center" accent />
        <StaggerRows t={t - 0.1} x={70} y={520} rowH={120} rows={[row("TOKENIZER A", ["To", "##ken", "##ization"], "3"),
          row("TOKENIZER B", ["Token", "##ization"], "2"), row("TOKENIZER C", ["Tok", "##en", "##ization"], "3")]} />
        {cap(f, "Different models cut the same text <b>differently</b>.", t, 0, 1.2)}</Frame>;
    } },
];

// scan_window's length comes from its own schedule.
{
  const e = ENTRIES.find((x) => x.id === "scan_window")!;
  const pieces: ScanPiece[] = [{ len: 2, label: "" }, { len: 3, label: "" }, { len: 7, label: "" }];
  e.dur = scanSchedule("Tokenization", pieces).slice(-1)[0].end + 0.4;
}

export const GROUPS: Group[] = ["Set 1 objects", "Set 2 objects", "Chrome and captions", "Transitions", "Chapter card", "Animations"];

/** The settled time objects are shown at in the overview. */
export const SETTLED = Settled;
export { FIELDS, H, Layer };
