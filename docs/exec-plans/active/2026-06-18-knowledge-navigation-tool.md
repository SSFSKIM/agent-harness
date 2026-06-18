---
status: active
last_verified: 2026-06-18
owner: harness
base_commit: 3edfe47
review_level: standard
type: exec-plan
tags: [knowledge-format, navigation, tooling, nav, docs-nav]
description: Build of the Phase-2 knowledge navigation tool — nav.py (live-query library+CLI) and the docs-nav skill, with the LINK/staleness primitives extracted to harness_lib.
---
# Knowledge navigation tool (Phase 2) — build nav.py + docs-nav skill

## Goal

A working, portable, read-only knowledge navigator. Definition of done, all
observable from the repo root:

- `python3 plugin/scripts/nav.py catalog --type adr` prints the ADR pages with
  their `description`s; `--type/--tag/--status` filter; `--json` emits valid JSON
  records — and a body-less page still appears with full metadata (proves the
  catalog reads frontmatter, not bodies).
- `python3 plugin/scripts/nav.py backlinks docs/PLANS.md` prints exactly the
  pages that markdown-link to `PLANS.md` (matches a manual grep); `links <path>`
  prints its forward targets.
- `python3 plugin/scripts/nav.py stale` agrees with what lint D4 would flag at
  the same `stale_days`; `orphans` lists no-inbound governed pages; `drift` flags
  `resource`-bound pages whose code is newer than `last_verified` (advisory,
  fail-soft).
- The markdown-link regex and the staleness predicate exist **once** in
  `harness_lib`, consumed by both `lint_docs.py` and `nav.py`; the existing
  `lint_docs` tests pass unchanged.
- `plugin/skills/docs-nav/SKILL.md` exists, maps intents → `nav.py` invocations,
  is registered (D9), and is mirrored into the `harness-init` templates +
  AGENTS.md / MEMORY pointers (self-host **and** ported hosts — belief 13).
- `python3 plugin/scripts/check.py` is GREEN (lints + full suite incl.
  `tests/test_nav.py`); `nav.py` is **not** wired into the gate (advisory, R8).

## Context

Builds on the Phase-2 spec — the design authority for this build; do not
re-derive it:
[`../../product-specs/2026-06-18-knowledge-navigation-tool.md`](../../product-specs/2026-06-18-knowledge-navigation-tool.md).
That spec defines the record model (D-1), CLI surface (D-2), health queries
(D-3), the shared-primitive refactor (D-4), git drift (D-5), the skill (D-6), and
portability (D-7), plus the non-goals (no committed catalog, no generated
`index.md`, no `viz.html`, drift advisory-only).

Upstream: [Phase-1 format spec](../../product-specs/2026-06-18-knowledge-format-evolution.md)
(the `type`/`tags`/`description`/`resource` keys this consumes; `read_frontmatter`
is already list-aware), [`KNOWLEDGE_FORMAT.md`](../../KNOWLEDGE_FORMAT.md) (the
format), [OKF comparison](../../design-docs/okf-comparison.md) (why this is the
"consumer" half).

Code a novice needs to read first:
- `plugin/scripts/harness_lib.py` — `read_frontmatter` (returns `str | list[str]`),
  `repo_root`, `iter_md`, `gate_config`, `MANAGED_*`. The cross-cutting resolver;
  the shared primitives land here (ARCHITECTURE layer law, core-belief 5).
- `plugin/scripts/lint_docs.py` — owns today `LINK = re.compile(...)` (used by
  `check_links`/D5) and the inline D4 staleness math (`check_frontmatter`), plus
  `_governed_doc` (which pages the gate governs). These are what M1 refactors.
- `plugin/scripts/gen_inventory.py` — the sibling script pattern nav.py mirrors
  (procedural, `harness_lib`-backed, `argparse`, portable).
- `tests/test_lint_docs.py`, `tests/test_harness_lib.py` — the regression nets
  that must stay green through the refactor.

## Approach (self-generated alternatives)

**Link/staleness sourcing:**
- A: `nav.py` re-implements link parsing + staleness internally, leaving
  `lint_docs` untouched. Tradeoff: smaller diff, no gate-hot-path risk — but two
  definitions of "what a link is" / "what stale means" that will drift apart
  (the exact failure core-belief 5 and spec R7 forbid).
- B: Extract `links_in`/`LINK` and `is_stale` into `harness_lib`; both
  `lint_docs` and `nav` consume them. Tradeoff: touches the gate's hot path
  (regression risk) but yields one source of truth; risk is bounded by the
  existing `lint_docs` test suite, which must stay green as the refactor's proof.
- **Chosen: B** — R7 mandates single-definition; the divergence in A is the
  anti-pattern. The refactor is mechanical and test-guarded.

