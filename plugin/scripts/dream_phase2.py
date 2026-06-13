#!/usr/bin/env python3
"""Phase 2 of the dreaming pipeline: global consolidation (Codex `phase2.rs`).

Serialized (global lock + 6h cooldown). Selects the top-N stage-1 outputs, syncs
them into the git-baselined workspace (memories_workspace, M4), and — only if the
workspace is git-dirty — spawns ONE locked-down agent that rewrites `MEMORY.md` +
`memory_summary.md` (first line `v1`) using the diff for surgical add/forget. On
success the selection is marked and the baseline reset; on any escape/failure the
workspace is rolled back.

SECURITY — the path restriction (T2/poisoning). Claude Code has no `writable_roots`
sandbox: a headless `claude -p` with the Write tool can write ANYWHERE (verified).
So the agent runs least-privilege (Read/Write/Edit/Glob/LS — NO Bash, NO network;
the only escape vector is Write/Edit to an out-of-workspace path) and we enforce
scope POST-HOC: snapshot every git-visible file in the host repo before the agent
(the workspace itself is gitignored, so "git-visible" == "outside the workspace"),
and after, revert byte-for-byte any that changed — restoring user WIP exactly and
deleting agent-created files. ANY escape hard-fails the run and rolls back the
workspace. Inputs are DATA (T1/T7, stated in the prompt); no raw transcript text
reaches this agent (it reads digest-derived summaries).
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import harness_lib as hl
import memories_db as mdb
import memories_workspace as mw

DEFAULT_MODEL = "sonnet"               # Codex phase 2 = larger/stronger model
PHASE2_TIMEOUT = 1200
PHASE2_LEASE = 1800                    # > timeout: no heartbeat needed at our scale
SNAPSHOT_FILE_CAP = 4 * 1024 * 1024   # scope check covers files up to 4MB (the
#                                       real escape surface is small text/config)


def load_templates():
    d = hl.plugin_root() / "skills" / "dream" / "templates"
    return (d / "consolidation_system.md").read_text(encoding="utf-8"), \
           (d / "consolidation_input.md").read_text(encoding="utf-8")


def render_prompt(system_tmpl, input_tmpl, memory_root):
    filled = input_tmpl.format(memory_root=memory_root,
                               diff_file=mw.WORKSPACE_DIFF_FILE)
    return system_tmpl + "\n\n" + filled


def spawn_phase2(workspace, model, timeout=PHASE2_TIMEOUT, templates=None):
    """Spawn the locked-down consolidation agent (cwd=workspace, least-priv tools,
    headless guard, prompt via stdin). Raises on nonzero/timeout/OS error."""
    system_tmpl, input_tmpl = templates or load_templates()
    prompt = render_prompt(system_tmpl, input_tmpl, workspace)
    proc = subprocess.run(
        ["claude", "-p", "--model", model,
         "--allowedTools", "Read,Write,Edit,Glob,LS"],
        input=prompt, capture_output=True, text=True,
        cwd=str(workspace), env=hl.headless_env(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exit {proc.returncode}: {proc.stderr[:300]}")
    return proc.stdout


# ---- post-hoc workspace-scope enforcement (the T2 path restriction) --------

def _git_root(root, args):
    return subprocess.run(["git", "-C", str(root), *args],
                          capture_output=True, text=True)


def _git_visible_files(root):
    """Tracked + untracked-non-ignored files (repo-relative). The dreaming
    workspace is gitignored, so this is exactly the set OUTSIDE it that an escape
    would touch. Empty if `root` is not a git repo (the check no-ops, logged)."""
    out = set()
    for args in (["ls-files", "-z"],
                 ["ls-files", "--others", "--exclude-standard", "-z"]):
        r = _git_root(root, args)
        if r.returncode == 0:
            out.update(p for p in r.stdout.split("\0") if p)
    return out


_OVERCAP = object()   # sentinel: file is git-visible but its content is over the cap
_MISSING = object()   # sentinel: file was not git-visible at snapshot time


def snapshot_outside_workspace(root):
    """Map every git-visible file (the workspace is gitignored ⇒ this is the set
    OUTSIDE it) to its byte content, or `_OVERCAP` when it exceeds the cap. We
    record the PRESENCE of over-cap files (not their content) so a NEW out-of-cap
    file is still detected as created — only byte-restoring a pre-existing
    over-cap file is out of bound (the escape surface is small text/config)."""
    snap = {}
    for rel in _git_visible_files(root):
        try:
            data = (Path(root) / rel).read_bytes()
        except OSError:
            continue
        snap[rel] = data if len(data) <= SNAPSHOT_FILE_CAP else _OVERCAP
    return snap


def enforce_workspace_scope(root, before):
    """Revert any out-of-workspace write the agent made and return the escaped
    paths (empty = clean). Newly-created files are deleted (ANY size); files whose
    snapshotted bytes changed/were deleted are restored exactly. A pre-existing
    over-cap file that changed is flagged as escaped but not byte-restored (the
    documented bound)."""
    after = snapshot_outside_workspace(root)
    escaped = []
    for rel in set(before) | set(after):
        b = before.get(rel, _MISSING)
        a = after.get(rel, _MISSING)
        if b is a or b == a:               # unchanged (incl. both _OVERCAP / both bytes-equal)
            continue
        escaped.append(rel)
        p = Path(root) / rel
        if b is _MISSING:                  # agent created it (any size) → remove
            try:
                p.unlink()
            except OSError:
                pass
        elif b is _OVERCAP:                # pre-existing over-cap changed → can't byte-restore
            continue                       # detected (escaped) + run is rejected, but no content to restore
        else:                              # had a ≤cap snapshot → restore exact pre-content
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b)
    return sorted(escaped)


def validate_outputs(wdir):
    """Phase-2 must leave a non-empty MEMORY.md and a memory_summary.md whose
    first line is exactly `v1`. Returns (ok, problems)."""
    wdir = Path(wdir)
    problems = []
    mem = wdir / "MEMORY.md"
    if not mem.exists() or not mem.read_text(encoding="utf-8", errors="replace").strip():
        problems.append("MEMORY.md missing or empty")
    summ = wdir / "memory_summary.md"
    if not summ.exists():
        problems.append("memory_summary.md missing")
    else:
        lines = summ.read_text(encoding="utf-8", errors="replace").splitlines()
        if not lines or lines[0].strip() != "v1":
            problems.append("memory_summary.md first line is not exactly `v1`")
    return (not problems, problems)


# ---- orchestration ---------------------------------------------------------

def consolidate(conn, root, now, model=DEFAULT_MODEL, spawn=spawn_phase2,
                worker_id=None, lease_seconds=PHASE2_LEASE):
    """Claim the global lock → select+sync → if dirty, run the locked-down agent
    → enforce scope + validate → mark selected + reset baseline, else reject and
    roll back. `spawn` is injectable for tests (no live model)."""
    worker_id = worker_id or f"dream-{os.getpid()}"
    token = mdb.claim_phase2(conn, worker_id, lease_seconds, now)
    if token is None:
        return {"status": "skipped"}        # running / cooldown / backoff
    wdir = mw.workspace_dir(root)
    try:
        res = mw.select_and_sync(conn, root, now)
        if not res["dirty"]:
            mdb.finish_phase2(conn, token, now, ok=True)
            return {"status": "clean", "selected": res["selected"]}
        if not res["rows"] and not (Path(wdir) / "MEMORY.md").exists():
            # fresh workspace with nothing selected and no existing handbook —
            # don't spawn a model to consolidate zero memories. (An empty
            # selection WITH an existing MEMORY.md still runs: that's forgetting.)
            mw.reset_baseline(wdir)
            mdb.finish_phase2(conn, token, now, ok=True)
            return {"status": "empty", "selected": []}
        before = snapshot_outside_workspace(root)
        spawn(wdir, model)
        escaped = enforce_workspace_scope(root, before)
        ok, problems = validate_outputs(wdir)
        if escaped or not ok:
            mw.discard_workspace_changes(wdir)
            err = ("scope escape: " + ",".join(escaped)) if escaped \
                else ("invalid output: " + "; ".join(problems))
            mdb.finish_phase2(conn, token, now, ok=False, error=err[:500])
            return {"status": "rejected", "escaped": escaped, "problems": problems}
        mdb.mark_phase2_selected(
            conn, [(r["thread_id"], r["source_updated_at"]) for r in res["rows"]])
        mw.reset_baseline(wdir)
        mdb.finish_phase2(conn, token, now, ok=True)
        return {"status": "consolidated", "selected": res["selected"], "escaped": []}
    except Exception as exc:  # noqa: BLE001 — roll back + mark failed (backoff)
        mw.discard_workspace_changes(wdir)
        mdb.finish_phase2(conn, token, now, ok=False, error=str(exc)[:500])
        return {"status": "failed", "error": str(exc)[:200]}


def main():
    root = hl.repo_root()
    now = int(time.time())
    model = os.environ.get("HARNESS_DREAM_PHASE2_MODEL", DEFAULT_MODEL)
    conn = mdb.connect(root)
    try:
        result = consolidate(conn, root, now, model=model)
    finally:
        conn.close()
    json.dump(result, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
