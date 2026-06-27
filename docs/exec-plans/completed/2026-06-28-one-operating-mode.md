---
status: completed
last_verified: 2026-06-28
owner: harness
type: exec-plan
description: Collapse the Director's multi-"mode" surface (watched / lights-out / autonomous / daemon / batch) into ONE operating mode — Director ⟷ Board — with human-presence and run-loop bounds as properties and the pure-code/batch paths as fixtures; daemon becomes the default loop.
base_commit: c52f2187003b700b1a13694a699d3762bbf89299
review_level: standard
---
# One operating mode — Director ⟷ Board

## Goal

After this plan, the Director presents **exactly one operating mode** everywhere a
reader or operator meets it: an always-present **Director** (judging agent)
adjudicating an always-present **Board** (the Linear work queue). The things today
called "modes" are reclassified and renamed:

- **attended vs lights-out** → a *property of the moment* (is the human at the
  keyboard?), not a mode — already one code path (`make_queue_decider`).
- **daemon vs batch/once** → the **daemon (always-on) loop is THE mode and the
  default**; `--batch`/`--once` survive only as explicitly-labeled dev/test/CI
  *fixtures*.
- **`--autonomous` (pure-code `autonomous_decide`)** → a *no-judge CI/`--mock`
  fixture*, never advertised beside the real mode.

Definition of done (observable):
1. `python3 -m director.orchestrator --team T` (real run, no loop flag) runs the
   **always-on daemon** — `director.status` reports `mode=daemon`.
2. `python3 -m director.orchestrator --team T --mock` runs **bounded** (drains the
   in-memory board and exits — does NOT loop forever).
3. `--batch` runs the multi-pass drain-and-exit loop; `--once` runs a single pass;
   `--autonomous` selects the no-judge decider — each documented as a fixture.
4. `grep -rInE "three modes|the third mode" .claude docs` returns **nothing** in
   governed docs; DIRECTOR.md presents "one mode + properties + fixtures".
5. `docs/adr/0007-one-operating-mode.md` exists, is indexed, and refines ADR 0002/0003.
6. `python3 plugin/scripts/check.py` is GREEN; the full unittest suite passes.

## Context

A novice needs these to execute from the plan alone:

- **The conceptual arc already in the repo.** `docs/adr/0002-graduated-autonomy.md`
  (Director: per-turn judge → exception-handler) and
  `docs/adr/0003-lights-out-director.md` ("**split the one mode bit into two
  independent axes** — is a Director present? × is the human present?"; rebinds
  "autonomous" to *no-human, Director-only*; demotes the pure-code decider to a
  no-agent niche). This plan **completes** that arc by removing the residual
  multi-mode *framing* (and aligning the CLI to it). ADR 0007 (M1) is the decision
  record; it refines — does not rewrite — 0002/0003 (ADRs are immutable).
- **The two orthogonal axes + the niche, in code:**
  - *Run-loop axis* — `director/orchestrator.py`: `run_forever` (daemon, always-on,
    exp-backoff), `run_until_drained` (multi-pass batch), `run_once` (single pass).
    Selected in `orchestrator.main` (~L1375–1392): `--daemon`→forever,
    `--once`→once, else `run_until_drained` (today's default).
  - *Agency axis* — decider chosen in `orchestrator.main` (~L1303):
    `decider.make_queue_decider` (a Director answers turn-ends; **attended and
    lights-out are the SAME path** — only *who* answers differs) vs
    `decider.autonomous_decide` (pure code, no judge), selected by
    `--autonomous OR --mock`.
- **The current mis-framing in docs:** `.claude/DIRECTOR.md` §6 is titled "The
  three modes (who answers turn ends)"; §12 calls daemon "the third mode"; §5/§13
  describe attended/lights-out as distinct modes; scattered "across modes / every
  mode / watched-mode only" lines. `docs/DIRECTOR_RUNBOOK.md` repeats it (quick-ref
  L33, §8 launch L215–223, §9 L356–360, L420 "attended/lights-out/no-agent modes").
