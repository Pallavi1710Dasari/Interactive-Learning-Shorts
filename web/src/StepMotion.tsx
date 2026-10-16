import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Spinner } from "./Spinner";
import { Figure } from "./motion/cast/CharacterSheet";
import { defaultPreset } from "./motion/cast/presets";
import { buildPerformance } from "./motion/cast/performance";
import { VrmPortrait } from "./motion/vrm/VrmPortrait";

/**
 * Making a motion reel: ONE STEP AT A TIME, like the old app (2026-10-13).
 *
 *   Upload -> Topic -> Teaching approach -> Language -> Theme -> Script -> Your reel
 *
 * Each screen asks one thing, says in one line why, and has one big
 * Continue. Everything else is decided for you with the recommended choice:
 * the setup (section, characters), the template (the theme you pick decides
 * it), and the scenes, voice and timing, which run on the last screen with a
 * progress list. A paid step says what it costs on its button before it
 * spends; in stub mode everything is free.
 *
 * The server side is shorts/motion_jobs.py — its stages are still
 * options -> topic -> approach -> template -> theme -> script -> scenes ->
 * voice -> timing -> done; this screen shows them as the seven steps above.
 */

interface Job {
  job_id: string; doc_name: string; short_id: string | null; stage: string; status: string;
  activity: string | null; activity_info: { model: string; eta_seconds: number; since: number; local: boolean } | null;
  progress: { done: number; total: number; label: string } | null;
  review: any; preflight: { stage: string; total: number; spent: number; projected: number; cap: number; fits: boolean } | null;
  message: string; error: Problem | null; stub: boolean; options: Record<string, any>;
  cost: { reel: number; cap: number }; summary: Record<string, { value: string; detail: string }>;
}
interface Problem { title: string; what: string; lost: string; next: string; action: string; details?: string }
interface Opt { value: unknown; label: string; description?: string; tag?: string }
interface Rec { value: unknown; label: string; reason: string; description?: string }

export const MOTION_STEPS: [string, string][] = [
  ["upload", "Upload"], ["topic", "Topic"], ["approach", "Teaching approach"], ["language", "Language"],
  ["theme", "Theme"], ["cast", "Characters"], ["script", "Script"], ["reel", "Your reel"],
];
const STEP_OF: Record<string, number> = {
  options: 1, topic: 1, approach: 2, template: 3, theme: 4, script: 6, scenes: 7, voice: 7, timing: 7, done: 7,
};
/** The visible step a job is on: the Characters step is the script stage
 * before the speakers are confirmed. */
export const stepIndex = (stage: string, castConfirmed = true) =>
  stage === "script" && !castConfirmed ? 5 : STEP_OF[stage] ?? 1;

/** Each step's question and its one-line why. */
const ASK: Record<string, [string, string]> = {
  topic: ["Which question should the reel answer?", "One reel answers one question. The AI picked the one most worth learning first."],
  approach: ["How should it be explained?", "Pick the way a beginner will understand it fastest."],
  language: ["Which language is this about?", "It sets the reel's badge, tags and character."],
  theme: ["How should the reel tell it?", "One narrator, an interview, a mentor and a student… Pick the one that fits."],
  cast: ["Who is in the reel?", "One avatar and one voice for each speaker. Keep the recommendation or change it."],
  script: ["Read what the reel will say", "Read it like a beginner would. Every line was checked against your material."],
  reel: ["Making your reel", "Drawing the visuals, recording the voice and timing every word."],
};

const money = (n: number) => `$${n.toFixed(2)}`;

/** "reel" or "video" (shorts/schema.py MotionFormat): what the job makes. */
type Noun = "reel" | "video";
/** A line said about a reel, said about a video instead. */
const as = (text: string, noun: Noun) => noun === "reel" ? text : text.replace(/\breel\b/g, "video").replace(/\bReel\b/g, "Video");

