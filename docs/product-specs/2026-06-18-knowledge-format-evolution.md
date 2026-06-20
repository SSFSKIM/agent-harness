---
status: active
last_verified: 2026-06-18
owner: harness
phase: knowledge-format/01-evolution
type: product-spec
tags: [knowledge-format, frontmatter, memory, porting]
description: Adds optional frontmatter keys (type, tags, resource) to the knowledge corpus, upgrades read_frontmatter to recognize lists, and hardens the format from implicit-in-lint into an explicit versioned KNOWLEDGE_FORMAT.md spec.
---
# Knowledge Format evolution — OKF-grounded keys + a versioned format spec (Phase 1)

## Problem

Our knowledge corpus (`docs/`, `docs/memory/`) is a markdown + YAML-frontmatter
tree governed by `lint_docs.py`. The OKF parity analysis
([`docs/design-docs/okf-comparison.md`](../design-docs/okf-comparison.md))
established that Google's Open Knowledge Format independently arrived at the same
substrate, and named three concrete things OKF has at the **format layer** that
we lack:

1. **No machine-readable concept-kind.** Our "type" is implicit in the
   *directory* (`knowledge/` vs `adr/` vs `limitations/` vs `openq/`). A consumer
   — or the Phase-2 navigation tool — cannot filter the corpus by kind without
   hard-coding our directory taxonomy. OKF's required `type` field makes kind
   explicit and orthogonal to location.
2. **No structured asset binding.** Pages name their source in prose
   (`## Source: plugin/scripts/harness_lib.py`) but not as a machine-resolvable
   field. OKF's `resource` lets tooling link a page to the code/asset it
   describes — the precondition for automated drift detection.
3. **No cross-cutting facets.** We have only the directory tree and manual
   cross-links; no `tags` axis.

A fourth, structural gap: **our format is implicit in `lint_docs.py`.** There is
no single document a human or agent can read to learn "what a conformant harness
knowledge page is." OKF's contribution is precisely that it is *specified* and
*versioned*. To make our recording system more sophisticated — and to give the
Phase-2 navigation tool a stable contract to build against — the format must
become an explicit, versioned artifact.

A fifth, navigation-oriented gap: pages are not **self-describing**. A page's
one-line summary lives in its category `index.md` (hand-written), not in the page
itself — so an agent reading the page, or a tool cataloguing the corpus by code
execution over frontmatter alone, has no "what is this page" without parsing the
body. OKF's `title`/`description` keys close this: a `description` is the snippet a
navigator surfaces and the basis for a *generated* (rather than dual-maintained)
index. This pairs with `type`/`tags` — together `(path, type, tags, description)`
is a queryable table-of-contents an agent can filter without loading any body.

Two facts constrain the solution:

- **The frontmatter parser is flat.** `harness_lib.read_frontmatter` parses only
  `key: value` scalar lines; it skips indented/`-` lines. It cannot read a YAML
  list. So `tags` (a list) is not merely "a new key" — its value representation
  must be chosen so our own stack can read it. (The other four new keys are
  scalars the flat parser already reads.)
- **The gate must stay permissive on new keys.** Per the product decision, the
  new keys are all *optional*; `check.py` must not start failing pages that omit
  them, and authors must not be forced to backfill the entire corpus.

This is **Phase 1** of a two-phase arc. Phase 1 evolves the *format and recording
structure*. Phase 2 (a separate future spec) builds the *query / navigation tool*
that consumes this format. Phase 1 is shippable and verifiable on its own.

## Requirements

Each is independently checkable by a human.

- **R1 — Five optional frontmatter keys are defined and documented**, in two
  tiers: *routing/binding* (`type`, `tags`, `resource`) and *display* (`title`,
  `description`). Each has written semantics; `type` has a recommended
  vocabulary, `tags` a canonical authored form. A reader can determine, for any
  page, whether its frontmatter uses them correctly.
- **R2 — The keys are genuinely optional.** `check.py` is GREEN on the repo both
  before and after the change with pages that omit all five keys. No new blocking
  lint rule keys on `type`/`tags`/`resource`/`title`/`description`. `D3` still
  requires exactly `status / last_verified / owner`.
- **R3 — `read_frontmatter` reads list-valued keys.** Given a page whose
  frontmatter contains `tags` in the canonical form, `read_frontmatter` returns a
  Python `list` of strings for `tags`. Given any pre-existing scalar key, it
  returns the identical string it returned before (byte-for-byte behavior
  preserved). Covered by unit tests that fail before the change and pass after.
