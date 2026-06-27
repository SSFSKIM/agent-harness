# ARCHITECTURE.md

Codemap + invariants. Read this before modifying `plugin/`.

## Two layers, one repo

- **Instance** (repo root): `AGENTS.md`, `ARCHITECTURE.md`, `docs/` — the
  knowledge base + structured memory of THIS repo.
- **Machine** (`plugin/`): a portable Claude Code plugin. Installed into another
  repo, that repo brings its own instance layer; the machine stays unchanged.

## Layer law (dependency direction — enforced by lint_structure.py)

`scripts → skills → agents → hooks` (left = lowest; an arrow means "may be
referenced by"; nothing references rightward).

- `plugin/scripts/` — pure stdlib python3; all logic lives here.
- `plugin/skills/` — procedures (SKILL.md); may instruct running scripts.
- `plugin/agents/` — personas dispatched by the main session; may follow skills.
- `plugin/hooks/hooks.json` — thin wiring only: every command invokes a script
  via `${CLAUDE_PLUGIN_ROOT}`; hooks contain no logic.

**Cross-cutting rule (Providers analog):** path/env/frontmatter resolution
exists ONLY in `plugin/scripts/harness_lib.py`. Other scripts never call
`os.getcwd()` / `Path.cwd()` / `CLAUDE_PROJECT_DIR` directly (lint S2).

**Prose exceptions:** the layer law governs imports/invocation. Scripts MAY
read skill-owned *data* (harness-init seed templates), and FIX texts MAY
point rightward at skills — the most actionable instruction wins.

## Invariants

1. **Portability:** nothing in `plugin/` hardcodes an absolute path (lint S3).
2. **Headless recursion guard:** every hook entry script exits immediately when
   `HARNESS_HEADLESS=1`; every spawned `claude -p` child sets it. Without this:
   SessionStart → feeder spawns claude → its SessionStart → ∞.
3. **Deterministic gate:** `check.py` = lint_structure + lint_docs +
   gen_inventory --check (strict for self-host; advisory for external-plugin
   hosts unless `.harness.json` `component_inventory: strict`) + an optional
   host-lint step (invariant 7) + the test step — a host test command from
   `.harness.json`/env, else unittest discovery when a `tests/` dir exists (the
   host command replaces the default, it is not additive). GREEN before every
   commit.
4. **Generated files** carry a GENERATED header; only scripts write them.
5. **Runtime state** (queues, locks, seen-sessions, processed-log) lives in
   `.claude/harness/` — gitignored, never under `docs/`. Tracked central-agent
   operating config (`.claude/DIRECTOR.md`, `settings.json`) likewise belongs in
   `.claude/`, not the `docs/` knowledge graph: `docs/` is the project's
   knowledge base, `.claude/` is how the agent itself is configured.
6. **Tiered docs governance:** machine-critical docs and harness-managed roots
   (`adr`, `design-docs`, `exec-plans`, `product-specs`) are strict by
   default. Host-owned business/marketing/research docs under `docs/` are
   flexible unless the host opts a root into `.harness.json`
   `managed_doc_roots` or sets `doc_governance: strict`. `docs/.harnessignore`
   is now a strict-mode
   migration tool, matched on path-segment boundaries; harness-managed roots
   (`hl.MANAGED_ROOTS`) and top-level machine docs (`hl.MANAGED_DOCS`) are never
   exemptable.
7. **Host-owned enforcement (the setter axis):** the built-in lints
   (S/D series) enforce only the harness's OWN structure (`plugin/`,
   `docs/`, and the root map docs `AGENTS.md`/`ARCHITECTURE.md`). A host's
   app-code invariants are not hardcoded by the machine —
   the `architecture-setup` **skill** (run with the repo's full context) derives
   them per-repo and routes each by FORM: **lints** under `.claude/lints/` for
   mechanical invariants (wired into the gate via `<root>/.harness.json`
   `lint_cmd` — `hl.gate_config`; `check.py` runs it as the `host-lint` step),
   **guide-skills** under `.claude/skills/` for methodology. The harness ships
   the substrate (the gate step, the `FAIL … FIX:` contract, the override knobs)
   and the authoring method — never the rules; the lint and skill sets are the
   host's output (zero of either is valid). Harness
   freshness defaults (D4 30d) are per-repo overridable via the same file
   (`stale_days`); component inventory/coverage can be made strict explicitly
   (`component_inventory`, `component_coverage`). Absent → defaults unchanged.
   `lint_cmd`/`test_cmd` are executable config that run every commit
   (SECURITY.md T9).

## Data flows

> **The harness ships no automatic memory loop.** The old INJECT/IMPRINT/
> CONSOLIDATE hooks (`feeder_*`/`imprint_*` + the `dream` skill / `dreamer` agent)
> were **retired** in favor of Claude Code's native memory (packaging Slice 1; see
> `docs/logs.md`). Durable, version-controlled knowledge lives in `docs/` —
> decisions in `docs/adr/`, deferred work + open questions in
> `docs/exec-plans/tech-debt-tracker.md`, the evolution narrative in `docs/logs.md`.
> The active runtime is REVIEW (#1) + TIDY (#2) + the deterministic gate.

1. **REVIEW** — `execplan` completion gate → self-review → always-on
   **spec-compliance** then **code-quality** review (every ExecPlan) → spend the
   plan's `review_level` budget for the *risk personas* (`none`, `targeted`,
   `standard`, `full`). Review personas are grounded 1:1 in docs for taste/contract
   authority, but may flag demonstrable bugs with concrete evidence. review-security
   is dispatched only when the diff touches the live exec surface (hooks /
   `.harness.json` / `.harnessignore`; the rest of SECURITY.md is dormant since the
   memory loop was retired — deferred 2026-06-13) → iterate until satisfied.