async function api<T>(url: string, body?: unknown): Promise<T> {
  let r: Response;
  try {
    r = await fetch(url, body === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    throw new Error("The app's server can't be reached. Check that it is running, then try again.");
  }
  if (!r.ok) {
    const d = await r.json().catch(() => ({}));
    throw new Error(typeof d.detail === "string" ? d.detail : `The server answered ${r.status}.`);
  }
  return r.json();
}

/** `code` spans as code, not raw backticks. */
function Txt({ text }: { text: string }) {
  return <>{String(text).split(/(`[^`]+`)/).map((p, i) => p.length > 2 && p.startsWith("`") && p.endsWith("`")
    ? <code key={i}>{p.slice(1, -1)}</code> : <span key={i}>{p}</span>)}</>;
}

/** The AI's pick first ("recommended", with its reason), then the rest. */
function Choices({ rec, options, value, onChange, show = 3 }: {
  rec: Rec; options: Opt[]; value: unknown; onChange: (v: unknown) => void; show?: number;
}) {
  const [all, setAll] = useState(false);
  const first = options.find((o) => o.value === rec.value) ?? { value: rec.value, label: rec.label, description: rec.description };
  const rest = options.filter((o) => o.value !== rec.value);
  const one = (o: Opt, isRec: boolean) => (
    <button key={String(o.value)} type="button" className={`mchoice${value === o.value ? " on" : ""}`}
            data-choice={String(o.value)} onClick={() => onChange(o.value)} aria-pressed={value === o.value}>
      <div className="t"><Txt text={o.label} />{isRec && <span className="pilltag">recommended</span>}{o.tag && <span className="chip dim">{o.tag}</span>}</div>
      {o.description && <div className="d"><Txt text={o.description} /></div>}
      {isRec && rec.reason && <div className="r"><b>Why: </b><Txt text={rec.reason} /></div>}
    </button>
  );
  return (
    <div className="mchoices">
      {one(first, true)}
      {(all ? rest : rest.slice(0, show)).map((o) => one(o, false))}
      {!all && rest.length > show && <button className="ghost" onClick={() => setAll(true)}>Show {rest.length - show} more</button>}
    </div>
  );
}

function ProblemBox({ p }: { p: Problem }) {
  return (
    <div className="mproblem" role="alert" data-testid="problem">
      <h3>{p.title}</h3>
      <dl><dt>What happened</dt><dd>{p.what}</dd><dt>Lost or charged?</dt><dd>{p.lost}</dd><dt>What to do</dt><dd>{p.next}</dd></dl>
      {p.details && <details style={{ marginTop: 10 }}><summary className="hintline" style={{ cursor: "pointer" }}>Show details</summary>
        <pre style={{ whiteSpace: "pre-wrap", fontSize: 11, color: "var(--muted)", maxHeight: 260, overflow: "auto" }}>{p.details}</pre></details>}
    </div>
  );
}

function Working({ job, label }: { job: Job; label?: string }) {
  const a = job.activity_info;
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const t = setInterval(() => setNow(Date.now() / 1000), 500); return () => clearInterval(t); }, []);
  const secs = a?.since ? Math.max(0, Math.round(now - a.since)) : 0;
  const p = job.progress;
  return (
    <div data-testid="working">
      <div className="drafting" style={{ fontSize: 15 }}><Spinner label={`${label ?? job.activity ?? "Working"}…`} /></div>
      <div className="hintline" style={{ fontSize: 13, marginTop: 6 }}>
        {secs > 0 && `${secs}s so far.`}{p && ` ${p.label} ${p.done} of ${p.total}.`}
      </div>
      <div className={`mbar${p ? "" : " moving"}`}><i style={p ? { width: `${(100 * p.done) / Math.max(1, p.total)}%` } : undefined} /></div>
    </div>
  );
}

/** "Try again", with a box for what should change when the step needs one. */
function Redo({ busy, act, label, reason: needs }: { busy: boolean; act: Act; label: string; reason?: boolean }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  if (!needs) return <button className="ghost" disabled={busy} onClick={() => act("regenerate")}>↻ {label}</button>;
  if (!open) return <button className="ghost" disabled={busy} onClick={() => setOpen(true)}>↻ {label}</button>;
  return (
    <div className="redo" style={{ width: "100%" }}>
      <input className="note" autoFocus value={text} data-testid="reason" placeholder="What should be different? e.g. “ask it the way a beginner would”"
             onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) act("regenerate", { reason: text }); }} />
      <button className="ghost" disabled={busy || !text.trim()} onClick={() => act("regenerate", { reason: text })}>↻ Try again</button>
      <button className="ghost" onClick={() => setOpen(false)}>Cancel</button>
    </div>
  );
}

/** The last step's checklist: what is being made, in order. */
function Building({ job }: { job: Job }) {
  const order = ["scenes", "voice", "timing", "done"];
  const at = order.indexOf(job.stage);
  const rows: [string, string][] = [
    ["scenes", "Drawing the visuals for every line"],
    ["voice", "Recording the voice (free, on this computer)"],
    ["timing", "Timing every word to the voice"],
  ];
  return (
    <ul className="mbuild">
      {rows.map(([k, label], i) => {
        const state = job.stage === "done" || i < at ? "done" : i === at ? "now" : "next";
        return (
          <li key={k} className={state}>
            <span className="dot">{state === "done" ? "✓" : state === "now" ? "●" : "○"}</span>
            <span>{label}</span>
            {state === "now" && job.progress && <span className="hintline"> {job.progress.label} {job.progress.done} of {job.progress.total}</span>}
          </li>
        );
      })}
    </ul>
  );
}

interface CastPick { characters: boolean; avatars: Record<string, string>; voices: Record<string, string>;
                    /** the 3D avatar each speaker wears (assets/avatars/<name>.vrm) */
                    vrm: Record<string, string> }
interface CastInfo {
  speakers: { role: string; label: string; does: string; avatar: string; voice: string | null; vrm?: string }[];
  /** the reel draws 3D avatars (MOTION_AVATARS=vrm, and every video): pick one of vrm_avatars */
  three_d?: boolean; vrm_avatars?: { value: string; label: string; description?: string }[];
  avatars: { value: string; label: string; gender?: string | null }[];
  voices: { value: string; label: string; stamp?: number }[]; characters: boolean; reason: string;
  avatars_recommended: boolean; avatars_reason: string;
}

const IDLE = buildPerformance({ role: "preview", seed: 7, cues: [{ t: 0.1, kind: "expression", name: "happy", cue: "" }] }, []);

/** One voice sample player for the whole page: ▶ plays, ❚❚ pauses, and
 * starting another voice stops the one playing. */
function useSample() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  useEffect(() => () => { audio.current?.pause(); }, []);
  const toggle = (id: string, url: string) => {
    if (playing === id) { audio.current?.pause(); setPlaying(null); return; }
    audio.current?.pause();
    const a = new Audio(url);
    a.onended = () => setPlaying(null);
    a.onpause = () => setPlaying((p) => (p === id ? null : p));
    audio.current = a;
    a.play().then(() => setPlaying(id)).catch(() => setPlaying(null));
  };
  return { playing, toggle };
}

/** The Characters step: whether to show avatars (the AI's advice, with its
 * reason), then per speaker an avatar (faces) and a voice (hear it, or open
 * the voice studio to record or change one). Two speakers, two voices. */
function Cast({ jobId, pick, setPick, onOpenVoice, version }: {
  jobId: string; pick: CastPick | null; setPick: (p: CastPick) => void; onOpenVoice?: () => void; version: number;
}) {
  const [info, setInfo] = useState<CastInfo | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [more, setMore] = useState<Record<string, boolean>>({});
  const sample = useSample();
  useEffect(() => {
    if (version < 0) return;                       // the voice studio is open
    api<CastInfo>(`/api/motion-jobs/${jobId}/cast`).then((i) => {
      setInfo(i);
      // keep the reviewer's picks when the voices are listed again
      setPick(pick ?? { characters: i.characters, avatars: Object.fromEntries(i.speakers.map((s) => [s.role, s.avatar])),
                        voices: Object.fromEntries(i.speakers.map((s) => [s.role, s.voice ?? ""])),
                        vrm: Object.fromEntries(i.speakers.map((s) => [s.role, s.vrm ?? "mentor"])) });
    }).catch((e) => setErr((e as Error).message));
  }, [jobId, version]); // eslint-disable-line react-hooks/exhaustive-deps
  if (err) return <div className="error">{err}</div>;
  if (!info || !pick) return <div className="drafting"><Spinner label="Finding the speakers…" /></div>;
  const clash = info.speakers.length > 1 && new Set(Object.values(pick.voices)).size < info.speakers.length;
  const two = info.speakers.length > 1;
  return (
    <div>
      <div className="outcome" style={{ marginBottom: 14 }}>{info.reason}</div>

      <div className="qlabel">Avatars on screen</div>
      <div className="mchoices two">
        {[true, false].map((on) => (
          <button key={String(on)} type="button" className={`mchoice${pick.characters === on ? " on" : ""}`}
                  onClick={() => setPick({ ...pick, characters: on })}>
            <div className="t">{on ? (two ? "Show two avatars" : "Show an avatar") : "No avatars"}
              {on === info.avatars_recommended && <span className="pilltag">recommended</span>}</div>
            <div className="d">{on ? "A character for each speaker, talking with the voice." : "Only the visuals and the captions."}</div>
            {on === info.avatars_recommended && info.avatars_reason && <div className="r"><b>Why: </b>{info.avatars_reason}</div>}
          </button>))}
      </div>

      {info.speakers.map((sp) => {
        const recA = sp.avatar, recV = sp.voice;
        const shown = more[sp.role] ? info.avatars : info.avatars.filter((a) => a.value === recA || a.value === pick.avatars[sp.role]
          || ["host", "arjun", "riya"].includes(a.value)).slice(0, 4);
        return (
          <div key={sp.role} className="mspeaker">
            <div className="mspeakerhead"><b>{sp.label}</b><span className="hintline">{sp.does}</span></div>
            {pick.characters && info.three_d && <div className="mavatars m3d">
              {(info.vrm_avatars ?? []).map((a) => (
                <button key={a.value} type="button" className={`mavatar${(pick.vrm ?? {})[sp.role] === a.value ? " on" : ""}`}
                        data-vrm={a.value} title={a.description}
                        onClick={() => setPick({ ...pick, vrm: { ...(pick.vrm ?? {}), [sp.role]: a.value } })}>
                  <VrmPortrait name={a.value} />
                  <span>{a.label}{a.value === sp.vrm && <em className="pilltag">recommended</em>}</span>
                </button>))}
              <div className="hintline m3dhint">3D presenters from <code>assets/avatars/</code>. Add your own <code>.vrm</code> file there and it shows up here.</div>
            </div>}
            {pick.characters && !info.three_d && <div className="mavatars">
              {shown.map((a) => (
                <button key={a.value} type="button" className={`mavatar${pick.avatars[sp.role] === a.value ? " on" : ""}`}
                        onClick={() => setPick({ ...pick, avatars: { ...pick.avatars, [sp.role]: a.value } })}>
                  <Figure config={defaultPreset(a.value)} perf={IDLE} t={1} width={130} face />
                  <span>{a.label}</span>
                  {a.value === recA && <em className="pilltag">recommended</em>}
                </button>))}
              {!more[sp.role] && <button type="button" className="ghost sm" onClick={() => setMore({ ...more, [sp.role]: true })}>More avatars</button>}
            </div>}
            <div className="mvoices">
              <span className="hintline">Voice</span>
              {info.voices.map((v) => {
                const id = `${sp.role}:${v.value}`;
                return (
                  <span key={v.value} className={`mvoice${pick.voices[sp.role] === v.value ? " on" : ""}`}>
                    <button type="button" onClick={() => setPick({ ...pick, voices: { ...pick.voices, [sp.role]: v.value } })}>
                      {v.label}{v.value === recV && <em className="pilltag">recommended</em>}
                    </button>
                    <button type="button" className="play" title={sample.playing === id ? "pause" : "hear this voice"}
                            onClick={() => sample.toggle(id, `/api/voices/${encodeURIComponent(v.value)}?v=${v.stamp ?? 0}`)}>
                      {sample.playing === id ? "❚❚" : "▶"}
                    </button>
                  </span>);
              })}
            </div>
          </div>
        );
      })}
      {clash && <div className="error sm">Two speakers need two different voices.</div>}
      {onOpenVoice && (
        <div className="mvoicehelp">
          <span>Want a different voice? Record your own or change one in the voice studio — it shows up here, and in the reel.</span>
          <button type="button" className="ghost sm" onClick={onOpenVoice}>Record or change a voice…</button>
        </div>
      )}
    </div>
  );
}

/** "Your reel so far": every step with what was decided, the step you are on
 * highlighted, and Change on the finished ones while the reel is not being
 * made yet (it reopens that step as it was — no new call). */
function Choices2({ job, step, busy, onBack }: { job: Job; step: number; busy: boolean; onBack: (target: string) => void }) {
  const sum = job.summary ?? {};
  const o = job.options ?? {};
  const noun: Noun = o.format === "video" ? "video" : "reel";
  const making = ["scenes", "voice", "timing", "done"].includes(job.stage);
  const rows: [string, number, string, string | undefined][] = [
    ["topic", 1, "Topic", sum.topic?.value],
    ["approach", 2, "Teaching approach", sum.approach?.value],
    ["template", 3, "Language", step > 3 ? String(o.language ?? "") : undefined],
    ["theme", 4, "Theme", sum.theme?.value],
    ["cast", 5, "Characters", o.cast_confirmed ? sum.cast?.value : undefined],
    ["script", 6, "Script", sum.script?.value],
  ];
  return (
    <aside className="mside">
      <div className="mside-title">Your {noun} so far</div>
      <ol className="mside-list">
        {rows.map(([k, idx, name, value]) => {
          const state = idx < step || job.status === "done" ? "done" : idx === step ? "now" : "next";
          return (
            <li key={k} className={`mside-row ${state}`}>
              <span className="mside-dot">{state === "done" ? "✓" : idx + 1}</span>
              <div className="mside-text">
                <div className="mside-name">{name}</div>
                <div className="mside-value">
                  {value ? <Txt text={value} /> : state === "now" ? "deciding now…" : "—"}
                </div>
              </div>
              {state === "done" && value && !making &&
                <button className="mside-change" disabled={busy} onClick={() => onBack(k)} title={`go back and change the ${name.toLowerCase()}`}>Change</button>}
            </li>
          );
        })}
      </ol>
      <div className="mside-foot">{making ? `🔒 The ${noun} is being made — choices are locked.` : "Change any step until you approve the script."}</div>
    </aside>
  );
}

type Act = (action: string, o?: { reason?: string; choice?: unknown }) => void;

/** A video's script to read: its opening, each chapter under its own
 * heading, then the closing — every line, numbered through. */
function VideoScript({ script }: { script: any }) {
  const titles: Record<number, string> = Object.fromEntries((script.chapters ?? []).map((c: any) => [c.n, c.title]));
  const groups: { key: string; title: string; shots: any[] }[] = [];
  for (const sh of script.shots) {
    const key = sh.chapter != null ? `c${sh.chapter}` : groups.length && groups[groups.length - 1].key !== "open" ? "close" : "open";
    if (!groups.length || groups[groups.length - 1].key !== key)
      groups.push({ key, title: sh.chapter != null ? `Chapter ${sh.chapter} · ${titles[sh.chapter] ?? ""}` : key === "open" ? "Opening" : "Closing", shots: [] });
    groups[groups.length - 1].shots.push(sh);
  }
  let n = 0;
  return <div className="mvscript">
    {groups.map((g) => (
      <section key={g.key}>
        <h3>{g.title}</h3>
        <ol className="mlines" start={n + 1}>
          {g.shots.flatMap((sh: any) => sh.captions.map((c: any, i: number) => {
            n += 1;
            return <li key={`${sh.id}-${i}`}><Txt text={c.text.replace(/<\/?b>/g, "")} /></li>;
          }))}
        </ol>
      </section>
    ))}
  </div>;
}

export function StepMotion({ jobId, onFinished, onOpenVoice, voiceVersion = 0 }: {
  jobId: string; onFinished: () => void;
  /** open the "your voice" studio (top bar) — to record or change a voice */
  onOpenVoice?: () => void; voiceVersion?: number;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState<unknown>(undefined);      // the current step's choice
  const [setup, setSetup] = useState<any>(null);              // recommendations (language list)
  const [lang, setLang] = useState<string | null>(null);
  const [sectionOpen, setSectionOpen] = useState(false);
  const [section, setSection] = useState<string>("");
  const [castPick, setCastPick] = useState<CastPick | null>(null);
  const inFlight = useRef(false);
  const autoDone = useRef<string>("");

  const load = useCallback(() => api<Job>(`/api/motion-jobs/${jobId}`).then((j) => { setJob(j); setErr(null); })
    .catch((e) => setErr((e as Error).message)), [jobId]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (job?.status !== "running") return;
    const t = setInterval(load, 700);
    return () => clearInterval(t);
  }, [job?.status, load]);
  useEffect(() => { setPick(job?.review?.recommended?.value); setSectionOpen(false); }, [job?.stage, job?.status, job?.review?.recommended?.value]);
  useEffect(() => { if (job?.status === "done") onFinished(); }, [job?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (setup) return;
    api<any>(`/api/motion-jobs/${jobId}/options`).then((i) => { setSetup(i); setLang(i.language.recommended.value); })
      .catch((e) => setErr((e as Error).message));
  }, [jobId, setup]);

  const call = (p: () => Promise<Job>) => {
    if (inFlight.current) return;                  // a second click while one is in flight
    inFlight.current = true; setBusy(true); setErr(null);
    p().then(setJob).catch((e) => { setErr((e as Error).message); load(); })
      .finally(() => { inFlight.current = false; setBusy(false); });
  };
  const act: Act = (action, o = {}) => call(() => api(`/api/motion-jobs/${jobId}/decide`, {
    action, reason: o.reason ?? "", choice: o.choice ?? null, expect: job ? `${job.stage}/${job.status}` : null }));
  const resume = () => call(() => api(`/api/motion-jobs/${jobId}/resume`, {}));

  // THE STEPS YOU DON'T SEE: the setup starts with the recommended choices,
  // and the scenes are drawn and approved by themselves (they are checked;
  // a failure shows as a problem with a retry). Free steps that only ask
  // "spend nothing?" in stub mode go on by themselves too.
  useEffect(() => {
    if (!job || !setup || inFlight.current) return;
    const key = `${job.stage}/${job.status}/${job.review?.passed ?? ""}`;
    if (autoDone.current === key) return;
    const go = (f: () => void) => { autoDone.current = key; f(); };
    if (job.status === "options") {
      go(() => call(() => api(`/api/motion-jobs/${jobId}/start`, {
        section: null, language: setup.language.recommended.value, characters: true, character: null,
        format: job.options.format ?? "reel" })));
    } else if (job.stage === "scenes" && job.status === "preflight") {
      go(() => act("proceed"));
    } else if (job.stage === "scenes" && job.status === "review" && job.review?.passed) {
      go(() => act("approve"));
    } else if (job.stage === "script" && job.status === "review" && job.options.cast_confirmed
               && job.review && !job.review.passed && !job.review.rechecked) {
      // a failed script is checked again (free) once — the checks may have been fixed since
      go(() => act("recheck"));
    } else if (job.stub && job.status === "preflight" && (job.stage !== "script" || job.options.cast_confirmed)) {
      go(() => act("proceed"));
    }
  }, [job, setup, busy]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!job) return <div className="panel wide">{err ? <div className="error">{err}</div> : <div className="drafting"><Spinner label="Opening the reel…" /></div>}</div>;

  const step = stepIndex(job.stage, !!job.options.cast_confirmed);
  const noun: Noun = job.options.format === "video" ? "video" : "reel";
  const key = MOTION_STEPS[step][0];
  const r = job.review;
  const done = job.status === "done";
  const building = step === 7;

  // ------------------------------------------------ the current step's body
  let body: ReactNode = null;
  let main: { label: string; run: () => void; disabled?: boolean } | null = null;
  let extra: ReactNode = null;
  if (job.status === "error" && job.error) {
    body = <ProblemBox p={job.error} />;
    main = { label: job.error.action, run: resume };
  } else if (job.status === "cap") {
    body = <ProblemBox p={{ title: "This step would go over the cost limit", what: job.message,
      lost: "Nothing you approved was lost, and nothing was charged for this step.",
      next: `To continue, raise ${noun === "video" ? "MAX_VIDEO_USD" : "MAX_REEL_USD"} in the .env file and restart the server, then open this ${noun} again.`, action: "OK, stop here" }} />;
    main = { label: "OK, stop here", run: () => act("stop") };
  } else if (job.status === "stopped") {
    body = <div className="outcome" style={{ fontSize: 14 }}>{job.message || "Paused."} Everything you chose is kept.</div>;
    main = { label: "Continue", run: resume };
  } else if (building && !done) {
    body = <>
      <Building job={job} />
      {job.status === "running" ? <Working job={job} /> : <div className="drafting"><Spinner label="Starting…" /></div>}
      {job.stage === "scenes" && job.status === "review" && !job.review?.passed && (
        <ProblemBox p={{ title: "The visuals didn't pass their checks", what: job.review?.message ?? "",
          lost: "Nothing you chose was lost.", next: "Draw them again.", action: "Draw again" }} />)}
    </>;
    if (job.stage === "scenes" && job.status === "review" && !job.review?.passed) main = { label: "Draw the visuals again", run: () => act("regenerate") };
  } else if (key === "cast" && (job.status === "preflight" || job.status === "review")) {
    body = <Cast jobId={jobId} pick={castPick} setPick={setCastPick} onOpenVoice={onOpenVoice} version={voiceVersion} />;
    main = { label: "Continue →", disabled: !castPick,
             run: () => castPick && call(() => api(`/api/motion-jobs/${jobId}/decide`, {
               action: "cast", choice: castPick, expect: `${job.stage}/${job.status}` })) };
  } else if (job.status === "running" || job.status === "options") {
    body = <Working job={job} label={job.status === "options" ? "Reading your material" : undefined} />;
  } else if (job.status === "preflight") {
    // a paid step, shown on the step it belongs to, with its cost on the button
    const p = job.preflight!;
    const what: Record<string, [string, string]> = {
      theme: ["The AI looks at your topic and suggests the best way to tell it.", "Suggest a style"],
      script: ["The AI writes every line and checks it against your material.", "Write the script"],
    };
    const [say, btn] = what[p.stage] ?? ["", "Continue"];
    body = <div className="outcome" style={{ fontSize: 15 }}>{say}</div>;
    main = { label: `${btn} — ${job.stub ? "free" : `up to ${money(p.total)}`} →`, run: () => act("proceed") };
  } else if (job.status === "review") {
    if (job.stage === "topic") {
      body = <Choices rec={r.recommended} options={r.options} value={pick} onChange={setPick} />;
      extra = <>
        <Redo busy={busy} act={act} label="Ask it differently" reason />
        <button className="ghost" disabled={busy} onClick={() => setSectionOpen(!sectionOpen)}>Use another part of the material</button>
        {sectionOpen && (
          <div style={{ width: "100%", marginTop: 8 }}>
            <Choices rec={{ value: r.section_id, label: r.sections.find((s: Opt) => s.value === r.section_id)?.label ?? r.section_id, reason: "Where this topic comes from." }}
                     options={r.sections} value={section || r.section_id} onChange={(v) => setSection(v as string)} show={4} />
            <button className="primary" disabled={busy || !section || section === r.section_id}
                    onClick={() => act("section", { choice: section })}>Find a question here{job.stub ? "" : ` (about ${money(r.section_cost)})`}</button>
          </div>)}
      </>;
      main = { label: "Continue →", run: () => act("approve", { choice: pick }) };
    } else if (job.stage === "approach") {
      body = <>
        <div className="outcome" style={{ marginBottom: 10 }}>For: <b><Txt text={r.question} /></b></div>
        <Choices rec={r.recommended} options={r.options} value={pick} onChange={setPick} />
      </>;
      extra = <Redo busy={busy} act={act} label="Ask the AI to think again" reason />;
      main = { label: "Continue →", run: () => act("approve", { choice: pick }) };
    } else if (job.stage === "template") {
      // the Language step (the template is chosen for you: the theme decides it)
      body = setup ? <Choices rec={setup.language.recommended} options={setup.language.options} value={lang}
                              onChange={(v) => setLang(v as string)} show={4} />
                   : <div className="drafting"><Spinner label="Reading your material…" /></div>;
      main = { label: "Continue →", run: () => act("language", { choice: lang }), disabled: !lang };
    } else if (job.stage === "theme") {
      const failing = (r.tag_checks as { passed: boolean; reason: string }[]).filter((x) => !x.passed);
      body = <>
        <Choices rec={r.recommended} options={r.options.map((o: any) => ({ ...o, tag: o.speakers }))} value={pick} onChange={setPick} show={4} />
        {failing.length > 0 && <div className="error sm">{failing.map((f) => f.reason).join(" ")}</div>}
      </>;
      const label = r.options.find((o: Opt) => o.value === pick)?.label ?? String(pick);
      main = { label: `Continue with ${label} →`, run: () => act("approve", { choice: pick }), disabled: pick === r.choice.theme && failing.length > 0 };
    } else if (job.stage === "script") {
      const s = r.script;
      const failed = (r.results as { name: string; passed: boolean; reason: string }[]).filter((x) => !x.passed);
      body = <>
        {r.reused && <div className="outcome" style={{ color: "var(--teal-hi)", marginBottom: 8 }}>{r.reused}</div>}
        {!r.passed && <div className="error sm">{r.message}
          {failed.length > 0 && <ul className="mfails">{failed.map((x) => <li key={x.name}>{x.reason}</li>)}</ul>}</div>}
        {s && <>
          <div className="topic">{s.hook_question}</div>
          {noun === "video" && <div className="hintline" style={{ marginBottom: 8 }}>
            About {Math.round((s.estimated_seconds ?? 0) / 60)} minutes · {s.chapters?.length ?? 0} chapters · {s.shots.length} shots</div>}
          {noun === "video" ? <VideoScript script={s} /> : <ol className="mlines">
            {s.shots.flatMap((sh: any) => sh.captions.map((c: any, i: number) => (
              <li key={`${sh.id}-${i}`}>{c.speaker && <span className="who">{c.speaker.toLowerCase()}</span>}<Txt text={c.text.replace(/<\/?b>/g, "")} /></li>)))}
          </ol>}
        </>}
        <div className="graders">
          {r.passed ? <span className="chip ok">✓ easy to follow, true to your material</span>
            : <span className="chip" style={{ background: "rgba(255,90,90,.12)", color: "#ff8a8a" }}>✗ some checks failed</span>}
        </div>
      </>;
      extra = <>
        {!r.passed && <button className="ghost" disabled={busy} onClick={() => act("recheck")}>Check the saved attempts again (free)</button>}
        <Redo busy={busy} act={act} label={r.passed ? "Write it again" : "Write a new one"} />
      </>;
      // the visuals are drawn next without asking again: their cost is said here
      const visuals = (setup?.estimate?.rows ?? []).filter((x: any) => String(x.label).startsWith("motion_scenes"))
        .reduce((n: number, x: any) => n + x.worst, 0);
      main = { label: `Looks good — make the ${noun}${job.stub || !visuals ? "" : ` (visuals up to ${money(visuals)}, voice free)`} →`,
               run: () => act("approve"), disabled: !r.passed };
    }
  }

  return (
    <div className="panel wide mwizard" data-stage={job.stage} data-status={job.status}>
      <div className="mprogress" aria-label={`step ${step + 1} of ${MOTION_STEPS.length}`}>
        {MOTION_STEPS.map(([k, name], i) => (
          <div key={k} className={`mdot ${i < step || done ? "done" : i === step ? "now" : ""}`}>
            <span>{i < step || done ? "✓" : i + 1}</span><em>{as(name, noun)}</em>
          </div>
        ))}
      </div>

      <div className="mlayout">
      <div className="mmain">
      {done ? (
        <div className="card approved mstepcard">
          <h1>Your {noun} is ready 🎉</h1>
          <p className="lede">{job.summary.topic?.value ? <>It answers: <b><Txt text={job.summary.topic.value} /></b></> : null}</p>
          <div className="mrow">
            {noun === "video"
              ? <a className="primary big" href={`#motion-video/${job.short_id}`} data-testid="watch"
                   onClick={(e) => { e.preventDefault(); location.hash = `#motion-video/${job.short_id}`; location.reload(); }}>▶ Watch your video</a>
              : <a className="primary big" href={`#reels/${job.short_id}`} data-testid="watch"
                   onClick={(e) => { e.preventDefault(); location.hash = `#reels/${job.short_id}`; location.reload(); }}>▶ Watch your reel</a>}
          </div>
          {job.message && <div className="error sm">{job.message}</div>}
        </div>
      ) : (
        <div className="card mstepcard" data-step={key}>
          <div className="mstepno">Step {step + 1} of {MOTION_STEPS.length}</div>
          <h1>{as(ASK[key]?.[0] ?? "", noun)}</h1>
          <p className="lede">{as(ASK[key]?.[1] ?? "", noun)}</p>
          <div className="mbody">{body}</div>
          {err && <div className="error">{err}</div>}
          <div className="mactions">
            {extra}
            <span className="spacer" />
            {main && <button className="primary big" disabled={busy || main.disabled} onClick={main.run}>{main.label}</button>}
          </div>
        </div>
      )}

      </div>
      <Choices2 job={job} step={step} busy={busy} onBack={(target) => act("back", { choice: target })} />
      </div>

      <div className="mfoot">
        From <b>{job.doc_name}</b> · {noun === "video" ? "a video, 6–12 min, 16:9" : "a reel"} · so far: <b>{money(job.cost.reel)}</b> of {money(job.cost.cap)} limit
        {job.stub && " · test mode: AI steps are free"}
        {job.status === "review" && !done && <button className="linkbtn" disabled={busy} onClick={() => act("skip")}>Stop here for now</button>}
      </div>
    </div>
  );
}
