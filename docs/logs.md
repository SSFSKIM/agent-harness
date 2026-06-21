---
status: stable
last_verified: 2026-06-21
owner: harness
type: log
description: Append-only, milestone-grained project log — how the docs system and the project evolved over time, read on-demand (not auto-loaded into context).
---
# Logs — project & docs-system evolution

> **What this is.** A light, append-only narrative of how the project and its
> docs system changed, at **milestone grain** — an ExecPlan completion, an ADR, a
> docs-system restructure. Not a per-commit ledger (git is that) and **not
> auto-loaded** into session context (read it on demand). Newest first. Link the
> related spec / ADR / plan where it adds value; links are optional, not a tax.
>
> Durable *decisions* live in [`adr/`](adr/index.md); deferred work and open
> questions live in [`exec-plans/tech-debt-tracker.md`](exec-plans/tech-debt-tracker.md);
> mechanical change is in git history. This file is the human-readable "how did we
> get here" that those three don't tell on their own.

## 2026-06-21 — Gardening pass: promote the packaging proposed-rules + retire the memory-loop rule text

A doc-gardening pass closing the packaging initiative's accumulated doc-debt
(tech-debt-tracker rows for Slices 2–6) plus the residual retired-loop rule text.
**Promoted** (write-now proposals, each terse): DESIGN `## Scripts` gained the
script→script-import prohibition (a helper two scripts share goes to `harness_lib`,
never cross-imported) and the `base/` rendered-not-baked discipline; DESIGN `## Skills`
gained the seed-template prose-density + centralized-consumption-by-reference rule and
the "retire = grep the surviving bodies, not just the links" hygiene rule; ARCHITECTURE
invariant 5 (main) gained the tracked-config-belongs-in-`.claude/` boundary and the
`director/` invariant 5 gained signature-default aliasing via a module constant;
RELIABILITY R22 widened from `lint_docs` to every `check.py` gate lint step. The two
specs were amended (packaging R6.4 names the self-host *instance* `agent-harness.md`; the
2026-06-16 qa spec got a one-line supersession note). **Retired-loop text:** chose a
**parallel historical note** over a renumber — RELIABILITY's new status note frames
R1–R5/R7 as the retired feeder/imprint loop's lineage (R8–R22, ~15 tracker rows, and
tests cite the numbering, so renumbering would shatter every cross-ref); QUALITY_SCORE
dropped the `memory-store`/`feeder`/`imprint`/`dreaming` rows; ARCHITECTURE's stale
"Failure modes" headline was rewritten to the live R-rules. **Held by discipline** (left
tracked, not promoted): the feedback-twice scaffold-invariant rules (Slice 2) and the
recurrence-gated marketplace containment lint (Slice 5); the driver-layer named-constant
refactor (Slice 4) is code-debt, not doc-debt. Honest gap recorded in QUALITY_SCORE: the
`director/` application is not yet graded there.

## 2026-06-21 — Packaging COMPLETE: the packaged base artifact + legacy strip (Slice 6, capstone)

The capstone landed and **completes the six-slice packaging spec** (packaging
[Slice 6](product-specs/2026-06-21-harness-packaging-portable-template.md)). A new
checked-in **`base/`** tree is the tangible "open one folder and see the whole clean
system" artifact: the 24 seed templates rendered at their host destinations (the live
`{{COMPONENTS}}` machine index + the `adr` `{{CATEGORY}}` substituted; `{{PROJECT}}`/
`{{TODAY}}` preserved as fill-markers) + a `SETUP.md` that brings it to life and points
the centralized Director (reusing `.claude/DIRECTOR.md` §0). It is legacy-free (no
`docs/generated/`, symphony-original, EDUCATION, superpowers, okf-comparison,
symphony-parity-gap). A new blocking `plugin/scripts/lint_base.py` (the `base` gate
step) keeps the hand-synced base honest — it derives its expected set from the same
`harness_lib.SEEDS`/`render`/`components_table` that `scaffold.py` uses (so the base is
drift-proof by construction: a missing/extra/edited file or a stale component table
fails the gate), is R22-total, and no-ops on a ported host. The seed primitives were
promoted from `scaffold.py` to `harness_lib.py` (ARCHITECTURE invariant 8). `{{TODAY}}`
is preserved rather than baked, so the drift-check has no calendar dependence.

**With this, the harness is a portable, inspectable, drift-checked strict base — not
just one instance of itself.** The six slices: memory retirement → strict-base docs →
Director relocation → two-profile consolidation → plugin cleanup → this base artifact.
Remaining: doc-debt gardening (the tracked proposed rules + retired-loop text in
QUALITY_SCORE/RELIABILITY/SECURITY) and R5.3's public republish (a human go/no-go).

## 2026-06-21 — Packaging: plugin cleanup + manifest update (Slice 5)

