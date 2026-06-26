---
status: stable
last_verified: 2026-06-27
owner: harness
phase: knowledge-format/07-charter-reframe
type: product-spec
tags: [methodology, knowledge-format, charter, intent]
description: Reframe CHARTER.md from 5 sections to 4 — Mission absorbs north-star altitude + the workstream filter + a folded observable clause; Locked assumptions → Core Axioms (generative, reversal-tested); delete the static "What done looks like"; propagate to the bootstrap template and base seed.
---
# Charter restructure — fewer sections, generative axioms, a Mission that steers

Supersedes the *structure* (not the intent layer's existence) established in
[Charter & derived progress map](2026-06-19-charter-and-progress-map.md). That
spec built the charter as the Orient anchor; this one reshapes its sections after
the intent layer has been lived in.

## Problem

`CHARTER.md` today carries five sections — **Mission**, **What "done" looks
like**, **Design philosophy (기획의도)**, **Locked assumptions**, **Initiatives**.
Three observable problems:

1. **A static doneness snapshot that rots and double-states the Mission.** "What
   done looks like" restates the Mission in observable terms, then freezes it.
   The project already has a *live* doneness view (`nav.py roadmap`, derived from
   frontmatter) and now gains a *directional* end (an ambitious Mission). A
   hand-maintained snapshot sits awkwardly between the two and is the kind of
   hand-kept artifact the project's own philosophy ("structure is a projection,
   not hand-maintained") tells us to delete.
2. **"Locked assumptions" is framed defensively, not generatively.** "Taken as
   given and not re-litigated" invites *not touching*; for a harness whose whole
   game is self-correction and proactively proposing the right workstreams, the
   load-bearing claims should invite *deriving from* — they are the center the
   project is built on, not a list we refuse to argue about. The current
   axiom-vs-philosophy test is a behavioral symptom ("if you re-argue it, it was
   philosophy"), not a definition, so the bar for what gets locked is fuzzy.
3. **The Mission under-reaches.** It reads as a bounded "it's a portable harness
   that…" — identity without ambition. Nothing in the charter is written at the
   altitude that lets an agent ask *"is this proposed workstream the right
   one?"* The motivating idea (a north star — the wide-reaching goal that selects
   workstreams) has no home. (We deliberately do **not** add a separate North
   Star section: a north star sits *above* projects, grounding several missions
   at the team/business level; a single repo's charter has one project, so its
   Mission and its north star coincide. A separate section would import a
   team-level construct into a project-level doc and re-introduce problem 1's
   double-statement. The Mission must instead be *written at* north-star
   altitude.)

## Requirements

- **R1.** `CHARTER.md` has exactly four sections, in order: **Mission**, **Core
  Axioms**, **Design philosophy (기획의도)**, **Initiatives**. (Verify: heading
  list.)
- **R2.** **Mission** is written at the most ambitious altitude (a wide-reaching
  end-state, allowed to be bigger than the harness artifact), contains exactly
  one observable *"you can tell it's working when…"* clause (the folded remnant
  of deleted doneness), and contains an explicit sentence naming the Mission as
  the **filter for which workstreams belong**. (Verify: a reader can point to all
  three — ambition, observable clause, filter sentence.)
- **R3.** **Core Axioms** replaces "Locked assumptions". Its preamble states the
  **reversal test** — *"if we reversed this, would it still be the same
  project?" No → axiom; Yes → philosophy or an ADR* — and the **lock-as-few-as-
  possible** rule. The three current axioms (agents-write-everything, not-in-
  repo-doesn't-exist, general-by-identity) survive verbatim in substance. (Verify:
  preamble carries both rules; the three claims are present.)
- **R4.** "What "done" looks like" is **deleted** as a section; its observable
  content survives only as R2's folded clause. (Verify: no such heading; the
  observable clause is in Mission.)
- **R5.** The restructure lands in **all three charter copies** identically in
  shape: the filled self-host `docs/CHARTER.md`, the bootstrap template
  `plugin/skills/harness-init/templates/charter.md`, and its byte-identical seed
  `base/docs/CHARTER.md`. Template + seed stay byte-identical after the change.
  (Verify: `diff base/docs/CHARTER.md plugin/skills/harness-init/templates/charter.md`
  is empty; all three have the four headings.)
- **R6.** Template/seed **FILL guidance** is rewritten so a host's human is
  directed correctly: the Mission FILL comment says *write at the most ambitious
  altitude; this is the human's to set; it is the lens for which workstreams
  belong*; the Core Axioms FILL comment carries the reversal test and the
  lock-as-few rule. (Verify: read the FILL comments.)
