---
status: active
last_verified: 2026-06-15
owner: harness
base_commit: 0c9ec4c2a866f3a795dd068f869e27791732845b
review_level: standard
---
# Multi-turn 티켓 실행 — Director-driven continuation + worker-proposed status

## Goal
A single ticket drives across **multiple turns on one Codex thread** until the
worker (not code) judges it terminal. Observable definition of done, all on the
mock board unless noted:

1. A ticket runs ≥2 `turn/start` calls on the **same thread id**; the board does
   **not** move to Done between turns (R1/R4).
2. When a turn ends in prose with no terminal signal (e.g. "A 일 수도 B 일 수도"),
   the Director returns a **free-form content-bearing directive** ("A 로 해라"),
   fed as the next turn's input — *not* a fixed "continue" (R3/R7).
3. The board transitions **only** on a terminal signal: a worker
   `report_outcome(done)` → Done; `report_outcome(blocked, spawned_ticket_ids=[…])`
   → comment + recorded children; nothing else moves it (R3/R4).
4. A worker that never signals terminal stops at **max-turns** and is reported
   `stuck` (R6).
5. **Live wire-pin** (real `codex app-server`): one real worker runs a 2+-turn
   task, a mid-turn fork gets a content-bearing reply, and it finishes terminal.
6. `git diff <base>..HEAD` shows **no** `completed → Done` turn-status→board-state
   mapping in `director/orchestrator.py` (R4).
7. `python3 plugin/scripts/check.py` GREEN.

## Context
- **Design owner (read first):**
  `docs/product-specs/2026-06-15-multi-turn-ticket-execution.md` (R1–R8, D-39..D-45).
  This plan owns the *build*; the spec owns the *what/why*. Do not re-derive it.
- **Reconcile model being redesigned:**
  `docs/product-specs/2026-06-14-orchestrator-dispatch-loop.md` — its
  "turn-status → board-state code mapping" (`completed → Done`) is what R4 removes.
- **What exists today (the single-turn machine):**
  - `director/run.py::run_ticket` — `thread_start` then **one** `run_turn`, returns
    `{status, turn_id}`. No loop, drops the assistant message.
  - `director/worker/app_server.py::run_turn` (line 209) — streams to
    `turn/completed|failed|cancelled`, returns `{status, turn_id}`. The agent's
    final message arrives as an `item/completed` notification with
    `item.type == "agentMessage"` (see `_mock_app_server.complete_turn`) and is
    currently **discarded**.
  - `director/orchestrator.py::reconcile` (line 104) — `status == "completed"` →
    `set_state(states["done"])`. **This is the wrong code mapping** (R4).
  - `director/worker/tools.py` — the `linear_graphql` dynamicTool + executor pattern
    `report_outcome` will copy (advertise in `thread/start`, route via
    `item/tool/call` → `tool_executor`).
  - `director/queue/__init__.py` + `director/worker/approval.py` — the
    request/answer seam. The **watched** turn-end decider reuses this exact channel
    (append a request, block for the answer) rather than inventing a new transport.
  - `director/director_min.py` — the main session's hands on the queue
    (`pending`/`answer`); gains a turn-review helper.
  - `director/status.py` — orchestration snapshot; gains per-ticket turn count (R8).
- **Verified live (this session, not assumed):** multi-turn continuation works —
  two `run_turn` calls on one thread, turn 2 recalled turn 1's codeword (BANANA7).
  The mechanism (`thread_start` + repeated `run_turn`) is present; only
  `run_ticket` stops after one turn. `codex app-server` is on PATH (codex-cli
  0.139.0).
- **Posture unchanged:** `--autonomous` keeps the slice-3 preset; SECURITY T11 /
  the exfil tech-debt are not touched here.

## Approach (self-generated alternatives)

**A1 — where the multi-turn loop lives.**
- A: a new `drive()` in `director/run.py` that owns the turn loop and calls an
  **injected** `decide(ctx) → Disposition`; `director/orchestrator.py` only
  *executes* the terminal disposition onto the board. — keeps DI grain consistent
  with the repo (`tool_executor`, `status`, `http_post`, `make_seam` are all
  injected), keeps board writes in the orchestrator where they already live.
- B: put the loop in the orchestrator. — bloats the dispatch loop, mixes
  thread-driving with board reconciliation, harder to unit-test one ticket.
- **Chosen: A.** `drive` owns turn-driving + disposition routing; orchestrator owns
  board execution. The decider is *injected*, so watched (queue) and un-watched
  (code) are two implementations of the same callable.

**A2 — terminal signal channel.**
- A: a `report_outcome` **dynamicTool** (advertised like `linear_graphql`, routed
  via `item/tool/call`), recording into a per-drive sink. — structured, reliable,
  reuses the existing `tool_executor` path (spec D-44).
