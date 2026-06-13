#!/usr/bin/env python3
"""HOST LINT TEMPLATE — copy to `.claude/lints/<invariant>.py` and adapt.

One host-authored lint = one architecture invariant, mechanically enforced on
every commit (the architecture-setup skill wires it via `.harness.json`
lint_cmd, behind the aggregating `.claude/lints/check.py` runner). This file is
the HOST's, not the machine's — the harness ships the shape, the host owns the
rule.

Contract (matches the harness's own lints): pure stdlib; decide from files
only (no network, no untrusted input); print one line per violation as
`FAIL <rule> <path>: <problem> FIX: <imperative instruction>` and exit 1;
exit 0 when clean. The FIX text is the product — write it for an agent that
acts on it verbatim. Scope tightly (allowlist the sanctioned location) so the
lint has no false positives.
"""
import re  # FILL: import only what this invariant needs (ast/json/…) — stdlib
import sys
from pathlib import Path

RULE = "H1"                                  # FILL: short stable id for the rule
ROOT = Path(__file__).resolve().parents[2]   # .claude/lints/<f>.py → repo root
SCAN = ("backend", "frontend/src")           # FILL: dirs the invariant governs
ALLOW = ("main.py",)                         # FILL: the sanctioned exception(s)
PATTERN = re.compile(r"FILL-the-real-pattern")  # FILL: what a violation looks like


def violations():
    out = []
    for sub in SCAN:
        for p in (ROOT / sub).rglob("*.py"):       # FILL: file glob(s) to inspect
            rel = p.relative_to(ROOT).as_posix()
            if any(rel == a or rel.endswith("/" + a) for a in ALLOW):
                continue
            for m in PATTERN.finditer(p.read_text(encoding="utf-8", errors="replace")):
                out.append((rel, m.group(0)))
    return out


def main():
    fails = violations()
    for rel, found in fails:
        print(f"FAIL {RULE} {rel}: <problem with `{found}`>. "   # FILL: real problem
              f"FIX: <imperative fix the agent can apply>.")      # FILL: real fix
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
