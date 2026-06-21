---
status: completed
last_verified: 2026-06-21
owner: harness
type: exec-plan
description: Relocate the Director operating manual docs/DIRECTOR.md → .claude/DIRECTOR.md (central-agent config, not project knowledge), retire the .claude/skills/director/ launcher (its launch steps already live in DIRECTOR.md §0/§5), and repoint every live reference so check.py D5 stays GREEN with no live docs/DIRECTOR.md path remaining.
base_commit: 70e36cf2f7a81879973c41656f6a8456ebe2ab19
review_level: standard
---
# Director relocation + launcher retirement (packaging/03)

## Goal

`docs/DIRECTOR.md` is gone; the Director operating manual lives at
`.claude/DIRECTOR.md` (central-agent config, alongside `settings.json`). The
`.claude/skills/director/` launcher is retired — "becoming the Director" is now
"read `.claude/DIRECTOR.md`", whose §0/§5 already carry the exact launch steps the
launcher pointed to. Every **live** reference is repointed: the two D5 markdown
links (AGENTS.md §0 pointer, CHARTER.md), the AGENTS.md map row + porting prose
(launcher clause dropped), the `harness-init` §0 pointer, the self-host
`PRINCIPLES.md` sibling mention, and the `director/*.py` comment path strings.
Definition of done: `python3 plugin/scripts/check.py` GREEN (D5 finds no broken
link); `grep -rn "docs/DIRECTOR.md"` returns only archived history + the
packaging spec's own description of this move (nothing live); the director test
suite stays GREEN (the code edits are comment-only — no behavior change).

## Context