- B: parse the prose final message for "done"/"blocked". — brittle, NL-classified.
- **Chosen: A** for terminal signals; prose final message is the channel for
  *mid-work* dispositions (Director reads it). Two channels, one wire (D-44/D-45).

**A3 — the Director reply (the headline RV2 case).**
- A: `decide()` returns a free-form `reply` string fed verbatim as the next turn's
  input. Watched: a human/main-session writes it via the queue. Un-watched:
  default code reply = "use your best judgment and continue". — matches D-45
  (content-bearing, not a fixed enum).
- B: a fixed `continue` token. — **rejected by the spec** (D-45): can't answer
  "A 냐 B 냐".
- **Chosen: A.**

## Assumptions & open questions (self-interrogation)
- **Assumption — the real Codex emits the agent's final message as an
  `item/completed` (or `item/updated`) notification carrying `agentMessage` text**,
  same family as the mock. *What breaks if wrong:* `final_message` capture is empty
  and the Director reads nothing. **De-risked in M1 first** (live inspection of the
  real event stream) before the loop is built on it.
- **Assumption — a worker can call a client-advertised `report_outcome` tool and
  the call reaches `tool_executor`** (the `linear_graphql` path already proves
  `item/tool/call` routing). *What breaks if wrong:* terminal signals never arrive;
  the safety net (R7) is that a no-signal turn-end defaults to a Director read, and
  `report_outcome` adoption is M1-measured.
- **Open — does the worker reliably *choose* to call `report_outcome` at terminal?**
  Resolved autonomously: **do not depend on it.** The Director-read path is the
  primary mid-work channel; `report_outcome`, when present, makes terminal
  *certain*; when absent, the Director infers terminal from the final message, and
  the max-turns bound (R6) is the backstop. M1 measures adoption to tune the
  default, not to gate the design.
- **Open — `max_turns` default.** Resolved autonomously: **8** per ticket
  (`--max-turns`, configurable). Rationale: generous enough for research→design→
  impl hand-offs within one ticket, small enough that a looping worker surfaces as
  `stuck` quickly. Recorded in Decision log; not a taste call.
- **Open — terminal `blocked` board state.** Resolved autonomously: mirror the
  existing optional `--failed-state` with an optional `--blocked-state`; absent it,
  a blocked terminal stays in `started` + comment and records `spawned_ticket_ids`
  (the worker creates children itself via `issueCreate`; the DAG/Phase-3a picks
  them up on the next poll). No new mandatory workflow state. Not a taste call.
- **Open — who mutates the board for a terminal?** Resolved: the **orchestrator**
  executes the *current ticket's* status from the worker's *proposed* outcome
  (worker proposes, Director/code executes — D-40); the worker may *spawn children*
  itself (it already has `issueCreate` via `linear_graphql`). This avoids
  double-mutation of the parent's status while honoring R4 (the *judgment* is the
  worker's LLM; code only applies the proposal).

## Milestones

- **M1 — PoC: pin the two unknowns against a real worker (final-message capture +
  `report_outcome` adoption).** The only genuine unknowns are wire-shaped, so settle
  them before building the loop on top. Add final-message capture to
  `run_turn` (accumulate the latest `agentMessage`/text item, return it as
  `final_message`; keep `{status, turn_id}` intact) and add a `report_outcome`
  dynamicTool spec + executor that records into a sink. Then **live-run one real
  `codex app-server` turn** with both wired and an `on_event` tap, on a throwaway
  prompt that (a) ends in prose and (b) a second prompt that asks the worker to call
  `report_outcome(done)`. At the end: a short PoC script under
  `/tmp` (not committed) printing the captured `final_message` and whether
  `report_outcome` fired. Run: the PoC script via `codex app-server`. Expect: the
  prose turn yields a non-empty `final_message`; the structured prompt shows whether
  the worker calls the tool. Record the **observed real event shape** in Surprises —
  it pins the capture logic. (If the real shape differs from the mock, adjust the
  capture predicate here, where it is cheap.)

- **M2 — the `drive` loop + decider, unit-tested on the mock.** Replace
  `run_ticket`'s single turn with `drive(ticket, …, decide, max_turns)`:
  `thread_start` once, then loop `run_turn` up to `max_turns`; each iteration clears
  the report_outcome sink, runs the turn, builds a turn context
  `{final_message, report_outcome?, ticket, turn_index}`, calls `decide(ctx) →
  Disposition`, and routes: `terminal` → return it; `escalate` → return it;
  `reply` → feed `disp.reply` as the next turn's input (board untouched);
  exhaust `max_turns` → return `{kind: "stuck", reason: "max_turns"}`. Ship the
  **un-watched code decider** (`director/worker/` or `director/run.py`): terminal
  `report_outcome` → terminal disposition; `needs_human` → escalate; **no signal /
  prose → `reply` = "Use your best judgment; if you reached a fork pick the most
  reasonable option and proceed"** (the "self-resolve and continue" generalization).
  Extend `_mock_app_server.py` with multi-turn scenarios: a thread that takes N
  turns, one that calls `report_outcome` on turn 2, one that ends every turn in
  prose. At the end: `director/run.py` drives multiple turns on one thread with a
  pluggable decider; `tests/test_director_run.py` (+ a new
  `tests/test_director_drive.py`) prove: 2-turn same-thread progression, prose-end →
  reply fed forward, `report_outcome(done)` → terminal, max-turns → stuck. Run:
  `python3 -m unittest tests.test_director_drive tests.test_director_run`. Expect:
  green; assertions on same `thread_id` across turns and on the disposition kinds.

