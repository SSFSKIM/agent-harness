"""Worker secret boundary — host-declared, deny-by-default worker environment.

The harness is transplanted into *other* host repos (AGENTS.md "Porting"). A worker
spawns with `cwd=<host repo>` inside the host's filesystem, so the credentials it can
reach are the *host's* — unknowable to the harness. A boundary that enumerates "known"
secret vars cannot protect unknown host secrets; only **deny-by-default** can. So the
worker subprocess never inherits the Director's full environment: it receives a freshly
*constructed* env — an operational base (the non-secret vars a process needs to start)
plus the keys the host explicitly allows in `<root>/.harness.json` `worker_policy`.

This closes the **env-inheritance** exfil channel of SECURITY.md T11. It does NOT close
the other two (filesystem-wide reads of an on-disk `.env`, and egress) — those need an
OS boundary and are deferred to the container ExecPlan. `network_allowlist`/`capabilities`
are *declared* here for later enforcement; this module only enforces `worker_env`.

ARCHITECTURE invariant 7: a host's rules are the host's, declared in `.harness.json` —
not hardcoded here. The operational base below is harness *mechanism* (make the
subprocess runnable), not the host's secret policy.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Operational base — non-secret vars a language/OS runtime needs to start. An EXPLICIT
# finite NAME allowlist (no wildcard/prefix: a prefix like `LC_*` would be fail-open for
# a secret-agnostic boundary — a `LC_<anything>` credential would slip through). The
# POSIX/glibc `LC_*` locale vars are enumerated in full instead. Everything else (every
# host credential) is denied unless the host lists it in `worker_env`. Resolved
# empirically (a real worker must still complete a turn); widen only on a start failure.
_BASE_NAMES = frozenset({
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "PWD", "TMPDIR", "TZ",
    "LANG", "LANGUAGE", "TERM",
    # python / node runtime plumbing (non-secret)
    "PYTHONPATH", "PYTHONHOME", "PYTHONUNBUFFERED", "VIRTUAL_ENV",
    "__PYVENV_LAUNCHER__", "NODE_PATH", "NVM_DIR", "NVM_BIN",
    "LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH",
    # locale (POSIX + glibc LC_* — enumerated, never prefix-matched)
    "LC_ALL", "LC_COLLATE", "LC_CTYPE", "LC_MESSAGES", "LC_MONETARY",
    "LC_NUMERIC", "LC_TIME", "LC_PAPER", "LC_NAME", "LC_ADDRESS",
    "LC_TELEPHONE", "LC_MEASUREMENT", "LC_IDENTIFICATION",
})

# T11 (cc-codex-appserver): the Claude-backed drop-in app-server and its bundled
# `claude` CLI + Linear MCP require auth credentials the deny-by-default boundary
# otherwise blocks.  A host using cc-codex-appserver must add these to
# .harness.json "worker_policy": {"worker_env": ["CLAUDE_CODE_OAUTH_TOKEN",
# "ANTHROPIC_API_KEY", "LINEAR_API_KEY"]} so build_worker_env passes them through.
# They are NOT in _BASE_NAMES (credentials are host-declared, never harness-hardcoded).


def _empty_policy() -> dict:
    return {"worker_env": [], "network_allowlist": [], "capabilities": []}


def _is_base(name: str) -> bool:
    return name in _BASE_NAMES


def discover_root(start: str | Path | None = None) -> Path:
    """The host root that owns `.harness.json` — walk up from `start` (cwd by default)
    to the first dir containing `.harness.json`, else the first containing `.git`, else
    `start` itself. No file found is a legitimate state (deny-by-default applies)."""
    cur = Path(start or os.getcwd()).resolve()
    git_root = None
    for d in (cur, *cur.parents):
        if (d / ".harness.json").is_file():
            return d
        if git_root is None and (d / ".git").exists():
            git_root = d
    return git_root or cur


def load_worker_policy(root: str | Path | None = None) -> dict:
    """Read `<root>/.harness.json` `worker_policy`; absent file/key → deny-by-default
    (all-empty). A malformed `worker_policy` **fails loud** (raises) rather than
    silently opening the boundary — a half-parsed policy must never widen access."""
    base = Path(root) if root is not None else discover_root()
    cfg_path = base / ".harness.json"
    if not cfg_path.is_file():
        return _empty_policy()
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    wp = raw.get("worker_policy")
    if wp is None:
        return _empty_policy()
    if not isinstance(wp, dict):
        raise ValueError(f".harness.json worker_policy must be an object, got {type(wp).__name__}")
    out = {}
    for key in ("worker_env", "network_allowlist", "capabilities"):
        val = wp.get(key, [])
        if not isinstance(val, list) or not all(isinstance(x, str) for x in val):
            raise ValueError(f".harness.json worker_policy.{key} must be a list of strings")
        out[key] = list(val)
    return out


def build_worker_env(policy: dict, environ: dict | None = None) -> dict:
    """Construct the worker subprocess env: operational base (copied from `environ`) +
    the host-allowed `worker_env` keys. Everything else — every host credential not on
    the base or the allowlist — is dropped. This is the enforcement point of the
    env-inheritance boundary; the returned dict is what `Popen(env=...)` receives."""
    src = os.environ if environ is None else environ
    allow = set(policy.get("worker_env") or ())
    return {k: v for k, v in src.items() if _is_base(k) or k in allow}
