---
status: active
last_verified: 2026-06-21
owner: harness
type: exec-plan
description: Make the two plugin manifests name only existing components (marketplace skill list — dream removed, docs-nav added) and bump the plugin version; verify the generated inventory is current; prepare (but do not push) a republish.
base_commit: 83bf1b91632d7eb246fe4e306a806b9f94548356
review_level: targeted
phase: packaging/05-plugin-cleanup
---
# Packaging Slice 5 — plugin cleanup + manifest update

## Goal
The two plugin manifests describe the harness **as it actually is** after the
memory retirement (Slice 1) and the subsequent slices, and the plugin version is
bumped to mark the packaging changes. Observable definition of done:

1. `.claude-plugin/marketplace.json`'s plugin description lists exactly the **8
   skills that exist on disk** — `execplan, harness-lint, docs-tree, docs-nav,
   product-design, harness-init, architecture-setup, garden` — with the deleted
   `dream` removed and the present `docs-nav` added.
2. `plugin/.claude-plugin/plugin.json` `version` is bumped (`0.1.0` → `0.2.0`),
   and its description carries no memory-loop term (`feeder` / `imprint` /
   `dreaming` / `memory loop`) — confirmed already clean, so only the bump lands.
3. The generated component inventory (`docs/generated/component-inventory.md`) is
   consistent with the plugin contents — verified, not hand-edited.
4. `python3 plugin/scripts/check.py` is GREEN.
5. Republish is **prepared, not performed** — the manifest is release-ready; the
   actual public push is recorded as a separate human go/no-go (R5.3).

## Context
Implements **Slice 5 (`packaging/05`)** of
`docs/product-specs/2026-06-21-harness-packaging-portable-template.md`
(R5.1–R5.3 + acceptance #5). The spec owns the design; this plan owns the build.
Prior slices (1–4) are complete; the plugin's actual components changed in Slice 1
(deleted the `dream` skill + `dreamer` agent + memory scripts), and the inventory
was regenerated under the gate then.

Verified current state (the build rests on these facts, not assumptions):
- **Skills on disk** (`plugin/skills/`): architecture-setup, docs-nav, docs-tree,
  execplan, garden, harness-init, harness-lint, product-design — **8**, no `dream`.
- **Agents** (`plugin/agents/`): doc-gardener + the 5 review personas — no `dreamer`.
- **`docs/generated/component-inventory.md`** already lists exactly those 8 skills,
  6 agents, and the one `Stop → tidy_stop.py` hook; `gen_inventory.py --check`
  passes today (so R5.2 needs no regeneration — only verification).
- **`plugin/.claude-plugin/plugin.json`**: `version 0.1.0`; description =
  "AI-native harness: docs-as-memory knowledge system, taste lints, and
  review-persona gates …" — **already free** of the memory-loop clause the original
  v1 manifest carried (`docs/superpowers/plans/2026-06-12-agent-harness-v1.md:79`
  shows the old "…and a memory loop (feeder / imprint / dreaming)…" wording, since
  dropped). So plugin.json needs only the version bump.
- **`.claude-plugin/marketplace.json`**: plugin description's parenthetical skill
  list reads "…architecture-setup, **dream**, garden" — it names the deleted
  `dream` and **omits** `docs-nav`. This is the real R5.1 drift.
- **`docs-as-memory` is a term of art** — it appears in `harness-init/SKILL.md`,
  the `agent-harness.md` design-doc (frontmatter tag + body), and `okf-comparison.md`
  as the name of the durable-knowledge-in-docs model. It does **not** reference the
  retired loop, so it stays in both manifests.

## Approach (self-generated alternatives)
- A: **Minimal manifest edits + verify the inventory** — fix marketplace's skill
  list (remove `dream`, add `docs-nav`), bump `plugin.json` version, confirm
  `gen_inventory --check` is green and `check.py` GREEN. Tradeoff: marketplace's
  skill list is freeform prose, not gate-checked, so it can drift again.
- B: **A + a lint** that asserts marketplace's described skill list matches the
  skills on disk. Tradeoff: parsing a prose description into a skill set is brittle
  and over-engineered for a one-line marketplace blurb; YAGNI.
- **Chosen: A** — the drift here is a one-time stale description; a parser-lint for
  a freeform blurb is disproportionate. Record the "marketplace skill list is
  hand-maintained, not gate-checked" gap as tech-debt instead of building a lint.

## Assumptions & open questions (self-interrogation)
- **Assumption — the inventory needs no regeneration.** Verified: `gen_inventory.py
  --check` passes on HEAD (the deletions landed + regenerated in Slice 1; Slices 2–4
  added no skill/agent/hook). *If wrong*, the gate would redden and M2 regenerates it.
- **Assumption — `plugin.json`'s description is already memory-loop-free.** Verified
  by inspection (no feeder/imprint/dreaming/"memory loop" substring). *If wrong*, M1
  also rewords it. Recorded so a reviewer can re-check the exact string.
- **Open — version bump granularity (`0.2.0` vs `0.1.1`)?** Resolved autonomously:
  **`0.2.0`** (minor). The packaging effort removed user-visible components (the
  `dream` skill, `dreamer` agent, the memory loop), relocated the Director, and
  consolidated the profiles — a minor-version's worth of change for a 0.x plugin.
  Mechanical call, recorded in the Decision log; not a taste fork.
- **Open — is the publish itself in scope?** No (R5.3): the manifest is made
  release-ready, but pushing a public release is a separate **human go/no-go**
  (outward-facing). This plan stops at a release-ready manifest + a green gate.
- **Open — fix the other stale `dream`/loop mentions** (QUALITY_SCORE "dreaming"
  grade rows, PRODUCT_SENSE, SECURITY T-rules)? No — out of R5.1's scope (the two
  manifests) and **already tracked** as the "numbered-rule text still describes the
  retired memory loop" doc-debt row from Slice 1. Not re-opened here.

