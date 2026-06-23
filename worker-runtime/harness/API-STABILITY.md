# API Stability Tiers — cc-harness

The tiers below document intent, not enforced contracts. `stable` exports follow semver once the package is published (no breaking changes without a major bump). `experimental` exports wrap an unstable SDK surface or an alpha beta feature and may change in minor releases. `advanced-seam` exports are designed for embedders running their own daemon, swarm, or MCP toolchain; they are functional but may shift as internals evolve — use them if you need them, but pin your version.

| Export | Tier |
|---|---|
| `createHarness` | stable |
| `resumeHarness` | stable |
| `openSession` | stable |
| `resumeSession` | stable |
| `Session` | stable |
| `listSessions` | stable |
| `getSessionMessages` | stable |
| `getSessionInfo` | stable |
| `forkSession` | stable |
| `renameSession` | stable |
| `tagSession` | stable |
| `deleteSession` | stable |
| `resolveOptions` | stable |
| `resolveAutoModel` | advanced-seam |
| `isAutoSupportedModel` | advanced-seam |
| `validateHarnessConfig` | stable |
| `HarnessConfigError` | stable |
| `TaskStore` | stable |
| `TaskError` | stable |
| `createTaskMcpServer` | stable |
| `DEFAULTS` | stable |
| `BUILTIN_AGENTS` | stable |
| `BUILTIN_OUTPUT_STYLES` | stable |
| `injectContext` | stable |
| `guardTool` | stable |
| `blockTool` | stable |
| `observe` | stable |
| `mergeHooks` | stable |
| `KairosAssistant` | experimental |
| `applyAssistantPersona` | experimental |
| `resolveAssistantPosture` | experimental |
| `createBriefMcpServer` | experimental |
| `stdoutBriefSink` | experimental |
| `DaemonSupervisor` | advanced-seam |
| `DaemonServer` | advanced-seam |
| `daemonRequest` | advanced-seam |
| `daemonSocketPath` | advanced-seam |
| `DaemonError` | advanced-seam |
| `SwarmRuntime` | advanced-seam |
| `createSwarmMcpServer` | advanced-seam |
| `SwarmError` | advanced-seam |
| `createContextMcpServer` | advanced-seam |
| `createCompactMcpServer` | advanced-seam |
| `CONTEXT_TOOL` | advanced-seam |
| `COMPACT_TOOL` | advanced-seam |
| `summarizeUsage` | advanced-seam |
| `connectDaemon` | advanced-seam |
| `collect` | advanced-seam |
| `createPermissionGate` | advanced-seam |
| `PermissionBroker` (type) | advanced-seam |
| `PermissionDecision` (type) | advanced-seam |
| `PermissionRequest` (type) | advanced-seam |
| `PendingEntry` (type) | advanced-seam |
| `DaemonClient.pendingPermissions()` / `DaemonClient.respondPermission()` | advanced-seam |
