// test/unit/posture.test.ts
import { describe, it, expect } from "vitest";
import { resolvePosture, parseConfigFlags } from "../../src/posture.js";

describe("posture", () => {
  it("auto_review or approvalPolicy:never -> auto, no round-trip", () => {
    expect(resolvePosture({ approvalPolicy: "on-request", autoReview: true })).toEqual({ permissionMode: "auto", roundTripApprovals: false });
    expect(resolvePosture({ approvalPolicy: "never", autoReview: false })).toEqual({ permissionMode: "auto", roundTripApprovals: false });
  });
  it("on-request without auto_review -> default + broker", () => {
    expect(resolvePosture({ approvalPolicy: "on-request", autoReview: false })).toEqual({ permissionMode: "default", roundTripApprovals: true });
    expect(resolvePosture({ approvalPolicy: "untrusted", autoReview: false })).toEqual({ permissionMode: "default", roundTripApprovals: true });
  });
  it("parses -c approvals_reviewer=auto_review from argv", () => {
    expect(parseConfigFlags(["app-server", "-c", "approvals_reviewer=auto_review", "-c", "x=y"]).autoReview).toBe(true);
    expect(parseConfigFlags(["app-server"]).autoReview).toBe(false);
  });
});
