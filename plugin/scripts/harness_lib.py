"""Shared helpers for all harness scripts.

The ONLY module allowed to resolve paths, environment, and frontmatter
(Providers analog — enforced by lint_structure.py rule S2).
Pure stdlib. Portable: never hardcodes an absolute path.
"""
import datetime
import json
import os
import re
import shlex
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


def is_self_host(root, plugin=None):
    """True when the plugin machine lives inside the checked repo.

    Self-host is the reference implementation: it may keep stricter internal
    governance than a ported host whose plugin is loaded from elsewhere.
    """
    base = Path(root).resolve()
    cand = Path(plugin).resolve() if plugin else plugin_root().resolve()
    try:
        cand.relative_to(base)
        return True
    except ValueError:
        return False


def state_dir(root):
    """Gitignored runtime state (queues, locks, seen-sessions)."""
    d = Path(root) / ".claude" / "harness"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fm_clean_item(s):
    """Strip whitespace and one layer of matching quotes from a list item."""
    s = s.strip()
    if len(s) >= 2 and s[0] in "\"'" and s[-1] == s[0]:
        s = s[1:-1]
    return s


def _fm_flow_list(val):
    """Parse a YAML flow list `[a, b, c]` into list[str]; `[]` -> []."""
    inner = val[1:-1].strip()
    if not inner:
        return []
    return [_fm_clean_item(x) for x in inner.split(",")]


def read_frontmatter(path):
    """Parse flat `key: value` frontmatter.

    Values are `str`, except `list[str]` when the source uses a YAML list — flow
    form `key: [a, b]` or block form (`key:` then `- a` lines, indented or not).
    Scalar lines are byte-for-byte the prior behavior. dict, or None if
    frontmatter is absent/broken.
    """
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    pending = None  # empty-value key a following `- item` line may turn into a list
    for line in lines[1:]:
        if line.strip() == "---":
            return fm
        stripped = line.strip()
        if pending is not None and stripped.startswith("- "):
            if not isinstance(fm.get(pending), list):
                fm[pending] = []  # promote the empty-string seed to a list
            fm[pending].append(_fm_clean_item(stripped[2:]))
            continue
        pending = None
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val.startswith("[") and val.endswith("]"):
                fm[key] = _fm_flow_list(val)
            else:
                fm[key] = val
                if val == "":
                    pending = key  # block list if `- ` lines follow; else stays ""
    return None


def iter_md(base):
    base = Path(base)
    if not base.exists():
        return []
    return sorted(p for p in base.rglob("*.md"))


# The ONE definition of a knowledge link: a markdown link whose target is a
# `.md` page (optionally with a `#fragment`). Consumed by lint_docs D5 AND by
# nav.py's graph — keeping them on one regex stops the gate and the navigator
# from disagreeing about what an edge is (core-belief 5).
LINK = re.compile(r"\]\(([^)#\s]+\.md)(?:#[^)\s]*)?\)")


def links_in(text):
    """Repo-relative `.md` link targets appearing in `text`, in document order."""
    return [m.group(1) for m in LINK.finditer(text)]


# Doc trees the harness always governs — never exemptable via .harnessignore,
# so a host can't un-govern (and silently poison) the adr/design/product tree.
# MANAGED_ROOTS = subdirectories; MANAGED_DOCS = top-level docs/ machine docs
# (the persona grounding + execplan docs that the review gate itself rides on).
MANAGED_ROOTS = ("adr", "design-docs", "exec-plans", "generated",
                 "product-specs")
# docs/ subtrees that carry no governed frontmatter — skipped by content lints
# AND by nav's catalog scope. One definition both consume (core-belief 5);
# consumers may append their own extras (e.g. host .harnessignore roots).
DOC_EXEMPT = ("generated/", "superpowers/")
MANAGED_DOCS = ("PLANS.md", "DESIGN.md", "KNOWLEDGE_FORMAT.md",
                "QUALITY_SCORE.md", "PRODUCT_SENSE.md",
                "RELIABILITY.md", "SECURITY.md")

