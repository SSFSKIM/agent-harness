---
status: draft
last_verified: 2026-06-14
owner: harness
---
# docs-sync — unified curated-doc maintenance (currency + forgetting)

## Purpose
The harness can ADD knowledge (the dreaming router appends into docs) but has no
robust way to UPDATE or RETRACT curated knowledge when the world changes — so
`AGENTS.md` / `ARCHITECTURE.md` / design-docs drift stale, and a dropped session's
contributed memory is never retracted. Those are the SAME capability — *update /
retract curated docs* — with two triggers: a **code/decision change** (currency)
and a **dropped session's provenance** (forgetting). `docs-sync` is one engine for
both. Modeled on openai-agents-js `.agents/skills/docs-sync` (audit → evidence-backed
report → approve → scoped edit), adapted to our read-only-agent + deterministic-
applicator pattern with a hybrid auto/report safety split.

## Two scopes, one engine
- **Change-driven (currency).** Trigger: the completion gate (an ExecPlan/commit
  completing). Scope: `git diff main...HEAD` — the changed public surface
  (exports/config/behaviors/decisions). "You changed code but not the docs that
  describe it" is caught at the natural review point; diff-scoping keeps it cheap.
- **Provenance-driven (forgetting).** Trigger: a dreaming run. Scope: the journal
  `[routed] … -> docs/X` lines of sessions just dropped from Phase-2 selection —
  revisit `docs/X` and retract/soften the now-unsupported content.

## Components
- **scope builder** — produces the audit input: a change inventory (from the diff)
  or a provenance target set (from the dropped sessions' journal lines).
- **audit agent (read-only: Read/Glob/Grep/LS)** — compares the scope against the
  docs that describe it and emits a **maintenance plan** (JSON). Each item:
  `target` (doc + section), `kind` (`missing|outdated|retract|structural`),
  `evidence` (file:line proving the gap), `change` (the proposed edit), `risk`
  (`mechanical|semantic`). It WRITES NOTHING — it only proposes.
- **applicator (extends `dream_router`)** — reuses the allowlist + the symlink-safe
  within-repo write guard (`harness_lib.within_repo_no_symlink`), now with EDIT/DELETE, not
  just append.
- **Docs Sync Report** — openai-style findings (doc-first / code-first / outdated /
  retract / structural / proposed edits / questions), evidence-backed.

## The safety crux — the "mechanical 4" whitelist
The applicator deterministically RE-VALIDATES each item's `risk` (never trusting the
agent's label) and auto-applies ONLY four mechanical kinds:
1. regenerate a generator-owned section (e.g. the component inventory; drift-proof
   by construction — more such sections as generated-maximize lands);
2. set a frontmatter field (`last_verified`);
3. a verbatim symbol-rename swap — `old` must be a SPECIFIC code symbol/path (it
   carries identifier structure `_ . / -` / a digit / mixed case, so a bare prose
   word like "set" can never trigger a global prose rewrite), `new` is symbol-shaped,
   and `old` is found at a token boundary (a literal replace, no prose authoring);
4. a `retract` DELETE the engine can ATTRIBUTE — a journal `[routed] "snippet" ->
   target` whose snippet PREFIXES the line's content (after stripping the router's
   `- `/`- <date>: `/`| ` framing). Prefix-anchored, not substring-anywhere: a short
   routed phrase can't authorize deleting an unrelated human line that contains it.

Everything else — any free-prose rewrite, an unattributable "should be removed", a
structural reshuffle — is forced to `semantic` and goes to the report. **The machine
never auto-edits curated prose.** This is the whole safety story: append was bounded;
edit/delete is bounded by this whitelist + the allowlist + the symlink guard +
`check.py` re-run with batch rollback on red.

## Data flow
    SCOPE (diff | dropped-provenance)
      -> audit agent (read-only) -> maintenance plan (risk-classed, evidence)
      -> applicator: deterministic risk re-validation
           |- mechanical -> EDIT/DELETE/regenerate -> check.py -> commit (or rollback)
           '- semantic   -> Docs Sync Report -> gate/human approves -> manual apply

## Detection (hybrid)
- Change-driven: the diff's changed files/symbols → (a) docs that REFERENCE them
  (grep), (b) generated sections (regenerate + diff), (c) the agent reasons about
  semantic drift on the changed public surface (openai's doc-first + code-first
  passes).
- Provenance-driven: the journal `[routed] -> docs/X` lines → for a dropped session,
  revisit `docs/X` and propose retract/soften.

## Gate integration (respects "minimal blocking gates")
Only `check.py` blocks a commit — `docs-sync` does NOT hard-block. It is a step in
the completion-gate REVIEW (alongside review-arch/reliability/security): mechanical
fixes are auto-applied + committed; semantic findings surface in the review and are
either addressed before the ExecPlan is declared satisfied or filed as
tech-debt-tracker rows (fix-forward).

## Scope / sequencing
- **v1**: the engine + change-driven (completion-gate) integration + hybrid apply.
- **v1.1 (thin)**: the provenance-forgetting scope (dreaming integration) — same
  engine, only the scope input changes.
- **Out of scope (tracked):** full generated-docs-maximize (do opportunistically; a
  mechanical-kind #1 already covers regenerating existing generated sections); a
  large on-device search tool (scale-gated, see `memory-architecture.md`).

## Relation to existing pieces
Reuses the dreaming write pattern (`dream_router`: read-only agent proposes, the
deterministic allowlist+symlink-safe applicator writes). Revives the dormant
`doc-gardener` role onto this engine (its GC becomes the provenance-forgetting pass).
Builds on the existing drift-proofing the lints already give (D9 inventory coverage,
D4 staleness pressure, D8 indexes) — `docs-sync` turns those passive signals into
proposed actions.

## Open questions
- Exact docs↔code mapping for change-driven detection: pure grep-reference + agent
  reasoning (v1), or an explicit declared mapping later if grep proves too noisy.
- Whether the semantic report, when unaddressed at gate time, auto-creates tracker
  rows or just surfaces (lean: surface in v1, auto-row later).