## Milestones

- **M1 — Manifests name only existing components (R5.1).** Scope: the two manifest
  files. In `.claude-plugin/marketplace.json`, rewrite the plugin description's
  skill list to `execplan, harness-lint, docs-tree, docs-nav, product-design,
  harness-init, architecture-setup, garden` (remove `dream`, add `docs-nav`),
  keeping the rest of the blurb (incl. "docs-as-memory") intact. In
  `plugin/.claude-plugin/plugin.json`, bump `version` `0.1.0` → `0.2.0` (description
  unchanged — already loop-free). At the end, both manifests name exactly the
  components that exist. Run: `python3 -c "import json,glob,os;
  m=json.load(open('.claude-plugin/marketplace.json'));
  skills=sorted(os.path.basename(os.path.dirname(p)) for p in
  glob.glob('plugin/skills/*/SKILL.md'));
  print('disk:',skills); print('desc has dream:', 'dream' in
  m['plugins'][0]['description']); print('desc has docs-nav:', 'docs-nav' in
  m['plugins'][0]['description'])"` — expect `desc has dream: False`,
  `desc has docs-nav: True`, and the disk list = the 8 skills.
  Acceptance: `grep -c '"dream"\|, dream,\| dream,' .claude-plugin/marketplace.json`
  → 0; `grep version plugin/.claude-plugin/plugin.json` → `0.2.0`; both JSON files
  still parse (the python one-liner runs without error).

- **M2 — Inventory verified + gate GREEN + republish readiness (R5.2 + R5.3).**
  Scope: verification + a recorded republish decision (no code/file change beyond
  what M1 did). Confirm `python3 plugin/scripts/gen_inventory.py --check` passes
  (the inventory already matches disk — no regeneration), then run the full gate.
  Record that the republish (R5.3) is **prepared, not performed** — a human go/no-go.
  At the end, the gate is GREEN and the release-readiness state is explicit. Run:
  `python3 plugin/scripts/gen_inventory.py --check && python3 plugin/scripts/check.py`
  — expect both green (`check: GREEN — commit allowed`). Acceptance: gate GREEN; the
  plan records the republish as deferred-to-human; no inventory drift.

## Progress log
- [ ] (2026-06-21) Plan created; manifest/inventory surface mapped; confirmed
  inventory already current + plugin.json description already loop-free + the lone
  drift is marketplace's `dream`/missing-`docs-nav`. (done: exploration + plan;
  remaining: M1–M2 + completion gate)

## Surprises & discoveries
- R5.2 ("regenerate the inventory") is effectively a no-op: the inventory was
  regenerated when Slice 1 deleted dream/dreamer (the gate enforces it), and Slices
  2–4 changed no skill/agent/hook. The only live manifest drift is the hand-maintained
  marketplace skill list (freeform prose, not gate-checked).
- `docs-as-memory` reads at first like a memory-loop reference but is actually the
  established name for the durable-docs-as-knowledge model — kept, not stripped.

## Decision log
- 2026-06-21: version `0.1.0` → `0.2.0` (minor) — packaging removed user-visible
  components + relocated/consolidated the agents; a minor bump marks it for a 0.x plugin.
- 2026-06-21: keep "docs-as-memory" in both manifests — it is the model's name, not a
  reference to the retired feeder/imprint/dream loop.
- 2026-06-21: do NOT build a marketplace-skill-list lint (Approach B) — disproportionate
  for a freeform blurb; track the not-gate-checked gap as tech-debt instead.
- 2026-06-21: republish (R5.3) is prepared, not performed — the public push is a human
  go/no-go (outward-facing), per the spec.

## Feedback (from completion gate)

## Outcomes & retrospective
