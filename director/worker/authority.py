"""Worker authority guardrail (Phase 4, first slice).

Bounds what the worker's `linear_graphql` tool may do: reads always pass; a
`mutation` operation passes only when every top-level mutation root field is on
the allowlist; everything else is refused locally before any Linear POST
(default-deny, fail-closed). Spec: docs/product-specs/2026-06-14-worker-authority-guardrail.md.

Why a classifier and not a regex: Linear only *executes* a mutation field when the
operation keyword is literally `mutation`. A document that hides `mutation` inside a
comment/string, or calls a mutation field under a `query`, is parsed by Linear as a
read and runs nothing. So the classifier just has to see the same document the
server's lexer sees — strip comments and string literals, then read the operation
type and the mutation's root field names. It is aligned with the server parse, not
trying to outsmart an adversary (D-23, D-26).

Two structural facts the lexer relies on:
  - Selection-set braces `{}` and object-value braces `{}` are the same character,
    but object values only appear inside argument lists `(...)`. So we track brace
    depth only while paren depth is 0 — argument braces never move our depth.
  - A mutation's root fields are the depth-1 names of its selection set (skipping
    an `alias:` prefix, arguments, directives, and sub-selections).
"""
from __future__ import annotations

import re

# The exact mutations the worker's installed `.codex/skills` + 3b worker-driven
# decomposition use (D-27): board reads stay free, these forward-only writes are
# the worker's legitimate job. Destructive ops (delete/archive/batch) are absent →
# default-deny refuses them. Overridable at executor construction.
DEFAULT_MUTATION_ALLOWLIST: frozenset[str] = frozenset({
    "issueCreate",            # worker-driven child tickets (3b)
    "issueUpdate",            # state transitions, labels, assignment
    "commentCreate",          # progress / completion comments
    "commentUpdate",          # edit a prior comment (linear skill)
    "issueRelationCreate",    # blocked_by relations for the typed DAG (3b)
    "attachmentLinkURL",      # link a URL to an issue
    "attachmentLinkGitHubPR", # link a PR to an issue (land skill)
    "fileUpload",             # upload an asset for a comment (linear skill)
})

# `...` (spread) | GraphQL name | the punctuators we track | any other single char.
_TOKEN = re.compile(r"\.\.\.|[A-Za-z_][A-Za-z0-9_]*|[{}():@]|[^\s]")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_OP_KEYWORDS = {"query", "mutation", "subscription", "fragment"}


def _strip(query: str) -> tuple[str, bool]:
    """Blank out line comments and string literals (what the GraphQL lexer ignores),
    so braces/keywords inside them never affect classification. Returns
    (stripped, ok); ok is False if a string literal is left unterminated — a
    malformed document the classifier must fail closed on directly, rather than
    relying on the truncation happening to unbalance the braces."""
    out: list[str] = []
    ok = True
    i, n = 0, len(query)
    while i < n:
        c = query[i]
        if c == "#":                                  # line comment -> EOL
            while i < n and query[i] != "\n":
                i += 1
            continue
        if c == '"':
            closed = False
            if query[i:i + 3] == '"""':               # block string
                i += 3
                while i < n:
                    if query[i] == "\\" and query[i + 1:i + 4] == '"""':
                        i += 4
                        continue
                    if query[i:i + 3] == '"""':
                        i += 3
                        closed = True
                        break
                    i += 1
            else:                                      # regular string
                i += 1
                while i < n:
                    if query[i] == '"':
                        i += 1
                        closed = True
                        break
                    if query[i] == "\\":
                        i += 2
                        continue
                    i += 1
            if not closed:
                ok = False
            out.append(" ")
            continue
        out.append(c)
        i += 1
    return "".join(out), ok


def _is_name(tok: str) -> bool:
    return bool(_NAME.match(tok))


