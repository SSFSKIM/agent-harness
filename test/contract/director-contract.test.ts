import { describe, it, expect, beforeAll } from "vitest";
import { DirectorClient } from "./client.js";
import { execSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const BIN = resolve(here, "../../dist/bin.js");

describe("Director drop-in contract (fake session, no key)", () => {
  beforeAll(() => { execSync("npm run build", { cwd: resolve(here, "../..") }); });
  it("a plain turn reaches completed with a final_answer", async () => {
    const c = new DirectorClient(["node", BIN, "app-server"], { ...process.env, CC_APPSERVER_FAKE: "1" } as any);
    await c.initialize();
    const tid = await c.threadStart("/tmp");
    expect(tid).toMatch(/^thr_/);
    const r = await c.runTurn(tid, "do a thing", "/tmp");
    c.stop();
    expect(r.status).toBe("completed");
    expect(r.final).toBe("final text");
  });
  it("a REPORT turn carries outcome on turn/completed", async () => {
    const c = new DirectorClient(["node", BIN, "app-server"], { ...process.env, CC_APPSERVER_FAKE: "1" } as any);
    await c.initialize();
    const tid = await c.threadStart("/tmp");
    const r = await c.runTurn(tid, "REPORT done", "/tmp");
    c.stop();
    expect(r.outcome).toMatchObject({ status: "done" });
  });
});
