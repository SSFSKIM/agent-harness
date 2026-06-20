"""Director run entrypoint (Phase 1, M4).

`python -m director.run --ticket <stub.json>` drives ONE Codex app-server worker
through one ticket in an isolated workspace. The worker's approval/input requests
go to the Director queue (the main Claude session answers them via director_min);
the turn resumes on each answer. `--mock` swaps in the bundled fake app-server for
an offline end-to-end run; without it the real `codex app-server` is launched.

Stub ticket JSON:  {"id": "STUB-1", "prompt": "...", "workspace"?: "...", "model"?: "..."}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from director import config, taxonomy
from director.decider import autonomous_decide
from director.worker import autonomy, policy as worker_policy, tools as worker_tools
from director.worker.app_server import AppServerClient, ReadTimeout, TurnCancelled
from director.worker.approval import make_seam

DEFAULT_WORKSPACE_ROOT = Path(".claude/harness/director-workspaces")
# Owned by config.DEFAULTS["max_turns"] (single source); a host overrides via
# .harness.json director.max_turns (the --max-turns flag still wins). Multi-turn
# drive bound (R6): a worker that never signals terminal stops here, reported stuck.
DEFAULT_MAX_TURNS = config.DEFAULTS["max_turns"]
_MOCK = str(Path(__file__).resolve().parent / "worker" / "_mock_app_server.py")
_SKILLS_SRC = Path(__file__).resolve().parent / "workspace_skills"


def install_workspace_skills(workspace) -> None:
    """Copy the vendored Codex worker skills into <workspace>/.codex/skills/.

    Safety (completion-gate P1): the per-ticket workspace is reused across runs and
    a prior worker (workspace-write sandbox) can plant symlinks, so we must never
    write THROUGH a pre-existing symlink. A symlinked `.codex`/`skills` parent is
    refused; each skill target is removed (link unlinked, dir/file deleted) before a
    fresh copy — copytree never runs into an attacker-controlled destination.
    Idempotent: always re-copies clean."""
    ws = Path(workspace)
    for parent in (ws / ".codex", ws / ".codex" / "skills"):
        if parent.is_symlink():
            raise RuntimeError(f"refusing to install skills through symlink: {parent}")
    dst = ws / ".codex" / "skills"
    dst.mkdir(parents=True, exist_ok=True)
    for item in _SKILLS_SRC.iterdir():
        if item.name == "ATTRIBUTION.md":
            continue
        target = dst / item.name
        if target.is_symlink() or target.is_file():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def load_ticket(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "id" not in data or "prompt" not in data:
        raise ValueError("stub ticket needs at least 'id' and 'prompt'")
    return {"id": data["id"], "prompt": data["prompt"],
            "model": data.get("model"), "workspace": data.get("workspace")}


def workspace_key(identifier) -> str:
    """Sanitize a board identifier into a single-component workspace directory NAME
    (Symphony §9.5 invariant 3): every character outside `[A-Za-z0-9._-]` becomes `_`, so
    a `/` can no longer split the key into multiple path segments. Note `.` IS allowed, so
    a degenerate id (`""`/`.`/`..`) still yields a key that resolves to the root or its
    parent — sanitization alone is NOT sufficient containment. `is_contained` (applied at
    every derive and every delete site) is the mandatory guard that rejects those."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(identifier))


def workspace_path(identifier, workspace_root) -> Path:
    """The per-ticket workspace path — `<root>/<sanitized key>`. The SINGLE derivation
    used by dispatch (`_workspace_for`), merge-enqueue (`orchestrator._maybe_enqueue_merge`),
    and startup cleanup (`orchestrator._startup_recovery`) so all three agree on the
    directory for a given (id, root) (ARCHITECTURE invariant 8 — shared helper, not
    re-derived per call site)."""
    return Path(workspace_root) / workspace_key(identifier)


