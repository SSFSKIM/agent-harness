---
status: active
last_verified: 2026-06-13
owner: harness
base_commit: 4a2f29f29618144ef1f740f0b3a53e116be63abf
---
# Host-owned architecture & taste enforcement (the setter axis)

## Goal
A host repo can mechanize **its own** architecture invariants into the
deterministic commit gate, with the harness hardcoding **zero** of the rules —
only the substrate and the authoring role. "Architecture invariant" = a
property the host's app code must always hold (e.g. "learning-locale codes
appear only in the sanctioned config"). "Substrate" = the injection point that
runs a host-authored check on every commit. Demonstrable, three observable
behaviors:

1. **Injection works and persists to the hook.** A host with
   `.harness.json` → `{"lint_cmd": "<cmd>"}` makes `check.py` run `<cmd>` as a
   gate step; if `<cmd>` exits nonzero the gate is RED and the commit is
   blocked by the scaffold-installed `.git/hooks/pre-commit`. Remove the key →
   GREEN. (The pre-commit hook injects no env, so the wiring MUST be a
   versioned file, not an env var — that is the load-bearing fact this proves.)
2. **Our taste is a default, not a mandate.** A repo whose map legitimately
   runs long (the public `openai/codex` AGENTS.md is 295 lines) sets
   `.harness.json` → `{"size_limits": {"AGENTS.md": 300}}` and D1/D7 stop
   failing — without editing any plugin source. Absent config → today's
   defaults (120/400/60/30d) still enforce.
3. **A real host authors a real rule.** Running the new `architecture-setter`
   persona against the live Lingual host produces ≥1 deterministic lint encoding
   a genuine Lingual invariant, wired via `.harness.json`; the Lingual gate
   stays GREEN, and deliberately introducing a violation turns it RED with a
   FIX-bearing message.

## Context
This plan implements the synthesis from the 2026-06-13 blog re-audit
(`harness-blog-gap-analysis.md` G3 + the user's course-correction): the blog's
central axis — "아키텍처 및 취향 강제 적용" via *Codex-generated, per-repo*
custom linters — is the one axis the harness must NOT hardcode. Today our
enforcement (lints S1–S7, D1–D10) is 100% deterministic AND applies only to the
harness's own structure (`plugin/`, `docs/`); a host's app code gets zero
enforcement, and the thresholds (D1 120 / D4 30d / D7 400) are our universal
opinion frozen as constants — the same monolithic-manual anti-pattern the blog
rejects for AGENTS.md, committed at the lint layer.

The fix separates three things we had collapsed: **WHAT** to enforce
(per-repo, agent-derived — never us), **WHO** authors the enforcement (a
per-repo persona, the "setter"), and the **FORM** enforcement takes at runtime
(deterministic lint for mechanical invariants — kept, because determinism is a
cheap reproducible floor, not rigidity; LLM-judge for semantic ones — deferred
to v1.x; persona-review or fix-forward otherwise). Rigidity came from *our
universal hardcoding*, not from the deterministic runtime; the cure is to move
authoring to the repo, not to delete the substrate. A repo with no
mechanizable invariant authors zero lints — the lint count is a per-project
judgment output, not a top-down mandate.

Resolves the tracker's open row: "Lint thresholds … and HARNESS_LINT_CMD
remain open; design one host-config mechanism jointly … driven by which
constants the target actually fights." LLM-judge (the third gate FORM) is
explicitly out of scope (v1.x) per the user decision.

Key files: `plugin/scripts/harness_lib.py` (the only path/env/config
resolver — S2), `plugin/scripts/check.py` (the gate), `plugin/scripts/lint_docs.py`
(D1/D4/D7), `plugin/agents/` (personas, e.g. `review-arch.md` — the setter is
its constructive counterpart), `plugin/skills/harness-init/SKILL.md` (port flow).

## Milestones
- [ ] M1 (PoC — proves the unknown) `harness_lib.gate_config(root)` parses an
  optional `<root>/.harness.json` (parse-don't-validate: any error → `{}`,
  fail-open like `exempt_roots`). `check.py` adds a `host-lint` step from
  `HARNESS_LINT_CMD` (env) **or** `gate_config(root)["lint_cmd"]`. Toy proof: a
  `.harness.json` whose `lint_cmd` is a one-line always-fail script makes the
  gate exit 1; remove it → exit 0. Unit tests (valid / absent / malformed JSON
  / non-dict / wrong-typed `lint_cmd`).
- [ ] M2 `check.py` reads `test_cmd` from config too (env still wins) — closes
  the latent gap where `HARNESS_TEST_CMD` set only in a shell never reaches the
  pre-commit hook. Tests: config `test_cmd` runs; env overrides config.
- [ ] M3 `lint_docs.py` D1/D4/D7 read overrides from `gate_config`
  (`size_limits` dict merged over `SIZE_LIMITS`, `default_size_limit`,
  `stale_days`); defaults unchanged when absent; wrong-typed overrides ignored.
  Tests: a 200-line AGENTS.md passes under an override and FAILs without it; a
  bad-typed override falls back to the default.
- [ ] M4 The role + wiring. New `architecture-setter` persona
  (`plugin/agents/architecture-setter.md`, Write-capable, grounded in the
  host's ARCHITECTURE.md + core-beliefs #4) that derives the host layer law +
  invariants, classifies each by FORM, authors deterministic lints under
  `.claude/lints/` with FIX-embedded errors, wires `.harness.json`, and records
  the invariant→FORM map in ARCHITECTURE.md. New `host-lint.py` template (FIX
  format + exit contract). harness-init step (dispatch the setter; note the
  threshold-override escape). ARCHITECTURE invariant 7 + DESIGN rule + SECURITY
  T9 (`.harness.json` lint_cmd/test_cmd is Tier-0 executable config) +
  agent-harness.md template pointer + self-host AGENTS.md map row +
  component-inventory regen + tracker row resolved.
- [ ] M5 (demonstration) Run the setter method on the live Lingual host
  (`harness-init` branch, main untouched): author one genuine invariant lint
  (lead candidate: locale-parametric), wire `.harness.json`, prove gate GREEN +
  violation→RED, commit to the branch.
- [ ] M6 Completion gate: self-review the full diff, then arch / reliability /
  security review (codex per CLAUDE.md) until all SATISFIED.

## Progress log
- 2026-06-13: plan created from the blog re-audit + user course-correction.

## Surprises & discoveries

## Decision log
- 2026-06-13: persistence via a versioned `<root>/.harness.json`, not an env
  var — the pre-commit hook is `exec python3 check.py --root <root>` with no env
  injection, so only a committed file makes a host lint run on *every* commit
  (the whole point: catch the invariant even when the session isn't looking).
  Env vars are kept as an ad-hoc override (precedence over config).
- 2026-06-13: the setter is an **agent** (constructive persona, like
  doc-gardener/dreamer), not a skill — dispatched by harness-init and re-run
  when the architecture evolves; it is the constructive counterpart to the
  review-arch *review* persona.
- 2026-06-13: `gate_config` lives in `harness_lib` (the sole cross-cutting
  resolver, S2); `check.py` and `lint_docs.py` each read it via the lib in
  their own `main()`, mirroring how `host = hl.exempt_roots(root)` is already
  threaded.
- 2026-06-13: LLM-judge (semantic FORM) deferred to v1.x — separate cost /
  flakiness / prompt-design judgment; the setter names semantic invariants but
  routes them to review/defer, not to a gate step, for now.

## Feedback (from completion gate)

## Outcomes & retrospective
