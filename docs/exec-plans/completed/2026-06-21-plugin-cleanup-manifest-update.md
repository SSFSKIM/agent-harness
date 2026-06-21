---
status: completed
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
- [x] (2026-06-21) Plan created; manifest/inventory surface mapped; confirmed
  inventory already current + plugin.json description already loop-free + the lone
  drift is marketplace's `dream`/missing-`docs-nav`.
- [x] (2026-06-21) M1 — marketplace.json skill list corrected (dropped `dream`,
  added `docs-nav` → the 8 disk skills); plugin.json version `0.1.0`→`0.2.0`.
  Verified: desc has no `dream`, has `docs-nav`, no disk skill missing; no
  memory-loop terms in plugin.json.
- [x] (2026-06-21) M2 — `gen_inventory --check` green (no regen); full gate GREEN
  (694 tests); republish recorded as a human go/no-go.
- [x] (2026-06-21) Completion gate: GREEN; behavioral N/A (descriptive metadata —
  see below); reviews — arch SATISFIED; spec-compliance + code-quality SATISFIED
  (Claude fallback — codex stalled on a rate-limit/empty-turn condition). P2s tracked.

## Behavioral check
**N/A — pure descriptive metadata.** The deliverable is two manifest fields (a
freeform skill-list blurb + a semver string); there is no CLI/service/UI flow to
exercise. Verification is by JSON-parse (both files load), the disk↔description
set-match assertion (the 8 skills, no `dream`, has `docs-nav`), `gen_inventory.py
--check` (inventory consistent), and the full `check.py` gate — all green.

## Surprises & discoveries
- R5.2 ("regenerate the inventory") is effectively a no-op: the inventory was
  regenerated when Slice 1 deleted dream/dreamer (the gate enforces it), and Slices
  2–4 changed no skill/agent/hook. The only live manifest drift is the hand-maintained
  marketplace skill list (freeform prose, not gate-checked).
- `docs-as-memory` reads at first like a memory-loop reference but is actually the
  established name for the durable-docs-as-knowledge model — kept, not stripped.
- The `Stop → tidy_stop.py` hook in the inventory looks like memory-loop residue but
  is a **deliberate, documented Slice-1 deviation** (`tidy_stop` kept as the
  gate-on-stop net; tracker row from Slice 1). So R5.2's "inventory consistent with
  plugin contents" is satisfied by the as-built reality, not the spec's R1.6 wording —
  spec-compliance flagged this correctly as a Slice-1 matter, not a Slice-5 finding.
- **codex stalled again** on the spec-compliance review (turn started, zero commands,
  no verdict — the known rate-limit/empty-turn mode; a sibling codex job has hung 13h+).
  Fell back to the Claude review personas per CLAUDE.md. Arch (Claude persona) ran fine.

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
All four reviews (arch; spec-compliance + code-quality via Claude fallback)
SATISFIED, no P1. Two P2s + three proposed rules, all tracked in
`docs/exec-plans/tech-debt-tracker.md`.

- **P2 (code-quality) — record the gap in the DURABLE tracker, not just the plan.**
  Approach A promised to "track the not-gate-checked marketplace gap as tech-debt,"
  but it lived only in this plan's Decision log / Surprises — which disappears when
  the plan is archived (core-belief 8: non-blocking findings go to the tracker;
  belief 2: not in the repo = doesn't exist). Fixed at completion: a tracker row now
  records the gap. 
- **P2 (code-quality) — marketplace skill-list ordering.** The list follows the
  spec's logical/workflow order, not the inventory's alphabetical order, so the two
  can't be eyeball-reconciled. Kept the spec's order (R5.1 specified it; the
  gate-checked inventory is the source of truth, the blurb is freeform by design);
  folded the ordering note into the tracker row rather than deviating from R5.1.
- **Proposed rule (review-arch) — a marketplace↔disk containment lint.** Not a prose
  parser (the brittle objection that killed Approach B) but a substring-containment
  check: every `plugin/skills/*/` dirname appears in the marketplace description and
  no deleted-skill token lingers. Disposition: leave as tech-debt; build only if the
  drift recurs. Tracked.
- **Proposed rule (review-spec-compliance) — downstream-consistency inherits as-built
  reality.** When a downstream slice's "consistency" requirement (R5.2) rests on an
  upstream slice's documented deviation (Slice 1 keeping `tidy_stop` vs R1.6's "delete
  it"), the plan should cite the deviation inline so the surviving artifact isn't read
  as drift. A one-line spec convention. Tracked.

## Outcomes & retrospective
Slice 5 delivered its Goal: the two plugin manifests now name only components that
exist, and the version is bumped to mark the packaging work.

- **R5.1 — manifests reflect reality.** `marketplace.json`'s skill list dropped the
  retired `dream` and added the present `docs-nav` (now the 8 skills on disk, agreeing
  with the gate-checked inventory); `plugin.json` bumped `0.1.0`→`0.2.0`. The lone real
  drift was the marketplace blurb — `plugin.json`'s description was already loop-free,
  and "docs-as-memory" was correctly kept (it names the durable-docs model, not the
  retired loop).
- **R5.2 — inventory current by construction.** `gen_inventory --check` was already
  green (Slice 1's deletions regenerated it under the gate; Slices 2–4 touched no
  skill/agent/hook), so no regeneration was needed — only verification. Recorded, not
  silently skipped.
- **R5.3 — republish prepared, not performed.** The manifest is release-ready; the
  public push is a separate human go/no-go (outward-facing), left to the human.
- **Smallest slice so far** — the real value was the exploration that scoped it down:
  confirming the inventory was already current, that `docs-as-memory` is a term of art
  to keep, and that the only live drift was one freeform blurb. The reviews added the
  durable-tracker discipline (a finding that lives only in an archived plan is lost).
- **Process:** codex stalled on the spec-compliance review (rate-limit/empty-turn); the
  Claude fallback (per CLAUDE.md) carried it cleanly. No new code, so the behavioral
  check was a recorded N/A.
- **Next:** Slice 6 (`packaging/06`, capstone) — the checked-in reference base artifact
  + `SETUP.md` + a drift-check lint + the legacy strip; the inspectable "open one folder
  and see the whole system" deliverable.
