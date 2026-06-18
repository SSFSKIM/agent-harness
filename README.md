# cc-harness

A headless TypeScript library that wraps the [Claude Agent SDK](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)
with **Claude Code-faithful defaults**, exposing Claude Code's harness capabilities — one-shot runs,
interactive sessions, a long-lived multi-session daemon, programmatic hooks, a teammate swarm, and a
durable task list — as a library plus a thin `cc-harness` CLI.

The Agent SDK *is* Claude Code's engine (a bundled native binary), so most CC behavior already exists;
the harness's job is to **configure and verify** the SDK the way CC does by default, and to surface
capabilities the bare SDK doesn't expose as a library. See
[`../docs/parity/coverage.md`](../docs/parity/coverage.md) for the capability scorecard and
[`API-STABILITY.md`](./API-STABILITY.md) for per-export stability tiers.

## Install

```bash
cd CC-to-SDK/harness
npm install
npm run build
```

`cc-harness` is `private: true` — it is **not yet published to npm**; today you consume it in-repo (or via
`npm link`). Requires **Node ≥18**. Authentication uses `ANTHROPIC_API_KEY` (or a provider flag — see the
[`HarnessConfig` reference](#harnessconfig-reference)); for local runs the key is read from
`CC-to-SDK/.env` (gitignored): `set -a; source ../.env; set +a`.

## Quickstart

```ts
import { createHarness } from "cc-harness";

const harness = createHarness({ permissionMode: "bypassPermissions", maxTurns: 4 });
const { result, sessionId } = await harness.run("Explain this repo's layout.");
console.log(result);
```

## Core surfaces

cc-harness is a toolkit, not a single entry point. Each surface below is one import from `cc-harness`.

### One-shot harness — `createHarness`

`createHarness(config, deps?)` returns a `Harness` that drives a single `query()` turn. `run()` collects
the whole turn; `stream()` yields the SDK message stream.

```ts
import { createHarness } from "cc-harness";

const harness = createHarness({ outputStyle: "explanatory", maxTurns: 4 });

const { result, messages, sessionId } = await harness.run("List the open TODOs.");

for await (const message of harness.stream("Now summarize them.")) {
  // render each SDK message…
}
```

`resolveOptions(config)` is exported separately and is **pure** (config → SDK `Options`), so the
CC-faithful bridges are unit-testable without the network. `resumeHarness(sessionId, config?)` continues a
prior session by id.

### Interactive session — `openSession`

`openSession(config, deps?)` opens a long-lived multi-turn `Session`. Each `submit(prompt, onMessage?)`
runs one turn against the same session; `stream(prompt)` is the async-generator form. `.sessionId` is
captured from the first turn's init frame. Dispose when done.

```ts
import { openSession } from "cc-harness";

const session = openSession({ permissionMode: "bypassPermissions" });
await session.submit("Remember the codeword is BLUEBIRD.");
const { result } = await session.submit("What was the codeword?");
console.log(result, session.sessionId);
await session.dispose();
```

`resumeSession(id, config?)` reopens a persisted session by id (preserving its `session_id`). A live
`Session` also exposes `compact()`, `rewind(userMessageId)`, `setModel()`, `setPermissionMode()`, and the
introspection methods below.

### Multi-session daemon — `DaemonSupervisor` / `DaemonServer`

`DaemonSupervisor` owns an in-process pool of long-lived sessions with idle-reaping and crash-restart;
`DaemonServer` exposes it over a Unix-domain-socket NDJSON protocol for out-of-process clients.

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSupervisor, DaemonServer, daemonSocketPath } from "cc-harness";

const supervisor = new DaemonSupervisor({ query }, { restart: "on-failure", rehydrate: true });
const id = supervisor.spawn({ model: "claude-opus-4-8" });
const { result } = await supervisor.submit(id, "Hello", () => {});

const server = new DaemonServer(supervisor, daemonSocketPath());
await server.listen();
// … out-of-process clients connect via daemonRequest(socketPath, op) …
await server.close();
await supervisor.shutdown();
```

`rehydrate: true` opts into **boot-rehydration**: a fresh supervisor adopts the prior process's
still-resumable sessions and revives each on first access (instead of reaping them). `DaemonOptions` also
cover `restart`/`maxRestarts`/`backoffMs`, `maxSessions`, `idleTimeoutMs`, `sharedTasks`, and
`contextTool`/`compactTool`. Client helpers `daemonRequest(socketPath, op)` and `daemonSocketPath(env?)`
speak the protocol from another process; `DaemonError` is the thrown error type.

### Session store: read, fork, mutate

The SDK persists every transcript under `~/.claude/projects`. These wrappers read and curate that store
(harness `cwd` → SDK `dir`).

```ts
import { listSessions, getSessionMessages, forkSession, renameSession, tagSession, deleteSession } from "cc-harness";

const sessions = await listSessions({ limit: 20 });
const messages = await getSessionMessages(sessions[0].sessionId);

const { sessionId: branch } = await forkSession(sessions[0].sessionId, { title: "experiment" });
await renameSession(branch, "Experiment A");
await tagSession(branch, "wip");
await deleteSession(branch);   // destructive + irreversible
```

`getSessionInfo(id, opts?)` fetches one session's metadata. `forkSession` mints a **new** id (the original
is untouched); reach the branch with `resumeSession(branch)`.

### Hooks — `injectContext` / `blockTool` / `observe`

Programmatic SDK hooks as composable builders. Fold them with `mergeHooks` and pass the result as
`config.hooks`.

```ts
import { createHarness, injectContext, blockTool, observe, mergeHooks } from "cc-harness";

const hooks = mergeHooks(
  injectContext(() => "The current sprint ends Friday."),
  blockTool("Bash", /rm -rf/, "no destructive shell"),
  blockTool("Write", /\.env\b/, "never write secrets"),
  observe("PostToolUse", (input) => console.error("hook:", input.hook_event_name)),
);

const harness = createHarness({ hooks, permissionMode: "default" });
```

`guardTool(matcher, decide)` is the lower-level gate `blockTool` builds on (return `{ block, reason }` to
deny). Only 8 of the SDK's 30 hook events fire headlessly; the builders cover the verified ones
(`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `SubagentStop`).