- **R4 — A versioned Knowledge Format spec exists as a standing document.**
  `docs/KNOWLEDGE_FORMAT.md` specifies the frontmatter schema (required +
  optional keys), reserved filenames, link semantics, the conformance rules the
  lints actually enforce (mapped to D-rule IDs), and a declared format version.
  It is registered in the `AGENTS.md` map and carries standard governance
  frontmatter. A new contributor can author a conformant page from this doc
  alone, without reading `lint_docs.py`.
- **R5 — The authoring guidance reflects the new keys.** The `docs-tree` skill's
  frontmatter procedure and `docs/memory/MEMORY.md`'s write rules mention the
  optional keys and point to `docs/KNOWLEDGE_FORMAT.md` as the authority.
- **R6 — A representative slice of the corpus uses the new keys.** Every concept
  page under `docs/memory/{knowledge,adr,limitations,openq}/` (excluding
  `index.md`) carries `type`, `tags`, and a one-sentence `description`, and
  carries `resource` when the page documents a concrete code asset. This proves
  the format end-to-end and gives Phase 2 real data to consume. (`title` is
  authored only where the H1 is a poor display label; index pages MAY carry
  `type`.)
- **R7 — Everything stays GREEN.** `python3 plugin/scripts/check.py` passes
  (lints + full unittest suite), including the new parser tests.

## Design

### D-1. The five keys (R1)

All five are **optional**, added to the *recommended* tier of the frontmatter
schema (required tier `status / last_verified / owner` unchanged). They split by
cost and purpose:

- **Routing/binding** — `type`, `tags`, `resource`: machine axes the Phase-2 tool
  filters and traverses on. `tags` is the only one that drove the parser change.
- **Display** — `title`, `description`: zero-cost scalar labels for navigation.

**`type` — concept-kind, made explicit and queryable.** A scalar string naming
the *epistemic kind* of the page, lifting our directory-implicit taxonomy into a
machine-readable field that survives independent of path. Recommended vocabulary
(free/extensible — consumers tolerate unknown values, OKF-style):

| `type` value | For pages like |
|---|---|
| `knowledge` | `docs/memory/knowledge/*` — reusable how-it-works |
| `adr` | `docs/adr/*` — decision + why |
| `limitation` | `docs/memory/limitations/*` — known landmines |
| `openq` | `docs/memory/openq/*` — unresolved questions |
| `progress` | `docs/memory/progress/*` — where we are |
| `session-digest` | `docs/memory/archive/sessions/*` |
| `design-doc` | `docs/design-docs/*` |
| `product-spec` | `docs/product-specs/*` |
| `exec-plan` | `docs/exec-plans/**` |
| `reference` | `docs/references/*` — external-API digests |
| `methodology` | top-level machine docs (PLANS, DESIGN, …) |

`type` is *intrinsic kind*, the directory is *location*; they usually agree, but
`type` is authoritative for machine routing (a `knowledge`-typed page can live
outside `knowledge/`). It is scalar, so the flat parser already reads it — **no
parser change needed for `type`.**

**`resource` — asset binding.** An optional scalar: a repo-relative path
(preferred) or a URL identifying the single primary asset the page documents
(e.g. `plugin/scripts/harness_lib.py`). Absent for pages describing abstract
ideas or many assets. Scalar → flat parser reads it unchanged. This field is the
**precondition for Phase-2 drift detection** (compare the resource's git state
against `last_verified`); Phase 1 only introduces and populates the field — no
drift logic, and the lint does **not** verify the target exists (permissive).

**`tags` — cross-cutting facets.** An optional list of short lowercase strings.
**Canonical authored form is YAML flow inline:** `tags: [a, b, c]` on one line.
This is compact, diff-friendly, and the cheapest possible parser extension. The
parser additionally *tolerates* the OKF block form (`tags:` then `- a` lines) on
read, so we can consume foreign OKF bundles, but our own pages author the flow
form.

**`description` — the navigation snippet.** An optional scalar: a *single
sentence* summarizing the page, self-contained (readable without the body). It is
the highest-value navigation key — what a code-execution catalog or the Phase-2
tool surfaces per page, and the basis for *generating* category indexes instead of
hand-maintaining them. Especially recommended for long pages; short pages where
the H1 + first line already say it MAY omit it. Scalar → flat parser reads it.

