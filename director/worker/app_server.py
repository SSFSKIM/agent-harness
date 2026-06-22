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

from director import config

# The worker-posture FALLBACK defaults below (thread_start / run_turn) derive from
# `config.DEFAULTS["worker"]` — the single source of truth (declarative-config slice;
# autonomy.py uses the same precedent). Sourcing them here rather than re-typing the
# literals means there is exactly ONE copy of "the default posture", so the wire client
# cannot drift from the documented default (the stale hardcoded `"untrusted"` it used to
# carry predated the 2026-06-15 `on-request` decision, SECURITY T11). Evaluated once at
# import; every production caller (director/run.py) passes the resolved posture
# explicitly, so these are exercised only by direct/test callers.
_DEFAULT_APPROVAL_POLICY = config.DEFAULTS["worker"]["approval_policy"]
_DEFAULT_SANDBOX = config.DEFAULTS["worker"]["sandbox"]

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


class TurnCancelled(RuntimeError):
    """The active turn was cancelled out-of-band (a reconciliation `cancel_event`
    fired). DELIBERATELY not an `AppServerError` subclass — `director.run.drive`
    must distinguish a cancel (→ no retry) from a genuine failure (→ retry-once),
    so it catches this exception separately (active-run-reconciliation slice, D-59)."""


# Max latency for observing a mid-turn `cancel_event`: the read wait polls `select`
# in slices no longer than this, so a cancel is seen within ~_CANCEL_POLL_S even
# inside a long turn (spec R4), while still enforcing the read_timeout_s budget.
_CANCEL_POLL_S = 0.5


def normalize_tool_result(result) -> dict:
    """Coerce a tool_executor return into the Codex dynamic-tool result shape
    {success, output, contentItems:[{type:"inputText", text}]} (confirmed against
    the app-server schema: DynamicToolCallOutputContentItem)."""
    if not isinstance(result, dict):
        result = {"success": False, "output": str(result)}
    success = bool(result.get("success", False))
    output = result.get("output")
    if not isinstance(output, str):
        output = json.dumps(result, ensure_ascii=False, default=str)  # never raise here
    items = result.get("contentItems")
    if not isinstance(items, list):
        items = [{"type": "inputText", "text": output}]
    return {"success": success, "output": output, "contentItems": items}


def agent_message_text(params: dict) -> tuple[str, str | None] | None:
    """If a notification's params carry a *completed* agentMessage item, return
    `(text, phase)`; else None. Live-pinned against codex-cli 0.139.0: the agent's
    message arrives as `item/completed` with `item.type=="agentMessage"`, the full
    assembled `text`, and a `phase` ∈ {"commentary","final_answer"} (the streaming
    `item/agentMessage/delta` events are redundant — the completed item has the full
    text). The Director reads the *final_answer* message; commentary is mid-turn
    narration. An empty text (the `item/started` placeholder) is ignored upstream."""
    item = params.get("item")
    if isinstance(item, dict) and item.get("type") == "agentMessage":
        text = item.get("text")
        if isinstance(text, str):
            return text, item.get("phase")
    return None


# Lenient field-name maps for codex token-usage payloads. §13.5 (Symphony SPEC)
# says extract input/output/total "leniently from common field names", because the
# exact casing/keys drift across codex versions — so we accept snake_case, camelCase,
# and the prompt/completion synonyms rather than pinning one schema.
_TOKEN_KEYS = {
    "input": ("input_tokens", "inputTokens", "input", "prompt_tokens", "promptTokens"),
    "output": ("output_tokens", "outputTokens", "output", "completion_tokens", "completionTokens"),
    "total": ("total_tokens", "totalTokens", "total"),
}


