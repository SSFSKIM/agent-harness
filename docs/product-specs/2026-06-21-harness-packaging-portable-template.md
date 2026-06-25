---
status: stable
last_verified: 2026-06-21
owner: harness
phase: packaging/00-portable-template
type: product-spec
tags: [packaging, template, portability, memory, director, plugin, profiles]
description: Package the whole repo system as a strict, self-describing, portable base template — retire the dead memory-loop subsystem in favor of native Claude Code memory, reorganize the docs system (memory/→adr/+logs.md+tech-debt), relocate the Director's operating manual to agent config (.claude/), consolidate the two scattered agent profiles (Director + Codex worker) into one settable source each, and clean + republish the plugin. Parent spec; six slices, each a linked ExecPlan at build time.
---
# Harness packaging — the portable strict-base template + the two-agent profile model

Parent spec. The harness is mature and self-hosting, but it exists only as **one
instance of itself**, not as a clean, implantable, self-describing base another
project can start from. This spec packages the whole system — repo structure, docs
system, the two-agent (Director + Codex worker) profiles, and the plugin — as a
**strict, comprehensive base** that any project adopts and then extends ("strict
base + add whatever each repo needs").

The design was settled with the human over two design turns (the consumption-model
fork → centralized Director; the template-content fork → self-describing guidance
docs; the memory-retirement fork → retire the whole loop; the logs.md fork → light
milestone-grained). This spec records that design; it does not re-derive it.

## Problem

Adopting the harness today requires **repo-spelunking** — the exact friction the
real dogfood exposed (setup reconstructed from memory). Five concrete gaps:

1. **The docs system carries a dead memory subsystem.** `docs/memory/` (bootloader
   `MEMORY.md`, `progress/`, `openq/`, `limitations/`, `knowledge/`, `archive/sessions/`,
   `adr/`) was built for a feeder→imprint→dream loop that is **disabled** (AGENTS.md:
   "the automatic feeder/imprint memory loop is disabled pending redesign"). Native
   Claude Code memory now owns ephemeral continuity. The subsystem clutters any
   "strict clean base" and ships dead machinery (`feeder_*.py`, `imprint_*.py`,
   `tidy_stop.py` + its Stop hook, the `dream` skill, the `dreamer` agent).

2. **The Director's two agent configs are scattered.** The Codex-worker posture lives
   across `config.py` `DEFAULTS["worker"]`, `worker/autonomy.py`, `worker/app_server.py`
   (its own hardcoded fallback defaults), the `.harness.json` `director.worker` override
   surface, and the `workspace_skills/` bundle. The Director's own identity is split
   across `.claude/settings.json`, the `.claude/skills/director/` launcher, and
   `docs/DIRECTOR.md`. There is no single settable, guided source per agent.

3. **The Director's operating manual sits in `docs/` as if it were general project
   knowledge.** `docs/DIRECTOR.md` is central-agent *config* (how the watched main
   session behaves), not portable project knowledge — but it lives next to CHARTER and
   PLANS and is seeded nowhere (correctly, since the Director is centralized).

4. **The base doc set is incomplete and under-guided for adoption.** The harness ships
   ~20 seed templates in `plugin/skills/harness-init/templates/`, but they are partly
   blank-FILL stubs rather than **self-describing authoring guides**, `PRINCIPLES.md`
   has no template at all, and there is no `references/` seed (LLMs struggle without
   external-API/source context).

5. **No inspectable, drift-checked "base" artifact exists.** You cannot open one folder
   and see the whole clean system; you reconstruct it mentally from the live instance.

## Design — the packaging model

Three content natures, three handling rules (the principle that resolves drift):

| Layer | Handling | Why |
|---|---|---|
| **Guidance docs** (CHARTER, ARCHITECTURE, AGENTS, PLANS, …) | *Authored guidance* — each file teaches how to write itself; mirrors repo structure | Stable methodology, near-zero drift |
| **The machine** (`plugin/` skills, agents, scripts, lints) | **Referenced, never copied** (the marketplace `path` wiring self-host already uses); the base carries an *index* of what exists | Zero drift by construction |
| **Config + the two profiles** (`.harness.json`, `.claude/`, `config.py`) | **Pre-filled defaults + `<!-- FILL -->`** for per-project knobs | Settable, guided, no wizard |

The base **mirrors the repo's shape**; only the *content nature* changes per layer.
The Director stays **centralized** (run from the agent-harness repo against an external
board+repo) — the base ships a Director-*ready* config, not a Director.

Six slices, in dependency order. Each is independently verifiable and becomes a linked
ExecPlan (`packaging/01`…`packaging/06`).

### Slice 1 — Memory subsystem retirement (`packaging/01`)

Retire the disabled memory loop and reorganize the docs system around durable,
version-controlled knowledge + native CC memory for continuity.

- **R1.1 — Remove `docs/memory/`.** Delete the tree. Native Claude Code memory owns
  ephemeral working continuity (no in-repo bootloader).
- **R1.2 — Surface ADRs to `docs/adr/`.** Move `0001`–`0003` + `index.md`; ADRs are
  the durable, version-controlled decision record and deserve top-level standing.
- **R1.3 — tech-debt-tracker absorbs `openq/` + `limitations/`.** Fold
  `memory/openq/*` and `memory/limitations/*` content into
  `docs/exec-plans/tech-debt-tracker.md` (it already tracks deferred work); retire the
  separate dirs and their indexes.
- **R1.4 — Rehome `recursion-guard.md`.** `memory/knowledge/recursion-guard.md` is a
  design rationale → move to `docs/design-docs/`.
- **R1.5 — Add `docs/logs.md`.** Light, append-only project narrative at **milestone
  grain** (ExecPlan completion / ADR / docs-system change). Links opt-in. **Read
  on-demand, NOT auto-loaded** (zero standing-context cost). Replaces `progress/current.md`.
  Wire a one-line "log at milestones" note into AGENTS.md — **not** a per-change mandate.
- **R1.6 — Retire the memory-loop machine.** Delete `plugin/scripts/feeder_firstprompt.py`,
  `feeder_sessionstart.py`, `imprint_enqueue.py`, `imprint_guard.py`, `imprint_run.py`,
  `tidy_stop.py`; remove the `Stop → tidy_stop.py` hook from `plugin/hooks/hooks.json`
  (leaving `hooks.json` with an empty/removed Stop entry); delete the `dream` skill
  (`plugin/skills/dream/`) and the `dreamer` agent (`plugin/agents/dreamer.md`); delete
  the `memory-bootloader.md` template.
- **R1.7 — Rewire the machine off `memory/`.** Update `scaffold.py` (drop `docs/memory/*`
  from `SCAFFOLD_DIRS`/`SEEDS`/`CATEGORY_INDEXES`; add `docs/adr/` + its index, `docs/logs.md`,
  `docs/references/`), `lint_docs.py` (`adr` becomes a top-level managed/indexed root;
  drop `memory/*` roots and the `MEMORY.md` special-cases), `harness_lib.py`
  (`MANAGED_DOCS`), and `gen_inventory.py` if it enumerates memory scripts/hooks.
- **R1.8 — Update self-host docs.** AGENTS.md "Memory (read/write paths)" → native CC
  memory + `docs/adr/` + `docs/logs.md` + tech-debt; ARCHITECTURE.md memory references.

Verify: `check.py` GREEN; `grep -rn "docs/memory" docs plugin director --include=*.md
--include=*.py` returns only archived/completed-spec history (live tree clean); the
removed scripts/hooks/skills/agents are gone and nothing imports them (tests pass).

### Slice 2 — Strict-base docs + guidance enrichment (`packaging/02`)

Mature the seed-template layer into the self-describing strict base.

- **R2.1 — Define + complete the strict-base doc set.** CHARTER, KNOWLEDGE_FORMAT,
  PLANS, DESIGN, **PRINCIPLES**, PRODUCT_SENSE, QUALITY_SCORE, RELIABILITY, SECURITY
  (optional), `design-docs/core-beliefs.md`, AGENTS, CLAUDE (3-line pointer), ARCHITECTURE,
  `adr/` + index, `references/` + index, `exec-plans/{active,completed}/` + tech-debt-tracker,
  `design-docs/index.md`, `product-specs/index.md`, `logs.md`.
- **R2.2 — Every shipped doc's template is a self-describing guide.** Each carries a
  "**How to write this file**" block + scoped `<!-- FILL -->` markers — not blank stubs,
  not this-repo's content. An agent authors each doc from the file alone.
- **R2.3 — Author the missing `PRINCIPLES.md` template + guide** (the human's
  externalized decision-taste doc; no seed exists today).
- **R2.4 — `ARCHITECTURE.md` template → redirect to the `architecture-setup` skill.**
  The skill already owns architecture authoring; the template is a short pointer to it,
  not a duplicated guide.
- **R2.5 — Add `references/` seed + index** with a guide explaining *why* (LLMs need
  external-API/source digests; llms.txt convention).
- **R2.6 — Structured templates for `exec-plans/active/` and `exec-plans/completed/`**
  (the plan skeleton from PLANS.md), and **`index.md` templates** for `design-docs/` and
  `product-specs/`.

Verify: a fresh `scaffold.py --root <tmp>` produces a base where every doc is
self-describing (manual read-through: no blank stub, no instance content); `check.py
--root <tmp>` GREEN; no surviving `FILL` outside intended markers.

### Slice 3 — Director relocation + launcher retirement (`packaging/03`)

- **R3.1 — Move `docs/DIRECTOR.md` → `.claude/DIRECTOR.md`.** It is central-agent
  config, not portable project knowledge.
- **R3.2 — Retire the `.claude/skills/director/` launcher.** Its two launch steps fold
  into DIRECTOR.md (which already has §0 "Standing up the Director"); "becoming the
  Director" = read `.claude/DIRECTOR.md`.
- **R3.3 — Update every live reference** — `director/{decider,director_min,merger,
  orchestrator,status}.py` path strings, AGENTS.md map row, the `harness-init` §0 pointer,
  CHARTER.md, PRINCIPLES.md — **and bulk-update archived links** in `exec-plans/completed/*`
  and `product-specs/*` (mechanical path edit, enforced by D5; not a history rewrite).
  No redirect stub left in `docs/` (that would contradict the move).

Verify: `check.py` GREEN (D5 no broken links); `grep -rn "docs/DIRECTOR.md"` returns
nothing live; the Director manual loads from `.claude/`.

### Slice 4 — Two agent profiles consolidated (`packaging/04`)

One settable source + one guide per agent. **No `agents/director/` or `agents/worker/`
directories** — each profile's natural home already exists.

- **R4.1 — Director profile = two halves, documented.** Agent identity → `.claude/`
  (`settings.json` + `.claude/DIRECTOR.md`); orchestrator runtime → `.harness.json`
  `director` block; secrets → `.env`. A short guide names the two halves and the env
  contract (GH_TOKEN, LINEAR_API_KEY, DIRECTOR_TEAM).
- **R4.2 — Worker profile = single source, reconciled.** `config.py` `DEFAULTS["worker"]`
  is the documented single source of truth; **reconcile `worker/app_server.py`'s
  hardcoded fallback defaults** (`"untrusted"`, `"workspace-write"`) so they cannot drift
  from `config.DEFAULTS`; document the `.harness.json` `director.worker` override surface
  + the `workspace_skills/` bundle as the worker's installed-skill set. A short guide.
- **R4.3 — Retire `qa` from `workspace_skills/`** (self-QA is folded into the execplan
  completion gate); update any worker template/protocol text that referenced it.

Verify: each profile has exactly one settable source + one guide; `check.py` GREEN;
a config round-trip test shows app_server defaults equal `config.DEFAULTS` (no drift).

### Slice 5 — Plugin cleanup + manifest update (`packaging/05`)

- **R5.1 — Manifests reflect reality.** `plugin/.claude-plugin/plugin.json` description
  drops "memory loop / feeder / imprint / dreaming"; **version bump**.
  `.claude-plugin/marketplace.json` plugin description lists the current skill set
  (execplan, harness-lint, docs-tree, docs-nav, product-design, harness-init,
  architecture-setup, garden) — `dream` removed.
- **R5.2 — Regenerate the component inventory** (`gen_inventory.py`) after the deletions.
- **R5.3 — Republish.** Building the manifest is in scope; **actually pushing a public
  release is a separate go/no-go** the human confirms (outward-facing / taste).

Verify: `check.py` GREEN (component inventory/coverage consistent); manifests name only
existing components.

### Slice 6 — The packaged base artifact + legacy strip (`packaging/06`, capstone)

- **R6.1 — Checked-in reference base instance.** A clean, self-describing base
  (rendered from the matured scaffold) committed for inspection — the tangible "open one
  folder and see the whole system" artifact. **Hand-synced** (manual drift discipline,
  per the chosen no-generator model).
