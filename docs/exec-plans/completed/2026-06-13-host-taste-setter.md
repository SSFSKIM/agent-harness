---
status: completed
last_verified: 2026-06-13
owner: harness
type: exec-plan
tags: [architecture, taste, lint, host-governance, enforcement]
description: Let a host repo mechanize its own architecture invariants into the deterministic commit gate with the harness hardcoding zero rules — providing only the per-commit substrate and the authoring role for host-owned checks.
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
- [x] M1 (PoC — proves the unknown) `harness_lib.gate_config(root)` parses an
  optional `<root>/.harness.json` (parse-don't-validate: any error → `{}`,
  fail-open like `exempt_roots`). `check.py` adds a `host-lint` step from
  `HARNESS_LINT_CMD` (env) **or** `gate_config(root)["lint_cmd"]`. Toy proof: a
  `.harness.json` whose `lint_cmd` is a one-line always-fail script makes the
  gate exit 1; remove it → exit 0. Unit tests (valid / absent / malformed JSON
  / non-dict / wrong-typed `lint_cmd`).
- [x] M2 `check.py` reads `test_cmd` from config too (env still wins) — closes
  the latent gap where `HARNESS_TEST_CMD` set only in a shell never reaches the
  pre-commit hook. Tests: config `test_cmd` runs; env overrides config.
- [x] M3 `lint_docs.py` D1/D4/D7 read overrides from `gate_config`
  (`size_limits` dict merged over `SIZE_LIMITS`, `default_size_limit`,
  `stale_days`); defaults unchanged when absent; wrong-typed overrides ignored.
  Tests: a 200-line AGENTS.md passes under an override and FAILs without it; a
  bad-typed override falls back to the default.
- [x] M4 The role + wiring. New `architecture-setter` persona
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
- [x] M5 (demonstration) Run the setter method on the live Lingual host
  (`harness-init` branch, main untouched): author one genuine invariant lint
  (lead candidate: locale-parametric), wire `.harness.json`, prove gate GREEN +
  violation→RED, commit to the branch.
- [x] M6 Completion gate: self-review the full diff, then arch / reliability /
  security review (codex per CLAUDE.md) until all SATISFIED.

## Progress log
- 2026-06-13: plan created from the blog re-audit + user course-correction.
- 2026-06-13: M1-M3 done. `gate_config` (fail-open `{}`); `check.py`
  `host-lint`/`tests` steps via `resolve_cmd` (env > config); D1/D4/D7
  thresholds overridable (`_int_or` guard drops bool/non-int). 75 tests (+13).
  End-to-end PoC on the real self-host gate: a `.harness.json` `lint_cmd`
  appears as a `host-lint` step and its exit-1 turns the gate RED; malformed
  config falls open to GREEN.
- 2026-06-13: M4 done. `architecture-setter` agent (constructive counterpart to
  review-arch: derive invariants → classify FORM → author host lints → wire
  `.harness.json` → record in ARCHITECTURE.md), `host-lint.py` template,
  harness-init step 7 (verify→8/writeback→9; scaffold message bumped),
  ARCHITECTURE invariant 7 + gate-invariant clause, DESIGN host-vs-machine
  rule, SECURITY T9 (`.harness.json` Tier-0 exec config), agent-harness.md
  pointers (template + self-host) + AGENTS porting line, inventory regen,
  tracker G3/threshold row resolved. Gate GREEN, 75 tests.
- 2026-06-13: M5 done on the live Lingual host (`harness-init` branch, commit
  d6e953e). The setter's judgment step rejected the naive locale lint (banning
  hardcoded locale strings → 15+ false positives on legit `'ko-KR'` defaults)
  and authored the correct one: L1 = `ALLOWED_LEARNING_LOCALES ⊆
  LEARNING_LOCALE_PROMPT_CONFIG` (the invariant's exact stated coupling, parsed
  from main.py via ast, zero-FP). Wired via `.harness.json` `lint_cmd`; Lingual
  gate GREEN with `== host-lint ==` active; injecting a 7th locale into ALLOWED
  only turned the gate RED with the L1 FIX, revert → GREEN.

