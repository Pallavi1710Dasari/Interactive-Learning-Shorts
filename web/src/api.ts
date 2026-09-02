import type { QA, Topic, Unit, GraderResult } from "./types";

// Vite proxies /api to the FastAPI server in dev (see vite.config.ts), and in
// production the same server serves this bundle — so a relative path works in both.
async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await detail(res));
  return res.json();
}

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

export const makeScript = (doc_id: string, topic: Topic) =>
  post<ScriptResult>("/api/script", { doc_id, topic });

export type BatchResult = {
  results: { topic: Topic; qa?: QA; graders?: GraderResult[]; error?: string }[];
  usage: UsageTotals;
  total: UsageTotals;
};

/** Draft every topic in one request; the server runs them concurrently. */
export const makeScripts = (doc_id: string, topics: Topic[]) =>
  post<BatchResult>("/api/scripts", { doc_id, topics });

export const regenerate = (
  doc_id: string,
  topic: Topic,
  instruction: string,
  target: "question" | "answer" | "script",
  /** The script on screen — without it the model rewrites from scratch. */
  qa?: QA,
) =>
  post<{ topic: Topic; qa: QA; graders: GraderResult[]; usage: UsageTotals; total: UsageTotals }>("/api/regenerate", {
    doc_id, topic, instruction, target, qa,
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

export const finalize = (doc_id: string, approved: { topic: Topic; qa: QA }[]) =>
  post<FinalizeResult>("/api/finalize", { doc_id, approved });

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
