---
status: completed
last_verified: 2026-06-13
owner: harness
base_commit: 35deac5df7fd5efd08d289ba865f95d29e360322
---
# Architecture-setter: agent → skill, output FORM-routed

## Goal
A repo's architecture & taste enforcement is **set up by a skill the main agent
follows** (with the repo's full context), not by a dispatched persona — and that
skill routes each concern to its right enforcement **FORM**: a deterministic
**lint** for mechanical invariants (always-true, machine-checkable, costly if
missed — e.g. dependency direction), a host **guide-skill** for methodology (how
to develop respecting the architecture — no single frozen answer), persona
review or fix-forward otherwise. Terms: *FORM* = the medium an invariant is
enforced through; *mechanical invariant* = a property a script can decide and
that one bad line silently breaks; *methodology* = how-to-work guidance that
needs judgment, not a frozen rule; *guide-skill* = a host `.claude/skills/` skill
that encodes that methodology. Demonstrable:

1. `plugin/skills/architecture-setup/SKILL.md` exists, the gate is GREEN, and it
   triggers on setup language; `plugin/agents/architecture-setter.md` is gone and
   **no live doc or skill references the old agent** (`grep -rl architecture-setter`
   over the plugin + live docs returns only this plan's history).
2. `harness-init` step 7 **runs the architecture-setup skill**, not a Task
   dispatch of a persona.
3. On the live Lingual host, the skill's method produces a **host guide-skill**
   encoding a methodology invariant a lint cannot capture (e.g. the safe
   procedure for touching a dual-write/read-flag persistence seam) — proving the
   skill-FORM output the way the locale L1 lint proved the lint-FORM. Committed to
   the `harness-init` branch.

## Context
Follows the host-taste-setter plan (the setter axis: `.harness.json` host-lint
substrate + the `architecture-setter` persona). Two findings drove this rework:
(a) the setter only ever ran **inline** — it was already skill-shaped, never
dispatched as an isolated agent; (b) the deeper design call (user + the fork
analysis): enforcement has two media — a **skill enforces by instruction**
(soft; the agent reads and follows it with judgment — right for *methodology*)
and a **lint enforces by interception** (hard; the gate blocks regardless of
what the agent looked at — right for *mechanical invariants*). The setter's
*authoring process* is a procedure → it belongs in a skill. But the **output is
not skill-only**: layered-architecture enforcement decomposes — "respect the
layers while developing" is a guide-skill, "no upward import" is a lint (our own
**S2** is exactly that dependency-direction lint). So this plan converts the
medium (agent → skill) and adds **skill** as a first-class FORM the procedure
can emit, without removing lint as the FORM for mechanical invariants.

Why a skill (not an agent) for setup: the procedure must read the codebase
deeply → it needs the main agent's full repo context, not an isolated subagent;
its description triggers it at the right moment (harness-init / arch evolution);
and a skill's soft-enforcement weakness does not bite a one-time *explicit setup
action* (unlike a per-commit invariant, which is why those stay lints).
review-arch stays an **agent**: review wants isolated, independent judgment;
setup wants construction with full context. The asymmetry is intentional.

## Milestones
- [x] M1 New `plugin/skills/architecture-setup/` skill: lean imperative SKILL.md
  (third-person trigger description) + `references/` (the full FORM rubric, the
  `FAIL…FIX:` authoring contract, the lint skeleton pointer, the guide-skill
  pattern). Content converted from `architecture-setter.md`'s Method, with
  **skill** added as a FORM. Follows skill-dev best-practices (progressive
  disclosure; SKILL.md ≤ ~2k words). Gate GREEN.
- [x] M2 Remove `plugin/agents/architecture-setter.md`; rewire `harness-init`
  step 7 (run the skill, not dispatch a persona); update every LIVE reference —
  ARCHITECTURE invariant 7 + data-flow note, DESIGN (host-vs-machine rule +
  constructive-personas note), SECURITY T9, AGENTS porting line, agent-harness.md
  (template + self-host components table), QUALITY_SCORE host-enforcement row;
  regenerate the component inventory. Gate GREEN.
- [x] M3 Demonstrate the skill-FORM on the live Lingual host (`harness-init`
  branch): run the architecture-setup method, author one host guide-skill under
  `.claude/skills/` encoding a methodology invariant, `git add -f`, gate GREEN,
  commit. (The lint-FORM was proven by L1; this proves the skill-FORM.)
- [x] M4 Completion gate: self-review + review-arch + review-reliability all
  SATISFIED (review-security skipped — this diff touches skills/agents/docs, not
  the live exec surface — hooks/`.harness.json`/`.harnessignore`). 4 P2s applied,
  0 P1. review-arch ran on Claude (fallback) after codex stalled twice.

## Progress log
- 2026-06-13: plan created from the user decision + fork synthesis (decompose,
  don't replace; setter's medium → skill, output stays FORM-routed).
- 2026-06-13: M1+M2 done (one commit — D9 coverage + inventory couple them).
  New `architecture-setup` skill (SKILL.md ≤2k words, imperative, third-person
  trigger desc; references/forms.md + authoring.md per progressive disclosure).
  Agent removed; harness-init step 7 runs the skill; ARCHITECTURE inv7, DESIGN
  (host-vs-machine + a new "construction needing full context = skill, not
  persona" rule), SECURITY T9, AGENTS porting, both agent-harness.md, QUALITY_
  SCORE updated; inventory regen. Gate GREEN, 82 tests. Plugin has zero live
  refs to the old agent (only historical plan/tracker/quality-score records).
- 2026-06-13: M3 done on the live Lingual host (`harness-init` @ 582416f). Ran
  the architecture-setup method inline (= how the skill runs: main agent, full
  repo context) → authored `.claude/skills/persistence-seam/` encoding the safe
  procedure for the Firestore↔PG dual-write seam (invariant 1), wired into
  AGENTS.md mandatory-skill usage + the ARCHITECTURE Enforcement table. Lingual
  gate GREEN with both FORMs now live: L1 lint + the guide-skill. Resynced
  Lingual's harness doc + inventory for the agent→skill change.
- 2026-06-13: M4 completion gate cleared. review-reliability (codex) + skill-reviewer
  + review-arch all SATISFIED, 0 P1, 4 P2 all applied (host-lint.py stale
  docstring; SKILL.md duplicate-trim + conditional `git add`; authoring.md
  off-by-one path). review-arch ran on a Claude fallback after the codex reviewer
  stalled twice on `git diff 35deac5`. Gate GREEN, 82 tests. Plan → completed/.

## Surprises & discoveries
- **The cross-host coupling recurred exactly as predicted.** Adding the
  `architecture-setup` skill + removing the `architecture-setter` agent reddened
  Lingual's gate (D9: the new skill wasn't in Lingual's docs; GEN: stale
  inventory). Same tracker row from host-taste-setter M5 — every plugin component
  change forces a host doc + inventory resync. Fixed Lingual; the recurrence
  confirms the row is worth a real fix, not just a note.
- M3 chose invariant 1 (the dual-write seam) for the guide-skill because it is
  textbook methodology: "check the LIVE flags (`gcloud`...), don't 'finish the
  migration' by retiring the rollback bridge" — judgment a lint cannot make. The
  three families have non-uniform states (analytics PG-sole fail-closed,
  relational dual-write bridge, memberships Firestore-authoritative), which is
  exactly the kind of context a guide-skill carries and a regex can't.

## Decision log
- 2026-06-13: agent → skill because setup needs the main agent's full repo
  context, triggers at the right moment, and soft-enforcement doesn't bite a
  one-time explicit action. The setter only ever ran inline = already a skill.
- 2026-06-13: NOT a replacement of lint by skill. The skill's output is
  FORM-routed: mechanical invariant → lint (S2-style); methodology → guide-skill.
  Decompose, not replace (preserves the deterministic floor at big-codebase
  scale, where pattern-replication drift is exactly the blog's warning).
- 2026-06-13: review-arch stays an agent (isolated judgment); only setup becomes
  a skill (construction with full context). doc-gardener/dreamer stay agents for
  now (bounded memory/docs scope) — revisit separately, out of scope here.
- 2026-06-13: security review skipped for this plan's gate per the 2026-06-13
  scoping — no change to hooks/`.harness.json`/`.harnessignore`.

## Feedback (from completion gate)
- **review-reliability** (codex) → SATISFIED. One P2: `host-lint.py:5` docstring
  still named the deleted `architecture-setter`. Fixed (→ "the architecture-setup
  skill wires it via `.harness.json` lint_cmd, behind the aggregating
  `.claude/lints/check.py` runner"). A `.py` file the markdown-only grep missed —
  the reviewer caught it.
- **skill-reviewer** → "well-formed, ship it." Polish applied: trimmed the
  duplicated "why not skill-only" paragraph in SKILL.md; added the
  point-`lint_cmd`-at-the-aggregating-runner warning to authoring.md. Skipped the
  cosmetic "currently deferred" reword (accurate as-is).
- **review-arch** → SATISFIED, 0 P1, 2 P2 (both fixed):
  - `authoring.md` lint-skeleton pointer was `../harness-init/…` but the file
    lives one dir deeper (`references/`), so it was off by one `../`. Fixed to
    `../../harness-init/templates/host-lint.py` (SKILL.md's identical-looking
    pointer is correct because it sits a level shallower).
  - SKILL.md step 5 `git add -f .claude/lints/ .claude/skills/ .harness.json` was
    unconditional → a guide-skill-only run would error on the missing
    `.claude/lints/`/`.harness.json`. Made conditional: add only the subtree(s)
    this run authored.
- **Proposed rule (deferred, not applied):** review-arch suggested DESIGN.md §Skills
  require a skill's grounding section to cite its `docs/` grounding path with the
  same discipline S5 enforces on review agents (SKILL.md already does this, lines
  74-76; it's just not a written/lintable rule). Net-new rule, single occurrence,
  out of this plan's scope → recorded here per "feedback-twice → promote"; promote
  if a second skill ungrounds.

## Outcomes & retrospective
- **Shipped:** `architecture-setter` agent → `architecture-setup` skill,
  output FORM-routed. Both FORMs are now proven on a live host (Lingual): the
  `L1` locale **lint** (mechanical) and the `persistence-seam` **guide-skill**
  (methodology). The deterministic floor is preserved; only the *authoring of the
  rules* moved from a dispatched persona to a full-context skill.
- **The gate earned its keep again** (5th consecutive plan with real findings):
  three independent reviewers surfaced four P2s — a stale `.py` docstring two
  searches missed, an off-by-one relative path, and an unconditional `git add`
  footgun — none caught by self-review.
- **Surprise — the codex reviewer was unreliable for this diff.** review-arch
  stalled **twice** at the same step (the `git diff 35deac5` over a ~140-line
  change): the first session was killed mid-grep before its verdict; the re-run
  went silent for 15 min with a frozen output file. The earlier verdicts were
  recoverable from `~/.codex/sessions/` rollout JSONL even though the
  orchestration handles were severed by a compaction. Per CLAUDE.md, fell back to
  a Claude review-arch agent — the completion-gate invariant is "a real
  architecture verdict exists," not "codex produced it," so model-agnostic
  fallback kept the gate honest. Worth noting: codex's background runner appears
  to choke on large `git diff` payloads.
- **Cross-host coupling recurred** (see Surprises) — adding/removing a plugin
  component reddened Lingual's gate via D9 + inventory. The tracker row for a real
  fix (a host-resync helper) is now confirmed three times over.
