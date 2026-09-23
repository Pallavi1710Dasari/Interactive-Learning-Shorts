import { useEffect, useRef, useState } from "react";
import { makeWorkflowScripts, regenerate, type MaterialResult, type UsageTotals } from "./api";
import { Spinner } from "./Spinner";
import { money, tokens } from "./CostPill";
import { Interviewer } from "./Avatars";
import { describeApproach, effectiveTeachingApproach,
         type QuestionWorkflow, type ReviewItem } from "./types";

/**
 * Step 8-9 of the question workflow: draft a script for each question WHOSE
 * TEACHING APPROACH A HUMAN HAS ALREADY APPROVED (see StepTeachingApproach,
 * the step before this one), and let a human read it before anything is
 * drawn or rendered.
 *
 * Every script here is drafted through the WORKFLOW-AWARE path — framing, the
 * APPROVED teaching approach, then write_script_for_workflow — via
 * POST /api/workflow/scripts, not the plain write_script make_scripts used to
 * call. See that endpoint's own docstring: it now refuses a workflow whose
 * teaching approach is not approved, rather than deciding or approving one
 * itself — that decision belongs entirely to StepTeachingApproach.
 *
 * Scripts are drafted one workflow at a time so a slow or failing one never
 * blocks reviewing the others, and nothing is generated for a workflow the
 * reviewer drops. Regeneration takes a free-text note; that note is the whole
 * point of the step. Approved scripts are handed to StepVisualPlan next —
 * rendering does not happen here.
 */
