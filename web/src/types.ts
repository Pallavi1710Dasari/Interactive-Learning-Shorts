// Mirrors the payloads shorts/server.py and shorts/feed.py produce. If you add a
// field there, add it here — the app fetches these shapes at runtime, so a
// mismatch shows up as an empty panel rather than a compile error.

/** One word of the narration, with the moment it is spoken. */
export type CaptionWord = { w: string; s: number; e: number };

export type Beat = {
  speaker: "interviewer" | "student";
  line: string;
  on_screen: string;
  visual_ref: string;
  /** Word-by-word timings for the flowing caption. See shorts/feed.py. */
  words?: CaptionWord[];
  /** The sentence of the source this beat restates; student beats only. */
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
};

/** Step 3 — one structured reason a question was selected. See
 *  shorts/schema.py's SelectionReason. */
export type SelectionReason = {
  category: "importance" | "foundational" | "commonly_confused" |
            "concrete_and_answerable" | "distinct_angle" | "other";
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

export type TeachingApproach = {
  primary: TeachingApproachKind;
  combined_with: TeachingApproachKind[];
  alternatives: TeachingApproachKind[];
  rationale: string;
};

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
  /** Legacy — Step 6's own UI never sets this; see "NO DIRECT OVERRIDES" in
   *  shorts/schema.py's TeachingApproachApproval. */
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

/** The full record for one candidate question, Steps 3-11 — what
 *  /api/material returns per topic (selection + question_approval only, at
 *  that point), and what /api/selections/*, /api/teaching-approach/*,
 *  /api/workflow/advance (Step 7), /api/visual-plan/* (Step 11) all take and
 *  return as it fills in. `script` is intentionally not modeled here yet —
 *  no frontend flow reads it. */
export type QuestionWorkflow = {
  selection: QuestionSelection;
  question_approval: QuestionApproval;
  framing?: QuestionFraming | null;
  teaching_approach?: TeachingApproach | null;
  teaching_approach_approval: TeachingApproachApproval;
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

/** Mirrors shorts/schema.py's QuestionWorkflow.effective_teaching_approach:
 *  the latest regeneration, else a legacy override, else the original
 *  LLM decision — or null if no teaching_approach has been chosen at all. */
export function effectiveTeachingApproach(wf: QuestionWorkflow): TeachingApproach | null {
  const a = wf.teaching_approach_approval;
  return a.regenerated_approach ?? a.override ?? wf.teaching_approach ?? null;
}

/** Mirrors shorts/schema.py's QuestionWorkflow.approved_teaching_approach:
 *  null unless teaching_approach_approval.status is exactly "approved". */
export function approvedTeachingApproach(wf: QuestionWorkflow): TeachingApproach | null {
  return wf.teaching_approach_approval.status === "approved"
    ? effectiveTeachingApproach(wf) : null;
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

/** The review view's shape: a question plus the student answers. */
export type QA = {
  short_id: string;
  question: string;
  answers: {
    index: number; line: string; on_screen: string; visual_ref: string;
    /** The sentence of the source this answer restates. Verified server-side. */
    source_quote?: string | null;
  }[];
  beats: Beat[];
  seconds: number;
  words: number;
};

export type Judge = {
  faithfulness: number;
  clarity: number;
  pace: number;
  problems: string[];
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

/** One row in the review step: a topic, its script, and the human's verdict. */
export type ReviewItem = {
  topic: Topic;
  qa: QA | null;
  graders: GraderResult[];
  state: "idle" | "loading" | "ready" | "error" | "approved" | "skipped";
  error?: string;
  note: string;
  target: "question" | "answer" | "script";
  /** What this card has cost so far, across its draft and regenerations. */
  spent?: import("./api").UsageTotals;
};
