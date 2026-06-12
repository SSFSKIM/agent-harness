---
status: active
last_verified: 2026-06-12
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

- [ ] M1 — G1: portable gate references in 7 plugin markdown files + lint S7
      (no `plugin/scripts/` literal in plugin markdown) + test.
- [ ] M2 — A2: enrich docs/PLANS.md with the four upstream rules (done before
      M3 so the host template copies final text).
- [ ] M3 — G2: new seed templates (plans, design, architecture, quality-score,
      product-sense, product-specs/references indexes) + SEEDS update +
      template AGENTS.md Review step + lint D10 (machine-referenced docs
      exist) + tests.
- [ ] M4 — G4: scaffold installs pre-commit hook (idempotent, never
      overwrites) + run scaffold against self-host (installs hook, seeds
      docs/design-docs/agent-harness.md) + register/adapt that page + tests.
- [ ] M5 — G7/A1/A8: harness-init steps for app-verify skill and
      `.claude/skills/`; AGENTS.md template mandatory-skills stub +
      negative-space line; self-host AGENTS.md negative-space line.
- [ ] M6 — A3: `tidy_stop.py` Stop hook (fingerprint-deduped lint subset,
      block-once, fail-open, headless guard) + hooks.json entry + RELIABILITY
      R11 + DESIGN.md gate-hook exception + ARCHITECTURE data flow + tests.
- [ ] M7 — docs sync: QUALITY_SCORE rows, progress/current.md, inventory.
- [ ] M8 — completion gate: self-review → review-arch / review-reliability /
      review-security → iterate → move to completed/.

## Progress log

- 2026-06-12: Plan created from vault gap analysis + repo evidence research.

## Surprises & discoveries

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

## Feedback (from completion gate)

## Outcomes & retrospective
