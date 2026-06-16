---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: 21d63c6670683fd9c6bf8d421ce15668d3e98809
review_level: standard
---
# Director declarative config (`.harness.json` `director` block)

## Goal
Director orchestration policy that is today scattered across code constants and
`argparse` defaults becomes a single repo-owned, version-controlled `director`
block in the existing `<root>/.harness.json`. Definition of done (observable): a
new `director/config.py` exists; `python3 -m director.config` prints the resolved
effective config as JSON; with a `director` block declaring a different `team`,
`states`, `concurrency`, and worker `posture`, `python3 -m director.orchestrator
--mock` drives using those values **without any code or flag edit**; a CLI flag
still overrides the config value (CLI > config > default); an **absent** block
runs byte-identically to today (defaults), while a **present-but-malformed** block
fails loud at startup **before any worker spawns**; and `$VAR`/`${VAR}` string
values resolve from the environment. `python3 plugin/scripts/check.py` is GREEN.

## Context
- **Spec (owns the design — do not re-derive):**
  `docs/product-specs/2026-06-16-director-declarative-config.md` — R1–R7,
  D-54..D-58. This plan owns the *build*.
- **Why now:** the gap-analysis artifact
  `docs/design-docs/symphony-parity-gap.md` (the "WORKFLOW.md / §5–6 declarative
  contract" gap, #4) — the human-chosen next move toward Symphony parity.
- **Symphony oracle:** `docs/symphony-original/SPEC.md` §5 (WORKFLOW.md format),
  §6 (config resolution pipeline, `$VAR`, reload), §6.4 (config cheat-sheet).
- **Existing precedent this must follow:**
  - `director/worker/policy.py` — `discover_root()` (walk up to `.harness.json`),
    `load_worker_policy()` (absent → deny-default; **malformed → raise**). The
    `director` block reuses `discover_root`; its validation mirrors this
    fail-loud-on-malformed discipline.
  - `plugin/scripts/harness_lib.py` `gate_config()` (parse-don't-validate,
    **fail-open to `{}`**) and `gate_command()` (env var > `.harness.json` value —
    the precedence shape we mirror as CLI > config).
  - `ARCHITECTURE.md` "Host runtime (`director/`) invariants": stdlib-only (no
    YAML), explicit `base=`/`root=`, pure core + thin transport.
- **Knobs in scope (from spec R2):** `team`, `states`
  (ready/started/done/failed/blocked → Linear state names), `concurrency`,
  `max_turns`, `max_passes`, `max_dispatched`, `done_types`, `read_timeout_s`,
  `turn_review_timeout_s`, `codex_command`, worker `posture`
  (approval_policy/sandbox/auto_review/network), `paths`
  (workspace_root/queue_dir/status_dir), `merger` (poll_s/read_timeout_s/
  max_merges). **Out of scope (spec R3, stays code):** taxonomy stage templates,
  `TERMINAL_CONTRACT`, queue schema, disposition kinds, `policy._BASE_NAMES`,
  label→type priority, `worker_policy` (already externalized).

## Approach (self-generated alternatives)
- **A — config owns DEFAULTS as literals; old constants become references into
  it; config imports only `policy` + stdlib.** Move the few defaults that live in
  modules which will import config (`orchestrator.DEFAULT_STATE_NAMES`,
  `run.DEFAULT_WORKSPACE_ROOT`/`DEFAULT_MAX_TURNS`, and the posture literals from
  `autonomy.py`) into `config.DEFAULTS`; redefine the old names as thin aliases
  (`autonomy.APPROVAL_POLICY = config.DEFAULTS["posture"]["approval_policy"]`,
  etc.) so direct callers/tests are unchanged and there is exactly one source.
  Trade-off: touches three modules' constant definitions, but guarantees a clean
  acyclic graph (`config → policy` only; everyone else `→ config`).
- **B — separate `director/defaults.py` that both config and the modules
  import.** Avoids moving constants "into" config. Trade-off: an extra module
  whose only job is to dodge a cycle the spec already anticipated; config still
  has to own the merge/resolve logic, so the default *values* and the *resolution*
  end up split across two files for no behavioral gain.
- **Chosen: A.** It realizes the spec's "DEFAULTS = single source of truth in
  config.py" literally, keeps the dependency DAG obviously acyclic (verified:
  `policy.py` imports only stdlib; `autonomy.py` imports nothing from `director`
  today, so the alias edge `autonomy → config` cannot cycle), and the alias trick
  means zero behavior change for any code path that doesn't supply a config.

## Assumptions & open questions (self-interrogation)
- **Assumption:** the repo's current `.harness.json` has **no** `director` key
  (confirmed — it holds only `worker_policy`), so every existing test that runs
  `main()` resolves to `DEFAULTS` and stays byte-identical. *Breaks if* a test
  fixture introduces a `director` block; none does today.