- **`--mock` already special-cases behavior** in `orchestrator.main` (decider,
  `install_skills`, `tools`, hooks) — "mock ⇒ bounded loop" is one more fixture
  override in the same place, not a new concept.
- **Posture is identical across all of today's "modes"** (SECURITY T11: shared
  `on-request` + `auto_review` + network). This plan does **not** touch posture or
  any security surface — the mode collapse is orthogonal to it.
- Brainstorm that produced this plan: user wants "one Mode. Always-present
  Director, and Board." Scope chosen: **reframe + align CLI** (not docs-only; not
  delete-the-mechanisms). Daemon = the literal default (user-approved).
- Method/format: `docs/PLANS.md` (this template), `docs/KNOWLEDGE_FORMAT.md`
  (frontmatter), `docs/design-docs/agent-harness.md` (gate = `python3
  plugin/scripts/check.py`).

## Approach (self-generated alternatives)

- **A — Docs-only reframe.** Rewrite DIRECTOR.md/runbook/ADR to "one mode"; leave
  the CLI (`--daemon`/`--once`/`--autonomous`) untouched. *Tradeoff:* zero code
  risk, but the interface still advertises the old multi-mode surface — the muddle
  the user objects to survives in the CLI. Rejected (incomplete).
- **B — Reframe + align CLI (chosen).** Make the daemon the default loop and
  `--mock` bounded; demote `--autonomous` to a documented fixture; keep
  `--batch`/`--once` as labeled fixtures; then rewrite the docs to match.
  *Tradeoff:* a real (intended) behavioral change to the CLI default + modest test
  churn (concentrated in `test_director_config.py`), but resolves the muddle in
  BOTH narrative and interface without deleting load-bearing mechanisms.
- **C — Reframe + retire paths.** Additionally delete `run_until_drained`/`run_once`
  and standalone `--autonomous`. *Tradeoff:* truly singular interface, but rewrites
  a large, healthy test surface (27 `run_until_drained` + 14 `run_forever` refs)
  and removes useful bounded-run/CI mechanisms for naming purity. Rejected (over-reach
  vs. "all are not needed" — which is about *framing*, not *capability*).
- **Chosen: B.** It is the faithful completion of ADR 0002→0003 and exactly the
  user-approved scope. The daemon-default's only sharp edge — an unbounded loop over
  the offline mock board — is removed by the "mock ⇒ bounded" rule (mirrors existing
  `--mock` special-casing), which also minimizes test churn.

## Assumptions & open questions (self-interrogation)

