# Working rules for this repo

These apply to every phase of every task, without being restated.

## Review and approval
- **The user reviews everything themselves.** Passing tests, evals or graders are evidence, not approval. Never describe work as "approved", "done" or "ready to ship" because your own checks pass.
- **Everything you build must be viewable by the user**, either in the web UI or in `docs/reference/<phase>/` (screenshots, sample outputs, write-ups). When you report, say exactly where to look (URL, route or file path) and what to check there.

## Git
- **Never commit until the user says the work is approved.**
- **Never push unless the user asks.** One "push" covers that push only.
- The working branch is `pallavi-workspace-in`. `pallavi-workspace-laptop` is a backup; leave it alone.

## Money
- **No paid API calls unless the user runs them.** Use stub mode (`SHORTS_STUB=1`) for everything you run yourself. Local, free tools (Chatterbox, faster-whisper, the forced aligner, Chrome screenshots) are fine.
- Do not trigger any pipeline step that creates a real reel (script, scenes, visuals, finalize, run.py, motion_reel without `SHORTS_STUB=1`). Prepare the command, show its estimated cost, and let the user run it.
- Tests write to temp folders, never to `output/` or `assets/`.
