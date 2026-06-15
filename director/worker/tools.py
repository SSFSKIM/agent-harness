"""Worker-side dynamic tools (Phase 2, W2).

`linear_graphql` lets a Codex worker run raw Linear GraphQL (read/write) during a
turn — the same client-advertised tool Symphony exposes. The client advertises the
spec in thread/start (`dynamicTools`) and routes `item/tool/call` to the executor
built here. Auth + HTTP reuse director.board.linear (raw `Authorization` key from
`.env`, stdlib urllib, injectable http_post for tests). A top-level GraphQL
`errors` array is a FAILED tool call even when the HTTP call itself succeeded
(per Symphony's linear skill contract).
"""
from __future__ import annotations

import json
from typing import Callable

from director.board import linear
from director.worker import authority

LINEAR_TOOL = "linear_graphql"

REPORT_OUTCOME_TOOL = "report_outcome"
REPORT_OUTCOME_STATUSES = ("done", "blocked", "needs_human")


def report_outcome_spec() -> dict:
    """DynamicToolSpec for the worker's TERMINAL signal (multi-turn slice, D-44).

    Narrowed to terminal outcomes on purpose: done / blocked(+children) / needs_human.
    The worker does NOT call this to ask "should I continue?" — a non-terminal turn
    end is read directly from the final assistant message and the Director answers
    free-form (D-45). So this tool is the reliable structured channel ONLY for the
    moment work actually ends."""
    return {
        "name": REPORT_OUTCOME_TOOL,
        "description": "Report the TERMINAL outcome of your work on THIS ticket. Call "
                       "it exactly once, only when work truly ends: status=done when "
                       "the ticket is complete; status=blocked when you cannot proceed "
                       "and have filed follow-up tickets (put their ids in "
                       "spawned_ticket_ids); status=needs_human when a product/taste "
                       "decision is required. Do NOT call it to ask whether to continue "
                       "— just keep working; your turn-end message is read directly.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["status", "reason"],
            "properties": {
                "status": {"type": "string", "enum": list(REPORT_OUTCOME_STATUSES)},
                "reason": {"type": "string",
                           "description": "One line: why this is the outcome."},
                "spawned_ticket_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Ids of tickets you created (e.g. when blocked → "
                                   "decomposed into follow-ups)."},
            },
        },
    }


def make_report_outcome_executor(sink: dict) -> Callable[[str, dict], dict]:
    """A tool_executor for `report_outcome` that records the worker's PROPOSED
    terminal outcome into `sink` (a mutable dict owned by the drive loop) and returns
    success to the worker. The drive loop clears `sink` before each turn and reads
    `sink.get("outcome")` after — so the structured terminal signal travels the same
    `item/tool/call` path as linear_graphql (D-44), with no prose parsing. The worker
    only *proposes*; the Director/orchestrator *executes* the board transition (D-40)."""
    def execute(name: str, arguments: dict) -> dict:
        if name != REPORT_OUTCOME_TOOL:
            return {"success": False, "output": f"unsupported tool: {name!r}"}
        status = (arguments or {}).get("status")
        if status not in REPORT_OUTCOME_STATUSES:
            return {"success": False,
                    "output": f"report_outcome status must be one of "
                              f"{list(REPORT_OUTCOME_STATUSES)}"}
        sink["outcome"] = {
            "status": status,
            "reason": (arguments or {}).get("reason"),
            "spawned_ticket_ids": (arguments or {}).get("spawned_ticket_ids") or [],
        }
        return {"success": True, "output": "outcome recorded"}
    return execute


def tool_dispatcher(executors: dict) -> Callable[[str, dict], dict]:
    """Route a dynamic-tool call to the executor registered under its tool name.

    `executors` is {tool_name: executor}. Lets one worker advertise several tools
    (e.g. linear_graphql + report_outcome) behind the single `tool_executor` the
    AppServerClient calls — each underlying executor still self-checks its name."""
    def execute(name: str, arguments: dict) -> dict:
        fn = executors.get(name)
        if fn is None:
            return {"success": False, "output": f"unsupported tool: {name!r}"}
        return fn(name, arguments)
    return execute


def linear_graphql_spec() -> dict:
    """DynamicToolSpec advertised in thread/start (name/description/inputSchema)."""
    return {
        "name": LINEAR_TOOL,
        "description": "Execute a raw GraphQL query or mutation against Linear "
                       "using the session's configured auth.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["query"],
            "properties": {
                "query": {"type": "string",
                          "description": "GraphQL query or mutation document."},
                "variables": {"type": ["object", "null"],
                              "description": "Optional GraphQL variables object.",
                              "additionalProperties": True},
            },
        },
    }


def make_linear_tool_executor(
        api_key: str | None = None,
        endpoint: str = linear.DEFAULT_ENDPOINT,
        http_post: Callable[[str, bytes, dict], dict] = linear.urllib_post,
        allow_mutations: frozenset[str] | None = None,
        guard: bool = True,
) -> Callable[[str, dict], dict]:
    """A tool_executor `(name, arguments) -> {success, output}` handling linear_graphql.

    The authority guardrail is ON by default (`guard=True`): reads pass, only
    allowlisted forward-only mutations go out, destructive/unknown mutations are
    refused locally before any POST (director.worker.authority; spec D-28). Pass
    `guard=False` only for a trusted, explicit opt-out.
    """
    key = api_key or linear.load_api_key()

    def execute(name: str, arguments: dict) -> dict:
        if name != LINEAR_TOOL:
            return {"success": False, "output": f"unsupported tool: {name!r}"}
        if not key:
            return {"success": False, "output": "LINEAR_API_KEY not found (env or .env)"}
        query = (arguments or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            return {"success": False, "output": "linear_graphql requires a non-empty 'query'"}
        if guard:  # authority boundary — refuse before any network side effect
            verdict = authority.authorize(query, allow_mutations=allow_mutations)
            if not verdict["allowed"]:
                return {"success": False, "output": "blocked by authority guardrail: "
                        + verdict["reason"]}
        variables = (arguments or {}).get("variables") or {}
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        headers = {"Authorization": key, "Content-Type": "application/json"}
        try:
            resp = http_post(endpoint, body, headers)
        except Exception as exc:
            return {"success": False, "output": f"linear request failed: {exc}"}
        if resp.get("errors"):
            return {"success": False, "output": json.dumps({"errors": resp["errors"]})}
        return {"success": True, "output": json.dumps(resp.get("data", resp))}

    return execute
