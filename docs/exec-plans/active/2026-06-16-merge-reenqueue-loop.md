---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: 17dea43bb7e09cb5a3ff39c592927a85258d5dfe
review_level: targeted
---
# Merge re-enqueue-after-Director-guidance loop

## Goal
Close the last deferred item of the serialized-merge pipeline: when the merger escalates a PR
(`mergeReview`), let the Director **requeue it with guidance** so the merger retries with a
directive — today it cannot, because `merge|<ticket>` / `mergereview|<ticket>` dedupe one-open-
per-ticket, so a consumed merge can never be re-queued under the same id. Observable:
1. Merge ids carry a **fresh attempt discriminant** (`merge|<ticket>|a<n>`, `mergereview|<ticket>|a<n>`),
   so re-enqueuing a ticket's merge (attempt 2) is a NEW request, not a dedupe — and a second
   failed attempt surfaces a distinct `mergeReview` (also fixes the old re-escalation dedup).
2. `director_min.requeue_merge(review, note=…)` answers the `mergeReview` AND re-enqueues the PR
   with `attempt+1` and the Director's `guidance=note`; the land lane's prompt carries that
   guidance. A `max_attempts` cap refuses runaway re-queues (→ the Director abandons/escalates).
3. End-to-end: a PR escalates → the Director requeues with a directive → the merger drains the
   retry (guidance in the land prompt) → merged, with the inbox empty.
4. `python3 plugin/scripts/check.py` GREEN.

## Context
- **Builds on** `docs/exec-plans/completed/2026-06-16-activate-serialized-merge-pipeline.md`
  (M1 handoff + M2 merger + M3 chain; live-verified local + full gh roundtrip) and its parent
  spec `docs/product-specs/2026-06-16-worker-qa-and-serialized-pr-merge.md` (R6 escalate-to-Director,
  D-48 single human surface). The re-enqueue loop is the parent's tracked Open Q.
- **Reuse:** `director/queue.append_merge_request`/`append_merge_review` (the id is the
  discriminant point), `director/merger.py` (`_surface_escalation` carries the attempt; `land_prompt`
  carries the guidance), `director/director_min.py` (`merge_reviews`/`answer_merge_review` —
  `requeue_merge` is the new loop driver), `docs/DIRECTOR.md` §7 (requeue currently documented as
  not-yet-wired; this wires it). The turnReview attempt-discriminant fix
  (`{tid}|turn|{turn_index}|a{attempt}` in `director/decider.py`) is the exact precedent.
- **Single-human-surface (D-48):** requeue is a DIRECTOR ACTION (it reads the mergeReview and
  decides with judgment), not an automatic merger retry — so the human stays in the loop.

## Approach (self-generated alternatives)
- **Discriminant:** A) **attempt number on the id** (`…|a<n>`), threaded through the
  mergeRequest→mergeReview→requeue cycle. Matches the turnReview precedent exactly; the attempt is
  meaningful (merge try #n). **Chosen.** B) a random/uuid suffix — rejected: opaque, no ordering,
  can't cap by attempt.
- **Who drives the loop:** A) **`director_min.requeue_merge`** = the Director's tool (answer review
  + re-enqueue attempt+1 with guidance), called when the Director decides to retry. Keeps the human
  in the loop (D-48). **Chosen.** B) automatic merger re-retry on escalate — rejected: removes the
  human judgment the escalation exists to get, risks blind loops.
- **Runaway guard:** a `max_attempts` cap in `requeue_merge` (refuse beyond N, signal give-up) so a
  buggy retry can't loop forever; the Director then abandons/escalates-to-human.

## Assumptions & open questions (self-interrogation)
- **Assumption — the mergeReview carries everything requeue needs** (pr, branch, workspace, attempt).
  `_surface_escalation` already has the source `req`; it will pass attempt + the request's
  pr/branch/workspace into the review. *If wrong:* requeue reads stale/missing fields → guard with
  the review's own payload + top-level workspace_path.
- **Assumption — attempt defaults to 1 keeps reconcile + existing callers unchanged** (the first
  enqueue is `…|a1`; tests assert payload/len, not the raw id). *If wrong:* a test pins the id →
  update it.
- **Open — `max_attempts` value.** Resolved autonomously: default 3 (attempt 1 auto + up to two
  guided retries), overridable; beyond it requeue refuses and the Director abandons/human (not a
  silent stop). Escalate only if a human wants a different policy (taste) — not a "what next?".

