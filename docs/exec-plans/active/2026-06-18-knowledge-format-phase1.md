---
status: active
last_verified: 2026-06-18
owner: harness
base_commit: 0ff9be38d56d367b44d852e957956677c1ff91c0
review_level: targeted
---
# Knowledge Format evolution — Phase 1 build

## Goal

Author conformant knowledge pages using the five new optional frontmatter keys,
and have the harness read them — observably. Definition of done:

1. `docs/KNOWLEDGE_FORMAT.md` exists, declares **Knowledge Format v1.0**, and a
   reader can author a conformant page (required + the five optional keys, the
   `type` vocabulary, the `tags` form, conformance↔D-rule map) from it alone.
2. `python3 -c "import sys; sys.path.insert(0,'plugin/scripts'); import
   harness_lib as h; print(h.read_frontmatter('docs/memory/knowledge/recursion-guard.md')['tags'])"`
   prints a Python **list**, not a string.
3. Every memory concept page under `docs/memory/{knowledge,adr,limitations,openq}/`
   (the 7 non-index pages) carries `type`, `tags`, and a one-sentence
   `description`; pages bound to one code asset carry `resource`.
4. `python3 plugin/scripts/check.py` is GREEN throughout, including new parser
   unit tests, and removing any new key from any page keeps it GREEN (the keys
   are permissive — no D-rule names them).

## Context

- **Spec (owns the design — build from it, do not re-derive):**
  [`docs/product-specs/2026-06-18-knowledge-format-evolution.md`](../../product-specs/2026-06-18-knowledge-format-evolution.md).
  Read its Design (D-1..D-6), Non-goals (NG-1..NG-7), and Acceptance criteria.
- **Rationale:** [`docs/design-docs/okf-comparison.md`](../../design-docs/okf-comparison.md)
  — why these keys (OKF parity) and why we keep our permissive-on-optional /
  strict-on-required asymmetry.
- **The parser being changed:** `plugin/scripts/harness_lib.py` →
  `read_frontmatter` (flat `key: value`; today returns `dict[str,str]`). Called by
  `lint_docs.py`, the feeder, and the imprint scripts — all read only the scalar
  required keys.
- **The gate:** `python3 plugin/scripts/check.py` (lints + `unittest discover -s
  tests`). Must be GREEN before every commit (`harness-lint` interprets failures).
- **Backfill targets (7):** `docs/memory/adr/000{1,2,3}-*.md`,
  `docs/memory/knowledge/recursion-guard.md`,
  `docs/memory/limitations/progress-staleness.md`,
  `docs/memory/openq/{memory-loop-redesign,tracker-fixed-traceability}.md`.
- **Worktree note:** `docs/symphony-original/` is a gitignored local-only
  reference replicated into this worktree so D5 passes; it is never committed.

## Approach (self-generated alternatives)

- **A — Parser-first (bottom-up):** land `read_frontmatter` list support + tests
  first, then `KNOWLEDGE_FORMAT.md`, then authoring guidance, then the backfill.
  The backfill (which introduces the first real list-valued `tags`) becomes a
  live end-to-end exercise of the parser through the gate. Tradeoff: the durable
  contract doc lands after the code it specifies.
- **B — Doc-first (top-down):** write `KNOWLEDGE_FORMAT.md` (the contract) first,
  implement the parser to match, backfill last. Tradeoff: the only behavior that
  can *regress existing consumers* (the shared parser) lands later, after time
  spent on docs — de-risking is deferred.
- **Chosen: A.** The parser is the sole change that can break existing behavior
  (gate, feeder, imprint all import `read_frontmatter`); landing and proving it
  first — with a regression-net test asserting scalars are byte-unchanged —
  de-risks everything downstream, and the backfill doubles as the integration
  test. The contract doc (M2) still pins the design; it documents a parser that
  already provably works.

## Assumptions & open questions (self-interrogation)

- **Assumption: no existing page uses a list-valued frontmatter key.** Every
  current key is a scalar (`status`/`last_verified`/`owner`/etc.). If wrong, a
  pre-existing `[...]`-shaped scalar would newly parse as a list. Mitigation: the
  flow trigger requires a value that *both* starts `[` and ends `]`; M1 greps the
  corpus to confirm none exist before trusting the assumption.
- **Assumption: `lint_docs.py` needs no change.** `D3` checks only `FM_REQUIRED`;
  extra keys are already tolerated, and no lint reads `tags`/list values. If the
  gate unexpectedly flags a new key, that is a Surprise → handle inline (the spec
  keeps lints permissive, so the fix is to exempt, not to validate).
