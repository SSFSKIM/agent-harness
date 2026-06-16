import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import type { SwarmRuntime } from "./runtime.js";
import {
  teamCreateShape, teamDeleteShape, spawnTeammateShape, sendMessageShape, checkMessagesShape,
  respondPermissionShape, shutdownTeammateShape, approvePlanShape,
} from "./types.js";

const ok = (data: unknown) => ({ content: [{ type: "text" as const, text: JSON.stringify(data) }] });
const fail = (message: string) => ({ content: [{ type: "text" as const, text: message }], isError: true });

/** Build the eight cc-swarm SDK tool definitions over a SwarmRuntime (exported for direct handler testing). */
export function buildSwarmTools(runtime: SwarmRuntime) {
  return [
    tool("TeamCreate", "Create a team of teammates; returns its teamId and roster.", teamCreateShape, async (a) => {
      try { const t = runtime.createTeam(a.name, a.members); return ok({ teamId: t.id, roster: t.members }); }
      catch (e) { return fail((e as Error).message); }
    }),
    tool("TeamDelete", "Disband a team and stop its teammates.", teamDeleteShape, async (a) => {
      try { const t = await runtime.deleteTeam(a.teamId); return ok({ teamId: t.id, roster: t.members }); }
      catch (e) { return fail((e as Error).message); }
    }),
    tool("spawnTeammate", "Spawn a long-lived teammate session on a team, seeded with a prompt.", spawnTeammateShape, async (a) => {
      try { const s = runtime.spawnTeammate(a); return ok({ name: s.name, teamId: s.teamId }); }
      catch (e) { return fail((e as Error).message); }
    }),
    tool("SendMessage", "Send a message to a teammate (delivered as a turn) or to 'coordinator'.", sendMessageShape, async (a) => {
      try { return ok(runtime.sendMessage(a.to, a.body, a.kind)); }
      catch (e) { return fail((e as Error).message); }
    }),
    tool("CheckMessages", "Read and clear messages addressed to the coordinator.", checkMessagesShape, async () => {
      return ok(runtime.checkMessages());
    }),
    tool("RespondPermission", "Resolve a teammate's escalated permission request by id (allow/deny).", respondPermissionShape, async (a) => {
      return runtime.respondPermission(a.requestId, a.decision, a.message)
        ? ok({ resolved: a.requestId, decision: a.decision })
        : fail(`unknown request ${a.requestId}`);
    }),
    tool("ShutdownTeammate", "Gracefully shut down a teammate (finish current turn, then stop).", shutdownTeammateShape, async (a) => {
      try { await runtime.requestShutdown(a.name); return ok({ shutdown: a.name }); }
      catch (e) { return fail((e as Error).message); }
    }),
    tool("ApprovePlan", "Approve or reject a teammate's escalated plan by id (approve → it implements; reject → it revises with your feedback).", approvePlanShape, async (a) => {
      return (await runtime.respondPlan(a.requestId, a.decision, a.feedback))
        ? ok({ resolved: a.requestId, decision: a.decision })
        : fail(`unknown request ${a.requestId}`);
    }),
  ];
}

/** Wrap a SwarmRuntime as an in-process SDK MCP server exposing the eight cc-swarm tools. */
export function createSwarmMcpServer(runtime: SwarmRuntime) {
  return createSdkMcpServer({ name: "cc-swarm", version: "0.1.0", tools: buildSwarmTools(runtime) });
}
