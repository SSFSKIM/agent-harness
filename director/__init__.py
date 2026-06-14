"""Director: the human-taste orchestration layer over Symphony-style Codex workers.

Host app-code (ARCHITECTURE invariant 7 — a long-running service is the host's
app, not the portable harness machinery under plugin/), built from the design in
docs/product-specs/2026-06-14-symphony-director-orchestration.md and the Phase 1
plan docs/exec-plans/active/2026-06-14-director-phase1-worker-approval-seam.md.

Phase 1 scope: a Codex app-server worker whose mid-turn approval/input requests
route to the Director (the main Claude session) via the queue here, so the same
turn resumes on the answer instead of being killed.
"""
