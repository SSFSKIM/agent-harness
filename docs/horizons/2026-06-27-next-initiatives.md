---
status: stable
last_verified: 2026-06-27
owner: harness
type: horizon
description: First scout horizon — a divergent panel (moonshot / competitor-killer / first-principles-reframe / narrowest-wedge) judged against the Mission + Core Axioms. Tier 1 = the standalone PR-verdict wedge; Tier 2 = three foundational challenges (Judgment Ledger, open Worker Protocol, intent-as-source reconciliation). All four stances converged on the governance/verification layer as the harness's unique value.
---
# Horizon — next initiatives (2026-06-27)

The first `scout` run. Four stance-forced generators (with outward web research)
proposed one vision each; an independent `vision-judge` scored each against the
Mission (the bar) and the Core Axioms (the screen) and routed it. This doc is
**decision-support — it proposes, it does not enact.** A chosen Tier-1 pick
becomes a product-spec via `product-design`; a Tier-2 challenge is a question for
the human, not an action.

## The signal worth seeing first

All four divergent stances — independently, blind to each other — landed on the
**same layer**: governance / verification / trust, *not* code generation.

- *Moonshot* → be the trust plane any agent fleet is governed by.
- *Competitor-killer* → own the governance + orchestration + memory substrate;
  rent the engine.
- *First-principles* → the Director becomes a conformance reconciler driving code
  toward declared intent.
- *Narrowest-wedge* → ship the completion gate as a portable PR verdict.

When four stances pushed to four different edges and converged on one place, that
convergence is the finding: **the harness's scarce, non-commoditizing asset is
warranted trust in autonomous output — codegen is the commodity.** The research
backs it (the field's bottleneck has moved from writing to verification; SWE-bench
is saturating while review effort climbs). Every Tier-1 *and* Tier-2 item below is
a different bet on owning that layer. The Tier-1 wedge is the cheapest way in.

## Tier 1 — actionable initiatives (ranked)

### 1. Standalone repo-grounded PR verdict *(narrowest-wedge)*

**The bet.** Unbundle the existing completion gate into a portable, PR-triggered
**verdict** — the deterministic lint floor + the doc-grounded review personas,
each finding citation-chained to the repo's own written law — that drops in front
of *any* coding agent's PR (Cursor, Copilot, Devin, Claude Code) and returns
"land it" or "exactly these N points need a human." Teams drowning in agent PRs
govern by **exception** instead of reading diffs.

