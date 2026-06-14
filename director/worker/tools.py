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

LINEAR_TOOL = "linear_graphql"


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
        http_post: Callable[[str, bytes, dict], dict] = linear.urllib_post
) -> Callable[[str, dict], dict]:
    """A tool_executor `(name, arguments) -> {success, output}` handling linear_graphql."""
    key = api_key or linear.load_api_key()

    def execute(name: str, arguments: dict) -> dict:
        if name != LINEAR_TOOL:
            return {"success": False, "output": f"unsupported tool: {name!r}"}
        if not key:
            return {"success": False, "output": "LINEAR_API_KEY not found (env or .env)"}
        query = (arguments or {}).get("query")
        if not isinstance(query, str) or not query.strip():
            return {"success": False, "output": "linear_graphql requires a non-empty 'query'"}
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
