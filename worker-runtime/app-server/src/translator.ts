import type { UsageTotals } from "./protocol.js";

/** Pull the concatenated text of an SDK assistant message; "" if it carries no text block.
 *  Probe-pinned (Task 1): text lives at message.content[] entries with type==="text". */
export function extractAssistantText(m: any): string {
  if (m?.type !== "assistant") return "";
  const content = m?.message?.content;
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content.filter((b: any) => b?.type === "text" && typeof b.text === "string").map((b: any) => b.text).join("");
}

export class TurnTranslator {
  private itemN = 0;
  private held: string | undefined;     // last assistant text, not yet emitted (buffered to suppress dup of final)
  constructor(private threadId: string, private turnId: string) {}

  private nextItem(): string { return `item_${this.turnId}_${++this.itemN}`; }
  private agentMessage(text: string, phase: "commentary" | "final_answer"): object {
    return { method: "item/completed", params: { itemId: this.nextItem(), threadId: this.threadId, turnId: this.turnId, item: { type: "agentMessage", text, phase } } };
  }

  /** A thread/tokenUsage/updated notification carrying the absolute CUMULATIVE totals.
   *  Emitted both by the per-turn usage heartbeat (live mid-turn accrual + keep-alive — without
   *  it the Director only ever sees tokens at turn-end, and a long silent tool run looks like a
   *  hung worker) AND at finalize, so the Director's extract_usage reads ONE shape either way. */
  tokenUsage(usage: UsageTotals): object {
    return { method: "thread/tokenUsage/updated", params: { threadId: this.threadId, turnId: this.turnId, tokenUsage: { total: { totalTokens: usage.totalTokens, inputTokens: usage.inputTokens, outputTokens: usage.outputTokens } } } };
  }

  /** Wire notifications for ONE streamed (non-result) SDK message. */
  onMessage(m: any): object[] {
    const out: object[] = [];
    const text = extractAssistantText(m);
    if (text) { if (this.held !== undefined) out.push(this.agentMessage(this.held, "commentary")); this.held = text; }
    return out;
  }

  /** Terminal notifications. The final_answer agentMessage is MANDATORY (the Director's primary signal).
   *  report_outcome (when advertised) rides item/tool/call like any dynamic tool — it is NOT carried here. */
  finalize(result: { text: string; isError: boolean; usage?: UsageTotals }): object[] {
    if (result.isError) return [{ method: "turn/failed", params: { turn: { id: this.turnId, status: "failed" } } }];
    const out: object[] = [];
    const finalText = result.text || this.held || "";
    if (this.held !== undefined && this.held !== finalText) out.push(this.agentMessage(this.held, "commentary"));
    out.push(this.agentMessage(finalText, "final_answer"));
    if (result.usage) out.push(this.tokenUsage(result.usage));
    out.push({ method: "turn/completed", params: { turn: { id: this.turnId, status: "completed" } } });
    return out;
  }
}
