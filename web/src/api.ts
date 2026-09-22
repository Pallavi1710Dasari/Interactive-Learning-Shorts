import type { QA, Topic, Unit, GraderResult, QuestionApproval, QuestionWorkflow,
             TeachingApproachKind, WorkflowProgress, Judge } from "./types";

// Vite proxies /api to the FastAPI server in dev (see vite.config.ts), and in
// production the same server serves this bundle — so a relative path works in both.
//
// EVERY CALL HAS A TIMEOUT, and this used to not be true. `fetch` with no
// `signal` waits as long as the browser lets it — which is not "forever" in
// theory, but is far longer than a human waits before assuming the app is
// broken, and a stuck request never rejects, so a caller's `catch` never
// runs. That is exactly what StepBuild.tsx's blank, endlessly-spinning
// "planning the visuals…" screen was: the fetch for /api/workflow/advance or
// /api/finalize hung — a slow model call, a crashed backend, a dropped
// connection — and nothing ever turned `working` false, because nothing
// ever rejected the promise `working` was waiting on. The catch block and the
// Retry button were already there; they just never fired.
//
// DEFAULT_TIMEOUT_MS covers an ordinary single-workflow call (one script
// draft, one regeneration, one approval). `timeoutMs` lets a caller ask for
// longer where that is genuinely not enough — see LONG_TIMEOUT_MS below, for
// calls that do real generation work across several workflows.
const DEFAULT_TIMEOUT_MS = 180_000;

