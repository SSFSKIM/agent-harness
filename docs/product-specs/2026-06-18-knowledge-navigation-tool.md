---
status: active
last_verified: 2026-06-18
owner: harness
phase: knowledge-format/02-navigation
type: product-spec
tags: [knowledge-format, navigation, query, tooling, porting]
description: A live-query knowledge navigation tool (nav.py library+CLI) plus a docs-nav skill that consume the Phase-1 frontmatter (type/tags/description/resource) and the D5 link graph, so an agent navigates the corpus by querying instead of bulk-reading bodies.
---
# Knowledge navigation tool — live query over the Phase-1 format (Phase 2)

## Problem

Phase 1 made the corpus *describable*: every page now carries machine-readable
`type`/`tags`/`description` and (where it binds to code) `resource`, on top of the
existing `status`/`last_verified` and the markdown link graph that `lint_docs` D5
already validates. ([Phase 1 spec](2026-06-18-knowledge-format-evolution.md);
[OKF comparison](../design-docs/okf-comparison.md), adoption #4.)

Nothing yet *consumes* that structure. Today an agent that needs to orient —
"which ADRs touch the gate?", "what links to `PLANS.md` before I edit it?",
"which pages claim to describe `harness_lib.py`?", "what's gone stale?" — has only
two moves: read `index.md` files (hand-curated prose, no machine filter) or open
pages and read their bodies. For a ~80-page corpus that is the exact context burn
the Phase-1 `description` key was introduced to avoid. The frontmatter is a
queryable table-of-contents `(path, type, tags, status, description, resource)`
with a link graph over it — but there is no tool that reads it that way.

Concretely, four capabilities are missing, all derivable from data we already
have:

1. **Catalog / filter** — list pages by `type`/`tag`/`status` with their
   `description`, *without reading bodies*. This is the headline: navigate by
   metadata, not by opening files.
2. **Link graph traversal** — forward links and **backlinks** ("what links
   here"). The reverse-link view is the single most useful pre-edit safety check
   and is free from the same edges D5 walks.
3. **Health** — which pages are **stale** (the D4 contract, surfaced as a query
   rather than only as a blocking lint), and which are **orphans** (no inbound
   links — unreachable knowledge).
4. **Drift** — which pages bind a `resource` whose code has changed since the
   page was last verified. `resource` was introduced in Phase 1 *precisely* to
   enable this; this is the field's first consumer.

Two design facts constrain the solution, learned from reading the repo as it is:

- **The consumer is the agent, not a human browser.** This harness governs an
  *actor*. The high-value query happens mid-session, in code: the agent wants a
  filtered JSON table, not a rendered graph. So the tool optimizes
  agent-queryable output first; OKF's human-facing `viz.html` is out of scope
  (decision below).
- **Derived artifacts must not rot, and curated ones must not be flattened.** The
  repo's generated-artifact pattern (`gen_inventory.py`) is *check-and-regen*, not
  hook-write; and the category `index.md` files carry curation richer than any
  one-sentence `description` (e.g. `product-specs/index.md`'s paragraph-length,
  ADR-cross-linked entries). Both facts push the same way: **compute the catalog
  live on every call** — never persist it, never auto-generate `index.md`. Live
  query is always fresh (the frontmatter is the source of truth) and adds zero
  staleness machinery and zero per-commit friction.

This is **Phase 2** of the two-phase arc. Phase 1 evolved the *format*; Phase 2
builds the *consumer*. It is shippable and verifiable on its own and adds no new
blocking gate — it is read-only, on-demand tooling.

## Requirements

Each is independently checkable by a human.

- **R1 — A portable navigation engine exists as a library + CLI.**
  `plugin/scripts/nav.py` builds, on every invocation, an in-memory record per
  governed `docs/` page: `(path, type, tags, status, description, resource,
  last_verified, links)`. It is importable (functions return Python data) and has
  a thin CLI front-end (subcommands print text or `--json`). It hardcodes no
  absolute path and reuses `harness_lib` for root/frontmatter resolution. No file
  is written; nothing is added to `docs/generated/`.
- **R2 — Catalog & filter without reading bodies.** `nav.py catalog` lists every
  page with its `type`/`tags`/`status`/`description`; `--type X`, `--tag Y`,
  `--status Z` filter (combinable, AND semantics); `--json` emits the records as
  JSON. The output is derived from frontmatter alone — verifiable by confirming a
  page with no body content still appears with full metadata.
- **R3 — Link graph traversal.** `nav.py links <path>` lists the pages a page
  links to; `nav.py backlinks <path>` lists the pages that link to it. Both use
  the *same* link-extraction primitive `lint_docs` D5 uses (R7), so the nav graph
  and the lint graph can never diverge.
- **R4 — Health queries.** `nav.py stale` lists pages past the D4 staleness
  window (reusing the D4 date logic, honoring `status` archived/completed
  exemptions and the per-repo `stale_days`), and `nav.py orphans` lists governed
  pages with zero inbound links (excluding reserved files `index.md`/`MEMORY.md`
  and the entry maps). These are advisory reports, not gate steps.
- **R5 — Drift detection (advisory, git-based).** `nav.py drift` lists pages
  whose `resource` is a repo-relative path whose last git-commit date is newer
  than the page's `last_verified` (the code moved under the page). It shells to
  `git log`; if the repo is not git or the resource is a URL / missing path, that
  page is reported as `unknown`, never an error (fail-soft). No content-hash
  frontmatter field is added; no blocking lint is created.
- **R6 — An agentic `docs-nav` skill.** `plugin/skills/docs-nav/SKILL.md` teaches
  the agent *when* to query instead of bulk-reading and *how* to map an intent to
  a `nav.py` invocation (orient by type/tag, pre-edit backlinks check, health
  sweeps). It is registered (D9 coverage) and cross-linked with the `docs-tree`
  skill (placement) and `KNOWLEDGE_FORMAT.md` (the format it queries).
- **R7 — Shared primitives, single definition.** The markdown-link regex and the
  staleness predicate are extracted into `harness_lib` and consumed by *both*
  `lint_docs.py` and `nav.py`. `lint_docs` behavior is unchanged (its existing
  tests stay green); there is exactly one definition of "what a link is" and
  "what stale means" in the repo (core-belief 5).
- **R8 — Permissive & non-blocking.** No new D-rule. `nav.py` is never wired into
  `check.py` as a gate step; `python3 plugin/scripts/check.py` is GREEN before and
  after, with the tool present. Drift/stale/orphan findings are surfaced only on
  demand.
- **R9 — Portability (core belief 13).** The engine and skill live in `plugin/`,
  so they travel with the machine automatically (no `scaffold.py` doc-seed
  needed). The `AGENTS.md` map and the authoring pointers (`docs-tree` SKILL,
  `MEMORY.md`) are updated in **both** the self-host docs and the `harness-init`
  templates, so a ported host learns the tool exists. Host-agnostic — no self-host
  paths (lint S7).
- **R10 — Tested & GREEN.** `tests/test_nav.py` covers each query against a
  fixture corpus (including list-valued `tags`, missing optional keys, a
  `resource` drift case, an orphan, a stale page). `python3 plugin/scripts/check.py`
  passes (lints + full unittest suite).

## Design

### D-1. The record model (R1)

One pure function `build_index(root) -> list[Record]` is the spine; every query
is a projection over its output. A `Record` is a dict (stdlib, no dataclass
ceremony required, but a `typing`-light shape):

```
path           repo-relative posix string (e.g. "docs/adr/0003-...md")
type           str | None        # frontmatter `type`, else None
tags           list[str]         # frontmatter `tags` (already list-aware), else []
status         str | None
description    str | None
resource       str | None
last_verified  str | None        # raw ISO string as authored
links          list[str]         # repo-relative targets this page links to
```

`build_index` walks `hl.iter_md(root/"docs")` plus the two entry maps
(`AGENTS.md`, `ARCHITECTURE.md`) for link purposes, reads each page's frontmatter
via `hl.read_frontmatter` (Phase-1 list-aware — `tags` already returns a list),
and extracts links via the shared primitive (D-4). A record is **catalog-eligible**
when it carries frontmatter and is not a reserved spine file (`index.md` /
`MEMORY.md`); exempt subtrees (`generated/`, `superpowers/`, host
`.harnessignore` roots) are skipped via the shared `hl.is_exempt`. nav must **not**
import `lint_docs` (lint S1 / core-belief 7 forbid script→script deps), so it
derives this scope from `harness_lib` + frontmatter rather than reusing the gate's
predicate. In **self-host** that scope equals lint's governed content pages
(every governed page carries D3 frontmatter); in relaxed hosts nav may surface a
few more frontmatter-bearing pages — acceptable for a read-only navigator.

Bodies are never parsed beyond the link scan (a single regex pass) — the catalog
columns come from frontmatter only, which is the whole point (R2).

### D-2. The CLI surface (R2–R5)

`nav.py` uses stdlib `argparse` with subcommands. Each subcommand calls
`build_index` once, projects, and prints. Text output is the default (compact,
greppable: `path  type  [tags]  — description`); `--json` emits the raw records
or query result for the code-execution path.

| Subcommand | Args | Returns |
|---|---|---|
| `catalog` | `--type --tag --status --json` | filtered records (AND of filters) |
| `links` | `<path>` | the page's outbound link targets |
| `backlinks` | `<path>` | pages whose `links` contain `<path>` |
| `stale` | `--json` | pages past the staleness window (D-3) |
| `orphans` | `--json` | governed pages with no inbound links (D-3) |
| `drift` | `--json` | `resource`-bound pages whose code is newer (D-5) |

`backlinks`/`orphans` are computed by inverting the `links` edges across the whole
index — one reverse-map build, O(edges). `<path>` args are normalized
(repo-relative posix) so `docs/PLANS.md` and an absolute path both resolve.

Importable equivalents (`catalog(records, type=…, tag=…)`, `backlinks(records,
path)`, `stale(records, …)`, `drift(records, root)`) are the functions the CLI
wraps, so an agent in the code-execution paradigm does
`from nav import build_index, backlinks` and filters in-process — same logic, no
shell.

### D-3. Health: stale & orphans (R4)

**Stale** reuses the D4 predicate (D-4): `is_stale(last_verified, stale_days,
status)`. `nav.py stale` reads `stale_days` from `hl.gate_config` exactly as
`lint_docs` does, and skips `status in (archived, completed)`. The *only*
difference from D4 is presentation: D4 fails the commit; `nav.py stale` reports.
(Protected-path tightening is a gate concern, not a reporting one, so the report
uses the effective window.)

**Orphans** = governed pages with no inbound edge, excluding reserved files
(`index.md`, `MEMORY.md`) and the entry maps (`AGENTS.md`/`ARCHITECTURE.md`),
which are roots by definition. An orphan is *advisory* — it usually means "should
be registered in an index or linked from a parent", which is knowledge the agent
or doc-gardener acts on, not a hard error.

### D-4. Shared primitives — the single-definition refactor (R7)

Today `lint_docs.py` owns `LINK = re.compile(...)` and inlines the D4 staleness
date math. Phase 2 moves both into `harness_lib` (the cross-cutting resolver, per
ARCHITECTURE's layer law and core-belief 5):

- `hl.LINK` (or `hl.links_in(text) -> list[str]`) — the one definition of a
  knowledge link. `lint_docs.check_links` and `nav.build_index` both call it.
- `hl.is_stale(last_verified, stale_days, status) -> bool` — the one definition of
  staleness: `False` for archived/completed, else whether `today -
  last_verified > stale_days`. It parses the date **first**, so a bad or
  non-scalar date (e.g. a YAML list) **raises** `ValueError`/`TypeError` — the
  caller owns the reporting UX (lint → catch → its existing D4 FAIL message +
  list-date guard; nav → catch → skip the page). This keeps lint's bad-date
  detection working while centralizing the date math.

`lint_docs` is refactored to import these; its observable behavior is unchanged,
proven by its **existing** test suite staying green (the refactor adds no new D4
semantics — D4's list-valued-date guard from Phase 1 stays in `lint_docs`, which
owns *reporting*; `harness_lib` owns the *predicate*). This avoids the real risk:
two link parsers or two staleness rules drifting apart.

### D-5. Drift detection (R5)

`drift(records, root)` filters to records with a `resource` that is a
repo-relative path resolving inside `root`. For each, it runs
`git -C <root> log -1 --format=%cI -- <resource>` to get the resource's last
commit timestamp and compares its date to the page's `last_verified`:

- resource commit date **>** `last_verified` → **`drifted`** (code moved after the
  page was verified).
- resource not found / not committed / not a git repo / `git` unavailable / a URL
  → **`unknown`** (fail-soft; never an exception, never a non-zero exit).
- otherwise → **`current`**.

`nav.py drift` prints the `drifted` set (and `--json` includes all three states).
This is the lightest credible drift signal: no new frontmatter field, no hashing,
no stored state — git already records when the code changed. Deeper drift
(content hashes, per-symbol binding) is explicitly out of scope (NG-3).

### D-6. The `docs-nav` skill (R6)

A new skill, sibling to `docs-tree`. `docs-tree` answers *where a page should
live*; `docs-nav` answers *how to find what already exists without reading it
all*. SKILL.md content:

- **When to reach for it** — before editing a page (run `backlinks` to see what
  depends on it); when orienting in an unfamiliar area (`catalog --type/--tag`);
  during a GC/garden pass (`stale`/`orphans`/`drift`).
- **Intent → command** table mapping natural questions to invocations.
- **Output contract** — what the columns mean; that the catalog is live (no
  staleness caveat); that drift/stale/orphans are advisory.
- Cross-links: `docs-tree` (placement), `KNOWLEDGE_FORMAT.md` (the queried
  format), `okf-comparison.md` (why this is the OKF "consumer" half).

It is referenced from `AGENTS.md` (map/coverage) and the `doc-gardener` workflow
naturally uses `stale`/`orphans`/`drift`.

### D-7. Portability wiring (R9)

The engine (`plugin/scripts/nav.py`) and skill (`plugin/skills/docs-nav/`) are in
the portable layer, so they ship with the plugin to any host — no `scaffold.py`
doc-seed is required (seeds are for host `docs/` files, not plugin code). What
must propagate is *awareness*:

- `AGENTS.md` map gains a one-line `docs-nav` / `nav.py` entry; the
  `harness-init` `agent-harness.md` + `agents.md` templates get the same, so a
  ported host's map mentions the tool.
- The `docs-tree` SKILL and `MEMORY.md` "navigate on demand" guidance point at
  `docs-nav` as the query path (self-host + templates).

No new `MACHINE_DOC`/`MANAGED_DOC` (nav.py is a script, not a governed doc; the
`docs-nav` SKILL is covered by D9 like every other skill).

### Decisions resolved autonomously (recorded per methodology)

- **Live query, no committed catalog (reversal, on evidence).** The earlier
  default was an additive `docs/generated/knowledge-catalog.json` (gen_inventory
  pattern). Rejected after reading the repo: (a) a docs catalog would trip a
  `--check` gate on *every docs commit* (far more friction than gen_inventory,
  whose source rarely changes); (b) an auto-write commit hook is the anti-pattern
  the repo already declined (mutating the staged tree → surprise commits/races);
  (c) the agent has the live query regardless, so a stored copy earns almost
  nothing. Live compute is always fresh and friction-free. A committed,
  `--check`-gated snapshot becomes worthwhile only when a *second* consumer needs
  it (e.g. the deferred graph view) — added then, not now.
- **`index.md` stays hand-curated; NG-2 reframed, not deferred.** Generating
  `index.md` from `description` would flatten genuine curation
  (`product-specs/index.md` carries paragraph-length, ADR-linked entries). So the
  "duplication" Phase 1 flagged is mostly complementary: **live `nav.py catalog`
  is the machine-readable index**; the curated `index.md` is the human spine.
- **Drift = git-based, advisory.** Honors the permissive stance (Phase 1 D-3) and
  NG-7 "validation comes last": surface drift, don't block on it; use git rather
  than a new hash field.
- **No graph view (`viz.html`).** The consumer is the agent (queries JSON);
  backlinks/orphans/links already serve the navigation need in data form. The
  force-directed HTML serves a *human browsing* — low value for this actor-driven
  harness. Deferred (user decision, 2026-06-18). Easy to add later atop a stored
  catalog.
- **Engine = library + CLI in `plugin/scripts/`.** Superset of "code-execution
  tool": shell out *or* import. Matches the existing script siblings and the
  portability law (travels with the plugin).
- **Reuse over re-implement (LINK + staleness).** Extracted to `harness_lib` so
  lint and nav share one definition — the alternative (nav re-parsing links /
  re-deriving staleness) risks a silent divergence from the gate.

## Non-goals

Each is fenced out and given a named home so the roadmap survives.

- **NG-1 — A committed/generated catalog artifact.** No
  `docs/generated/knowledge-catalog.{json,md}` this phase (live query). Revisit
  only when a second consumer (graph view) needs a stored data source.
- **NG-2 — Generated `index.md`.** `index.md` stays hand-curated; live `catalog`
  is the machine index. Not revisited unless curation is shown to be pure
  duplication somewhere (it is not, today).
- **NG-3 — Deep drift.** No content-hash frontmatter field, no per-symbol
  binding, no drift *lint*. Git last-commit-date vs `last_verified` is the whole
  drift surface.
- **NG-4 — Graph view / `viz.html`.** Deferred (decision above). The OKF
  adoption-#4 capstone; build atop a stored catalog if/when a human-browsing need
  appears.
- **NG-5 — Lint validation of the new keys.** Still deferred (Phase-1 NG-7):
  `nav` *reports* on `type`/`resource`; it does not *enforce* a vocabulary or
  resolution. Permissive until evidence earns a blocking check.
- **NG-6 — Typed link relationships.** Links stay untyped edges (Phase-1 NG-6 /
  KF v1.1, later). `backlinks` returns "what links here", not "what *supersedes*
  here".
- **NG-7 — MCP server / cross-repo serving.** `nav.py` is a local script + skill,
  not a served endpoint. Externalizing harness knowledge across a repo boundary
  is the OKF-exchange frontier, not this phase.

## Acceptance criteria

1. `plugin/scripts/nav.py` exists; `python3 plugin/scripts/nav.py catalog
   --type adr` lists the ADR pages with their descriptions, and `--json` emits
   valid JSON records — with **no** file written under `docs/generated/`. (R1, R2)
2. `nav.py backlinks docs/PLANS.md` lists the pages that link to `PLANS.md`, and
   that set matches a manual grep of markdown links to `PLANS.md`. (R3, R7)
3. `nav.py stale`, `nav.py orphans`, and `nav.py drift` each run and produce an
   advisory report; `stale` agrees with what D4 would flag at the same
   `stale_days`. (R4, R5)
4. `harness_lib` owns the single `LINK`/`links_in` and `is_stale` definitions;
   `lint_docs` imports them; the **existing** `lint_docs` tests pass unchanged.
   (R7)
5. `plugin/skills/docs-nav/SKILL.md` exists, maps intents to `nav.py`
   invocations, is registered (D9), and cross-links `docs-tree` +
   `KNOWLEDGE_FORMAT.md`. (R6)
6. `AGENTS.md` and the `harness-init` templates (`agent-harness.md`, `agents.md`)
   mention the tool; the `docs-tree` SKILL and `MEMORY.md` (self-host +
   templates) point at `docs-nav` for querying. No self-host paths leak (S7).
   (R9)
7. `tests/test_nav.py` covers catalog/filter, links/backlinks, stale, orphans,
   and a drift case against a fixture corpus; `python3 plugin/scripts/check.py`
   is GREEN. (R8, R10)

## Relationship to prior work

- Builds directly on [Knowledge Format evolution (Phase 1)](2026-06-18-knowledge-format-evolution.md):
  this is the "Phase 2 — Knowledge navigation/query tool + agentic skill" named in
  that spec's roadmap, and it absorbs the Phase-1 deferrals it can (drift from
  NG-3 as an advisory query; the machine-index need behind NG-2 via live
  `catalog`).
- Realizes adoption **#4** (and the consumer half of #1–#3) from
  [the OKF comparison](../design-docs/okf-comparison.md), while consciously
  declining OKF's human-facing `viz.html` for an agent-facing query surface.
