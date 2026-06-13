---
status: active
last_verified: 2026-06-14
owner: dreamer
---
# Current state

- Phase 0-6 complete: foundation docs, lint gate, skills, personas, STORE tree,
  2-stage INJECT, IMPRINT queue, CONSOLIDATE (dreaming).
- Completion gate (Task 17) passed: 2 real P1s caught and fixed
  (per-entry exception isolation in imprint_run.py; prompt-injection encoding
  in feeder_firstprompt.py). Gate commit fe3308a.
- §7 success criteria validated (Task 18): 4/4 PASS.
  - Criterion 1 (self-hosting loop): PASS — live plugin session oriented from
    context pack, fixed tech-debt m4, dispatched review-arch Task in-plugin.
  - Criterion 2 (continuity): PASS with staleness caveat (see
    docs/memory/limitations/progress-staleness.md).
  - Criterion 3 (dreaming lint-green): PASS.
  - Criterion 4 (human touchpoints): PASS.
- Wiki file-back (Task 19) complete — Q37 closed in the vault wiki
  (agent-harness-v1-buildlog); v1 build done.
- 2026-06-12 post-v1: `harness-init` skill added — ports the harness into a
  new/existing host repo (scaffold.py + 11 seed templates + migration
  playbook + 6 tests incl. fresh-host-lint-green). check.py now skips the
  tests step when the host has no tests/ dir.
- 2026-06-12 (later): ExecPlan `portability-hardening` M1-M7 done — vault gap
  analysis (blog vs repo) + OpenAI public-repo evidence research drove:
  S7 lint (no self-host paths in plugin markdown), D10 lint + scaffold seeds
  for machine-read docs, pre-commit gate hook, Stop-hook tidy (R11,
  block-once), PLANS.md upstream quality rules, harness-init steps for
  instance skills (.claude/skills/) + app-verify. Gate (M8) PASSED
  2026-06-13: arch caught a real P1 (placeholder gate indirection in the
  host template — resolved: the pre-commit hook IS the recorded gate
  command); reliability/security P2s hardened tidy_stop (crash≠FAIL,
  timeouts, atomic write, T7 DATA guard). Plan → completed/.
- 2026-06-13: host-legacy-docs ExecPlan completed (gate SATISFIED x3) —
  `docs/.harnessignore` lets a doc-heavy host scope which docs the content
  lints govern; segment-boundary matching + MANAGED_ROOTS/MANAGED_DOCS keep
  the harness tree non-exemptable. Commits 14e0061→4576b28→2504488.
- 2026-06-13: **second target ported** — agent-harness bootstrapped into the
  real Lingual-Project (Flask+Firestore+React, ~80 legacy docs) on a branch
  (`harness-init`, main untouched), doc gate GREEN, mechanically enforced by
  the installed pre-commit hook. Two portability findings, both resolved:
  1. Lint scoped all of `docs/` as harness-owned → 74 legacy D3/D6/D7 fails on
     a doc-heavy host. Fixed generally by `docs/.harnessignore` (above).
  2. harness-init's "gut CLAUDE.md to a 3-line pointer" default is over-specific
     for a doc-sophisticated host (Lingual has a working layered CLAUDE.md +
     AGENTS.md split). Fixed: step 3 now branches — additive graft (AGENTS.md
     canonical, CLAUDE.md keeps content + pointer header, relocate only
     duplication) for such hosts; declare pre-existing trees legacy.
- 2026-06-13: post-port harness polish (3 more findings from the Lingual run,
  all fix-forward, 62 tests green): harness-init step 7 FILL grep scoped to
  `*.md` (data files like CSV legitimately contain the substring); step 6 +
  `templates/verify-skill.md` make the instance `verify` skill turnkey and
  document that `.claude/`-ignoring hosts need `git add -f` for skills to
  travel; scaffold detects a blanket `.claude/` ignore → emits a NOTE instead
  of a redundant ignore line. Structural tension (gitignored runtime +
  must-travel skills both under `.claude/`) logged to the tracker.
- 2026-06-13: **automatic memory loop DISABLED** (user decision — needs a more
  sophisticated redesign first). Unwired the SessionStart/UserPromptSubmit
  (feeder) + PreCompact/SessionEnd (imprint) hooks from `hooks.json`; only the
  Stop tidy-gate remains. Scripts (`feeder_*`/`imprint_*`) + dream/garden
  skills retained dormant; `docs/memory/` now hand-maintained (still
  lint-governed). Redesign captured in
  `docs/memory/openq/memory-loop-redesign.md`. ARCHITECTURE data flows +
  agent-harness.md (self-host + template) updated to say so.
- 2026-06-13: flexible host governance maturity step implemented in active
  ExecPlan `flexible-host-governance`: ported hosts now keep only
  machine-critical docs + harness-managed roots strict by default; host-owned
  project docs under `docs/` stay flexible unless opted into `.harness.json`
  `managed_doc_roots` / `doc_governance: strict`. D9 component coverage now
  defaults to self-host only (`component_coverage: strict` opt-in for ported
  hosts), and generated component inventory is advisory for external-plugin
  hosts unless `component_inventory: strict`. ExecPlans gained `review_level`
  (`none`/`targeted`/`standard`/`full`);
  review personas now treat grounding docs as taste/contract authority while
  still allowing demonstrable bug findings. Negative-space command language was
  replaced with preferred-path + promote-if-repeated guidance. Gate GREEN
  (89 tests). Formal subagent review not dispatched in this environment because
  subagent tools require explicit user authorization.
- 2026-06-14 follow-up: `docs/product-specs/` is back in the default governed
  surface. Product intent is machine-critical enough for harness decisions, so
  ported hosts keep machine-critical docs + product specs + harness-managed
  roots strict by default. Additional host-owned roots such as
  business/marketing/research/curriculum stay flexible unless opted in;
  `docs/references/` remains host-owned/advisory by default.
- 2026-06-14: **Product Design entry mode** added (ExecPlan
  `product-design-phase`, completed). A spec-first phase now sits in front of the
  ExecPlan methodology: before work the agent picks an entry mode by judgment
  (throwaway / Product Design / ExecPlan), and when the *what* outlives a single
  plan, fans out, or needs independent verification, it writes a durable spec in
  `docs/product-specs/` (new `product-design` skill) that ExecPlans reference
  instead of re-deriving. Wired into PLANS.md + AGENTS.md (and both harness-init
  seeds), core-beliefs #12, execplan Context. This adopts superpowers'
  front-loading as a *separable artifact*, not a human gate — Product Design is
  the one place product-direction escalation lands; ExecPlan stays fully
  autonomous. Gate GREEN (92 tests); codex review-arch caught one P1 (host
  AGENTS.md seed missed the entry decision) → fixed.
- Next: (a) memory-loop redesign (openq) — the deferred sophistication;
  (b) optionally migrate a wave of Lingual's declared legacy trees;
  (c) complete review/close `flexible-host-governance` if subagent dispatch is
  authorized; (d) open tracker items — imprint child unscoped Write, cleaner
  `.claude/` runtime/skills split.