export function StepReview({
  material, workflows, onDone, onSpend,
}: {
  material: MaterialResult;
  /** Step 6's gate output — workflows whose teaching approach is approved. */
  workflows: QuestionWorkflow[];
  onDone: (workflows: QuestionWorkflow[]) => void;
  onSpend: (delta: UsageTotals, total: UsageTotals) => void;
}) {
  const [items, setItems] = useState<ReviewItem[]>(
    workflows.map((workflow) => ({
      workflow, topic: workflow.selection.topic, qa: null, graders: [], judge: undefined,
      state: "loading", note: "", target: "script", spent: undefined,
    })),
  );
  const [drafting, setDrafting] = useState(true);
  // TWO SEPARATE REFS, ON PURPOSE. `started` gates whether a fetch is ever
  // sent — set once, NEVER reset, checked BEFORE the fetch — so StrictMode's
  // double-mount in dev cannot send /api/workflow/scripts (a real
  // script-writing LLM call) twice. `mounted` tracks whether THIS component
  // instance is *currently* on screen, and is reset on EVERY effect
  // invocation, not just the first — so it correctly reads `true` again by
  // the time the one real fetch resolves, even though StrictMode's
  // synchronous mount -> cleanup -> remount cycle runs (and its cleanup
  // fires) before that fetch's promise settles. A single `alive` local
  // variable captured only by the FIRST invocation's closure could not
  // recover from that cleanup — it stayed `false` forever, so the only
  // fetch that ever ran had its successful result silently discarded and
  // the "drafting…" spinner never cleared.
  const started = useRef(false);
  const mounted = useRef(false);

  const patch = (i: number, next: Partial<ReviewItem>) =>
    setItems((prev) => prev.map((it, k) => (k === i ? { ...it, ...next } : it)));

  // Every question is drafted up front, in one request the server fans out
  // concurrently. Drafting card-by-card meant most of the page sat empty saying
  // "draft it", and the total wait was the sum of every call instead of the
  // slowest one.
  useEffect(() => {
    mounted.current = true;
    if (!started.current) {
      started.current = true;
      (async () => {
        try {
          const r = await makeWorkflowScripts(material.doc_id, workflows);
          if (!mounted.current) return;
          onSpend(r.usage, r.total);
          setItems((prev) => prev.map((it) => {
            const hit = r.results.find((x) => x.topic.id === it.topic.id);
            if (!hit) return { ...it, state: "error", error: "no result returned" };
            if (hit.error || !hit.qa) return { ...it, state: "error", error: hit.error ?? "no script" };
            // hit.topic is the workflow's approved_topic (regenerated wording
            // already substituted, if any) — the same effective text the
            // script was actually drafted from, not the original suggestion.
            return { ...it, topic: hit.topic, qa: hit.qa, graders: hit.graders ?? [],
                     judge: hit.judge ?? null,
                     state: "ready", workflow: hit.workflow ?? it.workflow };
          }));
        } catch (e) {
          if (!mounted.current) return;
          setItems((prev) => prev.map((it) => ({ ...it, state: "error", error: (e as Error).message })));
        } finally {
          if (mounted.current) setDrafting(false);
        }
      })();
    }
    return () => { mounted.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** Retry one card after a failure — the batch has already finished by then. */
  async function generate(i: number) {
    patch(i, { state: "loading", error: undefined });
    try {
      const r = await makeWorkflowScripts(material.doc_id, [items[i].workflow]);
      onSpend(r.usage, r.total);
      const hit = r.results[0];
      if (!hit || hit.error || !hit.qa) throw new Error(hit?.error ?? "no script returned");
      patch(i, { topic: hit.topic, qa: hit.qa, graders: hit.graders ?? [],
                 judge: hit.judge ?? null, state: "ready",
                 spent: r.usage, workflow: hit.workflow ?? items[i].workflow });
    } catch (e) {
      patch(i, { state: "error", error: (e as Error).message });
    }
  }

  async function redo(i: number) {
    const it = items[i];
    if (!it.note.trim()) return patch(i, { error: "Say what to change first." });
    patch(i, { state: "loading", error: undefined });
    try {
      // it.workflow carries the framing + approved teaching approach the
      // script was drafted from, so the regeneration keeps following it too.
      const r = await regenerate(material.doc_id, it.topic, it.note, it.target,
                                 it.qa ?? undefined, it.workflow);
      onSpend(r.usage, r.total);
      // /api/regenerate does not run the review judge (see server.py) — the old
      // verdict was for the script this just replaced, so drop it rather than
      // show a stale score against new wording.
      patch(i, { qa: r.qa, graders: r.graders, judge: undefined, state: "ready", note: "",
                 spent: addUsage(it.spent, r.usage), workflow: r.workflow ?? it.workflow });
    } catch (e) {
      patch(i, { state: "error", error: (e as Error).message });
    }
  }

  const approved = items.filter((it) => it.state === "approved" && it.qa);
  const undecided = items.filter((it) => it.state === "ready" || it.state === "loading");
  // "after all accepted then continue" — so nothing may still be waiting on a
  // decision. Skipping is a decision; leaving it open is not.
  const canContinue = approved.length > 0 && undecided.length === 0 && !drafting;

  return (
    <div className="panel wide">
      <h1>Review the narration</h1>
      <p className="lede">
        {material.sections.length} sections · {items.length} question{items.length === 1 ? "" : "s"}.
        Each is explained by a single narrator in 3&ndash;4 connected short parts, written
        using the teaching approach you already approved. Approve the ones that read
        well, regenerate the ones that don&rsquo;t, skip any you don&rsquo;t want. The
        visual plan is reviewed next, once every question here is decided.
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
            : "plans what each beat must show, next"}
        </span>
        <button
          className="primary"
          disabled={!canContinue}
          onClick={() => onDone(approved.map((it) => it.workflow))}
        >
          Continue to visual plan →
        </button>
      </div>
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
  const { topic, qa, graders, judge, state, workflow } = item;
  const failing = graders.filter((g) => !g.passed);
  const approach = effectiveTeachingApproach(workflow);
  // Below 4/5 is the same "must not be weaker" bar config.py documents for the
  // judge role generally — a script this thin on faithfulness is exactly what
  // slipped through review unseen before this warning existed (faithfulness
  // 2/5 on a script built from a headings-only section, approved without a
  // second look because nothing on this card said otherwise).
  const weakJudge = judge && judge.faithfulness < 4;

  return (
    <div className={`card${state === "approved" ? " approved" : ""}${state === "skipped" ? " skipped" : ""}`}>
      <div className="cardhead">
        <div>
          <span className="tag">§{topic.source_section_id}</span>{" "}
          <span className="tag dim">{topic.difficulty}</span>
          {approach && (
            <span className="tag dim" title={approach.rationale || undefined}>
              taught via: {describeApproach(approach)}
            </span>
          )}
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
          {/* ONE NARRATOR, ONE CONNECTED EXPLANATION — not a question-and-answer
              exchange. qa.beats[0] is the opening line; every beat after it
              continues the same narrator's explanation, in speaking order. See
              shorts/schema.py's Script.opening_beat / .body_beats. The topic
              itself (qa.question) is already shown above in .topic/.why —
              this list is the narration that explains it, start to finish. */}
          <div className="qa narration">
            {qa.beats.map((b, k) => (
              <div className="qaline" key={k}>
                <span className="label">{k === 0 ? "Narrates" : ""}</span>
                <span className="avatarcell">
                  {k === 0 ? <Interviewer size={34} /> : <span className="stepdot">{k + 1}</span>}
                </span>
                <span className="body">
                  {b.line}
                  <span className="os">on screen: {b.on_screen}</span>
                  {/* The sentence this beat restates, checked against the section
                      by substring match server-side. Shown so the reviewer can
                      confirm the line against the material without leaving the
                      page — that comparison is the whole job of this step. Never
                      present on the opening beat by design (see checks.py's
                      check_question_grounded, which checks that one instead). */}
                  {b.source_quote && (
                    <span className="cited" title="verified present in the source section">
                      “{b.source_quote}”
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
            {judge && (
              <span
                className={`chip ${weakJudge ? "bad" : "ok"}`}
                title={judge.problems.join(" · ") || "no problems reported"}
              >
                {weakJudge ? "✕" : "✓"} judge: faithfulness {judge.faithfulness}/5,
                clarity {judge.clarity}/5, pace {judge.pace}/5
              </span>
            )}
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
          {/* The code graders above only check that the script is well FORMED —
              length, citations present, no repetition. This is the one signal
              that checks whether it is actually TRUE to the section, and it is
              exactly the thing a reviewer approved blind before this existed:
              a script built from a headings-only section passed every code
              grader and scored faithfulness 2/5 here. */}
          {weakJudge && (
            <div className="error sm">
              <b>Judge flags this as weakly grounded (faithfulness {judge!.faithfulness}/5)</b>
              {judge!.problems.map((p, k) => <div key={k}>{p}</div>)}
            </div>
          )}

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