### Swarm — `SwarmRuntime`

A coordinator-plus-teammates runtime over an in-process message bus, sharing one durable task store.

```ts
import { query } from "@anthropic-ai/claude-agent-sdk";
import { SwarmRuntime } from "cc-harness";

const swarm = new SwarmRuntime({ query }, { cwd: process.cwd() });
swarm.spawnTeammate({ name: "reviewer", teamId: "core", prompt: "Review the diff for bugs." });
// … coordinate via swarm.bus / swarm.tasks …
await swarm.disposeAll();
```

You can also enable it declaratively with `createHarness({ swarm: true })`, which registers the `cc-swarm`
MCP tools. `createSwarmMcpServer` and `SwarmError` are exported for embedding.

### Durable tasks — `taskTools` / `harness.tasks`

Claude Code's durable `Task*` list, which the bare SDK doesn't ship, reproduced as an in-process MCP
server.

```ts
import { createHarness } from "cc-harness";

const harness = createHarness({ taskTools: true });
await harness.run("Use TaskCreate to add 'ship docs', then TaskList.");
const tasks = await harness.tasks!.list();   // same store, programmatic
```

The store is file-backed JSON at `<cwd>/.cc-harness/tasks/<listId>.json`, written atomically and
serialized, with a `pending → in_progress → completed` machine and a `blockedBy` DAG. `TaskStore` and
`createTaskMcpServer` are exported for embedding; `TaskError` is the thrown error type.

### Introspection

A `Harness`, a `Session`, and the daemon expose live introspection. These are SDK **control requests** that
need an open transport — call them while a query/turn is active (they throw after a one-shot `run()`
completes), so the cleanest place is a live `Session`:

```ts
import { openSession } from "cc-harness";

const session = openSession();
await session.submit("Analyze the repo.");           // an active turn opens the transport
const usage = await session.usage();                 // session cost + token totals
const ctx = await session.getContextUsage();         // context-window occupancy
const init = await session.initializationResult();   // models / commands / agents available
await session.dispose();
```

`accountInfo()` returns plan/account metadata. `summarizeUsage(raw)` reduces raw context usage to a
compact summary; `createContextMcpServer` / `createCompactMcpServer` (with `CONTEXT_TOOL` / `COMPACT_TOOL`)
expose context and compaction to the model as MCP tools, wired via `config.contextTool` /
`compactTool`.

