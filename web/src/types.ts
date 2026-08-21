// Mirrors the payloads shorts/server.py and shorts/feed.py produce. If you add a
// field there, add it here — the app fetches these shapes at runtime, so a
// mismatch shows up as an empty panel rather than a compile error.

export type Beat = {
  speaker: "interviewer" | "student";
  line: string;
  on_screen: string;
  visual_ref: string;
  /** The sentence of the source this beat restates; student beats only. */
  source_quote?: string | null;
  /** Inline SVG, already stripped of <script> and on* handlers in Python. */
  svg?: string | null;
  start?: number;
  end?: number;
};

/** A beat as it comes back inside a reel payload — timings always present. */
export type ReelBeat = Beat & { svg: string | null; start: number; end: number };

export type Topic = {
  id: string;
  topic: string;
  why_it_matters: string;
  source_section_id: string;
  difficulty: "easy" | "medium" | "hard";
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
