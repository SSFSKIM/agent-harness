import { describe, it, expect } from "vitest";
import { Readable } from "node:stream";
import { runServer } from "../../src/bin.js";

describe("runServer", () => {
  it("serializes outgoing wire objects as NDJSON to stdout and ignores argv noise", async () => {
    const lines: string[] = [];
    const stdin = new Readable({ read() {} });
    const { } = runServer({ stdin, stdout: { write: (s: string) => { lines.push(s); } }, argv: ["app-server", "-c", "approvals_reviewer=auto_review"] });
    stdin.push(JSON.stringify({ id: 1, method: "initialize", params: {} }) + "\n");
    await new Promise((r) => setTimeout(r, 5));
    expect(lines[0].endsWith("\n")).toBe(true);
    const msg = JSON.parse(lines[0]);
    expect(msg).toMatchObject({ id: 1, result: { userAgent: "cc-codex-appserver" } });
    expect("jsonrpc" in msg).toBe(false);
  });
});
