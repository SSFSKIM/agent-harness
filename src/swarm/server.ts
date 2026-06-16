import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import type { SwarmRuntime } from "./runtime.js";
import { teamCreateShape, teamDeleteShape, spawnTeammateShape, sendMessageShape, checkMessagesShape } from "./types.js";

const ok = (data: unknown) => ({ content: [{ type: "text" as const, text: JSON.stringify(data) }] });
const fail = (message: string) => ({ content: [{ type: "text" as const, text: message }], isError: true });

/** Build the five cc-swarm SDK tool definitions over a SwarmRuntime (exported for direct handler testing). */
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
  ];
}

/** Wrap a SwarmRuntime as an in-process SDK MCP server exposing the five cc-swarm tools. */
export function createSwarmMcpServer(runtime: SwarmRuntime) {
  return createSdkMcpServer({ name: "cc-swarm", version: "0.1.0", tools: buildSwarmTools(runtime) });
}
