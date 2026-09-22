// Mirrors the payloads shorts/server.py and shorts/feed.py produce. If you add a
// field there, add it here — the app fetches these shapes at runtime, so a
// mismatch shows up as an empty panel rather than a compile error.

/** One word of the narration, with the moment it is spoken. */
export type CaptionWord = { w: string; s: number; e: number };

export type Beat = {
  /** Always "narrator" now — one voice for the whole reel. Kept as a plain
   *  string, not a union, because units saved before this change still carry
   *  the old "interviewer" / "student" values and still have to load. Nothing
   *  in the app keys behaviour off this value any more; see shorts/schema.py's
   *  Beat.speaker for the full story. */
  speaker: string;
  line: string;
  on_screen: string;
  visual_ref: string;
  /** Word-by-word timings for the flowing caption. See shorts/feed.py. */
  words?: CaptionWord[];
  /** The sentence of the source this beat restates; never present on the
   *  opening beat (index 0). */
  source_quote?: string | null;
  /** Inline SVG, already stripped of <script> and on* handlers in Python. */
  svg?: string | null;
  start?: number;
  end?: number;
};

/** A beat as it comes back inside a reel payload — timings always present. */
export type ReelBeat = Beat & {
  svg: string | null; start: number; end: number; words: CaptionWord[];
};

export type Topic = {
  id: string;
  topic: string;
  why_it_matters: string;
  source_section_id: string;
  difficulty: "easy" | "medium" | "hard";
  importance?: number | null;
  concept?: string | null;
  answer_quote?: string | null;
  /** Selection's own cross-candidate comparison: does another selected
   *  concept in this material depend on this one first? See shorts/
   *  skills/select.py's SYSTEM prompt and Topic.is_foundational. */
  is_foundational?: boolean | null;
  foundational_note?: string | null;
};

/** Step 3 — one structured reason a question was selected. See
 *  shorts/schema.py's SelectionReason. */
export type SelectionReason = {
  category: "importance" | "foundational" | "commonly_confused" |
            "concrete_and_answerable" | "distinct_angle" |
            "candidate_comparison" | "other";
  explanation: string;
};

/** Why one candidate question was surfaced, before any teaching decision. */
export type QuestionSelection = {
  topic: Topic;
  source_title: string;
  reasons: SelectionReason[];
};

/** One completed LLM regeneration of a question. The human only ever supplies
 *  `reason` — see shorts/schema.py's RegenerationAttempt / QuestionApproval
 *  "NO DIRECT EDITING". */
export type RegenerationAttempt = {
  reason: string;
  previous_question: string;
  regenerated_question: string;
};

export type QuestionApproval = {
  status: "pending" | "approved" | "rejected" | "regenerating";
  note?: string | null;
  /** Legacy — Step 3's own UI never sets this. */
  edited_question?: string | null;
  regenerated_question?: string | null;
  regeneration_history: RegenerationAttempt[];
};

/** Step 4 — how the approved question is actually put to the student.
 *  source_question is set deterministically server-side (see
 *  shorts/skills/framing.py) — never something the LLM or this UI writes. */
export type QuestionFraming = {
  source_question: string;
  teaching_question: string;
  framing_rationale?: string | null;
  role: "primary" | "hook" | "reinforcement" | "misconception_check" | "transition";
};

/** Step 5 — the pedagogical device. See shorts/schema.py's
 *  TeachingApproachKind; `primary` has no default on the Python side either,
 *  so there is no sensible placeholder value to default it to here. */
export type TeachingApproachKind =
  "analogy" | "real_world_example" | "code" | "conceptual_visual" |
  "process_demonstration" | "comparison" | "direct_explanation";

/** Every fixed device a human can pick directly on the teaching-approach
 *  review screen — see StepTeachingApproach.tsx. Not derived from any one
 *  workflow's `alternatives`: the picker always offers the full fixed set
 *  shorts/schema.py's TeachingApproachKind defines, the same seven the LLM
 *  itself chooses from. */
