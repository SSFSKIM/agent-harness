import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod/v4";

export type BriefStatus = "normal" | "proactive";
export interface BriefMessage { text: string; status: BriefStatus; at?: number }
export interface BriefSink { write(msg: BriefMessage): void | Promise<void> }

/** Default sink: print to stdout, tagging proactive messages (the push-eligibility signal). */
export const stdoutBriefSink: BriefSink = {
  write(msg) { process.stdout.write(`[brief${msg.status === "proactive" ? ":proactive" : ""}] ${msg.text}\n`); },
};

const sendUserMessageShape = { message: z.string(), status: z.enum(["normal", "proactive"]).optional() };

/** Exported for direct handler testing (mirrors tasks/server.ts buildTaskTools). */
export function buildBriefTools(sink: BriefSink) {
  return [
    tool("SendUserMessage",
      "Send a user-visible message through the Brief channel. Use status 'proactive' for messages worth a push notification; 'normal' otherwise.",
      sendUserMessageShape,
      async (args) => { await sink.write({ text: args.message, status: args.status ?? "normal" }); return { content: [{ type: "text" as const, text: "delivered" }] }; }),
  ];
}

/** Wrap a BriefSink as an in-process SDK MCP server exposing the SendUserMessage tool. */
export function createBriefMcpServer(sink: BriefSink) {
  return createSdkMcpServer({ name: "cc-brief", version: "0.1.0", tools: buildBriefTools(sink) });
}
