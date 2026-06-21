// Codex v2 JSON-RPC "lite": NDJSON, no "jsonrpc" field.
export interface RpcError { code: number; message: string; data?: unknown }
export interface RpcRequest { id: number | string; method: string; params?: unknown }
export interface RpcNotification { method: string; params?: unknown }
export interface RpcResponse { id: number | string; result?: unknown; error?: RpcError }
export type Incoming = RpcRequest | RpcNotification | RpcResponse;

export function isRequest(m: any): m is RpcRequest { return !!m && typeof m.method === "string" && m.id !== undefined && m.id !== null; }
export function isNotification(m: any): m is RpcNotification { return !!m && typeof m.method === "string" && (m.id === undefined || m.id === null); }
export function isResponse(m: any): m is RpcResponse { return !!m && typeof m.method !== "string" && m.id !== undefined && m.id !== null; }

export interface DynamicToolSpec { name: string; description?: string; inputSchema?: Record<string, unknown> }
export interface ThreadStartParams { cwd: string; approvalPolicy?: string; sandbox?: string; model?: string; dynamicTools?: DynamicToolSpec[] }
export interface TurnStartParams { threadId: string; input: Array<{ type: string; text?: string }>; cwd?: string; approvalPolicy?: string; sandboxPolicy?: unknown }
export interface UsageTotals { totalTokens: number; inputTokens: number; outputTokens: number }

// JSON-RPC error codes used by the server.
export const ERR = { PARSE: -32700, INVALID_REQUEST: -32600, METHOD_NOT_FOUND: -32601, INVALID_PARAMS: -32602, INTERNAL: -32603 } as const;
