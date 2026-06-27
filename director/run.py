"""Director run entrypoint (Phase 1, M4).

`python -m director.run --ticket <stub.json>` drives ONE Codex app-server worker
through one ticket in an isolated workspace. The worker's approval/input requests
go to the Director queue (the main Claude session answers them via director_min);
the turn resumes on each answer. `--mock` swaps in the bundled fake app-server for
an offline end-to-end run; without it the real `codex app-server` is launched.

Stub ticket JSON:  {"id": "STUB-1", "prompt": "...", "workspace"?: "...", "model"?: "..."}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from director import config, taxonomy
from director.decider import autonomous_decide
from director.worker import autonomy, policy as worker_policy, tools as worker_tools
from director.worker.app_server import AppServerClient, ReadTimeout, TurnCancelled
from director.worker.approval import make_seam

DEFAULT_WORKSPACE_ROOT = Path(".claude/harness/director-workspaces")
# Owned by config.DEFAULTS["max_turns"] (single source); a host overrides via
# .harness.json director.max_turns (the --max-turns flag still wins). Multi-turn
# drive bound (R6): a worker that never signals terminal stops here, reported stuck.
DEFAULT_MAX_TURNS = config.DEFAULTS["max_turns"]
_MOCK = str(Path(__file__).resolve().parent / "worker" / "_mock_app_server.py")
# What the Director vendors into each worker workspace so a WORKER — not just the Director —
# runs the whole methodology. Two surfaces, each placed where the target runtime's NATIVE
# loader actually reads it (asymmetric ON PURPOSE — memory codex-worker-config-surface):
#   - SKILLS: the git/PR/Linear worker skills (`agent-harness-workspace`, Apache-2.0, vendored
#     from openai/symphony) + the methodology skills the worker invokes (`agent-harness`),
#     copied verbatim. Claude Code scans `.claude/skills/`; the REAL Codex CLI scans
#     `.agents/skills/` (the repo path) — NOT `.codex/skills/`, which it never reads.
#   - AGENTS: the review/gardener personas the worker DISPATCHES at the execplan completion
#     gate (`agent-harness`). Claude reads `.claude/agents/*.md` verbatim; the real Codex CLI
#     reads `.codex/agents/*.toml` (translated from the same `.md` source by
#     `_translate_agent_md_to_toml`; the `.codex/` layer loads only when the ws is trusted).
# A runtime dispatches agents only from its own dir, never an arbitrary repo path (memory
# mid-session-agents-not-dispatchable), so agents MUST be copied/translated in. Each plugin's
# LICENSE/NOTICE/manifest live at its plugin root, outside these dirs, so are not copied.
_PLUGIN_ROOT = Path(__file__).resolve().parent.parent
# Skill source dirs — both copied into each runtime's skills dir; their entry-name sets are
# disjoint (`_assert_skill_sources_disjoint`), so they coexist without clobber.
_SKILL_SOURCES = (
    _PLUGIN_ROOT / "plugin-workspace" / "skills",  # git/PR/Linear skills
    _PLUGIN_ROOT / "plugin" / "skills",            # methodology skills
)
# The skills dir each runtime's loader scans: Claude=.claude/skills, Codex=.agents/skills.
_SKILL_DESTS = (".claude/skills", ".agents/skills")
# Agent persona source (.md — the single authoring format) and its per-runtime dest dirs.
_AGENT_SOURCE = _PLUGIN_ROOT / "plugin" / "agents"   # review/gardener personas (.md)
_AGENT_DEST_CLAUDE = ".claude/agents"   # .md copied verbatim (cc-harness reads project agents)
_AGENT_DEST_CODEX = ".codex/agents"     # Codex custom-agent dir (trust-gated `.codex/` layer)
# Every Director-injected methodology dir, for the PR-hygiene `.git/info/exclude` and the
# symlink-refusal sweep. Derived from the dests above so it can never drift from them.
_INJECTED_DIRS = (*_SKILL_DESTS, _AGENT_DEST_CLAUDE, _AGENT_DEST_CODEX)


def _refuse_symlink(path) -> None:
    """A vendored destination (runtime root or leaf dir) that is a symlink is REFUSED, never
    written through — a prior workspace-write worker could plant one to redirect the copy
    outside the workspace (completion-gate P1)."""
    if Path(path).is_symlink():
        raise RuntimeError(f"refusing to install methodology through symlink: {path}")


def _clear_target(target: Path) -> None:
    """Remove a pre-existing target before copy (idempotent re-run + planted-node safety):
    unlink a symlink WITHOUT following it, unlink a special node (fifo/socket/device) or a
    file, rmtree only a REAL directory — a symlink-to-dir is removed as the link itself."""
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        target.unlink()
    elif target.is_dir():
        shutil.rmtree(target)


def _copy_into(src_dir: Path, dst_dir: Path) -> None:
    """Copy every entry of `src_dir` into the already-created, non-symlink `dst_dir`, each
    cleared via `_clear_target` first. Dirs deep-copied, files copied with metadata."""
    for item in src_dir.iterdir():
        target = dst_dir / item.name
        _clear_target(target)
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _assert_skill_sources_disjoint() -> None:
    """The skill sources share one dest dir, so their entry names MUST be disjoint or the
    later copy silently clobbers the earlier. Fail loud (naming both sources) rather than
    rely on disjointness holding as the plugins evolve — they are disjoint today."""
    seen: dict[str, Path] = {}
    for src in _SKILL_SOURCES:
        for item in src.iterdir():
            if item.name in seen:
                raise RuntimeError(f"vendored skill name collision: '{item.name}' from both "
                                   f"{seen[item.name]} and {src}")
            seen[item.name] = src


def _parse_agent_frontmatter(text: str):
    """Split an agent `.md` into (frontmatter dict, body str). Frontmatter is the block
    between the first two `---` fence lines; each entry a `key: value` split on the FIRST
    colon (a value may itself contain colons). Body is everything after the closing `---`,
    with leading blank lines trimmed."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise RuntimeError("agent .md has no opening '---' frontmatter fence")
    fm: dict[str, str] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i].strip()
        if line and ":" in line:
            key, val = line.split(":", 1)
            fm[key.strip()] = val.strip()
        i += 1
    if i >= len(lines):
        raise RuntimeError("agent .md frontmatter not closed with '---'")
    return fm, "".join(lines[i + 1:]).lstrip("\n")


