import { describe, it, expect } from "vitest";
import { resolveOptions } from "../../src/config/resolveOptions.js";
import type { PermissionBroker } from "../../src/permissions/types.js";

const broker: PermissionBroker = { request: async () => ({ kind: "allow_once" }) };

describe("resolveOptions × permissionBroker", () => {
  it("sets canUseTool to a function when a broker is supplied", () => {
    const opts = resolveOptions({ permissionBroker: broker });
    expect(typeof opts.canUseTool).toBe("function");
  });
  it("leaves canUseTool unset when no broker is supplied (existing callers unchanged)", () => {
    expect(resolveOptions({}).canUseTool).toBeUndefined();
  });
});
