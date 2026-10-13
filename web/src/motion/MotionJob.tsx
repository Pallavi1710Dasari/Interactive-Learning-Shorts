// The Motion list's links into the workspace's motion steps (StepMotion.tsx),
// where a reel being made in the UI lives at #motion/job/<id>:
//   JobList     reels started in the UI that have not finished
//   ResumeReel  resume a reel from the list — its own job, or a new one for a
//               reel the command line started
// App picks its screen once per page load, so opening a reel's steps reloads.

import { useEffect, useState, type CSSProperties } from "react";

const muted = "#9AA0C0";
const card: CSSProperties = { background: "#151A33", borderRadius: 14, padding: "14px 18px", marginBottom: 18 };
const link: CSSProperties = { color: "#FDD13E", textDecoration: "none", fontWeight: 700 };
const STAGE: Record<string, string> = { options: "Upload", topic: "Topic", approach: "Teaching approach",
  template: "Template", theme: "Theme", script: "Script", scenes: "Scenes", voice: "Voice & timing",
  timing: "Voice & timing", done: "Done" };
const STATUS: Record<string, string> = { options: "waiting to start", review: "waiting for a decision",
  preflight: "waiting to start this step", cap: "stopped at the cost limit", stopped: "paused",
  error: "stopped by a problem", running: "working", done: "done" };

interface JobRow { job_id: string; short_id: string | null; doc_name: string; stage: string; status: string; cost: { reel: number } }

export function openJob(jobId: string) {
  location.hash = `#motion/job/${jobId}`;
  location.reload();
}

/** In-progress UI reels, each with its step and a link to resume it. */
export function JobList() {
  const [jobs, setJobs] = useState<JobRow[]>([]);
  useEffect(() => { fetch("/api/motion-jobs").then((r) => r.json()).then((d) => setJobs(d.jobs)).catch(() => {}); }, []);
  const open = jobs.filter((j) => j.status !== "done");
  if (!open.length) return null;
  return (
    <div style={card}>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>In progress</h2>
      <p style={{ margin: "0 0 10px", color: muted, fontSize: 13 }}>Reels started in the UI that have not finished. Open one to carry on where it stopped.</p>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <tbody>{open.map((j) => (
          <tr key={j.job_id} style={{ borderTop: "1px solid #2A3052" }}>
            <td style={{ padding: 8 }}><a href={`#motion/job/${j.job_id}`} style={link}
                 onClick={(e) => { e.preventDefault(); openJob(j.job_id); }}>{j.short_id ?? j.doc_name}</a></td>
            <td>{STAGE[j.stage] ?? j.stage}</td>
            <td style={{ color: muted }}>{STATUS[j.status] ?? j.status}</td>
            <td>${j.cost.reel.toFixed(2)}</td>
          </tr>))}</tbody>
      </table>
    </div>
  );
}

/** Resume a reel from the Motion list: its UI job, or a new one for a CLI reel. */
export function ResumeReel({ shortId }: { shortId: string }) {
  const [err, setErr] = useState<string | null>(null);
  return (
    <span>
      <button style={{ background: "#232A4D", color: "#E9EBF7", border: "none", borderRadius: 10, padding: "8px 14px",
                       fontWeight: 800, fontSize: 14, cursor: "pointer", fontFamily: "inherit" }}
              onClick={() => fetch(`/api/motion/${encodeURIComponent(shortId)}/job`, { method: "POST" })
                .then(async (r) => { const d = await r.json(); if (!r.ok) throw new Error(d.detail ?? r.statusText); openJob(d.job_id); })
                .catch((e) => setErr(e.message))}>Resume</button>
      {err && <span style={{ color: "#FFB524", fontSize: 12, marginLeft: 8 }}>{err}</span>}
    </span>
  );
}