def _toml_basic_string(s: str) -> str:
    """A single-line TOML basic string with the minimal escapes (backslash, double-quote)."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _translate_agent_md_to_toml(md_path: Path) -> str:
    """Translate a Claude agent `.md` (frontmatter `name`/`description`/`tools` + markdown
    body) into a Codex custom-agent TOML (developers.openai.com/codex/subagents): the three
    required keys `name`/`description`/`developer_instructions`, plus a `sandbox_mode` derived
    from the `.md` `tools` (Edit/Write present → `workspace-write`, else `read-only` — Codex
    has no tool allowlist, so the sandbox posture is the closest equivalent). `name` is kept
    IDENTICAL to the `.md` so the methodology's bare-name dispatch refers to one name on both
    runtimes. The body becomes `developer_instructions` verbatim via a TOML multiline LITERAL
    string (no escape processing — safe for the regex/backslashes/quotes in a persona prompt;
    the only sequence it cannot contain is `'''`, which we reject loudly)."""
    fm, body = _parse_agent_frontmatter(md_path.read_text(encoding="utf-8"))
    for req in ("name", "description"):
        if not fm.get(req):
            raise RuntimeError(f"agent {md_path.name} missing frontmatter '{req}'")
    tools = fm.get("tools", "")
    sandbox = "workspace-write" if ("Edit" in tools or "Write" in tools) else "read-only"
    if "'''" in body:
        raise RuntimeError(f"agent {md_path.name} body contains \"'''\" — cannot emit it as a "
                           f"TOML literal string; escape it in the source or extend the translator")
    return (f"name = {_toml_basic_string(fm['name'])}\n"
            f"description = {_toml_basic_string(fm['description'])}\n"
            f"sandbox_mode = {_toml_basic_string(sandbox)}\n"
            f"developer_instructions = '''\n{body}'''\n")


def _install_agents(ws: Path) -> None:
    """Vendor the review/gardener personas into BOTH runtimes' agent dirs, each in its NATIVE
    format: Claude reads `.claude/agents/*.md` (copied verbatim); the real Codex CLI reads
    `.codex/agents/*.toml` (translated — `_translate_agent_md_to_toml`). Codex loads the
    `.codex/agents/` layer only when the workspace is TRUSTED — handled at launch (M3)."""
    # Claude — copy the .md personas verbatim.
    _refuse_symlink(ws / Path(_AGENT_DEST_CLAUDE).parts[0])
    claude = ws / _AGENT_DEST_CLAUDE
    _refuse_symlink(claude)
    claude.mkdir(parents=True, exist_ok=True)
    _copy_into(_AGENT_SOURCE, claude)
    # Codex — translate each .md persona into a custom-agent .toml.
    _refuse_symlink(ws / Path(_AGENT_DEST_CODEX).parts[0])
    codex = ws / _AGENT_DEST_CODEX
    _refuse_symlink(codex)
    codex.mkdir(parents=True, exist_ok=True)
    for item in sorted(_AGENT_SOURCE.iterdir()):
        if item.is_file() and item.suffix == ".md":
            target = codex / (item.stem + ".toml")
            _clear_target(target)
            target.write_text(_translate_agent_md_to_toml(item), encoding="utf-8")


def install_worker_methodology(workspace) -> None:
    """Vendor the worker skills + the agent-harness methodology (skills + review/gardener
    agents) into each runtime's NATIVE loader path so a WORKER (not just the Director) runs
    the whole execplan completion gate. Skills → `.claude/skills/` (Claude) and
    `.agents/skills/` (the only repo path the real Codex CLI scans); agents → `.claude/agents/`
    (Claude, `.md`) and `.codex/agents/` (Codex). The review agents are the load-bearing part:
    a runtime dispatches agents only from its own dir, never an arbitrary repo path, so without
    this copy the worker's gate has no personas to dispatch (memory:
    mid-session-agents-not-dispatchable, codex-worker-config-surface).

    Safety (completion-gate P1): the per-ticket workspace is reused across runs and a prior
    worker (workspace-write sandbox) can plant symlinks, so we never write THROUGH a
    pre-existing symlink — `_refuse_symlink` rejects a symlinked runtime root or dest dir, and
    `_clear_target` removes each target (link unlinked, special node/file deleted, real dir
    rmtree'd) before a fresh copy. Idempotent.

    PR hygiene: the injected methodology is not part of the ticket's work, so its dirs are
    added to the clone's local `.git/info/exclude` (uncommitted, modifies no tracked file)
    and thus stay out of `git status`/`git add -A` — see `_exclude_injected_methodology`."""
    ws = Path(workspace)
    _assert_skill_sources_disjoint()
    # SKILLS — copy both source dirs verbatim into each runtime's skills dir.
    for dest in _SKILL_DESTS:
        _refuse_symlink(ws / Path(dest).parts[0])  # the runtime root (.claude / .agents)
        dst = ws / dest
        _refuse_symlink(dst)
        dst.mkdir(parents=True, exist_ok=True)
        for src in _SKILL_SOURCES:
            _copy_into(src, dst)
    # AGENTS — Claude reads .md verbatim; Codex reads its own `.codex/agents/` dir.
    _install_agents(ws)
    _exclude_injected_methodology(ws)


def _exclude_injected_methodology(ws: Path) -> None:
    """Keep the Director-injected methodology dirs (`skills/` + `agents/`) out of the
    worker's PR via the clone's `.git/info/exclude` — a per-clone, uncommitted ignore that
    touches no tracked file and never appears in the worker's diff (a worker that runs
    `git add -A` would otherwise stage the methodology). No-op when the workspace has no git
    dir (mock/offline runs). Like the skill/agent copy, this REFUSES to write through a
    planted symlink: a prior sandboxed worker that symlinked `.git`, `.git/info`, or the
    `exclude` file could otherwise redirect this write outside the workspace."""
    gitdir = ws / ".git"
    if gitdir.is_symlink():
        raise RuntimeError(f"refusing to write exclude through symlinked git dir: {gitdir}")
    if not gitdir.is_dir():
        return
    info = gitdir / "info"
    if info.is_symlink():
        raise RuntimeError(f"refusing to write exclude through symlink: {info}")
    info.mkdir(exist_ok=True)
    exclude = info / "exclude"
    if exclude.is_symlink():
        raise RuntimeError(f"refusing to write exclude through symlink: {exclude}")
    existing = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    patterns = [f"/{d}/" for d in _INJECTED_DIRS]
    missing = [p for p in patterns if p not in existing.splitlines()]
    if not missing:
        return
    prefix = existing if (not existing or existing.endswith("\n")) else existing + "\n"
    note = "# director: injected worker methodology (not part of the ticket)\n"
    exclude.write_text(prefix + note + "\n".join(missing) + "\n", encoding="utf-8")


def load_ticket(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if "id" not in data or "prompt" not in data:
        raise ValueError("stub ticket needs at least 'id' and 'prompt'")
    return {"id": data["id"], "prompt": data["prompt"],
            "model": data.get("model"), "workspace": data.get("workspace")}


def workspace_key(identifier) -> str:
    """Sanitize a board identifier into a single-component workspace directory NAME
    (Symphony §9.5 invariant 3): every character outside `[A-Za-z0-9._-]` becomes `_`, so
    a `/` can no longer split the key into multiple path segments. Note `.` IS allowed, so
    a degenerate id (`""`/`.`/`..`) still yields a key that resolves to the root or its
    parent — sanitization alone is NOT sufficient containment. `is_contained` (applied at
    every derive and every delete site) is the mandatory guard that rejects those."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(identifier))


