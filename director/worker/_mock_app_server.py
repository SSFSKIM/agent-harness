#!/usr/bin/env python3
"""Fake Codex app-server for Director worker tests (Phase 1, M2/M3).

Speaks the SPEC §10 line-delimited JSON-RPC on stdin/stdout without Codex, so the
worker client + approval seam can be tested deterministically (plan Approach A).

Scenario (argv[1]):
  - "plain"    : handshake + a plain turn that completes.
  - "approval" : a turn that emits ONE item/commandExecution/requestApproval
                 mid-turn, waits for the client's decision, then resumes the SAME
                 turn (same turnId) to turn/completed. This is the M3 seam proof.
  - "usage"    : each turn emits a thread/tokenUsage/updated with CUMULATIVE
                 (absolute) thread totals that rise per turn (turn n → total n*100),
                 then completes — exercises extract_usage + drive's latest-absolute
                 accumulation (telemetry-capture plan M1/M2).
"""
import json
import sys

THREAD_ID = "thr_mock_1"
TURN_ID = "turn_mock_1"
APPROVAL_ID = 9001  # id of the server-initiated approval request
TOOL_CALL_ID = 9002  # id of the server-initiated dynamic-tool call
REPORT_CALL_ID = 9003  # id of the server-initiated report_outcome dynamic-tool call


def out(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def complete_turn():
    out({"method": "item/completed",
         "params": {"itemId": "msg_1", "threadId": THREAD_ID, "turnId": TURN_ID,
                    "item": {"type": "agentMessage", "text": "done"}}})
    out({"method": "turn/completed",
         "params": {"turn": {"id": TURN_ID, "status": "completed"}}})


def main():
    scenario = sys.argv[1] if len(sys.argv) > 1 else "plain"
    awaiting_approval = False
    awaiting_tool = False
    turn_n = 0  # turns started this session — drives the rising "usage" totals
    while True:  # readline() (not `for line in sys.stdin`) to avoid pipe read-ahead deadlock
        raw = sys.stdin.readline()
        if raw == "":
            break  # EOF: client closed stdin
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line)
        method = msg.get("method")
        mid = msg.get("id")

        if method == "initialize":
            out({"id": mid, "result": {"userAgent": "mock", "platformOs": "test"}})
        elif method == "initialized":
            pass
        elif method == "thread/start":
            out({"id": mid, "result": {"thread": {"id": THREAD_ID}}})
            out({"method": "thread/started", "params": {"thread": {"id": THREAD_ID}}})
        elif method == "turn/start":
            if scenario == "turn_error":
                out({"id": mid, "error": {"code": -32000, "message": "boom"}})
                continue
            out({"id": mid, "result": {"turn": {"id": TURN_ID, "status": "inProgress"}}})
            out({"method": "turn/started", "params": {"turn": {"id": TURN_ID}}})
            if scenario in ("approval", "approval_done"):
                out({"id": APPROVAL_ID,
                     "method": "item/commandExecution/requestApproval",
                     "params": {"itemId": "item_1", "threadId": THREAD_ID,
                                "turnId": TURN_ID, "command": ["rm", "-rf", "/tmp/cache"],
                                "cwd": "/ws",
                                "availableDecisions": ["accept", "decline", "cancel"]}})
                awaiting_approval = True
            elif scenario == "tool":
                out({"id": TOOL_CALL_ID, "method": "item/tool/call",
                     "params": {"tool": "linear_graphql",
                                "arguments": {"query": "query { viewer { id } }"},
                                "itemId": "item_t", "threadId": THREAD_ID,
                                "turnId": TURN_ID}})
                awaiting_tool = True
            elif scenario == "report":
                # terminal-signal proof: the worker calls report_outcome(done) mid-turn,
                # then the turn completes. drive's sink captures it → terminal disposition.
                out({"id": REPORT_CALL_ID, "method": "item/tool/call",
                     "params": {"tool": "report_outcome",
                                "arguments": {"status": "done", "reason": "mock done"},
                                "itemId": "item_r", "threadId": THREAD_ID,
                                "turnId": TURN_ID}})
                awaiting_tool = True
            elif scenario == "turn_failed":
                # mid-turn failure (NOT a turn/start error): drive maps it to kind=failed.
                out({"method": "turn/failed",
                     "params": {"turn": {"id": TURN_ID, "status": "failed"}}})
            elif scenario == "usage":
                # CUMULATIVE thread totals that rise per turn (turn n → total n*100).
                # `total_token_usage` is the absolute-wrapper extract_usage prefers;
                # the latest value (not a sum) is the ticket total (§13.5). Then a
                # report_outcome(done) so an autonomous/orchestrated run terminates in
                # one turn (a scripted decider can still drive ≥2 turns for the
                # latest-absolute proof — the sink signal is just ignored there).
                turn_n += 1
                out({"method": "thread/tokenUsage/updated",
                     "params": {"total_token_usage": {"input_tokens": turn_n * 60,
                                                       "output_tokens": turn_n * 40,
                                                       "total_tokens": turn_n * 100}}})
                out({"id": REPORT_CALL_ID, "method": "item/tool/call",
                     "params": {"tool": "report_outcome",
                                "arguments": {"status": "done", "reason": "mock done"},
                                "itemId": "item_r", "threadId": THREAD_ID,
                                "turnId": TURN_ID}})
                awaiting_tool = True
            else:
                complete_turn()
        elif awaiting_approval and mid == APPROVAL_ID and ("result" in msg or "error" in msg):
            # the client's decision on the approval request -> resume the SAME turn
            out({"method": "serverRequest/resolved",
                 "params": {"threadId": THREAD_ID, "requestId": APPROVAL_ID}})
            awaiting_approval = False
            if scenario == "approval_done":
                # after the approval, signal terminal so a multi-turn drive completes.
                out({"id": REPORT_CALL_ID, "method": "item/tool/call",
                     "params": {"tool": "report_outcome",
                                "arguments": {"status": "done", "reason": "mock done"},
                                "itemId": "item_r", "threadId": THREAD_ID, "turnId": TURN_ID}})
                awaiting_tool = True
            else:
                complete_turn()
        elif awaiting_tool and mid in (TOOL_CALL_ID, REPORT_CALL_ID) \
                and ("result" in msg or "error" in msg):
            # the client's tool result -> resume the SAME turn
            out({"method": "item/completed",
                 "params": {"itemId": "item_t", "threadId": THREAD_ID, "turnId": TURN_ID}})
            complete_turn()
            awaiting_tool = False
        # anything else: ignore


if __name__ == "__main__":
    main()
