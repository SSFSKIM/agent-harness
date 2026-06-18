---
status: stable
last_verified: 2026-06-17
owner: harness
---
# OKF parity — Google's Open Knowledge Format vs our docs/memory system

A holistic comparison of Google's **Open Knowledge Format (OKF v0.1, Draft)**
against this harness's knowledge system (`docs/`, `docs/memory/`, the docs-tree
skill, and the `lint_docs.py` D-gate). Written 2026-06-17 from a full read of
both sides: the OKF spec end-to-end (`SPEC.md` §1–11 + appendix), the reference
enrichment agent + visualizer READMEs, and three produced bundles
(`ga4`, `stackoverflow`, `crypto_bitcoin`) on Google's side; our `AGENTS.md`,
`docs-tree` skill, `lint_docs.py`, `MEMORY.md` bootloader, and the live memory
tree on ours.

Sources: <https://github.com/GoogleCloudPlatform/knowledge-catalog> —
`okf/SPEC.md`, `okf/README.md`, `okf/bundles/*`. Apache-2.0, "not an official
Google product." Announced via the Cloud blog on the Open Knowledge Format.

This is observational (what differs and why), not a roadmap. Concrete adoptions
are ranked in the last section; none are committed work until they have a spec.

---

## 0. The category caveat — read this first

OKF and our system are **not the same kind of artifact**, and the comparison is
unfair unless that is named up front.

- **OKF is a *format specification*.** It standardizes the smallest set of
  structural rules needed to make a markdown corpus self-describing, and
  **deliberately scopes out** storage, serving, query infrastructure, lifecycle,
  and any fixed taxonomy (SPEC §1 Non-goals). It punts everything past "what a
  file looks like" to the producer.
- **Ours is a *governed system*.** It is a format **plus** a lifecycle (staleness,
  ownership, status) **plus** a blocking gate (`check.py` → `lint_docs.py`)
  **plus** a loading protocol (`MEMORY.md`) **plus** an operating loop that
  *acts* on the knowledge.

So the fair read has two layers:

1. **Format layer (apples-to-apples).** Frontmatter fields, directory/index
   conventions, link semantics. Here OKF has things we lack and vice versa.
2. **Lifecycle layer.** Most of "what we have that OKF lacks" is something OKF
   *chose* to leave open, not something it failed at. Crediting us there is only
   fair if we also credit OKF for being intentionally minimal so anyone can
   produce into it. Both points are made below.

## 1. The headline: same substrate, opposite objective functions

Strip the surface and both systems made the **same substrate decision**:
knowledge is a git-versioned **directory of markdown files with YAML
frontmatter**, human- *and* agent-readable with no SDK, navigated by `index.md`
progressive disclosure, cross-linked into a graph by plain markdown links. Two
teams arrived there independently — OKF for cross-org **data-catalog exchange**,
us for intra-repo **software-engineering self-governance**. That convergence is
the real signal: the substrate is hardening into a de-facto standard.

The divergence is not contradiction; it is **different objective functions**:

- **OKF maximizes interoperability across an untrusted, multi-producer
  boundary.** Many independent producers (humans, ADK/LangChain/custom agents,
  catalog exporters), many independent consumers (LLMs, MkDocs, graph viewers),
  no shared authority. The optimal stance is *permissive*: one required field
  (`type`), and consumers **MUST NOT reject** a bundle for missing fields,
  unknown types, or broken links (SPEC §9). Never lose knowledge in transit.

- **We maximize freshness and correctness of one actor's working memory inside a
  single trusted repo.** The harness *acts* on this corpus, so a stale or
  unregistered fact is a live hazard. The optimal stance is the **opposite**:
  a blocking gate that *rejects* rot. Never let the corpus decay in place.

Everything below is downstream of that one difference.

## 2. Shared — what both arrived at independently (the convergent core)

| Convergent pattern | OKF | Here |
|---|---|---|
| Markdown body + YAML frontmatter as the unit of knowledge | §4 | every page |
| Git-versioned directory tree, domain-independent layout | §3 | whole `docs/` tree, `docs-tree` skill |
| `index.md` for **progressive disclosure** (see-before-open) | §6 | every category `index.md`; `MEMORY.md` "navigate on demand" |
| Cross-links via standard markdown links → **graph over tree** | §5 | links, validated by lint **D5** |
| One-line `description` used by index generators / snippets | §4.1 | one-line entry per page in each `index.md` |
| A last-modified timestamp in frontmatter | `timestamp` (opt) | `last_verified` (required) |
| A **chronological change log** | §7 `log.md` | `progress/current.md`, ADR History sections, `archive/sessions/`, QUALITY_SCORE History |
| **Citations / sources** backing claims | §8 `# Citations` | `## Source` sections (e.g. `knowledge/recursion-guard.md`) |
| A **`references/` dir** holding external material as first-class pages | §8 note | `docs/references/` (llms.txt digests) |
| Reserved filenames with defined meaning (`index.md`) | §3.1 | `index.md`, `MEMORY.md` |
| Extensibility — arbitrary extra frontmatter keys tolerated | §4.1 | extra keys allowed; gate checks only required ones |

