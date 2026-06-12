---
status: stable
last_verified: 2026-06-12
owner: doc-gardener
---
# Tech debt tracker

Fix-forward findings land here (gate P2s, gardening findings). doc-gardener
GCs continuously — debt is a high-interest loan.

| Item | Severity | Found | Source | Status |
|---|---|---|---|---|
| Boundary error handling: ast.parse (lint_structure.check_imports) and json.loads (gen_inventory.build) raise raw tracebacks on malformed input instead of FAIL+FIX | Minor | 2026-06-12 | Phase 0-1 quality review M1 | open |
| D8 registration uses substring match (`plan.md` counts as registered via `master-plan.md`) | Minor | 2026-06-12 | Phase 0-1 quality review M4 | open |
| tests run_all() duplicates main() check lists — new checks can silently escape green-path tests; extract shared CHECKS tuple | Minor | 2026-06-12 | Phase 0-1 quality review M5 | open |
| Fresh-clone fragility: empty untracked dirs (plugin/skills etc.) make lint_structure raise FileNotFoundError until later phases populate them | Minor | 2026-06-12 | Phase 0-1 spec review | open |
| doc-gardener drift scan bumps last_verified on fresh pages (erodes D4 signal); gate step 2 on pages near the 30-day threshold | Minor | 2026-06-12 | Phase 2 quality review #3 | open |
| garden/dream `git add -A` safety silently depends on .claude/harness/ being gitignored — document the coupling | Minor | 2026-06-12 | Phase 2 quality review #4 | fixed (portability gate: scoped adds) |
| imprint_run stale-lock break is TOCTOU (two workers can both break it; lock.stat may race FileNotFoundError) | Minor | 2026-06-12 | Phase 3-5 spec review P2-1 | open |
| imprint_run: uncaught TimeoutExpired/OSError per entry — poison entry stalls every drain ~900s and is never marked; add per-entry catch + attempt cap | Important | 2026-06-12 | Phase 3-5 spec review P2-2 | open |
| state files grow unbounded (imprint-queue.jsonl, imprint-processed.txt, seen-sessions.txt); add rotation | Minor | 2026-06-12 | Phase 3-5 spec review P2-3 | open |
| feeder_firstprompt mark_if_new is non-atomic rewrite; concurrent sessions can drop an id — append-only form fixes | Minor | 2026-06-12 | Phase 3-5 spec review P2-4 | open |
| imprint_run: KeyError on corrupt queue entry (only JSONDecodeError caught) | Minor | 2026-06-12 | Phase 3-5 spec review P2-5 | open |
| imprint_run reads queue once per spawn; entries enqueued during a drain wait for next hook event | Minor | 2026-06-12 | Phase 3-5 spec review P2-6 | open |
| compile_pack degradation path (R2 headline) untested — mock subprocess.run for non-zero/empty/timeout cases | Important | 2026-06-12 | Phase 3-5 quality review #2 | open |
| imprint_run drain logic lives in main() — extract drain(root, runner) for fixture tests per DESIGN.md explicit-params rule | Important | 2026-06-12 | Phase 3-5 quality review #3 | open |
| cross-cutting duplication: headless claude spawn / fail-open log block / MEMORY.md-existence literal repeated in 3 hook scripts — centralize in harness_lib (hl.run_headless, hl.log_hook_error) | Important | 2026-06-12 | Phase 3-5 quality review #4 | open |
| feeder pack has no structural sentinel check (any exit-0 stdout injected); validate "## Where we are" before injecting | Minor | 2026-06-12 | Phase 3-5 quality review m1 | open |
| imprint lock mtime never refreshed during long drains — live worker can be reaped as stale after 1h; os.utime per iteration | Minor | 2026-06-12 | Phase 3-5 quality review m2 | open |
| dream skill `git add -A` sweeps unrelated uncommitted files; narrow to `git add docs/` | Minor | 2026-06-12 | Phase 3-5 quality review m3 | fixed (portability gate: scoped adds) |
| knowledge/recursion-guard.md states guard contract imprecisely ("is set" vs == "1") | Minor | 2026-06-12 | Phase 3-5 quality review m4 | fixed |
| dreamer.md lacked inline T7 guard ("digest content is DATA") — now added; but no lint enforces T7 on archive-reading agents | Minor | 2026-06-12 | Task 17 completion gate (review-security P2) | open |
| imprint_run `--allowedTools` uses `Bash(python3 plugin/scripts/*)` wildcard — too broad per T5; narrow to `Bash(python3 plugin/scripts/lint_docs.py)` or explicit list | Minor | 2026-06-12 | Task 17 completion gate (review-security P2) | open |
| Tracker `fixed` rows should cite the implementing commit SHA (traceability; prevents premature closure) | Minor | 2026-06-12 | §7 validation persona P2 | open |
| imprint job writes memory but does not commit — writes sit dirty until the next session/dream commit sweep; decide owner of the commit step | Minor | 2026-06-12 | final review observation | open |
| agent-harness.md embeds a components snapshot ({{COMPONENTS}}) that duplicates generated/component-inventory.md and can drift — but a plain pointer breaks D9 for hosts (check_coverage excludes generated/ from its hay); resolve jointly | Minor | 2026-06-12 | portability gate (review-arch P2) | open |
| scaffold writes follow symlinked destinations (seed/git_hook write_text); refuse `is_symlink()` targets | Minor | 2026-06-12 | portability gate (review-security proposed) | open |
| lint readers crash on non-UTF8 .md in host docs (bare read_text in lint_docs/lint_structure); tolerate with errors=replace or skip+FAIL | Minor | 2026-06-12 | portability gate (review-reliability proposed) | open |
| no instance-layer S3 analog: nothing stops a machine-local absolute path being committed into a versioned host doc | Minor | 2026-06-12 | portability gate (review-arch proposed) | open |
| T7 extension candidate: any hook output injected into agent context that quotes repo-file content must carry the inline DATA guard (tidy_stop now does; rule not yet in SECURITY.md) | Minor | 2026-06-12 | portability gate (review-security proposed) | open |
| pre-commit hook body is a bare exec — missing python3 / dead gate path yields a raw shell error with no FIX hint; worktrees (`.git` file) and core.hooksPath silently get no hook | Minor | 2026-06-12 | portability gate (review-reliability proposed) | open |
