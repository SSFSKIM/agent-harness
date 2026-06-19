---
status: stable
last_verified: {{TODAY}}
owner: harness
type: methodology
tags: [knowledge-format, frontmatter, lint]
description: The Knowledge Format v2.0 contract that every knowledge page in this repo follows, making explicit the rules governed by the lint D-gate.
---
# KNOWLEDGE_FORMAT.md — the harness knowledge format

**Knowledge Format (KF) v2.0.** The contract every knowledge page in this repo
follows: a markdown body under a YAML-ish frontmatter block, governed by the
lint **D-rules**. This document makes the format *explicit* — until now it
lived implicitly in the lint. Author a conformant page from this doc alone; you
do not need to read the lint source.

Informed by Google's **Open Knowledge Format (OKF)**: KF shares OKF's
markdown+frontmatter substrate and adopts its recommended keys. But where OKF
tells consumers *never to reject* (it is a general **exchange** format), KF runs
an **enforced** gate — and **v2.0 flips the old "permissive on optional" stance**:
the load-bearing **navigation** keys (`type`, `description`, and `phase` on the
work-tier anchor) are now *checked rules*. We are a single actor's **enforced,
fresh working memory**, so a key whose absence silently costs navigability is a
defect, not a free choice. What stays optional is a thin tail (`tags`, `title`)
plus the *validate-if-present* keys (`resource`, `supersedes`, `phase` elsewhere).
Why we diverge from OKF here: §7.

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

### 2.1 Required (the gate enforces these)

**Governance core (D3)** — present on every governed page:

| Key | Meaning |
|---|---|
| `status` | `stable` / `active` / `draft` / `archived` / `completed`. Drives the staleness exemption: `archived` and `completed` pages are stale-exempt (D4). |
| `last_verified` | ISO `YYYY-MM-DD` of the last time the page's **content was checked against reality**. Over `STALE_DAYS` (30) old and not archived/completed → **D4 fails**. Bump it on a **content** edit (you verified the page). A purely **mechanical metadata-only change** — e.g. a bulk add of navigation keys — is *not* a re-verification and must **not** bump it: resetting the clock at scale would erode the staleness signal the gate depends on. |
| `owner` | Who maintains the page (e.g. `harness`, `doc-gardener`, `imprint-job`). |

These are governance fields with no OKF equivalent; they make the corpus a
*maintained working memory* rather than a static catalog.

**Navigation core (D11, KF v2.0)** — present on every governed *content* page
(reserved spines `index.md`/`MEMORY.md` are exempt — they are listings, not
navigable concept-pages):

| Key | Requirement |
|---|---|
| `type` | A non-empty `type` — the page's *concept-kind*, queryable independent of directory (vocabulary in §2.3). **Presence** is enforced; the *value* stays free/extensible (OKF's tolerate-unknown is kept for values). |
| `description` | A non-empty one-line self-contained summary — the navigation snippet a catalog/tool surfaces per page, and the basis for generated indexes. |
| `phase` | **Required on `product-spec`** (it anchors the derived roadmap). Other types may omit it — an `exec-plan` inherits its spec's phase via the `implements` edge. Must be well-formed when present (§2.2). |

### 2.2 Optional and validate-if-present

**Optional (never checked)** — a page may carry these or not:

| Key | Form | Meaning |
|---|---|---|
| `tags` | **list** | Cross-cutting facets — short lowercase strings. Canonical authored form is YAML flow inline: `tags: [a, b, c]`. (The parser also tolerates the block form `- a` on read for OKF-bundle interop; author the flow form.) |
| `title` | scalar | Display-name override. Authored **only** when the H1 is a poor label; otherwise the H1 (or filename) is the title. |

**Validate-if-present (D12)** — *not* required, but checked for correctness when
authored (an authored-but-broken value is a defect; an absent one is fine):