def workspace_path(identifier, workspace_root) -> Path:
    """The per-ticket workspace path — `<root>/<sanitized key>`. The SINGLE derivation
    used by dispatch (`_workspace_for`), merge-enqueue (`orchestrator._maybe_enqueue_merge`),
    and startup cleanup (`orchestrator._startup_recovery`) so all three agree on the
    directory for a given (id, root) (ARCHITECTURE invariant 8 — shared helper, not
    re-derived per call site)."""
    return Path(workspace_root) / workspace_key(identifier)


def is_contained(path, workspace_root) -> bool:
    """True iff `path` resolves to a STRICT descendant of `workspace_root` — under the
    root AND not the root itself (spec R2b / Symphony §9.5 invariant 2: a workspace is
    "a directory whose parent is the workspace root", never the root). Strictness is
    load-bearing because the cleanup paths `rmtree` this: a degenerate sanitized key
    (`""`/`.`/`..`) resolves to the root or its parent, and must NOT count as a contained
    workspace, or cleanup could delete the entire root (review-security/spec-compliance
    P1). Pure path comparison (no fs writes); shared by dispatch (reject an escaping
    derived path) and cleanup (never rmtree at/above the root). An unresolvable/
    incomparable path is NOT contained (fail safe)."""
    try:
        resolved = Path(path).resolve()
        root = Path(workspace_root).resolve()
        return resolved != root and resolved.is_relative_to(root)
    except (OSError, ValueError):
        return False