- **R6.2 — Drift-check lint.** A check that flags when the checked-in base falls out of
  sync with its source (the seed-template set + the referenced plugin component list), so
  manual sync stays honest. Advisory or blocking — decided in the slice's ExecPlan.
- **R6.3 — `SETUP.md`** in the base: guided "bring this instance alive + point the
  central Director at it" (reuses the runbook `docs/DIRECTOR_RUNBOOK.md`).
- **R6.4 — Legacy strip from the base.** Exclude `docs/symphony-original/`, `EDUCATION.md`,
  `docs/superpowers/`, `docs/generated/`, and the **self-host instance** design-docs
  (`okf-comparison.md`, `symphony-parity-gap.md`, and the *filled* self-host
  `docs/design-docs/agent-harness.md`). These stay in the self-host repo; the base ships
  none of them. **Note (clarified in the slice):** the base *does* ship the generic
  `design-docs/agent-harness.md` **template** — it carries the `{{COMPONENTS}}` machine
  index that R6.2 drift-checks; what is stripped is the self-host instance content of that
  doc, not the template seed.

Verify: the base folder is inspectable, self-describing, legacy-free; the drift-check
passes; a from-scratch read (no source repo) is enough to bring it to life.

## Non-goals (YAGNI)

- **No per-project portable Director.** The Director stays centralized (settled). The
  base is Director-*ready*, not Director-bearing. No extraction of `director/` into an
  installable standalone tool (the bigger packaging option was declined).
