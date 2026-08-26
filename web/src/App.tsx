import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, getShorts, getUsage, type MaterialResult, type UsageTotals } from "./api";
import { CostPill } from "./CostPill";
import { Reel } from "./Reel";
import { StepMaterial } from "./StepMaterial";
import { StepReview } from "./StepReview";
import { pickVoices, useVoices } from "./useNarration";
import type { Feedback, Unit } from "./types";

type Step = "material" | "review" | "reels";

export default function App() {
  const [step, setStep] = useState<Step>("material");
  const [material, setMaterial] = useState<MaterialResult | null>(null);
  const [shorts, setShorts] = useState<Unit[]>([]);
  const [health, setHealth] = useState<Awaited<ReturnType<typeof getHealth>> | null>(null);
  const [total, setTotal] = useState<UsageTotals | null>(null);
  const [delta, setDelta] = useState<UsageTotals | undefined>();

  useEffect(() => {
    getHealth().then((h) => { setHealth(h); setTotal(h.total); }).catch(() => {});
  }, []);

  // #reels opens the feed straight away, on whatever is already in output/, and
  // #reels/<short_id> opens it scrolled to one particular short.
  //
  // Watching the reels is the part you come back to; making that a link means not
  // clicking through step 1 to reach it, it gives the player a URL that can be
  // opened on a phone, and it makes "look at this one" a thing you can send to
  // somebody rather than a scroll instruction.
  const [focus, setFocus] = useState<string | null>(null);
  useEffect(() => {
    const [route, id] = location.hash.replace(/^#/, "").split("/");
    const openingReels = route === "reels";
    if (openingReels) setFocus(id ? decodeURIComponent(id) : null);

    // THE FEED IS LOADED ON EVERY MOUNT, not only behind #reels. Before this, the
    // shorts already in output/ were fetched ONLY when the URL carried the hash —
    // so on a normal page load `shorts` stayed empty, which left the step-3 crumb
    // `disabled={!shorts.length}` and step 3 itself showing "No reels yet. Paste
    // material in step 1". Sixteen finished shorts were sitting on disk and the one
    // tab built to play them could not be opened. The only way in was to know to
    // type #reels, which is not a thing a user knows.
    //
    // It is one cheap GET on a local server, and it is the same call the hash path
    // already made, so nothing new can fail.
    getShorts()
      .then((s) => { setShorts(s); if (openingReels) setStep("reels"); })
      .catch(() => {});
    getUsage().then(setTotal).catch(() => {});
  }, []);

  // Anything that spends money hands back its own cost plus the new running total.
  const onSpend = (d: UsageTotals, t: UsageTotals) => { setDelta(d); setTotal(t); };

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><span className="spark">▶</span> Learning Shorts</div>
        <nav className="steps">
          <Crumb n={1} label="Material" on={step === "material"} done={!!material}
                 onClick={() => setStep("material")} />
          <Crumb n={2} label="Review Q&amp;A" on={step === "review"} done={shorts.length > 0}
                 disabled={!material} onClick={() => setStep("review")} />
          <Crumb n={3} label="Reels" on={step === "reels"} done={false}
                 disabled={!shorts.length} onClick={() => setStep("reels")} />
        </nav>
        <span className="spacer" />
        {total && <CostPill total={total} delta={delta} />}
        <span className="hintline">{health ? (health.stub ? "stub mode" : health.model) : "…"}</span>
        <button
          className="ghost sm"
          onClick={() => {
            getShorts().then((s) => { setShorts(s); setStep("reels"); });
            getUsage().then(setTotal).catch(() => {});
          }}
        >
          existing reels
        </button>
      </header>

      {step === "material" && (
        <StepMaterial
          onDone={(r) => { onSpend(r.usage, r.total); setMaterial(r); setStep("review"); }}
        />
      )}
      {step === "review" && material && (
        <StepReview
          material={material}
          onSpend={onSpend}
          onDone={(s) => { setShorts(s); setStep("reels"); }}
        />
      )}
      {step === "reels" && <Reels shorts={shorts} focus={focus} />}
    </div>
  );
}

function Crumb({ n, label, on, done, disabled, onClick }: {
  n: number; label: string; on: boolean; done: boolean;
  disabled?: boolean; onClick: () => void;
}) {
  return (
    <button
      className={`crumb${on ? " on" : ""}${done ? " done" : ""}`}
      disabled={disabled}
      onClick={onClick}
    >
      <span className="num">{done && !on ? "✓" : n}</span>
      <span dangerouslySetInnerHTML={{ __html: label }} />
    </button>
  );
}

