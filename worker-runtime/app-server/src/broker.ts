import { createSdkMcpServer, tool } from "@anthropic-ai/claude-agent-sdk";
import { z } from "zod";
import type { Peer } from "./peer.js";
import type { DynamicToolSpec } from "./protocol.js";

// One in-process MCP server fronts EVERY Director-advertised dynamic tool. Each tool's handler does NOT
// execute anything locally — it relays the call back to the client (Director) via the codex `item/tool/call`
// server→client request, exactly like `codex app-server` does. The client's executor (e.g. authority.py +
// the Linear key, both Director-side) runs the tool and replies; we only translate. This is what makes the
// server a faithful drop-in: dynamic tools, their guardrails, and their credentials all stay on the consumer.
const DYN_SERVER = "cc-dyn";
/** Model-facing MCP tool name for an advertised dynamic tool. Namespace-qualified so two namespaces can carry
 *  same-named tools without colliding in the single in-process server. */
export const dynamicToolName = (name: string, namespace?: string): string => (namespace ? `${namespace}__${name}` : name);
export const dynamicToolId = (name: string, namespace?: string): string => `mcp__${DYN_SERVER}__${dynamicToolName(name, namespace)}`;

/** The client's `item/tool/call` reply (codex shape: contentItems + success; Director also adds `output`). */
export interface DynamicToolResult {
  success?: boolean;
  output?: string;
  contentItems?: Array<{ type: string; text?: string; imageUrl?: string }>;
}

interface NormTool { namespace?: string; name: string; description: string; inputSchema: any }

/** Flatten the codex `DynamicToolSpec` union into individually-callable tools. The canonical spec is a tagged
 *  union {type:"function"|"namespace"}, but codex's own deserializer ALSO accepts the flat
 *  {name,description,inputSchema} form the Director sends — so we detect by shape: a `tools` array ⇒ a
 *  namespace spec (expand its inner function tools, tagging each with the namespace); otherwise a single
 *  function tool (flat or {type:"function"}). */
export function normalizeSpecs(specs: DynamicToolSpec[] | undefined): NormTool[] {
  const out: NormTool[] = [];
  for (const s of specs ?? []) {
    const a = s as any;
    if (Array.isArray(a?.tools)) {
      for (const t of a.tools) if (t?.name) out.push({ namespace: a.name, name: t.name, description: t.description ?? "", inputSchema: t.inputSchema });
    } else if (a?.name) {
      out.push({ namespace: a.namespace, name: a.name, description: a.description ?? "", inputSchema: a.inputSchema });
    }
  }
  return out;
}

/** Relays a dynamic-tool invocation to the client over item/tool/call, emitting the documented
 *  item/started → request → item/completed lifecycle. Construct once per thread; turnId is read live. */
export class ToolBroker {
  private callN = 0;
  constructor(private peer: Peer, private threadId: string, private turnId: () => string) {}

  async call(toolName: string, args: unknown, namespace?: string): Promise<DynamicToolResult> {
    const threadId = this.threadId;
    const turnId = this.turnId();
    const callId = `call_${threadId}_${++this.callN}`;
    // The codex ThreadItem.dynamicToolCall shape: `id` (not callId) is the stable identifier clients correlate on.
    const item = (status: string, extra: Record<string, unknown> = {}) => ({ type: "dynamicToolCall", id: callId, ...(namespace ? { namespace } : {}), tool: toolName, arguments: args, status, ...extra });
    this.peer.notify("item/started", { item: item("inProgress"), threadId, turnId, startedAtMs: Date.now() });
    const reqParams: Record<string, unknown> = { threadId, turnId, callId, tool: toolName, arguments: args };
    if (namespace) reqParams.namespace = namespace;
    const resp = await this.peer.request("item/tool/call", reqParams);
    const result: DynamicToolResult = resp.error
      ? { success: false, contentItems: [{ type: "inputText", text: `tool error: ${resp.error.message}` }] }
      : ((resp.result as DynamicToolResult) ?? {});
    const ok = result.success !== false;
    this.peer.notify("item/completed", { item: item(ok ? "completed" : "failed", { contentItems: result.contentItems ?? [], success: ok }), threadId, turnId, completedAtMs: Date.now() });
    return result;
  }
}

/** Flatten the client's reply into the single text block an SDK MCP tool result carries. */
function resultText(r: DynamicToolResult): string {
  if (Array.isArray(r.contentItems) && r.contentItems.length) return r.contentItems.map((c) => c?.text ?? "").join("");
  if (typeof r.output === "string") return r.output;
  return JSON.stringify(r ?? {});
}

// Best-effort JSON-Schema → Zod shape. This drives ONLY the model-facing tool schema (what fields the model
// is told to send). It is NOT a security boundary — the real gate is the client's executor/guardrail on the
// round-trip — so an imprecise conversion is safe (worst case: the client's executor rejects bad arguments).
function nodeToZod(node: any): z.ZodTypeAny {
  if (!node || typeof node !== "object") return z.any();
  let type = node.type;
  let nullable = false;
  if (Array.isArray(type)) { nullable = type.includes("null"); type = type.find((t: any) => t !== "null"); }
  let base: z.ZodTypeAny;
  if (Array.isArray(node.enum) && node.enum.length && node.enum.every((v: any) => typeof v === "string")) {
    base = z.enum(node.enum as [string, ...string[]]);
  } else {
    switch (type) {
      case "string": base = z.string(); break;
      case "integer": case "number": base = z.number(); break;
      case "boolean": base = z.boolean(); break;
      case "array": base = z.array(node.items ? nodeToZod(node.items) : z.any()); break;
      case "object": base = z.record(z.string(), z.any()); break;
      default: base = z.any();
    }
  }
  if (typeof node.description === "string") base = base.describe(node.description);
  return nullable ? base.nullable() : base;
}

export function jsonSchemaToZodShape(schema: any): Record<string, z.ZodTypeAny> {
  const shape: Record<string, z.ZodTypeAny> = {};
  const props = schema && typeof schema === "object" && schema.properties && typeof schema.properties === "object" ? schema.properties : {};
  const required: string[] = Array.isArray(schema?.required) ? schema.required : [];
  for (const [key, node] of Object.entries(props)) {
    const z0 = nodeToZod(node);
    shape[key] = required.includes(key) ? z0 : z0.optional();
  }
  return shape;
}

export function buildDynamicToolServer(specs: DynamicToolSpec[], broker: ToolBroker) {
  const tools = normalizeSpecs(specs).map((nt) =>
    tool(dynamicToolName(nt.name, nt.namespace), nt.description, jsonSchemaToZodShape(nt.inputSchema), async (args: any) => {
      const r = await broker.call(nt.name, args ?? {}, nt.namespace);
      return { content: [{ type: "text" as const, text: resultText(r) }], isError: r.success === false };
    }),
  );
  return createSdkMcpServer({ name: DYN_SERVER, version: "0.1.0", tools });
}

/** COPY of cfg with the dynamic-tool broker server + its allowed tool ids merged (never mutates). */
export function withDynamicTools(cfg: any, specs: DynamicToolSpec[], broker: ToolBroker): any {
  const norm = normalizeSpecs(specs);
  if (!norm.length) return cfg;
  const existing = (cfg.mcpServers as Record<string, unknown> | undefined) ?? {};
  const allowed = (cfg.allowedTools as string[] | undefined) ?? [];
  return {
    ...cfg,
    mcpServers: { ...existing, [DYN_SERVER]: buildDynamicToolServer(specs, broker) },
    allowedTools: [...new Set([...allowed, ...norm.map((nt) => dynamicToolId(nt.name, nt.namespace))])],
  };
}