**Why it wins.** It *is* the Mission expressed as a function ("surface only genuine
forks of human judgment"), it is the most portable and least-Director-coupled
organ the project owns, and the judge verified against the code that the gate is
*already* a `git diff → per-persona Verdict` function with personas already
portable — so this is aggregation + a thin runner, not invention. Against generic
AI reviewers (CodeRabbit/Greptile) the differentiation is structural: *your*
written law (not best-practice noise), citation-gated + lint-floored (auditable,
not vibes), and one trust verdict that *removes* review load instead of adding to
it.

**Judge score sheet.** Mission **5** · Axiom-fit **5** (violates none; reinforces
2 + 3, leaves 1 untouched) · Competitive edge **3** (crowded lane; a binary
verdict raises the trust-to-adopt bar — positioning is the whole game) ·
Leverage **5** (inverts adoption order: the lightest organ banks trust, then each
new want pulls a heavier organ that already exists — harness-init → Knowledge
format → methodology/workers → Director *last*) · Feasibility **4**.

**First wedge.** Ship the deterministic lint floor + the four *doc-grounded*
personas (arch / reliability / security / code-quality — drop spec-compliance,
which presumes a plan) as a PR-triggered runner emitting one aggregated verdict,
and **dogfood it on this repo's own incoming PRs first**, where mature written law
already exists. That sequences the one real danger (a false "merge-clean" — the
project's own memory records personas can confabulate a confident pass) onto home
turf *before* the harder lawless-foreign-PR case.

**The one thing to watch.** The moat collapses to "another AI reviewer" the moment
it runs on a repo *without* written law — so the **bootstrap-law path**
(harness-init / architecture-setup) is not optional leverage to pull later, it
*is* the moat. Treat the lawless-foreign-PR demo as the real validation milestone.

## Tier 2 — foundational challenges (escalated, not enacted)

Each was compelling on Mission-fit, edge, or leverage, but its core **strains the
Mission's scope or a named Core Axiom** — so the judge routed it here. These are
questions for the human: *should the constraint move?* Each carries a Tier-1-able
**carve-out wedge** that tests the thesis cheaply *without* committing to the
challenge.

### A. The Judgment Ledger / governance substrate *(moonshot)*

**Idea.** Become the runtime-agnostic trust plane any fleet is governed *by*,
accumulating a versioned, replayable Judgment Ledger that compounds into a
per-repo taste model and self-improves from landed-vs-reverted outcomes.

**What it strains.** The Mission clause **"*surfacing* only genuine forks of human
judgment."** A loop that optimizes *what to escalate* against *did-it-land* is, by
construction, a mechanism that decides what *not* to surface — the opposite of
surfacing. It also expands identity from "a harness any repo adopts" to "the trust
plane the industry is governed by." Score: Mission 4 · Axiom 4 · Edge 3 ·
Leverage 4 · Feasibility 2 (platform-scale ingestion + ML-on-weak-signal — the
grand re-architecture the project's taste is wary of).

**The human re-decision.** May a learned outcome-model ever *suppress* a fork, or
must every fork always reach the human? That is itself a taste-fork only the human
can resolve — and it decides whether the Mission stays "surface, don't decide."

**Carve-out wedge (Tier-1-able).** Instrument the harness's *own* governance
decisions as a Judgment Ledger — which forks the Director surfaced, what the human
decided, did-it-land-and-survive. Pure dogfood, zero re-architecture, no
auto-decide loop. It tests whether the signal is even rich enough to compound
before betting the project on platform scope.

### B. Open Worker Protocol — "own the harness, rent the engine" *(competitor-killer)*

**Idea.** Harden the worker-adapter into a published, versioned, conformance-tested
**Worker Protocol** so Devin / Factory / Codex / OpenHands become commoditized,
hot-swappable workers beneath agent-harness; the host repo owns governance +
orchestration + memory.

**What it strains.** No axiom breaks (it is Axiom 3 taken to its conclusion) — but
the defining commitment, an **ecosystem-steward posture** (spec-grade public
contract, conformance suites, outsider docs, adapter upkeep for engines it doesn't
own), directly contradicts the project's stated taste (lean, dogfood-first, wary
of grand re-architectures) and, by the vision's own admission, forecloses the more
lucrative closed-product path. Score: Mission 3 · Axiom 4 · Edge 2
(stack-inversion needs adoption leverage a lean repo lacks, or rivals
cooperating against their own interest) · Leverage 4 · Feasibility 2.

**The human re-decision.** Re-scoping identity to "THE substrate the industry's
engines plug beneath," foreclosing a margin path, and spending scarce lean
capacity on a standards/GTM war — a fork of human judgment, not an agent call.

**Carve-out wedge (Tier-1-able).** Promote the *existing* worker-adapter into a
documented, versioned **Worker Protocol spec + conformance test, committed in-repo**,
proven live across the Codex + Claude workers it already runs. Clears the Mission,
violates no axiom, ~80%-built, and is the cheapest probe of whether the grand
thesis has any pull — without committing to standards-body posture.

### C. Reconciliation control-plane — intent as source *(first-principles-reframe)*

**Idea.** Stop maintaining a codebase; maintain a declarative **intent model** and
continuously *reconcile* the repo toward it (a Kubernetes-style controller; code
becomes cattle, regenerated, not a patched pet). The highest Mission-fit of the
four (5/5) — it gives intent the first-class home the Mission implies but the
harness today lacks.

**What it strains.** **Axiom 2** (*bent*, not cleanly broken — the judge's sharper
read: Axiom 2 is "the repo is the durable shared ground-truth," which an in-repo
intent model + a materialized projection both satisfy; what changes is *which
artifact is authoritative-for-regeneration*). **Axiom 3** (*genuinely strained* —
legacy hosts have no intent model and need a lossy reverse-lift, so "any repo
adopts it" silently becomes "intent-native or lifted repos adopt it"). Plus an
unsolved research bet: spec→code non-determinism. Score: Mission 5 · Axiom 2 ·
Edge 3 · Leverage 4 · Feasibility 2.

**The human re-decision.** Is **"general by identity"** inviolable, or is the
harness willing to become *intent-native-first* and re-earn portability later via
reverse-lift? That identity trade is the fork — and it is gated behind a research
risk, so it cannot be an agent decision.

**Carve-out wedge (Tier-1-able).** Author one self-hosted subsystem's intent model,
let the Director regenerate *that slice* from intent, and prove conformance by
test. If it can't converge on real code + tests, the whole challenge is a DROP —
so this wedge is the cheap go/no-go probe.

## Dropped

None. (Three of four bold visions routed to Tier 2 rather than dropping — the
expected shape: the stances pushed to the edges on purpose, and the axiom-screen
*routed* them to the human instead of killing them. The keystone, working.)

## Reading this horizon

If you want one thing to *do*: **Tier-1 #1** (the PR-verdict wedge), dogfooded on
this repo first. If you want one thing to *decide*: whichever Tier-2 constraint you
feel — the Mission's "surface, don't decide" (A), "general by identity" (C), or
the lean-vs-steward identity (B). Notably, **every Tier-2 carve-out wedge is itself
a cheap, axiom-clean, Tier-1-able probe** — so you can fund the *learning* behind a
foundational challenge without yet committing to the challenge. The convergence
signal suggests the through-line for the next arc is the **governance/verification
layer**; the PR verdict is its smallest shippable expression.
