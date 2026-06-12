---
status: completed
last_verified: 2026-06-13
owner: harness
base_commit: 3744c4e8bc175cd82e8d0a43cd1841713428fb66
---
# Portability hardening + upstream adoptions (gap-analysis must-fix)

## Goal

A vault-side audit (OpenAI harness-engineering blog vs this repo, plus a survey
of openai/codex, openai/openai-agents-js, openai/apps-sdk-ui) found that the
machine breaks when ported and that several cheap upstream practices are
missing. After this plan, all of the following are observable:

1. `grep -rn "plugin/scripts/" plugin/ --include="*.md"` prints nothing, and a
   new lint (S7) keeps it that way — plugin markdown no longer assumes the
   self-host layout, so skills/agents work in ported hosts.
2. `scaffold.py` into an empty repo seeds every doc the machine reads
   (PLANS, DESIGN, ARCHITECTURE, QUALITY_SCORE, PRODUCT_SENSE, agent-harness
   page, product-specs/references indexes), and a new lint (D10) fails any
   harness repo missing one. A fresh host's review gate is functional
   out of the box.
3. `git commit` is mechanically gated: scaffold installs `.git/hooks/pre-commit`
   running the check gate (self-host repo included). The gate stops being an
   honor-system instruction.
4. Ending a session with a lint-dirty tree produces corrective FAIL/FIX output
   via a Stop hook (`tidy_stop.py`) that blocks **at most once per distinct
   dirty-tree fingerprint** (no block loops), fails open, and is
   headless-guarded.
5. `docs/PLANS.md` carries four upstream ExecPlan quality rules (demonstrable
   behavior, define terms, prose-first, PoC milestones, autonomous ambiguity
   resolution) — verbatim adopted from openai-agents-js PLANS.md.
6. `harness-init` covers two previously missing porting steps: app
   boot/verification skill and instance-layer skills (`.claude/skills/`);
   AGENTS.md templates carry the Review gate step and a negative-space rule
   ("commands not listed are out of scope").

## Context (self-contained)

- **G1 (P1)**: execplan/harness-lint/docs-tree/garden/dream SKILL.md and
  doc-gardener/dreamer agents hardcode `python3 plugin/scripts/check.py` — a
  path that only exists in self-host. Ported hosts keep the plugin outside the
  repo (`claude --plugin-dir`), so every gate call breaks. Fix: all plugin
  markdown points to the gate command **recorded in
  `docs/design-docs/agent-harness.md`** (seeded per-repo by scaffold; self-host
  gets one too in M4).
- **G2 (P1)**: scaffold.py SEEDS lacks docs/PLANS.md (execplan skill reads it),
  ARCHITECTURE.md + docs/DESIGN.md (review-arch grounding 1:1 — without them
  the persona may not enforce anything), docs/QUALITY_SCORE.md (gate step 5,
  doc-gardener step 4), docs/PRODUCT_SENSE.md, product-specs/references
  indexes. Lint only requires AGENTS.md, so a scaffolded host is GREEN while
  functionally lame. Template AGENTS.md operating model also lost the Review
  step (has Write-back where self-host has Review).
- **G4**: "check.py GREEN before commit" is prose; `.git/hooks` is empty.
  Blog enforces via CI. Local equivalent: pre-commit hook (still honoring
  minimal-gates: the hook runs only the deterministic gate).
- **G7**: harness-init has no checklist item for a host app boot/verify skill.
- **A2**: our PLANS.md (43 lines) mirrors the structure of the upstream spec
  (openai-agents-js/PLANS.md, 146 lines) but lacks its quality rules.
- **A3**: openai-agents-js runs a `.codex/hooks` Stop hook that lints touched
  files at session end, fingerprints the diff (SHA256) for idempotence, and
  blocks with corrective output. Hook contract is the same as Claude Code's.
- **A1-lite/A8**: upstream AGENTS.md files wire mandatory repo-local skills
  and declare negative space ("Ignore all other script commands").

## Milestones

- [x] M1 — G1: portable gate references in 7 plugin markdown files + lint S7
      (no `plugin/scripts/` literal in plugin markdown) + test.
- [x] M2 — A2: enrich docs/PLANS.md with the four upstream rules (done before
      M3 so the host template copies final text).
- [x] M3 — G2: new seed templates (plans, design, architecture, quality-score,
      product-sense, product-specs/references indexes) + SEEDS update +
      template AGENTS.md Review step + lint D10 (machine-referenced docs
      exist) + tests.
- [x] M4 — G4: scaffold installs pre-commit hook (idempotent, never
      overwrites) + run scaffold against self-host (installs hook, seeds
      docs/design-docs/agent-harness.md) + register/adapt that page + tests.
- [x] M5 — G7/A1/A8: harness-init steps for app-verify skill and
      `.claude/skills/`; AGENTS.md template mandatory-skills stub +
      negative-space line; self-host AGENTS.md negative-space line.
- [x] M6 — A3: `tidy_stop.py` Stop hook (fingerprint-deduped lint subset,
      block-once, fail-open, headless guard) + hooks.json entry + RELIABILITY
      R11 + DESIGN.md gate-hook exception + ARCHITECTURE data flow + tests.
- [x] M7 — docs sync: QUALITY_SCORE rows, progress/current.md, inventory.
- [x] M8 — completion gate: self-review → review-arch / review-reliability /
      review-security → iterate → move to completed/.

## Progress log

