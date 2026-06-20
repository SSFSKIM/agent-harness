---
status: stable
last_verified: {{TODAY}}
owner: harness
type: design-doc
description: The installed harness: its components, native memory, and the commit gate.
---
# agent-harness — the installed harness

This repo is operated by the `agent-harness` Claude Code plugin: docs-as-memory
knowledge system, taste lints whose FAIL messages carry FIX instructions, and
review personas grounded 1:1 in docs. Session continuity uses Claude Code's
native memory (no feeder/imprint/dream loop). Bootstrapped by the `harness-init`
skill on {{TODAY}}.

## Run it

- Load: `claude --plugin-dir <plugin>` from this repo's root — the plugin's
  location on this machine is recorded in `.git/hooks/pre-commit` (its
  check.py path reveals the plugin dir). Session continuity uses Claude Code's
  native memory — no feeder/imprint loop. Durable knowledge: `docs/adr/`
  (decisions), `docs/exec-plans/tech-debt-tracker.md` (debt/open questions),
  `docs/logs.md` (evolution).
- Gate: run `.git/hooks/pre-commit` — scaffold installs it with this
  machine's exact `check.py` invocation (no placeholders to resolve; rerun
  scaffold.py after moving the repo or plugin and the hook is rewritten).
  Must be GREEN before every commit; the `harness-lint` skill interprets
  failures. `--no-verify` only for emergencies — fix forward right after.
- Navigate docs: the `docs-nav` skill runs `nav.py` (alongside the gate's
  `check.py` in the plugin) — read-only over the corpus, queried from frontmatter
  + the link graph instead of bulk-reading: `map`/`roadmap` (the whole picture /
  progress), `tree`/`relations` (typed relationships), `catalog`/`links`/
  `backlinks`, `followups`, and `stale`/`orphans`/`drift`. Not in the gate.
- Tests in the gate: wired via the `HARNESS_TEST_CMD` env var (e.g.
  `HARNESS_TEST_CMD="pytest -q"`) or `.harness.json` `test_cmd`; default is
  unittest discovery when a `tests/` directory exists, skipped otherwise.
- Host enforcement: this repo's own architecture invariants are mechanized by
  the `architecture-setup` skill (harness-init step 7), routed by FORM — host
  lints under `.claude/lints/` (wired into the gate via `.harness.json`
  `lint_cmd`) for mechanical invariants, guide-skills under `.claude/skills/` for
	  methodology. Override freshness and strictness defaults for this repo in the
	  same file (`stale_days`, `managed_doc_roots`, `doc_governance`). See
	  ARCHITECTURE.md invariant 7; the rules are this repo's, not the machine's.
- Docs governance is tiered: machine-critical docs and harness-managed roots
  (`adr`, `design-docs`, `exec-plans`, `product-specs`) are strict;
  host-owned business/marketing/research docs are flexible unless listed in
  `.harness.json` `managed_doc_roots` or the host sets
  `doc_governance: strict`.
- Plugin component inventory and coverage are self-host strict but advisory for
  external-plugin hosts unless the host opts into `.harness.json`
  `component_inventory: strict` or `component_coverage: strict`.

## Components

| Kind | Name | What it does |
|---|---|---|
{{COMPONENTS}}

## Docs placement

| Knowledge kind | Home |
|---|---|
| Design rationale / principle | `docs/design-docs/` |
| Architectural invariant | `ARCHITECTURE.md` (short) or design-docs |
| Component taste rule | `docs/DESIGN.md` |
| Failure mode / idempotency rule | `docs/RELIABILITY.md` |
| Threat / mitigation | `docs/SECURITY.md` |
| Reusable how-it-works | `docs/design-docs/` |
| Decision + why | `docs/adr/` |
| Known landmine / unresolved question | `docs/exec-plans/tech-debt-tracker.md` |
| Project / docs evolution | `docs/logs.md` |
| Product behavior | `docs/product-specs/` (harness-managed by default) |
| External API facts | `docs/references/` |
| Host-specific business/marketing/curriculum/etc. | Natural `docs/<domain>/` roots chosen during `harness-init` |

Procedure for a new harness-managed page: kebab-case filename → frontmatter
(required `status / last_verified / owner / type / description`, plus `phase` on
product-specs; optional `tags / title`; validate-if-present `resource / supersedes`
— per `docs/KNOWLEDGE_FORMAT.md` KF v2.0) → write → register in that
directory's `index.md` → cross-link → run the gate (the `docs-tree` skill owns
this). The format itself is specified in `docs/KNOWLEDGE_FORMAT.md`.
Host-owned project roots may use the structure that best fits the repo unless
they are opted into managed governance.

`docs/.harnessignore` is a strict-mode migration backlog. Use it only when this
repo opts into global docs governance but still needs declared legacy subtrees.
Harness-managed trees can't be listed there.

## Memory — native (no loop)

The harness ships **no automatic memory loop**. Session continuity uses Claude
Code's native memory; there is no feeder/imprint/dream machine. Durable,
version-controlled knowledge lives in `docs/`:

- **Decisions + why** → `docs/adr/` (ADRs, registered in `docs/adr/index.md`).
- **Deferred work + open questions + limitations** → `docs/exec-plans/tech-debt-tracker.md`.
- **Evolution narrative** → `docs/logs.md` (milestone-grained, read on-demand).
- **Reusable how-it-works** → `docs/design-docs/`.

`garden` (entropy GC) remains a manual tool. The lints still enforce frontmatter,
naming, and index registration on every governed page.

## Growing the grounding docs

`docs/RELIABILITY.md` and `docs/SECURITY.md` start as small seeds. When a
review finding or a human correction surfaces a rule worth keeping, append it
as the next numbered rule (feedback twice → promote). Review personas cite
relevant written rules for taste/contract findings, and may also block on
demonstrable bugs with concrete evidence.