export const TEACHING_APPROACH_KINDS: TeachingApproachKind[] = [
  "conceptual_visual", "process_demonstration", "comparison", "analogy",
  "real_world_example", "code", "direct_explanation",
];

export type TeachingApproach = {
  primary: TeachingApproachKind;
  combined_with: TeachingApproachKind[];
  alternatives: TeachingApproachKind[];
  rationale: string;
};

/** "process_demonstration" -> "process demonstration". Human-facing label,
 *  never the raw enum value — used by StepTeachingApproach and StepReview's
 *  own small "taught via" chip. */
export function describeApproachKind(kind: TeachingApproachKind): string {
  return kind.replace(/_/g, " ");
}

/** "Process demonstration, combined with conceptual visual" — the one-line
 *  human-facing summary of a TeachingApproach. No rubric, no scores. */
export function describeApproach(approach: TeachingApproach): string {
  const line = describeApproachKind(approach.primary);
  return approach.combined_with.length
    ? `${line}, combined with ${approach.combined_with.map(describeApproachKind).join(", ")}`
    : line;
}

/** Step 6 — one completed LLM reconsideration of a TeachingApproach. Always a
 *  COMPLETE decision, never a patch to one field — see
 *  shorts/schema.py's TeachingApproachRegenerationAttempt. */
export type TeachingApproachRegenerationAttempt = {
  reason: string;
  previous_approach: TeachingApproach;
  regenerated_approach: TeachingApproach;
};

export type TeachingApproachApproval = {
  status: "pending" | "approved" | "modified" | "regenerating";
  note?: string | null;
  /** A human's direct pick of a different TeachingApproachKind, written (and
   *  approved) by POST /api/teaching-approach/approve's `override` field —
   *  see shorts/review.select_teaching_approach. Cleared by every
   *  regeneration; see effectiveTeachingApproach's own priority order. */
  override?: TeachingApproach | null;
  regenerated_approach?: TeachingApproach | null;
  regeneration_history: TeachingApproachRegenerationAttempt[];
};

/** Step 10 — what ONE beat's frame has to make a viewer see, decided before
 *  any template. See shorts/schema.py's BeatStrategy. */
export type Relationship =
  "process" | "comparison" | "data_movement" | "hierarchy" |
  "cause_effect" | "structure" | "effect" | "quantity";

export type PhysicalForm =
  "single_container" | "linked_nodes" | "nested_levels" | "flat_parts" |
  "two_sides" | "single_object" | "not_applicable";

export type BeatStrategy = {
  ref: string;
  concept: string;
  relationship: Relationship;
  physical_form: PhysicalForm;
  why_visual: string;
  must_see: string;
  changes_from_previous: string;
  focus: string;
};

/** The composition plan for one short, before any of it is drawn. See
 *  shorts/schema.py's VisualStrategy. */
export type VisualStrategy = {
  subject: string;
  beats: BeatStrategy[];
};

/** Step 11 — one completed LLM regeneration of a VisualStrategy. Always a
 *  COMPLETE plan, never a patch to one beat — see shorts/schema.py's
 *  VisualStrategyRegenerationAttempt. */
export type VisualStrategyRegenerationAttempt = {
  reason: string;
  previous_strategy: VisualStrategy;
  regenerated_strategy: VisualStrategy;
};

/** Step 11 — the human gate on the visual plan. See shorts/schema.py's
 *  VisualPlanApproval, and TeachingApproachApproval's "NO DIRECT OVERRIDES"
 *  for why `override` is legacy-only and never written by this UI. */
export type VisualPlanApproval = {
  status: "pending" | "approved" | "modified" | "regenerating";
  note?: string | null;
  override?: VisualStrategy | null;
  regenerated_strategy?: VisualStrategy | null;
  regeneration_history: VisualStrategyRegenerationAttempt[];
};