**`title` — optional display override.** An optional scalar display name. Because
every page already carries an H1 (and OKF itself derives title from the H1/
filename when absent), `title` is authored **only** when the H1 is a poor display
label (e.g. an H1 with inline code, or a filename-driven heading). Low value for
us; included for OKF parity and the occasional override. Scalar.

### D-2. Parser upgrade — `harness_lib.read_frontmatter` (R3)

`read_frontmatter` gains list handling, strictly additively:

- **Contract change:** the returned dict's *values* are now `str | list[str]`
  instead of `str`. A value is a `list[str]` **only** when the source uses a list
  form; every scalar `key: value` line continues to yield the identical string.
- **Flow form:** a value matching `[ ... ]` is parsed into a list by splitting on
  commas and stripping whitespace/quotes from each element; `[]` → `[]`.
- **Block form (tolerated):** a `key:` line with an empty value followed by lines
  whose stripped form starts with `- ` accumulates those items into a list until
  a non-item line. This is the one place the loop must look past the current line;
  it must not disturb scalar parsing.
- **Backward-compatibility proof:** no existing page uses a list-valued key (every
  current key is `status`/`last_verified`/`owner`/etc., all scalar), so the
  upgrade changes *zero* existing parse results. The new parser tests assert both
  the new list behavior and a representative scalar-unchanged case.

**Blast-radius check.** `read_frontmatter` is called by `lint_docs.py`, the
feeder, and the imprint scripts. All existing callers read only scalar keys
(`status`, `last_verified`, `owner`) and never touch `tags`/list values, so a
`list` appearing under a new key cannot reach a code path that assumes `str`.
The ExecPlan verifies this by grep + a GREEN full-suite run.

Files: `plugin/scripts/harness_lib.py` (the function), `tests/` (new parser
test module).

### D-3. Lint — permissive by construction (R2)

No new D-rule. `lint_docs.py` is touched only as needed to:

- leave `FM_REQUIRED` and `D3` exactly as they are (the new keys are never
  required); and
- confirm (via the existing tests + a new assertion) that a page carrying the new
  keys — including a `list`-valued `tags` — passes all current rules unchanged.