- **M3 — orchestrator reconcile redesign + watched decider + visibility.** Remove
  the `completed → Done` mapping from `director/orchestrator.py::reconcile`;
  `dispatch` calls `drive` and the orchestrator **executes the terminal
  disposition** onto the board (`apply_terminal`: `done` → done state + comment;
  `blocked` → optional `--blocked-state` else stay started + comment, record
  `spawned_ticket_ids`; `escalate`/`needs_human` → leave visible + surface; `stuck`
  → stuck summary). A non-terminal disposition never reaches the orchestrator
  (it is consumed inside `drive`). Wire the **watched decider** as the default
  (orchestrator without `--autonomous`): a `decide` that appends a `turnReview`
  request to `director/queue` ({final_message, report_outcome?, ticket}) and blocks
  for the answer, mapping `{disposition: terminal|reply|escalate, …}` to a
  `Disposition`; add a `director_min` helper to answer turn reviews and a
  `director-oversight` SKILL.md section on reading them (the skill reclaims its
  original purpose). Un-watched (`--autonomous`) selects the M2 code decider. Add
  `--max-turns`/`--blocked-state` to both `run` and `orchestrator` CLIs. Reflect
  turn count in `director/status.py` (R8). At the end: a `--mock` orchestrator run
  drives multi-turn tickets, the board moves only on terminal, and the snapshot
  shows turn counts. Run:
  `python3 -m director.orchestrator --mock --team T --once` (and the existing
  `tests/test_director_orchestrator.py` extended for the new reconcile). Expect:
  Done only on terminal; `git diff` shows no turn-status→board-state mapping (Goal 6).

- **M4 — live wire-pin (acceptance).** One real `codex app-server` worker runs a
  task that genuinely spans 2+ turns (e.g. "research then implement"), with a
  scripted/un-watched decider that, at a mid-turn fork, supplies a **content-bearing**
  directive ("do A"), and the run ends on a terminal signal. At the end: a
  transcript (kept in Outcomes) showing same-thread multi-turn progression, the
  content-bearing reply, and the terminal finish — the spec's "Live wire-pin"
  acceptance. Run: `python3 -m director.run --linear <id>` (or a stub) against the
  real worker with `--max-turns` set. Expect: ≥2 turns, one content-bearing reply,
  terminal end; the board (if Linear) moves only at terminal.

## Progress log
- [ ] M1 — final-message capture + report_outcome wiring; live-pin event shape.
- [ ] M2 — `drive` loop + code decider + mock scenarios + unit tests.
- [ ] M3 — orchestrator reconcile redesign + watched decider + status + CLI flags.
- [ ] M4 — live wire-pin (real codex, 2+ turns, content-bearing reply, terminal).

## Surprises & discoveries

## Decision log
- 2026-06-15: **Loop lives in `run.py::drive`; orchestrator executes terminal only**
  (A1-A) — keeps the injected-dependency grain and board writes where they are.
- 2026-06-15: **`report_outcome` = dynamicTool with a per-drive sink** (A2-A / spec
  D-44) — structured terminal signal reusing the `tool_executor` path; prose final
  message is the mid-work channel.
- 2026-06-15: **Director reply is a free-form string, not a fixed enum** (A3-A /
  spec D-45) — un-watched default reply = "self-resolve and continue"; watched =
  queue-answered.
- 2026-06-15: **`max_turns` default = 8**, `--max-turns` configurable — bounds
  auto-continue (R6) without starving multi-stage tickets.
- 2026-06-15: **Blocked terminal uses optional `--blocked-state`** (mirrors
  `--failed-state`); else stay `started` + comment + record `spawned_ticket_ids`.
- 2026-06-15: **Worker proposes status, orchestrator executes the parent's status;
  worker spawns children itself** (D-40) — no double-mutation; R4 honored (judgment
  is the LLM's, code applies the proposal).
- 2026-06-15: **M1 de-risks the wire unknowns before the loop is built** — live
  inspection pins the real `agentMessage` event shape and `report_outcome` adoption.

## Feedback (from completion gate)

## Outcomes & retrospective