The striking ones: both independently minted a `references/` directory for
mirrored external knowledge, and both treat `index.md` as the progressive-
disclosure spine rather than dumping the whole corpus into context.

## 3. What OKF advanced that we lack (candidate adoptions)

These are real gaps at the **format layer** — things OKF's frontmatter/structure
encodes that ours does not.

1. **`type` as the single required, routing-first field.** OKF's one mandatory
   field is `type` (`BigQuery Table`, `Playbook`, `Reference`, `Metric`, …),
   used by consumers for routing/filtering/presentation. Our required fields are
   `status / last_verified / owner` — *governance* fields — and we carry **no
   machine-readable concept-kind**. Our "type" is implicit in the *directory*
   (`knowledge/` vs `adr/` vs `limitations/` vs `openq/`). OKF makes kind
   explicit and **orthogonal to location**, so a corpus is filterable by kind
   without knowing the directory taxonomy. This is the cleanest borrowable idea.

2. **`resource` — a canonical URI binding a concept to the real asset it
   describes.** OKF concepts can point at the live thing (a BigQuery table URL).
   We name sources in *prose* (`## Source: plugin/scripts/harness_lib.py`) but
   not as a structured, machine-resolvable field. A `resource:`/`source:`
   frontmatter key would let tooling link knowledge → code automatically and
   **detect drift** when the target changes — which is exactly what `doc-gardener`
   does by hand today.

3. **`tags` for cross-cutting facets** orthogonal to the tree. We have none; our
   only cross-cutting axis is manual links. OKF notes a tag-browse view can be
   synthesized at consumption time from frontmatter alone.

4. **A published, versioned interoperability spec.** OKF *names a version*
   (`okf_version`) and defines a 3-point conformance test (SPEC §9, §11). Our
   format is **implicit in `lint_docs.py`** — there is no externally publishable
   "this is a conformant harness knowledge page." If we ever want foreign agents
   to consume harness knowledge, we'd need to externalize the spec the way OKF
   did.

5. **The producer/consumer split as a first-class frame, with rules written *for
   the consumer*.** "Consumers MUST tolerate unknown types / broken links."
   OKF is engineered for exchange across organizational trust boundaries; that
   robustness-to-unknown-producer is something we structurally lack because we
   are a single closed corpus. Not a gap to "fix" — but the frame is worth
   stealing if harness knowledge ever crosses a repo boundary.

6. **A reference *consumer* artifact — the visualizer.** A self-contained
   `viz.html`: force-directed concept graph, type-colored nodes, **"Cited by"
   backlinks** (reverse link graph), search, type filter. We have no graph view;
   navigation is bootloader + indexes only. We already compute the link data
   (D5) — a generated graph/backlinks view is a cheap win for a growing corpus.

## 4. What we advanced that OKF lacks (mostly the lifecycle layer)

Per §0, much of this is OKF-by-design-omission, not OKF-failure. But for an
*actor's* working memory these are load-bearing, and OKF has no slot for them.

1. **An enforced conformance gate — the inverse of OKF's permissiveness.** OKF §9
   forbids rejection. Our `lint_docs.py` *is* rejection: **D3** required
   frontmatter, **D4** staleness, **D5** broken links FAIL, **D6** kebab-case,
   **D8** index registration FAIL, **D9** component coverage, **D10** machine-doc
   reference integrity — all block the commit via `check.py`. Opposite stance,
   because opposite objective (§1).

2. **Staleness as a first-class, *enforced* lifecycle.** `last_verified` + **D4**
   (stale after `STALE_DAYS=30` unless `status` is `archived`/`completed`) + the
   `doc-gardener` persona that re-reads pages against reality. OKF's `timestamp`
   is descriptive only — it has no concept of "this knowledge has *expired* and
   must be re-verified." For a corpus the agent acts on, **a stale fact is worse
   than a missing one**; this is arguably the single most important thing we have
   that OKF doesn't.