def _expected_ws(ticket: dict, workspace_root) -> Path:
    """The workspace path a ticket resolves to — explicit override or derived (sanitized).
    Pure (no mkdir); shared by `_prepare`'s cwd assert and the lifecycle-hook call sites so
    they target the same dir `_workspace_for` creates."""
    return Path(ticket["workspace"]) if ticket.get("workspace") \
        else workspace_path(ticket["id"], workspace_root)


def run_hook(name: str, script, *, cwd, timeout_s: float, fatal: bool) -> None:
    """Run one workspace lifecycle hook (Symphony §9.4) as `sh -lc <script>` with cwd=the
    workspace, under a wall-clock timeout. Director-side (trusted host config — runs with the
    Director's own environment, so a private-repo clone has credential reach). A falsy
    `script` is a no-op. Start/failure/timeout log a structured line to STDERR (the
    daemon-diagnostic stream). On non-zero exit or timeout: if `fatal` (after_create/
    before_run) raise; else (after_run/before_remove) swallow. Never returns a value —
    hooks are side-effecting."""
    if not script:
        return
    print(json.dumps({"hook": name, "event": "start", "cwd": str(cwd)}), file=sys.stderr)
    try:
        proc = subprocess.run(["sh", "-lc", script], cwd=str(cwd), env=os.environ.copy(),
                              capture_output=True, text=True, timeout=timeout_s)
    except subprocess.TimeoutExpired as exc:
        print(json.dumps({"hook": name, "event": "timeout", "timeout_s": timeout_s}),
              file=sys.stderr)
        if fatal:
            raise RuntimeError(f"workspace hook {name!r} timed out after {timeout_s}s") from exc
        return
    except OSError as exc:
        # Launch failure (missing `sh`, a `cwd` deleted out from under us by a concurrent
        # session, perms). run_hook must be TOTAL against this family (RELIABILITY R8):
        # a non-fatal hook (after_run/before_remove) MUST swallow it, never crash the reap
        # loop / daemon nor mask a disposition; a fatal hook still raises.
        print(json.dumps({"hook": name, "event": "error", "error": str(exc)}),
              file=sys.stderr)
        if fatal:
            raise RuntimeError(f"workspace hook {name!r} failed to launch: {exc}") from exc
        return
    if proc.returncode != 0:
        print(json.dumps({"hook": name, "event": "failed", "code": proc.returncode,
                          "stderr": (proc.stderr or "")[-2000:]}), file=sys.stderr)
        if fatal:
            raise RuntimeError(f"workspace hook {name!r} failed (exit {proc.returncode})")


def _workspace_for(ticket: dict, workspace_root) -> tuple[Path, bool]:
    explicit = ticket.get("workspace")
    if explicit:
        # Explicit override: the single-ticket-CLI / test affordance (a trusted caller
        # may target an arbitrary path, e.g. /tmp). It is NEVER produced by the Linear
        # daemon path (board ids are always derived), so it is exempt from the
        # containment check below (the board-controlled id is the real escape vector,
        # and workspace_key sanitizes that).
        ws = Path(explicit)
    else:
        ws = workspace_path(ticket["id"], workspace_root)
        # Containment (§9.5 invariant 2): the derived path MUST resolve under the root.
        # workspace_key already guarantees this; the check catches a sanitizer regression
        # before any mkdir or worker launch.
        if not is_contained(ws, workspace_root):
            raise RuntimeError(f"workspace path escapes root: {ws} not under {workspace_root}")
    created_now = not ws.exists()  # captured BEFORE mkdir — drives the after_create hook
    ws.mkdir(parents=True, exist_ok=True)
    return ws, created_now


