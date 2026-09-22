import { useEffect, useRef, useState } from "react";
import { advanceWorkflows, approveTeachingApproach, regenerateTeachingApproach,
         type MaterialResult, type UsageTotals } from "./api";
import { Spinner } from "./Spinner";
import { describeApproach, describeApproachKind, llmRecommendedApproach,
         TEACHING_APPROACH_KINDS, type QuestionWorkflow, type TeachingApproachKind } from "./types";

/**
 * Step 5-6 of the question workflow: the AI recommends a teaching approach
 * for each approved question, and a human approves it — either as
 * recommended, or by picking a different one directly — BEFORE any script
 * is written.
 *
 * THE AI'S DECISION AND THE HUMAN'S APPROVAL ARE TWO DIFFERENT CALLS, NEVER
 * ONE. Mounting this screen calls POST /api/workflow/advance — the existing
 * orchestrator (shorts/workflow.py's advance()) — which generates framing and
 * a recommended TeachingApproach and then STOPS on its own; it never
 * approves anything. No script is drafted on this screen — see StepReview,
 * which only runs after every workflow here reaches "approved".
 *
 * THREE WAYS TO REACH "approved", ALL EXISTING SERVER LOGIC:
 *   - Approve, untouched picker -> POST /api/teaching-approach/approve with
 *     no `override` — keeps whatever the AI currently recommends.
 *   - Approve, picker moved to a different device -> the SAME endpoint with
 *     `override` set — shorts/review.select_teaching_approach writes the
 *     human's direct choice and approves it, with NO extra LLM call.
 *   - Regenerate with a reason -> POST /api/teaching-approach/regenerate —
 *     asks the LLM to reconsider. The fresh recommendation becomes the
 *     picker's new default (regeneration clears any prior direct pick
 *     server-side — see TeachingApproachApproval.override's own docstring),
 *     and the human can still pick a different device before approving.
 */
