"""Shared helpers for all harness scripts.

The ONLY module allowed to resolve paths, environment, and frontmatter
(Providers analog — enforced by lint_structure.py rule S2).
Pure stdlib. Portable: never hardcodes an absolute path.
"""
import datetime
import json
import os
from pathlib import Path

HEADLESS_ENV = "HARNESS_HEADLESS"


def is_headless():
    """True inside any harness-spawned headless claude run (recursion guard)."""
    return os.environ.get(HEADLESS_ENV) == "1"


def headless_env():
    """Env for spawning headless children: inherits + sets the guard."""
    env = dict(os.environ)
    env[HEADLESS_ENV] = "1"
    return env


def project_env(root):
    """Env for running harness scripts against an explicit host repo root."""
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(root)
    return env


def repo_root():
    """Instance repo root. Hooks get CLAUDE_PROJECT_DIR; otherwise walk up."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    cur = Path.cwd().resolve()
    for cand in (cur, *cur.parents):
        if (cand / "AGENTS.md").exists() or (cand / ".git").exists():
            return cand
    return cur


def plugin_root():
    """The plugin directory (parent of scripts/)."""
    return Path(__file__).resolve().parent.parent


def state_dir(root):
    """Gitignored runtime state (queues, locks, seen-sessions)."""
    d = Path(root) / ".claude" / "harness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_frontmatter(path):
    """Parse flat `key: value` YAML frontmatter. dict, or None if absent/broken."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip()
    return None


def iter_md(base):
    base = Path(base)
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.md"))


# Doc trees the harness always governs — never exemptable via .harnessignore,
# so a host can't un-govern (and silently poison) the memory/design tree.
# MANAGED_ROOTS = subdirectories; MANAGED_DOCS = top-level docs/ machine docs
# (the persona grounding + execplan docs that the review gate itself rides on).
MANAGED_ROOTS = ("design-docs", "exec-plans", "generated", "memory",
                 "product-specs", "references")
MANAGED_DOCS = ("PLANS.md", "DESIGN.md", "QUALITY_SCORE.md", "PRODUCT_SENSE.md",
                "RELIABILITY.md", "SECURITY.md")


def exempt_roots(root):
    """Host-declared legacy doc subtrees the content lints skip.

    Reads `<root>/docs/.harnessignore`: docs-relative path prefixes, one per
    line (a trailing `/` is optional — matching is on path-segment boundaries
    either way, so `business` and `business/` both mean the `business/` tree
    and neither touches a sibling `business-plan.md`). `#` comments and blanks
    ignored. Absent/unreadable → () (fresh-host behavior unchanged; fail-open =
    govern everything). The list is a migration backlog — it shrinks as legacy
    docs adopt the convention. Entries naming a MANAGED_ROOT subtree or a
    MANAGED_DOC are dropped: the harness governs its own tree regardless of
    what a host writes here.
    """
    try:
        # errors="replace" is the load-bearing guard against non-UTF8 bytes;
        # except OSError only catches missing-file / permission / is-a-dir.
        lines = (Path(root) / "docs" / ".harnessignore").read_text(
            encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ()
    out = []
    for line in lines:
        s = line.split("#", 1)[0].strip()
        # Normalize so the managed-tree drop-guard and _exempt agree: strip
        # `./`, leading/`//`, and `.` segments. (Without this, `./memory` slips
        # the guard's first-segment test — inert in _exempt, but the two layers
        # should not disagree.) `..` segments are kept (inert) and never escape.
        segs = [seg for seg in s.split("/") if seg and seg != "."]
        norm = "/".join(segs)
        if not norm or segs[0] in MANAGED_ROOTS or norm in MANAGED_DOCS:
            continue
        out.append(norm)
    return tuple(out)


def gate_config(root):
    """Optional per-repo gate config: `<root>/.harness.json`.

    The ONE place a host overrides harness defaults or wires its own checks
    into the deterministic gate WITHOUT editing plugin source — so the rules a
    host enforces are the host's, not ours hardcoded. Keys, all optional:
      - `lint_cmd` / `test_cmd` (str) — host check commands the gate runs as
        steps (a host-authored structural lint; the real test suite).
      - `size_limits` (dict name→int) — merged over D1/D7 line caps.
      - `default_size_limit` (int) — D7 default cap.
      - `stale_days` (int) — D4 staleness window.

    Parse-don't-validate (core-belief #6): any read/parse error, or a non-object
    top level, returns `{}` — fail-open to harness defaults, exactly like
    `exempt_roots`. Consumers type-guard each key they read; a malformed value
    never crashes the gate. The unversioned env vars HARNESS_LINT_CMD /
    HARNESS_TEST_CMD take precedence over this file as an ad-hoc override — but
    this committed file is the persistent form the `.git/hooks/pre-commit` gate
    actually sees (the hook injects no env). It is executable config (Tier 0):
    `lint_cmd`/`test_cmd` run on every commit — see SECURITY.md T9.
    """
    try:
        data = json.loads((Path(root) / ".harness.json").read_text(
            encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def today():
    return datetime.date.today()
