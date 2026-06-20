import { describe, it, expect } from "vitest";
import { isRequest, isNotification, isResponse } from "../../src/protocol.js";

describe("protocol shape guards", () => {
  it("classifies the three wire shapes", () => {
    expect(isRequest({ id: 1, method: "thread/start", params: {} })).toBe(true);
    expect(isNotification({ method: "turn/completed", params: {} })).toBe(true);
    expect(isResponse({ id: 1, result: { ok: true } })).toBe(true);
    // a server-initiated request reply (response) is NOT a request:
    expect(isRequest({ id: 1, result: {} })).toBe(false);
    expect(isResponse({ id: 1, method: "x" })).toBe(false); // has method -> request, not response
  });
});
