import { useEffect, useState } from "react";
import { finalize, makeScripts, regenerate, type MaterialResult, type UsageTotals } from "./api";
import { Spinner } from "./Spinner";
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
      topic, qa: null, graders: [], state: "loading", note: "", target: "script",
      spent: undefined,
    })),
  );
  const [building, setBuilding] = useState(false);
  const [drafting, setDrafting] = useState(true);
  const [buildError, setBuildError] = useState<string | null>(null);
  // Shorts that BUILT but failed a diagram grader. Separate from buildError: the
  // reel exists and is watchable, its picture is just weaker than it should be.
  const [buildWarnings, setBuildWarnings] = useState<string[]>([]);

  const patch = (i: number, next: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it, k) => (k === i ? { ...it, ...next } : it)));

  // Every question is drafted up front, in one request the server fans out
  // concurrently. Drafting card-by-card meant most of the page sat empty saying
  // "draft it", and the total wait was the sum of every call instead of the
  // slowest one.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await makeScripts(material.doc_id, material.topics);
        if (!alive) return;
        onSpend(r.usage, r.total);
        setItems((prev) => prev.map((it) => {
          const hit = r.results.find((x) => x.topic.id === it.topic.id);
          if (!hit) return { ...it, state: "error", error: "no result returned" };
          if (hit.error || !hit.qa) return { ...it, state: "error", error: hit.error ?? "no script" };
          return { ...it, qa: hit.qa, graders: hit.graders ?? [], state: "ready" };
        }));
      } catch (e) {
        if (!alive) return;
        setItems((prev) => prev.map((it) => ({ ...it, state: "error", error: (e as Error).message })));
      } finally {
        if (alive) setDrafting(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Retry one card after a failure — the batch has already finished by then. */
  async function generate(i: number) {
    patch(i, { state: "loading", error: undefined });
    try {
      const r = await makeScripts(material.doc_id, [items[i].topic]);
      onSpend(r.usage, r.total);
      const hit = r.results[0];
      if (!hit || hit.error || !hit.qa) throw new Error(hit?.error ?? "no script returned");
      patch(i, { qa: hit.qa, graders: hit.graders ?? [], state: "ready", spent: r.usage });
    } catch (e) {
      patch(i, { state: "error", error: (e as Error).message });
    }
  }

  async function redo(i: number) {
    const it = items[i];
    if (!it.note.trim()) return patch(i, { error: "Say what to change first." });
    patch(i, { state: "loading", error: undefined });
    try {
      const r = await regenerate(material.doc_id, it.topic, it.note, it.target,
                                 it.qa ?? undefined);
      onSpend(r.usage, r.total);
      patch(i, { qa: r.qa, graders: r.graders, state: "ready", note: "",
                 spent: addUsage(it.spent, r.usage) });
    } catch (e) {
      patch(i, { state: "error", error: (e as Error).message });
    }
  }

  const approved = items.filter((it) => it.state === "approved" && it.qa);
  const undecided = items.filter((it) => it.state === "ready" || it.state === "loading");
  // "after all accepted then generate the reels" — so nothing may still be
  // waiting on a decision. Skipping is a decision; leaving it open is not.
  const canBuild = approved.length > 0 && undecided.length === 0 && !drafting;

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
      setBuildWarnings(
        Object.entries(r.warnings ?? {}).map(([id, ws]) => `${id} — ${ws.join("; ")}`),
      );
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
        {material.sections.length} sections · {items.length} question{items.length === 1 ? "" : "s"}.
        Each is answered in 3&ndash;4 short parts. Approve the ones that read well, regenerate
        the ones that don&rsquo;t, skip any you don&rsquo;t want. Reels are built once every
        question is decided.
      </p>
      {material.notes && material.notes.length > 0 && (
        <div className="notes">
          <b>Section references corrected</b>
          {material.notes.map((n, i) => <span key={i}>{n}</span>)}
        </div>
      )}
      {drafting && (
        <div className="drafting"><Spinner label={`Writing ${items.length} question${items.length === 1 ? "" : "s"}\u2026`} /></div>
      )}

      {items.map((it, i) => (
        <ReviewCard
          key={it.topic.id}
          item={it}
          onGenerate={() => generate(i)}
          onApprove={() => patch(i, { state: "approved" })}
          onUnapprove={() => patch(i, { state: "ready" })}
          onSkip={() => patch(i, { state: "skipped" })}
          onUnskip={() => patch(i, { state: "ready" })}
          onNote={(note) => patch(i, { note })}
          onTarget={(target) => patch(i, { target })}
          onRedo={() => redo(i)}
        />
      ))}

      <div className="sticky">
        <span><b>{approved.length}</b> approved{undecided.length > 0 && `, ${undecided.length} still to decide`}</span>
        <span className="spacer" />
        <span className="hintline">
          {undecided.length > 0
            ? "approve or skip every question first"
            : "building draws the diagrams and runs the judge"}
        </span>
        <button className="primary" disabled={!canBuild || building} onClick={build}>
          {building
            ? <Spinner label="Drawing diagrams & grading…" />
            : `Build ${approved.length} reel${approved.length === 1 ? "" : "s"} →`}
        </button>
      </div>
      {buildError && <div className="error">{buildError}</div>}
      {buildWarnings.length > 0 && (
        <div className="warn">
          <b>Built, but the diagrams need work</b>
          {buildWarnings.map((w, i) => <span key={i}>{w}</span>)}
        </div>
      )}
    </div>
  );
}

function ReviewCard({
  item, onGenerate, onApprove, onUnapprove, onSkip, onUnskip, onNote, onTarget, onRedo,
}: {
  item: ReviewItem;
  onGenerate: () => void;
  onApprove: () => void;
  onUnapprove: () => void;
  onSkip: () => void;
  onUnskip: () => void;
  onNote: (s: string) => void;
  onTarget: (t: "question" | "answer" | "script") => void;
  onRedo: () => void;
}) {
  const { topic, qa, graders, state } = item;
  const failing = graders.filter((g) => !g.passed);

  return (
    <div className={`card${state === "approved" ? " approved" : ""}${state === "skipped" ? " skipped" : ""}`}>
      <div className="cardhead">
        <div>
          <span className="tag">§{topic.source_section_id}</span>{" "}
          <span className="tag dim">{topic.difficulty}</span>
          <div className="topic">{topic.topic}</div>
          <div className="why">{topic.why_it_matters}</div>
        </div>
        <div className="cardactions">
          {state === "idle" && <button className="ghost" onClick={onGenerate}>Draft it</button>}
          {state === "loading" && <Spinner label="writing…" />}
          {state === "ready" && (
            <>
              <button className="ghost sm" onClick={onSkip}>Skip</button>
              <button className="primary sm" onClick={onApprove}>Approve</button>
            </>
          )}
          {state === "approved" && (
            <button className="ghost sm" onClick={onUnapprove}>✓ approved — undo</button>
          )}
          {state === "skipped" && (
            <button className="ghost sm" onClick={onUnskip}>skipped — bring back</button>
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
                  {/* The sentence this answer restates, checked against the section
                      by substring match server-side. Shown so the reviewer can
                      confirm the answer against the material without leaving the
                      page — that comparison is the whole job of this step. */}
                  {a.source_quote && (
                    <span className="cited" title="verified present in the source section">
                      “{a.source_quote}”
                    </span>
                  )}
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
              {state === "loading" ? <Spinner label="regenerating…" /> : "↻ Regenerate"}
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
