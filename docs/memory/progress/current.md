---
status: active
last_verified: 2026-06-13
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
- Next: (a) optionally migrate a wave of Lingual's declared legacy trees into
  the convention; (b) open tracker items still pending — threshold-VALUE
  tuning + HARNESS_LINT_CMD (G3), imprint child unscoped Write (path-scoping),
  cleaner `.claude/` runtime/skills split.
