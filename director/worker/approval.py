"""Phase 1 seam (M3): route a worker's mid-turn approval/input request to the
Director queue and resume the SAME turn on the answer — never killing the turn.

`make_seam(...)` returns the `on_server_request(method, params)` callback that
AppServerClient calls when Codex sends a server-initiated request. The callback
queues the request for the Director (the main Claude session), blocks for the
answer, and returns the mapped result, which AppServerClient sends straight back
to Codex as `{id, result}` so the turn continues. A missing answer within timeout
falls back to the safe default (decline), so a turn never hangs forever (plan R7).
"""
from __future__ import annotations

import datetime
from typing import Callable

import director.queue as dq

# Codex server->client request method -> normalized queue kind.
METHOD_KIND = {
    "item/commandExecution/requestApproval": "commandApproval",
    "item/fileChange/requestApproval": "fileChange",
    "tool/requestUserInput": "userInput",
    "mcpServer/elicitation/request": "elicitation",
}
_APPROVAL_KINDS = ("commandApproval", "fileChange")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _request_id(ticket_id: str, params: dict) -> str:
    turn = params.get("turnId", "?")
    item = params.get("itemId") or params.get("requestId") or "req"
    return f"{ticket_id}|{turn}|{item}"


def _payload(kind: str, params: dict) -> dict:
    if kind == "commandApproval":
        return {"command": params.get("command"), "cwd": params.get("cwd"),
                "reason": params.get("reason")}
    if kind == "fileChange":
        return {"changes": params.get("changes"), "reason": params.get("reason")}
    if kind in ("userInput", "elicitation"):
        return {"questions": params.get("questions") or params.get("message")}
    return dict(params)


def _to_result(kind: str, answer: dict | None):
    """Map the Director's answer to the Codex result shape (or the safe default).

    Approval responses are an OBJECT {"decision": <enum>} — confirmed against the
    Codex app-server generated schema (CommandExecutionRequestApprovalResponse /
    FileChangeRequestApprovalResponse). decision ∈ accept|acceptForSession|decline.
    Input responses carry the answers payload. A missing answer declines (R7)."""
    if kind in _APPROVAL_KINDS:
        decision = "decline" if answer is None else answer.get("decision", "decline")
        return {"decision": decision}
    if answer is None:
        return {}
    return answer.get("answers", {})


def make_seam(ticket_id: str, workspace_path: str, *, base=None,
              timeout_s: float = 300.0,
              now: Callable[[], str] = _now_iso) -> Callable[[str, dict], object]:
    """Build the on_server_request callback for one ticket's worker."""

    def on_server_request(method: str, params: dict):
        kind = METHOD_KIND.get(method, "unknown")
        rid = _request_id(ticket_id, params)
        dq.append_request({
            "request_id": rid,
            "ticket_id": ticket_id,
            "session_id": f"{params.get('threadId')}-{params.get('turnId')}",
            "kind": kind,
            "payload": _payload(kind, params),
            "workspace_path": workspace_path,
            "created_at": now(),
        }, base=base)
        answer = dq.wait_for_answer(rid, base=base, timeout_s=timeout_s)
        return _to_result(kind, answer)

    return on_server_request