def is_contained(path, workspace_root) -> bool:
    """True iff `path` resolves to a STRICT descendant of `workspace_root` — under the
    root AND not the root itself (spec R2b / Symphony §9.5 invariant 2: a workspace is
    "a directory whose parent is the workspace root", never the root). Strictness is
    load-bearing because the cleanup paths `rmtree` this: a degenerate sanitized key
    (`""`/`.`/`..`) resolves to the root or its parent, and must NOT count as a contained
    workspace, or cleanup could delete the entire root (review-security/spec-compliance
    P1). Pure path comparison (no fs writes); shared by dispatch (reject an escaping
    derived path) and cleanup (never rmtree at/above the root). An unresolvable/
    incomparable path is NOT contained (fail safe)."""
    try:
        resolved = Path(path).resolve()
        root = Path(workspace_root).resolve()
        return resolved != root and resolved.is_relative_to(root)
    except (OSError, ValueError):
        return False


def _expected_ws(ticket: dict, workspace_root) -> Path:
    """The workspace path a ticket resolves to — explicit override or derived (sanitized).
    Pure (no mkdir); shared by `_prepare`'s cwd assert and the lifecycle-hook call sites so
    they target the same dir `_workspace_for` creates."""
    return Path(ticket["workspace"]) if ticket.get("workspace") \
        else workspace_path(ticket["id"], workspace_root)


def run_hook(name: str, script, *, cwd, timeout_s: float, fatal: bool) -> None:
    """Run one workspace lifecycle hook (Symphony §9.4) as `sh -lc <script>` with cwd=the
    workspace, under a wall-clock timeout. Director-side (trusted host config — runs with the
    Director's own environment, so a private-repo clone has credential reach). A falsy
    `script` is a no-op. Start/failure/timeout log a structured line to STDERR (the
    daemon-diagnostic stream). On non-zero exit or timeout: if `fatal` (after_create/
    before_run) raise; else (after_run/before_remove) swallow. Never returns a value —
    hooks are side-effecting."""
    if not script:
        return
    print(json.dumps({"hook": name, "event": "start", "cwd": str(cwd)}), file=sys.stderr)
    try:
        proc = subprocess.run(["sh", "-lc", script], cwd=str(cwd), env=os.environ.copy(),
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"hook": name, "event": "timeout", "timeout_s": timeout_s}),
              file=sys.stderr)
        if fatal:
            raise RuntimeError(f"workspace hook {name!r} timed out after {timeout_s}s") from exc
        return
    except OSError as exc:
        # Launch failure (missing `sh`, a `cwd` deleted out from under us by a concurrent
        # session, perms). run_hook must be TOTAL against this family (RELIABILITY R8):
        # a non-fatal hook (after_run/before_remove) MUST swallow it, never crash the reap
        # loop / daemon nor mask a disposition; a fatal hook still raises.
        print(json.dumps({"hook": name, "event": "error", "error": str(exc)}),
              file=sys.stderr)
        if fatal:
            raise RuntimeError(f"workspace hook {name!r} failed to launch: {exc}") from exc
        return
    if proc.returncode != 0:
        print(json.dumps({"hook": name, "event": "failed", "code": proc.returncode,
                          "stderr": (proc.stderr or "")[-2000:]}), file=sys.stderr)
        if fatal:
            raise RuntimeError(f"workspace hook {name!r} failed (exit {proc.returncode})")


def _workspace_for(ticket: dict, workspace_root) -> tuple[Path, bool]:
    explicit = ticket.get("workspace")
    if explicit:
        # Explicit override: the single-ticket-CLI / test affordance (a trusted caller
        # may target an arbitrary path, e.g. /tmp). It is NEVER produced by the Linear
        # daemon path (board ids are always derived), so it is exempt from the
        # containment check below (the board-controlled id is the real escape vector,
        # and workspace_key sanitizes that).
        ws = Path(explicit)
    else:
        ws = workspace_path(ticket["id"], workspace_root)
        # Containment (§9.5 invariant 2): the derived path MUST resolve under the root.
        # workspace_key already guarantees this; the check catches a sanitizer regression
        # before any mkdir or worker launch.
        if not is_contained(ws, workspace_root):
            raise RuntimeError(f"workspace path escapes root: {ws} not under {workspace_root}")
    created_now = not ws.exists()  # captured BEFORE mkdir — drives the after_create hook
    ws.mkdir(parents=True, exist_ok=True)
    return ws, created_now