| Key | Form | Meaning + check |
|---|---|---|
| `resource` | scalar | A repo-relative path (preferred) or URL identifying the single primary asset the page documents (e.g. `src/auth/session.py`). Absent for abstract pages. **D12: if a repo path (not a URL), it must exist.** The precondition for drift detection. |
| `supersedes` | scalar **or list** | Repo-relative `.md` path(s) this page **replaces** — a *declared* pivot edge, the one genuine "design changed" signal. `nav.py` emits a `supersedes` relation to each target, surfaced inline in `roadmap`/`map` as `[superseded-by …]` — KF's first declared edge. **D12: each target must resolve.** |
| `phase` | scalar | The initiative + phase, convention `<initiative>/<NN>-<slug>` (e.g. `payments/04-refunds`; a bare `<initiative>` is the umbrella). The **group-by axis for the derived roadmap**: `NN` orders phases within an initiative. **D12: well-formed when present** (`<initiative>` or `<initiative>/<NN>-<slug>`, NN numeric). (Required on `product-spec` — §2.1.) |

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
| `charter` | `CHARTER.md` — top-level intent: mission, design philosophy, locked assumptions |

### 2.4 Frontmatter value forms

The frontmatter parser is flat-but-list-aware:

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
Each is enforced by the gate (the lint the `harness-lint` skill runs) on every
commit:

| Rule | Requirement |
|---|---|
| **D3** | Parseable frontmatter with `status`, `last_verified`, `owner`. |
| **D4** | `last_verified` within `STALE_DAYS` (30), unless `status` is `archived`/`completed`. |
| **D5** | Every markdown link to a `.md` target resolves. |
| **D6** | Filename is `kebab-case.md` (or `UPPER_CASE.md` for top-level machine docs). |
| **D8** | Indexed categories have an `index.md`, and every page is registered in it. |
| **D11** | Navigation core (KF v2.0): non-empty `type` + `description` on every governed content page; `phase` on every `product-spec`. (Reserved spines `index.md`/`MEMORY.md` exempt.) |
| **D12** | Validate-if-present: a repo-path `resource` exists, each `supersedes` target resolves, and `phase` is well-formed. |

The remaining keys (`tags`, `title`) stay **outside** conformance — a page is no
less conformant for omitting them. The v2.0 shift: the load-bearing navigation
keys were promoted from optional to checked once they proved load-bearing in daily
use. Promoting a further key remains a governance decision made on that evidence.

## 6. Versioning

KF is versioned `<major>.<minor>` (OKF's scheme): a **minor** bump adds
backward-compatible options (a new optional key, a new conventional section); a
**major** bump may rename a required key or change a reserved filename.

- **v1.0** — the required-key core, plus the optional keys `type`, `tags`,
  `resource`, `title`, and `description`.
- **v1.1** — adds the optional `phase` key (the derived-roadmap group-by) and the
  `charter` value to the `type` vocabulary.
- **v1.2** — adds the optional `supersedes` key, KF's first **declared** edge
  (all other relationships stay inferred from the link graph). Additive.
- **v2.0** (current) — **conformance-breaking governance flip**: `type` +
  `description` become required (D11), `phase` becomes required on `product-spec`
  (D11), and `resource`/`supersedes`/`phase` are validated when present (D12). The
  major bump reflects that pages valid under v1.x may now fail. Rationale: §7.

## 7. Relationship to OKF

KF and Google's Open Knowledge Format independently chose the same substrate
(markdown + frontmatter + git tree + `index.md` progressive disclosure + a
markdown-link graph + a `references/` dir). KF adopts OKF's entire recommended
frontmatter surface — `type`, `title`, `description`, `resource`, `tags` — and
omits only OKF's `timestamp` (our required `last_verified` subsumes it and drives
the staleness gate). The divergence is objective-function, not quality: OKF
optimizes permissive exchange across an untrusted boundary; KF optimizes a single
actor's enforced, fresh working memory. **v2.0 sharpens exactly this divergence**:
OKF keeps its recommended keys advisory because a producer it cannot control might
omit them; we *do* control our producers (one actor, one gate), so we enforce the
navigation surface OKF leaves permissive.
