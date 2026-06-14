#!/usr/bin/env python3
"""Phase 2 (docs-router variant): route distilled memories into the docs brain.

The memory-architecture pivot (`docs/design-docs/memory-architecture.md`): instead
of writing a flat MEMORY.md into a sandbox, Phase 2 ROUTES each distilled claim to
its docs home and records provenance in `docs/journal/`. This is the self-hosting
output path; the flat-store sandbox (`dream_phase2.py`) stays as the bare-host
fallback (a host without a docs library).

SECURITY — containment by construction. The router agent is READ-ONLY
(`--allowedTools Read,Glob,LS` — no Write/Edit/Bash) so a transcript injection has
no mechanism to write anything; the agent only EMITS a structured routing plan
(JSON). A deterministic applicator (this module, the "MemoryManager") then applies
the plan, and ONLY append operations onto an ALLOWLIST of docs targets — an
out-of-allowlist target is refused and demoted to a journal `[held]` note. Inputs
are DATA (T1/T7, stated in the prompt); content is re-redacted before it is
written (T4 defense in depth).
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import dream_phase1 as p1
import harness_lib as hl
import memories_db as mdb

DEFAULT_MODEL = "sonnet"                # Codex phase 2 = larger/stronger model
ROUTER_TIMEOUT = 1200
ROUTER_LEASE = 1800                     # > timeout: no heartbeat needed at our scale
MAX_PLAN_OPS = 64
MAX_SELECT = 256                        # Codex max_raw_memories_for_consolidation
MAX_UNUSED_DAYS = 30                    # Codex max_unused_days

JOURNAL_DIR = "docs/journal"            # the residual ledger (episodic + provenance)
TRACKER = "docs/exec-plans/tech-debt-tracker.md"
DESIGN_DIR = "docs/design-docs"
OP_KINDS = ("tracker_row", "design_decision", "design_openq", "journal")


# ---- prompt ----------------------------------------------------------------

def load_templates():
    d = hl.plugin_root() / "skills" / "dream" / "templates"
    return (d / "router_system.md").read_text(encoding="utf-8"), \
           (d / "router_input.md").read_text(encoding="utf-8")


def _rows_block(rows):
    """Render the selected stage-1 rows as one DATA block for the prompt."""
    parts = []
    for r in rows:
        parts.append(
            f"### Rollout `{r['thread_id']}`\n"
            f"summary: {(r['rollout_summary'] or '').strip()}\n\n"
            f"{(r['raw_memory'] or '').strip()}")
    return "\n\n---\n\n".join(parts)


def render_router_prompt(system_tmpl, input_tmpl, rows):
    """System (raw) + input (.format-substituted). Only the input template is
    formatted; the rows block is inserted as a value, so its braces are not
    re-scanned and can't break the framing (same guarantee as Phase 1)."""
    filled = input_tmpl.format(raw_memories=_rows_block(rows))
    return system_tmpl + "\n\n" + filled