def _prepare(ticket: dict, *, command, queue_base, workspace_root, timeout_s,
             read_timeout_s, tool_executor, install_skills,
             worker_env: dict | None = None, cancel_event=None,
             hooks: dict | None = None, hook_timeout_s: float = 60.0,
             on_event=None) -> AppServerClient:
    """Build (but do not start) the worker client for one ticket: resolve+create the
    workspace, run the create/run lifecycle hooks, optionally install the vendored skills,
    and wire the approval seam. Shared by the single-turn `run_ticket` and the multi-turn
    `drive`.

    Secure by construction: unless the caller passes an explicit `worker_env`, the
    worker subprocess env is the **deny-by-default** construction from the host policy
    (director/worker/policy.py) — a worker never inherits the Director's host secrets
    (SECURITY.md T11, env-inheritance channel)."""
    hooks = hooks or {}
    ws, created_now = _workspace_for(ticket, workspace_root)
    # after_create (Symphony §9.4): populate a BRAND-NEW workspace (the repo-population
    # clone). FATAL — a worker must never start on a workspace whose population failed.
    if created_now:
        run_hook("after_create", hooks.get("after_create"), cwd=ws,
                 timeout_s=hook_timeout_s, fatal=True)
    # §9.5 invariant 1 (R2d): before launch, the worker's cwd (we pass cwd=ws below) must
    # be a real directory AND resolve to exactly the canonical workspace path. `expected`
    # is re-derived independently of `_workspace_for`, so this catches a future refactor
    # that lets the launch cwd drift off the contained workspace, not just a torn path.
    expected = _expected_ws(ticket, workspace_root)
    if not ws.is_dir():
        raise RuntimeError(f"workspace path is not a directory before launch: {ws}")
    if ws.resolve() != expected.resolve():
        raise RuntimeError(f"launch cwd {ws} != expected workspace {expected}")
    # before_run (Symphony §9.4): runs before EVERY attempt (e.g. sync to origin/main).
    # FATAL — abort the attempt if the pre-run sync fails.
    run_hook("before_run", hooks.get("before_run"), cwd=ws,
             timeout_s=hook_timeout_s, fatal=True)
    if install_skills:
        install_workspace_skills(ws)
    if worker_env is None:
        worker_env = worker_policy.build_worker_env(worker_policy.load_worker_policy())
    seam = make_seam(str(ticket["id"]), str(ws), base=queue_base, timeout_s=timeout_s)
    return AppServerClient(command, cwd=ws, on_server_request=seam,
                           tool_executor=tool_executor, read_timeout_s=read_timeout_s,
                           env=worker_env, cancel_event=cancel_event, on_event=on_event)


def run_ticket(ticket: dict, *, command: list[str], queue_base=None,
               workspace_root=DEFAULT_WORKSPACE_ROOT,
               timeout_s: float = 300.0, read_timeout_s: float = 30.0,
               tools=None, tool_executor=None, install_skills: bool = False,
               approval_policy: str = "untrusted",
               sandbox: str = "workspace-write",
               hooks: dict | None = None, hook_timeout_s: float = 60.0,
               on_event=None) -> dict:
    """Drive one worker through ONE turn; returns {status, turn_id, final_message}.

    The single-turn primitive (kept for callers that want one turn). The multi-turn
    driver is `drive`. `approval_policy`/`sandbox` set the worker's Codex posture on
    thread AND turn (the autonomous preset passes `on-request`/`workspace-write`; the
    default is the conservative watched `untrusted`)."""
    client = _prepare(ticket, command=command, queue_base=queue_base,
                      workspace_root=workspace_root, timeout_s=timeout_s,
                      read_timeout_s=read_timeout_s, tool_executor=tool_executor,
                      install_skills=install_skills, hooks=hooks,
                      hook_timeout_s=hook_timeout_s, on_event=on_event)
    try:
        with client as c:
            c.initialize()
            thread_id = c.thread_start(model=ticket.get("model"), tools=tools,
                                       approval_policy=approval_policy, sandbox=sandbox)
            # `sandbox` is a THREAD-level attribute (set on thread/start only); the turn
            # inherits it, so run_turn takes approval_policy but not sandbox.
            return c.run_turn(thread_id, ticket["prompt"], approval_policy=approval_policy)
    finally:
        # after_run (Symphony §9.4): fires once the attempt ends, on any outcome; logged
        # and ignored (never alters the result).
        run_hook("after_run", (hooks or {}).get("after_run"),
                 cwd=_expected_ws(ticket, workspace_root), timeout_s=hook_timeout_s,
                 fatal=False)