**nav.py shape:**
- A: class-based `Catalog` object holding records. B: procedural — a pure
  `build_index(root) -> list[dict]` plus stateless query functions + an `argparse`
  CLI. **Chosen: B** — matches `gen_inventory.py`'s style, stdlib-light, trivially
  importable for the code-execution path (spec D-2), no lifecycle to manage.

**Governance scope:** reuse `lint_docs`'s notion of a governed doc rather than
re-deriving it, so the catalog and the gate agree on "which pages count" — import
the predicate, don't copy it.

## Assumptions & open questions (self-interrogation)

- Assumption: `read_frontmatter` already returns `tags` as `list[str]` (Phase-1).
  If a page authored tags in an unsupported form, `tags` degrades to a string —
  nav must treat a non-list `tags` defensively (coerce to `[]` or `[str]`), never
  crash. What breaks if wrong: a `--tag` filter on a malformed page; mitigated by
  defensive coercion + a test.
- Assumption: `git` is available for `drift`. If not (or not a git repo), drift
  is `unknown`, never an error (spec D-5 fail-soft). What breaks if wrong:
  nothing — fail-soft is the contract.
- Open: nav's page set = lint's governed set, or all `docs/**/*.md`? → resolved:
  the **governed** set (catalog ↔ gate agree), but link/backlink traversal also
  reads `AGENTS.md`/`ARCHITECTURE.md` as link sources+targets (they are graph
  roots). Recorded.
- Open: drift date granularity? → resolved: compare **dates** — `last_verified`
  is a date; take the date of git `%cI`. Resource committed on/before
  `last_verified` = `current`; strictly after = `drifted`. Recorded.
- Open: orphan candidates? → resolved: exclude reserved/root files
  (`index.md`, `MEMORY.md`, `AGENTS.md`, `ARCHITECTURE.md`) — they are spines, not
  orphans. An orphan = a governed content page with zero inbound markdown links.
- Open: should `lint_docs` keep its D4 list-valued-date guard (Phase-1)? →
  resolved: yes — `harness_lib.is_stale` owns the *predicate* (returns bool /
  raises on bad date per a documented contract); `lint_docs` keeps owning the
  *reporting* (catching a bad/list date → D4 FAIL message). The refactor moves the
  date math, not the error UX. Recorded.

## Milestones

- **M1 — Shared primitives, single definition.** Move the markdown-link regex
  into `harness_lib` as `LINK` + a `links_in(text) -> list[str]` helper, and add
  `is_stale(last_verified, stale_days, status) -> bool` (the D4 math: parses the
  ISO date, returns `False` for `status in {archived, completed}`, raises
  `ValueError`/`TypeError` on a bad/non-scalar date so the caller decides the UX).
  Refactor `lint_docs.check_links` to call `hl.links_in` and `check_frontmatter`
  (D4) to call `hl.is_stale` inside its existing `try/except` (preserving the
  exact D4 FAIL + list-date guard). At the end the link/staleness logic exists
  once in `harness_lib`; `lint_docs` imports it. Run
  `python3 -m unittest tests.test_lint_docs tests.test_harness_lib -v` and
  `python3 plugin/scripts/check.py`; expect all green with **no** edits to the
  existing test assertions (behavior unchanged is the proof).