- **R7.** Every **prose reference site** that names the old section set is
  updated to the new one. These are: the self-host `AGENTS.md` and
  `docs/KNOWLEDGE_FORMAT.md`; the **seed templates**
  `plugin/skills/harness-init/templates/{agents-md.md,knowledge-format.md}` (the
  *portable source*); `docs/product-specs/index.md`; and the `description`
  frontmatter of each charter copy. **`base/AGENTS.md` and
  `base/docs/KNOWLEDGE_FORMAT.md` are NOT edited directly — they are rendered
  from the seed templates** (`harness_lib.SEEDS` + `hl.render`; `lint_base` B2 /
  `test_real_base_in_sync` enforce `base/{dest}` byte-equals `render(seed)`), so
  fixing the seed re-syncs `base/`. (Verify: grep for "locked assumption" / "what
  \"done\"" across the live *reference* docs returns only historical records and
  descriptive mentions; `lint_base` is OK.)
- **R8.** The historical records of the v1 charter design — this file aside —
  are **not** rewritten: `2026-06-19-charter-and-progress-map.md` (spec) and its
  completed ExecPlan stay as the v1 record. (Verify: they are untouched except an
  optional forward cross-link.)

## Design

A pure docs/methodology change — no code, no scripts. The "components" are the
charter copies and the prose that names their sections.

### Safety: nothing parses the headings

`grep` across `plugin/scripts/` and `tests/` for `## Mission` / `Locked
assumptions` / `What "done"` / `Design philosophy` returns **empty**. `nav.py`
keys the charter off its `type: charter` frontmatter, not heading text; `check.py`
and the unittest suite never read the section names. Renaming and deleting
sections is therefore a **content** change with no structural-break risk — the
only consumers are prose reference sites (R7), which are human-legible, not
parsers.

### The four-section shape

```
## Mission                       ← R2: ambition + observable clause + filter sentence
## Core Axioms                   ← R3: reversal test + lock-as-few; the 3 claims  (was "Locked assumptions")
## Design philosophy (기획의도)    ← unchanged content; now sits below the axioms it is contrasted against
## Initiatives                   ← unchanged; live status via nav.py roadmap
```

