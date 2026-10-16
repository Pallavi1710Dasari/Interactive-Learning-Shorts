import { useRef, useState } from "react";
import { Spinner } from "./Spinner";

/**
 * Step 1 — choose what to make, then paste or upload the reading material.
 *
 * What to make (2026-10-16): a REEL (vertical, under two minutes, as before)
 * or a VIDEO (landscape 16:9, 6-12 minutes, the topic taught in depth — like
 * a YouTube lesson). Both go through the same steps.
 *
 * An upload always makes a MOTION reel or video: the material goes to a motion job
 * (shorts/motion_jobs.py, POST /api/motion-jobs — free) and the workspace
 * opens its steps (StepMotion). Nothing is spent until Start there. The old
 * explainer pipeline is CLI-only now (python -m shorts.run); its reels still
 * play in the reels feed.
 */
const FORMATS: { value: "reel" | "video"; label: string; description: string }[] = [
  { value: "reel", label: "Reel",
    description: "Vertical 9:16, under 2 minutes. One question, answered fast — for phones." },
  { value: "video", label: "Video",
    description: "Landscape 16:9, 6–12 minutes, like a YouTube lesson. The topic explained in depth: " +
      "how it works step by step, worked examples and common mistakes." },
];

export function StepMaterial({ onMotion }: {
  /** a motion job was created: open its steps */
  onMotion: (jobId: string) => void;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [format, setFormat] = useState<"reel" | "video">("reel");
  const picker = useRef<HTMLInputElement>(null);

  const ready = (file !== null || text.trim().length >= 200) && !busy;

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      if (file) form.set("file", file);
      else form.set("text", text);
      form.set("format", format);
      const r = await fetch("/api/motion-jobs", { method: "POST", body: form });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : `the server answered ${r.status}`);
      onMotion(d.job_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <h1>What do you want to make?</h1>
      <div className="mchoices mformat" role="radiogroup" aria-label="what to make">
        {FORMATS.map((f) => (
          <button key={f.value} type="button" role="radio" aria-checked={format === f.value}
                  className={`mchoice${format === f.value ? " on" : ""}`} data-format={f.value}
                  onClick={() => setFormat(f.value)}>
            <div className="t"><span className={`mformat-shape ${f.value}`} aria-hidden />{f.label}</div>
            <div className="d">{f.description}</div>
          </button>
        ))}
      </div>

      <h1 style={{ marginTop: 26 }}>Reading material</h1>
      <p className="lede">
        Paste it, or upload a <code>.md</code> / <code>.txt</code> file. Use headings
        like <code>## 3.1 Why paging exists</code> so every {format} can cite the section
        it came from. You get animated scenes, a 3D presenter and a voice, and you
        check each step before anything is spent.
      </p>

      <textarea
        className="paste"
        placeholder={"## 3.1 Why paging exists\nContiguous allocation forces every process…"}
        value={text}
        onChange={(e) => { setText(e.target.value); setFile(null); }}
        spellCheck={false}
      />

      <div className="row">
        <input
          ref={picker}
          type="file"
          accept=".md,.markdown,.txt,text/plain"
          style={{ display: "none" }}
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); setText(""); }}
        />
        <button className="ghost" onClick={() => picker.current?.click()}>
          {file ? `📄 ${file.name}` : "📄 Upload a file"}
        </button>
        {file && <button className="ghost" onClick={() => setFile(null)}>clear</button>}

        <span className="spacer" />
        <span className="hintline">
          {file ? "file selected" : `${text.trim().length} chars`}
        </span>
        <button className="primary big" disabled={!ready} onClick={go}>
          {busy ? <Spinner label="Reading the file…" /> : format === "video" ? "Make a video →" : "Make a reel →"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}
    </div>
  );
}
