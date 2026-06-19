"""Merge-gate code checks (merge-preservation-hardening R1 + R3).

Two code-owned, deterministic checks the merger runs *before* it squash-merges, so the
irreversible land is gated by code rather than the land worker's prose judgment:

  - **Preservation tripwire (R1)** — `parse_numstat` / `preservation_delta`: did the PR's
    intended change survive the rebase/conflict-resolution? (the bulk of this module)
  - **Hygiene gate (R3)** — `pr_hygiene` / `classify_checks`: are the PR's CI checks green
    and (configurably) its review threads resolved?

Both surface a `failing`/drop result the merger turns into a `mergeReview` (judgment),
never a silent merge; both fail **closed** (an unreadable diff / `gh` error → withhold).

The preservation tripwire is a deterministic, code-owned check that a PR's intended
change actually survives the
merger's rebase/conflict-resolution before it lands on `main`. It compares two
`--numstat` diffs:

  - INTENDED — the PR's own change, captured *before* the merger rebases it
    (`gh pr diff --numstat <pr>`).
  - ACTUAL   — what the squash would add to `main`, *after* the rebase
    (`git -C <ws> diff --numstat <base>..<branch>`).

A path the PR changed that is **absent** from the actual merge → `dropped`; one whose
added-line count fell by a clear margin → `shrunk`. Either makes the result not-`ok`.

It is a HEURISTIC, not a proof: a legitimate conflict resolution can correctly drop a
hunk (the PR's change was already on `main`). So a trip routes to the Director as a
`mergeReview` (judgment + an approve-and-requeue override), never a silent hard-reject
(spec D3). The conservative thresholds favor low false-positives — a Director look costs
less than a silent overwrite, but a noisy tripwire that cries wolf is ignored.

Pure logic (`parse_numstat`, `preservation_delta`) is unit-tested directly; the only I/O
is `numstat_from_cmd`, which shells a command with **argv** (never a shell string — the
PR ref / branch are worker-supplied) and fails closed (returns None) so the caller
withholds the merge when a diff cannot be read.
"""
from __future__ import annotations

import json
import re
import subprocess

# A PR url like https://github.com/<owner>/<repo>/pull/<number> → the parts the GitHub
# GraphQL reviewThreads query needs (gh pr view --json does NOT expose reviewThreads).
_PR_URL = re.compile(r"github\.com[/:]([^/]+)/([^/]+)/pull/(\d+)")

# Check conclusions/states that mean a completed check FAILED (any → the rollup is failing).
_FAIL_VERDICTS = {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED",
                  "STARTUP_FAILURE"}
# Statuses that mean a check has not finished (any non-failed → the rollup is pending).
_PENDING_STATUS = {"QUEUED", "IN_PROGRESS", "PENDING", "WAITING", "REQUESTED"}

_THREADS_QUERY = (
    "query($owner:String!,$repo:String!,$number:Int!){"
    "repository(owner:$owner,name:$repo){pullRequest(number:$number){"
    "reviewThreads(first:100){nodes{isResolved}}}}}"
)

# A path's added lines must fall to <= this fraction of the intended count AND by at least
# `_MIN_SHRINK` absolute lines to be flagged `shrunk` — conservative so a rebase that
# legitimately trims a few already-present lines does not trip (spec D3 / plan Decision log).
_SHRINK_RATIO = 0.5
_MIN_SHRINK = 3