## Milestones
- **M1 — attempt discriminant + guidance plumbing.** `director/queue.append_merge_request` gains
  `attempt:int=1` + `guidance:str|None=None` → id `merge|<ticket>|a<attempt>`, payload carries both;
  `append_merge_review` gains `attempt:int=1` → id `mergereview|<ticket>|a<attempt>`, payload carries
  `attempt`. `director/merger.py`: `_surface_escalation` reads the request's attempt and passes it
  to `append_merge_review`; `_LAND_PROMPT`/`land_prompt` render a "DIRECTOR GUIDANCE (retry)" section
  when `payload.guidance` is set. At the end: re-enqueuing attempt 2 is a distinct pending request
  (not deduped); a 2nd-attempt escalation posts a distinct mergeReview; the land prompt shows
  guidance. Run: `python3 -m unittest discover -s tests -p "test_director_merger.py"` (+ new
  assertions); expect GREEN.
- **M2 — the loop driver + DIRECTOR.md.** `director/director_min.requeue_merge(review, *, note,
  base=None, max_attempts=3)`: answers the mergeReview (`action=requeue`), then re-enqueues the PR
  with `attempt+1` + `guidance=note` (reading pr/branch/workspace/attempt off the review); refuses
  beyond `max_attempts` (returns `{"requeued": False, "reason": "max_attempts"}` — Director then
  abandons/human). `docs/DIRECTOR.md` §7 requeue bullet rewritten: requeue NOW works (fresh attempt
  + guidance; the merger retries with the directive; cap). At the end: a `requeue_merge` call clears
  the review from the inbox and creates a fresh drainable mergeRequest carrying the guidance. Run:
  the same test file (+ `requeue_merge` tests); expect GREEN.
- **M3 — end-to-end loop test + completion gate.** One integration test (mock land driver): enqueue
  attempt 1 → drain → escalate → `mergeReview` → `requeue_merge(note="rebase onto X")` → a fresh
  attempt-2 mergeRequest (guidance present) → drain again (mock → merged) → merged + inbox empty;
  plus a max_attempts-exhausted path. At the end: the full guided-retry loop converges, proven by a
  test that fails before M1/M2. Run: `python3 plugin/scripts/check.py`; expect GREEN; then the
  targeted completion gate (review-reliability via codex — the loop convergence/cap/id-correctness
  is the risk).

## Progress log
- [x] (2026-06-16) M1 — attempt discriminant + guidance plumbing. `append_merge_request` gained
  `attempt:int=1`+`guidance` → id `merge|<t>|a<attempt>`, payload carries both; `append_merge_review`
  gained `attempt:int=1` → id `mergereview|<t>|a<attempt>`, payload carries `attempt`.
  `merger._surface_escalation` reads the request's attempt and passes it to the review;
  `land_prompt` renders a "DIRECTOR GUIDANCE (retry attempt N)" block when `payload.guidance` is set.
  Tests: attempt discriminates merge ids (attempt 1 vs 2 = 2 distinct requests; same attempt still
  dedupes); land prompt shows guidance only on a guided retry; escalation review carries + discriminates
  by attempt. Gate GREEN (307); existing reconcile/chain tests unaffected (attempt defaults to 1).
- [x] (2026-06-16) M2 — loop driver + DIRECTOR.md. `director_min.requeue_merge(review, note=…,
  max_attempts=3)`: reads attempt/pr/branch/workspace off the review, answers it (`action=requeue`),
  and re-enqueues at `attempt+1` with `guidance=note`; refuses beyond `max_attempts` (returns
  `{"requeued": False, "reason": "max_attempts"}`) leaving the review OPEN so the Director
  abandons/human (no silent infinite retry). `answer_merge_review`/`merge_reviews` docstrings +
  `DIRECTOR.md` §7 requeue bullet rewritten (requeue now works). Tests: requeue re-enqueues attempt 2
  with guidance + carried pr/branch/workspace, review handled; max_attempts refuses + leaves review open.
- [x] (2026-06-16) M3 — end-to-end loop test (`test_full_guided_retry_loop_converges`): attempt 1
  escalates → `requeue_merge(note=…)` → attempt 2 drains and MERGES, where the driver merges only
  when "DIRECTOR GUIDANCE" is in the land prompt — so a green result proves the guidance drove it.
  Queue + inbox empty (converged). Gate GREEN (310). Targeted completion gate (review-reliability via
  codex) next.

## Surprises & discoveries

## Decision log
- 2026-06-16: attempt-number discriminant on merge ids (mirrors the turnReview fix); requeue is a
  Director action (`requeue_merge`), keeping the human in the loop (D-48); `max_attempts` cap (default 3)
  prevents runaway re-queues.

## Feedback (from completion gate)

## Outcomes & retrospective
