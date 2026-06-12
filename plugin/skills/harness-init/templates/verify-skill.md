---
name: verify
description: Use before every commit and after any change to run THIS repo's full verification order in the right sequence with the right barriers. Encodes the build/test commands so sessions never guess them.
---
# verify — this repo's verification order

<!-- FILL: name the source of truth for commands (Makefile, package.json
scripts, justfile, …) and say "do not invent ad-hoc commands". -->

Run these in order; stop at the first failure and fix forward.

## 1. Lint + typecheck (fast)
- <!-- FILL: the lint/typecheck command(s), e.g. `npm run lint`, `ruff check`. -->

## 2. Build (if the host has a build step)
- <!-- FILL: the build command + what it produces; note any output dir that
  must never be hand-edited. Omit this section if there is no build. -->

## 3. Tests
- <!-- FILL: the default test command and what it covers. -->
- <!-- FILL: deeper/optional suites and WHEN to run each (emulator, e2e,
  integration) + their preconditions (servers running, Java, etc.). -->
- <!-- FILL: how to run a single test file. -->

## 4. Harness doc gate (before commit)
- Run `.git/hooks/pre-commit` (the recorded gate: lint_structure + lint_docs).
  Must be GREEN. Failures carry their own FIX — the `harness-lint` skill
  interprets them. `--no-verify` only for emergencies; fix forward right after.

## Barriers
<!-- FILL: the dependency order — e.g. tests need a build; e2e needs running
servers; the doc gate is independent. State what must be green before commit. -->
