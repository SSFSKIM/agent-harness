---
status: active
last_verified: 2026-06-28
owner: harness
type: exec-plan
description: Build the Partner — a second central role (role doc + cabinet ADR + DIRECTOR.md §14 edit + self-scheduled proactive wake + vendoring fence), doc-only v1, from the ideation-partner-cabinet spec.
base_commit: 8a121a4fec10bf6588b519c8a8ce59bbf38d3af6
review_level: targeted
---
# Ideation Partner — the cabinet's first new role

## Goal

A new central role, the **Partner**, exists as a behavioral doc the way the
Director does. Definition of done, observable: (1) `.claude/PARTNER.md` exists and,
read into a fresh session, makes that session correctly state it is the Partner —
it will crystallize an idea to a pre-spec brief and drop it as a board ticket, and
it refuses to write a spec, decompose, code, merge, or transition ticket state;
(2) `docs/adr/0010-cabinet-of-central-roles.md` records the reframe and
`.claude/DIRECTOR.md` §14 no longer claims "exactly two kinds of agent" but
cross-links it; (3) the proactive-wake mechanism (`CronCreate durable`) is shown to
persist + be removable so the role doc's self-scheduling instruction is grounded in
a verified primitive; (4) the gate is GREEN and both indexes register their new
pages. This plan is **doc-only** — no `director/` Python changes (the declarative
`partner` config block is a spec Non-goal).

## Context

- Built from the product-spec
  [ideation-partner-cabinet](../../product-specs/2026-06-28-ideation-partner-cabinet.md)
  — the spec owns the design (Identity, the two modes, guardrails G1–G5, the brief
  format, the session/scheduler model); this plan owns the build. Do not re-derive
  the spec.
- The Partner mirrors the Director's role-doc pattern: read
  [`.claude/DIRECTOR.md`](../../../.claude/DIRECTOR.md) — Identity, §2 (taste-vs-handle,
  the line the Partner's converge-vs-diverge + brief-fence mirror), §13 (lights-out,
  which the Partner deliberately does NOT have), §14 (the two-profile config split the
  reframe revises).
- The cabinet reframe is the sibling move to [ADR 0003](../../adr/0003-lights-out-director.md)
  (which named the Daemonized-Claude runtime — now the Partner's substrate — as a
  separate track) and reuses `docs/PRINCIPLES.md` (the externalized-taste layer the
  Partner consults, same as the Director).
- Scout is the Partner's upstream seed + callable divergence tool, not a peer
  ([workstream-scout spec](../../product-specs/2026-06-27-workstream-scout.md); its
  `scope: director` worker-vendoring exclusion is the fence the Partner joins).
- The daemon/`claude agents` substrate and the `CronCreate durable` / `-p --resume`
  drive surfaces were verified live 2026-06-28 (Claude Code v2.1.195) — recorded in the
  spec's Verification.

## Approach (self-generated alternatives)

- **A — Doc-first, scheduler-as-prose.** v1 ships the role doc + ADR + §14 edit, and
  expresses the proactive wake as a PARTNER.md *runtime instruction* (the Partner
  session self-schedules via `CronCreate durable`); no harness Python. Tradeoff: the
  schedule/team live in prose, not config — fine for one centralized Partner, defers
  the config-code blast radius until a second host needs it.
- **B — Declarative-config-first.** Add a `.harness.json:partner` block +
  `director/config.py` validation now so schedule/team are config-driven from day one.
  Tradeoff: "more complete", but builds speculative config + tests for a knob nobody
  needs yet, and the spec already put the declarative block in Non-goals (YAGNI).
- **Chosen: A** — the spec decided doc-only v1; B speculatively builds config for a
  single-Partner deployment. A reaches a usable Partner fastest with minimal blast
  radius. (Decision log.)

## Assumptions & open questions (self-interrogation)

- **Assumption:** the next free ADR number is **0010** (index lists 0001–0009). If a
  concurrent session lands a 0010 first, renumber to the next free one at M1 (re-grep
  the index before writing) — what breaks otherwise is a duplicate-number lint.
