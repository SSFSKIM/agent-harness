"""Codex app-server JSON-RPC/stdio client (Phase 1, M2).

Drives one `codex app-server` subprocess (or the test mock) through the SPEC §10
handshake and a turn:  initialize -> initialized -> thread/start -> turn/start ->
stream until turn/completed | turn/failed | turn/cancelled.

Three message shapes on the wire (line-delimited JSON):
  - response to our request : has `id` + `result`/`error`, no `method`
  - notification            : has `method`, no `id`
  - server-initiated request: has `method` AND `id`  -> we MUST reply {id, result}

The last shape is the seam: a mid-turn approval / user-input request. We never
kill the turn for it — we hand it to `on_server_request(method, params)` and send
that callback's return value straight back as the result, so the SAME turn resumes
(M3 makes that callback route to the Director queue).
"""
from __future__ import annotations

import json
import os
import select
import subprocess
from pathlib import Path
from typing import Callable

# Codex server->client request methods that mean "a human-style decision is needed".
APPROVAL_METHODS = (
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
)
INPUT_METHODS = (
    "tool/requestUserInput",
    "mcpServer/elicitation/request",
)


class AppServerError(RuntimeError):
    """The app-server errored or closed unexpectedly."""


class ReadTimeout(RuntimeError):
    """No output from the app-server within read_timeout_s."""


class AppServerClient:
    def __init__(self, command: list[str], cwd: Path | str,
                 on_event: Callable[[dict], None] | None = None,
                 on_server_request: Callable[[str, dict], object] | None = None,
                 read_timeout_s: float = 10.0):
        self.command = command
        self.cwd = str(cwd)
        self.on_event = on_event or (lambda ev: None)
        self.on_server_request = on_server_request
        self.read_timeout_s = read_timeout_s
        self._id = 0
        self._proc: subprocess.Popen | None = None
        self._rbuf = b""  # raw stdout bytes awaiting line framing

    # -- lifecycle --------------------------------------------------------
    def start(self) -> "AppServerClient":
        # binary + unbuffered (bufsize=0): we frame lines ourselves so select()
        # and our buffer never disagree (a buffered readline would hide bytes
        # from select and stall the turn).
        self._proc = subprocess.Popen(
            self.command, cwd=self.cwd,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0)
        return self

    def stop(self) -> None:
        if self._proc is None:
            return
        for stream in (self._proc.stdin, self._proc.stdout):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()
        self._proc = None

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # -- wire I/O ---------------------------------------------------------
    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, msg: dict) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self._proc.stdin.flush()

    def _read_msg(self) -> dict | None:
        """Next JSON message, or None at EOF. Frames lines from a raw byte buffer
        (no buffered readline) so select() governs exactly what we have read."""
        assert self._proc and self._proc.stdout
        while True:
            nl = self._rbuf.find(b"\n")
            if nl >= 0:
                raw, self._rbuf = self._rbuf[:nl], self._rbuf[nl + 1:]
                line = raw.strip()
                if not line:
                    continue
                return json.loads(line.decode("utf-8"))
            ready, _, _ = select.select([self._proc.stdout], [], [], self.read_timeout_s)
            if not ready:
                raise ReadTimeout("no app-server output within read timeout")
            chunk = os.read(self._proc.stdout.fileno(), 65536)
            if not chunk:  # EOF — flush any trailing line
                rest, self._rbuf = self._rbuf.strip(), b""
                return json.loads(rest.decode("utf-8")) if rest else None
            self._rbuf += chunk

    def _handle_server_initiated(self, msg: dict) -> None:
        """Reply to a server-initiated request via on_server_request (the seam)."""
        result = None
        if self.on_server_request is not None:
            result = self.on_server_request(msg["method"], msg.get("params", {}))
        self._send({"id": msg["id"], "result": result})

    def _request(self, method: str, params: dict) -> dict:
        rid = self._next_id()
        self._send({"id": rid, "method": method, "params": params})
        while True:
            msg = self._read_msg()
            if msg is None:
                raise AppServerError(f"app-server closed during {method}")
            if msg.get("method") is not None:
                if "id" in msg:
                    self._handle_server_initiated(msg)
                else:
                    self.on_event({"method": msg["method"], "params": msg.get("params", {})})
                continue
            if msg.get("id") == rid:
                if "error" in msg:
                    raise AppServerError(f"{method} error: {msg['error']}")
                return msg.get("result", {})
            # response to some other id — ignore

    # -- protocol ---------------------------------------------------------
    def initialize(self) -> None:
        self._request("initialize", {
            "clientInfo": {"name": "director", "title": "Director", "version": "0.1.0"},
            "capabilities": {"experimentalApi": True},
        })
        self._send({"method": "initialized", "params": {}})

    def thread_start(self, model: str | None = None,
                     approval_policy: str = "untrusted",
                     sandbox: str = "workspace-write") -> str:  # SandboxMode enum (hyphenated)
        params = {"cwd": self.cwd, "approvalPolicy": approval_policy, "sandbox": sandbox}
        if model:
            params["model"] = model
        return self._request("thread/start", params)["thread"]["id"]

    def run_turn(self, thread_id: str, text: str,
                 approval_policy: str = "untrusted",
                 sandbox_policy: dict | None = None) -> dict:
        """Start a turn and stream to terminal. Returns {status, turn_id}.

        status ∈ {completed, failed, cancelled}. turn_id is captured from the
        turn/start response and confirmed by the terminal notification — this is
        what proves a mid-turn approval did NOT spawn a new turn (M3)."""
        rid = self._next_id()
        params = {"threadId": thread_id, "input": [{"type": "text", "text": text}],
                  "cwd": self.cwd, "approvalPolicy": approval_policy}
        if sandbox_policy:
            params["sandboxPolicy"] = sandbox_policy
        self._send({"id": rid, "method": "turn/start", "params": params})

        turn_id: str | None = None
        while True:
            msg = self._read_msg()
            if msg is None:
                raise AppServerError("app-server closed during turn")
            method = msg.get("method")
            if method is not None and "id" in msg:        # server-initiated request (seam)
                self._handle_server_initiated(msg)
                continue
            if method is not None:                        # notification
                self.on_event({"method": method, "params": msg.get("params", {})})
                if method in ("turn/completed", "turn/failed", "turn/cancelled"):
                    turn_id = turn_id or msg.get("params", {}).get("turn", {}).get("id")
                    return {"status": method.split("/", 1)[1], "turn_id": turn_id}
                continue
            if msg.get("id") == rid:                       # response to turn/start
                turn_id = msg.get("result", {}).get("turn", {}).get("id")