- **Assumption: colons inside `description` are safe.** `read_frontmatter` uses
  `line.partition(":")` (splits on the *first* colon only), so
  `description: Triage: do X` yields val `"Triage: do X"`. Verified by reading the
  function; M1 adds a test pinning it.
- **Open: quoting/whitespace in `tags` items** → resolved autonomously: each flow
  item is whitespace-stripped and has surrounding `'`/`"` stripped; `[]` → `[]`.
- **Open: block-form `tags`** → resolved: parser *tolerates* it on read (OKF
  interop) but our pages author the canonical flow form; M1 tests both.
- **Open: do index.md pages get `type`?** → resolved: out of scope for the
  backfill (spec R6 says concept pages only; index pages MAY, we skip them to keep
  the diff minimal).
- Escalate nothing here — these are mechanical; the only product forks
  (phasing, key set) are already settled in the spec.

## Milestones

- **M1 — Parser list support + regression-net tests.** Upgrade
  `plugin/scripts/harness_lib.read_frontmatter` so a flow-form value `key: [a, b]`
  returns `["a","b"]` and a tolerated block form (`key:` then `- a` lines) returns
  the same, while every scalar line returns its identical prior string. First grep
  the corpus to confirm no page already uses a list value. Extend
  `tests/test_harness_lib.py` with cases: flow→list, block→list, `[]`→[], quoted/
  spaced items, scalar-unchanged, colon-in-value preserved. At the end the shared
  parser reads lists with zero scalar regression. Run
  `python3 -m unittest -v tests.test_harness_lib` (new cases pass) **and**
  `python3 plugin/scripts/check.py` (full 414+ suite GREEN). Acceptance: a new
  test that fails against the pre-M1 parser passes after M1.
- **M2 — The versioned format spec doc.** Create `docs/KNOWLEDGE_FORMAT.md` per
  spec D-4: frontmatter `status: stable / last_verified / owner`; declares KF
  v1.0; documents required + the five optional keys with the `type` vocabulary
  (D-1 table) and the `tags` canonical flow form; reserved filenames; link
  semantics (D5 rejects broken links — the deliberate divergence from OKF);
  conformance mapped to D-rule IDs (D3/D4/D5/D6/D8); a short OKF pointer. Add a row
  to the `AGENTS.md` Map table. At the end the format is an explicit, discoverable
  contract. Run `python3 plugin/scripts/check.py` — GREEN (the new doc satisfies
  D3 frontmatter, UPPER-case top-level naming, and the AGENTS.md link is valid).
  Acceptance: the doc declares v1.0, lists all five keys + vocab + tags form +
  conformance map, and is linked from `AGENTS.md`.
- **M3 — Authoring guidance.** Update `plugin/skills/docs-tree/SKILL.md` (the
  frontmatter-procedure step) and `docs/memory/MEMORY.md` (the write-rules bullet)
  to name the optional keys and point to `docs/KNOWLEDGE_FORMAT.md` as the
  authority. At the end an author following the routine path learns the keys exist.
  Run `python3 plugin/scripts/check.py` — GREEN. Acceptance: both files reference
  the optional keys and link the format spec.
- **M4 — Representative backfill + permissive proof.** Add `type` (per the D-1
  vocabulary for each directory), `tags` (2–5 flow-form facets), and a
  one-sentence `description` to all 7 memory concept pages; add `resource` to the
  pages bound to one code asset (e.g. `recursion-guard.md` →
  `plugin/scripts/harness_lib.py`); bump each page's `last_verified` to 2026-06-18.
  At the end the corpus exercises the full format through the real gate (first
  live list-valued `tags`). Run `python3 plugin/scripts/check.py` — GREEN; then
  demonstrate permissiveness by deleting one new key from one page, re-running the
  gate (still GREEN), and restoring it. Acceptance: all 7 pages carry
  type+tags+description (resource where applicable); gate GREEN with and without
  any single new key.

## Progress log
- [ ] (2026-06-18) Plan created; base_commit recorded. Starting M1.

## Surprises & discoveries

## Decision log
- 2026-06-18: Chose parser-first execution (Approach A) — the shared-parser change
  is the only regression risk; prove it first, let the backfill integration-test it.
- 2026-06-18: `tags` flow item normalization = strip whitespace + surrounding
  quotes; block form tolerated on read, flow form authored.
- 2026-06-18: index.md pages excluded from the backfill (spec R6 = concept pages).

## Feedback (from completion gate)

## Outcomes & retrospective
