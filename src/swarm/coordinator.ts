/** System-prompt append that turns a session into the swarm coordinator (30.4). */
export const COORDINATOR_PROMPT = [
  "You are the COORDINATOR of a team of AI teammates.",
  "Use TeamCreate to form a team, spawnTeammate to add workers (each runs as an independent session),",
  "SendMessage to assign or follow up with a teammate, and CheckMessages to read their replies.",
  "Decompose the goal into durable tasks with TaskCreate (set blockedBy for dependencies); a teammate",
  "claims a task by setting it in_progress. Do the planning and integration yourself; delegate the",
  "implementation to teammates and integrate their results.",
  "Poll CheckMessages regularly; answer any permission requests with RespondPermission, and stop a",
  "teammate with ShutdownTeammate when its work is done.",
  "When a teammate sends a plan (kind 'plan'), review it and respond with ApprovePlan — approve to let it",
  "implement, or reject with feedback so it revises.",
].join(" ");

/**
 * Native (per-session) task tools disabled on swarm sessions so the shared `cc-tasks` store is
 * authoritative. Native Task state is keyed by session_id (`~/.claude/tasks/<session_id>/`) and is NOT
 * shared across peer query() sessions, so a teammate using native `TaskCreate` would create a task
 * invisible to the team. See docs/parity/CORRECTIONS-2026-06-16-native-tools.md.
 */
export const NATIVE_TASK_TOOLS = ["TaskCreate", "TaskGet", "TaskList", "TaskUpdate", "TodoWrite"];

/** Default coordinator tool whitelist (30.11): orchestration + tasks + read-only inspection. */
export function coordinatorTools(): string[] {
  return [
    "mcp__cc-swarm__TeamCreate", "mcp__cc-swarm__TeamDelete", "mcp__cc-swarm__spawnTeammate",
    "mcp__cc-swarm__SendMessage", "mcp__cc-swarm__CheckMessages",
    "mcp__cc-swarm__RespondPermission", "mcp__cc-swarm__ShutdownTeammate", "mcp__cc-swarm__ApprovePlan",
    "mcp__cc-tasks__TaskCreate", "mcp__cc-tasks__TaskUpdate", "mcp__cc-tasks__TaskGet", "mcp__cc-tasks__TaskList",
    "Read", "Grep", "Glob",
  ];
}

/** Mutate resolved SDK options to apply the coordinator persona append + tool whitelist. */
export function applyCoordinatorPersona(options: Record<string, unknown>, tools?: string[]): void {
  const sp = options.systemPrompt as { type?: string; preset?: string; append?: string } | string | undefined;
  if (sp && typeof sp === "object") {
    options.systemPrompt = { ...sp, append: (sp.append ? sp.append + "\n\n" : "") + COORDINATOR_PROMPT };
  } else {
    options.systemPrompt = { type: "preset", preset: "claude_code", append: COORDINATOR_PROMPT };
  }
  options.allowedTools = tools ?? coordinatorTools();
}
