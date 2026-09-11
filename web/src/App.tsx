import { useCallback, useEffect, useRef, useState } from "react";
import { getHealth, getShorts, getUsage, renderStatus, startRender,
         type MaterialResult, type UsageTotals } from "./api";
import { CostPill } from "./CostPill";
import { Reel } from "./Reel";
import { StepMaterial } from "./StepMaterial";
import { StepApprove } from "./StepApprove";
import { StepReview } from "./StepReview";
import { VoiceLab } from "./VoiceLab";
import { CaptureStage } from "./CaptureStage";
import { pickVoices, useVoices } from "./useNarration";
import type { Feedback, Topic, Unit } from "./types";

type Step = "material" | "approve" | "review" | "reels";

export default function App() {
  // #capture/<short_id> — the MP4 renderer's entry point, and deliberately the
  // FIRST thing checked. It must render the short and nothing else: no topbar, no
  // step crumbs, no cost pill. shorts/video.py photographs whatever is on this
  // page, so anything drawn here ends up in the file someone posts.
  const capture = useCaptureRoute();
  if (capture) return <CaptureRoute shortId={capture} />;

  return <Workspace />;
}

/** The short id in #capture/<id>, or null when this is a normal page load. */
function useCaptureRoute(): string | null {
  const [route] = useState(() => {
    const [head, id] = location.hash.replace(/^#/, "").split("/");
    // The id carries its own query string — `?bgscale=` for ThreeStage, read
    // straight off location.hash where it is set — so split that off here rather
    // than handing "shortid?bgscale=0.3" to the feed lookup as a literal id.
    const bare = id ? id.split("?")[0] : id;
    return head === "capture" && bare ? decodeURIComponent(bare) : null;
  });
  return route;
}

/**
 * One short, alone on the page, for the renderer to photograph.
 *
 * It fetches the feed rather than being handed a unit, because the renderer opens
 * this URL cold in a fresh browser. `window.__captureError` is set on failure so
 * the renderer can fail with the reason instead of timing out on a blank page.
 *
 * HELD SHORTS INCLUDED, deliberately. The ordinary feed leaves a quarantined short
 * out, which made `python -m shorts.video <held id>` fail with "no such short in
 * the feed" — the reel was on disk, watchable once asked for by name, and could
 * still not be exported. Naming an id here IS asking for it by name.
 */
function CaptureRoute({ shortId }: { shortId: string }) {
  const [unit, setUnit] = useState<Unit | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getShorts(true)
      .then((all) => {
        const hit = all.find((u) => u.short_id === shortId);
        if (!hit) throw new Error(`no such short in the feed: ${shortId}`);
        setUnit(hit);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        (window as unknown as Record<string, unknown>).__captureError = msg;
        setError(msg);
      });
  }, [shortId]);
  if (error) return <div className="center"><b>capture failed</b><p>{error}</p></div>;
  if (!unit) return null;
  return <CaptureStage unit={unit} />;
}