### Config validation — `validateHarnessConfig`

Every front door (`createHarness`, `openSession`, `DaemonSupervisor`) validates its config before any side
effect, throwing `HarnessConfigError` on a malformed value. Call it yourself to fail fast:

```ts
import { validateHarnessConfig, HarnessConfigError } from "cc-harness";

try {
  validateHarnessConfig({ maxTurns: -1 });
} catch (e) {
  if (e instanceof HarnessConfigError) console.error(e.message);
}
```

Validation guards constrained fields only (it never transforms); escape hatches
(`extraOptions`/`settings`/`managedSettings`/`customHeaders`) pass through untouched.

## `HarnessConfig` reference

`HarnessConfig` is the friendly config every surface accepts; `resolveOptions(config)` turns it into the
SDK `Options`. Validated fields throw `HarnessConfigError` on bad input; fields marked **un-validated**
pass straight through.

| field | meaning | default |
|---|---|---|
| `cwd`, `model`, `fallbackModel`, `maxTurns` | passthrough to SDK `Options` | SDK defaults |
| `effort` | reasoning effort: `low`/`medium`/`high`/`xhigh`/`max` | SDK default |
| `thinking` | extended-thinking config (`{type:'adaptive'\|'disabled'}` or `{type:'enabled',budgetTokens?}`) | SDK default |
| `maxBudgetUsd` | hard USD ceiling; **exceeding it hard-stops the run (throws or returns empty)** — wrap in try/catch | — |
| `taskBudget` | token-pacing hint `{ total }`; **opus-4-8 only** (sonnet/haiku return 400) | — |
| `includePartialMessages` | emit `stream_event` partial-assistant frames | `false` |
| `forwardSubagentText` | forward nested subagent text/thinking | `false` |
| `settingSources` | which settings layers load (`user`/`project`/`local`) | **all three** (CC-faithful; SDK default is *none*) |
| `settings`, `managedSettings` | inline settings objects (**un-validated**) | — |
| `disableProjectContext` | skip CLAUDE.md/project files → `settingSources: []` | `false` |
| `excludeDynamicSections` | drop git/date dynamic prompt blocks | `false` |
| `outputStyle` | persona; appended to the `claude_code` system prompt | — |
| `appendSystemPrompt` | extra text appended to the system prompt | — |
| `permissionMode` | `default`/`plan`/`acceptEdits`/`auto`/`bypassPermissions`/`dontAsk` | SDK default |
| `allowedTools`, `disallowedTools` | tool allow/deny lists | SDK defaults |
| `toolPreset` | `"claude_code"` (full pool) or `"none"` | `"claude_code"` |
| `toolAliases` | rename tools | — |
| `webFetchDomains` | `{ allow?, deny? }` → `WebFetch(domain:<host>)` rules | — |
| `sandbox` | `true` or `{ enabled?, network?, autoAllowBashIfSandboxed? }` (`network` is the SDK object, not a bool) | off |
| `provider` | `"anthropic"`/`"bedrock"`/`"vertex"`/`"foundry"` → env flag | `"anthropic"` |
| `baseUrl`, `customHeaders` | gateway base URL + headers via env (`customHeaders` **un-validated**) | — |
| `agents` | extra `AgentDefinition`s (override built-ins by key) | — |
| `includeBuiltinAgents` | register `general-purpose`/`Explore`/`Plan` | `true` |
| `enableFileCheckpointing` | enable file checkpoints (for `rewind`) | `true` |
| `resume` | SDK `session_id` to reload prior context | — |
| `persistSession` | persist transcript to disk; `false` = ephemeral | SDK-true |
| `sessionStore` | BYO transcript-mirror backend (advanced passthrough) | — |
| `autoCompactEnabled` | the SDK's native ~167k auto-compaction safety net | SDK-on |
| `autoCompactWindow` | tokens of headroom before auto-compaction | SDK default |
| `taskTools` | enable the durable `Task*` MCP server (`true` or `{ dir?, listId?, agentName? }`) | off |
| `swarm` | enable the teammate swarm (`true` or `{ team?, coordinatorPersona?, tools?, permissions? }`) | off |
| `contextTool` | expose the `cc-context` GetContextUsage tool to the model | off |
| `hooks` | programmatic SDK hooks (`HooksMap`; build with the hook builders + `mergeHooks`) | — |
| `mcpServers`, `plugins` | passthrough to SDK | — |
| `env` | extra environment variables (merged last, spread over `process.env`) | — |
| `extraOptions` | escape hatch merged last into SDK `Options` (**un-validated**) | — |