async function post<T>(url: string, body: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(await detail(res));
    return await res.json();
  } catch (e) {
    if ((e as Error).name === "AbortError") {
      throw new Error(
        `${url} did not respond within ${Math.round(timeoutMs / 1000)}s — the ` +
        "server may be slow, stuck, or unreachable. Nothing was lost; retry when ready.");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

//: Batch, multi-stage calls — visual planning, script drafting, and
//: rendering (design + TTS + judge) across every workflow in one request —
//: measured to legitimately take several minutes per short even one at a
//: time (see shorts/tts.py's Chatterbox path, ~2-3 min to load the model
//: alone). DEFAULT_TIMEOUT_MS would abort these mid-flight on a normal run,
//: not just a stuck one.
const LONG_TIMEOUT_MS = 20 * 60_000;

async function detail(res: Response): Promise<string> {
  try {
    const j = await res.json();
    return typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
  } catch {
    return `${res.status} ${res.statusText}`;
  }
}

export type MaterialResult = {
  usage: UsageTotals;
  total: UsageTotals;
  doc_id: string;
  /** Set when the model cited a section that does not exist and it was corrected. */
  notes?: string[];
  sections: { section_id: string; title: string; chars: number; lines: string }[];
  topics: Topic[];
  /** Step 3 — one per topic, each starting `pending`. See StepApprove. */
  workflows: QuestionWorkflow[];
};

/** Step 1 — paste or upload. Multipart so one endpoint serves both. */
export async function submitMaterial(
  input: { text?: string; file?: File; target: number },
): Promise<MaterialResult> {
  const form = new FormData();
  form.set("target", String(input.target));
  if (input.file) form.set("file", input.file);
  else if (input.text) form.set("text", input.text);
  const res = await fetch("/api/material", { method: "POST", body: form });
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export type ScriptResult = {
  topic: Topic;
  section_id: string;
  qa: QA;
  graders: GraderResult[];
  attempts: { attempt: number; graders: GraderResult[] }[];
  usage: UsageTotals;
  total: UsageTotals;
};

/** `approval` is Step 3's gate — omit it and this behaves exactly as before
 *  Step 3 existed. Sent, the server refuses (409) unless it is "approved". */
export const makeScript = (doc_id: string, topic: Topic, approval?: QuestionApproval) =>
  post<ScriptResult>("/api/script", { doc_id, topic, approval });

export type BatchResult = {
  results: { topic: Topic; qa?: QA; graders?: GraderResult[]; error?: string }[];
  usage: UsageTotals;
  total: UsageTotals;
};

/** Draft every topic in one request; the server runs them concurrently.
 *  `approvals` is Step 3's gate, keyed by topic id — see makeScript. */
export const makeScripts = (doc_id: string, topics: Topic[],
                            approvals?: Record<string, QuestionApproval>) =>
  post<BatchResult>("/api/scripts", { doc_id, topics, approvals }, LONG_TIMEOUT_MS);

// ------------------------------------------------- Step 8-9: workflow-aware scripts

export type WorkflowScriptResult = {
  topic: Topic;
  section_id?: string;
  qa?: QA;
  graders?: GraderResult[];
  /** The review-time verdict, present only when the free graders all passed
   *  and JUDGE_AT_REVIEW is on — see server.py's _review_judge. */
  judge?: Judge | null;
  /** Carries the framing and (auto-approved) teaching approach the script
   *  was actually written from — see StepReview, which keeps this per card
   *  so a later regeneration keeps following the same approach. */
  workflow?: QuestionWorkflow;
  error?: string;
};

export type WorkflowBatchResult = {
  results: WorkflowScriptResult[];
  usage: UsageTotals;
  total: UsageTotals;
};

/** Draft a script for every workflow at once, through the WORKFLOW-AWARE
 *  path — framing, a teaching approach, then write_script_for_workflow —
 *  instead of makeScripts's bare write_script. See POST
 *  /api/workflow/scripts for why this is a separate endpoint. */
export const makeWorkflowScripts = (doc_id: string, workflows: QuestionWorkflow[]) =>
  post<WorkflowBatchResult>("/api/workflow/scripts", { doc_id, workflows }, LONG_TIMEOUT_MS);

// ------------------------------------------------- Step 3: question approval gate

/** Approve a workflow as it currently stands (original question, or the
 *  latest regeneration) — see StepApprove. */
export const approveSelection = (doc_id: string, workflow: QuestionWorkflow, note?: string) =>
  post<{ workflow: QuestionWorkflow }>("/api/selections/approve", { doc_id, workflow, note });

export const rejectSelection = (doc_id: string, workflow: QuestionWorkflow, note?: string) =>
  post<{ workflow: QuestionWorkflow }>("/api/selections/reject", { doc_id, workflow, note });

/** Ask the LLM to refine the question's WORDING from a human's reason. There
 *  is no way to send replacement text directly — see QuestionApproval's "NO
 *  DIRECT EDITING" in shorts/schema.py. Always lands back on `pending`. */
export const regenerateSelection = (doc_id: string, workflow: QuestionWorkflow, reason: string) =>
  post<{ workflow: QuestionWorkflow; usage: UsageTotals; total: UsageTotals }>(
    "/api/selections/regenerate", { doc_id, workflow, reason });

// ------------------------------------------------- Step 6: teaching approach gate

/** Approve a workflow's teaching approach — the LLM's recommendation as it
 *  stands (omit `override`), or a human's direct pick of a different
 *  TeachingApproachKind (`override`), with NO extra LLM call either way. See
 *  POST /api/teaching-approach/approve's own `override` field: sending the
 *  same kind as the current recommendation is treated as a plain approve. */
export const approveTeachingApproach = (
  doc_id: string, workflow: QuestionWorkflow, note?: string, override?: TeachingApproachKind,
) =>
  post<{ workflow: QuestionWorkflow }>(
    "/api/teaching-approach/approve", { doc_id, workflow, note, override });

/** Ask the LLM to reconsider the teaching approach from a human's reason.
 *  There is no way to send a replacement primary/combined_with/alternatives/
 *  rationale directly — see TeachingApproachApproval's "NO DIRECT OVERRIDES"
 *  in shorts/schema.py. Always lands back on `pending`. */
export const regenerateTeachingApproach = (doc_id: string, workflow: QuestionWorkflow, reason: string) =>
  post<{ workflow: QuestionWorkflow; usage: UsageTotals; total: UsageTotals }>(
    "/api/teaching-approach/regenerate", { doc_id, workflow, reason });

// ------------------------------------------------------- Step 11: visual plan gate

/** Approve a workflow's visual plan as it currently stands (Step 10's
 *  original plan, or the latest regeneration). */
export const approveVisualPlan = (doc_id: string, workflow: QuestionWorkflow, note?: string) =>
  post<{ workflow: QuestionWorkflow }>("/api/visual-plan/approve", { doc_id, workflow, note });

/** Ask the LLM to reconsider the visual plan from a human's reason. There is
 *  no way to send a replacement subject/beats directly — see
 *  VisualPlanApproval's "NO DIRECT EDITING" in shorts/schema.py. Always
 *  lands back on `pending`. */
export const regenerateVisualPlan = (doc_id: string, workflow: QuestionWorkflow, reason: string) =>
  post<{ workflow: QuestionWorkflow; usage: UsageTotals; total: UsageTotals }>(
    "/api/visual-plan/regenerate", { doc_id, workflow, reason });

// --------------------------------------------------- Step 7: advance workflows

/** shorts/workflow.py's orchestration boundary, over HTTP: advance every
 *  workflow as far as it can go without a human, and report where each one
 *  stopped. Safe to call repeatedly — a workflow already at a stopping point
 *  comes back unchanged, at no extra cost (see WorkflowProgress). */
export const advanceWorkflows = (doc_id: string, workflows: QuestionWorkflow[]) =>
  post<{ results: WorkflowProgress[]; usage: UsageTotals; total: UsageTotals }>(
    "/api/workflow/advance", { doc_id, workflows }, LONG_TIMEOUT_MS);

export const regenerate = (
  doc_id: string,
  topic: Topic,
  instruction: string,
  target: "question" | "answer" | "script",
  /** The script on screen — without it the model rewrites from scratch. */
  qa?: QA,
  /** The workflow this script was drafted from (via makeWorkflowScripts), so
   *  the regeneration keeps following its approved teaching approach too —
   *  omitting it falls back to the plain write_script path. */
  workflow?: QuestionWorkflow,
) =>
  post<{ topic: Topic; qa: QA; graders: GraderResult[]; usage: UsageTotals; total: UsageTotals;
        workflow?: QuestionWorkflow }>("/api/regenerate", {
    doc_id, topic, instruction, target, qa, workflow,
  });

export type FinalizeResult = {
  built: string[];
  failed: { topic_id: string; error: string }[];
  /** Unit graders that failed on a short that was built anyway, by short_id.
   *  These judge the PICTURES, and they run after the money is spent — so a
   *  frame that came back as a slide of its own narration is reported here
   *  rather than throwing the short away. Regenerate the ones worth it. */
  warnings: Record<string, string[]>;
  /** Built, paid for, on disk — and scored under the bar by the judge, so held
   *  out of the reel. `built` counts these; `shorts` does not. Never infer a
   *  failure from `shorts.length === 0` alone: a build can produce nothing
   *  playable with `failed` completely empty, and this is why. */
  quarantined: Unit[];
  shorts: Unit[];
  usage: UsageTotals;
  total: UsageTotals;
};

export const finalize = (
  doc_id: string,
  /** `workflow` carries the human-approved visual plan (and teaching
   *  approach) through to rendering — see POST /api/finalize, which draws
   *  from workflow.approved_visual_strategy instead of silently re-planning
   *  its own when one is present. */
  approved: { topic: Topic; qa: QA; workflow?: QuestionWorkflow }[],
) =>
  post<FinalizeResult>("/api/finalize", { doc_id, approved }, LONG_TIMEOUT_MS);

export type RevisualResult = {
  short: Unit | null;
  /** Design graders still failing after the retries — the reel is watchable anyway. */
  problems: string[];
  warnings: string[];
  usage: UsageTotals;
  total: UsageTotals;
};

/** Redraw ONE short's frames from a free-text note. See POST /api/revisual. */
export const revisual = (short_id: string, instruction: string) =>
  post<RevisualResult>("/api/revisual", { short_id, instruction });

export type RenderJob = {
  short_id: string;
  status: "idle" | "queued" | "rendering" | "done" | "error";
  done: number; total: number; error: string | null;
};

/** Begin (or rejoin) a render. Returns immediately — poll renderStatus. */
export const startRender = (short_id: string) =>
  post<RenderJob>(`/api/video/${encodeURIComponent(short_id)}`, {});

export async function renderStatus(short_id: string): Promise<RenderJob> {
  const res = await fetch(`/api/video/${encodeURIComponent(short_id)}/status`);
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

/** Publish a held short over the judge's verdict. The verdict itself is kept. */
export const release = (short_id: string) =>
  post<{ short: Unit | null }>("/api/release", { short_id });

/** The feed. `held` also returns shorts the judge quarantined — see GET /api/shorts. */
export async function getShorts(held = false): Promise<Unit[]> {
  const res = await fetch(held ? "/api/shorts?held=1" : "/api/shorts");
  if (!res.ok) throw new Error(await detail(res));
  return (await res.json()).shorts;
}

export type UsageTotals = {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  estimated: boolean;
  by_label: Record<string, { calls: number; tokens: number; cost: number }>;
};

export async function getUsage(): Promise<UsageTotals> {
  const res = await fetch("/api/usage");
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

export async function getHealth() {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(await detail(res));
  return res.json() as Promise<{
    ok: boolean; stub: boolean; model: string; judge: string; units: number;
    total: UsageTotals;
  }>;
}
