---
name: harness-lint
description: Use to run the deterministic gate (taste lints + structure lints + generated-file check + unit tests) and act on failures — run before every commit and whenever docs/plugin structure changed.
---
# Harness lint

Run the gate command recorded in `docs/design-docs/agent-harness.md` —
every harness repo (self-host or scaffolded host) records its exact
`check.py` invocation there.

- GREEN → commit allowed.
- FAIL → every failure line carries a FIX instruction; apply it verbatim,
  rerun. Failures are corrective signals, not suggestions.
- If a rule itself seems wrong (false positive on legitimate work): that is
  harness feedback — record it in the active ExecPlan's Decision log and
  change the rule in the same commit as the work, with a test.
