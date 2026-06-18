import { daemonRequest } from "../daemon/client.js";
import type { MonitorClient } from "./snapshot.js";
import type { ListEntry } from "../daemon/types.js";

/** Real MonitorClient backed by the daemon UDS op protocol. Each method is one short-lived connection.
 *  list() surfaces transport errors (no daemon) by rejecting → collect() maps that to { daemonUp: false }. */
export function daemonMonitorClient(socketPath: string): MonitorClient {
  return {
    async list(): Promise<ListEntry[]> {
      const [res] = await daemonRequest(socketPath, { op: "list" });
      if (!res?.ok) throw new Error(res?.error ?? "list failed");
      return res.sessions as ListEntry[];
    },
    async contextUsage(id: string): Promise<unknown> {
      const [res] = await daemonRequest(socketPath, { op: "control", id, frame: { type: "context_usage" } });
      if (!res?.ok) throw new Error(res?.error ?? "context_usage failed"); // collect() catches → ctx stays undefined
      return res.usage;
    },
  };
}