> `openSession` accepts one extra field beyond `HarnessConfig`: **`compactTool`** (boolean) — expose the
> `cc-compact` RequestCompaction tool to the model. It is session-level, not on the base `HarnessConfig`.

## CLI

```bash
npm run cli -- "Reply with exactly the word OK." --max-turns 1
echo "FILE CONTENT" | npm run cli -- "Summarize the piped text." --max-turns 1
```

The packaged bin is `cc-harness` (`dist/cli.js`). Flags: `--model`, `--output-style`,
`--permission-mode`, `--max-turns`, `--cwd`, `--no-project-context`, `--sandbox`. The CLI defaults to
`permissionMode: bypassPermissions` for headless runs; non-TTY stdin is appended to the prompt.

## CC-faithful defaults (the bridges)

These are the places where the SDK is *not* CC-faithful out of the box; the harness makes the CC choice
(all unit-tested via `resolveOptions`):

- **Settings:** `settingSources` defaults to **all three** (the SDK default is *none*, which would skip
  `CLAUDE.md`); `project` is required for project context.
- **Output style:** `outputStyle` is a **phantom SDK option** (not in `sdk.d.ts` v0.3.178); the harness
  reproduces personas by **appending** to the `claude_code` `systemPrompt` preset.
- **Sandbox:** friendly `sandbox` config → `Options.sandbox`.
- **Provider:** `provider`/`baseUrl`/`customHeaders` → `env` (Bedrock/Vertex/Foundry flags, base URL,
  custom headers).
- **Tools:** `claude_code` tool preset + WebFetch `domain:<host>` allow/deny rules.
- **Agents:** the SDK does **not** auto-ship CC's built-in agents; the harness registers
  `general-purpose`, plus read-only `Explore`/`Plan` (mutation tools disallowed).
- **Checkpointing/rewind:** `enableFileCheckpointing` on by default; `rewind()` → `Query.rewindFiles`.
- **Commands/skills:** loaded from disk via `settingSources` (no extra wiring).
- **CLI stdin:** non-TTY stdin is read and composed into the prompt.

A few SDK sharp edges the harness papers over:

- **`env` replaces the subprocess environment** when set (it is *not* merged with `process.env`). The
  harness spreads `process.env` first, so setting `provider`/`baseUrl`/`customHeaders`/`env` never erases
  `PATH`/`HOME`/`ANTHROPIC_API_KEY`.
- **`bypassPermissions`** requires `allowDangerouslySkipPermissions: true`; `resolveOptions` sets it
  automatically for that mode, so no caller can select the mode without satisfying its contract.
- **`settingSources` default:** `sdk.d.ts` v0.3.178 loads *all* sources when omitted; the harness sets
  `['user','project','local']` explicitly regardless, so it stays CC-faithful across SDK-default drift.

## Stability & testing

```bash
npm run test:unit    # fast, no network
npm run test:live    # real SDK calls; needs ANTHROPIC_API_KEY (auto-skips without it)
npm run typecheck    # tsc --noEmit
npm run build        # tsc -p tsconfig.build.json → dist/
```

Unit tests are deterministic and dependency-injected (a fake `query`, no network); live tests exercise the
real SDK and auto-skip without `ANTHROPIC_API_KEY`. See [`API-STABILITY.md`](./API-STABILITY.md) for
per-export tiers (`stable` / `experimental` / `advanced-seam`).

## Where this fits

cc-harness is the CC→SDK program's **headless harness**: it replicates Claude Code's harness capabilities
on top of the Agent SDK as a library + CLI. See [`../docs/parity/coverage.md`](../docs/parity/coverage.md)
for the capability scorecard (what's built vs. reachable vs. out-of-reach) and
[`../docs/parity/roadmap.md`](../docs/parity/roadmap.md) for direction. Licensed Apache-2.0.