def parse_numstat(text: str) -> dict[str, tuple[int, int]]:
    """Parse `git diff --numstat` / `gh pr diff --numstat` output → {path: (added, deleted)}.

    Each line is `<added>\\t<deleted>\\t<path>`; a binary file shows `-` for the counts →
    recorded as (0, 0) but still keyed, so its presence/absence is tracked. Renames
    (`old => new` / brace forms) keep the raw path token — a coarse key is fine for a
    presence/added-count heuristic. Blank/malformed lines are skipped."""
    out: dict[str, tuple[int, int]] = {}
    for line in (text or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a_raw, d_raw, path = parts[0], parts[1], "\t".join(parts[2:]).strip()
        if not path:
            continue
        added = 0 if a_raw == "-" else int(a_raw) if a_raw.isdigit() else 0
        deleted = 0 if d_raw == "-" else int(d_raw) if d_raw.isdigit() else 0
        out[path] = (added, deleted)
    return out


def preservation_delta(intended: dict[str, tuple[int, int]],
                       actual: dict[str, tuple[int, int]]) -> dict:
    """Compare INTENDED (pre-rebase PR diff) vs ACTUAL (post-rebase merge diff).

    Returns {"ok": bool, "dropped_paths": [...], "shrunk_paths": [...]}.
      - dropped: a path the PR changed that is entirely absent from the actual merge.
      - shrunk:  a path in both whose added lines fell to <= _SHRINK_RATIO of intended AND
                 by >= _MIN_SHRINK absolute lines (a clear, sizable reduction).
    Both lists sorted for deterministic output / stable test + escalation messages."""
    dropped: list[str] = []
    shrunk: list[str] = []
    for path, (added, deleted) in intended.items():
        act = actual.get(path)
        if act is None:
            if added or deleted:          # the PR touched this file; the merge does not
                dropped.append(path)
            continue
        a_add, _ = act
        if added > 0 and a_add < added \
                and (added - a_add) >= _MIN_SHRINK and a_add <= added * _SHRINK_RATIO:
            shrunk.append(path)
    return {"ok": not dropped and not shrunk,
            "dropped_paths": sorted(dropped), "shrunk_paths": sorted(shrunk)}


def numstat_from_cmd(argv: list[str], *, cwd: str | None = None,
                     run=subprocess.run) -> dict[str, tuple[int, int]] | None:
    """Run `argv` (a list — never a shell string; the PR ref/branch are untrusted input)
    and parse its stdout as numstat. Returns the parsed map, or **None** on any failure
    (non-zero exit, missing tool, exception) — fail-closed, so the caller withholds the
    merge rather than landing on an unreadable diff."""
    try:
        proc = run(argv, cwd=cwd, capture_output=True, text=True)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    return parse_numstat(proc.stdout)


# ── Hygiene gate (R3) ──────────────────────────────────────────────────────────────

def classify_checks(rollup: list | None) -> str:
    """Reduce a `statusCheckRollup` list → "green" | "failing" | "pending".

    Each entry is a CheckRun (has `status`/`conclusion`) or a StatusContext (has `state`).
    Precedence: any failed completed check → "failing"; else any unfinished check →
    "pending"; else "green". An empty/None rollup → "green" (no checks to fail — this repo
    has no required checks, so a PR with none lands on the integration gate alone, R5)."""
    any_pending = False
    for c in rollup or []:
        status = (c.get("status") or "").upper()
        if status in _PENDING_STATUS:
            any_pending = True
            continue
        verdict = (c.get("conclusion") or c.get("state") or "").upper()
        if verdict in _FAIL_VERDICTS:
            return "failing"
        if verdict in ("PENDING", "EXPECTED"):
            any_pending = True
        # SUCCESS / NEUTRAL / SKIPPED (or a completed check with no verdict) → pass
    return "pending" if any_pending else "green"


def _gh_json(argv: list[str], *, run=subprocess.run):
    """Run a `gh` command (argv — never a shell string) and parse stdout as JSON. Returns
    the parsed object, or None on any failure (non-zero, unparseable, exception) — the
    caller fails closed."""
    try:
        proc = run(argv, capture_output=True, text=True)
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except (ValueError, TypeError):
        return None


def unresolved_thread_count(pr: str, *, run=subprocess.run) -> int | None:
    """Count the PR's unresolved GitHub review threads via `gh api graphql` (the native
    signal; `gh pr view --json` does not expose reviewThreads). Returns the count, or None
    when it cannot be determined (unparseable PR url, `gh` error) — caller fails closed.

    Scope note (D4): this is GitHub's native *inline review thread* state. A host whose
    review convention does not use resolvable threads (e.g. issue-comment reviews where a
    reply does not resolve a thread) turns the gate off via `require_resolved_threads`."""
    m = _PR_URL.search(pr or "")
    if not m:
        return None
    owner, repo, number = m.group(1), m.group(2), m.group(3)
    data = _gh_json(["gh", "api", "graphql", "-f", f"query={_THREADS_QUERY}",
                     "-f", f"owner={owner}", "-f", f"repo={repo}", "-F", f"number={number}"],
                    run=run)
    try:
        nodes = data["data"]["repository"]["pullRequest"]["reviewThreads"]["nodes"]
    except (TypeError, KeyError):
        return None
    return sum(1 for n in nodes if not n.get("isResolved", False))


def pr_hygiene(pr: str, *, require_threads: bool, run=subprocess.run) -> str:
    """Tri-state pre-land hygiene verdict for `pr` → "green" | "failing" | "pending".

      - checks: `gh pr view <pr> --json statusCheckRollup` → `classify_checks`. A read
        failure is fail-closed ("failing" — withhold rather than land on an unknown state).
      - threads (only when `require_threads`): "failing" if any unresolved review thread,
        and fail-closed if the count cannot be read.

    "pending" (CI still running) short-circuits before the thread check — there is nothing
    to resolve against an unfinished PR; the merger defers it."""
    rollup = _gh_json(["gh", "pr", "view", pr, "--json", "statusCheckRollup"], run=run)
    if rollup is None:
        return "failing"
    checks = classify_checks(rollup.get("statusCheckRollup"))
    if checks != "green":
        return checks
    if require_threads:
        n = unresolved_thread_count(pr, run=run)
        if n is None or n > 0:
            return "failing"
    return "green"
