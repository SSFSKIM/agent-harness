# Authoring contracts

## Lint (mechanical invariant)

Start from `../harness-init/templates/host-lint.py`. Contract:
- Pure stdlib; decide from files only (no network, no untrusted input).
- Print one line per violation: `FAIL <rule-id> <path>: <problem> FIX:
  <imperative instruction>`. The FIX text is the product — write it for an agent
  that acts on it verbatim.
- Exit 1 on any violation, 0 when clean.
- Scope tightly (allowlist the sanctioned location) so there are no false
  positives. Fail loud if the symbol/config it keys off is absent — a vacuous
  pass silently disables the invariant.

Wire it: add a `.claude/lints/check.py` runner that runs every sibling
`.claude/lints/*.py` and exits nonzero if any fails, then set
`<root>/.harness.json` → `{"lint_cmd": "python3 .claude/lints/check.py"}`. The
gate runs it as the `host-lint` step on every commit.

## Guide-skill (methodology)

Author `.claude/skills/<name>/SKILL.md`:
- Frontmatter `name` + `description`. The description is **third-person** and
  names the trigger phrases / moments ("when changing a persistence seam",
  "before adding a school feature") — that is what loads the skill at the right
  time.
- Body in **imperative** form: when it applies, what to read first, the safe
  sequence, the judgment calls and their criteria, what NOT to do.
- Keep it lean (~1.5–2k words); push long material into the skill's own
  `references/` (progressive disclosure).
- Wire it into AGENTS.md "Mandatory skill usage" with its trigger + skip
  conditions.

A guide-skill encodes a methodology a lint cannot: it shapes how the agent
approaches the work, leaving room for judgment, while the trigger ensures it
loads when relevant.

## Record (ARCHITECTURE.md)

Add or refresh an **Enforcement (invariant → FORM)** section: a table mapping
each invariant to its FORM (lint / guide-skill / judge / persona / fix-forward)
with a one-line why, plus the layer law. The next session — and the next setup
run — reads this to know which medium holds each invariant.
