# worker-runtime/ — the Claude worker for the Director

This directory is the **Claude Agent-SDK worker runtime** the Director can dispatch
via `--worker claude` (the default worker stays `codex`). It is a codex-app-server
protocol adapter over the Claude Agent SDK, so the Director drives it through the
exact same JSON-RPC stdio contract it uses for `codex app-server` — no Director code
is specific to it.

Two packages (npm `file:` siblings):

| Package | npm name | Role |
|---|---|---|
| `harness/` | `cc-harness` | Config/wrapper layer over `@anthropic-ai/claude-agent-sdk` (resolveOptions, sandbox, agents). |
| `app-server/` | `cc-harness-appserver` | The codex-app-server adapter; bin `cc-codex-appserver` → `dist/bin.js`. |

The only external dependency is the published `@anthropic-ai/claude-agent-sdk` (pinned
in each `package.json`) plus `zod` — the SDK itself is **not** vendored.

Every worker session is opened with two in-process self-introspection MCP tools enabled
(`handlers.threadStart` sets `contextTool`/`compactTool`): `mcp__cc-context__GetContextUsage`
(read its own context-window usage) and `mcp__cc-compact__RequestCompaction` (schedule a
self-compaction at the end of the current turn). These let a worker manage its own context
on long multi-turn tickets. They are additive — only appended to `allowedTools`, so built-in
tools stay available (live-tested in `test/live/appserver.e2e.test.ts`).

`handlers.threadStart` also sets `contextBudget`, layering a **context-budget policy** on those
tools: a system-prompt persona telling the worker WHEN to self-compact (checkpoint-first, a
275k–650k token band, and an explicit guard against ending work early just to free space) plus a
hook that pushes the worker's current usage at a clean checkpoint (a `git commit`) or a high-water
crossing. Compaction stays the model's decision — the hook only injects advisory usage, never
forces it. **Self-compaction is advisory and model-dependent**: a capable model often judges it
still has room and declines the checkpoint nudge (observed on haiku and sonnet, 2026-06-24), so
treat this as a best-effort nudge with the SDK's native auto-compact as the involuntary floor.
See `cc-harness` `src/context/budget.ts` (persona) + `budgetHook.ts` (push); the end-to-end smoke
+ observation lives in `harness/test/live/context-budget.test.ts`.

## Build (one-time, after clone)

```sh
worker-runtime/setup.sh
```

`node_modules/` and `dist/` are gitignored (generated). `setup.sh` runs `npm install`
in both packages and builds them in dependency order; the app-server's `prepare` hook
emits the executable `app-server/dist/bin.js`.

## How the Director invokes it

`.harness.json` declares the runtime with a `{harness_root}` placeholder that the
Director expands to the absolute repo root at config-load time (the worker subprocess
runs with `cwd` = the *workspace*, so the path must be absolute):

```json
"director": {
  "worker_runtimes": {
    "claude": "node {harness_root}/worker-runtime/app-server/dist/bin.js app-server"
  }
}
```

Then `director.run --worker claude …` (or set `director.worker_runtime: "claude"` to
make it the default). The Director appends its self-governance `-c` flags
(`approvals_reviewer=auto_review`, `sandbox_workspace_write.network_access=…`), which
the adapter parses.

## Containment

`--worker claude` is both approval-gated **and** OS-sandboxed (Seatbelt on macOS,
bubblewrap+socat on Linux for Bash subprocesses, plus credential-read deny rules for
native file tools) — at parity with the default codex runtime. See `docs/SECURITY.md`
(T11). On Linux, the OS sandbox needs `bubblewrap`+`socat`; absent them it degrades
gracefully unless `CC_APPSERVER_SANDBOX_STRICT=1`.

## Provenance

Subtree-absorbed (with full history) from the `cc-codex-appserver` project
(`SSFSKIM/codex_somersault` `CC-to-SDK/{harness,app-server}`). To pull upstream
changes: `git subtree pull --prefix=worker-runtime/<pkg> <remote> <ref>`.
