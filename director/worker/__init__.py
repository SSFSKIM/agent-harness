"""Director worker: drives one Codex app-server process for one ticket.

`app_server.AppServerClient` speaks line-delimited JSON-RPC over stdio (the Codex
app-server protocol, SPEC §10). Server-initiated requests (approvals / user input)
are dispatched to an `on_server_request` callback — that callback is where the
Phase 1 seam (route to the Director, resume on the answer) plugs in (M3).
`_mock_app_server.py` is a test fixture that emits the protocol without Codex.
"""