- **Assumption:** `.claude/PARTNER.md` is the right home (mirrors `.claude/DIRECTOR.md`,
  central, never host-seeded). If wrong, the role doc would be mis-placed under
  `docs/`; the spec's R1 fixes `.claude/` explicitly, so this is settled.
- **Assumption:** a full end-to-end dogfood (Partner brief → orchestrator claim →
  product-design worker → spec) needs a running orchestrator + live Linear board +
  workers, which is an operational stand-up out of this doc-only plan's scope. The
  plan's behavioral check is therefore the **PARTNER.md-behavior smoke** (a fresh
  subagent reading the doc demonstrates role + boundary), with the full-pipeline
  dogfood recorded as a post-merge live validation the human runs. — what breaks if
  wrong: nothing in the deliverable; only the depth of in-gate validation.
- **Open:** does the proactive pass re-arm the 7-day-expiring cron from *inside its
  own fire*, or on *session start*? → resolved autonomously: **document both** in
  PARTNER.md (re-arm on the final fire AND on session start — belt-and-suspenders,
  idempotent), since either alone has a failure window. Not a taste fork.
- **Open:** should M3 fire a live cron to prove the wake? → resolved: **no** — a live
  recurring fire injects a prompt into this session (disruptive). M3 proves the
  load-bearing property (durable persistence + removability) via a far-future one-shot
  that is created, observed in `.claude/scheduled_tasks.json`, then deleted — never
  fired. The live fire is the post-merge dogfood's job.

## Milestones

- **M1 — Cabinet reframe: ADR 0010 + DIRECTOR.md §14 + ADR index.** Scope: the
  *decision* layer, authored before the role doc so PARTNER.md can cross-link it. At the
  end there exists `docs/adr/0010-cabinet-of-central-roles.md` recording that the center
  is a named-role cabinet (Director = operations, Partner = ideation/strategy, room for
  more), explicitly superseding `.claude/DIRECTOR.md` §14's "the harness runs exactly
  **two** kinds of agent"; `.claude/DIRECTOR.md` §14 is edited to say "cabinet of central
  roles" and cross-link ADR 0010 (the two-config-half split for the Director profile
  stays — only the "exactly two" count changes); and `docs/adr/index.md` registers 0010.
  Run the gate (`python3 plugin/scripts/check.py`); expect GREEN, and
  `grep -n "exactly two" .claude/DIRECTOR.md` returns nothing while
  `grep -n "0010" .claude/DIRECTOR.md docs/adr/index.md` shows both cross-links.

- **M2 — `.claude/PARTNER.md` (the core).** Scope: the role doc, the bulk of the work,
  mirroring DIRECTOR.md's structure. At the end `.claude/PARTNER.md` exists with:
  *Identity* (reading it makes a session the Partner; front-of-pipeline owner; central,
  never host-seeded); *the operating line* (converge-vs-diverge dial = "ambitious yet
  reasonable"; the brief fence); *Mode 1* (on-demand dialogue → optionally `scout` /
  `deep-research` only when warranted → pre-spec brief → one `issueCreate` board ticket;
  human reaches it via `claude attach`); *Mode 2* (self-scheduled `CronCreate durable`
  proactive pass → assess via `docs-nav` roadmap + `logs.md` + recent runs → optional
  `scout` pass → `PushNotification` surface; re-arm on final-fire AND session-start);
  *Guardrails G1–G5* verbatim from the spec (surface-never-enact; stop-at-brief;
  no-worker-invoke/vendor; `issueCreate`-only / orchestrator owns lifecycle;
  direction/taste human-owned → consult `PRINCIPLES.md`, surface uncovered forks); *the
  brief format* (R5 fields); *config note* (identity half in `.claude/`; declarative
  block deferred). Run the gate; expect GREEN. Behavioral smoke: dispatch a fresh
  general-purpose subagent given only PARTNER.md + a toy idea — it must (a) state it is
  the Partner, (b) produce a well-formed pre-spec brief, (c) refuse to write a spec /
  code / decompose / transition state (G2/G4). Capture the transcript into Surprises.

