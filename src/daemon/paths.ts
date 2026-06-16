import { homedir } from "node:os";
import { join } from "node:path";

/** Default daemon socket path, overridable via CC_DAEMON_SOCK (env injectable for tests). */
export function daemonSocketPath(env: NodeJS.ProcessEnv = process.env): string {
  if (env.CC_DAEMON_SOCK) return env.CC_DAEMON_SOCK;
  const home = env.HOME ?? homedir();
  return join(home, ".claude", "cc-daemon", "sock");
}
