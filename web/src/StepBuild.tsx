import { useEffect, useRef, useState } from "react";
import { advanceWorkflows, approveVisualPlan, finalize, release,
         type MaterialResult, type UsageTotals } from "./api";
import { Spinner } from "./Spinner";
import { approvedTopic, scriptToQA, type QuestionWorkflow, type Unit } from "./types";

/**
 * The automatic stage between script approval and the finished reel: plan
 * the visual strategy, approve it, and render — with NO human wait.
 *
 * RENDERS AS A FIXED BAR, NOT A PAGE — see the `buildbar` wrapper in the
 * return below. App.tsx keeps StepReview mounted (locked) underneath while
 * this runs, so progress shows on the page the reviewer was already reading
 * instead of behind a blank full-screen replacement, and `onDone` jumps
 * straight from here to the reel with nothing in between.
 *
 * WHY THIS IS NOT A HUMAN GATE, UNLIKE QUESTION AND TEACHING-APPROACH
 * APPROVAL. The product wants exactly two human decisions in the normal
 * flow: which question, and how to teach it. Once those are made, the
 * visual plan and the render are the system carrying out a decision that
 * was already approved, not a new decision that needs its own review — see
 * shorts/skills/strategy.py's plan_strategy_for_workflow, which already
 * threads the human-approved teaching approach into what it plans, the same
 * way write_script_for_workflow does for the script.
 *
 * REUSES THE EXACT SAME BACKEND CALLS A HUMAN-REVIEWED SCREEN WOULD — this
 * is the important part. POST /api/workflow/advance generates the strategy
 * (shorts/workflow.py's advance(), unchanged), POST /api/visual-plan/approve
 * satisfies the same gate design_visuals reads at render time
 * (workflow.approved_visual_strategy — see server.py's /api/finalize), and
 * POST /api/finalize renders. No new generation logic, no duplicated gate —
 * only the human click in between is gone. The approve/regenerate
 * visual-plan endpoints are untouched and still directly callable, for
 * debugging or a future opt-in review screen.
 *
 * PARTIAL FAILURE IS PER-WORKFLOW, NOT BATCH-FATAL — same principle as
 * StepReview and the old StepVisualPlan: one workflow whose visual planning
 * or rendering fails must not lose the reels that succeeded.
 */
