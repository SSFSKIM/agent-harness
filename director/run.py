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
import shutil
import sys
from pathlib import Path

from director import taxonomy
from director.decider import autonomous_decide
from director.worker import autonomy, policy as worker_policy, tools as worker_tools
from director.worker.app_server import AppServerClient
from director.worker.approval import make_seam

DEFAULT_WORKSPACE_ROOT = Path(".claude/harness/director-workspaces")
DEFAULT_MAX_TURNS = 8  # multi-turn drive bound (R6): a worker that never signals
#                        terminal stops here and is reported stuck.
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


def _workspace_for(ticket: dict, workspace_root) -> Path:
    ws = Path(ticket["workspace"]) if ticket.get("workspace") \
        else Path(workspace_root) / str(ticket["id"])
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _prepare(ticket: dict, *, command, queue_base, workspace_root, timeout_s,
             read_timeout_s, tool_executor, install_skills,
             worker_env: dict | None = None) -> AppServerClient:
    """Build (but do not start) the worker client for one ticket: resolve+create the
    workspace, optionally install the vendored skills, and wire the approval seam.
    Shared by the single-turn `run_ticket` and the multi-turn `drive`.

    Secure by construction: unless the caller passes an explicit `worker_env`, the
    worker subprocess env is the **deny-by-default** construction from the host policy
    (director/worker/policy.py) — a worker never inherits the Director's host secrets
    (SECURITY.md T11, env-inheritance channel)."""
    ws = _workspace_for(ticket, workspace_root)
    if install_skills:
        install_workspace_skills(ws)
    if worker_env is None:
        worker_env = worker_policy.build_worker_env(worker_policy.load_worker_policy())
    seam = make_seam(str(ticket["id"]), str(ws), base=queue_base, timeout_s=timeout_s)
    return AppServerClient(command, cwd=ws, on_server_request=seam,
                           tool_executor=tool_executor, read_timeout_s=read_timeout_s,
                           env=worker_env)


def run_ticket(ticket: dict, *, command: list[str], queue_base=None,
               workspace_root=DEFAULT_WORKSPACE_ROOT,
               timeout_s: float = 300.0, read_timeout_s: float = 30.0,
               tools=None, tool_executor=None, install_skills: bool = False,
               approval_policy: str = "untrusted",
               sandbox: str = "workspace-write") -> dict:
    """Drive one worker through ONE turn; returns {status, turn_id, final_message}.

    The single-turn primitive (kept for callers that want one turn). The multi-turn
    driver is `drive`. `approval_policy`/`sandbox` set the worker's Codex posture on
    thread AND turn (the autonomous preset passes `on-request`/`workspace-write`; the
    default is the conservative watched `untrusted`)."""
    client = _prepare(ticket, command=command, queue_base=queue_base,
                      workspace_root=workspace_root, timeout_s=timeout_s,
                      read_timeout_s=read_timeout_s, tool_executor=tool_executor,
                      install_skills=install_skills)
    with client as c:
        c.initialize()
        thread_id = c.thread_start(model=ticket.get("model"), tools=tools,
                                   approval_policy=approval_policy, sandbox=sandbox)
        # `sandbox` is a THREAD-level attribute (set on thread/start only); the turn
        # inherits it, so run_turn takes approval_policy but not sandbox.
        return c.run_turn(thread_id, ticket["prompt"], approval_policy=approval_policy)


def drive(ticket: dict, *, command: list[str], decide=autonomous_decide,
          queue_base=None, workspace_root=DEFAULT_WORKSPACE_ROOT,
          timeout_s: float = 300.0, read_timeout_s: float = 30.0,
          tools=None, tool_executor=None, install_skills: bool = False,
          approval_policy: str = "untrusted", sandbox: str = "workspace-write",
          max_turns: int = DEFAULT_MAX_TURNS, attempt: int = 1) -> dict:
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
                      install_skills=install_skills)
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

    with client as c:
        c.initialize()
        thread_id = c.thread_start(model=ticket.get("model"), tools=advertised,
                                   approval_policy=approval_policy, sandbox=sandbox)
        # First turn: frame the ticket with the multi-turn terminal contract so the
        # worker knows to call report_outcome at terminal (else un-watched it would
        # loop to stuck). Later turns carry the decider's directive verbatim.
        input_text = taxonomy.with_terminal_contract(ticket["prompt"])
        for i in range(max_turns):
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
    return {"kind": "stuck", "reason": "max_turns", "turns": turns,
            "turn_id": turn_id, "final_message": final_message, "thread_id": thread_id,
            "telemetry": _telemetry()}


def _command(args) -> list[str]:
    if args.mock:
        return [sys.executable, _MOCK, args.mock_scenario]
    # Both modes self-govern per-action (auto_review) AND get full network; the only
    # watched/un-watched difference is the turn-end decider. Exfil deferred (T11).
    # `bash -c` (NOT `-lc`): a LOGIN shell would source the host's profile and re-inject
    # env the deny-by-default boundary (Popen env=) just stripped — defeating it for any
    # secret a user exports in ~/.profile etc. Non-login + `BASH_ENV` denied (not in the
    # base) means the worker's env is exactly the constructed one. The base carries PATH,
    # so codex still resolves (worker-secret-boundary M1, SECURITY.md T11).
    codex = autonomy.codex_command(args.codex)
    return ["bash", "-c", codex]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="director.run")
    ap.add_argument("--ticket", help="path to a stub ticket JSON")
    ap.add_argument("--linear", help="Linear issue id/identifier to read as the ticket")
    ap.add_argument("--mock", action="store_true", help="use the bundled fake app-server")
    ap.add_argument("--mock-scenario", default="plain",
                    choices=["plain", "approval", "approval_done", "report",
                             "tool", "turn_failed"])
    ap.add_argument("--codex", default="codex app-server", help="real worker command")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--tools", choices=["none", "linear"], default="none",
                    help="advertise worker tools (linear = linear_graphql)")
    ap.add_argument("--install-skills", action="store_true",
                    help="install vendored .codex/skills into the worker workspace")
    ap.add_argument("--autonomous", action="store_true",
                    help="un-watched: use the code turn-end decider (no live Director "
                         "answers turn ends). Per-action self-governance (on-request + "
                         "auto_review) and full network are shared with the watched default")
    ap.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS,
                    help="multi-turn drive bound (R6); over it → stuck")
    args = ap.parse_args(argv)

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
    # Per-action posture is the SHARED on-request + auto_review baseline (the command
    # is wrapped with auto_review in _command); only --autonomous adds network.
    policy = autonomy.APPROVAL_POLICY
    sandbox = autonomy.SANDBOX
    # The single-ticket CLI is un-watched (no orchestrator queue / live Director to
    # answer turn reviews), so it drives with the autonomous code decider.
    disp = drive(ticket, command=_command(args), decide=autonomous_decide,
                 queue_base=args.queue_dir, tools=tools, tool_executor=tool_executor,
                 install_skills=args.install_skills, approval_policy=policy,
                 sandbox=sandbox, max_turns=args.max_turns)
    print(json.dumps({"ticket": ticket["id"], **disp}))
    return 0 if disp.get("kind") == "terminal" else 1


if __name__ == "__main__":
    raise SystemExit(main())
