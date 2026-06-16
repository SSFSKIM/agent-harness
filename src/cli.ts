#!/usr/bin/env -S npx tsx
import { parseArgs, composePrompt } from "./cliArgs.js";
import { createHarness } from "./harness.js";

async function readStdin(): Promise<string | undefined> {
  if (process.stdin.isTTY) return undefined;
  const chunks: Buffer[] = [];
  for await (const c of process.stdin) chunks.push(c as Buffer);
  const s = Buffer.concat(chunks).toString("utf8");
  return s.trim() ? s : undefined;
}

async function main() {
  const { prompt: argPrompt, config } = parseArgs(process.argv.slice(2));
  const stdin = await readStdin();
  const prompt = composePrompt(argPrompt, stdin);
  if (!prompt) { console.error("usage: cc-harness \"<prompt>\" [--model ...] [--output-style ...]"); process.exit(2); }

  const harness = createHarness({ permissionMode: "bypassPermissions", ...config });
  for await (const m of harness.stream(prompt)) {
    const mm = m as any;
    if (mm.type === "assistant") {
      for (const block of mm.message?.content ?? []) if (block.type === "text") process.stdout.write(block.text);
    } else if (mm.type === "result") {
      process.stdout.write("\n");
    }
  }
}
main().catch((e) => { console.error(e); process.exit(1); });