2. **TIDY** — Stop hook → `tidy_stop.py` → fingerprint-deduped lint subset
   on the dirty tree; FAIL blocks once per state with FIX lines (R11).
   Commits are also gated mechanically by the scaffold-installed
   `.git/hooks/pre-commit` running `check.py`.

## Failure modes

See `docs/RELIABILITY.md` (numbered R-rules). Live headlines: the commit-gate
lints and `nav.py` are total over a hostile corpus (R21/R22 — a malformed page
FAILs/skips, never tracebacks); `director/` telemetry extractors and status
writers never raise or block the primary path (R12/R13); config/host-policy
loaders fail-open-absent / fail-loud-malformed before any side effect (R15); the
Stop-tidy gate blocks at most once per dirty-tree state (R11). The retired
feeder/imprint rules (R1–R5/R7) are kept only as historical lineage — see the
status note atop RELIABILITY.md.

## Host runtime (`director/`) invariants

`director/` is THIS repo's self-hosting application — the Symphony ticket-DAG
orchestrator (a Director main session + Codex app-server workers) the harness is
built to support. It is **instance-layer app code, not machine (`plugin/`)**: the
machine governs it only through the gate + review personas, so its own
architecture invariants live here (review-arch grounds in this doc). Runtime
*correctness* invariants live in `docs/RELIABILITY.md` (R9, R12–R18).

