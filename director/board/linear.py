"""Linear tracker adapter (board substrate = Linear, decision D-3).

Reads (Phase 1): one issue as a worker ticket. Writes (orchestrator, D-11): the
Director's own board-write authority — `list_ready_issues` (poll), `update_issue_state`
(claim + reconcile), `comment_issue` (outcome). This is separate from the worker's
`linear_graphql` tool (Phase 2): reconcile must work even when a worker has crashed,
so the Director writes under its own key. Auth is Linear's personal API key in the
raw `Authorization` header (no "Bearer"), per the Symphony reference adapter; the key
lives in repo-root `.env` (LINEAR_API_KEY, gitignored — decision D-6). HTTP uses
stdlib urllib (internalize dependencies) and is injectable so tests run without
network (mock-first). `LinearBoard` binds auth+endpoint into the object the
orchestrator depends on (swappable with a test/`--mock` board).
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

_CANDIDATE_FIELDS = """
      id identifier title description state { id name }
      labels { nodes { name } }
      inverseRelations { nodes { type issue { id state { id name type } } } }
""".strip("\n")

_READY_ISSUES = """
query DirectorReadyIssues($team: ID!, $state: ID!, $after: String) {
  issues(first: 50, after: $after,
         filter: { team: { id: { eq: $team } }, state: { id: { eq: $state } } }) {
    nodes {
%s
    }
    pageInfo { hasNextPage endCursor }
  }
}
""" % _CANDIDATE_FIELDS
_READY_ISSUES = _READY_ISSUES.strip()

_ISSUES_BY_STATES = """
query DirectorIssuesByStates($team: ID!, $states: [ID!], $after: String) {
  issues(first: 50, after: $after,
         filter: { team: { id: { eq: $team } }, state: { id: { in: $states } } }) {
    nodes {
%s
    }
    pageInfo { hasNextPage endCursor }
  }
}
""" % _CANDIDATE_FIELDS
_ISSUES_BY_STATES = _ISSUES_BY_STATES.strip()

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

_ISSUE_STATES = """
query DirectorIssueStates($ids: [ID!]) {
  issues(filter: { id: { in: $ids } }) {
    nodes { id state { id name type } }
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


def _paginate(query: str, variables: dict, *, api_key: str | None,
              endpoint: str, http_post: Callable[[str, bytes, dict], dict]) -> list[dict]:
    """Fetch ALL `issues.nodes` for a candidate query across pages (Symphony §11.2:
    pagination REQUIRED for candidate issues). Threads `after=endCursor` until
    `pageInfo.hasNextPage` is false, concatenating nodes in fetch order (order
    preserved across pages). A `hasNextPage: true` with a falsy `endCursor` is a
    pagination-integrity violation and RAISES (`linear_missing_end_cursor`) — never a
    silent truncation. A response without `pageInfo` is treated as a single final page
    (so a non-paginating fake/transport degrades to one fetch, never an infinite loop)."""
    nodes: list[dict] = []
    after = None
    while True:
        data = _post(query, {**variables, "after": after},
                     api_key=api_key, endpoint=endpoint, http_post=http_post)
        conn = data.get("issues") or {}
        nodes.extend(conn.get("nodes") or [])
        page = conn.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return nodes
        after = page.get("endCursor")
        if not after:
            raise RuntimeError("Linear pagination integrity error: hasNextPage with no "
                               "endCursor (linear_missing_end_cursor)")


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


def _parse_blockers(issue: dict) -> list[dict]:
    """Issues that block `issue`, as [{id, state_type}]. Linear models 'X blocked by
    Y' as X.inverseRelations containing {type:"blocks", issue:Y} (Y is the blocker).
    We fetch all inverseRelations and keep type=="blocks" (no connection filter arg)."""
    rels = ((issue.get("inverseRelations") or {}).get("nodes")) or []
    blockers = []
    for r in rels:
        if r.get("type") != "blocks":
            continue
        blk = r.get("issue") or {}
        bid = blk.get("id")
        if bid:
            blockers.append({"id": bid, "state_type": (blk.get("state") or {}).get("type")})
    return blockers


def _parse_labels(issue: dict) -> list[str]:
    """An issue's label names — the orchestrator derives the dev-stage type from these."""
    nodes = ((issue.get("labels") or {}).get("nodes")) or []
    return [n["name"] for n in nodes if n.get("name")]


def _normalize_candidate(issue: dict) -> dict:
    """A raw candidate issue -> a re-dispatchable ticket dict: the base normalization
    plus the current `state_id`, `blockers` ([{id, state_type}] — DAG predecessors),
    and `labels` (names — the dev-stage type). Shared by every candidate query so the
    ready-poll and the by-states fetch produce identical, re-dispatchable shapes."""
    ticket = normalize_issue(issue)
    ticket["state_id"] = (issue.get("state") or {}).get("id")
    ticket["blockers"] = _parse_blockers(issue)
    ticket["labels"] = _parse_labels(issue)
    return ticket


def list_ready_issues(team_id: str, ready_state_id: str, *, api_key: str | None = None,
                      endpoint: str = DEFAULT_ENDPOINT,
                      http_post: Callable[[str, bytes, dict], dict] = urllib_post) -> list[dict]:
    """Issues in one team currently in the given (ready) workflow state, each
    normalized to a ticket dict with its current `state_id`, `blockers`
    ([{id, state_type}] — DAG predecessors), and `labels` (names — the dev-stage type).
    Paginated (§11.2): ALL ready issues across pages, not just the first 50."""
    nodes = _paginate(_READY_ISSUES, {"team": team_id, "state": ready_state_id},
                      api_key=api_key, endpoint=endpoint, http_post=http_post)
    return [_normalize_candidate(issue) for issue in nodes]


def fetch_issues_by_states(team_id: str, state_ids, *, api_key: str | None = None,
                           endpoint: str = DEFAULT_ENDPOINT,
                           http_post: Callable[[str, bytes, dict], dict] = urllib_post
                           ) -> list[dict]:
    """Issues in one team currently in ANY of the given workflow states, normalized to
    re-dispatchable ticket dicts (same shape as `list_ready_issues`). Symphony §11.1 op
    #2 — the read behind startup terminal-workspace cleanup (pass the terminal state
    ids) and crash-orphan recovery (pass the `started` state id). Paginated like the
    candidate poll. An **empty `state_ids` makes NO API call** (returns `[]`; mirrors
    `fetch_issue_states_by_ids`'s empty-guard, §17.3)."""
    ids = list(state_ids)
    if not ids:
        return []
    nodes = _paginate(_ISSUES_BY_STATES, {"team": team_id, "states": ids},
                      api_key=api_key, endpoint=endpoint, http_post=http_post)
    return [_normalize_candidate(issue) for issue in nodes]


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


def fetch_issue_states_by_ids(issue_ids, *, api_key: str | None = None,
                              endpoint: str = DEFAULT_ENDPOINT,
                              http_post: Callable[[str, bytes, dict], dict] = urllib_post
                              ) -> dict[str, dict]:
    """Current workflow state of each given issue id, as
    `{id: {"state_id", "state_name", "state_type"}}` — the active-run reconciliation
    read (Symphony §16.3). An **empty `issue_ids` makes NO API call** (returns `{}`;
    Symphony §17.3 "empty fetch → no call"). Ids absent from the response are simply
    not in the returned map — the caller treats an unknown id conservatively (never
    cancels on missing data)."""
    ids = list(issue_ids)
    if not ids:
        return {}
    data = _post(_ISSUE_STATES, {"ids": ids},
                 api_key=api_key, endpoint=endpoint, http_post=http_post)
    nodes = ((data.get("issues") or {}).get("nodes")) or []
    out: dict[str, dict] = {}
    for n in nodes:
        iid = n.get("id")
        if iid is None:
            continue
        st = n.get("state") or {}
        out[iid] = {"state_id": st.get("id"), "state_name": st.get("name"),
                    "state_type": st.get("type")}
    return out


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

    def fetch_issues_by_states(self, team_id: str, state_ids) -> list[dict]:
        return fetch_issues_by_states(team_id, state_ids, api_key=self.api_key,
                                      endpoint=self.endpoint, http_post=self.http_post)

    def update_issue_state(self, issue_id: str, state_id: str) -> bool:
        return update_issue_state(issue_id, state_id, api_key=self.api_key,
                                  endpoint=self.endpoint, http_post=self.http_post)

    def comment_issue(self, issue_id: str, body: str) -> bool:
        return comment_issue(issue_id, body, api_key=self.api_key,
                             endpoint=self.endpoint, http_post=self.http_post)

    def fetch_issue_states_by_ids(self, issue_ids) -> dict[str, dict]:
        return fetch_issue_states_by_ids(issue_ids, api_key=self.api_key,
                                         endpoint=self.endpoint, http_post=self.http_post)
