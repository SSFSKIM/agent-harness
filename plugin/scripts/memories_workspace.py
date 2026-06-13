#!/usr/bin/env python3
"""Phase 2 memory workspace + input sync (Codex `phase2.rs`/`storage.rs`/
git-baseline port).

A self-contained workspace at `.claude/harness/memories/` (gitignored runtime)
with its OWN nested `.git` used purely as a diff/forgetting baseline — Codex's
`~/.codex/memories/.git` faithfully. The flow this module owns (M4):

  ensure_baseline → select top-N → sync (raw_memories.md + rollout_summaries/,
  prune unselected) → compute diff vs baseline → (the diff IS the dirty check) →
  write phase2_workspace_diff.md.

M5 then spawns the consolidation agent only when dirty, and on success calls
`reset_baseline` (commit the new state as the next baseline). Git here is an
implementation detail of "what changed since the last consolidation" — never a
user repo; commits never leave the machine.

raw_memories.md is rebuilt in STABLE thread-id order so usage-rank reshuffling
(which changes selection, not content) produces no phantom diff churn.
"""
import datetime
import re
import shutil
import subprocess
from pathlib import Path

import harness_lib as hl
import memories_db as mdb

WORKSPACE_DIFF_FILE = "phase2_workspace_diff.md"
RAW_MEMORIES_FILE = "raw_memories.md"
ROLLOUT_SUMMARIES_DIR = "rollout_summaries"
GITIGNORE = WORKSPACE_DIFF_FILE + "\n"     # the prompt artifact never enters git
MAX_RAW_MEMORIES = 256                      # Codex max_raw_memories_for_consolidation
MAX_UNUSED_DAYS = 30                        # Codex max_unused_days (forgetting window)
DIFF_MAX_BYTES = 4_000_000                  # Codex bounds the diff artifact at ~4MB
SLUG_MAX_LEN = 60


def workspace_dir(root):
    """`.claude/harness/memories/` — the dreaming workspace (dir), sibling of the
    `memories.db` file, both under gitignored runtime state."""
    return hl.state_dir(root) / "memories"