1. **Stdlib-only.** No third-party imports anywhere under `director/` (no
   `pyproject.toml` / `requirements.txt`) — the same "boring tech / internalize
   dependencies" grain as `plugin/scripts`. A new dependency is a design change to
   justify, never a default. **Scope:** this rule scopes *Python* imports, and the
   observability dashboard now has **no JS carve-out** — it is a single self-contained
   HTML page that serves **zero** vendored assets (the project graph is hand-rolled
   DOM+SVG, positioned from the server's layering). ADR 0006 once relaxed this to vendor
   a graph library; the 2026-06-27 graph-view re-skin dropped the library and **retired
   that relaxation** ([docs/adr/0006-observability-vendored-asset.md](docs/adr/0006-observability-vendored-asset.md) — superseded).
2. **Explicit `base=` over ambient state.** Every module resolves its state dir
   through a single `_root(base=None)` that honors an explicit `base=` (tests)
   then an env override then a default — and nothing else reads `cwd`/env
   directly. A test thus drives any module on a fixture dir with no globals
   (mirrors the `plugin/` cross-cutting S2 rule).
3. **New network listeners are loopback, fixed-route, read-only by default.** Any
   server added to `director/` (e.g. `director/dashboard.py`) binds `127.0.0.1`
   only, exposes a fixed route set (no request-derived filesystem path → zero
   traversal), and does not mutate state. A write/act surface is a separate,
   explicitly-fenced decision (origin check + the act-before-consume invariant),
   never the default.
4. **Pure core, thin transport.** Put the logic in a pure function that takes
   explicit paths and returns data (`build_view`, `reconcile`, `extract_usage`),
   unit-tested without a socket/subprocess; the HTTP/CLI/stdio layer is a thin
   shim over it. The transport is wiring, the core is the product — the `director/`
   analog of DESIGN.md's "every check function takes explicit paths; `main()` does
   the wiring".
5. **Deployment policy is declarative, not code.** Operator knobs (the board
   `team`, the logical→Linear state-name map, concurrency/bounds/timeouts, the
   worker posture, paths, merger knobs) live in the `director` block of
   `<root>/.harness.json` and are resolved ONCE at startup by `director/config.py`
   — the single `DEFAULTS` source, precedence CLI flag > config > default. The
   *methodology* (the worker protocol, queue schema, disposition kinds) stays in
   code: a host buys the harness's method and tunes only its deployment. A
   present-but-malformed block fails loud at load (before any worker spawns); an
   absent block uses the defaults. This is the `director/` analog of invariant 7
   ("a host's rules are the host's, declared in `.harness.json`"), and the Symphony
   `WORKFLOW.md` analog (SPEC §5–6). Every default that also lives in `DEFAULTS` is
   **aliased** from it (e.g. `merger.DEFAULT_MAX_MERGES = config.DEFAULTS["merger"]
   ["max_merges"]`) — no parallel literal in ANY `director/` module (merger included),
   so the single source can never silently drift. The alias may bind a **function-
   signature parameter default** through a module constant (`approval_policy: str =
   _DEFAULT_APPROVAL_POLICY` where `_DEFAULT_APPROVAL_POLICY = config.DEFAULTS[...]`),
   never a `None`-sentinel re-resolved in the body: binding the value at the signature is
   what lets an `inspect.signature` drift test pin the equality and fail on a stale literal.
6. **One first-turn framing seam.** The worker's first-turn protocol — the
   `WORKER_PROTOCOL` operating-disciplines preamble + the `TERMINAL_CONTRACT`, via
   `taxonomy.frame_first_turn` — is injected at exactly ONE point, `run.drive`'s first
   turn, and nowhere else (later turns carry the decider's directive verbatim). Every
   dispatch path (orchestrator, `run.main`, direct drive) inherits the protocol because
   all funnel through `drive`; a caller that framed again before `drive` would
   double-inject. Add new shared first-turn text here, never at a call site.
7. **One sharing boundary for batch + daemon; no new work spawns during a drain.** The
   batch wave (`_dispatch_wave`) and the continuous daemon (`run_forever`) share ONE
   implementation of claim → submit → reap → reconcile via `_RunState`; a new loop mode
   routes through it (e.g. `reap(on_retry=…)`), never re-derives the machinery. A graceful
   shutdown's "no new worker spawns while draining" is a STRUCTURAL guarantee
   (scheduled-not-immediate retries + a `not draining`-guarded due-retry step +
   exit-on-empty-`futures`), not a per-case patch. Two reconcile semantics ride here: a
   terminal summary's `final_state` is the orchestrator's best **observation** of the board
   state the ticket ends in (not an internal disposition label), and the active-run reconcile
   cadence is **wall-clock-anchored** (a monotonic `last_reconcile`) so it fires under steady
   completions, not only on a worker-completion wake.
8. **Shared helpers live in a core module, not private-imported from a sibling.** A pure
   helper or cross-module contract used by more than one `director/` module (a kind set, a
   summarizer) belongs in a module both can depend on without reaching into a transport's
   internals. A short-lived cross-module private import (`director.notify` reusing
   `dashboard._summary_for` + `HUMAN_BOUND_KINDS`) is tolerated for a two-consumer product
   slice that would otherwise duplicate-and-drift — but the moment a third consumer appears,
   promote the helper to a core module (public name) rather than spread the private import.