- **Assumption:** "Board" = the Linear work queue the Director polls (not the
  dashboard view). *If wrong:* terminology in the ADR/docs needs a noun swap; no
  code impact. (Confirmed by the codebase's consistent usage; low risk.)
- **Assumption:** the Daemonized-Claude-Code *runtime* (what makes lights-out run
  with no human) remains a **separate track** (ADR 0003) and is NOT built here —
  this plan only fixes the *model/framing + CLI*, which is the groundwork that
  runtime consumes. *If wrong:* out of scope regardless; a new plan.
- **Assumption:** retaining `--daemon` as an accepted-but-now-redundant alias (it
  still selects the daemon, which is the default) is preferable to a hard removal,
  to avoid breaking any existing invocation/runbook muscle-memory for one cycle.
  Resolved autonomously: **keep `--daemon` as a documented deprecated alias**;
  remove it in a later cleanup once the runbook + any scripts are updated.
- **Open → resolved autonomously:** *Should `--mock` default to `--batch` or
  `--once`?* → **`run_until_drained` (batch, multi-pass)**, because mock scenarios
  exercise the DAG-drain (blocked tickets unblocking across passes); `--once`
  remains available when a single pass is wanted. Recorded in Decision log.
- **Open → resolved autonomously:** *Keep the status `mode` field?* → **Yes**, but
  reframed: it is a runtime *heartbeat label* (`daemon` for the always-on loop,
  `batch` for the bounded fixture, `None` when not a polling loop), not a
  user-chosen "mode." No schema change; only doc/comment wording.
- **Taste/Style escalation:** none expected — the one taste call (daemon = literal
  default) was settled with the human in the brainstorm. Any *new* product-direction
  fork that surfaces mid-execution → escalate per PRODUCT_SENSE.md.

## Milestones

- **M1 — The decision record (ADR 0007).** *Scope:* author
  `docs/adr/0007-one-operating-mode.md` — the durable decision that there is one
  operating mode (Director ⟷ Board), with human-presence and run-loop bounds as
  *properties* and the pure-code/batch paths as *fixtures*, and daemon as the
  default loop (with the "mock ⇒ bounded" refinement). It states the
  taxonomy→property/fixture mapping, the CLI consequences (M2), and explicitly
  **refines** ADR 0002/0003 (adds a "refined by 0007" pointer to each, registers
  0007 in `docs/adr/index.md`, cross-links 0002/0003 + DIRECTOR.md + this plan).
  *At end:* the ADR exists, is indexed, and the graph links resolve. *Command:*
  `python3 plugin/scripts/check.py` (lints: frontmatter, index registration D8,
  link integrity) + `python3 plugin/scripts/nav.py backlinks docs/adr/0007-one-operating-mode.md`.
  *Acceptance:* check.py GREEN; `nav.py` shows 0007 linked from the index and
  cross-referenced by/with 0002/0003.

- **M2 — CLI alignment (code + tests).** *Scope:* in `director/orchestrator.py`
  `main`: make the loop default `run_forever` (daemon) for real runs; add `--batch`
  → `run_until_drained`; keep `--once` → `run_once`; make `--mock` imply the bounded
  (batch) loop (one more `--mock` override beside the existing decider/skills/tools
  ones); keep `--daemon` as an accepted, documented-deprecated alias of the default.
  Reframe the `--autonomous` help text to "no-judge CI/`--mock`/detached fixture —
  NOT a mode" (the decider-selection comment ~L1303 too). Touch `director/run.py`
  (`--autonomous` help, ~L816), `director/config.py` (the "Only used by `--daemon`"
  comments on `poll_interval_s`/`backoff_*` → "the default always-on loop"), and
  `director/status.py` (the `mode`/`polled()` heartbeat docstrings L99–103, L219–226
  → "heartbeat label, not a chosen mode"). Update the affected `main`-level tests in
  `tests/test_director_config.py` (the L625–711 default-loop assertions: a `--mock`
  call must now assert the **bounded** loop; a no-`--mock` no-flag call must assert
  **`run_forever`** is selected) and **add** a test that a bare real run selects
  `run_forever` and a `--mock` run selects the bounded loop. *At end:* the CLI
  default is the daemon for real runs and bounded for mock. *Command:*
  `python3 -m director.orchestrator --team T --mock --mock-scenario report` (must
  terminate); `python3 -m director.orchestrator --help` (shows the new framing);
  `python3 -m unittest discover -s tests -q`. *Acceptance:* the mock run exits (no
  hang); `--help` shows daemon-as-default + `--batch`/`--once`/`--autonomous` as
  fixtures; the new + updated tests pass; check.py GREEN.

- **M3 — Doc reframe (DIRECTOR.md + runbook).** *Scope:* rewrite `.claude/DIRECTOR.md`
  — retitle/rewrite §6 ("The three modes" → "One mode: Director ⟷ Board — and its
  properties"); fold §5/§13 so attended and lights-out read as the **same loop**
  differing only in human presence (lights-out's §13 *procedure* stays — it is the
  human-absent property's behavior, not a separate mode); rewrite §12 so the daemon
  is *the mode and default* and `--batch`/`--once` are fixtures; fix the scattered
  "across modes / every mode / watched-mode only / the third mode" lines. Rewrite
  `docs/DIRECTOR_RUNBOOK.md` — quick-ref (L33), §8 launch (L215–223), §9 (L356–360),
  and the L420 "attended/lights-out/no-agent modes" line — to the one-mode framing
  and the new flags. Light touch on `docs/adr/index.md` line for 0003 if its
  "no-agent niche" phrasing needs a forward-pointer (it gets the 0007 entry from M1).
  *At end:* every governed doc presents one mode. *Command:*
  `grep -rInE "three modes|the third mode" .claude docs` (expect: nothing in
  `.claude/DIRECTOR.md`/runbook; historical completed exec-plans/specs may retain
  it as a record — they are point-in-time and out of scope) + `python3
  plugin/scripts/check.py`. *Acceptance:* the grep is clean for the authoritative
  docs; check.py GREEN; a read-through confirms no remaining peer-mode language.

## Progress log
- [x] (2026-06-28) Plan created; base_commit recorded; creation-time self-review done.
- [x] (2026-06-28) M1 — ADR 0007 written, indexed (D8), refines-pointers added to 0002/0003; check.py GREEN.
- [x] (2026-06-28) M2 — orchestrator.py daemon-default + `--mock`⇒bounded + `--batch` + `--autonomous`/`--daemon` reframe; run.py/config.py/status.py comment reframes; 6 new loop-resolution tests + 2 repointed. Behavioral: `--mock` drains & exits (exit 0); full director suite 615 OK; check.py GREEN.
- [x] (2026-06-28) M3 — DIRECTOR.md §5 retitled, §6 rewritten ("one mode + properties + fixtures"), §12/§13 reframed (daemon=default; lights-out=property), §9/§11 scattered lines fixed; DIRECTOR_RUNBOOK quick-ref + §8/§9 + see-also reframed (bare command = daemon; --batch/--once fixtures; ADR 0007 linked). Acceptance grep clean (only ADR 0007 quotes the old titles); check.py GREEN.

## Surprises & discoveries
- (2026-06-28) `--mock` defaulting to the daemon would hang tests/quick-runs over the
  in-memory board → the "mock ⇒ bounded" rule is load-bearing, not cosmetic.

## Decision log
- 2026-06-28: Scope = "reframe + align CLI" (Approach B), daemon = literal default —
  user-approved in the originating brainstorm.
- 2026-06-28: `--mock` implies the bounded (`run_until_drained`) loop — mirrors the
  existing `--mock` special-casing and prevents an unbounded loop over the offline board.
- 2026-06-28: Keep `--daemon` as an accepted, documented-deprecated alias (now == the
  default) rather than a hard removal, to avoid breaking existing invocations this cycle.
- 2026-06-28: Keep the status `mode` heartbeat field; reframe its meaning (label, not
  a chosen mode). No schema change.

## Feedback (from completion gate)
- **review-spec-compliance: SATISFIED.** All 6 DoD items verified; scope honored (only specified
  files touched; `--batch` the one new flag, specified in M2). Full suite 851 tests OK.
  - **P2 (found + FIXED inline):** the `mode="batch"` heartbeat label was documented (ADR 0007 +
    `director/status.py` docstrings) but never emitted — `run_until_drained`/`run_once` call
    `status.wave()`, not `polled()`, so bounded fixtures keep `mode=None`. Fixed the ADR line +
    both status.py docstrings to state bounded fixtures emit no heartbeat (`mode=None`), matching
    the "no schema change" decision. Doc-only; no behavioral impact.
  - **Note (acceptance wording):** M1's acceptance cited `nav.py backlinks` to show the 0002/0003
    cross-refs, but `nav.py` indexes only Markdown `[text](path)` links, not `[[wikilinks]]` (the
    ADR cross-ref convention). The cross-refs genuinely exist and resolve (check.py link-integrity
    GREEN); the right tool to demonstrate wikilink ADR cross-refs is check.py link-integrity, not
    `nav.py backlinks`. Recorded as a one-off learning (not deferred work).
- **review-code-quality: SATISFIED.** Loop resolution is a clean resolve-then-dispatch block, no
  dead code; incidentally fixes the latent `s` settings-dict shadow; the new tests are
  fail-before/pass-after. P2s: (a) `--once` vs `--batch` precedence was unspecified/untested →
  **FIXED inline** (added `test_once_wins_over_batch` + spelled the total order in the `--batch`
  help). (b) `polled(mode="daemon")` keyword is now vestigial (no caller overrides) — pre-existing,
  taste-only; left as-is (removing the param is out of this plan's "no schema change" scope).
- **review-arch: SATISFIED.** Taxonomy coherent; refines-not-supersedes handled correctly; no
  layer-law/portability issues. P2s: (a) docs said "`--mock` **implies** `--batch`" but code makes
  it only the *default* (explicit `--daemon` wins → `--mock --daemon` runs the daemon) →
  **FIXED inline** (softened the wording to "defaults to … an explicit loop flag still wins" + the
  total order, in the `--batch` help / ADR 0007 / DIRECTOR.md §12; added
  `test_mock_daemon_explicit_flag_wins_over_mock_default`). (b) DIRECTOR.md §6 called the run loop
  "a second property" — contradicts the taxonomy (the daemon IS the mode) → **FIXED inline**
  ("the other axis … daemon IS the mode"). Proposed rule (run-loop as a `director.loop` config key)
  → **tracked** in tech-debt-tracker (out of scope, pre-existing).
- **review-reliability: SATISFIED.** Default flip is correctly guarded (`--mock`⇒bounded prevents
  CI hangs; 616 director tests pass under a 300s timeout, no hang), signal/drain unchanged, heartbeat
  `mode` change is a no-op for readers (none consume it). P2s: (a) ADR "Live risk" overstated the
  Ctrl-C mitigation given open tech-debt **F4** (draining daemon orphans worker children, burning
  tokens) → **FIXED inline** (ADR risk section now cites F4; F4's tracker row annotated that the
  daemon-default elevates its blast radius). (b) runbook §8 step-1 headline command was the bare
  (now-unbounded) daemon while the nav row promised "bounded … then exit" → **FIXED inline** (§8
  command now leads with `--once`, the canary-validation form). Proposed R-rule (draining daemon must
  reap its worker process tree) → **tracked** under F4.

## Outcomes & retrospective

**Shipped.** One operating mode — Director ⟷ Board — now presented consistently across the
decision record (ADR 0007, refining 0002/0003), the code (`director/orchestrator.py`: daemon is
the default loop, `--mock`⇒bounded, `--batch` added, `--once`/`--daemon`-alias kept,
`--autonomous` reframed as a fixture; comment/heartbeat reframes in run.py/config.py/status.py),
and the docs (`.claude/DIRECTOR.md` §5/§6/§12/§13 + scattered lines; `DIRECTOR_RUNBOOK` quick-ref
+ §8/§9 + see-also). Human-presence (attended/lights-out) and run-loop bounds are now *properties*;
the pure-code/batch paths are *fixtures*; no "N modes" framing remains in the authoritative docs.

**Verified.** `check.py` GREEN; full suite 851 tests OK (8 new/updated loop-resolution tests).
Behavioral: `python3 -m director.orchestrator --team T --mock --mock-scenario report` drains and
exits cleanly (exit 0 — the load-bearing `--mock`⇒bounded guard); `--help` shows the one-mode
framing. M1/M3 are docs (no separate runnable surface → N/A beyond the grep acceptance).

**Reviews.** All four SATISFIED (spec-compliance → code-quality → arch + reliability), 0 P1.
Six P2s: four FIXED inline (never-emitted `mode=batch` label; `--mock` "implies" overclaim +
precedence test; DIRECTOR.md §6 "second property" slip; ADR risk understating open F4 + runbook §8
unbounded headline); two TRACKED (F4 teardown blast-radius elevated by the daemon-default; run-loop
as a `director.loop` config knob). One taste note (vestigial `polled(mode=)` param) left as-is.

**Retrospective.** The "modes" muddle was overwhelmingly *naming*: two of the user's three points
(human-presence as a property; autonomous as a non-production fixture) were already true in the code
(`make_queue_decider` is one path; `autonomous_decide` is `--mock`/CI-gated) — only mis-labeled in
docs. The one genuine behavior change, daemon-as-default, was only safe because `--mock`⇒bounded
keeps the offline/CI path from looping forever. Adversarial review earned its keep: it caught the
doc-vs-code "implies" drift, an internal taxonomy slip in the authoritative guide, and an overstated
risk mitigation — none of which broke the gate, all of which would have shipped reader-confusion.
