import { connect } from "node:net";

/** Send one NDJSON op over the daemon UDS; resolve with all response lines (onLine streams them live). */
export function daemonRequest(socketPath: string, op: unknown, onLine?: (o: unknown) => void): Promise<any[]> {
  return new Promise((resolve, reject) => {
    const lines: any[] = [];
    let buf = "";
    let settled = false;
    const done = () => { if (!settled) { settled = true; resolve(lines); } };
    const fail = (e: Error) => { if (!settled) { settled = true; reject(e); } };
    const sock = connect(socketPath);
    sock.on("connect", () => sock.write(JSON.stringify(op) + "\n"));
    sock.on("data", (d) => {
      buf += d.toString("utf8");
      let nl: number;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl); buf = buf.slice(nl + 1);
        if (!line) continue;
        const o = JSON.parse(line); lines.push(o); onLine?.(o);
      }
    });
    sock.on("end", done);
    sock.on("close", done);  // daemon may close after shutdown without a clean end (settled-guarded)
    sock.on("error", fail);
  });
}