def drive(ticket: dict, *, command: list[str], decide=autonomous_decide,
          queue_base=None, workspace_root=DEFAULT_WORKSPACE_ROOT,
          timeout_s: float = 300.0, read_timeout_s: float = 30.0,
          tools=None, tool_executor=None, install_skills: bool = False,
          approval_policy: str = "untrusted", sandbox: str = "workspace-write",
          max_turns: int = DEFAULT_MAX_TURNS, attempt: int = 1, cancel_event=None,
          hooks: dict | None = None, hook_timeout_s: float = 60.0,
          on_event=None) -> dict:
    """Drive one worker through one ticket across MULTIPLE turns on a SINGLE thread
    until the worker is terminal (or `max_turns` is hit). This is the multi-turn
    slice's core: a ticket is a thread, a turn end is an *event* not a completion,
    and the per-turn disposition is owned by the injected `decide` (LLM/human in a
    watched run; the autonomous code decider un-watched) — never by this code (R4).

    Returns the FINAL disposition, enriched with run facts (incl. a `telemetry`
    block — Symphony-grade per-ticket tokens/turn_count/session_id/last_message/
    rate_limits — present on every kind, plan M2):
      {"kind": "terminal",  "outcome": {...}, "turns", "turn_id", "final_message", "thread_id"}
      {"kind": "escalate",  "reason": str, "outcome"?, "turns", ...}        # taste → human
      {"kind": "stuck",     "reason": "max_turns", "turns", ...}            # R6 bound
      {"kind": "failed",    "status": "failed"|"cancelled", "turns", ...}   # a turn errored

    `report_outcome` is wired in HERE (not by the caller): a per-turn sink captures the
    worker's terminal proposal, composed over any `tool_executor` the caller passed
    (e.g. linear_graphql), and `report_outcome` is appended to the advertised tools."""
    sink: dict = {}
    report_exec = worker_tools.make_report_outcome_executor(sink)

    def combined(name, arguments):
        if name == worker_tools.REPORT_OUTCOME_TOOL:
            return report_exec(name, arguments)
        if tool_executor is not None:
            return tool_executor(name, arguments)
        return {"success": False, "output": f"unsupported tool: {name!r}"}

    advertised = list(tools or [])
    if not any(t.get("name") == worker_tools.REPORT_OUTCOME_TOOL for t in advertised):
        advertised.append(worker_tools.report_outcome_spec())

    client = _prepare(ticket, command=command, queue_base=queue_base,
                      workspace_root=workspace_root, timeout_s=timeout_s,
                      read_timeout_s=read_timeout_s, tool_executor=combined,
                      install_skills=install_skills, cancel_event=cancel_event,
                      hooks=hooks, hook_timeout_s=hook_timeout_s, on_event=on_event)
    turns = 0
    turn_id = None
    thread_id = None
    final_message = None
    usage = None        # latest ABSOLUTE thread token totals (not a sum — §13.5)
    rate_limits = None  # latest rate-limit payload seen

    def _telemetry() -> dict:
        # Symphony-grade per-ticket telemetry (plan M2), folded into every
        # disposition via `base`. session_id = "<thread>-<turn>" (§4.1.6); tokens is
        # the LATEST absolute thread total (codex reports cumulative totals, so the
        # last value IS the ticket total — summing would double-count).
        sid = f"{thread_id}-{turn_id}" if (thread_id and turn_id) else None
        return {"tokens": usage, "turn_count": turns, "session_id": sid,
                "last_message": final_message, "rate_limits": rate_limits}

    def _cancelled() -> dict:
        # Active-run reconciliation stopped this worker (its ticket left `started`).
        # A DISTINCT disposition kind from "failed" so the orchestrator releases it
        # without a retry (D-59/D-62); carries the run facts like every other return.
        return {"kind": "cancelled", "reason": "reconciliation", "turns": turns,
                "turn_id": turn_id, "final_message": final_message,
                "thread_id": thread_id, "telemetry": _telemetry()}

    # after_run (Symphony §9.4) fires once this attempt ends, on ANY return path
    # (terminal/escalate/stuck/failed/cancelled); logged and ignored, never alters the
    # disposition. The finally wraps the whole worker session below.
    try:
        with client as c:
            # Wrap the WHOLE session: a reconciliation cancel can land during the handshake
            # (initialize/thread_start) or mid-turn (run_turn) — both surface as TurnCancelled
            # and must release, not fail-and-retry (D-59).
            try:
                c.initialize()
                thread_id = c.thread_start(model=ticket.get("model"), tools=advertised,
                                           approval_policy=approval_policy, sandbox=sandbox)
                # First turn: frame the ticket with the stage-agnostic WORKER PROTOCOL
                # (operating disciplines) + the multi-turn TURN PROTOCOL (terminal contract)
                # so the worker self-governs and knows to call report_outcome at terminal
                # (else un-watched it would loop to stuck). This single seam covers every
                # dispatch path (orchestrator, run.main, direct-drive). Later turns carry the
                # decider's directive verbatim.
                input_text = taxonomy.frame_first_turn(ticket["prompt"])
                for i in range(max_turns):
                    # Between-turns cancel check (covers the gap while a watched decider was
                    # parked); mid-turn cancellation arrives as TurnCancelled from run_turn.
                    if cancel_event is not None and cancel_event.is_set():
                        return _cancelled()
                    turns = i + 1
                    sink.pop("outcome", None)  # fresh terminal-signal slot for this turn
                    result = c.run_turn(thread_id, input_text, approval_policy=approval_policy)
                    turn_id = result.get("turn_id")
                    final_message = result.get("final_message")
                    if result.get("usage") is not None:        # keep latest absolute totals
                        usage = result["usage"]
                    if result.get("rate_limits") is not None:
                        rate_limits = result["rate_limits"]
                    status = result.get("status")
                    base = {"turns": turns, "turn_id": turn_id,
                            "final_message": final_message, "thread_id": thread_id,
                            "telemetry": _telemetry()}
                    if status != "completed":  # turn/failed | turn/cancelled — not a disposition
                        return {"kind": "failed", "status": status, **base}
                    disp = decide({"ticket": ticket, "turn_index": i, "status": status,
                                   "final_message": final_message, "outcome": sink.get("outcome"),
                                   "attempt": attempt})
                    if disp.get("kind") in ("terminal", "escalate"):
                        return {**disp, **base}
                    # kind == "reply": continue the SAME thread with the directive (board untouched)
                    input_text = disp.get("reply") or ""
            except TurnCancelled:  # mid-turn reconciliation cancel (D-59) — release, no retry
                return _cancelled()
            except ReadTimeout:  # F3: worker silent past read_timeout (cold start / a long
                # command / deep reasoning) — a RECOVERABLE failure, not an uncaught crash;
                # the orchestrator's reconcile retries it like any failed turn (R6 bound).
                return {"kind": "failed", "status": "read_timeout", "turns": turns,
                        "turn_id": turn_id, "final_message": final_message,
                        "thread_id": thread_id, "telemetry": _telemetry()}
        return {"kind": "stuck", "reason": "max_turns", "turns": turns,
                "turn_id": turn_id, "final_message": final_message, "thread_id": thread_id,
                "telemetry": _telemetry()}
    finally:
        run_hook("after_run", (hooks or {}).get("after_run"),
                 cwd=_expected_ws(ticket, workspace_root), timeout_s=hook_timeout_s,
                 fatal=False)