function Workspace() {
  const [step, setStep] = useState<Step>("material");
  const [voiceOpen, setVoiceOpen] = useState(false);
  // The cost breakdown is opt-in, not ambient. It used to render unconditionally
  // in the topbar, which put a running dollar figure and a token count in front
  // of a non-engineer reviewer on every screen — the product owner's own
  // complaint. The spend is still real and still worth a glance, so a click
  // reveals it; see the dot on the toggle button below for why a spend still
  // cannot go by unnoticed while collapsed.
  const [costOpen, setCostOpen] = useState(false);
  // THE ACTIVE VOICE IS SHOWN IN THE HEADER, not only inside the panel that sets
  // it. The voice is stored on the SERVER and shared by every device pointed at
  // it, so "which voice is live" is a fact about the app rather than about this
  // browser — and if it can only be seen by opening a dialog, the honest answer to
  // "is it still my voice?" is a click away instead of on screen.
  const [voiceNow, setVoiceNow] = useState<string | null>(null);
  const readVoice = useCallback(() => {
    fetch("/api/voice").then((r) => r.json())
      .then((v) => setVoiceNow(v.reason ?? null)).catch(() => {});
  }, []);
  useEffect(() => { readVoice(); }, [readVoice]);
  // Re-read when the studio closes: that is the only thing that can change it.
  useEffect(() => { if (!voiceOpen) readVoice(); }, [voiceOpen, readVoice]);
  const [material, setMaterial] = useState<MaterialResult | null>(null);
  // Step 3's gate output: ONLY the topics a human approved (with regenerated
  // wording already substituted in — see StepApprove's onDone). StepReview is
  // handed these instead of material.topics, unmodified otherwise.
  const [approvedTopics, setApprovedTopics] = useState<Topic[] | null>(null);
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
          <Crumb n={2} label="Approve" on={step === "approve"} done={!!approvedTopics}
                 disabled={!material} onClick={() => setStep("approve")} />
          <Crumb n={3} label="Review Q&amp;A" on={step === "review"} done={shorts.length > 0}
                 disabled={!approvedTopics} onClick={() => setStep("review")} />
          <Crumb n={4} label="Reels" on={step === "reels"} done={false}
                 disabled={!shorts.length} onClick={() => setStep("reels")} />
        </nav>
        <span className="spacer" />
        {total && costOpen && <CostPill total={total} delta={delta} />}
        <button className="ghost sm costtoggle" onClick={() => setCostOpen((v) => !v)}
                title={costOpen ? "hide cost & token spend" : "show cost & token spend"}>
          $
          {/* A spend still has to be noticeable while the pill is collapsed —
              this is the one thing that survives hiding it — but it is a dot,
              not the figure itself, so it does not reintroduce the always-on
              number the toggle exists to remove. */}
          {!costOpen && delta && delta.cost > 0 && <i className="costdot" aria-hidden="true" />}
        </button>
        <span className="hintline">{health ? (health.stub ? "stub mode" : health.model) : "…"}</span>
        <button className={`ghost sm voicechip${voiceNow?.startsWith("chatterbox") ? " mine" : ""}`}
                onClick={() => setVoiceOpen(true)}
                title={voiceNow ? `narration: ${voiceNow}` : "set the narration voice"}>
          {voiceNow?.startsWith("chatterbox") ? "your voice" : "voice"}
        </button>
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
          onDone={(r) => {
            onSpend(r.usage, r.total);
            setMaterial(r);
            setApprovedTopics(null);   // a fresh material means a fresh approval pass
            setStep("approve");
          }}
        />
      )}
      {step === "approve" && material && (
        <StepApprove
          material={material}
          onSpend={onSpend}
          onDone={(topics) => { setApprovedTopics(topics); setStep("review"); }}
        />
      )}
      {step === "review" && material && approvedTopics && (
        <StepReview
          material={{ ...material, topics: approvedTopics }}
          onSpend={onSpend}
          onDone={(s) => { setShorts(s); setStep("reels"); }}
          // A held short is kept out of the feed, so open the feed that includes it
          // and point the player straight at the one being asked about.
          onWatchHeld={(id) => {
            getShorts(true)
              .then((s) => { setShorts(s); setFocus(id); setStep("reels"); })
              .catch(() => {});
          }}
        />
      )}
      {voiceOpen && (
        <VoiceLab
          onClose={() => setVoiceOpen(false)}
          // Saving a voice is the start of making something, not the end of a
          // settings errand — so it hands back to step 1 rather than leaving the
          // person on a panel they are finished with.
          onKept={() => { readVoice(); setStep("material"); }}
        />
      )}

      {step === "reels" && (
        <Reels shorts={shorts} focus={focus}
               // A redraw replaces one short's frames on the server; swap it in
               // here so the feed shows the new pictures without a refetch.
               onReplace={(next) => setShorts((all) =>
                 all.map((u) => (u.short_id === next.short_id ? next : u)))} />
      )}
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
function Reels({ shorts, focus, onReplace }: {
  shorts: Unit[]; focus?: string | null; onReplace: (u: Unit) => void;
}) {
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
      // "d" is handled inside <Reel>, which knows which short is on screen and
      // owns the rail button it belongs to. Handling it here as well fired the
      // render twice for one keypress.
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active]);

  // DOWNLOAD THE SHORT ON SCREEN, as an MP4.
  //
  // HOOKS BEFORE THE EARLY RETURN, and that is not a style preference: this
  // useState pair used to sit BELOW the `if (!shorts.length) return` above, so on
  // the render where the feed arrives React saw two hooks appear out of nowhere and
  // the component's hook order changed. It survived only because the empty branch
  // is rare on a machine that already has units in output/.
  //
  // The render is a real capture of the player now — every frame photographed at
  // 30fps — so the first download of a short takes a minute rather than seconds
  // and the button MUST say so. It is cached afterwards.
  const [saving, setSaving] = useState<string | null>(null);
  const [saveErr, setSaveErr] = useState<string | null>(null);

  const [progress, setProgress] = useState(0);

  const download = useCallback(async (unit: Unit) => {
    if (!unit || saving) return;
    setSaving(unit.short_id);
    setSaveErr(null);
    setProgress(0);
    try {
      // POST-THEN-POLL, because the render is about ninety seconds. It used to be
      // one GET held open for the whole of it, which worked on localhost only
      // because nothing in the path times out — and gave the button nothing to show
      // but a spinner. Now the server owns the job and this asks how far it is.
      let job = await startRender(unit.short_id);
      while (job.status === "queued" || job.status === "rendering") {
        await new Promise((r) => setTimeout(r, 900));
        job = await renderStatus(unit.short_id);
        if (job.total) setProgress(Math.round((100 * job.done) / job.total));
      }
      if (job.status === "error") throw new Error(job.error ?? "render failed");

      const res = await fetch(`/api/video/${encodeURIComponent(unit.short_id)}`);
      if (!res.ok) {
        let msg = `render failed (${res.status})`;
        try { msg = (await res.json()).detail ?? msg; } catch { /* keep the status */ }
        throw new Error(msg);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${unit.short_id}.mp4`;
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
      setProgress(0);
    }
  }, [saving]);

  // Reachable now only by opening the app with an empty output/ — a build that
  // produces nothing playable keeps the reviewer on step 2, next to the reasons,
  // instead of dumping them here to read setup advice for work they already did.
  if (!shorts.length) {
    return (
      <div className="center">
        <div>
          <b>No reels yet</b>
          <p className="lede">
            Paste material in step 1, approve some answers in step 2. Shorts the judge
            scored under the bar are held back from the reel and reported on step 2 —
            they stay in <code>output/</code> with their verdict.
          </p>
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
                  onFeedback={onFeedback} onDownload={download}
                  downloading={saving === unit.short_id}
                  downloadPct={saving === unit.short_id ? progress : 0}
                  onRedrawn={onReplace} />
          </div>
        ))}
      </div>

      <div className="hint">
        scroll for the next short · <kbd>space</kbd> pause (stops the voice) ·{" "}
        <kbd>←</kbd>/<kbd>→</kbd> beat · <kbd>j</kbd>/<kbd>k</kbd> short ·{" "}
        <kbd>m</kbd> mute · <kbd>r</kbd> replay · <kbd>d</kbd> download
      </div>
    </div>
  );
}
