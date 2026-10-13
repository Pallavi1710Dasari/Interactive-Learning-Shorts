import { useRef, useState } from "react";
import { Spinner } from "./Spinner";

/**
 * Step 1 — paste or upload the reading material.
 *
 * An upload always makes a MOTION reel: the material goes to a motion job
 * (shorts/motion_jobs.py, POST /api/motion-jobs — free) and the workspace
 * opens its steps (StepMotion). Nothing is spent until Start there. The old
 * explainer pipeline is CLI-only now (python -m shorts.run); its reels still
 * play in the reels feed.
 */
export function StepMaterial({ onMotion }: {
  /** a motion job was created: open its steps */
  onMotion: (jobId: string) => void;
}) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const ready = (file !== null || text.trim().length >= 200) && !busy;

  async function go() {
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      if (file) form.set("file", file);
      else form.set("text", text);
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
      <h1>Reading material</h1>
      <p className="lede">
        Paste it, or upload a <code>.md</code> / <code>.txt</code> file. Use headings
        like <code>## 3.1 Why paging exists</code> so every reel can cite the section
        it came from. You get a motion reel: animated scenes and a voice, and you
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
          {busy ? <Spinner label="Reading the file…" /> : "Make a motion reel →"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}
    </div>
  );
}