def _command(args, codex_command, posture) -> list[str]:
    if args.mock:
        return [sys.executable, _MOCK, args.mock_scenario]
    # Posture (auto_review / network) is the resolved config's (a host may tighten it
    # in .harness.json director.worker). Exfil deferred (T11).
    # `bash -c` (NOT `-lc`): a LOGIN shell would source the host's profile and re-inject
    # env the deny-by-default boundary (Popen env=) just stripped — defeating it for any
    # secret a user exports in ~/.profile etc. Non-login + `BASH_ENV` denied (not in the
    # base) means the worker's env is exactly the constructed one. The base carries PATH,
    # so codex still resolves (worker-secret-boundary M1, SECURITY.md T11).
    codex = autonomy.codex_command(codex_command, auto_review=posture.auto_review,
                                   network=posture.network)
    return ["bash", "-c", codex]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="director.run")
    ap.add_argument("--ticket", help="path to a stub ticket JSON")
    ap.add_argument("--linear", help="Linear issue id/identifier to read as the ticket")
    ap.add_argument("--mock", action="store_true", help="use the bundled fake app-server")
    ap.add_argument("--mock-scenario", default="plain",
                    choices=["plain", "approval", "approval_done", "report",
                             "tool", "turn_failed"])
    ap.add_argument("--codex", default=None, help="real worker command")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--tools", choices=["none", "linear"], default="none",
                    help="advertise worker tools (linear = linear_graphql)")
    ap.add_argument("--install-skills", action="store_true",
                    help="install vendored .codex/skills into the worker workspace")
    ap.add_argument("--autonomous", action="store_true",
                    help="un-watched: use the code turn-end decider (no live Director "
                         "answers turn ends). Per-action self-governance (on-request + "
                         "auto_review) and full network are shared with the watched default")
    ap.add_argument("--max-turns", type=int, default=None,
                    help="multi-turn drive bound (R6); over it → stuck")
    args = ap.parse_args(argv)

    # Resolve posture / codex / bounds CLI > config > default (declarative-config
    # slice). A malformed .harness.json director block raises here, before any spawn.
    cfg = config.load_director_config()
    codex_command = args.codex if args.codex is not None else cfg.codex_command
    max_turns = args.max_turns if args.max_turns is not None else cfg.max_turns
    queue_dir = args.queue_dir if args.queue_dir is not None else cfg.paths.queue_dir

    if args.linear:
        from director.board.linear import read_issue
        issue = read_issue(args.linear)
        ticket = {"id": issue["identifier"], "prompt": issue["prompt"]}
    elif args.ticket:
        ticket = load_ticket(args.ticket)
    else:
        ap.error("one of --ticket or --linear is required")
    tools = None
    tool_executor = None
    if args.tools == "linear":
        from director.worker.tools import linear_graphql_spec, make_linear_tool_executor
        tools = [linear_graphql_spec()]
        tool_executor = make_linear_tool_executor()
    # Per-action posture is the resolved config's (a host may tighten it in
    # .harness.json director.worker; the command's auto_review/network follow it).
    posture = cfg.posture
    # Workspace lifecycle hooks (R4) from the resolved config — disabled under --mock
    # (the offline fake app-server has no real repo to populate).
    hooks = None if args.mock else cfg.workspace.hooks
    # The single-ticket CLI is un-watched (no orchestrator queue / live Director to
    # answer turn reviews), so it drives with the autonomous code decider.
    disp = drive(ticket, command=_command(args, codex_command, posture),
                 decide=autonomous_decide, queue_base=queue_dir, tools=tools,
                 tool_executor=tool_executor, install_skills=args.install_skills,
                 approval_policy=posture.approval_policy, sandbox=posture.sandbox,
                 max_turns=max_turns, read_timeout_s=cfg.read_timeout_s, hooks=hooks,
                 hook_timeout_s=cfg.workspace.hook_timeout_s)
    print(json.dumps({"ticket": ticket["id"], **disp}))
    return 0 if disp.get("kind") == "terminal" else 1


if __name__ == "__main__":
    raise SystemExit(main())
