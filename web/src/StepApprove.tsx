import { useState } from "react";
import { approveSelection, rejectSelection, regenerateSelection,
         type MaterialResult, type UsageTotals } from "./api";
import { Spinner } from "./Spinner";
import { effectiveQuestion, type QuestionWorkflow } from "./types";

/**
 * Step 2 — Step 3 of the question workflow: approve, reject, or request an
 * LLM regeneration of each candidate QUESTION, before a single script is
 * drafted for any of them.
 *
 * THIS RUNS BEFORE StepReview NOW, NOT INSIDE IT. StepReview used to call
 * makeScripts the instant it mounted — every candidate question got a drafted
 * script whether or not a human had looked at it yet. That is the expensive
 * work Step 3 exists to gate: nothing here costs more than one cheap
 * regenerate call, and StepReview (unchanged) only ever sees the topics that
 * were actually approved.
 *
 * NO DIRECT EDITING. There is deliberately no text field for the question
 * itself — see shorts/schema.py's QuestionApproval "NO DIRECT EDITING". A
 * human who wants different wording explains what should change; the LLM
 * rewrites it, grounded in the same section, and it always comes back
 * `pending` for another look.
 */
export function StepApprove({
  material, onDone, onSpend,
}: {
  material: MaterialResult;
  onDone: (workflows: QuestionWorkflow[]) => void;
  onSpend: (delta: UsageTotals, total: UsageTotals) => void;
}) {
  const [items, setItems] = useState<QuestionWorkflow[]>(material.workflows);
  const [busy, setBusy] = useState<number | null>(null);
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [showReason, setShowReason] = useState<number | null>(null);

  const patch = (i: number, wf: QuestionWorkflow) =>
    setItems((prev) => prev.map((it, k) => (k === i ? wf : it)));
  const patchError = (i: number, msg: string | null) =>
    setErrors((prev) => {
      const next = { ...prev };
      if (msg) next[i] = msg; else delete next[i];
      return next;
    });

  async function approve(i: number) {
    setBusy(i);
    patchError(i, null);
    try {
      const r = await approveSelection(material.doc_id, items[i]);
      patch(i, r.workflow);
    } catch (e) {
      patchError(i, (e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function reject(i: number) {
    setBusy(i);
    patchError(i, null);
    try {
      const r = await rejectSelection(material.doc_id, items[i]);
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
      const r = await regenerateSelection(material.doc_id, items[i], reason);
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

  const approved = items.filter((it) => it.question_approval.status === "approved");
  const pending = items.filter((it) => it.question_approval.status === "pending");
  const canContinue = approved.length > 0 && pending.length === 0;

  return (
    <div className="panel wide">
      <h1>Review the questions</h1>
      <p className="lede">
        {items.length} candidate question{items.length === 1 ? "" : "s"}, each shown with
        where it came from and why it was picked. Approve the ones worth a script,
        reject the rest, or ask for a sharper version of the wording — nobody types a
        question by hand here, so every one stays grounded in the material.
      </p>

      {items.map((it, i) => (
        <ApproveCard
          key={it.selection.topic.id}
          workflow={it}
          busy={busy === i}
          error={errors[i]}
          reason={reasons[i] ?? ""}
          showReason={showReason === i}
          onReason={(v) => setReasons((prev) => ({ ...prev, [i]: v }))}
          onToggleReason={() => setShowReason(showReason === i ? null : i)}
          onApprove={() => approve(i)}
          onReject={() => reject(i)}
          onRegenerate={() => requestRegeneration(i)}
        />
      ))}

      <div className="sticky">
        <span>
          <b>{approved.length}</b> approved
          {pending.length > 0 && `, ${pending.length} still to decide`}
        </span>
        <span className="spacer" />
        <span className="hintline">
          {pending.length > 0
            ? "approve or reject every question first"
            : "decides how to teach each approved question, next"}
        </span>
        <button
          className="primary"
          disabled={!canContinue}
          onClick={() => onDone(approved)}
        >
          Continue to teaching approach →
        </button>
      </div>
    </div>
  );
}

function ApproveCard({
  workflow, busy, error, reason, showReason,
  onReason, onToggleReason, onApprove, onReject, onRegenerate,
}: {
  workflow: QuestionWorkflow;
  busy: boolean;
  error?: string;
  reason: string;
  showReason: boolean;
  onReason: (v: string) => void;
  onToggleReason: () => void;
  onApprove: () => void;
  onReject: () => void;
  onRegenerate: () => void;
}) {
  const { selection, question_approval: qa } = workflow;
  const { topic } = selection;
  const effective = effectiveQuestion(workflow);
  const attempts = qa.regeneration_history.length;
  // ONE plain-language line on why this is worth teaching — not the full
  // selection-pipeline breakdown (importance/concrete_and_answerable/
  // distinct_angle/...). Prefer the reason actually about importance; any
  // reason at all beats none. The full breakdown is still one click away,
  // in <details> below, for debugging — never shown by default.
  // FILTERED HERE TOO, NOT JUST IN THE SCHEMA. schema.py's QuestionSelection
  // validator now drops blank-explanation reasons before they ever leave the
  // server, but a workflow object can also arrive here from a REGENERATE
  // round-trip or from state a browser tab held onto from before that fix —
  // this is the belt to that braces, so a blank reason can never render as
  // an empty bullet with nothing but a category tag in it.
  const realReasons = selection.reasons.filter((r) => r.explanation && r.explanation.trim());
  const topReasonObj = realReasons.find((r) => r.category === "importance") ?? realReasons[0];
  const topReason = topReasonObj?.explanation;
  // EXCLUDED FROM THE EXPANDED LIST BELOW, not just shown above it. This used
  // to render the exact same reason object twice — once as this one-line
  // summary, once again as its own bullet in "Why this question was
  // selected" — which read as the panel repeating itself before a reviewer
  // even got to a genuinely different reason.
  const otherReasons = realReasons.filter((r) => r !== topReasonObj);

  return (
    <div className={`card${qa.status === "approved" ? " approved" : ""}${qa.status === "rejected" ? " skipped" : ""}`}>
      <div className="cardhead">
        <div>
          <div className="qlabel">Question</div>
          <div className="topic">{effective}</div>
          {effective !== topic.topic && <div className="why">originally: {topic.topic}</div>}

          <div className="qlabel">Learning outcome / topic</div>
          <div className="outcome">{topic.why_it_matters}</div>
          <div className="why">
            <span className="tag dim">§{topic.source_section_id}</span>{" "}
            {selection.source_title}
          </div>

          {topReason && <div className="why onereason">{topReason}</div>}
          {attempts > 0 && (
            <div className="why">{attempts} regeneration{attempts === 1 ? "" : "s"} so far</div>
          )}

          {otherReasons.length > 0 && (
            <details className="advanced">
              <summary>Why this question was selected</summary>
              <ul className="reasons">
                {otherReasons.map((r, k) => (
                  <li key={k}><span className="tag dim">{r.category}</span> {r.explanation}</li>
                ))}
              </ul>
            </details>
          )}
        </div>
        <div className="cardactions">
          {busy ? <Spinner label="working…" /> : (
            <>
              {qa.status !== "approved" && (
                <button className="primary sm" onClick={onApprove}>Approve</button>
              )}
              {qa.status !== "rejected" && (
                <button className="ghost sm" onClick={onReject}>Reject</button>
              )}
              <button className="ghost sm" onClick={onToggleReason}>Request regeneration</button>
            </>
          )}
        </div>
      </div>

      {showReason && !busy && (
        <div className="redo">
          <input
            className="note"
            placeholder="What should improve? e.g. “too broad — focus on the mechanism”"
            value={reason}
            onChange={(e) => onReason(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") onRegenerate(); }}
          />
          <button className="ghost" onClick={onRegenerate}>↻ Regenerate</button>
        </div>
      )}

      {error && <div className="error sm">{error}</div>}
      <div className="graders">
        <span className={`chip ${qa.status === "approved" ? "ok" : qa.status === "rejected" ? "bad" : "dim"}`}>
          {qa.status}
        </span>
      </div>
    </div>
  );
}