export function StepBuild({
  material, workflows, onDone, onSpend, onWatchHeld,
}: {
  material: MaterialResult;
  /** Step 8's output — each already has an approved teaching approach and a
   *  human-approved script (workflow.script). */
  workflows: QuestionWorkflow[];
  onDone: (shorts: Unit[]) => void;
  onSpend: (delta: UsageTotals, total: UsageTotals) => void;
  onWatchHeld: (short_id: string) => void;
}) {
  const [phase, setPhase] = useState<"planning" | "rendering" | "done">("planning");
  const [skipped, setSkipped] = useState<string[]>([]);
  const [buildError, setBuildError] = useState<string | null>(null);
  const [buildWarnings, setBuildWarnings] = useState<string[]>([]);
  const [held, setHeld] = useState<Unit[]>([]);
  const [released, setReleased] = useState<string[]>([]);
  const [releaseErr, setReleaseErr] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  // TWO SEPARATE REFS, ON PURPOSE — see StepReview.tsx's identical pair for
  // the full reasoning. `startedFor` gates whether the multi-stage run (visual
  // strategy, approval, AND /api/finalize — diagrams + judge + voice, the most
  // expensive stage in the whole pipeline) is ever STARTED for a given
  // `attempt` — set once per attempt, never reset for that same attempt, so
  // StrictMode's double-mount in dev cannot start it twice. Keyed by
  // `attempt`, not a bare boolean, so the Retry button (which bumps
  // `attempt`) still starts a genuinely new run. `mounted` tracks whether
  // THIS component instance is *currently* on screen, and is reset on EVERY
  // effect invocation — so it correctly reads `true` again by the time the
  // one real run's `await`s resolve, even though StrictMode's synchronous
  // mount -> cleanup -> remount cycle runs (and its cleanup fires) before any
  // of them settle. A single `alive` local variable captured only by the
  // FIRST invocation's closure could not recover from that cleanup — every
  // stage's result was silently discarded and the build screen never left
  // "planning".
  const startedFor = useRef<number | null>(null);
  const mounted = useRef(false);

  useEffect(() => {
    mounted.current = true;
    if (startedFor.current !== attempt) {
      startedFor.current = attempt;
      (async () => {
        setPhase("planning");
        setSkipped([]);
        setBuildError(null);
        try {
          // 1. Plan the visual strategy for every workflow — advance() sees
          //    each already has a script, so this is the one thing left to
          //    generate before rendering.
          const adv = await advanceWorkflows(material.doc_id, workflows);
          if (!mounted.current) return;
          onSpend(adv.usage, adv.total);

          const ok: QuestionWorkflow[] = [];
          const failedNotes: string[] = [];
          for (const wf of workflows) {
            const hit = adv.results.find(
              (x) => x.workflow.selection.topic.id === wf.selection.topic.id);
            if (hit && hit.status !== "visual_plan_failed" && hit.status !== "script_failed") {
              ok.push(hit.workflow);
            } else {
              failedNotes.push(`${wf.selection.topic.id}: ${hit?.detail ?? "visual planning failed"}`);
            }
          }
          setSkipped(failedNotes);
          if (!ok.length) throw new Error(failedNotes.join("; ") || "no visual plan could be generated");

          // 2. Approve each plan automatically — no human wait in the normal
          //    flow. shorts/review.approve_visual_plan, unchanged, 0 LLM calls.
          const approvals = await Promise.allSettled(
            ok.map((wf) => approveVisualPlan(material.doc_id, wf)));
          const approved: QuestionWorkflow[] = [];
          approvals.forEach((res, i) => {
            if (res.status === "fulfilled") approved.push(res.value.workflow);
            else setSkipped((prev) => [...prev, `${ok[i].selection.topic.id}: ${res.reason}`]);
          });
          if (!mounted.current) return;
          if (!approved.length) throw new Error("no visual plan could be approved");

          // 3. Render.
          setPhase("rendering");
          const r = await finalize(material.doc_id, approved.map((wf) => ({
            topic: approvedTopic(wf) ?? wf.selection.topic,
            qa: scriptToQA(wf.script!),
            workflow: wf,
          })));
          if (!mounted.current) return;
          onSpend(r.usage, r.total);
          if (r.failed.length) {
            setSkipped((prev) => [...prev, ...r.failed.map((f) => `${f.topic_id}: ${f.error}`)]);
          }
          setBuildWarnings(
            Object.entries(r.warnings ?? {}).map(([id, ws]) => `${id} — ${ws.join("; ")}`));
          setHeld(r.quarantined ?? []);
          setPhase("done");

          // Only leave this screen if there is something to watch — a run
          // where every short was quarantined must not unmount the reasons.
          if (r.shorts.length) onDone(r.shorts);
        } catch (e) {
          if (!mounted.current) return;
          setBuildError((e as Error).message);
          setPhase("done");
        }
      })();
    }
    return () => { mounted.current = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const working = phase !== "done";

  // A FIXED BAR OVER THE (LOCKED) REVIEW SCREEN, NOT A PAGE OF ITS OWN. This
  // used to be `<div className="center">` — a full-screen replacement of
  // StepReview with nothing on it but a spinner, which read as an empty page
  // between approving the script and seeing the reel. App.tsx now keeps
  // StepReview mounted underneath (locked, not unmounted) while this runs, so
  // the loading state shows on the page the reviewer was already looking at,
  // and `onDone` above still jumps straight from here to the reel — there was
  // never a real "building" page to remove, only this component's own layout.
  return (
    <div className="buildbar">
      <div>
        {working && (
          <Spinner label={
            phase === "planning"
              ? `Planning the visuals for ${workflows.length} short${workflows.length === 1 ? "" : "s"}…`
              : "Drawing diagrams, recording narration & grading…"
          } />
        )}
        {/* Reachable in two cases: a clean success, for the instant before
            onDone (above) unmounts this screen for the reel view — harmless —
            or FinalizeResult coming back completely empty (built nothing,
            nothing failed, nothing held, no warnings), which used to leave
            this exact text sitting on screen forever with no spinner and no
            way forward. That is the other half of "blank/loading" this fixes:
            not every stuck screen is a hung request (see api.ts's timeout);
            this one is a response that arrived and said nothing happened. */}
        {!working && !buildError && !held.length && !buildWarnings.length && (
          <>
            <p className="lede">Building the reel…</p>
            {skipped.length === 0 && (
              <>
                <div className="error">
                  Nothing was built or reported — the server returned an empty result.
                </div>
                <button className="ghost" onClick={() => setAttempt((a) => a + 1)}>Retry →</button>
              </>
            )}
          </>
        )}
        {buildError && (
          <>
            <b>Nothing could be built</b>
            <div className="error">{buildError}</div>
            <button className="ghost" onClick={() => setAttempt((a) => a + 1)}>Retry →</button>
          </>
        )}
        {skipped.length > 0 && (
          <div className="warn">
            <b>{skipped.length} short{skipped.length === 1 ? "" : "s"} skipped</b>
            {skipped.map((s, i) => <span key={i}>{s}</span>)}
          </div>
        )}
        {held.length > 0 && (
          <div className="warn">
            <b>
              {held.length} short{held.length === 1 ? " was" : "s were"} built but held
              out of the reel — the judge scored {held.length === 1 ? "it" : "them"} under the bar
            </b>
            <span>
              {held.length === 1 ? "It is" : "They are"} on disk with the verdict attached.
              Watch {held.length === 1 ? "it" : "them"} and redraw the pictures from a
              note on the reel itself, or leave {held.length === 1 ? "it" : "them"} —
              nothing is lost.
            </span>
            {held.map((u) => (
              <span key={u.short_id}>
                <b>{u.short_id}</b>
                {u.judge && ` — faithfulness ${u.judge.faithfulness}/5, clarity ${u.judge.clarity}/5, pace ${u.judge.pace}/5`}
                {u.judge?.problems?.length ? `: ${u.judge.problems.join(" · ")}` : ""}
                {" "}
                <button className="ghost sm" onClick={() => onWatchHeld(u.short_id)}>
                  Watch it →
                </button>
                {" "}
                {released.includes(u.short_id)
                  ? <em>published — it is in the reel now</em>
                  : (
                    <button
                      className="ghost sm"
                      title="publish it anyway; the judge's verdict is kept on the short"
                      onClick={() => {
                        setReleaseErr(null);
                        release(u.short_id)
                          .then(() => setReleased((r) => [...r, u.short_id]))
                          .catch((e) => setReleaseErr((e as Error).message));
                      }}>
                      Publish anyway
                    </button>
                  )}
              </span>
            ))}
            {releaseErr && <span className="error">{releaseErr}</span>}
          </div>
        )}
        {buildWarnings.length > 0 && (
          <div className="warn">
            <b>Built, but the diagrams need work</b>
            {buildWarnings.map((w, i) => <span key={i}>{w}</span>)}
          </div>
        )}
      </div>
    </div>
  );
}
