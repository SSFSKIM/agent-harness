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

_TEAM_STATES = """
query DirectorTeamStates($id: String!) {
  team(id: $id) { states { nodes { id name type } } }
}
""".strip()

_READY_ISSUES = """
query DirectorReadyIssues($team: ID!, $state: ID!) {
  issues(filter: { team: { id: { eq: $team } }, state: { id: { eq: $state } } }) {
    nodes { id identifier title description state { id name } }
  }
}
""".strip()

_UPDATE_STATE = """
mutation DirectorSetState($id: String!, $state: String!) {
  issueUpdate(id: $id, input: { stateId: $state }) { success }
}
""".strip()

_COMMENT = """
mutation DirectorComment($id: String!, $body: String!) {
  commentCreate(input: { issueId: $id, body: $body }) { success }
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


def _post(query: str, variables: dict, *, api_key: str | None,
          endpoint: str, http_post: Callable[[str, bytes, dict], dict]) -> dict:
    """POST one GraphQL document and return `data`, raising on a top-level `errors`
    array (a GraphQL error is a failed call even when HTTP succeeded). Shared by
    every read/write method so auth + error handling live in one place."""
    key = api_key or load_api_key()
    if not key:
        raise RuntimeError("LINEAR_API_KEY not found (env or .env)")
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    headers = {"Authorization": key, "Content-Type": "application/json"}
    resp = http_post(endpoint, body, headers)
    if resp.get("errors"):
        raise RuntimeError(f"Linear GraphQL error: {resp['errors']}")
    return resp.get("data") or {}


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
    data = _post(_READ_ISSUE, {"id": issue_id},
                 api_key=api_key, endpoint=endpoint, http_post=http_post)
    issue = data.get("issue")
    if not issue:
        raise RuntimeError(f"Linear issue not found: {issue_id}")
    return normalize_issue(issue)


def workflow_states(team_id: str, *, api_key: str | None = None,
                    endpoint: str = DEFAULT_ENDPOINT,
                    http_post: Callable[[str, bytes, dict], dict] = urllib_post) -> dict:
    """A team's workflow states as `{name: {"id", "type"}}` — the orchestrator reads
    this once at startup to resolve its logical ready/started/done state names to ids."""
    data = _post(_TEAM_STATES, {"id": team_id},
                 api_key=api_key, endpoint=endpoint, http_post=http_post)
    nodes = (((data.get("team") or {}).get("states") or {}).get("nodes")) or []
    return {n["name"]: {"id": n["id"], "type": n.get("type")} for n in nodes}


def list_ready_issues(team_id: str, ready_state_id: str, *, api_key: str | None = None,
                      endpoint: str = DEFAULT_ENDPOINT,
                      http_post: Callable[[str, bytes, dict], dict] = urllib_post) -> list[dict]:
    """Issues in one team currently in the given (ready) workflow state, each
    normalized to a ticket dict with its current `state_id`. Flat state filter —
    DAG/blocked_by is not consulted (Phase 3)."""
    data = _post(_READY_ISSUES, {"team": team_id, "state": ready_state_id},
                 api_key=api_key, endpoint=endpoint, http_post=http_post)
    nodes = ((data.get("issues") or {}).get("nodes")) or []
    out = []
    for issue in nodes:
        ticket = normalize_issue(issue)
        ticket["state_id"] = (issue.get("state") or {}).get("id")
        out.append(ticket)
    return out


def update_issue_state(issue_id: str, state_id: str, *, api_key: str | None = None,
                       endpoint: str = DEFAULT_ENDPOINT,
                       http_post: Callable[[str, bytes, dict], dict] = urllib_post) -> bool:
    """Transition one issue to a workflow state (claim / reconcile). Returns success."""
    data = _post(_UPDATE_STATE, {"id": issue_id, "state": state_id},
                 api_key=api_key, endpoint=endpoint, http_post=http_post)
    return bool((data.get("issueUpdate") or {}).get("success"))


def comment_issue(issue_id: str, body: str, *, api_key: str | None = None,
                  endpoint: str = DEFAULT_ENDPOINT,
                  http_post: Callable[[str, bytes, dict], dict] = urllib_post) -> bool:
    """Post a comment on one issue (reconcile outcome — board visibility for watched
    Director). Returns success."""
    data = _post(_COMMENT, {"id": issue_id, "body": body},
                 api_key=api_key, endpoint=endpoint, http_post=http_post)
    return bool((data.get("commentCreate") or {}).get("success"))


class LinearBoard:
    """Stateful board adapter binding auth + endpoint, exposing the orchestrator's
    read/claim/reconcile surface over the module functions. The orchestrator depends
    on this object's shape (workflow_states / list_ready_issues / update_issue_state /
    comment_issue), so a test `FakeBoard` can stand in with zero network."""

    def __init__(self, *, api_key: str | None = None, endpoint: str = DEFAULT_ENDPOINT,
                 http_post: Callable[[str, bytes, dict], dict] = urllib_post):
        self.api_key = api_key or load_api_key()
        self.endpoint = endpoint
        self.http_post = http_post

    def workflow_states(self, team_id: str) -> dict:
        return workflow_states(team_id, api_key=self.api_key,
                               endpoint=self.endpoint, http_post=self.http_post)

    def list_ready_issues(self, team_id: str, ready_state_id: str) -> list[dict]:
        return list_ready_issues(team_id, ready_state_id, api_key=self.api_key,
                                 endpoint=self.endpoint, http_post=self.http_post)

    def update_issue_state(self, issue_id: str, state_id: str) -> bool:
        return update_issue_state(issue_id, state_id, api_key=self.api_key,
                                  endpoint=self.endpoint, http_post=self.http_post)

    def comment_issue(self, issue_id: str, body: str) -> bool:
        return comment_issue(issue_id, body, api_key=self.api_key,
                             endpoint=self.endpoint, http_post=self.http_post)