3. **An *epistemic* taxonomy, not just a subject taxonomy.** OKF's `type`
   classifies a concept's *subject*. Our memory classifies the **status of the
   knowledge itself**: `knowledge/` (settled how-it-works) vs `adr/` (decision +
   alternatives + why) vs `limitations/` (known landmines) vs `openq/`
   (unresolved questions) vs `progress/` (where we are) vs `archive/sessions/`
   (raw history). OKF has no slot to say "this is a *decision*" or "this is an
   *open question*." ADR especially (a genre of *why we chose X over Y*) has no
   OKF equivalent.

4. **A loading protocol / bootloader.** `MEMORY.md` defines the *order* to read,
   what to bulk-read vs lazy-load. OKF has progressive disclosure (the
   structure) but no opinion on *how an agent bootstraps a session*. We encode
   reading **strategy**, not just shape.

5. **`owner` — provenance of responsibility.** Every page names who maintains it
   (`imprint-job`, `doc-gardener`, `harness`), which drives the maintenance loop.
   OKF tracks the producing agent only implicitly via git.

6. **A quality meta-layer.** `QUALITY_SCORE.md` grades domain × layer A–F with
   history and trend. OKF has no quality/confidence dimension at all.

7. **A governance *gradient*, not uniform permissiveness.** `docs-tree` splits
   machine-critical/harness-managed roots (strict frontmatter + index + gate,
   `PROTECTED_PATHS` a host may only *tighten*) from host-owned project roots
   (convention only when useful; opt in via `.harness.json`). OKF is uniformly
   permissive; we have a **dial** — strict where correctness matters, loose where
   it doesn't.

8. **Knowledge wired into an operating loop, not a passive catalog.** OKF
   *describes data so agents can use the data* — the knowledge is inert. Ours
   *governs the actor*: review personas are grounded 1:1 in
   `RELIABILITY.md`/`SECURITY.md`/`ARCHITECTURE.md`; ADRs steer decisions; the
   feeder/imprint loop reads and writes memory; `D10` + the "**not in the repo =
   does not exist**" law make specific docs load-bearing. OKF describes the
   world; we govern an actor inside it.

## 5. Synthesis & ranked adoptions

**The takeaway.** Your read is correct: the *substrate* (md + frontmatter + git +
index + link-graph + `references/`) is converging into a de-facto standard for
agent knowledge, and OKF is its externalization for cross-org **data-catalog
exchange**. We built the same substrate for intra-repo **self-governance**, then
wrapped it in a lifecycle OKF intentionally leaves open. Neither is "more
evolved" — they sit at different points on a *permissive-exchange ↔
enforced-working-memory* axis, each optimal for its objective.

**Adopt (cheap, low-risk, format-layer wins):**

1. **Add optional `type:` to frontmatter** — a machine-readable concept-kind
   orthogonal to directory. Makes the corpus queryable by kind without encoding
   the directory taxonomy into every consumer. Highest value-to-cost.
2. **Add optional `resource:`/`source:`** — a URI/path binding a page to the
   code or asset it describes. Unlocks **automated drift detection** (gardener
   could diff target hash/mtime against `last_verified` instead of eyeballing).
3. **Add optional `tags:`** — cheap cross-cutting facets; synthesize a
   tag-browse view at read time.
4. **Generate a graph/backlinks view** (an OKF-style `viz.html`) from existing
   D5 link data — navigation aid for a growing corpus; "Cited by" backlinks are
   free from the reverse graph.
5. **Consider a versioned, externalizable mini-spec** of our format (an
   `okf_version`-like declaration) *if/when* harness knowledge needs to cross a
   repo boundary. Not needed while the corpus is single-repo.

**Explicitly do NOT adopt:**

- **OKF's permissive consumption stance.** For an actor's working memory,
  rejecting/flagging rot is the feature, not a bug. Our blocking gate is correct
  for our objective; importing "MUST NOT reject" would dismantle D3–D10.

These five adoptions are additive (new *optional* frontmatter keys + one
generated view) and do not touch the gate, so they cost almost nothing and lose
none of our lifecycle guarantees — they simply make our corpus as *queryable and
exchangeable* as OKF's while keeping it as *fresh and governed* as it already is.

## 6. Derived work

Adoptions 1–3 + 5 are specced as Phase 1:
[`../product-specs/2026-06-18-knowledge-format-evolution.md`](../product-specs/2026-06-18-knowledge-format-evolution.md)
— optional `type`/`tags`/`resource` keys (lint stays permissive), a flat-parser
list upgrade, and a versioned `docs/KNOWLEDGE_FORMAT.md` formalizing the
implicit-in-lint format. Adoption 4 (the graph/navigation view) is Phase 2: a
separate spec + ExecPlan that consumes the Phase-1 format. This doc remains the
observational comparison both phases cite.