def _pluck_tokens(obj) -> dict | None:
    """Pull `{input,output,total}` ints out of a usage-like dict, or None if it
    carries no recognizable token field. `total` is derived from input+output when
    absent. bool is rejected (it is an int subclass — `true` must not pass as 1)."""
    if not isinstance(obj, dict):
        return None
    out: dict = {}
    for canon, names in _TOKEN_KEYS.items():
        for n in names:
            v = obj.get(n)
            if isinstance(v, int) and not isinstance(v, bool):
                out[canon] = v
                break
    if not out:
        return None
    inp, outp = out.get("input", 0), out.get("output", 0)
    return {"input": inp, "output": outp, "total": out.get("total", inp + outp)}


def _absolute_from_wrapper(w) -> dict | None:
    """Absolute `{input,output,total}` from a usage wrapper, or None. codex-cli
    0.139.0 nests `{total:{...}, last:{...}, modelContextWindow}` under `tokenUsage`
    — take `total` (the cumulative thread total), NEVER `last` (the per-turn delta,
    §13.5). Falls back to a flat wrapper (`{totalTokens, inputTokens, ...}`) for
    forward/other shapes."""
    if not isinstance(w, dict):
        return None
    nested = _pluck_tokens(w.get("total"))  # codex 0.139.0: tokenUsage.total
    if nested is not None:
        return nested
    return _pluck_tokens(w)  # flat wrapper


def extract_usage(method: str, params: dict) -> dict | None:
    """Absolute thread token totals `{input,output,total}` from a codex notification,
    or None. Live-pinned to codex-cli 0.139.0: `thread/tokenUsage/updated` carries
    `params.tokenUsage = {total:{totalTokens,inputTokens,outputTokens,...}, last:{...}}`
    — read `.total` (absolute), ignore `.last` (per-turn delta). §13.5 rules:

      - an explicit absolute-total wrapper (`total_token_usage`) is trusted on ANY
        event (its name says "total");
      - the generic `tokenUsage`/`usage` wrapper is trusted ONLY on the dedicated
        `thread/tokenUsage/updated` notification (a generic `usage` map elsewhere is
        not necessarily cumulative);
      - delta-style payloads (a lone `last_token_usage`) are IGNORED — counting them
        would double-count the run aggregate.

    Tolerant by contract (plan R6): an unknown shape, a missing field, or a
    non-dict params yields None and NEVER raises — telemetry is instrumentation,
    never a gate (mirrors `agent_message_text`, live-pinned to codex-cli 0.139.0)."""
    if not isinstance(params, dict):
        return None
    for k in ("total_token_usage", "totalTokenUsage"):  # absolute wrapper, any event
        tot = _absolute_from_wrapper(params.get(k))
        if tot is not None:
            return tot
    if method == "thread/tokenUsage/updated":
        for k in ("tokenUsage", "token_usage", "usage"):  # nested/flat absolute usage
            tot = _absolute_from_wrapper(params.get(k))
            if tot is not None:
                return tot
        # A payload that carries ONLY a delta (last_token_usage) is not a total.
        if "last_token_usage" in params or "lastTokenUsage" in params:
            if not any(n in params for grp in _TOKEN_KEYS.values() for n in grp):
                return None
        return _pluck_tokens(params)  # flat absolute totals on the notification
    return None


def extract_rate_limits(params: dict):
    """The latest rate-limit payload carried by a notification, or None (§13.5:
    'track the latest rate-limit payload seen in any agent update'). Stored raw —
    presentation is out of scope."""
    if not isinstance(params, dict):
        return None
    for k in ("rate_limits", "rateLimits", "rate_limit", "rateLimit"):
        v = params.get(k)
        if v is not None:
            return v
    return None