- 2026-06-12: Plan created from vault gap analysis + repo evidence research.
- 2026-06-12: M1 done — 7 plugin markdown files now point to the gate via
  docs/design-docs/agent-harness.md; lint S7 + test added. Transient state:
  self-host gets its agent-harness.md page in M4 (backtick references are not
  D5 links, so the gate stays green meanwhile).
- 2026-06-12: M2+M3 done — PLANS.md quality rules; 5 new seed templates +
  product-specs/references indexes; lint D10; template AGENTS.md Review step.
  Pulled the self-host agent-harness.md seeding forward from M4 into M3
  because D10 would otherwise fail self-host (decision: D10 and the page must
  land in the same commit). Scaffold run on self-host doubled as a live
  idempotency check: 21 SKIP, 1 CREATE.
- 2026-06-12: M4-M7 done. The M4 commit itself was the first through the new
  pre-commit hook (observable per Goal 3). tidy_stop tests passed first run
  (5/5: block-once, fail-open, headless guard, fix-then-green, non-git).
  QUALITY_SCORE gained porting + stop-tidy rows.

## Surprises & discoveries

- D10 forced an ordering constraint discovered mid-build: the self-host repo
  itself lacked docs/design-docs/agent-harness.md, so the lint and the page
  had to land in one commit (pulled forward from M4 to M3).
- `hashlib` was missing from the S1 import allowlist — first allowlist
  addition since v1; justified for tree fingerprinting and recorded below.

## Decision log

- 2026-06-12: Gate-command indirection goes through
  `docs/design-docs/agent-harness.md` (one pointer per repo, seeded by
  scaffold) rather than skill self-location — personas have no file path of
  their own to self-locate from, and one indirection serves all seven files.
- 2026-06-12: Stop-tidy loop prevention uses dirty-tree fingerprinting (block
  at most once per distinct state) instead of the undocumented
  `stop_hook_active` field — our hooks reference digest does not list that
  field, and the fingerprint is deterministic and self-limiting.
- 2026-06-12: Stop-tidy blocks via exit 2 + stderr (digest-verified contract)
  running the fast deterministic subset (lint_structure, lint_docs,
  gen_inventory --check) — unittest stays out of the hook for latency.
- 2026-06-12 (gate iteration): a ported host's exact gate command is recorded
  in `.git/hooks/pre-commit` itself — unversioned and machine-local — not in
  a versioned doc, because a versioned doc cannot hold a machine-local
  absolute path without breaking on every clone (resolves arch P1 and the
  instance-path-hygiene concern jointly). Versioned docs only point at it.

## Feedback (from completion gate)

- review-arch: NOT SATISFIED — P1: the template gate line used literal
  `<plugin>` placeholders that no FILL grep enforces; the gate-command
  indirection dead-ended in ported hosts. Fixed: the pre-commit hook IS the
  recorded gate command (machine-local truth in an unversioned file); the
  versioned page points at it; scaffold now REWRITES ours-marked hooks
  (making "rerun scaffold to refresh" true — also arch P2#1). P2 fixed:
  garden/dream scoped `git add` per DESIGN.md. P2 deferred: components-table
  duplication (conflicts with D9 coverage — tracker row).
- review-reliability: SATISFIED — P2s fixed anyway: crash-vs-FAIL
  distinction (tooling crashes log + never block), per-check timeout 30s
  (fits the 120s hook budget), atomic fingerprint write (os.replace),
  headless check inside try, R11 wording narrowed, activation sentinel
  (no-op in non-harness repos — was a proposed rule). Rest → tracker rows.
- review-security: SATISFIED — P2 fixed: DATA-guard preamble on tidy stderr
  (T7 transitive channel) + D4 value clamp; proposed-T8 fixed now via
  shlex.quote in the generated pre-commit. Deferred: symlink-refusal,
  T7-extension codification (tracker rows).
- review-arch re-verdict (2026-06-13): SATISFIED — walked the pointer chain
  cold in a scaffolded temp host: plugin markdown → agent-harness.md →
  `.git/hooks/pre-commit` → executable GREEN gate, zero placeholders. Two
  residual P2s (harness-lint wording claiming hosts inline the invocation;
  template Load line's `<path-to-agent-harness>` placeholder) fixed in the
  completion commit.

## Outcomes & retrospective

All six Goal behaviors are observable: (1) `grep -rn "plugin/scripts/"
plugin/ --include="*.md"` prints nothing and S7 enforces it; (2) a fresh
scaffold seeds all eight machine-read docs and D10 fails any repo missing
one (proved by the fresh-host-lint-green test running lint_docs whole);
(3) commits are hook-gated — the M4 commit was the first through it, every
later commit shows the gate banner; (4) tidy_stop blocks once per dirty
fingerprint with FAIL/FIX + DATA guard (5+1 tests); (5) PLANS.md carries the
upstream quality rules; (6) harness-init gained instance-skills/app-verify
steps and templates carry Review + negative-space.

Retrospective. The gate caught a real P1 for the second plan running — this
time a *design* hole (placeholder indirection) rather than a code bug, which
self-review and 52 green tests both missed; persona review pays for itself
precisely where lints cannot look. Lesson promoted into the build style:
machine-local truths (absolute paths) belong in unversioned artifacts that
scaffold can rewrite; versioned docs hold only pointers. Reliability's
"checks crash ≠ repo fails" distinction is a pattern the imprint worker
should adopt too (tracker row exists). Source analysis (vault gap analysis +
OpenAI public-repo evidence) made this the fastest plan yet: every milestone
was specified before the session started.
