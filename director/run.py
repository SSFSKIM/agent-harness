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
import sys
from pathlib import Path

from director.worker.app_server import AppServerClient
from director.worker.approval import make_seam

DEFAULT_WORKSPACE_ROOT = Path(".claude/harness/director-workspaces")
_MOCK = str(Path(__file__).resolve().parent / "worker" / "_mock_app_server.py")


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


def run_ticket(ticket: dict, *, command: list[str], queue_base=None,
               workspace_root=DEFAULT_WORKSPACE_ROOT,
               timeout_s: float = 300.0, read_timeout_s: float = 30.0) -> dict:
    """Drive one worker through one ticket; returns the turn result {status, turn_id}."""
    ws = _workspace_for(ticket, workspace_root)
    seam = make_seam(str(ticket["id"]), str(ws), base=queue_base, timeout_s=timeout_s)
    client = AppServerClient(command, cwd=ws, on_server_request=seam,
                             read_timeout_s=read_timeout_s)
    with client as c:
        c.initialize()
        thread_id = c.thread_start(model=ticket.get("model"))
        return c.run_turn(thread_id, ticket["prompt"])


def _command(args) -> list[str]:
    if args.mock:
        return [sys.executable, _MOCK, args.mock_scenario]
    return ["bash", "-lc", args.codex]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="director.run")
    ap.add_argument("--ticket", help="path to a stub ticket JSON")
    ap.add_argument("--linear", help="Linear issue id/identifier to read as the ticket")
    ap.add_argument("--mock", action="store_true", help="use the bundled fake app-server")
    ap.add_argument("--mock-scenario", default="plain", choices=["plain", "approval"])
    ap.add_argument("--codex", default="codex app-server", help="real worker command")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    args = ap.parse_args(argv)

    if args.linear:
        from director.board.linear import read_issue
        issue = read_issue(args.linear)
        ticket = {"id": issue["identifier"], "prompt": issue["prompt"]}
    elif args.ticket:
        ticket = load_ticket(args.ticket)
    else:
        ap.error("one of --ticket or --linear is required")
    result = run_ticket(ticket, command=_command(args), queue_base=args.queue_dir)
    print(json.dumps({"ticket": ticket["id"], **result}))
    return 0 if result.get("status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
