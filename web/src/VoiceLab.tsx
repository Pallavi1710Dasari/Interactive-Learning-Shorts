import { useEffect, useState } from "react";
import { Spinner } from "./Spinner";

/**
 * The voice studio: give each speaker a voice, hear them talk, keep them.
 *
 * TWO SLOTS, NOT ONE CLIP. The first version took a single recording and said one
 * line with it. That answers "what does this clip sound like" and not the question
 * actually being asked, which is whether the INTERVIEWER and the STUDENT work
 * together — two voices that are each fine alone can still be too alike to tell
 * apart, or jarring back to back. A reel is an exchange, so the preview is an
 * exchange: the question in one voice, the answer in the other, in one track.
 *
 * Adopting writes voices/settings.json server-side, which Chatterbox.resolve()
 * reads before the environment — so a choice made by ear here survives a restart
 * with no file editing.
 */
type State = {
  chosen: { interviewer?: string; student?: string };
  chatterbox_ready: boolean;
  installed: boolean;
  active: string;
};

type Slot = "interviewer" | "student";

const DEFAULT_LINES: Record<Slot, string> = {
  interviewer: "Why must all computer data be represented in binary?",
  student:
    "Computers only work with two values, ones and zeros, so everything they " +
    "process has to be written that way.",
};

const ROLE: Record<Slot, { title: string; hint: string }> = {
  interviewer: { title: "Interviewer", hint: "asks the question" },
  student: { title: "Student", hint: "gives the answer" },
};

