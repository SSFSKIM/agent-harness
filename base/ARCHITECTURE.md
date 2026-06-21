# ARCHITECTURE.md

Codemap + invariants for {{PROJECT}}. Read this before modifying source.
Grounds the review-arch persona together with `docs/DESIGN.md`, and the gate
requires this file to exist (lint D10) — so this seed is a **placeholder**.

**Do not hand-fill a generic skeleton here.** This file is authored by the
`architecture-setup` skill (harness-init step 7), which reads {{PROJECT}}'s real
source and derives the content from it. Run that skill to replace this
placeholder. What it produces:

- **Bird's-eye view** — what the repo does, primary inputs/outputs, runtime shape.
- **Code map** — the real top-level source layout ("where is the thing that does
  X?" / "what does this thing do?").
- **Boundaries & layer law** — public/internal/generated/external surfaces and
  the allowed dependency direction (including the absence rules: which layers
  must NOT import which).
- **Architectural invariants** — numbered rules reviews cite by number; many are
  absences ("X never imports Y", "runtime state never lives in `docs/`").
- **Cross-cutting concerns** and the **few end-to-end data flows**.
- **Enforcement table** (Invariant → FORM → Enforced-by → Why) — routing each
  invariant to a `.claude/lints/` check, a guide-skill, a review persona, or
  fix-forward.

The invariants are {{PROJECT}}'s own — the skill derives them from this repo's
source, never by importing the harness's universal app-code rules (there are
none; see ARCHITECTURE invariant 7 in the harness self-host docs).