/** Step 3 — reels only. No Q&A panel: reviewing was step 2's job. */
function Reels({ shorts, focus }: { shorts: Unit[]; focus?: string | null }) {
  const [active, setActive] = useState(0);
  const [voiceOn, setVoiceOn] = useState(true);
  const [rate, setRate] = useState(1);
  const [feedback, setFeedback] = useState<Feedback[]>([]);
  const slots = useRef<(HTMLDivElement | null)[]>([]);
  const voices = useVoices();

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => entries.forEach((en) => {
        if (en.isIntersecting) {
          const i = slots.current.indexOf(en.target as HTMLDivElement);
          if (i !== -1) setActive(i);
        }
      }),
      { threshold: 0.6 },
    );
    slots.current.forEach((el) => el && obs.observe(el));
    return () => obs.disconnect();
  }, [shorts]);

  // Jump to the short named in the URL. Done after the slots exist and without
  // smooth scrolling, so it lands as "this is where the page opened" rather than
  // as the feed visibly travelling past the shorts in between.
  useEffect(() => {
    if (!focus || !shorts.length) return;
    const i = shorts.findIndex((s) => s.short_id === focus);
    if (i < 0) return;
    setActive(i);
    requestAnimationFrame(() => slots.current[i]?.scrollIntoView({ block: "center" }));
  }, [focus, shorts]);

  const onFeedback = useCallback((f: Feedback) => {
    setFeedback((prev) => {
      const next = [...prev, f];
      localStorage.setItem("shorts_feedback", JSON.stringify(next));
      return next;
    });
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "j") slots.current[active + 1]?.scrollIntoView({ behavior: "smooth" });
      if (e.key === "k") slots.current[active - 1]?.scrollIntoView({ behavior: "smooth" });
      if (e.key === "m") setVoiceOn((v) => !v);
      if (e.key === "d") void download();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);

  if (!shorts.length) {
    return (
      <div className="center">
        <div>
          <b>No reels yet</b>
          <p className="lede">Paste material in step 1, approve some answers in step 2.</p>
          <code>python -m shorts.run content/session_18_paging.md --topics 5 --no-tts</code>
        </div>
      </div>
    );
  }

  const picked = pickVoices(voices);
  const recorded = shorts.filter((s) => s.audio_url).length;

  // DOWNLOAD THE SHORT ON SCREEN, as an MP4.
  //
  // The render is synchronous on the server and takes a few seconds the first time
  // (Chrome screenshots one frame per beat, ffmpeg muxes them with the recorded
  // audio), then it is cached. So the button has to show that it is working, or a
  // click looks like it did nothing and gets clicked again.
  //
  // A plain <a href download> cannot do that — it fires and forgets, with no hook
  // for "started" or "failed". Fetching the blob lets the button say "rendering…",
  // and lets a failure surface as a message instead of a silently broken save.
  const [saving, setSaving] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);
  const current = shorts[active];

  const download = async () => {
    if (!current || saving) return;
    setSaving(current.short_id);
    setSaveErr(null);
    try {
      const res = await fetch(`/api/video/${encodeURIComponent(current.short_id)}`);
      if (!res.ok) {
        let msg = `render failed (${res.status})`;
        try { msg = (await res.json()).detail ?? msg; } catch { /* keep the status */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${current.short_id}.mp4`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      // Revoked on a tick, not immediately: Safari cancels the save if the object
      // URL disappears in the same frame as the click.
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (e) {
      setSaveErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="reelswrap">
      <div className="reeltop">
        <button className={voiceOn ? "primary sm" : "ghost sm"} onClick={() => setVoiceOn((v) => !v)}>
          {voiceOn ? "🔊 voice on" : "🔇 muted"}
        </button>
        <label className="inline">
          speed
          <input type="range" min={0.7} max={1.6} step={0.1} value={rate}
                 onChange={(e) => setRate(+e.target.value)} />
          <span className="hintline">{rate.toFixed(1)}×</span>
        </label>
        <button className="primary sm" onClick={download}
                disabled={!current || !!saving}
                title="download this reel as an MP4 (d)">
          {saving ? "⏳ rendering…" : "⬇ download reel"}
        </button>
        <span className="spacer" />
        {saveErr && <span className="error sm">{saveErr}</span>}
        {/* Name the narrator that is actually going to speak. Advertising the
            browser's voices while a recorded track plays was simply wrong, and it
            hid the thing worth knowing: which shorts still lack a recording. */}
        <span className="hintline">
          {recorded === shorts.length
            ? "recorded narration"
            : recorded > 0
              ? `recorded narration · ${shorts.length - recorded} still on browser voice`
              : voices.length === 0
                ? "no system voices — playing silently"
                : `browser voice: ${picked.interviewer?.name ?? "?"} / ${picked.student?.name ?? "?"}`}
        </span>
        <span className="hintline">{active + 1}/{shorts.length} · {feedback.length} signals</span>
      </div>

      <div className="feed">
        {shorts.map((unit, i) => (
          <div className="slot" key={unit.short_id} ref={(el) => { slots.current[i] = el; }}>
            <Reel unit={unit} active={i === active} voiceOn={voiceOn} rate={rate}
                  onFeedback={onFeedback} />
          </div>
        ))}
      </div>

      <div className="hint">
        scroll for the next short · <kbd>space</kbd> pause (stops the voice) ·{" "}
        <kbd>←</kbd>/<kbd>→</kbd> beat · <kbd>j</kbd>/<kbd>k</kbd> short ·{" "}
        <kbd>l</kbd> like · <kbd>m</kbd> mute · <kbd>d</kbd> download
      </div>
    </div>
  );
}
