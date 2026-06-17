import { describe, it, expect } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHarness, resumeHarness } from "../../src/index.js";

const live = process.env.ANTHROPIC_API_KEY ? describe : describe.skip;
const MODEL = "claude-haiku-4-5-20251001";

live("live session persistence (real SDK)", () => {
  it("resumeHarness reloads prior context across separate runs", async () => {
    const cwd = mkdtempSync(join(tmpdir(), "cc-persist-live-"));
    try {
      const h = createHarness({ model: MODEL, permissionMode: "auto", cwd });
      const r1 = await h.run("Remember this codeword: BANANA42. Reply OK and nothing else.");
      expect(r1.sessionId).toBeTruthy();
      const h2 = resumeHarness(r1.sessionId!, { model: MODEL, permissionMode: "auto", cwd });
      const r2 = await h2.run("What was the codeword? Reply with just the word.");
      expect(String(r2.result)).toMatch(/BANANA42/);
    } finally {
      rmSync(cwd, { recursive: true, force: true });
    }
  }, 60_000);
});
