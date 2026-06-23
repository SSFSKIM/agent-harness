import { connectDaemon } from "../daemon/connect.js";
import type { MonitorClient } from "./snapshot.js";

/** The read subset of the daemon client, for the read-only `cc-harness top` dashboard. DaemonClient
 *  extends MonitorClient, so connectDaemon's return is a valid MonitorClient. */
export function daemonMonitorClient(socketPath: string): MonitorClient {
  return connectDaemon(socketPath);
}