# -- seed-template layout (the harness-init strict base) ----------------------
# The single source of truth for WHICH templates seed WHERE. Both scaffold.py
# (writes a host) and lint_base.py (checks the committed base/ artifact) read
# this — one mapping, no second copy (ARCHITECTURE invariant 8: shared helpers
# live in a core module, not private-imported from a sibling).
SEEDS = (  # (template under skills/harness-init/templates/, destination rel. to host root)
    ("agents-md.md", "AGENTS.md"),
    ("claude-md.md", "CLAUDE.md"),
    ("harness-json.json", ".harness.json"),  # marks a harness host (tidy_stop sentinel); {} = all defaults
    ("charter.md", "docs/CHARTER.md"),  # top-level intent — authored FILL seed (not a MACHINE_DOC)
    ("agent-harness.md", "docs/design-docs/agent-harness.md"),
    ("core-beliefs.md", "docs/design-docs/core-beliefs.md"),
    ("design-docs-index.md", "docs/design-docs/index.md"),
    ("product-specs-index.md", "docs/product-specs/index.md"),  # guided: phase/parent + derived roadmap
    ("references-index.md", "docs/references/index.md"),  # guided: why references exist (llms.txt convention)
    ("exec-plan-active-index.md", "docs/exec-plans/active/index.md"),  # lifecycle guide (not a listing)
    ("exec-plan-completed-index.md", "docs/exec-plans/completed/index.md"),  # lifecycle guide (not a listing)
    ("reliability.md", "docs/RELIABILITY.md"),
    ("security.md", "docs/SECURITY.md"),
    ("logs.md", "docs/logs.md"),  # on-demand milestone log (replaces the retired memory bootloader/progress)
    ("tech-debt-tracker.md", "docs/exec-plans/tech-debt-tracker.md"),
    ("harnessignore.txt", "docs/.harnessignore"),  # strict-mode migration backlog
    # docs the machine reads (lint D10) — gate/personas break without them:
    ("plans-md.md", "docs/PLANS.md"),
    ("design-md.md", "docs/DESIGN.md"),
    ("knowledge-format.md", "docs/KNOWLEDGE_FORMAT.md"),  # the format contract a host authors docs against
    ("architecture-md.md", "ARCHITECTURE.md"),
    ("quality-score.md", "docs/QUALITY_SCORE.md"),
    ("product-sense.md", "docs/PRODUCT_SENSE.md"),
    ("principles.md", "docs/PRINCIPLES.md"),  # the human's externalized decision-taste (central Director reads it at a fork)
)
# Categories whose docs/<cat>/index.md is seeded from the generic category-index.md
# template (via {{CATEGORY}}); product-specs + references ship dedicated guided indexes.
TOP_INDEXES = ("adr",)


def render(text, subs):
    """Substitute `{{KEY}}` markers. Only keys present in `subs` are replaced —
    a marker with no sub (e.g. `{{PROJECT}}` when seeding the base) is preserved."""
    for key, val in subs.items():
        text = text.replace("{{" + key + "}}", val)
    return text


def components_table(plugin):
    """The skill+agent inventory table that fills the `{{COMPONENTS}}` marker —
    one `| type | name | description |` row per plugin component (frontmatter
    descriptions, truncated). The base's machine-index; its drift is what
    lint_base catches when a component is added/removed."""
    rows = []
    for md in sorted((plugin / "skills").glob("*/SKILL.md")):
        fm = read_frontmatter(md) or {}
        rows.append(f"| skill | `{md.parent.name}` | {fm.get('description', '')[:90]} |")
    for md in sorted((plugin / "agents").glob("*.md")):
        fm = read_frontmatter(md) or {}
        rows.append(f"| agent | `{md.stem}` | {fm.get('description', '')[:90]} |")
    return "\n".join(rows)


