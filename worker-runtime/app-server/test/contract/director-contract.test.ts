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
  it("a dynamic tool round-trips via item/tool/call (server relays, client executes)", async () => {
    const c = new DirectorClient(["node", BIN, "app-server"], { ...process.env, CC_APPSERVER_FAKE: "1" } as any);
    await c.initialize();
    const spec = { name: "linear_graphql", description: "Execute a GraphQL query against Linear.", inputSchema: { type: "object", required: ["query"], properties: { query: { type: "string" } } } };
    const tid = await c.threadStart("/tmp", [spec]);
    const r = await c.runTurn(tid, "USE_TOOL please", "/tmp");
    c.stop();
    expect(r.status).toBe("completed");
    // the server asked us (the client) to execute the tool, with the model's arguments
    expect(c.toolCalls.map((t) => t.tool)).toContain("linear_graphql");
    expect(c.toolCalls[0].arguments).toEqual({ query: "query { viewer { id } }" });
    expect(c.toolCalls[0]).toMatchObject({ threadId: tid, callId: expect.any(String) });
    // and the client's reply was fed back into the agent's answer
    expect(r.final).toContain("executed linear_graphql");
  });
});
