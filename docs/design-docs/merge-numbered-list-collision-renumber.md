---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [git, merge, docs, operating-gotcha]
description: Merging a behind feature branch here collides on append-only numbered-list docs (RELIABILITY R-rules, SECURITY T-rules, ARCHITECTURE invariants, tech-debt rows) — both sides grab the same next number; resolve by union + renumber the newer side + grep the whole tree for stale cross-refs.
---
# Merge: numbered-list collisions need renumber

A field note promoted from session memory. This repo runs many parallel feature
branches and keeps several **append-only numbered-list docs**:
[`RELIABILITY.md`](../RELIABILITY.md) (R-rules), [`SECURITY.md`](../SECURITY.md)
(T-rules), [`ARCHITECTURE.md`](../../ARCHITECTURE.md) (`director/` invariants),
and the [`tech-debt-tracker.md`](../exec-plans/tech-debt-tracker.md) table. When
two branches both append, they grab the **same next number** independently → a
merge **numbering collision**, not a clean append. A naive "accept both" leaves
two `R15`s (corrupt); "accept one side" silently drops the other's rule(s).

## How to resolve

1. **See the surface first:** `git merge-tree --write-tree --name-only <base>
   <branch>` — in this repo it is almost always a few append-heavy docs.
2. **Per numbered-list conflict:** keep both sides' entries; **renumber the
   collision on the side with fewer / less-referenced cites** (e.g. master owns
   R15–R20 widely → the branch's lone R15 → R21).
3. **Watch the tracker for stale-`open` duplicate rows** — master may have flipped
   a row to `fixed` while the earlier-forked branch still shows `open`; keep
   master's `fixed`, drop the branch dupe.
4. **After renumbering, `grep -rn "R<N>" docs/` across the WHOLE merged tree**
   (including `completed/` exec-plans) and fix every stale cross-ref — the
   line-level merge cannot see these.
5. **Gate the merged tree** (`python3 plugin/scripts/check.py`) *before*
   committing — a healthy sign is the test count = the union of both suites. Land
   big branches with a `--no-ff` merge commit, `--no-verify` after the manual
   gate (see
   [parallel sessions share one master index](parallel-sessions-share-master-index.md)).

## "No conflict" ≠ "integrated"

A clean auto-merge can still be semantically broken. The checks that matter, by
leverage: **(1) competing edits** — a file *both* sides edited
(`git rev-list --count <mergebase>..<side> -- <file>`) is the real risk;
**(2) parser type-widening blast radius** — when a shared parser widens a value's
type, the break surface is its caller set (`grep -rln <fn> --include=*.py`);
**(3) gate fails-closed, not crashes** — every gate consumer of the widened value
must degrade, not throw; **(4) new tests actually run** — invoke the new module by
name, don't trust the aggregate count; **(5) operating-manual prose drift** —
gates don't lint version strings.

**Gotcha:** the `implements` edge (hence phase inheritance + roadmap nesting) only
fires when a plan links its spec as a real **markdown link** — `nav.py`'s link
regex only sees markdown links, so a plan that names its spec as a **bare backtick
path** stays `(unphased)`. A docs-convention is **not**
propagated to work the other side authored in parallel: required lints
auto-enforce corpus-wide on merge, but the permissive navigation axis lags and
needs a manual one-time backfill (a doc-gardener job, per
[KNOWLEDGE_FORMAT.md](../KNOWLEDGE_FORMAT.md)). Detect with `nav.py catalog --json`
(pages with no `type`) and `nav.py map` (`⚠ not anchored` / `(unphased)`).
