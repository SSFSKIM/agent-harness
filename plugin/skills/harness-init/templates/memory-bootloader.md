# MEMORY.md — bootloader

Loading protocol for a fresh session. The feeder normally compiles this for
you; follow manually if no context pack was injected.

1. Read `progress/current.md` — where we are, what is in flight.
2. Read every file in `../exec-plans/active/` — the living plans.
3. Scan `openq/index.md` — open questions that may affect today's work.
4. Navigate on demand (do NOT bulk-read):
   - `knowledge/index.md` — reusable how-things-work pages
   - `adr/index.md` — decisions and why
   - `limitations/index.md` — known landmines
   - `archive/sessions/` — per-session digests (raw history; rarely needed)

Write rules:
- Imprint jobs and /dream write here. In-session: update
  `progress/current.md` plus the page your work touched; register new pages
  in their directory's index.md.
- Every page carries frontmatter `status / last_verified / owner` (lint D3).
- Session digests are `status: archived` (stale-exempt, immutable). Filename
  contract: `YYYY-MM-DD-{sid8}-{event_slug}.md` (event_slug = `session-end` or
  `pre-compact`). No two digests may share a name.
- This file is an index, not a knowledge dump.