def _with_codex_trust(command: list[str], ws) -> list[str]:
    """Append `-c projects."<ws_abs>".trust_level="trusted"` to the launch command so the real
    Codex CLI loads the workspace's project `.codex/` layer — the vendored `.codex/agents/*.toml`
    personas live there, and Codex SKIPS project-scoped `.codex/` layers for an UNTRUSTED project
    (developers.openai.com/codex/config-basic: "untrusted → skips project-scoped `.codex/`
    layers, including project-local config, hooks, and rules"). Skills are unaffected (they load
    from the repo `.agents/skills/` scan, not a trust-gated `.codex/` layer).

    Security (SECURITY.md): trusting the workspace ALSO makes Codex read the cloned target repo's
    own `.codex/config.toml` — a new untrusted-input surface. It cannot loosen the worker's
    posture, because CLI `-c`/`--config` and the `thread/start` approvalPolicy+sandbox params
    OUTRANK project config (config-basic precedence #1 > #2); the autonomy `-c` flags + thread
    params already pin approval/sandbox/network above anything the project file could set.

    Only the bash-wrapped real runtime is touched: a mock command (not `bash -c …`) is returned
    unchanged. The key is a no-op for the Claude adapter (it ignores codex `projects.*` config),
    matching how the autonomy `-c` flags already reach both runtimes. The path is shell-quoted so
    bash passes the TOML quoted-key literally to codex's `-c` parser (verified accepted)."""
    if len(command) == 3 and command[0] == "bash" and command[1] == "-c":
        kv = f'projects."{os.path.abspath(str(ws))}".trust_level="trusted"'
        return [command[0], command[1], command[2] + f" -c {shlex.quote(kv)}"]
    return command


def _prepare(ticket: dict, *, command, queue_base, workspace_root, timeout_s,
             read_timeout_s, tool_executor, install_skills,
             worker_env: dict | None = None, cancel_event=None,
             hooks: dict | None = None, hook_timeout_s: float = 60.0,
             on_event=None) -> AppServerClient:
    """Build (but do not start) the worker client for one ticket: resolve+create the
    workspace, run the create/run lifecycle hooks, optionally install the worker methodology,
    and wire the approval seam. Shared by the single-turn `run_ticket` and the multi-turn
    `drive`.

    Secure by construction: unless the caller passes an explicit `worker_env`, the
    worker subprocess env is the **deny-by-default** construction from the host policy
    (director/worker/policy.py) — a worker never inherits the Director's host secrets
    (SECURITY.md T11, env-inheritance channel)."""
    hooks = hooks or {}
    ws, created_now = _workspace_for(ticket, workspace_root)
    # after_create (Symphony §9.4): populate a BRAND-NEW workspace (the repo-population
    # clone). FATAL — a worker must never start on a workspace whose population failed.
    if created_now:
        run_hook("after_create", hooks.get("after_create"), cwd=ws,
                 timeout_s=hook_timeout_s, fatal=True)
    # §9.5 invariant 1 (R2d): before launch, the worker's cwd (we pass cwd=ws below) must
    # be a real directory AND resolve to exactly the canonical workspace path. `expected`
    # is re-derived independently of `_workspace_for`, so this catches a future refactor
    # that lets the launch cwd drift off the contained workspace, not just a torn path.
    expected = _expected_ws(ticket, workspace_root)
    if not ws.is_dir():
        raise RuntimeError(f"workspace path is not a directory before launch: {ws}")
    if ws.resolve() != expected.resolve():
        raise RuntimeError(f"launch cwd {ws} != expected workspace {expected}")
    # before_run (Symphony §9.4): runs before EVERY attempt (e.g. sync to origin/main).
    # FATAL — abort the attempt if the pre-run sync fails.
    run_hook("before_run", hooks.get("before_run"), cwd=ws,
             timeout_s=hook_timeout_s, fatal=True)
    if install_skills:
        install_worker_methodology(ws)
    # Trust the workspace so Codex loads the project `.codex/` layer we just vendored into
    # (`.codex/agents/*.toml`); a no-op for mock/Claude (see `_with_codex_trust`).
    command = _with_codex_trust(command, ws)
    if worker_env is None:
        worker_env = worker_policy.build_worker_env(worker_policy.load_worker_policy())
    seam = make_seam(str(ticket["id"]), str(ws), base=queue_base, timeout_s=timeout_s)
    return AppServerClient(command, cwd=ws, on_server_request=seam,
                           tool_executor=tool_executor, read_timeout_s=read_timeout_s,
                           env=worker_env, cancel_event=cancel_event, on_event=on_event)


