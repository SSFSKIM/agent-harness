"""Merge-preservation tripwire (merge-preservation-hardening R1).

A deterministic, code-owned check that a PR's intended change actually survives the
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

import subprocess

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