- **M2 — nav.py core: record model + catalog/filter.** New
  `plugin/scripts/nav.py`: `build_index(root) -> list[dict]` walking the governed
  `docs/` set (reusing `lint_docs`'s governance predicate) + the two entry maps
  for links, each record `(path, type, tags, status, description, resource,
  last_verified, links)` built from frontmatter + `hl.links_in` (no body parse
  beyond the link scan). `argparse` CLI with `catalog` (`--type/--tag/--status`
  AND-combined, `--json`). At the end `python3 plugin/scripts/nav.py catalog
  --type adr` lists the ADRs with descriptions and `--json` is valid JSON; a
  fixture page with empty body still appears. Run `python3 -m unittest
  tests.test_nav -v` (new) covering build_index + each filter + the body-less
  case + malformed-`tags` coercion; expect green.

- **M3 — nav.py graph + health.** Add subcommands `links <path>` /
  `backlinks <path>` (invert the `links` edges once), `stale` (via `hl.is_stale`
  + `gate_config` `stale_days`, skipping archived/completed), `orphans` (no inbound
  edge, excluding reserved/root files), and `drift` (for records whose `resource`
  is a repo-relative path inside root: `git -C root log -1 --format=%cI -- res`,
  compare its date to `last_verified` → `drifted`/`current`/`unknown`, fail-soft).
  At the end `nav.py backlinks docs/PLANS.md` matches `grep -rl "PLANS.md"` over
  governed docs; `nav.py stale` matches a hand-check against D4; `nav.py drift`
  runs without error on the real repo. Extend `tests/test_nav.py` with a
  backlinks case, a stale page, an orphan, and a `resource`-drift case against a
  git fixture; run `python3 -m unittest tests.test_nav -v`; expect green.

- **M4 — docs-nav skill + wiring + propagation.** Create
  `plugin/skills/docs-nav/SKILL.md` (when to query vs bulk-read; intent→command
  table; output contract; cross-links to `docs-tree`, `KNOWLEDGE_FORMAT.md`,
  `okf-comparison.md`). Add a one-line `docs-nav`/`nav.py` row to `AGENTS.md` map
  **and** the `harness-init` templates (`plugin/skills/harness-init/templates/
  agent-harness.md` + `agents.md`); point `docs-tree` SKILL + `MEMORY.md`
  (self-host + templates) at `docs-nav` for querying. At the end `python3
  plugin/scripts/check.py` is GREEN — D9 coverage sees `docs-nav`, S7 sees no
  self-host paths in templates, and `tests/test_scaffold.py::
  test_fresh_host_is_lint_green` still passes. Behavioral acceptance: run
  `catalog`/`backlinks`/`stale`/`drift` and capture output in Outcomes.

## Progress log
- [x] (2026-06-18) M1 — shared primitives. Added `hl.LINK`/`hl.links_in` +
  `hl.is_stale` to harness_lib; refactored `lint_docs.check_links` →
  `hl.links_in` and the D4 block → `hl.is_stale` (protected-path tightening +
  list-date guard preserved); removed lint_docs' now-dead `LINK` + `import
  datetime`. Regression: 38 lint_docs + 27 harness_lib tests green, NO existing
  assertion edited; full gate GREEN. Added 5 primitive tests (links_in, is_stale
  true/within-window/archived-exempt/raises-on-bad-date).
- [x] (2026-06-18) M2 — nav.py `build_index` + `catalog` (--type/--tag/--status,
  --json) + 8 tests. Hit lint **S1** (scripts may not import lint_docs) — reworked
  nav to derive its scope from harness_lib only: catalog-eligible = has
  frontmatter ∧ not reserved (index.md/MEMORY.md) ∧ not exempt; extracted the
  segment-boundary matcher to `hl.is_exempt` (lint_docs now delegates). Self-host
  scope == lint's governed content set. Gate GREEN; lint_docs 38 tests unchanged.
- [x] (2026-06-18) M3 — graph + health. Added `links`/`backlinks` (over the
  shared edge set), `orphans` (catalog pages with no inbound markdown link),
  `stale` (via `hl.is_stale` + new `hl.stale_window`, agrees with D4), `drift`
  (git last-commit vs `last_verified`, fail-soft: drifted/current/unknown). CLI
  subcommands + emitters. Cross-checked `backlinks okf-comparison.md` (6) ==
  manual grep (6). +4 tests (links/backlinks, orphans, stale, git-fixture drift)
  → 12 nav tests; gate GREEN. `hl.STALE_DAYS`/`hl.stale_window` added; lint
  re-exports STALE_DAYS (one default).
- [ ] M4 — docs-nav skill + AGENTS/template/MEMORY wiring + gate GREEN

## Surprises & discoveries
- Spec D-4 had an internal contradiction ("`is_stale` raises nothing on a bad
  date" AND "lint → D4 FAIL" — lint can't FAIL on a date the predicate hides).
  Resolved during M1 by making `is_stale` parse-first / raise on a bad date
  (caller owns reporting); updated the spec D-4 wording to match so the
  spec-compliance review sees agreement. The ExecPlan already specified this
  contract — the spec line was the imprecise one.
- **S1 blocked the spec's "reuse lint's predicate" design.** lint_structure S1
  forbids a script importing `lint_docs` (pure-stdlib+harness_lib only). Reworked
  nav's scope to be harness_lib-derived (frontmatter + `hl.is_exempt` + reserved
  exclusion); updated spec D-1 to match. This is *better* than the original design:
  no script→script coupling, and `is_exempt` is now a shared primitive. The gate
  caught a spec/architecture conflict the green-on-paper design hid.
- Tests run via `python3 -m unittest discover -s tests` (check.py step), not
  `-m unittest tests.test_x` (tests/ is not a package; modules self-insert
  plugin/scripts on sys.path). Pyright "harness_lib could not be resolved" is a
  static false positive for that runtime path insert (every test file).

## Decision log
- 2026-06-18: Approach B (extract shared primitives) over A (nav re-implements) —
  R7 single-definition; divergence is the anti-pattern. Risk bounded by existing
  lint tests.
- 2026-06-18: nav.py procedural (build_index + stateless queries + argparse),
  mirroring gen_inventory.py — importable for the code-execution path.
- 2026-06-18: nav governs lint's governed set (catalog↔gate agree); entry maps
  included for link traversal only.
- 2026-06-18: drift compares dates; `is_stale` predicate in harness_lib,
  reporting/UX stays in lint_docs (D4 list-date guard preserved).

## Feedback (from completion gate)

## Outcomes & retrospective