class AppServerClient:
    def __init__(self, command: list[str], cwd: Path | str,
                 on_event: Callable[[dict], None] | None = None,
                 on_server_request: Callable[[str, dict], object] | None = None,
                 tool_executor: Callable[[str, dict], dict] | None = None,
                 read_timeout_s: float = 10.0,
                 env: dict | None = None,
                 cancel_event=None):
        self.command = command
        # ABSOLUTE cwd is load-bearing across the stdio boundary: `cwd` is BOTH the
        # subprocess working dir AND sent verbatim as `thread/start` params.cwd. The host
        # default workspace root is relative (run.DEFAULT_WORKSPACE_ROOT); a Claude worker
        # is already launched IN this dir, then re-resolves params.cwd against its OWN cwd —
        # a relative path double-resolves to a nonexistent dir and the SDK spawn dies with
        # `ENOENT` (mislabeled "libc mismatch"). A cross-process path must be absolute.
        self.cwd = os.path.abspath(str(cwd))
        # The worker subprocess environment. `None` inherits the parent env (legacy /
        # direct callers); the spawn seam (run._prepare) passes a deny-by-default env
        # so a worker never inherits host secrets (director/worker/policy.py, T11).
        self.env = env
        self.on_event = on_event or (lambda ev: None)
        self.on_server_request = on_server_request
        self.tool_executor = tool_executor
        self.read_timeout_s = read_timeout_s
        # Optional reconciliation cancel signal (threading.Event). When set, the read
        # wait raises TurnCancelled so the orchestrator can stop a worker whose ticket
        # a human moved out of `started` mid-flight (active-run-reconciliation, D-59).
        self._cancel_event = cancel_event
        self._id = 0
        self._proc: subprocess.Popen | None = None
        self._rbuf = b""  # raw stdout bytes awaiting line framing

    # -- lifecycle --------------------------------------------------------
    def start(self) -> "AppServerClient":
        # binary + unbuffered (bufsize=0): we frame lines ourselves so select()
        # and our buffer never disagree (a buffered readline would hide bytes
        # from select and stall the turn).
        self._proc = subprocess.Popen(
            self.command, cwd=self.cwd, env=self.env,
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
            try:
                self._proc.wait(timeout=5)  # reap the child on the hard-kill path
            except Exception:
                pass
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

    def _wait_readable(self) -> None:
        """Block until stdout is readable. Polls `select` in slices ≤ _CANCEL_POLL_S so
        a mid-turn `cancel_event` is observed within ~that slice (raising TurnCancelled,
        spec R4), while still enforcing read_timeout_s of total inactivity (raising
        ReadTimeout). Equivalent to one `select(read_timeout_s)` when no cancel_event is
        wired — just woken periodically to check the flag."""
        assert self._proc and self._proc.stdout
        waited = 0.0
        while True:
            if self._cancel_event is not None and self._cancel_event.is_set():
                raise TurnCancelled("turn cancelled by reconciliation")
            remaining = self.read_timeout_s - waited
            if remaining <= 0:
                raise ReadTimeout("no app-server output within read timeout")
            slice_s = min(_CANCEL_POLL_S, remaining)
            ready, _, _ = select.select([self._proc.stdout], [], [], slice_s)
            if ready:
                return
            waited += slice_s

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
            self._wait_readable()  # blocks until readable; raises ReadTimeout/TurnCancelled
            chunk = os.read(self._proc.stdout.fileno(), 65536)
            if not chunk:  # EOF — flush any trailing line
                rest, self._rbuf = self._rbuf.strip(), b""
                return json.loads(rest.decode("utf-8")) if rest else None
            self._rbuf += chunk

    def _handle_server_initiated(self, msg: dict) -> None:
        """Reply to a server-initiated request: a Codex dynamic-tool call
        (`item/tool/call`) goes to tool_executor; approval/input requests go to
        on_server_request (the Phase 1 seam). Same channel, routed by method."""
        method = msg["method"]
        params = msg.get("params", {})
        if method == "item/tool/call":
            result = self._run_tool(params)
        else:
            result = None
            if self.on_server_request is not None:
                result = self.on_server_request(method, params)
        self._send({"id": msg["id"], "result": result})

    def _run_tool(self, params: dict) -> dict:
        name = params.get("tool") or params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str) or self.tool_executor is None:
            return normalize_tool_result(
                {"success": False, "output": f"unsupported tool call: {name!r}"})
        try:
            result = self.tool_executor(name, arguments)
        except Exception as exc:  # a tool must never crash the turn
            result = {"success": False, "output": f"tool {name!r} raised: {exc}"}
        return normalize_tool_result(result)

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
                     approval_policy: str = _DEFAULT_APPROVAL_POLICY,
                     sandbox: str = _DEFAULT_SANDBOX,  # SandboxMode enum (hyphenated)
                     tools: list[dict] | None = None) -> str:
        params: dict = {"cwd": self.cwd, "approvalPolicy": approval_policy, "sandbox": sandbox}
        if model:
            params["model"] = model
        if tools:
            params["dynamicTools"] = tools  # [{name, description, inputSchema}]
        return self._request("thread/start", params)["thread"]["id"]

    def run_turn(self, thread_id: str, text: str,
                 approval_policy: str = _DEFAULT_APPROVAL_POLICY,
                 sandbox_policy: dict | None = None) -> dict:
        """Start a turn and stream to terminal. Returns {status, turn_id,
        final_message, usage, rate_limits}.

        status ∈ {completed, failed, cancelled}. turn_id is captured from the
        turn/start response and confirmed by the terminal notification — this is
        what proves a mid-turn approval did NOT spawn a new turn (M3). final_message
        is the agent's turn-end assistant text (the Director's primary input for the
        next-turn disposition — multi-turn slice R2/R7): the last `final_answer`
        agentMessage, falling back to the last non-empty agentMessage of any phase,
        or None if the turn produced no message."""
        rid = self._next_id()
        params: dict = {"threadId": thread_id, "input": [{"type": "text", "text": text}],
                        "cwd": self.cwd, "approvalPolicy": approval_policy}
        if sandbox_policy:
            params["sandboxPolicy"] = sandbox_policy
        self._send({"id": rid, "method": "turn/start", "params": params})

        turn_id: str | None = None
        final_answer: str | None = None   # last phase=="final_answer" agentMessage
        last_message: str | None = None   # last non-empty agentMessage (any phase) — fallback
        usage: dict | None = None          # latest absolute thread token totals (§13.5)
        rate_limits = None                 # latest rate-limit payload seen (§13.5)
        while True:
            msg = self._read_msg()
            if msg is None:
                raise AppServerError("app-server closed during turn")
            method = msg.get("method")
            if method is not None and "id" in msg:        # server-initiated request (seam)
                self._handle_server_initiated(msg)
                continue
            if method is not None:                        # notification
                mparams = msg.get("params", {})
                self.on_event({"method": method, "params": mparams})
                # Telemetry capture (plan M1): the usage/rate-limit events stream by
                # on the same channel. We keep the LATEST absolute totals (not a sum):
                # codex reports cumulative thread totals, so the last value IS the total.
                u = extract_usage(method, mparams)
                if u is not None:
                    usage = u
                rl = extract_rate_limits(mparams)
                if rl is not None:
                    rate_limits = rl
                if method == "item/completed":
                    am = agent_message_text(mparams)
                    if am is not None:
                        msg_text, phase = am
                        if msg_text:
                            last_message = msg_text
                            if phase == "final_answer":
                                final_answer = msg_text
                if method in ("turn/completed", "turn/failed", "turn/cancelled"):
                    turn_id = turn_id or mparams.get("turn", {}).get("id")
                    return {"status": method.split("/", 1)[1], "turn_id": turn_id,
                            "final_message": final_answer or last_message,
                            "usage": usage, "rate_limits": rate_limits}
                continue
            if msg.get("id") == rid:                       # response to turn/start
                if "error" in msg:
                    raise AppServerError(f"turn/start error: {msg['error']}")
                turn_id = msg.get("result", {}).get("turn", {}).get("id")