The lint deliberately does **not** validate `type` against the recommended
vocabulary, nor check that `resource` resolves, nor constrain `tags` values:
permissive consumption is the OKF lesson we keep (`okf-comparison.md` §5, "do NOT
adopt … rejection" — applied here as "do not reject on the *new* keys"). Any
soft, non-blocking reporting on these keys is Phase-2 navigation-tool territory.

### D-4. The versioned format spec — `docs/KNOWLEDGE_FORMAT.md` (R4)

A new top-level governed doc, peer to `PLANS.md`/`DESIGN.md`, that makes the
format explicit. Sections:

- **Version.** Declares **Knowledge Format v1.0** (the required-key core is
  production-proven; `type`/`tags`/`resource`/`title`/`description` are the keys
  this version introduces). Versioning convention mirrors OKF's `<major>.<minor>`
  (minor = backward-compatible additions, major = breaking).
- **Frontmatter schema.** Required (`status`, `last_verified`, `owner`) with
  their meaning + the staleness contract; recommended, in two tiers —
  routing/binding (`type`, `resource`, `tags`) and display (`title`,
  `description`) — with D-1's semantics and the recommended `type` vocabulary.
- **Reserved filenames.** `index.md` (category listing, registered per D8),
  `MEMORY.md` (bootloader). 
- **Link semantics.** Markdown links form the cross-cutting graph; `D5` rejects
  broken links (stricter than OKF, which tolerates them — noted as a deliberate
  divergence with a one-line why).
- **Conformance.** The rules a conformant page satisfies, each mapped to its
  D-rule ID (D3 frontmatter, D4 staleness, D5 links, D6 kebab naming, D8 index
  registration). This is the "implicit-in-lint → explicit" payoff: the spec and
  the gate are two views of one contract.
- **Relationship to OKF.** A short pointer to `okf-comparison.md`: shared
  substrate, the permissive-vs-enforced divergence, and that `type`/`tags`/
  `resource`/`title`/`description` are the adopted keys.

It carries standard frontmatter (`status: stable`) and is added to the `AGENTS.md`
Map table so it is discoverable.

**Governance scope (decision, see below):** Phase 1 makes `KNOWLEDGE_FORMAT.md` a
*governed top-level doc* (standard D3/D4 apply) but does **not** wire it into the
protected machine-doc set (`harness_lib.MANAGED_DOCS`/lint `MACHINE_DOCS`) or the
`scaffold.py` porting seed. That "protect from loosening + seed into every ported
host" step pulls the porting subsystem into a format change; it is deferred to
keep this phase focused (Non-goal NG-4).

### D-5. Authoring guidance (R5)

- `plugin/skills/docs-tree/SKILL.md`: the "frontmatter (`status / last_verified /
  owner`)" step gains a clause naming the optional `type`/`tags`/`resource` keys
  and pointing to `docs/KNOWLEDGE_FORMAT.md` for their semantics.
- `docs/memory/MEMORY.md`: the write-rules bullet that states "Every page carries
  frontmatter `status / last_verified / owner` (lint D3)" gains a sentence on the
  optional keys + the spec pointer.

### D-6. Representative backfill (R6)

Add the new keys to existing concept pages under
`docs/memory/{knowledge,adr,limitations,openq}/` (not the `index.md` files):

- `type` on every such page, matching the D-1 vocabulary for its directory.
- `tags` on every such page (2–5 facets each, flow form).
- `description` on every such page — one self-contained sentence (often
  liftable from the page's existing `index.md` one-liner, which makes the
  duplication visible and sets up Phase-2 index generation).
- `resource` on pages that document one concrete code asset (e.g.
  `knowledge/recursion-guard.md` → `plugin/scripts/harness_lib.py`); omitted for
  purely abstract pages.
- `title` is **not** backfilled (every page's H1 is already a fine label).

This is a bounded set (currently a handful of pages), proves the format
end-to-end, and seeds Phase-2 with real `type`/`tag`/`resource`/`description`
data. The `last_verified` of each touched page is bumped to the edit date (the
edit *is* a re-verification of the page against reality, per D4 semantics).

### Decisions resolved autonomously (recorded per methodology)

- **`type` = epistemic kind, free vocabulary.** Chosen over an OKF-style
  subject-kind and over a lint-enforced closed vocabulary: it lifts the taxonomy
  we already have into a queryable field while honoring the permissive mandate.
- **Add `description` (high value) + `title` (parity only); both optional, no
  gate.** `description` is the navigation snippet — the same introduce-now /
  consume-in-Phase-2 shape as `resource`, which is why deferring it (the original
  NG-2) was inconsistent. `title` is mostly redundant with our H1, so it is in
  the schema for OKF parity but authored only as an override. Neither is
  gate-checked (permissive, per D-3).
- **`tags` canonical = YAML flow inline `[a, b]`, block form tolerated on read.**
  Chosen over (a) inline-string-without-parsing and (b) comma-separated scalar:
  it is real (minimal) YAML, gives Phase-2 genuine lists, and makes us able to
  read OKF bundles, at the cost of a ~small additive parser change. The
  alternatives avoid the parser change but push list-parsing into every consumer
  and break OKF interop.
- **Format spec as a governed top-level doc, protection/porting deferred.** See
  D-4 / NG-4 — keeps a format phase out of the porting subsystem.
- **Backfill scoped to `memory/{knowledge,adr,limitations,openq}` concept
  pages.** Proves the format without churning all ~80 docs (YAGNI); exec-plans,
  product-specs, references, and top-level docs are not backfilled this phase.

## Non-goals

Each NG below is fenced out of Phase 1 but carried forward to a named home in the
"Next phase — deferred roadmap" section; none is dropped.

- **NG-1 — The query / navigation tool.** No backlinks index, graph view, type/
  tag filter, or `viz.html`. That is Phase 2, built *on* this format.
- **NG-2 — Generating indexes from `description`.** The `description` field is
  introduced and populated, but `index.md` files stay hand-maintained this phase;
  auto-generating them from page descriptions (resolving the index/description
  duplication) is a Phase-2 consumer, like drift detection for `resource`.
- **NG-3 — Drift detection.** `resource` is introduced and populated but no code
  compares it against `last_verified` this phase.
- **NG-4 — Protected-doc / porting wiring for `KNOWLEDGE_FORMAT.md`.** Not added
  to `MANAGED_DOCS`/`MACHINE_DOCS`/`scaffold.py` this phase (D-4).
- **NG-5 — Full-corpus backfill.** Only the memory concept-page slice (D-6).
- **NG-6 — Typed link relationships.** Links stay untyped edges (as in OKF);
  relationship kind remains in prose.
- **NG-7 — Lint validation of the new keys.** No vocabulary check, no
  resource-resolves check (D-3).

## Acceptance criteria

1. `docs/KNOWLEDGE_FORMAT.md` exists, declares Knowledge Format v1.0, documents
   the required + the five optional keys (`type`/`tags`/`resource`/`title`/
   `description`) with the `type` vocabulary and the `tags` canonical form, maps
   conformance to D-rule IDs, and is linked from the `AGENTS.md` Map. (R1, R4)
2. A unittest for `read_frontmatter` asserts: a flow-form `tags: [a, b]` parses to
   `["a", "b"]`; a block-form list parses to the same; an existing scalar key
   parses to its unchanged string. The test fails on the pre-change parser and
   passes after. (R3)
3. `python3 plugin/scripts/check.py` is GREEN, with the corpus containing pages
   that both use and omit the new keys. Removing any of the new keys from any
   page keeps it GREEN; no D-rule names them. (R2, R7)
4. Every page under `docs/memory/{knowledge,adr,limitations,openq}/` except
   `index.md` carries `type`, `tags`, and a one-sentence `description`; pages
   documenting one code asset carry `resource`. (R6)
5. `plugin/skills/docs-tree/SKILL.md` and `docs/memory/MEMORY.md` mention the
   optional keys and point to `docs/KNOWLEDGE_FORMAT.md`. (R5)

## Next phase — deferred roadmap (durable; do not drop)

Everything Phase 1 fences out (the NG-* list) has a named future home here, so the
roadmap survives this spec. Nothing below is built in Phase 1.

### Phase 2 — Knowledge navigation/query tool + agentic skill (separate spec)

**Specced & in progress:**
[2026-06-18-knowledge-navigation-tool.md](2026-06-18-knowledge-navigation-tool.md)
(live-query `nav.py` + `docs-nav` skill; committed catalog, generated `index.md`,
and the graph view are all NON-goals there — see its decisions).

The *consumer* of the Phase-1 format. Consumes `type`/`tags`/`description` +
`resource` + the D5 link graph to provide a queryable catalog
(`(path, type, tags, description)` an agent filters without loading bodies),
backlinks ("what links here"), kind/tag/status filters, and stale/orphan
detection — surfaced both as a code-execution tool and an agentic docs-navigation
skill, optionally with an OKF-style graph view. Phase 2 absorbs these Phase-1
deferrals:

- **Drift detection** (from NG-3) — diff each page's `resource` against its
  `last_verified` (git state / hash) and flag pages whose code moved under them.
  The `resource` field exists precisely to enable this.
- **Generated indexes** (from NG-2) — auto-build `index.md` listings from page
  `description`s, retiring the hand-maintained index/description duplication.
- **Full-corpus backfill** (from NG-5) — ✅ **DONE 2026-06-18** (pulled forward at
  user request): `type`/`tags`/`description` applied to the remaining 68 content
  pages (machine docs, design-docs, product-specs, completed exec-plans, session
  digests, progress) via parallel subagents; `last_verified` deliberately not
  bumped (mechanical metadata-add, per the refined KNOWLEDGE_FORMAT.md rule).
  `index.md` files, `MEMORY.md`, and `ARCHITECTURE.md` (no frontmatter) excluded.

### Later — format & governance evolutions (post-Phase-2, own specs)

- **Typed link relationships** (from NG-6) — a future *format* minor version
  (KF v1.1+): give links a relationship kind (`supersedes`, `refines`,
  `depends-on`) instead of untyped edges. Format-layer change, versioned per the
  `KNOWLEDGE_FORMAT.md` scheme; worth doing only if Phase-2 navigation shows the
  untyped graph is too coarse. **Step 1 (inference-first, no format change) is now
  specced**: [Derived hierarchy — inferred typed graph + `nav.py tree`](2026-06-19-nav-derived-hierarchy.md)
  infers edge kinds from `(type, type, direction)` so declared keys are added later
  only if a query needs a relationship inference cannot supply.
- **Lint validation of the new keys** (from NG-7) — a future *governance*
  tightening: once the keys are proven in daily use, optionally promote some from
  permissive to checked (e.g. validate `type` against the vocabulary, verify a
  repo-relative `resource` resolves the way D5 does for links). Deliberately last
  — we keep OKF's permissive stance until there is evidence a check earns its
  blocking cost.
- **Protected-doc / porting wiring for `KNOWLEDGE_FORMAT.md`** (from NG-4) — add
  it to `MANAGED_DOCS`/`MACHINE_DOCS` + a `scaffold.py` seed so every ported host
  carries the format spec, protected from staleness-loosening. Do this when the
  porting path is next exercised.