The two plugin manifests were brought in line with reality (packaging
[Slice 5](product-specs/2026-06-21-harness-packaging-portable-template.md)).
`.claude-plugin/marketplace.json`'s skill list dropped the retired `dream` and
added the present `docs-nav` (now the 8 skills on disk, agreeing with the
gate-checked component inventory); `plugin/.claude-plugin/plugin.json` bumped
`0.1.0`→`0.2.0` to mark the packaging effort (removed components, relocated
Director, consolidated profiles). The generated inventory needed no regeneration —
it was already current from Slice 1's deletions under the gate. "docs-as-memory"
was kept deliberately: it names the durable-docs-as-knowledge model, not the retired
feeder/imprint/dream loop. Republish (a public release) is prepared but **not
performed** — that push is a separate human go/no-go. The reviews added one durable
discipline: a finding recorded only in a plan vanishes when the plan is archived, so
the "marketplace list isn't gate-checked" gap landed in the tech-debt tracker.

## 2026-06-21 — Packaging: two agent profiles consolidated (Slice 4)

The harness's two agents — the Director and the Codex worker — each got **one
settable source + one guide** (packaging
[Slice 4](product-specs/2026-06-21-harness-packaging-portable-template.md)). The
real change is a drift fix: `director/worker/app_server.py` now derives its
`thread_start`/`run_turn` fallback posture from `config.DEFAULTS["worker"]` (via
module constants) instead of a stale hardcoded `"untrusted"` (which predated the
2026-06-15 `on-request` decision) — a new `DefaultsDriftTest` pins the equality and
fails on the old literal. The redundant `qa` workspace skill was retired (the worker
self-QAs inline in `taxonomy._IMPL_TEMPLATE` and through the execplan completion gate
it runs). `.claude/DIRECTOR.md` gained **§14 "The two agent profiles"** — the Director's
two config halves (`.claude/` identity + `.harness.json` runtime + `.env` secrets) and
env contract, and the worker's single source + override surface + installed-skill bundle.
Reviews caught one real subtlety: the driver layer (`run.py`/`orchestrator.py`) keeps an
*intentional* conservative `"untrusted"` bare-call default (a fail-safe, pinned by a test)
— distinct from app_server's genuinely-stale copy — so only app_server was reconciled, and
§14's prose was corrected to tell the truth about the two tiers. No `agents/*` directory.

## 2026-06-21 — Packaging: Director relocation + launcher retirement (Slice 3)

The Director operating manual moved `docs/DIRECTOR.md` → `.claude/DIRECTOR.md`
(packaging
[Slice 3](product-specs/2026-06-21-harness-packaging-portable-template.md)) — it
is central-agent config (how the watched main session behaves), not a `docs/`
knowledge page, so it now sits beside `settings.json`. The
`.claude/skills/director/` launcher skill was retired: "becoming the Director" is
now "read `.claude/DIRECTOR.md`", whose §0/§5 already carried the launcher's
stand-up commands. Every live reference was repointed (2 D5 links, the AGENTS.md
map row + porting prose, `harness-init` §0, `PRINCIPLES.md`, and `director/*.py`
comment path strings); archived plans/specs keep their historical mentions (D5
ignores prose — not a history rewrite). No runtime behavior changed.

## 2026-06-21 — Packaging: strict-base docs + guidance enrichment (Slice 2)

The harness-init seed-template layer became the self-describing strict base
(packaging
[Slice 2](product-specs/2026-06-21-harness-packaging-portable-template.md)).
Added a `PRINCIPLES.md` template (the human's externalized decision-taste the
central Director reads at a fork), dedicated guided indexes for `references/`
(why external-API/`llms.txt` digests exist) and `product-specs/`, and lifecycle
`index.md` guides for `exec-plans/active|completed`. The `ARCHITECTURE.md`
template became a **redirect** to the `architecture-setup` skill rather than a
hand-fill skeleton — the same no-drift principle (point, don't copy) that kept
the plan skeleton single-sourced in `PLANS.md`. `scaffold.py` wires the five new
seeds and trims `TOP_INDEXES` to `("adr",)`. A fresh scaffold now gates GREEN
with every doc teaching how to write itself.

## 2026-06-21 — Packaging: memory subsystem retired (Slice 1)

The disabled feeder→imprint→dream memory loop was **retired** in favor of native
Claude Code memory (packaging
[Slice 1](product-specs/2026-06-21-harness-packaging-portable-template.md)). Deleted
the feeder/imprint scripts, the `dream` skill, the `dreamer` agent, and the
`MEMORY.md` bootloader; removed `docs/memory/`. Durable knowledge was re-homed:
ADRs surfaced to [`adr/`](adr/index.md), the `recursion-guard` knowledge page moved
to `design-docs/`, and the old `openq/`+`limitations/` folded into the
[tech-debt tracker](exec-plans/tech-debt-tracker.md). `progress/current.md` was
replaced by this `logs.md`. `tidy_stop` (the gate-on-stop safety net) was kept, with
its activation sentinel re-pointed off `MEMORY.md` to `.harness.json`.