- **Assumption:** `autonomy.py` imports nothing from `director` (confirmed by
  read), so making its posture constants alias `config.DEFAULTS` introduces the
  single edge `autonomy → config` with no back-edge. *Breaks if* config ever
  needs something from autonomy — it won't (config owns the posture literals).
- **Open:** dataclass vs dict for the resolved config → **resolved: frozen
  `DirectorConfig` with nested frozen `Posture`/`Paths`/`Merger`** — typed
  attribute access makes a typo an `AttributeError` at the call site, and frozen
  prevents a consumer mutating shared policy (mirrors the snapshot discipline).
- **Open:** where `$VAR` resolution applies → **resolved: to every string *leaf*
  value in the `director` block** (content-triggered per spec R5/Symphony §6.1 —
  a real value is never exactly `$NAME`), recursively, during load, before type
  validation. A `$VAR` that is unset/empty becomes `None` (missing).
- **Open:** `team` requiredness → **resolved: `config` does not force it**
  (`run.main`/`merger.main` don't need a team); only `orchestrator.main` errors
  with a clear "team not configured (set director.team or --team)" when both the
  flag and config resolve to `None`. This keeps config reusable across the three
  entrypoints.
- **Open:** does validating `approval_policy`/`sandbox` against a fixed enum risk
  rejecting a future Codex value? → **resolved: validate against the known set but
  treat it as the documented contract** (spec says "posture 미지 값 → raise"); a
  new Codex value is a deliberate config-schema change, exactly like adding a knob.

## Milestones

- **M1 — `director/config.py`: the pure loader (core, socket-free,
  unit-tested).** Scope: the whole resolution core with no wiring into the
  orchestrator yet. At the end there newly exists `director/config.py` with:
  `DEFAULTS` (a dict owning every in-scope knob's default value, including the
  posture literals and the `states`/path/`max_*` defaults moved out of
  orchestrator/run — with the T11 posture rationale relocated as a comment beside
  them); frozen dataclasses `Posture`, `Paths`, `Merger`, `DirectorConfig`;
  `_resolve_env(value)` (`$NAME`/`${NAME}` → `os.environ`, unset/empty → `None`);
  `load_director_config(root=None, *, environ=None) -> DirectorConfig` (reuse
  `policy.discover_root`; absent file/`director` key → `DEFAULTS`; present →
  deep-merge over defaults, `$VAR`-resolve string leaves, then validate types and
  fail **loud** (raise `ValueError`) on a non-dict block, a wrong-typed scalar, a
  non-positive bound, a bad state-map shape, or an unknown posture value); and a
  `main(argv)` for `python3 -m director.config [--root R]` that prints
  `json.dumps(asdict(cfg))`. New `tests/test_director_config.py` proves: absent →
  defaults; partial block → merged (unspecified keys keep defaults); each malformed
  shape → raises with a message naming the offending key; `$VAR` resolves from a
  supplied `environ` and unset → `None`; `python3 -m director.config` emits valid
  JSON. Run: `python3 -m unittest tests.test_director_config -v` and `python3 -m
  director.config`. Acceptance: all new tests pass; the CLI prints the default
  config when no block is present.

- **M2 — relocate constants + wire CLI > config > default at the three
  `main()`s.** Scope: make `orchestrator.main`, `run.main`, `merger.main` resolve
  every in-scope knob through the config, and turn the old module constants into
  aliases of `config.DEFAULTS` (Approach A). At the end: `autonomy.APPROVAL_POLICY/
  SANDBOX/AUTO_REVIEW/NETWORK`, `orchestrator.DEFAULT_STATE_NAMES`,
  `run.DEFAULT_WORKSPACE_ROOT/DEFAULT_MAX_TURNS` reference `config.DEFAULTS` (single
  source, identical values); `autonomy.codex_command(base, *, auto_review=True,
  network=True)` gains posture toggles (defaults preserve current behavior); each
  `main()` parses args with `None` sentinels for config-backed flags, calls
  `load_director_config()`, and resolves each knob as `cli if cli is not None else
  cfg.<knob>`; `--team` becomes optional and `orchestrator.main` raises the
  "team not configured" startup error when neither source supplies it (before any
  board read or worker spawn). Tests (extend `tests/test_director_config.py` or add
  to the orchestrator tests): a `director` block changes the mock run's resolved
  `states`/`concurrency`/posture; a CLI flag overrides the same config key; a
  malformed block makes `orchestrator.main` exit non-zero with **zero** workers
  dispatched (assert via the `MockBoard` transitions being empty). Run: `python3
  plugin/scripts/check.py`. Acceptance: gate GREEN (≥349 existing tests still pass,
  proving no-config behavior is byte-identical) **plus** the new precedence /
  config-driven / fail-loud tests; `python3 -m director.orchestrator --mock` still
  drains cleanly with no `director` block, and drains using config values when one
  is present.

- **M3 — docs + cross-links.** Scope: make the new surface discoverable and close
  the doc graph. At the end: `docs/DIRECTOR.md` documents the `.harness.json`
  `director` block (the knob list + that operators edit it and read it back with
  `python3 -m director.config`, load-once semantics) in a short section near §1;
  the spec `docs/product-specs/2026-06-16-director-declarative-config.md` gains the
  **reverse cross-link** to `docs/design-docs/symphony-parity-gap.md` (replacing
  the prose "직전 hollistic gap analysis" with the file link); and
  `ARCHITECTURE.md`'s `director/` invariants note that operator/deployment policy
  is externalized to `.harness.json` `director` (config is the resolution point)
  if it sharpens invariant 7's intent. Run: `python3 plugin/scripts/check.py`.
  Acceptance: gate GREEN (lint_docs passes — frontmatter, index registration,
  cross-links resolve).

## Progress log
- [x] (2026-06-16) Plan created; base_commit 21d63c6, review_level standard.
- [x] (2026-06-16) M1 — `director/config.py` (DEFAULTS, frozen DirectorConfig/
  Posture/Paths/Merger, `$VAR` resolver, fail-loud/open validation, `python3 -m
  director.config` surface) + `tests/test_director_config.py` (19 tests). Gate
  GREEN at 368 tests. Refinement vs plan: paths are OPTIONAL overrides (None =
  module built-in), so `run.DEFAULT_WORKSPACE_ROOT` stays in run.py — config.paths
  layers on top, not a relocation (see Decision log).
- [x] (2026-06-16) M2 — constant relocation + CLI>config>default wiring at all
  three `main()`s. `autonomy.APPROVAL_POLICY/SANDBOX` + `orchestrator.DEFAULT_STATE_NAMES`
  + `run.DEFAULT_MAX_TURNS` now alias `config.DEFAULTS`; `autonomy.codex_command`
  gained `auto_review`/`network` toggles; `orchestrator.resolve_settings` (pure) +
  `merger.run_loop(max_merges=...)`. Updated `tests/test_director_autonomy.py` to the
  new `_command` signature (+ a tighten-via-posture test) and added `WiringTest`
  (precedence, malformed→fail-loud-before-dispatch, missing-team→SystemExit). Gate
  GREEN at 374. Live-proved: `cd tmp && python3 -m director.orchestrator --mock --once`
  with **no `--team`** drained both demo tickets — team/concurrency/states all from a
  `.harness.json` `director` block (the headline "drop config, no flags" goal).
- [x] (2026-06-16) M3 — docs + cross-links. DIRECTOR.md §11 (the `.harness.json`
  `director` block: knobs, `python3 -m director.config`, precedence, `$VAR`,
  load-once, fail-loud); spec gets the reverse link to symphony-parity-gap.md;
  ARCHITECTURE.md `director/` invariant 5 ("deployment policy is declarative, not
  code"). Gate GREEN at 374.

## Surprises & discoveries
- 2026-06-16: `tests/` has no `__init__.py` — the gate runs `unittest discover -s
  tests`, so `python3 -m unittest tests.test_X` fails (ModuleNotFoundError); use
  discovery (`-p 'test_director_config.py'`) to run one file.

## Decision log
- 2026-06-16: **paths = optional overrides (None = module built-in), not a
  relocation.** `config.DEFAULTS["paths"]` is all-None; the built-in workspace path
  stays `run.DEFAULT_WORKSPACE_ROOT` and queue/status keep `_root(base=None)`. This
  is less churn and behavior-preserving (matches the existing `--workspace-root`/
  `--queue-dir`/`--status-dir` None-default flags). Only the scalar/states defaults
  are owned by config; M2 aliases those.
- 2026-06-16: **Approach A (config owns DEFAULTS; old constants alias it).** One
  source of truth, provably acyclic import graph (`config → policy` only).
- 2026-06-16: **`team` not required by config; only `orchestrator.main` enforces
  it.** Keeps the one config loader reusable across orchestrator/run/merger.
- 2026-06-16: **`$VAR` resolution is content-triggered on string leaves**
  (Symphony §6.1), unset/empty → `None` (missing), applied before type validation.
- 2026-06-16: **frozen `DirectorConfig` + nested frozen `Posture`/`Paths`/`Merger`**
  for typed access and immutability of shared policy.

## Feedback (from completion gate)

## Outcomes & retrospective