def spawn_router(prompt, model, cwd, timeout=ROUTER_TIMEOUT):
    """Spawn the READ-ONLY router agent (Read/Glob/LS only, cwd = repo root so it
    can inspect the docs tree for placement + dedupe, prompt via stdin). It writes
    NOTHING — it returns a routing plan as stdout JSON. Raises on nonzero/timeout."""
    proc = subprocess.run(
        ["claude", "-p", "--model", model, "--allowedTools", "Read,Glob,LS"],
        input=prompt, capture_output=True, text=True,
        cwd=str(cwd), env=hl.headless_env(), timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p exit {proc.returncode}: {proc.stderr[:300]}")
    return proc.stdout


def parse_routing_plan(text):
    """Extract the outermost JSON object and return its `operations` list (validated
    kinds, capped). Raises ValueError on empty/non-object/no-operations output."""
    if not text or not text.strip():
        raise ValueError("empty router output")
    s = text.strip()
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in router output")
    obj = json.loads(s[start:end + 1])
    if not isinstance(obj, dict) or not isinstance(obj.get("operations"), list):
        raise ValueError("router output lacks an `operations` list")
    # Keep every dict op — an unknown/typo'd `kind` is journaled (held), never
    # silently dropped (else a model typo consumes a memory with no provenance).
    ops = [o for o in obj["operations"] if isinstance(o, dict)]
    return ops[:MAX_PLAN_OPS]


# ---- deterministic applicator (the MemoryManager) --------------------------

def _date(now):
    return datetime.datetime.fromtimestamp(
        int(now), datetime.timezone.utc).strftime("%Y-%m-%d")


def _month(now):
    return datetime.datetime.fromtimestamp(
        int(now), datetime.timezone.utc).strftime("%Y-%m")


def _iso(now):
    return datetime.datetime.fromtimestamp(
        int(now), datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _oneline(s, cap=400):
    """Collapse to a single safe line: redact secrets, squash whitespace, cap."""
    s = p1.redact_secrets(str(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:cap]


def _cell(s, cap=400):
    return _oneline(s, cap).replace("|", "/")     # never break a markdown table


def _short(s, cap=70):
    return _oneline(s, cap)


def _read(path):
    p = Path(path)
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _within_repo_no_symlink(root, rel):
    """The write guard. Return `root/rel` iff NO path component (root → target) is
    a symlink AND the target resolves inside the repo — so a symlinked allowlist
    root or file can't redirect a deterministic write outside its intended place.
    Else None. (Matches the sandbox path's symlink rigor — the applicator is the
    only writer, so this is where "containment by construction" actually holds.)"""
    root = Path(root)
    cur = root
    for part in Path(rel).parts:
        cur = cur / part
        if cur.is_symlink():
            return None
    target = root / rel
    try:
        if not target.resolve().is_relative_to(root.resolve()):
            return None
    except (OSError, ValueError):
        return None
    return target


def _safe_design_target(root, target):
    """A design-doc append target must be an EXISTING `.md` directly under
    docs/design-docs/ by LITERAL path (no symlink in its ancestry, resolves inside
    the repo). Returns the path or None."""
    if not target:
        return None
    rel = os.path.normpath(target)
    if os.path.dirname(rel) != DESIGN_DIR or not rel.endswith(".md"):
        return None
    p = _within_repo_no_symlink(root, rel)
    return p if (p is not None and p.is_file()) else None


def _append_under_heading(path, heading, line):
    """Insert `line` at the end of the `heading` section (before the next `## ` or
    EOF); create the heading at EOF if absent. Dedupes on the line text. Returns
    True if it wrote."""
    text = _read(path)
    if line.strip() and line.strip() in text:
        return False
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.strip() == heading), None)
    if idx is None:
        sep = "" if text.endswith("\n") or not text else "\n"
        Path(path).write_text(text + sep + f"\n{heading}\n\n{line}\n",
                              encoding="utf-8")
        return True
    end = len(lines)
    for j in range(idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    while end > idx + 1 and not lines[end - 1].strip():
        end -= 1
    lines.insert(end, line)
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


def _append_tracker_row(root, desc, severity, source, now):
    path = _within_repo_no_symlink(root, TRACKER)
    if path is None or not path.is_file():
        return False
    sev = severity if severity in ("Minor", "Major", "Critical") else "Minor"
    row = f"| {_cell(desc)} | {sev} | {_date(now)} | {_cell(source, 60)} | open |"
    text = _read(path)
    if row in text:
        return False
    sep = "" if text.endswith("\n") or not text else "\n"
    Path(path).write_text(text + sep + row + "\n", encoding="utf-8")
    return True


def journal_path(root, now):
    return Path(root) / JOURNAL_DIR / f"{_month(now)}.md"


def _ensure_journal(root, now):
    """The month file, guarded against a symlinked `docs/journal` redirect — None
    if the journal path is unsafe (skip journaling rather than write through)."""
    safe = _within_repo_no_symlink(root, f"{JOURNAL_DIR}/{_month(now)}.md")
    if safe is None:
        return None
    safe.parent.mkdir(parents=True, exist_ok=True)
    if not safe.exists():
        safe.write_text(
            f"---\nstatus: stable\nlast_verified: {_date(now)}\nowner: dreamer\n---\n"
            f"# Journal {_month(now)}\n\n"
            "Append-only episodic record — dream-run provenance + residual memory "
            "(what the docs tree cannot hold). Newest at the bottom.\n",
            encoding="utf-8")
    return safe


def append_journal_block(root, now, sessions, lines):
    """Append one dated run-block listing every routed/held claim this run.
    Returns False (no write) if the journal path is unsafe."""
    p = _ensure_journal(root, now)
    if p is None:
        return False
    block = [f"## {_iso(now)} — dream run (sessions: {', '.join(sessions) or 'none'})"]
    block += [f"- {l}" for l in lines]
    text = p.read_text(encoding="utf-8")
    sep = "" if text.endswith("\n") else "\n"
    p.write_text(text + sep + "\n" + "\n".join(block) + "\n", encoding="utf-8")
    return True


def apply_plan(root, ops, rows, now):
    """Apply the routing plan deterministically: append-only onto the allowlist,
    then write one journal provenance block. Out-of-allowlist or malformed ops are
    demoted to journal `[held]` notes (never an out-of-scope write)."""
    sessions = [str(r["thread_id"])[:8] for r in rows]
    jlines = []
    applied = {k: 0 for k in OP_KINDS}
    applied["rejected"] = 0
    for op in ops:
        kind = op.get("kind")
        if kind == "tracker_row":
            wrote = _append_tracker_row(root, op.get("desc", ""),
                                        op.get("severity"), op.get("source", "dream"), now)
            applied["tracker_row"] += int(wrote)
            jlines.append(f"[routed] debt \"{_short(op.get('desc'))}\" -> {TRACKER}")
        elif kind in ("design_decision", "design_openq"):
            tgt = _safe_design_target(root, op.get("target", ""))
            if tgt is None:
                applied["rejected"] += 1
                jlines.append(f"[held] {kind} (bad target {op.get('target')!r}) "
                              f"\"{_short(op.get('decision') or op.get('question'))}\"")
                continue
            if kind == "design_decision":
                line = f"- {_date(now)}: {_oneline(op.get('decision'))} — {_oneline(op.get('why'))}"
                wrote = _append_under_heading(tgt, "## Decision log", line)
                applied["design_decision"] += int(wrote)
                jlines.append(f"[routed] decision \"{_short(op.get('decision'))}\" -> {op.get('target')}")
            else:
                wrote = _append_under_heading(tgt, "## Open decisions",
                                              f"- {_oneline(op.get('question'))}")
                applied["design_openq"] += int(wrote)
                jlines.append(f"[routed] open-q \"{_short(op.get('question'))}\" -> {op.get('target')}")
        else:  # journal (held): the conservative default AND any unknown/typo'd kind
            applied["journal"] += 1
            raw = (op.get("text") or op.get("decision") or op.get("desc")
                   or json.dumps(op, ensure_ascii=False))
            text = re.sub(r"^\[(?:held|routed)\]\s*", "", _oneline(raw),
                          flags=re.IGNORECASE)
            jlines.append(f"[held] {text}")
    if jlines:
        append_journal_block(root, now, sessions, jlines)
    return {"applied": applied, "journal_lines": len(jlines)}


# ---- orchestration ---------------------------------------------------------

def consolidate(conn, root, now, model=DEFAULT_MODEL, spawn=spawn_router,
                worker_id=None, lease_seconds=ROUTER_LEASE):
    """Claim the global lock → select top-N → spawn the read-only router → apply the
    plan into docs + journal → mark selected. `spawn` is injectable for tests."""
    worker_id = worker_id or f"dream-{os.getpid()}"
    token = mdb.claim_phase2(conn, worker_id, lease_seconds, now)
    if token is None:
        return {"status": "skipped"}            # running / cooldown / backoff
    try:
        rows = mdb.select_phase2_inputs(conn, MAX_SELECT, MAX_UNUSED_DAYS, now)
        if not rows:
            mdb.finish_phase2(conn, token, now, ok=True)
            return {"status": "empty", "selected": []}
        prompt = render_router_prompt(*load_templates(), rows)
        out = spawn(prompt, model, cwd=root)
        ops = parse_routing_plan(out)
        summary = apply_plan(root, ops, rows, now)
        mdb.mark_phase2_selected(
            conn, [(r["thread_id"], r["source_updated_at"]) for r in rows])
        mdb.finish_phase2(conn, token, now, ok=True)
        return {"status": "routed", "selected": [r["thread_id"] for r in rows],
                **summary}
    except Exception as exc:  # noqa: BLE001 — mark failed (backoff), no docs written
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
