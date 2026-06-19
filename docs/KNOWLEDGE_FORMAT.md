---
status: stable
last_verified: 2026-06-19
owner: harness
type: methodology
tags: [knowledge-format, frontmatter, lint]
description: The Knowledge Format v1.2 contract that every knowledge page in this repo follows, making explicit the rules governed by the lint_docs.py D-gate.
---
# KNOWLEDGE_FORMAT.md — the harness knowledge format

**Knowledge Format (KF) v1.2.** The contract every knowledge page in this repo
follows: a markdown body under a YAML-ish frontmatter block, governed by the
`lint_docs.py` D-rules. This document makes the format *explicit* — until now it
lived implicitly in the lint. Author a conformant page from this doc alone; you
do not need to read `lint_docs.py`.

Grounded in the OKF parity analysis
([`design-docs/okf-comparison.md`](design-docs/okf-comparison.md)): KF shares
OKF's markdown+frontmatter substrate and adopts its recommended keys, but keeps
our **enforced** gate (OKF tells consumers never to reject; we reject rot at
commit). The asymmetry is the whole design: **permissive on the optional keys,
strict on the required ones.**

## 1. A page

```
---
<frontmatter: YAML-ish key/value>
---
<markdown body>
```

The frontmatter is delimited by `---` on its own line at the top and a closing
`---`. Everything after the closing fence is the body. A file with no parseable
frontmatter fails the gate (D3) unless it is in an exempt tree (`generated/`,
`superpowers/`, or a host's `.harnessignore` subtree).

## 2. Frontmatter schema

### 2.1 Required (the gate enforces these — D3)

Exactly these three keys must be present on every governed page:

| Key | Meaning |
|---|---|
| `status` | `stable` / `active` / `draft` / `archived` / `completed`. Drives the staleness exemption: `archived` and `completed` pages are stale-exempt (D4). |
| `last_verified` | ISO `YYYY-MM-DD` of the last time the page's **content was checked against reality**. Over `STALE_DAYS` (30) old and not archived/completed → **D4 fails**. Bump it on a **content** edit (you verified the page). A purely **mechanical metadata-only change** — e.g. a bulk add of optional navigation keys — is *not* a re-verification and must **not** bump it: resetting the clock at scale would erode the staleness signal the gate depends on. |
| `owner` | Who maintains the page (e.g. `harness`, `doc-gardener`, `imprint-job`). |

These are governance fields with no OKF equivalent; they are what makes the
corpus a *maintained working memory* rather than a static catalog.

### 2.2 Recommended (optional — the gate never requires or rejects these)

Two tiers. All are optional; a page may carry any, all, or none. No D-rule names
them (KF keeps OKF's permissive stance for optional keys).

**Routing / binding** — machine axes a navigator filters and traverses on:

| Key | Form | Meaning |
|---|---|---|
| `type` | scalar | The page's *concept-kind*, made explicit and queryable independent of directory. See the vocabulary in §2.3. Intrinsic kind; the directory is location — they usually agree, but `type` is authoritative for machine routing. |
| `tags` | **list** | Cross-cutting facets — short lowercase strings. Canonical authored form is YAML flow inline: `tags: [a, b, c]`. (The parser also tolerates the block form `- a` on read for OKF-bundle interop; author the flow form.) |
| `resource` | scalar | A repo-relative path (preferred) or URL identifying the single primary asset the page documents (e.g. `plugin/scripts/harness_lib.py`). Absent for abstract pages. The precondition for future drift detection (compare the asset's state against `last_verified`). |
| `phase` | scalar | The initiative + phase this page belongs to, convention `<initiative>/<NN>-<slug>` (e.g. `symphony/04-worker-authority`; a bare `<initiative>` is the initiative umbrella). The **group-by axis for the derived roadmap** (`nav.py roadmap`): `NN` orders phases within an initiative, bare-initiative sorts first, a non-numeric `NN` sorts last. Absent → the page is unphased. A plan with no `phase` inherits it from the spec it `implements`. |
| `supersedes` | scalar **or list** | Repo-relative `.md` path(s) this page **replaces** — a *declared* pivot edge, the one genuine "design changed" signal. `nav.py` emits a `supersedes` relation to each target (additive to the inferred archived-supersession), surfaced inline in `roadmap`/`map` as `[superseded-by …]`. This is KF's **first declared edge**; all other relationship kinds stay inferred from the link graph (KF v1.2). |

**Display** — labels for navigation, zero machine cost:

| Key | Form | Meaning |
|---|---|---|
| `description` | scalar | One self-contained sentence summarizing the page — readable without the body. The navigation snippet a catalog or tool surfaces per page, and the basis for generated indexes. Especially recommended for long pages. |
| `title` | scalar | Display-name override. Authored **only** when the H1 is a poor label; otherwise the H1 (or filename) is the title. |

Together `(path, type, tags, description)` is a queryable table-of-contents an
agent can filter by code execution over frontmatter, without loading any body.
These axes are also what make **structure a projection of metadata, not the file
tree**: `nav.py` derives the hierarchy (`tree`) and the progress map (`roadmap`)
from `type` + `phase` + the link graph, independent of where files physically
live — so indexes and roadmaps are computed, never hand-maintained.

### 2.3 Recommended `type` vocabulary

Free and extensible — a consumer tolerates unknown values (OKF-style). Lift our
directory-implicit taxonomy into the field:

| `type` | For pages like |
|---|---|
| `knowledge` | `memory/knowledge/*` — reusable how-it-works |
| `adr` | `memory/adr/*` — decision + why |
| `limitation` | `memory/limitations/*` — known landmines |
| `openq` | `memory/openq/*` — unresolved questions |
| `progress` | `memory/progress/*` — where we are |
| `session-digest` | `memory/archive/sessions/*` |
| `design-doc` | `design-docs/*` |
| `product-spec` | `product-specs/*` |
| `exec-plan` | `exec-plans/**` |
| `reference` | `references/*` — external-API digests |
| `methodology` | top-level machine docs (PLANS, DESIGN, …) |
| `charter` | `CHARTER.md` — top-level intent: mission, design philosophy (기획의도), locked assumptions |

### 2.4 Frontmatter value forms

The parser (`harness_lib.read_frontmatter`) is flat-but-list-aware:

- **Scalar:** `key: value` → string (everything after the first `:`; a `:` inside
  the value is preserved).
- **Flow list:** `key: [a, b, c]` → `["a","b","c"]`; `[]` → `[]`.
- **Block list:** `key:` then `- a` / `- b` lines (indented or not) → `["a","b"]`.
- **Empty:** `key:` with nothing after and no `- ` lines → `""` (a scalar).

Extra producer-defined keys beyond this schema are allowed and preserved; the
gate ignores them.

## 3. Reserved filenames

| File | Role |
|---|---|
| `index.md` | A category's listing — one entry per page (D8 requires it in indexed dirs and that every page is registered). |
| `MEMORY.md` | The memory bootloader / loading protocol (`docs/memory/MEMORY.md`). |

Top-level machine docs are `UPPER_CASE.md` (this file, `PLANS.md`, `DESIGN.md`,
…); all other pages are `kebab-case.md` (D6).

## 4. Links

Pages cross-link with standard markdown links, forming a graph over the directory
tree — the structure `nav.py` traverses and against which `orphans` / `backlinks`
are computed. **Unlike OKF, broken links fail the gate (D5):** a link whose `.md`
target does not exist is an error, not "not-yet-written knowledge." For a corpus
an actor *acts on*, a dangling pointer is a defect.

**How to write one.** Standard markdown, with the *concept name* as the link
text — `[the completion gate](PLANS.md)`, never `[here](PLANS.md)`:

- **Target** a repo `.md` path. Resolution mirrors the gate: relative to the
  page's own directory first, then the repo root — an `adr/` page links a sibling
  knowledge page as `../knowledge/foo.md`, a root doc as `memory/knowledge/foo.md`.
- **Anchor** a section by appending its heading slug: `[…](DESIGN.md#some-heading)`.
- **Verify** before committing — D5 rejects a broken target, and `nav.py links
  <page>` prints the edges it actually resolved.
- **External URLs** (`http(s)://`) are fine as citations but are **not corpus
  edges**: D5 ignores them and the graph never sees them. Durable external facts
  get their own page under `docs/references/`.
- **Never hand-maintain backlinks.** The reverse graph is computed live
  (`nav.py backlinks <page>`); author *forward* links only — no "Cited by" lists.

Relationship *kind* is otherwise not written on the link: links are untyped edges,
and `nav.py` **infers** the kind from the endpoints' `type` (`implements`,
`refines`, `grounded-in`, …). The one exception is **`supersedes`**, which may be
**declared** as a frontmatter key (§2.2) — the single genuine pivot signal; all
other relationship kinds stay inferred. For *when* a relationship earns a link at
all — and the anti-orphan rule that every page needs an inbound one — see the
`docs-tree` authoring procedure.

## 5. Conformance — the spec and the gate are two views of one contract

A page is KF conformant when it satisfies the D-rules that apply to it.
Each is enforced by `plugin/scripts/lint_docs.py` and surfaced by the
`harness-lint` skill:

| Rule | Requirement |
|---|---|
| **D3** | Parseable frontmatter with `status`, `last_verified`, `owner`. |
| **D4** | `last_verified` within `STALE_DAYS` (30), unless `status` is `archived`/`completed`. |
| **D5** | Every markdown link to a `.md` target resolves. |
| **D6** | Filename is `kebab-case.md` (or `UPPER_CASE.md` for top-level machine docs). |
| **D8** | Indexed categories have an `index.md`, and every page is registered in it. |

The optional keys (§2.2) are intentionally **outside** conformance: a page is no
less conformant for omitting them, and no more conformant for malformed ones.
Promoting any optional key to a checked rule is a future governance decision,
made only once the key has proven its worth in daily use.

## 6. Versioning

KF is versioned `<major>.<minor>` (OKF's scheme): a **minor** bump adds
backward-compatible options (a new optional key, a new conventional section); a
**major** bump may rename a required key or change a reserved filename.

- **v1.0** — the required-key core, plus the optional keys `type`, `tags`,
  `resource`, `title`, and `description`.
- **v1.1** — adds the optional `phase` key (the derived-roadmap group-by) and the
  `charter` value to the `type` vocabulary.
- **v1.2** (current) — adds the optional `supersedes` key, KF's first **declared**
  edge (all other relationships stay inferred from the link graph). Additive:
  every earlier page stays conformant.

## 7. Relationship to OKF

KF and Google's Open Knowledge Format independently chose the same substrate
(markdown + frontmatter + git tree + `index.md` progressive disclosure + a
markdown-link graph + a `references/` dir). KF adopts OKF's entire recommended
frontmatter surface — `type`, `title`, `description`, `resource`, `tags` — and
omits only OKF's `timestamp` (our required `last_verified` subsumes it and drives
the staleness gate). The divergence is objective-function, not quality: OKF
optimizes permissive exchange across an untrusted boundary; KF optimizes a single
actor's enforced, fresh working memory. Full analysis:
[`design-docs/okf-comparison.md`](design-docs/okf-comparison.md).
