---
status: draft
last_verified: {{TODAY}}
owner: harness
---
# Core beliefs (golden rules)

Agent-first operating principles — the harness defaults, seeded by
`harness-init`. Rules 1 and 8-10 are **policy, not mechanics**: confirm with
the human which ones this repo adopts, prune or amend, then treat the
survivors as law. Every rule here is enforceable on sight; violating one is
a P1.

1. **No hand-written code.** Humans contribute prompts, reviews, and docs
   feedback — never code. All artifacts are agent-written.
2. **Not in the repo = does not exist.** Knowledge in chat threads or heads is
   invisible to agents. Encode decisions as versioned repo artifacts.
3. **Map, not encyclopedia.** Entry points stay short and stable; depth lives
   behind pointers (progressive disclosure).
4. **Taste is enforced mechanically, not described.** Boundaries via lints and
   structural tests; every lint error carries its own FIX instruction.
5. **Prefer shared utilities over hand-rolled helpers** for invariants that
   must stay centralized.
6. **Parse, don't validate, at boundaries.** External input is parsed into
   known shapes before use; no YOLO data poking.
7. **Internalize dependencies.** Prefer boring tech and the standard library;
   reimplementing a small helper beats importing an opaque package.
8. **Minimal blocking gates, fix-forward.** Only deterministic checks block
   commits. Agent throughput exceeds human attention; cheap fixes beat long
   waits. Non-blocking findings go to the tech-debt tracker.
9. **Struggling agent = harness gap.** Diagnose the missing
   tool/guardrail/doc, encode it, retry. Never just "try harder."
10. **Feedback twice → promote to doc or lint.** The same human correction
    must never be needed a third time.
11. **Tech debt is a high-interest loan.** GC continuously, not in big
    batches.
