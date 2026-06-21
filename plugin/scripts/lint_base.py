#!/usr/bin/env python3
"""Drift-check for the committed `base/` reference artifact (packaging Slice 6, R6.2).

`base/` is the hand-synced, inspectable strict-base tree — every seed template
rendered at its host destination (`{{COMPONENTS}}` and the `adr` `{{CATEGORY}}`
substituted; `{{PROJECT}}`/`{{TODAY}}` preserved as fill-markers), plus a
base-authored `SETUP.md`, and no `docs/generated/`. This lint keeps the hand-sync
honest: the base must stay in sync with its source — the seed-template set
(`harness_lib.SEEDS`) and the live plugin component table.

Self-host only: `base/` exists only in this repo. A ported host has no `base/`, so
this lint is a no-op there (the base artifact is not part of what travels to a host).
The expected file-set is derived from the SAME `harness_lib.SEEDS`/`render`/
`components_table` that `scaffold.py` uses — one source, so the base cannot silently
diverge from the seeds (ARCHITECTURE invariant 8).

Total over a hostile corpus (RELIABILITY R22): every read degrades to a coded FAIL,
never a traceback — a missing/unreadable seed template or a non-UTF8 base file is a
clean `B#` error, so the `base` gate step goes RED loudly rather than crashing.
"""
import sys
from pathlib import Path

import harness_lib as hl


def _read(path):
    """(text, None) on success; (None, reason) on any read error — so a missing,
    unreadable, or non-UTF8 file becomes a coded FAIL, never an uncaught raise (R22)."""
    try:
        return path.read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as e:
        return None, str(e)


def expected_files(plugin, templates, errors):
    """{dest: expected base content} for every file the base must carry — the
    rendered seeds + the `adr` category index. Rendered with the SAME subs the base
    was built with: `{{COMPONENTS}}` → the live component table, `{{CATEGORY}}` → the
    category for the index; `{{PROJECT}}`/`{{TODAY}}` preserved (not substituted), so
    the check has no calendar/host dependence. A seed template that cannot be read is
    a coded FAIL (B6), and that dest is skipped (not rendered) — never a raise."""
    subs = {"COMPONENTS": hl.components_table(plugin)}
    items = [(t, dest, subs) for t, dest in hl.SEEDS]
    for cat in hl.TOP_INDEXES:
        items.append(("category-index.md", f"docs/{cat}/index.md", {**subs, "CATEGORY": cat}))
    exp = {}
    for template, dest, s in items:
        text, err = _read(templates / template)
        if err is not None:
            errors.append(f"B6 templates/{template}: seed template missing/unreadable "
                          f"({err}). FIX: restore the template that seeds base/{dest}.")
            continue
        exp[dest] = hl.render(text, s)
    return exp


def check_base(root, plugin, errors):
    base = Path(root) / "base"
    templates = plugin / "skills" / "harness-init" / "templates"
    expected = expected_files(plugin, templates, errors)
    # SETUP.md is base-authored (not a seed) — presence only (R6.3).
    if not (base / "SETUP.md").is_file():
        errors.append("B5 base/SETUP.md: missing — the from-scratch bring-to-life guide (R6.3).")
    # The base must NOT ship the generated inventory — regenerated per host (R6.4).
    if (base / "docs" / "generated").exists():
        errors.append("B4 base/docs/generated/: present — the base ships no generated "
                      "inventory (regenerated at adoption). FIX: rm -r base/docs/generated.")
    # Every expected seed file present + byte-equal to its rendered template.
    for dest, content in sorted(expected.items()):
        f = base / dest
        if not f.is_file():
            errors.append(f"B1 base/{dest}: missing — out of sync with the seed set. "
                          f"FIX: re-render the seed template into base/{dest}.")
            continue
        actual, err = _read(f)
        if err is not None:
            errors.append(f"B2 base/{dest}: unreadable ({err}) — FIX: re-render the seed into base/{dest}.")
        elif actual != content:
            errors.append(f"B2 base/{dest}: content drift from its seed template "
                          f"(an edited seed, or a stale component table). "
                          f"FIX: re-render the seed into base/{dest}.")
    # No extra/unexpected files. `allowed` is the structural seed set (independent of
    # whether a template was readable) so a B6 skip never cascades into a false B3.
    allowed = ({dest for _, dest in hl.SEEDS}
               | {f"docs/{c}/index.md" for c in hl.TOP_INDEXES}
               | {"SETUP.md"})
    for f in sorted(base.rglob("*")):
        if f.is_file():
            rel = f.relative_to(base).as_posix()
            if rel not in allowed and not rel.startswith("docs/generated/"):
                errors.append(f"B3 base/{rel}: unexpected file (not a seed dest, the adr "
                              f"index, or SETUP.md). FIX: remove it, or add its seed to "
                              f"harness_lib.SEEDS and re-sync base/.")


def main():
    root = hl.repo_root()
    if not (root / "base").is_dir():
        print("lint_base: SKIP — no base/ (the base artifact is self-host only).")
        return
    errors = []
    check_base(root, hl.plugin_root(), errors)
    for e in errors:
        print(e)
    print(f"lint_base: {'OK' if not errors else str(len(errors)) + ' FAIL'}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