**Ordering decision (recorded):** Core Axioms precedes Design philosophy
(reversing the brainstorm's first sketch). Rationale: axioms are the bedrock and
philosophy is built on them and *defined in contrast* to them ("an axiom does not
move"); bedrock-before-building reads more naturally and puts the two principle
sections adjacent so the contrast note lands in place. This is a taste call on
the merits (no product fork) — decided here, not escalated.

### Mission — the load-bearing new prose (self-host fill)

Draft for `docs/CHARTER.md` (final wording tightened during the build; the
*shape* is the spec):

> *The ambition we steer by — and the lens for which work belongs.*
>
> Software development becomes something humans **govern by intent and taste**,
> not by typing. The agent-harness is the portable substrate that gets there: any
> repo can adopt it so an agent collective carries work from idea to landed
> change — planning, implementing, reviewing, remembering — across many sessions,
> surfacing only the genuine forks of human judgment. *You can tell it is working
> when* a developer runs `harness-init` against any repo and agents drive
> multi-session development end to end — picking the entry mode, writing the
> spec/plan, implementing in-style, gating and reviewing themselves, carrying
> memory forward — with the human touching only taste. **Every proposed
> workstream is measured against this:** does it move us toward
> *govern-by-intent, human-touches-only-forks*? (→ [`PRODUCT_SENSE.md`](../PRODUCT_SENSE.md))

The three embedded jobs map to R2: sentence 1 = ambition/altitude; sentence 3 =
the folded observable clause (R4); sentence 4 = the workstream filter.

### Core Axioms — preamble + the three claims

Preamble shape:

> *The few immovable claims the project is built on.* Test before locking one:
> **reverse it — would this still be the same project?** No → it is an axiom; Yes
> → it is a Design-philosophy strand (it can mature) or just an ADR. **Lock as
> few as possible** — every axiom is a thing we have chosen not to re-examine, so
> the bar is identity-defining, not merely "currently true". An axiom does not
> move, so it never appears in the evolution view.

The three current bullets carry over unchanged in substance (agents write
everything; not in the repo = does not exist; general by identity), each keeping
its `→ core belief N` pointer.

### Template + seed FILL guidance (R6)

`plugin/skills/harness-init/templates/charter.md` and `base/docs/CHARTER.md`
(kept byte-identical, R5) carry FILL comments instead of filled prose:

- **Mission** FILL: `<!-- FILL: one paragraph at the most ambitious altitude —
  the wide-reaching end-state this project steers by (it may be bigger than the
  artifact). THIS IS THE HUMAN'S TO SET. Include one observable "you can tell it
  is working when…" clause, and one sentence naming the Mission as the lens for
  which workstreams belong. -->`
- **Core Axioms** FILL: `<!-- FILL: the few identity-defining claims. Test each:
  reverse it — still the same project? No → axiom; Yes → it is philosophy or an
  ADR, not here. Lock as few as possible. -->`
- **Design philosophy** and **Initiatives** FILL comments carry over unchanged.

### Verification

Per-requirement checks are mechanical (heading list, `diff` of template vs seed,
grep for stale section names) and are the ExecPlan's acceptance steps. The gate
(`check.py`) must be GREEN — frontmatter conformance on the rewritten charters
and the new spec, link integrity for the new cross-links.

### Files to modify

| File | Change |
|---|---|
| `docs/CHARTER.md` | Rewrite to 4 sections; new Mission; Core Axioms; drop doneness; update `description` frontmatter |
| `plugin/skills/harness-init/templates/charter.md` | Same shape, FILL comments (R6) |
| `base/docs/CHARTER.md` | Byte-identical to the template (R5) |
| `AGENTS.md` (self-host) | Update the "(mission, design philosophy, locked assumptions)" references → new section set |
| `plugin/skills/harness-init/templates/agents-md.md` | Seed for `base/AGENTS.md` — same reference update (source of truth; `base/` re-renders) |
| `docs/KNOWLEDGE_FORMAT.md` (self-host) | Update the `charter` type-table description |
| `plugin/skills/harness-init/templates/knowledge-format.md` | Seed for `base/docs/KNOWLEDGE_FORMAT.md` — same `charter` row update |
| `base/AGENTS.md`, `base/docs/KNOWLEDGE_FORMAT.md` | NOT hand-edited — rendered from the seeds above (`lint_base` enforces) |
| `docs/product-specs/index.md` | Update the Korean charter description; register this spec |
| `docs/product-specs/2026-06-19-charter-and-progress-map.md` | Optional forward cross-link only (R8) |

## Non-goals

- **No separate North Star section.** Resolved in favour of an ambitious Mission
  (see Problem 3). YAGNI — it would double-state the Mission.
- **No programmatic enforcement of the charter shape** (no lint requiring the
  four headings). Nothing parses headings today; adding a parser is scope creep.
  The axiom-violation lint idea is a follow-up, not this spec.
- **Not building the four follow-up workstreams** (below) — they are the *output*
  of this reframe, captured for sequencing, not executed here.
- **No rewrite of historical records** (R8).

## Acceptance criteria

1. All three charter copies show the four headings in the R1 order; no "What
   "done" looks like" heading anywhere.
2. `diff base/docs/CHARTER.md plugin/skills/harness-init/templates/charter.md` is
   empty.
3. The self-host Mission contains the ambition, the observable clause, and the
   filter sentence (R2); Core Axioms preamble contains the reversal test + the
   lock-as-few rule (R3).
4. `grep -rni "locked assumption\|what \"done\"" docs/ base/ *.md` returns only
   the historical `2026-06-19-*` records.
5. `python3 plugin/scripts/check.py` is GREEN.

## Open factors — triage & resolution

- **North Star as its own section?** *(product-direction fork — escalated.)*
  **Resolved: no** — collapse into an ambitious Mission. The human judged the
  separate section redundant and noted it matches Anthropic's framing (north star
  is team/business-level, above a single project). Recorded in Problem 3 + Non-goals.
- **Deleted doneness — full delete vs fold one clause?** *(escalated.)*
  **Resolved: fold one observable clause into Mission** (R2/R4). Live progress
  stays in `nav.py roadmap`.
- **Axiom/philosophy ordering?** *(mechanical taste call — decided here.)* Core
  Axioms before Design philosophy (Design §ordering).

## Follow-ups (captured, not built)

The reframe's payoff is that the Mission becomes a **filter** that turns "suggest
workstreams" from noise into aligned proposals. Running candidates through *"does
this move us toward govern-by-intent, human-touches-only-forks?"* surfaces, in
rough sequence:

1. **Direction-GC ("workstream scout").** A periodic agent — sibling to `garden`
   (which GCs entropy) — that GCs *direction*: reads the corpus + roadmap and
   proposes new initiatives, each justified against the Mission and screened by
   the axioms. Operationalizes the motivating idea (agents proactively proposing
   the right workstreams). Highest meta-leverage; sequence first.
2. **Mission-distance roadmap view.** A `nav.py` view scoring each initiative's
   distance to the Mission's end-state — returns the deleted "doneness" as a
   *derived, live* falsifiability signal instead of a static snapshot.
3. **Axiom-violation lint.** Now that axioms are load-bearing, a deterministic
   check (or persona) flagging a change that quietly violates one (hand-written
   code creeping in; a decision living only in chat). Axioms enforced, not just
   stated.
4. **A real second host.** "General by identity" is asserted but only ever
   self-hosted; bootstrapping one genuine external host and running the loop there
   validates the axiom and is the most directly Mission-aligned substantive bet.
   Higher effort, highest proof value.
