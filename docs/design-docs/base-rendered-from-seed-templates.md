---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [portable-layer, templates, lint, operating-gotcha]
description: base/ files are RENDERED from plugin/skills/harness-init/templates/ seeds (lint_base enforces byte-equality); edit the seed not base/, and a repo-wide doc reference sweep must include templates/ — a machine-doc string lives in three places.
resource: plugin/scripts/lint_base.py
---
# base/ is rendered from seed templates

A field note promoted from session memory. `harness_lib.SEEDS` maps each seed
template under `plugin/skills/harness-init/templates/` to a host destination
(e.g. `agents-md.md → AGENTS.md`, `knowledge-format.md → docs/KNOWLEDGE_FORMAT.md`,
`charter.md → docs/CHARTER.md`). The strict-base artifact `base/{dest}` must be
**byte-equal to `render(seed, subs)`**, enforced by `plugin/scripts/lint_base.py`
(error `B2` "content drift from its seed template") and the base-in-sync test.

## So `base/` is GENERATED, not hand-maintained

Editing a `base/` file directly without editing its seed **fails the gate**. Fix:
edit the **seed** (the source of truth); `base/` re-renders from it. `render`
substitutes placeholders (`{{COMPONENTS}}`, `{{TODAY}}`, `{{PROJECT}}`, …);
non-placeholder lines pass through unchanged, so an identical plain-text edit to a
seed keeps `base/` in sync.

## Key implication — a string can live in three places

A repo-wide reference/rename sweep of a machine-doc string must include the
`templates/` **seeds** (the portable source), not just self-host `docs/` and the
`base/` mirror. Note the asymmetry: self-host `docs/CHARTER.md` /
`docs/KNOWLEDGE_FORMAT.md` / `AGENTS.md` are the live, free-form filled docs (NOT
rendered from a seed); only `base/` is the rendered mirror. So for these docs a
string lives in **three** places: self-host `docs/` (hand-edit), the `templates/`
seed (hand-edit the source), and `base/` (auto via the seed). A grep scoped to
`docs/ base/` will miss the seed and drift the gate.

This is the portable-layer face of core belief 13 ("general by identity; harness
changes propagate to the portable layer" — [core-beliefs.md](core-beliefs.md)).
It is distinct from the manual vendoring path in
[worker-runtime sync is a manual port](worker-runtime-sync-is-manual-port.md).
