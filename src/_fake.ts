import type { OpenFn } from "./handlers.js";
import type { OutcomeHolder } from "./tools.js";

/** Scripted, key-free session used ONLY when CC_APPSERVER_FAKE==="1" (bin/contract tests). It populates the
 *  injected outcome holder exactly as the real report_outcome tool would, so the outcome path is exercised. */
export const fakeOpen: OpenFn = (_cfg: any, holder: OutcomeHolder) => ({
  submit: async (prompt: string, onMessage: (m: any) => void) => {
    onMessage({ type: "assistant", message: { content: [{ type: "text", text: "thinking" }] } });
    if (prompt.includes("REPORT")) holder.outcome = { status: "done", reason: "mock" };
    return { result: "final text" };
  },
  usage: async () => ({}),
  dispose: async () => {},
} as any);
