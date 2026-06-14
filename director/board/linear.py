"""Linear tracker adapter (Phase 1, M5) — read one issue as a worker ticket.

Phase 1 only READS (board substrate = Linear, decision D-3); ticket WRITES (state
transitions, comments) are the worker's job in later phases. Auth is Linear's
personal API key in the raw `Authorization` header (no "Bearer"), per the Symphony
reference adapter. The key lives in repo-root `.env` (LINEAR_API_KEY, gitignored —
decision D-6). HTTP uses stdlib urllib (internalize dependencies) and is injectable
so tests run without network (mock-first, plan Approach A).
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path
from typing import Callable

DEFAULT_ENDPOINT = "https://api.linear.app/graphql"

_READ_ISSUE = """
query DirectorReadIssue($id: String!) {
  issue(id: $id) {
    id
    identifier
    title
    description
    state { name }
  }
}
""".strip()


def load_api_key(env_path: str | Path = ".env") -> str | None:
    """LINEAR_API_KEY from the environment, falling back to a repo-root .env line."""
    key = os.environ.get("LINEAR_API_KEY")
    if key:
        return key
    p = Path(env_path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("LINEAR_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def urllib_post(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310 (fixed Linear endpoint)
        return json.loads(resp.read().decode("utf-8"))


def normalize_issue(issue: dict) -> dict:
    """A raw Linear issue -> a Director ticket dict (id/identifier/prompt/...)."""
    title = issue.get("title") or ""
    desc = issue.get("description") or ""
    identifier = issue.get("identifier") or issue.get("id")
    return {
        "id": issue.get("id"),
        "identifier": identifier,
        "title": title,
        "description": desc,
        "state": (issue.get("state") or {}).get("name"),
        "prompt": f"{identifier}: {title}\n\n{desc}".strip(),
    }


def read_issue(issue_id: str, *, api_key: str | None = None,
               endpoint: str = DEFAULT_ENDPOINT,
               http_post: Callable[[str, bytes, dict], dict] = urllib_post) -> dict:
    """Read one Linear issue by id/identifier and normalize it into a ticket dict."""
    key = api_key or load_api_key()
    if not key:
        raise RuntimeError("LINEAR_API_KEY not found (env or .env)")
    body = json.dumps({"query": _READ_ISSUE, "variables": {"id": issue_id}}).encode("utf-8")
    headers = {"Authorization": key, "Content-Type": "application/json"}
    resp = http_post(endpoint, body, headers)
    if resp.get("errors"):
        raise RuntimeError(f"Linear GraphQL error: {resp['errors']}")
    issue = (resp.get("data") or {}).get("issue")
    if not issue:
        raise RuntimeError(f"Linear issue not found: {issue_id}")
    return normalize_issue(issue)