export function StepTeachingApproach({
  material, workflows, onDone, onSpend,
}: {
  material: MaterialResult;
  /** Step 3's gate output — approved questions, not yet framed or taught. */
  workflows: QuestionWorkflow[];
  onDone: (workflows: QuestionWorkflow[]) => void;
  onSpend: (delta: UsageTotals, total: UsageTotals) => void;
}) {
  const [items, setItems] = useState<QuestionWorkflow[]>(workflows);
  const [busy, setBusy] = useState<number | null>(null);
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [showReason, setShowReason] = useState<number | null>(null);
  const [deciding, setDeciding] = useState(true);

  const patch = (i: number, wf: QuestionWorkflow) =>
    setItems((prev) => prev.map((it, k) => (k === i ? wf : it)));
  const patchError = (i: number, msg: string | null) =>
    setErrors((prev) => {
      const next = { ...prev };
      if (msg) next[i] = msg; else delete next[i];
      return next;
    });

  // AI DECIDES, ONCE, FOR EVERY APPROVED QUESTION AT ONCE. One batched call
  // to the SAME orchestrator that will later generate the script and the
  // visual plan — no separate agent, no logic duplicated from
  // shorts/workflow.py. advance() stops itself the instant a teaching
  // approach exists but has not been approved; it can never skip past this
  // screen on its own.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const r = await advanceWorkflows(material.doc_id, workflows);
        if (!alive) return;
        onSpend(r.usage, r.total);
        setItems((prev) => prev.map((it, i) => {
          const hit = r.results.find(
            (x) => x.workflow.selection.topic.id === it.selection.topic.id);
          if (!hit) return it;
          if (hit.status === "teaching_approach_failed" || hit.status === "framing_failed") {
            patchError(i, hit.detail);
          }
          return hit.workflow;
        }));
      } catch (e) {
        if (!alive) return;
        const msg = (e as Error).message;
        setItems((prev) => {
          prev.forEach((_, i) => patchError(i, msg));
          return prev;
        });
      } finally {
        if (alive) setDeciding(false);
      }
    })();
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function retryDecision(i: number) {
    setBusy(i);
    patchError(i, null);
    try {
      const r = await advanceWorkflows(material.doc_id, [items[i]]);
      onSpend(r.usage, r.total);
      const hit = r.results[0];
      if (hit) {
        if (hit.status === "teaching_approach_failed" || hit.status === "framing_failed") {
          patchError(i, hit.detail);
        }
        patch(i, hit.workflow);
      }
    } catch (e) {
      patchError(i, (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  /** `chosen` is whatever the picker currently shows — the recommendation,
   *  untouched, or a device the reviewer picked instead. The server (not
   *  this function) decides whether that is a plain approve or a direct
   *  selection, by comparing it against the workflow's own recommendation —
   *  see POST /api/teaching-approach/approve's `override` field. */
  async function approve(i: number, chosen: TeachingApproachKind) {
    setBusy(i);
    patchError(i, null);
    try {
      const r = await approveTeachingApproach(material.doc_id, items[i], undefined, chosen);
      patch(i, r.workflow);
    } catch (e) {
      patchError(i, (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function requestRegeneration(i: number) {
    const reason = (reasons[i] ?? "").trim();
    if (!reason) return patchError(i, "Say what should improve first.");
    setBusy(i);
    patchError(i, null);
    try {
      const r = await regenerateTeachingApproach(material.doc_id, items[i], reason);
      onSpend(r.usage, r.total);
      patch(i, r.workflow);
      setReasons((prev) => ({ ...prev, [i]: "" }));
      setShowReason(null);
    } catch (e) {
      patchError(i, (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const approved = items.filter((it) => it.teaching_approach_approval.status === "approved");
  const canContinue = !deciding && approved.length > 0 && approved.length === items.length;

  return (
    <div className="panel wide">
      <h1>Review the teaching approach</h1>
      <p className="lede">
        For each approved question, the AI picked how it should actually be taught —
        an analogy, a real-world example, a walkthrough of a process, a comparison, or
        a plain explanation. Approve the recommendation, pick a different approach
        yourself, or ask the AI to reconsider. Nothing is scripted until you approve
        what is shown here.
      </p>

      {deciding && (
        <div className="drafting">
          <Spinner label={`Deciding how to teach ${items.length} question${items.length === 1 ? "" : "s"}…`} />
        </div>
      )}

      {items.map((it, i) => (
        <ApproachCard
          key={it.selection.topic.id}
          workflow={it}
          busy={busy === i}
          error={errors[i]}
          reason={reasons[i] ?? ""}
          showReason={showReason === i}
          onReason={(v) => setReasons((prev) => ({ ...prev, [i]: v }))}
          onToggleReason={() => setShowReason(showReason === i ? null : i)}
          onApprove={(chosen) => approve(i, chosen)}
          onRegenerate={() => requestRegeneration(i)}
          onRetryDecision={() => retryDecision(i)}
        />
      ))}

      <div className="sticky">
        <span>
          <b>{approved.length}</b> approved
          {items.length - approved.length > 0 && `, ${items.length - approved.length} still to decide`}
        </span>
        <span className="spacer" />
        <span className="hintline">
          {approved.length < items.length
            ? "approve or regenerate every teaching approach first"
            : "writes each script using the approved approach"}
        </span>
        <button className="primary" disabled={!canContinue} onClick={() => onDone(approved)}>
          Continue to scripts →
        </button>
      </div>
    </div>
  );
}

function ApproachCard({
  workflow, busy, error, reason, showReason,
  onReason, onToggleReason, onApprove, onRegenerate, onRetryDecision,
}: {
  workflow: QuestionWorkflow;
  busy: boolean;
  error?: string;
  reason: string;
  showReason: boolean;
  onReason: (v: string) => void;
  onToggleReason: () => void;
  onApprove: (chosen: TeachingApproachKind) => void;
  onRegenerate: () => void;
  onRetryDecision: () => void;
}) {
  const { framing, teaching_approach_approval: ta } = workflow;
  // The AI's OWN current recommendation — the latest regeneration, else its
  // original decision — never a prior human pick. This is what "Recommended
  // teaching approach" shows and what the picker defaults to.
  const recommended = llmRecommendedApproach(workflow);

  // HOOKS BEFORE THE EARLY RETURN BELOW — not a style preference. This card
  // stays mounted across the "still deciding" -> "has a recommendation"
  // transition (the parent patches the same list index in place), so a hook
  // called only in the branch that HAS a recommendation would change this
  // component's hook count between renders and break React's own
  // bookkeeping. `selected` starts at any fixed placeholder — it is never
  // rendered until `recommended` exists — and the effect snaps it to the
  // real recommendation the moment one exists, and again every time a
  // regeneration replaces it, without needing a remount.
  const [selected, setSelected] = useState<TeachingApproachKind>(
    recommended?.primary ?? "direct_explanation");
  const lastSeen = useRef<TeachingApproachKind | undefined>(recommended?.primary);
  useEffect(() => {
    if (recommended && recommended.primary !== lastSeen.current) {
      lastSeen.current = recommended.primary;
      setSelected(recommended.primary);
    }
  }, [recommended]);

  // STILL DECIDING (or the decision failed) — no framing/recommendation yet.
  if (!recommended || !framing) {
    return (
      <div className="card">
        <div className="cardhead">
          <div>
            <div className="qlabel">What are we teaching?</div>
            <div className="topic">{workflow.selection.topic.topic}</div>
          </div>
          <div className="cardactions">
            {error
              ? <button className="ghost sm" disabled={busy} onClick={onRetryDecision}>
                  {busy ? <Spinner label="retrying…" /> : "Retry"}
                </button>
              : <Spinner label="deciding…" />}
          </div>
        </div>
        {error && <div className="error sm">{error}</div>}
      </div>
    );
  }

  const attempts = ta.regeneration_history.length;
  const locked = ta.status === "approved" || busy;

  return (
    <div className={`card${ta.status === "approved" ? " approved" : ""}`}>
      <div className="cardhead">
        <div>
          <div className="qlabel">What are we teaching?</div>
          <div className="topic">{framing.teaching_question}</div>

          <div className="qlabel">How does the AI recommend teaching it?</div>
          <div className="outcome">{describeApproach(recommended)}</div>

          {attempts > 0 && (
            <div className="why">{attempts} regeneration{attempts === 1 ? "" : "s"} so far</div>
          )}
        </div>
        <div className="cardactions">
          {busy ? <Spinner label="working…" /> : (
            <>
              {ta.status !== "approved" && (
                <button className="primary sm" onClick={() => onApprove(selected)}>
                  Approve selected approach
                </button>
              )}
              <button className="ghost sm" onClick={onToggleReason}>Request regeneration</button>
            </>
          )}
        </div>
      </div>

      <div className="qlabel">Choose the teaching approach</div>
      <div className="approachpicker">
        {TEACHING_APPROACH_KINDS.map((kind) => (
          <button
            key={kind}
            type="button"
            className={`pill${selected === kind ? " on" : ""}`}
            disabled={locked}
            onClick={() => setSelected(kind)}
            title={kind === recommended.primary ? "the AI's recommendation" : undefined}
          >
            {describeApproachKind(kind)}
            {kind === recommended.primary && <span className="pilltag">recommended</span>}
          </button>
        ))}
      </div>

      {recommended.rationale && (
        <>
          <div className="qlabel">Why did the AI recommend this?</div>
          <div className="why">{recommended.rationale}</div>
        </>
      )}

      {showReason && !busy && (
        <div className="redo">
          <input
            className="note"
            placeholder="What should improve? e.g. “this needs a worked example, not just an explanation”"
            value={reason}
            onChange={(e) => onReason(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") onRegenerate(); }}
          />
          <button className="ghost" onClick={onRegenerate}>↻ Regenerate</button>
        </div>
      )}

      {error && <div className="error sm">{error}</div>}
      <div className="graders">
        <span className={`chip ${ta.status === "approved" ? "ok" : "dim"}`}>
          {ta.status === "approved" ? `approved · ${describeApproachKind(selected)}` : ta.status}
        </span>
      </div>
    </div>
  );
}
