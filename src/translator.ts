import type { Outcome, UsageTotals } from "./protocol.js";

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

  /** Wire notifications for ONE streamed (non-result) SDK message. */
  onMessage(m: any): object[] {
    const out: object[] = [];
    const text = extractAssistantText(m);
    if (text) { if (this.held !== undefined) out.push(this.agentMessage(this.held, "commentary")); this.held = text; }
    return out;
  }

  /** Terminal notifications. The final_answer agentMessage is MANDATORY (the Director's primary signal). */
  finalize(result: { text: string; isError: boolean; usage?: UsageTotals; outcome?: Outcome }): object[] {
    if (result.isError) return [{ method: "turn/failed", params: { turn: { id: this.turnId, status: "failed" } } }];
    const out: object[] = [];
    const finalText = result.text || this.held || "";
    if (this.held !== undefined && this.held !== finalText) out.push(this.agentMessage(this.held, "commentary"));
    out.push(this.agentMessage(finalText, "final_answer"));
    if (result.usage) out.push({ method: "thread/tokenUsage/updated", params: { threadId: this.threadId, turnId: this.turnId, tokenUsage: { total: { totalTokens: result.usage.totalTokens, inputTokens: result.usage.inputTokens, outputTokens: result.usage.outputTokens } } } });
    const params: any = { turn: { id: this.turnId, status: "completed" } };
    if (result.outcome) params.outcome = result.outcome;
    out.push({ method: "turn/completed", params });
    return out;
  }
}
