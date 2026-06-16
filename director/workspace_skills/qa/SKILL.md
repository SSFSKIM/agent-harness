---
name: qa
description:
  Self-QA an implementation before opening a PR — spec-compliance + code-quality
  self-review and task-specific tests (smoke/unit always, end-to-end via
  playwright/playwright-cli for UI), then write a PR self-description the merger
  reads. Use as an IMPL worker before report_outcome(done).
---

# QA — self-verify your work before the PR

You are an IMPL worker finishing a ticket. QA is **your** responsibility, not a gate:
nothing blocks you from declaring done, and the PR-merger does only a thin integration
check later. So the real verification happens HERE. Do it honestly — a weak self-QA
that the merger can't catch ships a bug.

## 1. Self-review (spec-compliance + code-quality)

- **Spec-compliance:** re-read the ticket and the spec/ExecPlan it builds. Does what you
  built do exactly that — no more (scope creep), no less (missing acceptance)? Walk the
  spec's acceptance criteria one by one; each should map to something you can demonstrate.
- **Code-quality:** match surrounding style and conventions; no dead code, no TODOs left
  for "later", no debug prints; errors handled where they can actually happen (not
  speculative). Read your own diff as a reviewer would.

## 2. Task-specific tests — author and run them

The host gate (`check.py` / the host's `test_cmd`) covers unit/lint; that is the floor,
not the ceiling. Add tests for **what this ticket changed**:

- **Smoke / unit (always):** the new behavior has a test that FAILS before your change
  and PASSES after. Prove the change, not just "it imports".
- **End-to-end (when the change is user-facing / UI / a flow):** use the `playwright`
  and `playwright-cli` skills. A worker runs headless in its sandbox and CAN drive a
  real browser (Chromium via playwright-cli) — navigate the flow, assert on the DOM /
  outcome. Tie each e2e to a spec acceptance criterion.
- **Graceful fallback:** if `playwright-cli` or a browser is not available on this host
  (a ported host may lack it), do NOT fail — note it in the PR body and cover the flow
  with the strongest smoke/unit test you can instead. Never fabricate a passing e2e.

Run everything; keep the host gate GREEN. If a test reveals a real defect, fix it and
re-run before the PR.

## 3. PR self-description — the handoff the merger reads

Open the PR with the `push` skill. The PR body is the merger's (and a human's) context;
fill these fields in prose:

```
## What
<the spec/feature/ticket this implements — link the spec/ExecPlan>
## Reviews
<spec-compliance: pass/notes · code-quality: pass/notes>
## Tests
<smoke/unit: what + result · e2e/playwright: what + result, or "fallback: <why> + smoke covered">
## Risks / notes
<anything the merger should know — migrations, follow-ups, deferred items>
```

A clean, specific self-description lets the merge stay thin. Vague or empty ("did the
work, tests pass") defeats the trust model — be concrete.

## 4. Then finish

Only after 1–3: `report_outcome(status="done", reason="…")`. If QA surfaced something you
cannot resolve (a real blocker, or a product/taste decision), do NOT force done — end the
turn asking, or report blocked/needs_human per the turn protocol.