def run_ticket(ticket: dict, *, command: list[str], queue_base=None,
               workspace_root=DEFAULT_WORKSPACE_ROOT,
               timeout_s: float = 300.0, read_timeout_s: float = 30.0,
               tools=None, tool_executor=None, install_skills: bool = False,
               approval_policy: str = "untrusted",
               sandbox: str = "workspace-write",
               hooks: dict | None = None, hook_timeout_s: float = 60.0,
               on_event=None) -> dict:
    """Drive one worker through ONE turn; returns {status, turn_id, final_message}.

    The single-turn primitive (kept for callers that want one turn). The multi-turn
    driver is `drive`. `approval_policy`/`sandbox` set the worker's Codex posture on
    thread AND turn (the autonomous preset passes `on-request`/`workspace-write`; the
    default is the conservative watched `untrusted`)."""
    client = _prepare(ticket, command=command, queue_base=queue_base,
                      workspace_root=workspace_root, timeout_s=timeout_s,
                      read_timeout_s=read_timeout_s, tool_executor=tool_executor,
                      install_skills=install_skills, hooks=hooks,
                      hook_timeout_s=hook_timeout_s, on_event=on_event)
    try:
        with client as c:
            c.initialize()
            thread_id = c.thread_start(model=ticket.get("model"), tools=tools,
                                       approval_policy=approval_policy, sandbox=sandbox)
            # `sandbox` is a THREAD-level attribute (set on thread/start only); the turn
            # inherits it, so run_turn takes approval_policy but not sandbox.
            return c.run_turn(thread_id, ticket["prompt"], approval_policy=approval_policy)
    finally:
        # after_run (Symphony §9.4): fires once the attempt ends, on any outcome; logged
        # and ignored (never alters the result).
        run_hook("after_run", (hooks or {}).get("after_run"),
                 cwd=_expected_ws(ticket, workspace_root), timeout_s=hook_timeout_s,
                 fatal=False)


