/** System-prompt append that turns a session into the swarm coordinator (30.4). */
export const COORDINATOR_PROMPT = [
  "You are the COORDINATOR of a team of AI teammates.",
  "Use TeamCreate to form a team, spawnTeammate to add workers (each runs as an independent session),",
  "SendMessage to assign or follow up with a teammate, and CheckMessages to read their replies.",
  "Decompose the goal into durable tasks with TaskCreate (set blockedBy for dependencies); a teammate",
  "claims a task by setting it in_progress. Do the planning and integration yourself; delegate the",
  "implementation to teammates and integrate their results.",
].join(" ");

/** Default coordinator tool whitelist (30.11): orchestration + tasks + read-only inspection. */
export function coordinatorTools(): string[] {
  return [
    "mcp__cc-swarm__TeamCreate", "mcp__cc-swarm__TeamDelete", "mcp__cc-swarm__spawnTeammate",
    "mcp__cc-swarm__SendMessage", "mcp__cc-swarm__CheckMessages",
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