- **M3 — Scheduler-persistence PoC + vendoring fence note.** Scope: ground the one
  unproven seam and close G3's bookkeeping. At the end: a recorded proof that
  `CronCreate({recurring:false, durable:true, cron:<far-future one-shot>})` writes the
  job to `.claude/scheduled_tasks.json` and `CronDelete` removes it (created → observed
  in the file → deleted → absent; never fired) — proving the durable-persistence /
  re-arm substrate PARTNER.md's Mode 2 relies on; AND
  `docs/exec-plans/tech-debt-tracker.md` gains a row (or amends the existing
  `scope: director` row) recording that `.claude/PARTNER.md` + the Partner's skills join
  the worker-vendoring exclusion (G3). Run the gate; expect GREEN, the tracker row
  present, and the PoC transcript in Surprises. (Doc-only — no harness code ships for the
  scheduler; the PoC validates the platform primitive the role doc instructs the Partner
  to use at runtime.)

## Progress log
- [x] (2026-06-28) M1 — cabinet reframe. Wrote `docs/adr/0010-cabinet-of-central-roles.md`
  (named-role cabinet, supersedes §14 "exactly two", loose board-mediated coupling, Partner
  no-lights-out). Edited `.claude/DIRECTOR.md` §14 intro → cabinet framing + `[ADR 0010]`
  cross-link (Director/worker config halves untouched). Registered 0010 in `docs/adr/index.md`.
  Acceptance: `grep -c "exactly two" .claude/DIRECTOR.md` = 0; both cross-links present; gate GREEN.
- [x] (2026-06-28) M2 — wrote `.claude/PARTNER.md` (Identity, §1 operating line, §2 Mode 1,
  §3 Mode 2, §4 guardrails G1–G5, §5 brief format, §6 cabinet seams, §7 config), mirroring
  DIRECTOR.md's second-person guide voice. All 9 cross-links resolve; gate GREEN. Behavioral
  smoke PASSED (see Surprises).
- [x] (2026-06-28) M3 — scheduler-persistence PoC + vendoring fence note. PoC RAN (see
  Surprises): `CronCreate`/`CronList`/`CronDelete` session scheduling works; **`durable: true`
  is NOT honored in this env** (one-shot AND recurring both reported `session-only`, no
  `.claude/scheduled_tasks.json` written at project or user scope). Corrected `PARTNER.md` §3 to
  make **session-start re-arm load-bearing** (durable = best-effort). Vendoring fence: amended
  the existing `scope: director` tracker row (line ~160) to generalize to the cabinet class —
  noting `PARTNER.md` is already non-vendored (in `.claude/`, outside the copy loop, like
  `DIRECTOR.md`), so G3 holds for the doc; only `scout` rides the tracked gap. Gate GREEN.

## Surprises & discoveries
- **M2 behavioral smoke (PASS).** A fresh `general-purpose` subagent given only
  `.claude/PARTNER.md` + a toy idea ("see progress at the initiative level, not per-ticket")
  + a boundary probe ("also write the spec and start implementing"): (a) correctly stated it
  is the Partner at the front of `Partner → board ticket → product-design → …`; (b) ran the
  converge dial and *deliberately skipped* scout/research per §1; (c) produced a well-formed
  pre-spec brief with every §5 field, and noted it would `issueCreate` but not `issueUpdate`
  (G4); (d) **refused** to write the spec (G2) and to implement (G2/G3), citing the guardrails
  by number. Confirms the role doc induces correct Partner behavior incl. the fences, with no
  scaffolding beyond the doc itself.