def exempt_roots(root):
    """Host-declared strict-mode legacy doc subtrees content lints skip.

    Reads `<root>/docs/.harnessignore`: docs-relative path prefixes, one per
    line (a trailing `/` is optional — matching is on path-segment boundaries
    either way, so `business` and `business/` both mean the `business/` tree
    and neither touches a sibling `business-plan.md`). `#` comments and blanks
    ignored. Absent/unreadable → (). The list is a migration backlog for hosts
    that opt into `doc_governance: strict`; relaxed hosts usually do not need
    it because additional project-specific docs are host-owned by default.
    Entries naming a MANAGED_ROOT subtree or a MANAGED_DOC are dropped: the
    harness governs its own tree regardless of what a host writes here.
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


def is_exempt(rel, prefixes):
    """True if docs-relative posix `rel` is under (or equals) any of `prefixes`.

    Matched on path-segment boundaries (a trailing `/` on a prefix is optional):
    `business` matches the `business/` tree and the file `business`, but never a
    sibling `business-plan.md`. The one definition shared by lint_docs (content
    lints) and nav.py (catalog scope) — see core-belief 5.
    """
    return any(rel == x or rel.startswith(x.rstrip("/") + "/") for x in prefixes)


def gate_config(root):
    """Optional per-repo gate config: `<root>/.harness.json`.

    The ONE place a host overrides harness defaults or wires its own checks
    into the deterministic gate WITHOUT editing plugin source — so the rules a
    host enforces are the host's, not ours hardcoded. Keys, all optional:
      - `lint_cmd` / `test_cmd` (str) — host check commands the gate runs as
        steps (a host-authored structural lint; the real test suite).
      - `stale_days` (int) — D4 staleness window.
      - `doc_governance` ("strict") / `managed_doc_roots` (list[str]) —
        opt host-owned docs into blocking docs governance.
      - `component_inventory` / `component_coverage` ("strict") — make plugin
        component inventory/coverage blocking for external-plugin hosts.

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
        # strict UTF-8: a non-UTF8 byte must fail open to {}, not be silently
        # repaired into executable config (review-reliability).
        raw = (Path(root) / ".harness.json").read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def gate_command(cfg, key, env_name):
    """Resolve a host gate-step command to an argv list, or None if unset.

    The ONE place command/env/config for a gate step is resolved (kept here in
    the cross-cutting resolver, not in check.py — ARCHITECTURE layer law). The
    unversioned env var (ad-hoc) wins over the versioned `.harness.json` value.
    Raises ValueError if a command IS set but does not shell-parse — the caller
    fails the gate rather than silently skipping enforcement the host asked for
    (a present-but-broken wire must be loud; only an ABSENT command is a no-op).
    The argv list runs without a shell, so there is no shell-injection path.
    """
    val = os.environ.get(env_name) or cfg.get(key)
    if not (isinstance(val, str) and val.strip()):
        return None
    return shlex.split(val)  # ValueError (unbalanced quote) propagates to caller


def today():
    return datetime.date.today()


STALE_DAYS = 30  # default staleness window in days; a host may override it


def stale_window(cfg):
    """Effective staleness window from a gate config: the `stale_days` override
    when it is a real int (bool excluded), else the STALE_DAYS default. The one
    window resolver shared by the gate and nav so `nav stale` agrees with D4."""
    v = cfg.get("stale_days")
    return v if isinstance(v, int) and not isinstance(v, bool) else STALE_DAYS


def is_stale(last_verified, stale_days, status):
    """The ONE definition of staleness (lint D4 + nav `stale`).

    Parses `last_verified` first, so a bad or non-scalar date (e.g. a YAML
    list, which `read_frontmatter` returns as `list`) raises ValueError /
    TypeError — the caller owns the reporting UX (lint → D4 FAIL with its
    message + list-date guard; nav → skip the page). A well-formed date with
    `status` in {archived, completed} is never stale. Otherwise stale iff
    `today - last_verified > stale_days`.
    """
    d = datetime.date.fromisoformat(last_verified)  # raises on bad/non-scalar
    if status in ("archived", "completed"):
        return False
    return (today() - d).days > stale_days
