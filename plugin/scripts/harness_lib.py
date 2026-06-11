"""Shared helpers for all harness scripts.

The ONLY module allowed to resolve paths, environment, and frontmatter
(Providers analog — enforced by lint_structure.py rule S2).
Pure stdlib. Portable: never hardcodes an absolute path.
"""
import datetime
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


def today():
    return datetime.date.today()