- **M3 scheduler PoC — durable persistence NOT honored here (negative finding).** Probed
  `CronCreate` with `durable: true`: a one-shot reported `session-only` (expected — one-shots
  never persist); a **recurring** `durable:true` job ALSO reported "Session-only (not written
  to disk)" and no `.claude/scheduled_tasks.json` appeared at project OR user scope. So the
  spec's R6 / Verification claim that `durable:true` persists to `.claude/scheduled_tasks.json`
  is **not true in this runtime** (a background-job session). Caught before it became a silent
  production failure. The design already carried the mitigation (re-arm), now promoted to
  load-bearing in `PARTNER.md` §3: **the session-start re-arm — not durable persistence — is
  what guarantees the proactive pass survives a recycle.** Session-scoped scheduling itself
  (create/list/delete, idle-only firing) is real and works.

## Decision log
- 2026-06-28: Chose Approach A (doc-first, scheduler-as-prose) over declarative-config —
  the spec put the `.harness.json:partner` block in Non-goals; A is minimal-blast-radius
  and reaches a usable Partner fastest.
- 2026-06-28: M3 proves the wake via durable-persistence + removability of a never-fired
  far-future one-shot, not a live recurring fire (which would inject a prompt into a live
  session). Full live fire is the post-merge dogfood.
- 2026-06-28: PARTNER.md documents re-arm on BOTH final-fire and session-start (idempotent
  belt-and-suspenders) to close the 7-day recurring-expiry window either alone leaves.
- 2026-06-28: After the M3 probe showed `durable:true` is not honored in this env, made
  session-start re-arm the *load-bearing* mechanism (durable demoted to best-effort) rather
  than treating durable as the persistence guarantee — honest-to-the-probe over honest-to-the-
  tool-contract.

## Feedback (from completion gate)
- **Spec drift (P2) — `durable` persistence claim.** The committed spec
  [ideation-partner-cabinet](../../product-specs/2026-06-28-ideation-partner-cabinet.md) R6 +
  Verification assert `CronCreate(durable:true)` persists to `.claude/scheduled_tasks.json`
  ("confirmed from the tool contract + a writability/baseline probe"). The M3 *behavioral* probe
  contradicts this in a background-job session (session-only, nothing written). PARTNER.md was
  corrected; the spec wording should be softened to "durable is best-effort; session-start
  re-arm is the guarantee" in a follow-up (the spec is committed + human-reviewed, so flag
  rather than silently rewrite). Belongs in a doc-gardening reconciliation pass.
- **review-arch P1 (FIXED in-gate) — handoff ignored the `agent-ready` dispatch gate.**
  PARTNER.md/ADR 0010 said the orchestrator "claims and executes" a fresh brief ticket, but
  under the default-on `agent-ready` gate (ADR 0009; `config.py` `dispatch_requires_label:
  True`; `orchestrator.py` `eligible_tickets(require_label=True)`) an un-tagged ticket is
  never dispatched — and `agent-ready` *is* the human-owned "pursue this?" bit, exactly what
  the Partner's no-lights-out identity reserves for the human. Fixed: the Partner now creates
  the brief **without** `agent-ready` (a proposal); the human admits it by marking
  `agent-ready`, which triggers the orchestrator — making loose-coupling, ADR 0009, and
  G1/G5 cohere. Edited Identity, §2 step 4, G4, §6, and ADR 0010's coupling paragraph. **Spec
  reconciliation (P2):** the spec's R3/Mode-1 handoff has the same omission — soften it to
  route through the `agent-ready` human admission in the doc-gardening pass.
- **P2 (FIXED in-gate, both Minor):** DIRECTOR.md §14 heading dropped "two" ("Agent profiles —
  where each is configured") so the TOC no longer contradicts the cabinet intro; ADR 0010's
  basename-ambiguous `[[…]]` spec wikilink replaced with an explicit relative path.
- **Proposed rules (doc-gardener — not blocking):** (a) a doc-only methodology spec should
  state which acceptance criteria are gate-verifiable vs deferred-to-live-dogfood
  (spec-compliance); (b) a role doc quoting a sibling's prose verbatim should be grep-anchored
  at authoring time — a DESIGN.md twin of "retire = grep the surviving bodies" (code-quality);
  (c) a reframe of a load-bearing count should reconcile the section *header* too, and dated
  `logs.md` entries are historical lineage exempt from the surviving-bodies sweep (review-arch).

## Outcomes & retrospective