export function VoiceLab({ onClose, onKept }: {
  onClose: () => void;
  /** Voices saved — hand control back so the user can go and make a reel. */
  onKept?: () => void;
}) {
  const [state, setState] = useState<State | null>(null);
  const [clips, setClips] = useState<Partial<Record<Slot, File>>>({});
  const [urls, setUrls] = useState<Partial<Record<Slot, string>>>({});
  const [lines, setLines] = useState<Record<Slot, string>>({ ...DEFAULT_LINES });
  const [dragging, setDragging] = useState<Slot | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ url: string; job: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/voice/state").then((r) => r.json()).then(setState).catch(() => {});
  }, []);

  function useClip(slot: Slot, f: File) {
    setResult(null);
    setClips((c) => ({ ...c, [slot]: f }));
    setUrls((u) => {
      if (u[slot]) URL.revokeObjectURL(u[slot]!);
      return { ...u, [slot]: URL.createObjectURL(f) };
    });
  }

  function clear(slot: Slot) {
    setResult(null);
    setClips((c) => { const next = { ...c }; delete next[slot]; return next; });
    setUrls((u) => {
      if (u[slot]) URL.revokeObjectURL(u[slot]!);
      const next = { ...u }; delete next[slot]; return next;
    });
  }

  const filled = (["interviewer", "student"] as Slot[]).filter((s) => clips[s]);

  async function speak() {
    if (!filled.length || busy) return;
    setBusy(true); setErr(null); setResult(null); setStatus("starting…");
    try {
      const form = new FormData();
      form.set("text_interviewer", lines.interviewer);
      form.set("text_student", lines.student);
      for (const s of filled) form.set(`clip_${s}`, clips[s]!);

      const res = await fetch("/api/voice/speak", { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json()).detail ?? `HTTP ${res.status}`);
      const { job_id } = await res.json();

      for (;;) {
        await new Promise((r) => setTimeout(r, 1200));
        const j = await (await fetch(`/api/voice/job/${job_id}`)).json();
        if (j.status === "error") throw new Error(j.error);
        if (j.status === "done") { setResult({ url: j.audio_url, job: job_id }); break; }
        // The first call of a run loads the model; say so rather than spin silently.
        setStatus(j.status === "speaking"
          ? "speaking… (the first one also loads the model, ~2 min)"
          : "queued…");
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); setStatus(null); }
  }

  /**
   * Save the voices. Does NOT require a preview.
   *
   * It used to: the button was `disabled={!result}`, so uploading two clips and
   * pressing Keep did nothing at all — silently, because a disabled button cannot
   * explain itself. Previewing is worth doing and still here; it is not a toll
   * gate. If a preview HAS been generated the job is adopted (its clips are
   * already on the server); otherwise the uploads are posted directly.
   */
  async function keep() {
    if (!filled.length || busy) return;
    setBusy(true); setErr(null); setSaved(null);
    try {
      let res: Response;
      if (result) {
        const form = new FormData();
        form.set("job_id", result.job);
        res = await fetch("/api/voice/adopt", { method: "POST", body: form });
      } else {
        const form = new FormData();
        for (const sl of filled) form.set(`clip_${sl}`, clips[sl]!);
        res = await fetch("/api/voice/keep", { method: "POST", body: form });
      }
      if (!res.ok) throw new Error((await res.json()).detail ?? `HTTP ${res.status}`);
      const next = await res.json();
      setState(next);
      setSaved(next.active ?? "saved");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  async function reset() {
    setBusy(true);
    try { setState(await (await fetch("/api/voice/reset", { method: "POST" })).json()); }
    finally { setBusy(false); }
  }

  const chosen = state?.chosen ?? {};
  const anyChosen = !!(chosen.interviewer || chosen.student);

  const renderSlot = (s: Slot) => (
    <div className="vslot" key={s}>
      <div className="vslothead">
        <b>{ROLE[s].title}</b><small>{ROLE[s].hint}</small>
      </div>
      {clips[s] ? (
        <div className="vslotclip">
          <div className="vslotname">
            {clips[s]!.name} · {(clips[s]!.size / 1024).toFixed(0)} KB
            <button className="linky" onClick={() => clear(s)}>replace</button>
          </div>
          <audio controls src={urls[s]} />
        </div>
      ) : (
        <label className="dropzone sm"
               data-dragging={dragging === s || undefined}
               onDragOver={(e) => { e.preventDefault(); setDragging(s); }}
               onDragLeave={() => setDragging(null)}
               onDrop={(e) => {
                 e.preventDefault(); setDragging(null);
                 const f = e.dataTransfer.files?.[0];
                 if (f) useClip(s, f);
               }}>
          <b>Drop {ROLE[s].title.toLowerCase()} voice</b>
          <span>or click · wav, mp3, m4a, ogg</span>
          <input type="file" accept="audio/*" hidden
                 onChange={(e) => e.target.files?.[0] && useClip(s, e.target.files[0])} />
        </label>
      )}
      <textarea rows={2} value={lines[s]}
                onChange={(e) => setLines((l) => ({ ...l, [s]: e.target.value }))} />
    </div>
  );

  return (
    <div className="voicelab">
      <header className="vlhead">
        <div>
          <h1>Voice</h1>
          <p className="lede">
            Upload a voice for each speaker, hear them read a question and answer,
            then keep them. Every reel is narrated in those two voices.
          </p>
        </div>
        <button className="ghost sm" onClick={onClose}>close</button>
      </header>

      {state && !state.installed && (
        <div className="error">
          Chatterbox is not installed yet. In a terminal, once:
          <code style={{ display: "block", marginTop: 6 }}>
            python3 -m venv venv-chatterbox &amp;&amp; venv-chatterbox/bin/pip install chatterbox-tts
          </code>
        </div>
      )}

      <div className="vlgrid">
        <section className="vlcard wide">
          <h2><span className="vlnum">1</span> A voice for each speaker</h2>
          <p className="why">
            7&ndash;20 seconds each, one person per clip, no music. These set the
            ceiling for everything generated from them. Upload one and it speaks
            both parts; upload two and they stay apart.
          </p>
          <div className="vslots">
            {(["interviewer", "student"] as Slot[]).map(renderSlot)}
          </div>
        </section>

        <section className="vlcard">
          <h2><span className="vlnum">2</span> Hear them together</h2>
          <p className="why">
            The lines above, spoken as an exchange — which is how a reel actually
            sounds. Two voices can each be fine and still be too alike side by side.
          </p>
          <button className="primary" disabled={!filled.length || busy} onClick={speak}>
            {busy && status ? <Spinner label={status} /> : "Speak it →"}
          </button>
          {result && (
            <div className="vlresult">
              <b>question, then answer</b>
              <audio controls autoPlay src={result.url} />
            </div>
          )}
        </section>

        <section className="vlcard">
          <h2><span className="vlnum">3</span> Keep them</h2>
          <p className="why">
            Saved for every reel you build from now on. Reels you have already made
            are left exactly as they are.
          </p>
          <button className="primary" disabled={!filled.length || busy} onClick={keep}>
            {busy ? <Spinner label="saving…" /> : "Keep these voices"}
          </button>
          {!filled.length && (
            <span className="why">Upload a voice above first.</span>
          )}

          {saved && (
            <div className="vlsaved">
              <b>✓ Saved</b>
              <span>
                Every reel you build from now on is narrated in these voices.
                Existing reels are unchanged.
              </span>
              <button className="primary sm" onClick={() => { onKept?.(); onClose(); }}>
                Make a reel →
              </button>
            </div>
          )}

          <div className="vlstate">
            <div><span>now speaking</span> {state?.active ?? "…"}</div>
            {chosen.interviewer && (
              <div><span>interviewer</span> {chosen.interviewer.split("/").pop()}</div>
            )}
            {chosen.student && (
              <div><span>student</span> {chosen.student.split("/").pop()}</div>
            )}
            {anyChosen && (
              <button className="ghost sm" onClick={reset} disabled={busy}>
                revert to .env
              </button>
            )}
          </div>
        </section>
      </div>

      {err && <div className="error">{err}</div>}
    </div>
  );
}