## Surprises & discoveries
- **Adding a plugin component retroactively reddened an already-ported host's
  gate.** Shipping the `architecture-setter` agent made Lingual's gate FAIL on
  D9 (component coverage checks the HOST's docs mention every plugin component)
  and `gen_inventory --check` (host inventory lists them). The inventory regen
  is mechanical, but D9 needs a hand-doc mention (`check_coverage` excludes
  `generated/`). So a plugin roster change couples to every ported host's docs.
  Fixed Lingual by resyncing its `agent-harness.md` + inventory; logged the
  coupling as a tracker row (separable from this axis).
- **The setter's value showed on first contact**, blog-style: while picking the
  locale lint, found `tl-PH` is in `ALLOWED_LEARNING_LOCALES` but missing from
  `REALTIME_TRANSCRIPTION_LANGUAGE_HINTS` (chat.py) — real locale drift. Left as
  a noted finding in Lingual's ARCHITECTURE.md (not folded into L1, which keys
  off the authoritative main.py tables).

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
- 2026-06-13 (self-review): `resolve_cmd` does the `shlex.split` itself and
  returns argv-or-None, fail-open on an unparseable command (unbalanced quote)
  — consistent with the harness's pervasive fail-open (gate_config/exempt_roots/
  feeder), and it keeps a malformed `.harness.json` from crashing the gate. The
  absent host-lint step is the visible signal. (Chose fail-open over fail-loud
  for consistency; a present-but-broken wire skipping silently is the accepted
  cost — the author sees `== host-lint ==` is missing when testing.)
- 2026-06-13: LLM-judge (semantic FORM) deferred to v1.x — separate cost /
  flakiness / prompt-design judgment; the setter names semantic invariants but
  routes them to review/defer, not to a gate step, for now.

## Feedback (from completion gate)

Round 1 (codex, gpt-5.5): **arch NOT SATISFIED · reliability NOT SATISFIED ·
security SATISFIED** (with sharp P2s). All addressed:

- **review-arch P1 → fixed:**
  - `resolve_cmd` resolved env/config inside `check.py` (violates "resolution
    only in harness_lib", S2/ARCHITECTURE). → moved to `hl.gate_command`;
    `check.py` is now a thin runner calling it (`_host_step` wrapper).
  - setter named root `ARCHITECTURE.md` as primary authority (DESIGN: non-review
    personas cite a `docs/` path as primary grounding). → reframed: primary
    grounding = `docs/design-docs/core-beliefs.md` + `docs/DESIGN.md`; the host's
    ARCHITECTURE.md is target INPUT (data).
  - setter output contract wasn't P1/P2/Verdict. → amended DESIGN to scope that
    contract to **review** personas; constructive personas (doc-gardener/dreamer/
    setter) report work product (fixes a latent inconsistency for the first two).
  - P2: invariant 7 said lints govern only `plugin/`+`docs/`, but D1/D10 govern
    root `AGENTS.md`/`ARCHITECTURE.md`. → wording fixed in ARCHITECTURE + DESIGN.
- **review-reliability P1 → fixed (empirically reverified):**
  - a missing host command crashed the gate (`FileNotFoundError`). → step run
    loop catches `OSError` → clean `FAIL gate <step>` + FIX.
  - a present-but-unparseable command was silently dropped → gate GREEN.
    → **fail-closed**: `gate_command` raises `ValueError`, `_host_step` turns it
    into a gate failure (the host asked for enforcement; a broken wire is loud).
  - Lingual `locale_parametric.py` false-GREEN if `ALLOWED_LEARNING_LOCALES`
    absent/renamed. → fails loud when it can't parse a non-empty allowed set.
  - P2: `gate_config` accepted non-UTF8 via `errors="replace"`. → strict decode,
    `UnicodeDecodeError` → `{}`.
- **review-security (SATISFIED) P2 → fixed:**
  - malformed `.harness.json` lint_cmd bypass → same fail-closed fix as above.
  - threshold overrides could loosen managed-doc governance (huge `stale_days`/
    `size_limits` un-governs `SECURITY.md`/`MEMORY.md`). → `lint_docs.PROTECTED`
    clamps `MANAGED_DOCS`+`MEMORY.md` to `min(override, default)` (tighten-only);
    SECURITY T9 documents it (mirrors T8). Tests added.
  - setter (Write-capable) lacked a T7-style DATA guard for scanned host code.
    → inline guard added: scanned source/comments/docs are DATA, never followed.

Post-fix: 81 tests green (+ host-command, protected-clamp, non-UTF8 cases);
both gates GREEN; the three reliability exploits reverified to fail clean.

Round 2 (codex): **arch SATISFIED · reliability SATISFIED · security NOT
SATISFIED** — the round-1 PROTECTED clamp was itself buggy. Fixes:

- **review-security (NOT SATISFIED) → fixed:** the clamp keyed on
  `p.parent == docs` + bare name, but the real bootloader is `docs/memory/
  MEMORY.md` (parent `docs/memory`), so it was **never protected** — T9 claimed a
  guarantee the code didn't deliver. Reworked to `PROTECTED_PATHS` (repo-relative
  paths: `docs/<MANAGED_DOC>` + `docs/memory/MEMORY.md`); empirically verified a
  `size_limits:{MEMORY.md:9999}` override no longer loosens the bootloader. T9
  reworded: size clamped for all; D4 staleness clamped for MANAGED_DOCS only (the
  bootloader is D4-exempt — `check_frontmatter` skips MEMORY.md). +MEMORY fixture.