def drive(ticket: dict, *, command: list[str], decide=autonomous_decide,
          queue_base=None, workspace_root=DEFAULT_WORKSPACE_ROOT,
          timeout_s: float = 300.0, read_timeout_s: float = 30.0,
          tools=None, tool_executor=None, install_skills: bool = False,
          approval_policy: str = "untrusted", sandbox: str = "workspace-write",
          max_turns: int = DEFAULT_MAX_TURNS, attempt: int = 1, cancel_event=None,
          hooks: dict | None = None, hook_timeout_s: float = 60.0,
          on_event=None) -> dict:
    """Drive one worker through one ticket across MULTIPLE turns on a SINGLE thread
    until the worker is terminal (or `max_turns` is hit). This is the multi-turn
    slice's core: a ticket is a thread, a turn end is an *event* not a completion,
    and the per-turn disposition is owned by the injected `decide` (LLM/human in a
    watched run; the autonomous code decider un-watched) — never by this code (R4).

    Returns the FINAL disposition, enriched with run facts (incl. a `telemetry`
    block — Symphony-grade per-ticket tokens/turn_count/session_id/last_message/
    rate_limits — present on every kind, plan M2):
      {"kind": "terminal",  "outcome": {...}, "turns", "turn_id", "final_message", "thread_id"}
      {"kind": "escalate",  "reason": str, "outcome"?, "turns", ...}        # taste → human
      {"kind": "stuck",     "reason": "max_turns", "turns", ...}            # R6 bound
      {"kind": "failed",    "status": "failed"|"cancelled", "turns", ...}   # a turn errored

    `report_outcome` is wired in HERE (not by the caller): a per-turn sink captures the
    worker's terminal proposal, composed over any `tool_executor` the caller passed
    (e.g. linear_graphql), and `report_outcome` is appended to the advertised tools."""
    sink: dict = {}
    report_exec = worker_tools.make_report_outcome_executor(sink)

    def combined(name, arguments):
        if name == worker_tools.REPORT_OUTCOME_TOOL:
            return report_exec(name, arguments)
        if tool_executor is not None:
            return tool_executor(name, arguments)
        return {"success": False, "output": f"unsupported tool: {name!r}"}

    advertised = list(tools or [])
    if not any(t.get("name") == worker_tools.REPORT_OUTCOME_TOOL for t in advertised):
        advertised.append(worker_tools.report_outcome_spec())

    client = _prepare(ticket, command=command, queue_base=queue_base,
                      workspace_root=workspace_root, timeout_s=timeout_s,
                      read_timeout_s=read_timeout_s, tool_executor=combined,
                      install_skills=install_skills, cancel_event=cancel_event,
                      hooks=hooks, hook_timeout_s=hook_timeout_s, on_event=on_event)
    turns = 0
    turn_id = None
    thread_id = None
    final_message = None
    usage = None        # latest ABSOLUTE thread token totals (not a sum — §13.5)
    rate_limits = None  # latest rate-limit payload seen

    def _telemetry() -> dict:
        # Symphony-grade per-ticket telemetry (plan M2), folded into every
        # disposition via `base`. session_id = "<thread>-<turn>" (§4.1.6); tokens is
        # the LATEST absolute thread total (codex reports cumulative totals, so the
        # last value IS the ticket total — summing would double-count).
        sid = f"{thread_id}-{turn_id}" if (thread_id and turn_id) else None
        return {"tokens": usage, "turn_count": turns, "session_id": sid,
                "last_message": final_message, "rate_limits": rate_limits}

    def _cancelled() -> dict:
        # Active-run reconciliation stopped this worker (its ticket left `started`).
        # A DISTINCT disposition kind from "failed" so the orchestrator releases it
        # without a retry (D-59/D-62); carries the run facts like every other return.
        return {"kind": "cancelled", "reason": "reconciliation", "turns": turns,
                "turn_id": turn_id, "final_message": final_message,
                "thread_id": thread_id, "telemetry": _telemetry()}

    # after_run (Symphony §9.4) fires once this attempt ends, on ANY return path
    # (terminal/escalate/stuck/failed/cancelled); logged and ignored, never alters the
    # disposition. The finally wraps the whole worker session below.
    try:
        with client as c:
            # Wrap the WHOLE session: a reconciliation cancel can land during the handshake
            # (initialize/thread_start) or mid-turn (run_turn) — both surface as TurnCancelled
            # and must release, not fail-and-retry (D-59).
            try:
                c.initialize()
                thread_id = c.thread_start(model=ticket.get("model"), tools=advertised,
                                           approval_policy=approval_policy, sandbox=sandbox)
                # First turn: frame the ticket with the stage-agnostic WORKER PROTOCOL
                # (operating disciplines) + the multi-turn TURN PROTOCOL (terminal contract)
                # so the worker self-governs and knows to call report_outcome at terminal
                # (else un-watched it would loop to stuck). This single seam covers every
                # dispatch path (orchestrator, run.main, direct-drive). Later turns carry the
                # decider's directive verbatim.
                input_text = taxonomy.frame_first_turn(ticket["prompt"])
                for i in range(max_turns):
                    # Between-turns cancel check (covers the gap while a watched decider was
                    # parked); mid-turn cancellation arrives as TurnCancelled from run_turn.
                    if cancel_event is not None and cancel_event.is_set():
                        return _cancelled()
                    turns = i + 1
                    sink.pop("outcome", None)  # fresh terminal-signal slot for this turn
                    result = c.run_turn(thread_id, input_text, approval_policy=approval_policy)
                    turn_id = result.get("turn_id")
                    final_message = result.get("final_message")
                    if result.get("usage") is not None:        # keep latest absolute totals
                        usage = result["usage"]
                    if result.get("rate_limits") is not None:
                        rate_limits = result["rate_limits"]
                    status = result.get("status")
                    base = {"turns": turns, "turn_id": turn_id,
                            "final_message": final_message, "thread_id": thread_id,
                            "telemetry": _telemetry()}
                    if status != "completed":  # turn/failed | turn/cancelled — not a disposition
                        return {"kind": "failed", "status": status, **base}
                    if _rate_limited(rate_limits):  # F7: credits/window exhausted → the worker
                        # returns empty turns (no progress). PARK now (a distinct escalate) rather
                        # than loop on empty turn-ends (watched) or burn turns to `stuck` (un-watched);
                        # retrying can't help until the window resets — a human/Director resumes it.
                        return {"kind": "escalate", "reason":
                                "rate-limited — Codex credits/window exhausted; awaiting reset", **base}
                    disp = decide({"ticket": ticket, "turn_index": i, "status": status,
                                   "final_message": final_message, "outcome": sink.get("outcome"),
                                   "attempt": attempt})
                    if disp.get("kind") in ("terminal", "escalate"):
                        return {**disp, **base}
                    # kind == "reply": continue the SAME thread with the directive (board untouched)
                    input_text = disp.get("reply") or ""
            except TurnCancelled:  # mid-turn reconciliation cancel (D-59) — release, no retry
                return _cancelled()
            except ReadTimeout:  # F3: worker silent past read_timeout (cold start / a long
                # command / deep reasoning) — a RECOVERABLE failure, not an uncaught crash;
                # the orchestrator's reconcile retries it like any failed turn (R6 bound).
                return {"kind": "failed", "status": "read_timeout", "turns": turns,
                        "turn_id": turn_id, "final_message": final_message,
                        "thread_id": thread_id, "telemetry": _telemetry()}
        return {"kind": "stuck", "reason": "max_turns", "turns": turns,
                "turn_id": turn_id, "final_message": final_message, "thread_id": thread_id,
                "telemetry": _telemetry()}
    finally:
        run_hook("after_run", (hooks or {}).get("after_run"),
                 cwd=_expected_ws(ticket, workspace_root), timeout_s=hook_timeout_s,
                 fatal=False)


def _rate_limited(rate_limits) -> bool:
    """True only when the worker's latest rate-limit payload CLEARLY shows exhaustion —
    no credits, or a fully-spent primary window (use-all shakedown F7). Total over a
    missing/odd shape (R12): anything unclear → False, so a healthy run is never falsely
    parked. Case-tolerant — codex emits `has_credits` (snake) or `hasCredits`/`usedPercent`
    (camel) across versions; `extract_rate_limits` stores the payload raw."""
    if not isinstance(rate_limits, dict):
        return False
    credits = rate_limits.get("credits")
    if isinstance(credits, dict):
        hc = credits.get("has_credits", credits.get("hasCredits"))
        if hc is False:
            return True
    primary = rate_limits.get("primary")
    if isinstance(primary, dict):
        up = primary.get("usedPercent", primary.get("used_percent"))
        if isinstance(up, (int, float)) and not isinstance(up, bool) and up >= 100:
            return True
    return False


