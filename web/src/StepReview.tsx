import { useEffect, useState } from "react";
import { finalize, makeScript, regenerate, type MaterialResult, type UsageTotals } from "./api";
import { money, tokens } from "./CostPill";
import { Interviewer, Student } from "./Avatars";
import type { QA, ReviewItem, Unit } from "./types";

/**
 * Step 2 — the human gate, on one question and one answer.
 *
 * Scripts are drafted one topic at a time so a slow or failing topic never blocks
 * reviewing the others, and nothing is generated for a topic the reviewer drops.
 * Regeneration takes a free-text note; that note is the whole point of the step.
 */
export function StepReview({
  material, onDone, onSpend,
}: {
  material: MaterialResult;
  onDone: (shorts: Unit[]) => void;
  onSpend: (delta: UsageTotals, total: UsageTotals) => void;
}) {
  const [items, setItems] = useState<ReviewItem[]>(
    material.topics.map((topic) => ({
      topic, qa: null, graders: [], state: "idle", note: "", target: "script",
      spent: undefined,
    })),
  );
  const [building, setBuilding] = useState(false);
  const [buildError, setBuildError] = useState<string | null>(null);

  const patch = (i: number, next: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it, k) => (k === i ? { ...it, ...next } : it)));

  async function generate(i: number) {
    patch(i, { state: "loading", error: undefined });
    try {
      const r = await makeScript(material.doc_id, items[i].topic);
      onSpend(r.usage, r.total);
      patch(i, { qa: r.qa, graders: r.graders, state: "ready", spent: r.usage });
    } catch (e) {
      patch(i, { state: "error", error: (e as Error).message });
    }
  }

  // Draft the first one automatically so the step is not an empty page.
  useEffect(() => {
    if (items.length && items[0].state === "idle") generate(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function redo(i: number) {
    const it = items[i];
    if (!it.note.trim()) return patch(i, { error: "Say what to change first." });
    patch(i, { state: "loading", error: undefined });
    try {
      const r = await regenerate(material.doc_id, it.topic, it.note, it.target);
      onSpend(r.usage, r.total);
      patch(i, { qa: r.qa, graders: r.graders, state: "ready", note: "",
                 spent: addUsage(it.spent, r.usage) });
    } catch (e) {
      patch(i, { state: "error", error: (e as Error).message });
    }
  }

  const approved = items.filter((it) => it.state === "approved" && it.qa);
  const drafted = items.filter((it) => it.qa);

  async function build() {
    setBuilding(true);
    setBuildError(null);
    try {
      const r = await finalize(
        material.doc_id,
        approved.map((it) => ({ topic: it.topic, qa: it.qa as QA })),
      );
      onSpend(r.usage, r.total);
      if (r.failed.length) {
        setBuildError(r.failed.map((f) => `${f.topic_id}: ${f.error}`).join("; "));
      }
      onDone(r.shorts);
    } catch (e) {
      setBuildError((e as Error).message);
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="panel wide">
      <h1>Review the questions &amp; answers</h1>
      <p className="lede">
        {material.sections.length} sections · {items.length} suggested shorts · {drafted.length} drafted.
        Each short is one question answered in 3&ndash;4 short parts. Approve what reads well; if it isn&rsquo;t
        right, say what to change and regenerate. Nothing is built until you say so.
      </p>

      {items.map((it, i) => (
        <ReviewCard
          key={it.topic.id}
          item={it}
          onGenerate={() => generate(i)}
          onApprove={() => patch(i, { state: "approved" })}
          onUnapprove={() => patch(i, { state: "ready" })}
          onNote={(note) => patch(i, { note })}
          onTarget={(target) => patch(i, { target })}
          onRedo={() => redo(i)}
        />
      ))}

      <div className="sticky">
        <span><b>{approved.length}</b> of {items.length} approved</span>
        <span className="spacer" />
        <span className="hintline">building draws the diagrams and runs the judge</span>
        <button className="primary" disabled={!approved.length || building} onClick={build}>
          {building ? "Drawing diagrams & grading…" : `Build ${approved.length} reel${approved.length === 1 ? "" : "s"} →`}
        </button>
      </div>
      {buildError && <div className="error">{buildError}</div>}
    </div>
  );
}

function ReviewCard({
  item, onGenerate, onApprove, onUnapprove, onNote, onTarget, onRedo,
}: {
  item: ReviewItem;
  onGenerate: () => void;
  onApprove: () => void;
  onUnapprove: () => void;
  onNote: (s: string) => void;
  onTarget: (t: "question" | "answer" | "script") => void;
  onRedo: () => void;
}) {
  const { topic, qa, graders, state } = item;
  const failing = graders.filter((g) => !g.passed);

  return (
    <div className={`card${state === "approved" ? " approved" : ""}`}>
      <div className="cardhead">
        <div>
          <span className="tag">§{topic.source_section_id}</span>{" "}
          <span className="tag dim">{topic.difficulty}</span>
          <div className="topic">{topic.topic}</div>
          <div className="why">{topic.why_it_matters}</div>
        </div>
        <div className="cardactions">
          {state === "idle" && <button className="ghost" onClick={onGenerate}>Draft it</button>}
          {state === "loading" && <span className="hintline">writing…</span>}
          {state === "ready" && <button className="primary sm" onClick={onApprove}>Approve</button>}
          {state === "approved" && (
            <button className="ghost sm" onClick={onUnapprove}>✓ approved — undo</button>
          )}
          {state === "error" && <button className="ghost" onClick={onGenerate}>Retry</button>}
        </div>
      </div>

      {item.error && <div className="error sm">{item.error}</div>}

      {qa && (
        <>
          <div className="qa">
            <div className="qaline">
              <span className="label">Asks</span>
              <span className="avatarcell"><Interviewer size={34} /></span>
              <span className="body">{qa.question}</span>
            </div>
            {qa.answers.map((a, k) => (
              <div className="qaline" key={a.index}>
                <span className="label">{k === 0 ? "Answers" : ""}</span>
                <span className="avatarcell">
                  {k === 0 ? <Student size={34} /> : <span className="stepdot">{k + 1}</span>}
                </span>
                <span className="body">
                  {a.line}
                  <span className="os">on screen: {a.on_screen}</span>
                </span>
              </div>
            ))}
          </div>

          <div className="graders">
            {graders.map((g) => (
              <span key={g.name} className={`chip ${g.passed ? "ok" : "bad"}`} title={g.reason}>
                {g.passed ? "✓" : "✕"} {g.name}
              </span>
            ))}
            <span className="chip dim">{qa.words} words · {qa.seconds}s</span>
            {item.spent && (
              <span className="chip dim" title={`${item.spent.calls} model calls`}>
                {money(item.spent.cost, item.spent.estimated)} · {tokens(item.spent.input_tokens + item.spent.output_tokens)}
              </span>
            )}
          </div>
          {failing.map((g) => (
            <div className="error sm" key={g.name}>{g.name}: {g.reason}</div>
          ))}

          <div className="redo">
            <select value={item.target} onChange={(e) => onTarget(e.target.value as never)}>
              <option value="script">rewrite both</option>
              <option value="question">just the question</option>
              <option value="answer">just the answer</option>
            </select>
            <input
              className="note"
              placeholder="What should change? e.g. “too vague — name the valid bit explicitly”"
              value={item.note}
              onChange={(e) => onNote(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") onRedo(); }}
            />
            <button className="ghost" disabled={state === "loading"} onClick={onRedo}>
              ↻ Regenerate
            </button>
          </div>
        </>
      )}
    </div>
  );
}

/** Per-card running cost across a draft plus any regenerations. */
function addUsage(a: UsageTotals | undefined, b: UsageTotals): UsageTotals {
  if (!a) return b;
  return {
    calls: a.calls + b.calls,
    input_tokens: a.input_tokens + b.input_tokens,
    output_tokens: a.output_tokens + b.output_tokens,
    cost: +(a.cost + b.cost).toFixed(6),
    estimated: a.estimated || b.estimated,
    by_label: b.by_label,
  };
}
