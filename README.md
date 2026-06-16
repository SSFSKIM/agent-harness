# cc-harness — Phase 1 (Headless Harness Core)

A TypeScript library that wraps the [Claude Agent SDK](https://www.npmjs.com/package/@anthropic-ai/claude-agent-sdk)
with **Claude Code-faithful defaults**, plus a thin `cc-harness` CLI. It is the stable core that the
CC→SDK program's Phase 2 (modes/backends) and Phase 3 (interactive TUI) build on.

The Agent SDK *is* Claude Code's engine (a bundled native binary), so most CC behavior is already
provided — the harness's job is to **configure and verify** it the way CC does by default, papering
over the SDK's sharp edges (the "bridges" below).

## Install

```bash
cd CC-to-SDK/harness
npm install
```

Requires Node ≥20. Authentication uses `ANTHROPIC_API_KEY` (or a provider flag — see below). For local
runs the key is read from `CC-to-SDK/.env` (gitignored); load it with `set -a; source ../.env; set +a`.

## Library API

```ts
import { createHarness } from "cc-harness"; // from ./src/index.ts in-repo

const harness = createHarness({
  outputStyle: "explanatory",
  permissionMode: "bypassPermissions",
  maxTurns: 4,
});

// One-shot: collect the whole run.
const { result, messages, sessionId } = await harness.run("Explain this repo's layout.");

// Streaming: iterate the SDK message stream.
for await (const message of harness.stream("List the open TODOs.")) {
  // render message…
}

// Introspection passthrough (call after a query has started):
await harness.supportedCommands();
await harness.supportedModels();
await harness.supportedAgents();
```

### `createHarness(config, deps?)`

- `config: HarnessConfig` — the friendly config (see fields below).
- `deps.query` — inject a custom/mocked SDK `query` for testing (defaults to the real SDK).
- Returns a `Harness`: `{ options, run, stream, rewind, supportedCommands, supportedModels, supportedAgents }`.
  - `options` is the resolved SDK `Options` object (the output of the pure `resolveOptions(config)`).

`resolveOptions(config)` is exported separately and is **pure** (config → SDK `Options`), so the bridges
are unit-testable without the network.

### `HarnessConfig` fields

| field | meaning | default |
|---|---|---|
| `cwd`, `model`, `fallbackModel`, `maxTurns` | passthrough to SDK `Options` | SDK defaults |
| `settingSources` | which settings layers to load (`user`/`project`/`local`) | **all three** (CC-faithful; SDK default is *none*) |
| `settings`, `managedSettings` | inline settings objects | — |
| `disableProjectContext` | skip CLAUDE.md/project files → `settingSources: []` | `false` |
| `excludeDynamicSections` | drop git/date dynamic prompt blocks | `false` |
| `outputStyle` | persona; appended to the `claude_code` system prompt (see note) | — |
| `appendSystemPrompt` | extra text appended to the system prompt | — |
| `permissionMode`, `allowedTools`, `disallowedTools` | permission controls | SDK defaults |
| `toolPreset` | `"claude_code"` (full pool) or `"none"` | `"claude_code"` |
| `toolAliases` | rename tools | — |
| `webFetchDomains` | `{ allow?, deny? }` → `WebFetch(domain:<host>)` rules | — |
| `sandbox` | `true` or `{ enabled?, network?, autoAllowBashIfSandboxed? }` | off |
| `provider` | `"anthropic" \| "bedrock" \| "vertex" \| "foundry"` → env flag | `"anthropic"` |
| `baseUrl`, `customHeaders` | gateway base URL + headers via env | — |
| `agents` | extra `AgentDefinition`s (override built-ins by key) | — |
| `includeBuiltinAgents` | register `general-purpose`/`Explore`/`Plan` | `true` |
| `enableFileCheckpointing` | enable file checkpoints (for `rewind`) | `true` |
| `mcpServers`, `plugins` | passthrough to SDK | — |
| `env` | extra environment variables (merged last) | — |
| `extraOptions` | escape hatch merged last into SDK `Options` | — |

## The 16 Phase-1 bridges

These are the places where the SDK is *not* CC-faithful out of the box; the harness makes the CC choice:

- **Settings (02.12/02.14/02.17/02.20/05.4):** `settingSources` defaults to **all three** (the SDK
  default is *none*, which would skip `CLAUDE.md`); `project` is required for project context.
- **Output style (02.18):** `outputStyle` is a **phantom SDK option** (not in `sdk.d.ts` v0.3.178); the
  harness reproduces personas by **appending** to the `claude_code` `systemPrompt` preset.
- **Sandbox (42.2/10.6):** friendly `sandbox` config → `Options.sandbox`.
- **Provider (22.6):** `provider`/`baseUrl`/`customHeaders` → `env` (Bedrock/Vertex/Foundry flags, base
  URL, custom headers).
- **Tools (05.7/13.8):** `claude_code` tool preset + WebFetch `domain:<host>` allow/deny rules.
- **Agents (14.10/14.21):** the SDK does **not** auto-ship CC's built-in agents; the harness registers
  `general-purpose`, plus read-only `Explore`/`Plan` (mutation tools disallowed).
- **Checkpointing/rewind (11.13):** `enableFileCheckpointing` on by default; `rewind()` → `Query.rewindFiles`.
- **Commands/skills (20.2):** loaded from disk via `settingSources` (no extra wiring).
- **CLI stdin (01.11):** non-TTY stdin is read and composed into the prompt.

## CLI

```bash
# direct prompt
npx tsx src/cli.ts "Reply with exactly the word OK." --max-turns 1

# piped stdin (appended to the prompt)
echo "FILE CONTENT" | npx tsx src/cli.ts "Summarize the piped text." --max-turns 1
```

Flags: `--model`, `--output-style`, `--permission-mode`, `--max-turns`, `--cwd`,
`--no-project-context`, `--sandbox`. The CLI defaults to `permissionMode: bypassPermissions` for
headless runs.

## Tests

```bash
npm run test:unit    # fast, no network — verifies every bridge via resolveOptions/createHarness
npm run test:live    # real SDK calls; needs ANTHROPIC_API_KEY (auto-skips without it)
npm run typecheck    # tsc --noEmit
```

- **Unit (`test/unit/`):** deterministic; each bridge has a test asserting its slice of the resolved
  `Options`. `createHarness` is tested with a fake `query` (no network).
- **Live parity (`test/live/`):** one real-SDK test per runtime-behavior bridge (end-to-end run,
  `.claude/commands` discovery, `Explore` registration, checkpointing-enabled file creation). These
  auto-skip when `ANTHROPIC_API_KEY` is unset.

> **Note on `rewind` and introspection:** the SDK's `rewindFiles()` and the `supported*()`
> introspection methods are **control-protocol requests** that need an *open* process transport — call
> them while a query is active (after `stream()` has started), not after a one-shot `run()` completes.
> The `rewind → rewindFiles` wiring is verified in the unit suite; live mid-session rewind is a Phase-2
> (interactive/streaming) capability.

> **Note on `env`:** the SDK's `Options.env`, when set, **replaces** the subprocess environment
> entirely (it is not merged with `process.env`). The harness therefore spreads `process.env` before
> applying provider flags / overrides, so setting `provider`/`baseUrl`/`customHeaders`/`env` never
> erases `PATH`/`HOME`/`ANTHROPIC_API_KEY`.

> **Note on `bypassPermissions`:** the SDK requires `allowDangerouslySkipPermissions: true` whenever
> `permissionMode: 'bypassPermissions'` is used (`sdk.d.ts:1719`). `resolveOptions` sets it
> automatically for that mode, so no caller can select the mode without satisfying its contract.

> **Note on `settingSources` default:** the bundled `sdk.d.ts` (v0.3.178) documents that an omitted
> `settingSources` loads *all* sources (matching the CLI) — newer than the Phase-0 "defaults to none"
> premise. The harness sets `['user','project','local']` explicitly regardless, so it stays
> CC-faithful across SDK-default drift.

## Where this fits

This package is **Phase 1** of replicating the Claude Code harness on the Agent SDK. It delivers the
headless core (config bridges + `query()` loop wiring + verification). Phase 2 adds non-UI modes and
backends (multi-agent coordinator, daemon/bridge/proactive, advanced config) around this core; Phase 3
adds the interactive Ink TUI as a rendering layer over the message stream this core already produces.
See `../docs/parity/roadmap.md`.
