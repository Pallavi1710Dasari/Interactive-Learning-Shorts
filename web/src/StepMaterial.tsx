import { useRef, useState } from "react";
import { submitMaterial, type MaterialResult } from "./api";
import { Spinner } from "./Spinner";

/**
 * Step 1 — paste or upload the reading material.
 *
 * One LLM call (topic selection), so this is cheap to redo.
 */
export function StepMaterial({ onDone }: { onDone: (r: MaterialResult) => void }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [target, setTarget] = useState(5);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const ready = (file !== null || text.trim().length >= 200) && !busy;

  async function go() {
    setBusy(true);
    setError(null);
    try {
      onDone(await submitMaterial({ text, file: file ?? undefined, target }));
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
        like <code>## 3.1 Why paging exists</code> so every short can cite the section
        it came from.
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

        <label className="inline">
          shorts to suggest
          <input
            type="number" min={1} max={12} value={target}
            onChange={(e) => setTarget(Math.max(1, Math.min(12, +e.target.value)))}
          />
        </label>

        <span className="spacer" />
        <span className="hintline">
          {file ? "file selected" : `${text.trim().length} chars`}
        </span>
        <button className="primary" disabled={!ready} onClick={go}>
          {busy ? <Spinner label="Reading & suggesting…" /> : "Suggest questions →"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}
    </div>
  );
}