def _iso(ts):
    return datetime.datetime.fromtimestamp(
        int(ts), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _rollout_path(root, thread_id):
    return hl.project_transcripts_dir(root) / f"{thread_id}.jsonl"


def summary_stem(thread_id, source_updated_at, rollout_slug):
    """Deterministic, unique, sortable file stem for a rollout's summary —
    adapted from Codex's `<timestamp>-<shorthash>[-<slug>]` (we derive the short
    id from the thread-id hex rather than UUIDv7 bit-extraction; same shape, same
    properties: stable per (thread, source_ts, slug) so diffs don't churn, and
    used identically for the prune keep-set)."""
    ts = datetime.datetime.fromtimestamp(
        int(source_updated_at), datetime.timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    short = (re.sub(r"[^0-9a-fA-F]", "", str(thread_id)).lower()[:8] or "00000000")
    prefix = f"{ts}-{short}"
    if not rollout_slug:
        return prefix
    slug = []
    for ch in str(rollout_slug):
        if len(slug) >= SLUG_MAX_LEN:
            break
        slug.append(ch.lower() if (ch.isascii() and ch.isalnum()) else "_")
    slug = "".join(slug).rstrip("_")
    return f"{prefix}-{slug}" if slug else prefix


# ---- git baseline (the "internal" diff repo) -------------------------------

def _git(wdir, args, check=True):
    return subprocess.run(["git", *args], cwd=str(wdir),
                          capture_output=True, text=True, check=check)


def _remove_diff_file(wdir):
    f = Path(wdir) / WORKSPACE_DIFF_FILE
    if f.exists():
        f.unlink()


def _init_repo(wdir):
    """Configure a fresh, self-contained, hook-free baseline repo."""
    _git(wdir, ["init", "-q"])
    _git(wdir, ["config", "user.email", "dreamer@harness.local"])
    _git(wdir, ["config", "user.name", "harness-dreamer"])
    _git(wdir, ["config", "commit.gpgsign", "false"])
    # neutralize any global core.hooksPath so the nested repo runs no host hooks
    _git(wdir, ["config", "core.hooksPath", "/dev/null"])
    (Path(wdir) / ".gitignore").write_text(GITIGNORE, encoding="utf-8")


def ensure_baseline(wdir):
    """Ensure `wdir` has a usable single-commit git baseline (Codex
    `ensure_git_baseline_repository`). Keeps an existing usable `.git` (HEAD
    resolves); otherwise (re)creates one. Always clears the stale diff artifact
    first so it is never treated as workspace input."""
    wdir = Path(wdir)
    wdir.mkdir(parents=True, exist_ok=True)
    _remove_diff_file(wdir)
    usable = (wdir / ".git").is_dir() and \
        _git(wdir, ["rev-parse", "HEAD"], check=False).returncode == 0
    if usable:
        return
    if (wdir / ".git").exists():
        shutil.rmtree(wdir / ".git")
    _init_repo(wdir)
    _git(wdir, ["add", "-A"])
    _git(wdir, ["commit", "-q", "--no-verify", "--allow-empty", "-m", "baseline"])


def compute_diff(wdir):
    """Changes since the latest baseline (Codex `diff_since_latest_init`). Stages
    everything (so adds/deletes show), removes the stale artifact first, returns
    `(changes, unified_diff)` where changes is `[(status, path)]`. The dirty check
    is simply `bool(changes)` — this, not a DB watermark, gates the agent."""
    wdir = Path(wdir)
    _remove_diff_file(wdir)
    _git(wdir, ["add", "-A"])
    # --no-renames: Codex's diff is strictly path-based (a delete+add is two
    # changes, never a rename) — a forgetting cue must stay a real Delete.
    name_status = _git(wdir, ["diff", "--cached", "--no-renames", "--name-status"]).stdout
    unified = _git(wdir, ["diff", "--cached", "--no-renames"]).stdout
    changes = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            changes.append((parts[0], parts[-1]))
    return changes, unified


def write_diff_file(wdir, changes, unified, max_bytes=DIFF_MAX_BYTES):
    """Render `phase2_workspace_diff.md` — the consolidation agent reads it FIRST
    (Codex `render_workspace_diff_file`): a status list + a bounded unified diff."""
    lines = ["# Memory Workspace Diff", "",
             "Generated before Phase 2 memory consolidation. Read this file first "
             "and do not edit it.", "", "## Status"]
    if not changes:
        lines.append("- none")
    else:
        lines += [f"- {status} {path}" for status, path in changes]
    body = "\n".join(lines) + "\n"
    if changes:
        d = unified
        if len(d.encode("utf-8")) > max_bytes:
            d = d.encode("utf-8")[:max_bytes].decode("utf-8", "ignore") + \
                f"\n[workspace diff truncated at {max_bytes} bytes]\n"
        if not d.endswith("\n"):
            d += "\n"
        body += "\n## Diff\n\n```diff\n" + d + "```\n"
    (Path(wdir) / WORKSPACE_DIFF_FILE).write_text(body, encoding="utf-8")


def discard_workspace_changes(wdir):
    """Roll the workspace back to its last baseline (discard the agent's writes).
    Used when a Phase-2 run fails or a scope escape is detected, so a bad/poisoned
    consolidation leaves no residue. `reset --hard` restores tracked files to the
    baseline commit; `clean -fd` removes agent-created files; the diff artifact
    (gitignored) is removed explicitly."""
    wdir = Path(wdir)
    _git(wdir, ["reset", "--hard", "-q", "HEAD"], check=False)
    _git(wdir, ["clean", "-fdq"], check=False)
    _remove_diff_file(wdir)


def reset_baseline(wdir):
    """Mark the current workspace state as the new baseline (Codex
    `reset_memory_workspace_baseline`): drop the diff artifact, then commit. We
    keep a commit chain rather than Codex's history-drop — the gitignored runtime
    `.git` is disposable and tiny; diffing vs HEAD is identical either way."""
    wdir = Path(wdir)
    _remove_diff_file(wdir)
    _git(wdir, ["add", "-A"])
    _git(wdir, ["commit", "-q", "--no-verify", "--allow-empty", "-m", "baseline"])


# ---- input sync (DB rows → workspace files) --------------------------------

def _write_raw_memories(wdir, root, rows):
    out = ["# Raw Memories", ""]
    if not rows:
        out.append("No raw memories yet.")
        (Path(wdir) / RAW_MEMORIES_FILE).write_text("\n".join(out) + "\n", encoding="utf-8")
        return
    out.append("Merged stage-1 raw memories (stable ascending thread-id order):")
    out.append("")
    for r in rows:
        stem = summary_stem(r["thread_id"], r["source_updated_at"], r["rollout_slug"])
        out += [
            f"## Thread `{r['thread_id']}`",
            f"updated_at: {_iso(r['source_updated_at'])}",
            f"cwd: {root}",
            f"rollout_path: {_rollout_path(root, r['thread_id'])}",
            f"rollout_summary_file: {stem}.md",
            "",
            (r["raw_memory"] or "").strip(),
            "",
        ]
    (Path(wdir) / RAW_MEMORIES_FILE).write_text("\n".join(out) + "\n", encoding="utf-8")


def _sync_rollout_summaries(wdir, root, rows):
    sdir = Path(wdir) / ROLLOUT_SUMMARIES_DIR
    sdir.mkdir(parents=True, exist_ok=True)
    keep = set()
    for r in rows:
        stem = summary_stem(r["thread_id"], r["source_updated_at"], r["rollout_slug"])
        keep.add(stem)
        body = (
            f"thread_id: {r['thread_id']}\n"
            f"updated_at: {_iso(r['source_updated_at'])}\n"
            f"rollout_path: {_rollout_path(root, r['thread_id'])}\n"
            f"cwd: {root}\n\n"
            f"{(r['rollout_summary'] or '').strip()}\n")
        (sdir / f"{stem}.md").write_text(body, encoding="utf-8")
    for f in sdir.glob("*.md"):           # prune dropped rollouts (forgetting cue)
        if f.stem not in keep:
            f.unlink()


def sync_inputs(wdir, root, rows):
    """Materialize the selected stage-1 rows into the workspace: rebuild
    raw_memories.md (stable order) + one rollout_summaries/<stem>.md each, and
    prune summaries no longer selected (a delete = a forgetting cue for Phase 2)."""
    _sync_rollout_summaries(wdir, root, rows)
    _write_raw_memories(wdir, root, rows)


def select_and_sync(conn, root, now, max_n=MAX_RAW_MEMORIES,
                    max_unused_days=MAX_UNUSED_DAYS):
    """The M4 entry M5 calls: ensure baseline → select top-N → sync → diff. Returns
    the selected rows + the diff (`dirty` = whether the consolidation agent should
    run at all)."""
    wdir = workspace_dir(root)
    ensure_baseline(wdir)
    rows = mdb.select_phase2_inputs(conn, max_n, max_unused_days, now)
    sync_inputs(wdir, root, rows)
    changes, unified = compute_diff(wdir)
    if changes:
        write_diff_file(wdir, changes, unified)
    return {"workspace": str(wdir), "rows": rows,
            "selected": [r["thread_id"] for r in rows],
            "changes": changes, "dirty": bool(changes)}
