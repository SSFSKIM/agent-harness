#!/usr/bin/env python3
"""Structural lints: layer law, portability, hook wiring discipline.

Mechanically enforces ARCHITECTURE.md. Exit 0 = green, 1 = FAIL(s).
"""
import ast
import json
import sys

import harness_lib as hl

ALLOWED_IMPORTS = {
    "argparse", "ast", "datetime", "difflib", "errno", "hashlib", "json",
    "os", "pathlib", "re", "shlex", "shutil", "sqlite3", "subprocess", "sys",
    "tempfile", "textwrap", "time", "unittest", "harness_lib",
    "imprint_guard", "memories_db", "dream_discover",
}
ALLOWED_EVENTS = {"SessionStart", "UserPromptSubmit", "PreCompact", "SessionEnd",
                  "PreToolUse", "PostToolUse", "Stop", "SubagentStop", "Notification"}
PATH_TOKENS = ("os.getcwd(", "Path.cwd(", "CLAUDE_PROJECT_DIR")
ABS_TOKENS = ("/Users/", "/home/")


def _fail(errors, rule, path, problem, fix):
    errors.append(f"FAIL {rule} {path}: {problem} FIX: {fix}")


def check_imports(plugin, errors):
    for p in sorted((plugin / "scripts").glob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module.split(".")[0]]
            for m in mods:
                if m not in ALLOWED_IMPORTS:
                    _fail(errors, "S1", p.name, f"imports `{m}` (not in allowlist).",
                          "Scripts are pure stdlib: drop the dependency or reimplement the helper (internalization rule).")


def check_path_discipline(plugin, errors):
    for p in sorted((plugin / "scripts").glob("*.py")):
        if p.name in ("harness_lib.py", "lint_structure.py"):
            continue
        text = p.read_text(encoding="utf-8")
        for tok in PATH_TOKENS:
            if tok in text:
                _fail(errors, "S2", p.name, f"resolves paths directly (`{tok}`).",
                      "Use harness_lib.repo_root()/state_dir() — harness_lib is the only cross-cutting module.")


def check_no_abs_paths(plugin, errors):
    for p in sorted(plugin.rglob("*")):
        if p.suffix not in (".py", ".json", ".md", ".txt") or not p.is_file():
            continue
        if p.name == "lint_structure.py":  # defines ABS_TOKENS itself
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for tok in ABS_TOKENS:
            if tok in text:
                _fail(errors, "S3", p.relative_to(plugin).as_posix(),
                      f"contains absolute path token `{tok}`.",
                      "plugin/ must stay portable: derive paths via harness_lib or ${CLAUDE_PLUGIN_ROOT}.")


def check_hooks(plugin, errors):
    hooks = plugin / "hooks" / "hooks.json"
    if not hooks.exists():
        return
    try:
        cfg = json.loads(hooks.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _fail(errors, "S4", "hooks/hooks.json", f"invalid JSON ({e}).", "Fix the JSON syntax.")
        return
    for event, entries in cfg.get("hooks", {}).items():
        if event not in ALLOWED_EVENTS:
            _fail(errors, "S4", "hooks/hooks.json", f"unknown event `{event}`.",
                  "If docs/references/claude-code-hooks-llms.txt confirms the event, add it to ALLOWED_EVENTS in lint_structure.py; otherwise fix the event name.")
        for entry in entries:
            for h in entry.get("hooks", []):
                cmd = h.get("command", "")
                if "${CLAUDE_PLUGIN_ROOT}" not in cmd:
                    _fail(errors, "S4", "hooks/hooks.json",
                          f"command for {event} lacks ${{CLAUDE_PLUGIN_ROOT}}.",
                          "Reference scripts as \"${CLAUDE_PLUGIN_ROOT}/scripts/<name>.py\" for portability.")
                else:
                    name = cmd.split("${CLAUDE_PLUGIN_ROOT}/", 1)[1].split('"')[0].split(" ")[0]
                    if not (plugin / name).exists():
                        _fail(errors, "S4", "hooks/hooks.json",
                              f"{event} references missing file `{name}`.",
                              "Create the script or fix the path.")


def check_agents(plugin, errors):
    for p in sorted((plugin / "agents").glob("*.md")):
        fm = hl.read_frontmatter(p)
        if not fm or "name" not in fm or "description" not in fm:
            _fail(errors, "S5", p.name, "frontmatter must define name and description.",
                  "Add `name:` and `description:` to the agent frontmatter.")
            continue
        if p.stem.startswith("review-"):
            body = p.read_text(encoding="utf-8")
            if "docs/" not in body and "ARCHITECTURE.md" not in body:
                _fail(errors, "S5", p.name, "review persona has no grounding document.",
                      "Reference the persona's grounding doc (e.g. docs/SECURITY.md) — persona↔doc 1:1 is the feedback mechanism.")


def check_skills(plugin, errors):
    for d in sorted((plugin / "skills").iterdir()):
        if not d.is_dir():
            continue
        md = d / "SKILL.md"
        if not md.exists():
            _fail(errors, "S6", f"skills/{d.name}/", "missing SKILL.md.",
                  "Every skill directory needs SKILL.md with name/description frontmatter.")
            continue
        fm = hl.read_frontmatter(md)
        if not fm or "name" not in fm or "description" not in fm:
            _fail(errors, "S6", f"skills/{d.name}/SKILL.md",
                  "frontmatter must define name and description.",
                  "Add `name:` and `description:` frontmatter.")


def check_self_host_paths(plugin, errors):
    for p in sorted(plugin.rglob("*.md")):
        if "plugin/scripts/" in p.read_text(encoding="utf-8"):
            _fail(errors, "S7", p.relative_to(plugin).as_posix(),
                  "assumes the self-host layout (`plugin/scripts/` literal).",
                  "Plugin markdown travels to hosts where plugin/ is not in-repo: point to the gate command recorded in docs/design-docs/agent-harness.md instead.")


def main():
    plugin = hl.plugin_root()
    errors = []
    check_imports(plugin, errors)
    check_path_discipline(plugin, errors)
    check_no_abs_paths(plugin, errors)
    check_hooks(plugin, errors)
    check_agents(plugin, errors)
    check_skills(plugin, errors)
    check_self_host_paths(plugin, errors)
    for e in errors:
        print(e)
    print(f"lint_structure: {'OK' if not errors else str(len(errors)) + ' FAIL'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