def _command(args, codex_command, posture) -> list[str]:
    if args.mock:
        return [sys.executable, _MOCK, args.mock_scenario]
    # Posture (auto_review / network) is the resolved config's (a host may tighten it
    # in .harness.json director.worker). Exfil deferred (T11).
    # `bash -c` (NOT `-lc`): a LOGIN shell would source the host's profile and re-inject
    # env the deny-by-default boundary (Popen env=) just stripped — defeating it for any
    # secret a user exports in ~/.profile etc. Non-login + `BASH_ENV` denied (not in the
    # base) means the worker's env is exactly the constructed one. The base carries PATH,
    # so codex still resolves (worker-secret-boundary M1, SECURITY.md T11).
    codex = autonomy.codex_command(codex_command, auto_review=posture.auto_review,
                                   network=posture.network)
    return ["bash", "-c", codex]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="director.run")
    ap.add_argument("--ticket", help="path to a stub ticket JSON")
    ap.add_argument("--linear", help="Linear issue id/identifier to read as the ticket")
    ap.add_argument("--mock", action="store_true", help="use the bundled fake app-server")
    ap.add_argument("--mock-scenario", default="plain",
                    choices=["plain", "approval", "approval_done", "report",
                             "tool", "turn_failed"])
    ap.add_argument("--codex", default=None, help="real worker command (raw override)")
    ap.add_argument("--worker", default=None,
                    help="worker runtime to dispatch: a key in director.worker_runtimes "
                         "(default: director.worker_runtime, built-in 'codex')")
    ap.add_argument("--queue-dir", default=None, help="Director queue dir override")
    ap.add_argument("--tools", choices=["none", "linear"], default="none",
                    help="advertise worker tools (linear = linear_graphql)")
    ap.add_argument("--install-skills", action="store_true",
                    help="install both plugins into the worker workspace — skills into "
                         ".claude/skills + .agents/skills, agents into .claude/agents + "
                         ".codex/agents (each runtime's native loader path)")
    ap.add_argument("--autonomous", action="store_true",
                    help="un-watched: use the code turn-end decider (no live Director "
                         "answers turn ends). Per-action self-governance (on-request + "
                         "auto_review) and full network are shared with the watched default")
    ap.add_argument("--max-turns", type=int, default=None,
                    help="multi-turn drive bound (R6); over it → stuck")
    args = ap.parse_args(argv)

    # Resolve posture / codex / bounds CLI > config > default (declarative-config
    # slice). A malformed .harness.json director block raises here, before any spawn.
    cfg = config.load_director_config()
    codex_command = (args.codex if args.codex is not None
                     else config.resolve_worker_command(cfg, args.worker))
    max_turns = args.max_turns if args.max_turns is not None else cfg.max_turns
    queue_dir = args.queue_dir if args.queue_dir is not None else cfg.paths.queue_dir

    if args.linear:
        from director.board.linear import read_issue
        issue = read_issue(args.linear)
        ticket = {"id": issue["identifier"], "prompt": issue["prompt"]}
    elif args.ticket:
        ticket = load_ticket(args.ticket)
    else:
        ap.error("one of --ticket or --linear is required")
    tools = None
    tool_executor = None
    if args.tools == "linear":
        from director.worker.tools import linear_graphql_spec, make_linear_tool_executor
        tools = [linear_graphql_spec()]
        tool_executor = make_linear_tool_executor()
    # Per-action posture is the resolved config's (a host may tighten it in
    # .harness.json director.worker; the command's auto_review/network follow it).
    posture = cfg.posture
    # Workspace lifecycle hooks (R4) from the resolved config — disabled under --mock
    # (the offline fake app-server has no real repo to populate).
    hooks = None if args.mock else cfg.workspace.hooks
    # The single-ticket CLI is un-watched (no orchestrator queue / live Director to
    # answer turn reviews), so it drives with the autonomous code decider.
    disp = drive(ticket, command=_command(args, codex_command, posture),
                 decide=autonomous_decide, queue_base=queue_dir, tools=tools,
                 tool_executor=tool_executor, install_skills=args.install_skills,
                 approval_policy=posture.approval_policy,
                 sandbox=config.resolve_worker_sandbox(cfg, args.worker),
                 max_turns=max_turns,
                 read_timeout_s=config.resolve_worker_read_timeout(cfg, args.worker), hooks=hooks,
                 hook_timeout_s=cfg.workspace.hook_timeout_s)
    print(json.dumps({"ticket": ticket["id"], **disp}))
    return 0 if disp.get("kind") == "terminal" else 1


if __name__ == "__main__":
    raise SystemExit(main())
