---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [worker-runtime, vendoring, maintenance]
description: worker-runtime/{harness,app-server} is a one-way vendored subtree (not a git remote, no auto-sync); pull upstream features by hand-porting the commit diff, verify, then rebuild dist via worker-runtime/setup.sh.
resource: worker-runtime/README.md
---
# worker-runtime sync is a manual port

A field note promoted from session memory. Cited as the precedent for manual,
pinned re-vendoring by
[ADR 0006 (observability vendored asset)](../adr/0006-observability-vendored-asset.md).
See [`worker-runtime/README.md`](../../worker-runtime/README.md) for what the
runtime is.

`worker-runtime/{harness,app-server}` was brought in via `git subtree` from an
external producer repo. It is a **one-way snapshot**: the producer is **not** a
git remote of this repo, so changes there do **not** propagate, and the two copies
can diverge both ways — a blind `git subtree pull` risks conflicts.

## Sync workflow (recommended = hand-port the diff)

1. Find the upstream commit in the producer repo (`git log --oneline`).
2. **Read its diff.** Gotcha: if the producer's git root is a *parent* dir,
   tracked paths carry a path prefix — use `git show <sha>:<prefix>/harness/...`
   even though the working tree lacks the prefix.
3. Apply equivalent edits to `worker-runtime/harness/...`. Most features wire
   through a single config seam (e.g. `resolveOptions`), so one edit reaches the
   whole runtime.
4. Verify from `worker-runtime/harness/`: `npm run typecheck`, `npm run test:unit`,
   `npm run build`; then the repo gate (`python3 plugin/scripts/check.py`).
5. To activate at runtime, rebuild `dist` via **`worker-runtime/setup.sh`**
   (harness first, then app-server — app-server's `tsc` needs harness's emitted
   types). `dist/` + `node_modules/` are **gitignored** (generated, never
   committed).

When you touch these files, **stage only what you touched** — the master index is
shared ([parallel sessions share one master index](parallel-sessions-share-master-index.md)).
A different, generated-from-seed vendoring path (the portable templates) is
described in
[base/ is rendered from seed templates](base-rendered-from-seed-templates.md).
