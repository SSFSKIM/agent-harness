"""Park notifier — webhook the human when a Director run needs them.

The lights-out "reach an absent human" channel (spec 2026-06-18-director-operator-
console, R4): tail the Director queue and POST a configured webhook ONCE per new
human-bound pending request, so a parked run pings you off-session. The operator
console (`director/dashboard.py`) is where you then *answer*; this is just the ping.

Design (spec D-4/D-5): network egress is isolated HERE, not folded into
`director.watch` (whose job is the Monitor-stdout emitter) — a webhook is a distinct
trust boundary. We reuse only the pure `watch.new_pending` (once-per-request_id dedup
+ kind filter) and `dashboard`'s human-bound kinds + per-kind summary. The URL comes
from `--webhook` or `$DIRECTOR_WEBHOOK_URL` (kept in `.env` — Slack/Discord webhooks
embed a secret token, so never `.harness.json`).

  python3 -m director.notify --webhook https://hooks.slack.com/...  [--queue-dir ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import director.queue as dq
from director import watch
# Reuse the console's human-bound kind set + per-kind summary so the ping matches what
# the console shows (`_summary_for` is module-private but the console+notifier are one
# product; promote it to public if a third consumer appears).
from director.dashboard import HUMAN_BOUND_KINDS, _summary_for

_RETRY_CAP = 5  # per-request POST attempts before abandoning a permanently-dead URL


def _resolve_webhook_url(cli=None, env_path: str | Path = ".env"):
    """The webhook URL: `--webhook`, else `$DIRECTOR_WEBHOOK_URL`, else a repo-root
    `.env` line — mirroring `board.linear.load_api_key` so the secret-bearing URL lives
    in `.env` (never committed) exactly like `LINEAR_API_KEY`."""
    if cli:
        return cli
    env = os.environ.get("DIRECTOR_WEBHOOK_URL")
    if env:
        return env
    p = Path(env_path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("DIRECTOR_WEBHOOK_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def webhook_payload(req: dict) -> dict:
    """The notification body for one pending request — minimal + glance-able. The
    console carries full detail; this is the 'you're needed' ping (spec R4)."""
    return {"request_id": req.get("request_id"),
            "kind": req.get("kind"),
            "ticket_id": req.get("ticket_id"),
            "summary": _summary_for(req.get("kind"), req.get("payload")),
            "created_at": req.get("created_at")}


def _urllib_post(url: str, data: bytes, headers: dict) -> int:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 (operator-configured URL)
        return resp.status


def make_webhook_notifier(url: str, *, http_post=_urllib_post):
    """A notifier `notify(event) -> bool`: POST `event` as JSON to `url`; True on 2xx,
    False on any non-2xx / transport error (NEVER raises — the caller owns retry). A
    future email/OS channel is another `make_*_notifier` behind this same shape."""
    def notify(event: dict) -> bool:
        body = json.dumps(event, ensure_ascii=False).encode("utf-8")
        try:
            status = http_post(url, body, {"Content-Type": "application/json"})
        except Exception:
            return False
        return 200 <= int(status or 0) < 300
    return notify


def run(notify, *, queue_dir=None, poll_s: float = 1.0, once: bool = False,
        max_ticks: int | None = None, kinds=HUMAN_BOUND_KINDS,
        retry_cap: int = _RETRY_CAP, sleep=time.sleep) -> None:
    """Tail the queue; fire `notify` exactly once per new human-bound pending
    request_id. Fail-soft + bounded retry: a `notify()` returning False leaves the
    request_id UNSEEN so the next tick retries (recovers a transient webhook outage),
    up to `retry_cap` attempts — then mark seen + log 'abandoned' so a dead URL never
    hammers. The loop never raises (a torn/absent queue read → no pending this tick).
    `once=True` (CLI) → one pass; `max_ticks` bounds it for tests; default → forever."""
    if once:
        max_ticks = 1
    seen: set = set()
    attempts: dict = {}
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        ticks += 1
        try:
            pending = dq.read_pending(base=queue_dir)
        except Exception:  # torn/absent queue read → nothing to notify this tick
            pending = []
        for req in watch.new_pending(pending, seen, set(kinds)):
            # new_pending added rid to `seen`; on a failed POST we discard it (retry).
            rid = req.get("request_id")
            if notify(webhook_payload(req)):
                attempts.pop(rid, None)  # delivered → drop any retry counter
                continue
            n = attempts.get(rid, 0) + 1
            attempts[rid] = n
            if n >= retry_cap:
                print(json.dumps({"notify": "abandoned", "request_id": rid,
                                  "attempts": n}), file=sys.stderr)
                attempts.pop(rid, None)  # abandoned (stays in `seen`) → counter not needed
            else:
                seen.discard(rid)  # leave unseen → retried next tick
        if max_ticks is None or ticks < max_ticks:
            sleep(poll_s)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="director.notify",
        description="Webhook the human on a new park (human-bound Director-queue request).")
    ap.add_argument("--webhook", default=None,
                    help="webhook URL (else $DIRECTOR_WEBHOOK_URL); Slack/Discord/custom")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--poll", type=float, default=1.0, help="poll interval seconds")
    ap.add_argument("--once", action="store_true", help="single pass then exit")
    args = ap.parse_args(argv)
    url = _resolve_webhook_url(args.webhook)
    if not url:
        ap.error("no webhook URL (pass --webhook, set $DIRECTOR_WEBHOOK_URL, or add "
                 "DIRECTOR_WEBHOOK_URL=... to repo-root .env)")
    if urlparse(url).scheme not in ("http", "https"):
        ap.error(f"webhook URL must be http(s), got scheme {urlparse(url).scheme!r}")
    run(make_webhook_notifier(url), queue_dir=args.queue_dir,
        poll_s=args.poll, once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
