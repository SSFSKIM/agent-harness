---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [director, worker-runtime, claude, security]
description: The Claude-backed worker runtime (--worker claude) is a config-only drop-in for the Director — it brokers ALL dynamicTools back to the Director so the stock Director needs zero code; LINEAR_API_KEY stays Director-side; it is now monorepo-absorbed under worker-runtime/ and runs classifier-only by deliberate decision.
resource: worker-runtime/README.md
---
# cc-codex-appserver: the Claude worker runtime (verified drop-in)

A field note promoted from session memory. This is the **durable summary**; the
live detail lives in [`worker-runtime/README.md`](../../worker-runtime/README.md)
and [`SECURITY.md`](../SECURITY.md) (the threat-model T-rules), and the build is
covered by [worker-runtime sync is a manual port](worker-runtime-sync-is-manual-port.md).

## What it is

A Claude Agent-SDK worker the Director can dispatch via `--worker claude` (the
default worker stays `codex`). It is a **codex-app-server protocol adapter** over
the Claude SDK, so the Director drives it through the **exact same JSON-RPC stdio
contract** as `codex app-server` — no Director code is specific to it.

## The decisions that hold

- **B2 — broker every dynamicTool.** The server brokers `linear_graphql` and
  `report_outcome` back to the Director over the codex `item/tool/call` request, so
  the **stock Director drives it with zero code changes** (the earlier "companion"
  design was discarded). A true drop-in means the *server* conforms to the
  consumer's protocol, not the reverse.
- **`LINEAR_API_KEY` stays Director-side, never in `worker_env`.** Brokered
  `linear_graphql` runs the executor *in the Director*, which reads the key from
  the repo `.env` and applies the single destructive-mutation guardrail
  (`authority.py`). Putting the key in `worker_env` re-leaks it into the worker —
  do **not**.
- **Monorepo-absorbed.** The adapter is now a first-party in-repo runtime under
  `worker-runtime/{harness,app-server}` (npm-link/PATH retired); the Director
  invokes the in-repo `dist/bin.js` via a `{harness_root}` placeholder.
- **Classifier-only by decision.** For `--worker claude`, the OS sandbox is
  **intentionally disabled** (`worker_runtime_sandbox={"claude":"danger-full-access"}`),
  so the SDK's `permissionMode:auto` model-classifier is the sole boundary. Codex
  is untouched (still OS-sandboxed). This is an **informed-accepted** residual
  recorded in [`SECURITY.md`](../SECURITY.md) — safe only with throwaway creds;
  revisit at a container/VM boundary. The OS-sandbox capability exists but is off.

For the full provenance (the bugs found and fixed along the way, live-verification
runs), see the completed ExecPlans under `docs/exec-plans/completed/` and the
SECURITY T-rules.
