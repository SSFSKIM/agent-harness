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
scope POST-HOC: snapshot every file under the host repo EXCEPT the workspace
subtree before the agent — including gitignored files and the host `.git/`
(hooks/config are code-exec vectors) — and after, restore byte-for-byte any that
changed, recreating the exact entry (symlink-safe: snapshot/restore never follow
links). ANY escape hard-fails the run and rolls back the workspace. Inputs are
DATA (T1/T7, stated in the prompt); no raw transcript text reaches this agent (it
reads digest-derived summaries).
"""
import hashlib
import json
import os
import shutil
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
SNAPSHOT_FILE_CAP = 4 * 1024 * 1024   # ≤ cap: snapshot bytes (exact restore);
#                                       over cap: snapshot a sha256 (change still
#                                       detected; restore is best-effort git)


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


# Subtrees pruned from the scope snapshot: the dreaming workspace (where the agent
# legitimately writes) and git's content-addressed object stores (huge; writing a
# loose object executes nothing — the exec vectors `.git/hooks`/`.git/config` are
# NOT under these and stay covered).
_PRUNE_GIT = (os.path.join(".git", "objects"), os.path.join(".git", "lfs"))


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _entry(p):
    """Symlink-safe snapshot of one path (never follows links). A regular file ≤
    cap → ('file', bytes); over cap → ('over', sha256) (change-detectable without
    holding content); a symlink → ('link', target); anything else → ('other',)."""
    if p.is_symlink():
        return ("link", os.readlink(p))
    if p.is_file():                        # not a symlink (checked above) → safe
        if p.stat().st_size <= SNAPSHOT_FILE_CAP:
            return ("file", p.read_bytes())
        return ("over", _sha(p))
    return ("other",)


def snapshot_outside_workspace(root):
    """Snapshot every entry under `root` EXCEPT the workspace subtree and git's
    object stores — INCLUDING gitignored files and the host `.git/` (hooks/config
    are code-exec vectors). Keyed by repo-relative path. The boundary is the
    filesystem, not git-visibility, so an escape into an ignored or `.git` path is
    caught."""
    root = Path(root)
    ws_rel = os.path.relpath(str(mw.workspace_dir(root)), str(root))
    snap = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = os.path.relpath(dirpath, root)
        kept = []
        for dn in dirnames:
            rel = dn if rel_dir == "." else os.path.normpath(os.path.join(rel_dir, dn))
            full = Path(dirpath) / dn
            if full.is_symlink():          # capture symlinked dirs as links, don't descend
                snap[rel] = ("link", os.readlink(full))
                continue
            if rel == ws_rel or rel.startswith(ws_rel + os.sep) or rel in _PRUNE_GIT:
                continue
            kept.append(dn)
        dirnames[:] = kept
        for fn in filenames:
            rel = fn if rel_dir == "." else os.path.normpath(os.path.join(rel_dir, fn))
            try:
                snap[rel] = _entry(Path(dirpath) / fn)
            except OSError:
                continue
    return snap


def _strip_symlinked_parents(root, rel):
    """Remove any symlinked directory in rel's parent chain. The agent must not
    turn an in-repo dir into a symlink; if it did, a later write/restore at `rel`
    would go THROUGH the link to an outside target. Unlinking the first symlinked
    ancestor (and stopping — everything below it is gone) guarantees subsequent
    `mkdir(parents=True)` rebuilds real directories."""
    cur = Path(root)
    for part in Path(rel).parts[:-1]:
        cur = cur / part
        if cur.is_symlink():
            try:
                cur.unlink()
            except OSError:
                pass
            return


def _remove_current(root, rel):
    """Delete whatever the agent left at `rel` (after clearing symlinked parents),
    never following links."""
    _strip_symlinked_parents(root, rel)
    p = Path(root) / rel
    try:
        if p.is_symlink() or p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p)
    except OSError:
        pass


def _recreate(root, rel, entry):
    """Recreate a snapshotted file/symlink entry into a symlink-free parent chain."""
    _strip_symlinked_parents(root, rel)
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        if p.is_symlink() or p.exists():
            _remove_current(root, rel)               # never write through a leftover
        if entry[0] == "file":
            p.write_bytes(entry[1])
        elif entry[0] == "link":
            os.symlink(entry[1], p)
        # 'other' (fifo/socket) — presence-only; not recreated
    except OSError:
        pass


def enforce_workspace_scope(root, before):
    """Restore any out-of-workspace change the agent made; return the escaped
    paths (empty = clean). Two passes so a dir→symlink swap can't make a restore
    write through a symlinked parent: (A) deepest-first, remove every current
    agent write (stripping symlinked parents); (B) shallowest-first, recreate the
    snapshotted file/symlink entries into the now-clean tree. Over-cap files
    (content not held) are best-effort `git checkout`-restored (tracked) — an
    untracked over-cap change is flagged + the run rejected, but left in place (no
    data loss). Compares symlink-safe entry tuples, so create/modify/delete/swap/
    over-cap all count."""
    after = snapshot_outside_workspace(root)
    changed = [rel for rel in set(before) | set(after)
               if before.get(rel) != after.get(rel)]
    overcap = {rel for rel in changed
               if (before.get(rel) or ("",))[0] == "over"}
    normal = [rel for rel in changed if rel not in overcap]
    depth = lambda r: r.count(os.sep)
    for rel in sorted(normal, key=depth, reverse=True):      # Pass A: neutralize
        _remove_current(root, rel)
    for rel in sorted(normal, key=depth):                    # Pass B: restore
        b = before.get(rel)
        if b is not None and b[0] in ("file", "link"):
            _recreate(root, rel, b)
    for rel in sorted(overcap):                              # over-cap: best-effort git
        _strip_symlinked_parents(root, rel)
        _git_root(root, ["checkout", "--", rel])
    return sorted(changed)


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