/** Output of Skill 2 — shorts/schema.py's Script. */
export type Script = {
  short_id: string;
  question: string;
  beats: Beat[];
};

/** The full record for one candidate question, Steps 3-11 — what
 *  /api/material returns per topic (selection + question_approval only, at
 *  that point), and what /api/selections/*, /api/teaching-approach/*,
 *  /api/workflow/advance (Step 7), /api/workflow/scripts (Step 8-9),
 *  /api/visual-plan/* (Step 11) all take and return as it fills in. */
export type QuestionWorkflow = {
  selection: QuestionSelection;
  question_approval: QuestionApproval;
  framing?: QuestionFraming | null;
  teaching_approach?: TeachingApproach | null;
  teaching_approach_approval: TeachingApproachApproval;
  /** Step 8-9 — set once /api/workflow/scripts has drafted this workflow's
   *  script through write_script_for_workflow. */
  script?: Script | null;
  visual_strategy?: VisualStrategy | null;
  visual_plan_approval: VisualPlanApproval;
};

/** Mirrors shorts/schema.py's QuestionWorkflow.effective_question: the
 *  latest regeneration, else a legacy direct edit, else the original
 *  question select.py produced. Never mutates selection.topic.topic. */
export function effectiveQuestion(wf: QuestionWorkflow): string {
  const qa = wf.question_approval;
  return qa.regenerated_question || qa.edited_question || wf.selection.topic.topic;
}

/** Mirrors shorts/schema.py's QuestionWorkflow.approved_topic: the
 *  selection's Topic with its `.topic` text replaced by the approved
 *  wording — or null unless question_approval.status is exactly "approved". */
export function approvedTopic(wf: QuestionWorkflow): Topic | null {
  if (wf.question_approval.status !== "approved") return null;
  return { ...wf.selection.topic, topic: effectiveQuestion(wf) };
}

/** workflow.script, as the QA shape StepReview/StepVisualPlan/finalize use
 *  for display and for POST /api/finalize. The server only ever reads
 *  `.question` and `.beats` off this (see server.py's build_one) — `seconds`/
 *  `words` are derived here purely for on-screen display, mirroring
 *  shorts/schema.py's Script.word_count / .estimated_seconds. */
export function scriptToQA(script: Script): QA {
  const words = script.beats.reduce(
    (n, b) => n + b.line.split(/\s+/).filter(Boolean).length, 0);
  return {
    short_id: script.short_id, question: script.question,
    beats: script.beats, seconds: Math.round((words / 2.5) * 10) / 10, words,
  };
}

/** Mirrors shorts/schema.py's QuestionWorkflow.effective_teaching_approach: a
 *  human's DIRECT selection outranks an LLM regeneration (it is always the
 *  LATER decision when both exist, and regeneration clears `override` — see
 *  shorts/review.regenerate_teaching_approach), which outranks the original
 *  LLM decision. Null if no teaching_approach has been chosen at all. */
export function effectiveTeachingApproach(wf: QuestionWorkflow): TeachingApproach | null {
  const a = wf.teaching_approach_approval;
  return a.override ?? a.regenerated_approach ?? wf.teaching_approach ?? null;
}

/** Mirrors shorts/schema.py's QuestionWorkflow.approved_teaching_approach:
 *  null unless teaching_approach_approval.status is exactly "approved". */
export function approvedTeachingApproach(wf: QuestionWorkflow): TeachingApproach | null {
  return wf.teaching_approach_approval.status === "approved"
    ? effectiveTeachingApproach(wf) : null;
}

/** The AI's OWN current recommendation — the latest regeneration, else its
 *  original decision — deliberately IGNORING any human `override`. This is
 *  what StepTeachingApproach shows as "Recommended approach" and defaults
 *  the picker to, so a reviewer always sees what the AI actually
 *  recommends, not a stale earlier pick of their own. */
export function llmRecommendedApproach(wf: QuestionWorkflow): TeachingApproach | null {
  const a = wf.teaching_approach_approval;
  return a.regenerated_approach ?? wf.teaching_approach ?? null;
}