- **Parent spec:** `docs/product-specs/2026-06-21-harness-packaging-portable-template.md`
  — Slice 3 is requirements **R3.1–R3.3** there. Builds from that design; does
  not re-derive it. The governing rationale (spec problem #3): `DIRECTOR.md` is
  central-agent *config* (how the watched main session behaves), not portable
  project knowledge — so it belongs next to `settings.json` in `.claude/`, not in
  the `docs/` knowledge tree, and it is seeded nowhere (the Director is
  centralized; the *method* travels via `harness-init`, the Director does not).
- **What "the Director" is:** the watched main session that runs the
  orchestrator (`director/`) against an external Linear board + git repo and
  answers worker turn-ends. Its manual is `DIRECTOR.md`. The `director` launcher
  skill was a one-shot "enter Director mode" pointer.
- **The launcher is pure redirection.** `.claude/skills/director/SKILL.md` says:
  read the manual, stand up the watched loop (the `python3 -m
  director.orchestrator --team <id>` background task + `python3 -m director.watch
  --kinds turnReview,…` Monitor), answer per §4. Verified: DIRECTOR.md **§0**
  (lines ~87–92) and **§5** (~225–238) already contain those exact commands, and
  **§4** the answer step. So retiring the launcher loses nothing — no folding
  needed; only the entry pointer changes.
- **Lint contract (verified at base_commit):**
  - `DIRECTOR.md` is in neither `MACHINE_DOCS` nor `MANAGED_DOCS` → D10 does not
    require it; moving it out of `docs/` trips no existence check. It is not in an
    `INDEXED_DIR`, so no `index.md` registration depends on it.
  - D5 (broken-link) only flags **markdown links** `](…path)`. A grep of the
    whole tree found exactly **two** links resolving to DIRECTOR.md: `AGENTS.md:106`
    and `docs/CHARTER.md:48`. Every other hit (≈40 in `completed/*`, ≈14 in
    `product-specs/*`, the ADRs, the code comments) is a bare/backtick mention —
    historical prose D5 ignores and the spec says not to rewrite.
  - `lint_structure.check_skills` scans `plugin/skills/`, **not** `.claude/skills/`
    — deleting the launcher dir trips no S-rule.
  - `.claude/` is tracked in the self-host repo (`settings.json`,
    `skills/director/SKILL.md` are committed) and only `.claude/harness/` is
    gitignored — so `.claude/DIRECTOR.md` will be a tracked file.
- **AGENTS.md is D5-linted** (the root operating manual + map, per DESIGN.md
  "host vs machine enforcement"). A link from AGENTS.md (repo root) to
  `.claude/DIRECTOR.md` resolves on the filesystem → D5 GREEN.

## Approach (self-generated alternatives)

For the two D5 links, the choice is "repoint vs de-link":
- **A — Repoint both to the new path.** AGENTS.md links to `.claude/DIRECTOR.md`
  (resolves from root); CHARTER.md links via a `../.claude/DIRECTOR.md` cross-tree
  path out of `docs/`. Tradeoff: keeps both as clickable links, but CHARTER
  (project intent) hard-linking into central-agent config via `../.claude/` is a
  layering smell — the spec's whole point is that DIRECTOR is *not* a docs-graph
  node anymore.
- **B — Repoint AGENTS.md (it is the operating front door that legitimately
  points at agent config), de-link CHARTER to a bare backtick mention.** CHARTER
  keeps the reference as prose (`the Director manual (\`.claude/DIRECTOR.md\`)`)
  with no graph edge. Tradeoff: CHARTER loses a clickable link, but DIRECTOR
  correctly drops out of the docs graph (it is no longer a docs/ page), and no
  awkward `../.claude/` link crosses the docs↔config boundary.
- **Chosen: B.** Relocating DIRECTOR *out of the knowledge tree* is the point of
  the slice; a `docs/` page should not graph-link into agent config. AGENTS.md is
  the one place a pointer to agent config belongs (it already documents how to run
  the Director). (Mirrored into the Decision log.)

For the AGENTS.md **map row** (which lists `docs/` files): the row's subject left
`docs/`. Chosen: update it in place to `\`.claude/DIRECTOR.md\`` and label it
"central-agent config (not a docs/ page)" + drop the retired-launcher clause —
keeping the manual discoverable from the front door without pretending it is a
docs/ knowledge page.

## Assumptions & open questions (self-interrogation)

- **Assumption:** the director test suite covers `director/*.py` such that a
  comment-only edit leaves it GREEN (no string is load-bearing in a test
  assertion). *If wrong* (a test asserts a `docs/DIRECTOR.md` substring), the gate
  surfaces it — fix the test to the new path. Mitigation: grep the tests for
  `DIRECTOR.md` before editing.
- **Assumption:** no auto-loader depends on the `director` skill's existence
  (settings.json doesn't reference it; confirmed). Becoming the Director is a
  documented manual step (AGENTS.md §0 pointer → `.claude/DIRECTOR.md`), which is
  the intended simplification (skill-invoke → read-file), not a regression.
- **Open → resolved autonomously:** CHARTER de-linked to a bare mention (B), not a
  `../.claude/` link. Recorded.
- **Open → resolved autonomously:** bare `DIRECTOR.md §N` mentions that carry no
  path (e.g. `merger.py`, `orchestrator.py:1201`, the ADRs) are left as-is — they
  name the doc, not its location, and stay correct. Only **path-bearing**
  `docs/DIRECTOR.md` strings + the two links change.
- **Scope fence:** archived `completed/*` and `product-specs/*` bare mentions are
  NOT rewritten (history). The parent packaging spec's own `docs/DIRECTOR.md`
  mentions (describing this very move) are left intact. No `director/` runtime
  behavior changes — comment/docstring edits only.

## Milestones

- **M1 — Move + retire (R3.1, R3.2).** `git mv docs/DIRECTOR.md
  .claude/DIRECTOR.md`; `git rm -r .claude/skills/director/`. In the moved
  `.claude/DIRECTOR.md`, update its own header line that names "the `director`
  launcher skill is the marker — you don't become the Director by accident" → the
  marker is now reading this file (the launcher is retired). At the end:
  `.claude/DIRECTOR.md` exists, `docs/DIRECTOR.md` and `.claude/skills/director/`
  are gone. Run `ls .claude/DIRECTOR.md && ls docs/DIRECTOR.md 2>&1`; expect the
  first to exist, the second to be absent.

- **M2 — Repoint all live references (R3.3).** (a) The two D5 links: AGENTS.md:106
  → `.claude/DIRECTOR.md`; CHARTER.md:48 → bare backtick mention (Approach B). (b)
  AGENTS.md map row (:54) → `.claude/DIRECTOR.md`, central-agent-config label,
  drop the launcher clause; AGENTS.md porting prose (:105–106) → drop the
  "`director` launcher skill enters the watched loop" clause, repoint the §0 link.
  (c) `harness-init` SKILL.md:13 `docs/DIRECTOR.md §0` → `.claude/DIRECTOR.md §0`.
  (d) self-host `PRINCIPLES.md:22` `DIRECTOR.md §2` → `.claude/DIRECTOR.md §2`. At
  the end: AGENTS.md's link resolves to `.claude/DIRECTOR.md` and CHARTER carries
  no markdown link to a `docs/`-resolved DIRECTOR path (verify by reading both).

- **M3 — director/*.py comment path strings (R3.3) + verify.** Update the
  path-bearing comments: `director/decider.py:88`, `director/director_min.py`
  (×3), `director/status.py:333`, `director/orchestrator.py:1238` — `docs/DIRECTOR.md`
  → `.claude/DIRECTOR.md` (leave the bare `DIRECTOR.md §N` mentions in
  `merger.py`/`orchestrator.py:1201` unchanged — no path). Then the behavioral +
  mechanical verification: `python3 plugin/scripts/check.py` → **GREEN**;
  `grep -rn "docs/DIRECTOR.md" . --include=*.py --include=*.md | grep -v
  completed/ | grep -v 2026-06-21-harness-packaging` → empty (no live reference);
  the director test suite passes (proves the comment edits broke nothing). Record
  behavioral check **N/A + why** (pure config/docs relocation + comment-only code
  edits; no runtime surface changed — verification is D5 + grep + the existing
  director tests staying GREEN).

## Progress log
- [x] (2026-06-21) Plan created; spec R3.1–R3.3 read; full reference map taken
  (80+ hits → 2 real D5 links); launcher confirmed pure-redirection (§0/§5 carry
  its commands); lint contract verified (DIRECTOR not a MACHINE/MANAGED doc,
  lint_structure scans only plugin/skills). base_commit 70e36cf.

## Surprises & discoveries

## Decision log
- 2026-06-21: **CHARTER de-linked to a bare mention; only AGENTS.md keeps a link**
  (Approach B) — relocating DIRECTOR out of the knowledge tree is the point; a
  `docs/` page should not graph-link into agent config, and AGENTS.md is the
  legitimate place to point at it.
- 2026-06-21: **Only path-bearing `docs/DIRECTOR.md` strings + the 2 links
  change**; bare `DIRECTOR.md §N` mentions (name, not location) and all archived
  history stay — fix what D5 enforces, don't rewrite history.

## Feedback (from completion gate)
- **review-spec-compliance: SATISFIED (round 2).** Round 1 NOT-SATISFIED on one
  P1 (below). Round 2 confirmed the fix + R3.1–R3.3 intact, no archived history
  rewritten. Non-blocking note: this plan's M3 DoD grep should also exclude
  `product-specs/` to match its own scope fence → tracker.
- **review-arch: SATISFIED (round 2).** Same P1 in round 1; round 2 confirmed the
  docs↔config boundary is improved, the launcher retirement loses nothing, the
  CHARTER de-link (Approach B) is correct. P2 (non-blocking): the AGENTS.md:54 map
  row lists a `.claude/` path in an otherwise docs/-oriented table — defensible
  with the explicit "central-agent config" label; left as-is. Proposed rule → tracker.
- **review-reliability: SATISFIED (round 1).** Independently verified the
  `director/*.py` edits are comment/docstring-only, **nothing opens/resolves the
  DIRECTOR.md path at runtime** (so the move is a true runtime no-op), the launcher
  deletion breaks no wiring (lint_structure scans only `plugin/skills/`; settings/
  hooks reference-free), 524 director tests pass.
- **review-code-quality: SATISFIED.** No P1. P2-1 (fixed inline): §0 "Launch"
  redundantly restated "there is no launcher skill" that the header already
  settled — trimmed to lead with the launch commands. P2-2 (map-row placement) —
  same as arch, left as-is. No new rule (terseness is already core-belief 3).
- **P1 (round 1, spec-compliance + arch, FIXED — commit e45cab9):** the relocated
  manual's own §0 "Launch" step still told the reader to invoke the `director`
  launcher skill deleted in this same slice, contradicting the header. I fixed the
  header self-reference but missed the §0 one inside the same file — the exact
  "grep the moved file body, not just inbound links" gap (now a tracker rule).

## Outcomes & retrospective

**Delivered.** `docs/DIRECTOR.md` now lives at `.claude/DIRECTOR.md` as
central-agent config (alongside `settings.json`), out of the `docs/` knowledge
graph. The `.claude/skills/director/` launcher is retired — "becoming the
Director" is "read `.claude/DIRECTOR.md`", whose §0/§5 already carried the exact
stand-up commands the launcher pointed to. Every live reference is repointed: the
two D5 markdown links (AGENTS.md §0 pointer → `.claude/`; CHARTER de-linked to a
bare mention), the AGENTS.md map row + porting prose (launcher clause dropped),
the `harness-init` §0 pointer, the self-host `PRINCIPLES.md` sibling mention, and
the five `director/*.py` comment path strings. `check.py` GREEN; no live
`docs/DIRECTOR.md` reference; 524 director tests pass (comment-only code edits).

**What worked.** Separating D5-checked markdown links from bare/backtick prose
collapsed an 80-hit grep into a 2-link surgery and confirmed the spec's
"bulk-update archived links" was a no-op (history left intact). The reliability
persona's runtime-path-consumer check turned "the code edits are comment-only"
from a claim into verified fact (nothing opens the path → the move is a runtime
no-op).

**What I missed (and the lesson).** The relocation had **two** launcher
self-references inside the moved manual; I fixed the header, missed the §0 Launch
step. Both spec-compliance and arch caught it. D5 couldn't — it's prose, not a
link. The discipline (now tracked): when you retire an artifact, grep the
*surviving file bodies* for its name, not only the inbound links. (I also re-hit
the Slice-2 `git add` stale-pathspec trap when committing the rename — caught and
fixed immediately; the memory note stands.)

**Carried forward (tracker, P2):** the docs↔`.claude/` boundary rule; the
"retire = grep the moved body" hygiene rule; the M3-DoD-grep self-consistency nit.

**Next:** Slice 4 (two agent profiles consolidated) — the packaging spec's next
phase.