- **No template generator.** Hand-authored guidance + manual sync + a drift-check
  (no on-demand generator) — chosen explicitly.
- **No setup wizard / new config system.** Reuse `.harness.json` + FILL + `SETUP.md`.
- **No `README.md` front door.** AGENTS.md stays the single front door.
- **No memory-loop redesign.** The loop is retired, not re-architected; native CC
  memory replaces it. (`docs/memory/openq/memory-loop-redesign.md` is closed, not carried.)
- **No rewrite of archived decisions.** Slice 3 updates archived *link paths* only.
- **No public plugin release in this work** — manifest is prepared; the push is a
  separate human go/no-go.

## Acceptance criteria

1. **Memory retired:** `docs/memory/` gone; ADRs at `docs/adr/`; openq+limitations in
   tech-debt-tracker; `logs.md` present (on-demand); the feeder/imprint/dream/dreamer/
   tidy_stop machine deleted with nothing importing it; `scaffold.py`/`lint_docs.py`/
   `harness_lib.py` rewired; `check.py` GREEN; tests pass.
2. **Strict base self-describing:** a fresh scaffold yields a base where each of the
   strict-base docs (incl. the new `PRINCIPLES.md` and `references/`) teaches how to
   write itself; ARCHITECTURE template redirects to `architecture-setup`; exec-plans
   active/completed + the two indexes have structured templates; `check.py --root` GREEN.
3. **Director relocated:** manual at `.claude/DIRECTOR.md`; launcher retired; no live
   `docs/DIRECTOR.md` reference; D5 GREEN.
4. **Two profiles consolidated:** Director = `.claude/` + `.harness.json:director` (+ env
   contract guide); worker = `config.py DEFAULTS` (app_server reconciled, drift-tested) +
   override surface + `workspace_skills/` (qa retired) + guide; no `agents/*` dirs.
5. **Plugin clean:** manifests + inventory name only existing components; version bumped;
   `check.py` GREEN.
6. **Base artifact:** checked-in, legacy-stripped, drift-checked, with `SETUP.md`; an
   agent can adopt it without reading the source repo.
7. **Whole-repo gate GREEN** at every slice's completion; the self-host repo remains a
   working harness throughout.

## Hand-off

Each slice → a linked ExecPlan (`execplan` skill), built in order (1→6; 2 may proceed
alongside 1 once the `memory/`→`adr/`/`logs.md` shape from 1 is fixed). The ExecPlans
reference this spec and own execution order/progress; they do not re-derive the design.