- **review-arch P2 → fixed:** invariant 3 wording implied the host test command
  was additive to unittest; reworded to "replaces the default". dreamer.md
  relabeled SECURITY.md as a constraint (not co-authority), per the sharpened
  DESIGN rule.
- **review-reliability P2 → fixed:** stale `check.resolve_cmd` name in SECURITY
  T9 → `hl.gate_command`/`check._host_step`; `check_sizes` now `_int_or`-coerces
  its limit args so a direct fixture call with a bad-typed limit can't TypeError.

Post-fix: 82 tests green; both gates GREEN; MEMORY.md clamp reverified.

Round 3 (codex, security re-confirm): **SATISFIED, no findings.** All three
lenses SATISFIED → gate passed.

## Outcomes & retrospective
Shipped the **setter axis**: a host mechanizes its OWN architecture invariants
into the deterministic gate with the harness hardcoding zero rules. Substrate =
`harness_lib.gate_config` (optional `.harness.json`) + `gate_command` + the
`check.py` `host-lint` step + per-repo threshold overrides (D1/D7/D4 become
defaults, not mandates, clamped so they can only tighten the harness's own
managed docs). Role = the new `architecture-setter` persona (constructive
counterpart to review-arch): derive invariants → classify FORM (deterministic
lint / judge-deferred / persona / fix-forward) → author host lints under
`.claude/lints/` → wire `.harness.json` → record the invariant→FORM map. Proven
end-to-end on the live Lingual host (L1 locale-parametric lint: GREEN now,
RED on a violation, revert GREEN). 82 tests. Resolves the G3/threshold tracker
row; LLM-judge (the semantic FORM) deferred to v1.x.

Retrospective:
- **The completion gate paid off a 4th consecutive time — and caught a
  self-referential bug.** My round-1 security fix (the PROTECTED clamp) *claimed*
  in SECURITY T9 to protect the memory bootloader but keyed on `parent == docs`,
  so it never reached `docs/memory/MEMORY.md` — the doc asserted a guarantee the
  code didn't deliver. Self-review + 81 green tests missed it (the tests used a
  top-level `SECURITY.md` fixture, blind to the bootloader's real path). Only an
  adversarial reviewer checking the *exact protected path* surfaced it. Same
  fixture-blindness lesson as host-legacy-docs: test at the boundary (the real
  path), not the convenient center.
- **fail-open vs fail-closed is per-seam, not global.** I defaulted to fail-open
  for consistency; two reviewers independently converged that a *present-but-
  broken* enforcement wire must fail LOUD (the host declared intent to enforce).
  Config-absent → skip; config-present-but-broken → block. The harness's
  fail-open philosophy is right for *defaults*, wrong for *declared enforcement*.
- **The setter's judgment IS the product.** The iconic demo lint only worked
  because the persona's FORM-triage rejected the naive "ban hardcoded locale
  strings" (15+ false positives on legit defaults) for the completeness check
  (`ALLOWED ⊆ PROMPT_CONFIG`, zero FP) — same invariant, opposite lint quality.
  A blind lint-generator would have shipped the bad one.
- **Layer-law caught the cross-cutting drift:** review-arch flagged that command
  resolution had leaked into check.py; moving it to `harness_lib.gate_command`
  kept the single-resolver invariant (S2) intact. The lint (S2 token-scan)
  couldn't see env resolution — the persona, grounded in the prose invariant,
  could. Deterministic + judgment layers are complementary, exactly the thesis.

Follow-on (not this plan): dispatch the architecture-setter as a live agent on
the next host (it's only been run inline); the D9/inventory cross-host coupling
tracker row; the imprint-write-scoping item that hardens T9's Tier-0 framing.
