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
