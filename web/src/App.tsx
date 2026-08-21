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
      {step === "reels" && <Reels shorts={shorts} />}
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
function Reels({ shorts }: { shorts: Unit[] }) {
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
        <span className="spacer" />
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
        <kbd>l</kbd> like · <kbd>m</kbd> mute
      </div>
    </div>
  );
}
