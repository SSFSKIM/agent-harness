# CLAUDE.md — harness

The headless harness: a TypeScript library/service wrapping the Claude Agent SDK, published as the npm
package **`cc-harness`**. Parent context is `../CLAUDE.md` (CC-to-SDK) + the repo root. See
`../docs/parity/coverage.md` for what each surface implements.

## Commands (run from `harness/`)

```bash
npm run typecheck                       # tsc --noEmit — the fast correctness gate (run after every change)
npm run test:unit                       # vitest run test/unit — DI-based, no API key, fast (preferred)
npx vitest run test/unit/<file> -t "x"  # one file / filter to one test
npm run build                           # tsc -p tsconfig.build.json → dist/ (proves public .d.ts resolve)
npm run cli                             # tsx src/cli.ts
```

- **Live tests are gated** on `ANTHROPIC_API_KEY` (`const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip`) — there is **no dotenv autoload**, so they skip cleanly without a key. Run them keyed from here: `set -a; . ../.env; set +a; npx vitest run test/live/<file>`. Live tests cost tokens and take ~10–90 s each; the controller runs them, implementers stop at the clean keyless skip.
- After a subagent edit you may see phantom **"Cannot find module" / "property does not exist"** LSP diagnostics — they are stale; trust a clean `npm run typecheck` + green vitest over them.

## `src/` module map

- **`index.ts`** — the curated **public API** barrel. Add exports here deliberately; `test/unit/index.test.ts` pins the surface.
- **`config/`** — `resolveOptions(config)` builds the SDK `Options`. **The single seam most features wire through** (`createHarness` + lib `Session` both call it). NB: the **daemon does NOT use it** — per-session options come from a caller-supplied `sessionOptions` factory (`daemon/supervisor.ts`).
- **`harness.ts`** — `createHarness` / `resumeHarness`: one-shot `run`/`stream` (single `query()` turn).
- **`session/`** — lib interactive multi-turn `Session` (`openSession`/`resumeSession`, `.sessionId` capture, compact/control/rewind). `sessions/` — read API (`listSessions`/`getSessionMessages`) + `forkSession`.
- **`daemon/`** — long-lived multi-session service: `supervisor` (pool + restart) + UDS `server` + `registry` (`DaemonSession extends Session`).
- **`swarm/`** (coordinator + bus + teammates) · **`tasks/`** (durable Task MCP server) · **`context/`** (`cc-context` tool) · **`compaction/`** (`cc-compact` tool) · **`proactive/`** (heartbeat) · **`kairos/`** (assistant persona) · **`bridge/`** (control protocol) · **`hooks/`** (programmatic SDK hooks — builders + `mergeHooks`).

## Conventions

- **Dense hand-style, NO Prettier.** Match the surrounding code (compact, multi-statement lines where the file already does so) — do not reformat.
- **ESM:** import specifiers **end in `.js`** (`from "./types.js"`) even though sources are `.ts`.
- **DI-by-deps:** inject SDK functions (e.g. a fake `QueryFn`) so unit tests run without the network; live tests exercise the real SDK. Mirror the existing `deps = { ... }` default-param pattern.
- **TDD:** failing test → red → minimal impl → green → `typecheck`. New public exports + behavior get a test.
- Keep modules small and focused; prefer a new module over growing a hot file.
