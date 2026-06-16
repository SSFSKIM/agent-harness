"""Director declarative config — the `.harness.json` `director` block (Symphony
WORKFLOW.md analog; SPEC §5–6). Owner: docs/product-specs/2026-06-16-director-
declarative-config.md (R1–R7, D-54..D-58).

Externalizes orchestration *deployment policy* (team, state-name map, concurrency,
worker posture, paths, merger knobs) out of code/CLI into one repo-owned,
version-controlled file — the same `<root>/.harness.json` that already carries
`worker_policy`. Methodology (taxonomy templates, queue schema, disposition kinds)
stays in code (spec R3): a host installing the harness buys its methodology.

Grain (ARCHITECTURE "Host runtime (`director/`) invariants"): stdlib-only — no
YAML, so stdlib `json` not Symphony's YAML front matter (invariant 1); explicit
`root=` over ambient state (invariant 2); pure core, thin transport (invariant 4).
This module OWNS `DEFAULTS` (the single source of truth) and the resolution; it
imports ONLY `director.worker.policy` (discover_root) + stdlib, so nothing it
touches can import it back — the dependency graph stays acyclic and every other
director module reads config, never the reverse (plan Approach A).

Validation discipline (spec R7), split by risk exactly like the two host-config
precedents: an ABSENT file/block → DEFAULTS (fail-open, like
`harness_lib.gate_config`); a PRESENT-but-malformed block (or a present-but-broken
`.harness.json`) → raise (fail-loud, like `policy.load_worker_policy`). A wrong
team/state must never silently claim/transition the wrong tickets, so the raise
lands at config load — before any board read or worker spawn.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

from director.worker import policy

# -- DEFAULTS: single source of truth for every externalized knob ------------
# Posture defaults carry the SECURITY.md T11 rationale: both watched and
# un-watched runs share `on-request` + `auto_review` + full `network` by human
# decision (2026-06-15); the network exfil residual is deferred to one holistic
# mitigation, so both postures are safe only where reachable creds are throwaway.
# A host MAY *tighten* these (network off, `untrusted`) — that is the fail-safe
# direction; this layer introduces no way to widen access past the default.
DEFAULTS: dict = {
    "team": None,
    "states": {"ready": "Todo", "started": "In Progress", "done": "Done",
               "failed": None, "blocked": None},
    "concurrency": 3,
    "max_turns": 8,
    "max_passes": 50,
    "max_dispatched": 200,
    "done_types": ["completed"],
    "read_timeout_s": 30.0,
    "turn_review_timeout_s": 300.0,
    # active-run reconciliation cadence: how often the wave loop re-reads in-flight
    # ticket states to stop a worker a human moved out of `started` (lower = faster
    # operator-stop, more tracker calls).
    "reconcile_interval_s": 15.0,
    # daemon (run_forever, gap #2) poll cadence: how often the always-on loop re-polls
    # the board for new ready work and ticks while idle (Symphony `polling.interval_ms`).
    # Only used by `--daemon`; the batch paths ignore it.
    "poll_interval_s": 10.0,
    "codex_command": "codex app-server",
    "worker": {"approval_policy": "on-request", "sandbox": "workspace-write",
               "auto_review": True, "network": True},
    # paths are OPTIONAL overrides: None = "use the module's built-in default"
    # (run.DEFAULT_WORKSPACE_ROOT for workspaces; queue/status `_root(base=None)`).
    "paths": {"workspace_root": None, "queue_dir": None, "status_dir": None},
    "merger": {"poll_s": 1.0, "read_timeout_s": 180.0, "max_merges": 200},
}

_STATE_KEYS = ("ready", "started", "done", "failed", "blocked")
_APPROVAL_VALUES = frozenset({"untrusted", "on-request", "on-failure", "never"})
_SANDBOX_VALUES = frozenset({"read-only", "workspace-write", "danger-full-access"})
_VAR_RE = re.compile(r"^\$(?:\{(\w+)\}|(\w+))$")


@dataclass(frozen=True)
class Posture:
    approval_policy: str
    sandbox: str
    auto_review: bool
    network: bool


@dataclass(frozen=True)
class Paths:
    workspace_root: str | None
    queue_dir: str | None
    status_dir: str | None


@dataclass(frozen=True)
class Merger:
    poll_s: float
    read_timeout_s: float
    max_merges: int


@dataclass(frozen=True)
class DirectorConfig:
    team: str | None
    states: dict
    concurrency: int
    max_turns: int
    max_passes: int
    max_dispatched: int
    done_types: tuple
    read_timeout_s: float
    turn_review_timeout_s: float
    reconcile_interval_s: float
    poll_interval_s: float
    codex_command: str
    posture: Posture
    paths: Paths
    merger: Merger


# -- $VAR indirection (spec R5 / Symphony §6.1) ------------------------------
def _resolve_env(value, environ: Mapping):
    """A string of the form `$NAME` / `${NAME}` → `environ[NAME]`; unset or empty
    → None ("missing", Symphony's api_key rule). Any other value is returned
    unchanged — resolution is content-triggered (a real config value is never
    exactly `$NAME`), so literals like `"Todo"` pass straight through."""
    if not isinstance(value, str):
        return value
    m = _VAR_RE.match(value)
    if not m:
        return value
    name = m.group(1) or m.group(2)
    resolved = environ.get(name)
    return resolved if resolved else None


def _resolve_env_deep(obj, environ: Mapping):
    """Map `_resolve_env` over every string leaf of a nested dict/list."""
    if isinstance(obj, dict):
        return {k: _resolve_env_deep(v, environ) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_deep(v, environ) for v in obj]
    return _resolve_env(obj, environ)


# -- typed validation (fail-loud on malformed; spec R7) ----------------------
def _pos_int(value, key: str) -> int:
    # bool is an int subclass — `true` must not pass as 1.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"director.{key} must be a positive integer, got {value!r}")
    return value


def _pos_num(value, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"director.{key} must be a positive number, got {value!r}")
    return float(value)


def _str_or_none(value, key: str):
    if value is not None and not isinstance(value, str):
        raise ValueError(f"director.{key} must be a string or null, got {value!r}")
    return value


def _bool(value, key: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"director.{key} must be a boolean, got {value!r}")
    return value


def _build(raw: dict) -> DirectorConfig:
    """Validate an (already env-resolved) director block over DEFAULTS and build
    the frozen config. Raises ValueError on any malformed field — the offending
    key is named (fail-loud, spec R7). `_build({})` reproduces DEFAULTS exactly."""
    s_raw = raw.get("states") or {}
    if not isinstance(s_raw, dict):
        raise ValueError("director.states must be an object")
    states = dict(DEFAULTS["states"])
    for k in _STATE_KEYS:  # known logical keys only — unknown keys ignored (§5.3)
        if k in s_raw:
            states[k] = _str_or_none(s_raw[k], f"states.{k}")

    w_raw = raw.get("worker") or {}
    if not isinstance(w_raw, dict):
        raise ValueError("director.worker must be an object")
    w = {**DEFAULTS["worker"], **w_raw}
    if w["approval_policy"] not in _APPROVAL_VALUES:
        raise ValueError(f"director.worker.approval_policy must be one of "
                         f"{sorted(_APPROVAL_VALUES)}, got {w['approval_policy']!r}")
    if w["sandbox"] not in _SANDBOX_VALUES:
        raise ValueError(f"director.worker.sandbox must be one of "
                         f"{sorted(_SANDBOX_VALUES)}, got {w['sandbox']!r}")
    posture = Posture(w["approval_policy"], w["sandbox"],
                      _bool(w["auto_review"], "worker.auto_review"),
                      _bool(w["network"], "worker.network"))

    p_raw = raw.get("paths") or {}
    if not isinstance(p_raw, dict):
        raise ValueError("director.paths must be an object")
    p = {**DEFAULTS["paths"], **p_raw}
    paths = Paths(_str_or_none(p["workspace_root"], "paths.workspace_root"),
                  _str_or_none(p["queue_dir"], "paths.queue_dir"),
                  _str_or_none(p["status_dir"], "paths.status_dir"))

    m_raw = raw.get("merger") or {}
    if not isinstance(m_raw, dict):
        raise ValueError("director.merger must be an object")
    m = {**DEFAULTS["merger"], **m_raw}
    merger = Merger(_pos_num(m["poll_s"], "merger.poll_s"),
                    _pos_num(m["read_timeout_s"], "merger.read_timeout_s"),
                    _pos_int(m["max_merges"], "merger.max_merges"))

    dt = raw.get("done_types", DEFAULTS["done_types"])
    if not isinstance(dt, list) or not dt or not all(isinstance(x, str) for x in dt):
        raise ValueError(f"director.done_types must be a non-empty list of strings, got {dt!r}")

    codex_command = raw.get("codex_command", DEFAULTS["codex_command"])
    if not isinstance(codex_command, str) or not codex_command.strip():
        raise ValueError(f"director.codex_command must be a non-empty string, got {codex_command!r}")

    return DirectorConfig(
        team=_str_or_none(raw.get("team", DEFAULTS["team"]), "team"),
        states=states,
        concurrency=_pos_int(raw.get("concurrency", DEFAULTS["concurrency"]), "concurrency"),
        max_turns=_pos_int(raw.get("max_turns", DEFAULTS["max_turns"]), "max_turns"),
        max_passes=_pos_int(raw.get("max_passes", DEFAULTS["max_passes"]), "max_passes"),
        max_dispatched=_pos_int(raw.get("max_dispatched", DEFAULTS["max_dispatched"]), "max_dispatched"),
        done_types=tuple(dt),
        read_timeout_s=_pos_num(raw.get("read_timeout_s", DEFAULTS["read_timeout_s"]), "read_timeout_s"),
        turn_review_timeout_s=_pos_num(raw.get("turn_review_timeout_s",
                                               DEFAULTS["turn_review_timeout_s"]), "turn_review_timeout_s"),
        reconcile_interval_s=_pos_num(raw.get("reconcile_interval_s",
                                              DEFAULTS["reconcile_interval_s"]), "reconcile_interval_s"),
        poll_interval_s=_pos_num(raw.get("poll_interval_s",
                                         DEFAULTS["poll_interval_s"]), "poll_interval_s"),
        codex_command=codex_command, posture=posture, paths=paths, merger=merger)


def defaults() -> DirectorConfig:
    """The effective config when no `director` block is present (single source —
    the value every entrypoint falls back to)."""
    return _build({})


def load_director_config(root=None, *, environ: Mapping | None = None) -> DirectorConfig:
    """Resolve the effective Director config from `<root>/.harness.json` `director`.

    `root=None` discovers the host root via `policy.discover_root` (the same walk
    `worker_policy` uses). Absent file or absent `director` key → DEFAULTS
    (fail-open). A present-but-broken `.harness.json` or a malformed `director`
    block → raise (fail-loud), at load time — before any worker spawns (spec R7)."""
    environ = os.environ if environ is None else environ
    base = Path(root) if root is not None else policy.discover_root()
    cfg_path = base / ".harness.json"
    if not cfg_path.is_file():
        return _build({})
    try:
        doc = json.loads(cfg_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        # A present file that won't parse is an operator error — fail loud, never
        # silently default (it could be a torn edit of real orchestration policy).
        raise ValueError(f"{cfg_path} is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"{cfg_path} top-level must be an object")
    block = doc.get("director")
    if block is None:
        return _build({})
    if not isinstance(block, dict):
        raise ValueError(".harness.json director must be an object")
    return _build(_resolve_env_deep(block, environ))


def main(argv=None) -> int:
    """`python3 -m director.config [--root R]` — print the resolved effective
    config as JSON (operator surface: "what is this run actually configured with").
    Read-only."""
    ap = argparse.ArgumentParser(
        prog="director.config",
        description="Print the resolved effective Director config as JSON.")
    ap.add_argument("--root", default=None,
                    help="host root holding .harness.json (default: discover upward)")
    args = ap.parse_args(argv)
    print(json.dumps(asdict(load_director_config(root=args.root)),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