def classify_operation(query: str) -> dict:
    """Reduce a GraphQL document to {kind, root_fields, parse_ok}.

    kind ∈ {"query","mutation","subscription","unknown"} with precedence
    subscription > mutation > query (a doc mixing a subscription or an
    unresolvable mutation with anything is refused upstream). root_fields is the
    union of every mutation operation's depth-1 fields. parse_ok is False when the
    document is unbalanced or a mutation root cannot be resolved (fragment spread
    / inline fragment) — both deny, fail-closed.
    """
    stripped, parse_ok = _strip(query)   # parse_ok starts False on an unterminated string
    tokens = _TOKEN.findall(stripped)
    paren = brace = 0
    current_op: str | None = None     # op type of the definition currently entered
    has_mut = has_query = has_sub = False
    fields: set[str] = set()

    i, n = 0, len(tokens)
    while i < n:
        t = tokens[i]
        nxt = tokens[i + 1] if i + 1 < n else None

        if t == "(":
            paren += 1; i += 1; continue
        if t == ")":
            paren -= 1
            if paren < 0:
                parse_ok = False; paren = 0
            i += 1; continue
        if paren > 0:                 # inside args/var-defs/object values: ignore all
            i += 1; continue

        if t == "{":
            brace += 1
            if brace == 1:            # a definition's selection set just opened
                if current_op == "mutation":
                    has_mut = True
                elif current_op == "subscription":
                    has_sub = True
                elif current_op in (None, "query"):   # anonymous or named query
                    has_query = True
                # current_op == "fragment": a fragment body, nothing to record
            i += 1; continue
        if t == "}":
            brace -= 1
            if brace < 0:
                parse_ok = False; brace = 0
            if brace == 0:
                current_op = None     # definition ended
            i += 1; continue

        if brace == 0:                # definition header: pick up the operation keyword
            if t in _OP_KEYWORDS:
                current_op = t
            i += 1; continue

        if brace == 1 and current_op == "mutation":   # mutation root selection set
            if t == "...":            # fragment spread / inline fragment -> unresolvable
                parse_ok = False; i += 1; continue
            if t == "@":              # directive: skip its name (args handled by paren)
                i += 1
                if i < n and _is_name(tokens[i]):
                    i += 1
                continue
            if _is_name(t):
                if nxt == ":":        # this is an alias -> the field name follows
                    i += 2; continue
                fields.add(t)         # a root field
                i += 1; continue
            i += 1; continue

        i += 1                        # sub-selection / non-mutation body: ignore

    if brace != 0 or paren != 0:
        parse_ok = False
    if has_sub:
        kind = "subscription"
    elif has_mut:
        kind = "mutation"
    elif has_query:
        kind = "query"
    else:
        kind = "unknown"
    return {"kind": kind, "root_fields": tuple(sorted(fields)), "parse_ok": parse_ok}


def authorize(query: str, *, allow_mutations: frozenset[str] | None = None) -> dict:
    """Decide whether `query` may run -> {allowed, reason}. Reads pass; mutations
    pass only when every root field is allowlisted; everything else is refused."""
    allow = allow_mutations if allow_mutations is not None else DEFAULT_MUTATION_ALLOWLIST
    op = classify_operation(query)
    if not op["parse_ok"]:
        return {"allowed": False,
                "reason": "could not parse GraphQL operation safely; refused (fail-closed)"}
    kind = op["kind"]
    if kind == "subscription":
        return {"allowed": False,
                "reason": "subscriptions are not permitted via linear_graphql"}
    if kind == "unknown":
        return {"allowed": False,
                "reason": "no GraphQL operation found; refused (fail-closed)"}
    if kind == "query":
        return {"allowed": True, "reason": "read operation"}
    # mutation
    fields = op["root_fields"]
    if not fields:
        return {"allowed": False,
                "reason": "mutation with no resolvable root field; refused (fail-closed)"}
    blocked = [f for f in fields if f not in allow]
    if blocked:
        return {"allowed": False,
                "reason": "mutation not allowed: " + ", ".join(sorted(blocked))
                          + " (not in allowlist)"}
    return {"allowed": True, "reason": "allowlisted mutation: " + ", ".join(fields)}
