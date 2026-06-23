import { Session, type SessionDeps } from "../session/session.js";

export interface DaemonSessionDeps extends SessionDeps {}

/** A daemon-managed Session: adds the daemon's sess-N handle id (used as the error label) on top of the
 *  shared streaming engine. The supervisor attaches its restart end-hook to the inherited `done`. */
export class DaemonSession extends Session {
  readonly id: string;
  constructor(
    id: string,
    deps: DaemonSessionDeps,
    options: Record<string, unknown>,
    now: () => number = Date.now,
    sessionOpts: { contextTool?: boolean; compactTool?: boolean } = {},
  ) {
    super(deps, options, { ...sessionOpts, label: id, now });
    this.id = id;
  }
}
