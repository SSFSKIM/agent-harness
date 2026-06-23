import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { query } from "@anthropic-ai/claude-agent-sdk";
import { DaemonSupervisor } from "../../src/daemon/supervisor.js";
import { resumeSession } from "../../src/index.js";

const live = (process.env.ANTHROPIC_API_KEY || process.env.CLAUDE_CODE_OAUTH_TOKEN) ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live daemon durable sessions (real SDK)", () => {
  it("submit persists a real session_id; that id resumes and recalls context", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-durable-live-"));
    // The daemon passes session options through verbatim (it bypasses resolveOptions), so set the
    // bypass flag explicitly; share `cwd` so the resumed session resolves to the same transcript.
    const sup = new DaemonSupervisor(
      { query },
      { dir: mkdtempSync(join(tmpdir(), "cc-daemon-")), sessionOptions: () => ({ permissionMode: "bypassPermissions", allowDangerouslySkipPermissions: true, cwd }) },
    );
    let sessionId: string | undefined;
    try {
      const id = sup.spawn({ model: MODEL });
      await sup.submit(id, "Remember this codeword: FALCON3. Reply OK only.", () => {});
      sessionId = sup.list()[0].sessionId;
      expect(sessionId).toMatch(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/); // a real UUID
    } finally { await sup.shutdown(); }

    const s = resumeSession(sessionId!, { model: MODEL, permissionMode: "bypassPermissions", cwd });
    try {
      const r = await s.submit("What codeword did I give you earlier? Reply with just the word.");
      expect(String(r.result)).toMatch(/FALCON3/);
    } finally { await s.dispose(); rmSync(cwd, { recursive: true, force: true }); }
  }, 90_000);
});