/** Mirrors shorts/schema.py's QuestionWorkflow.effective_visual_strategy:
 *  the latest regeneration, else a legacy override, else Step 10's own
 *  plan_strategy_for_workflow output — or null if none has run yet. */
export function effectiveVisualStrategy(wf: QuestionWorkflow): VisualStrategy | null {
  const a = wf.visual_plan_approval;
  return a.regenerated_strategy ?? a.override ?? wf.visual_strategy ?? null;
}

/** Mirrors shorts/schema.py's QuestionWorkflow.approved_visual_strategy:
 *  null unless visual_plan_approval.status is exactly "approved". */
export function approvedVisualStrategy(wf: QuestionWorkflow): VisualStrategy | null {
  return wf.visual_plan_approval.status === "approved"
    ? effectiveVisualStrategy(wf) : null;
}

/** Steps 7 and 9 — why shorts/workflow.py's advance() stopped, and what a
 *  caller should do about it. See that module's OrchestrationStatus. */
export type OrchestrationStatus =
  "awaiting_question_approval" | "rejected" |
  "awaiting_teaching_approach_approval" | "awaiting_visual_plan_approval" |
  "framing_failed" | "teaching_approach_failed" | "script_failed" |
  "visual_plan_failed";

export type WorkflowProgress = {
  workflow: QuestionWorkflow;
  status: OrchestrationStatus;
  detail: string;
};

export type GraderResult = { name: string; passed: boolean; reason: string };

/** The review view's shape: one narrator's connected explanation of `question`,
 *  in speaking order. `beats[0]` is the opening; every beat after it is the
 *  answer, one idea each — see shorts/schema.py's Script.opening_beat /
 *  .body_beats. THE WIRE KEY AND FIELD NAMES STAY AS THEY ARE (see
 *  shorts/server.py's `_as_qa` docstring for why): this used to also carry a
 *  separate `answers` list, a filtered copy of `beats` for beats spoken by a
 *  second "student" role — there is only one narrator now, so `beats` alone
 *  is the whole script and `answers` is gone. */
export type QA = {
  short_id: string;
  question: string;
  beats: Beat[];
  seconds: number;
  words: number;
};

export type Judge = {
  faithfulness: number;
  clarity: number;
  pace: number;
  problems: string[];
  /** Present on the review-time verdict (server._review_judge); absent on the
   *  finalized Unit's judge, which is scored against the audit bar elsewhere. */
  passed?: boolean;
};

export type Unit = {
  short_id: string;
  question: string;
  section: string;
  status: "draft" | "audited" | "approved" | "rendered" | "rejected";
  seconds: number;
  judge: Judge | null;
  diagrams: number;
  /** A recorded neural track, when one was built. Null means browser speech. */
  audio_url?: string | null;
  beats: ReelBeat[];
};

export type Feedback = {
  short_id: string;
  event: "view" | "confusing";
  at?: number;
  watched_pct?: number;
  dropped_at?: number;
};

/** One row in the review step: a workflow, its script, and the human's verdict. */
export type ReviewItem = {
  /** Step 3-9's full record — framing and the (auto-approved) teaching
   *  approach that governed this card's script, kept so a later
   *  regeneration (see api.ts's regenerate) keeps following it too. */
  workflow: QuestionWorkflow;
  topic: Topic;
  qa: QA | null;
  graders: GraderResult[];
  /** The review-time judge verdict (server._review_judge) — null when the free
   *  graders didn't all pass yet (nothing to ask a paid model about) or
   *  JUDGE_AT_REVIEW is off; undefined before the first draft comes back. */
  judge?: Judge | null;
  state: "idle" | "loading" | "ready" | "error" | "approved" | "skipped";
  error?: string;
  note: string;
  target: "question" | "answer" | "script";
  /** What this card has cost so far, across its draft and regenerations. */
  spent?: import("./api").UsageTotals;
};
