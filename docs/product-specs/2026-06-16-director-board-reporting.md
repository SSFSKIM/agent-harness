---
status: stable
last_verified: 2026-06-16
owner: harness
---
# Director board reporting (run-level pull)

Phase 4 (자율 Director) 의 로드맵 항목 **"board 리포팅"**. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(비전: Director 가 "board oversee · report"). 직전 슬라이스
[orchestration-visibility](2026-06-15-director-orchestration-visibility.md) 가 만든
`director.status` 스냅샷 위에서, **사람을 적절한 순간에 끌어들이는(pull)** 능력을 더한다.

## Problem (오늘 무엇이 불만족인가 — observable)

1. **리포팅이 on-demand 뿐이다.** Director 는 `docs/DIRECTOR.md` §8 로 사람이 *물어볼 때만*
   ("지금 뭐 돌아가?") `director.status` 로 답한다. unattended watched 런에서 런이 **종료
   국면**(drained 완료 / stuck — 사람이 풀어야 진행 / poll_failed / max_*)에 도달해도 사람을
   **능동적으로 끌어들이는 것이 없다** — 사람이 직접 들여다봐야 안다.
2. **per-ticket 이벤트는 개별 push 되지만 run-level 그림이 없다.** turnReview/mergeReview/
   escalation 은 이미 개별로 사람/Director 에 간다(§5). 빠진 건 **런 전체 상태를 담은 run-level
   pull** — "런이 끝났다/막혔다, 여기 요약, (필요하면) 당신이 필요하다."
3. PRODUCT_SENSE 의 명제(사람 시간·주의가 유일한 희소 자원)를 run 단위로 끌어올리려면, Director
   가 **주의가 정당한 순간에만**(런 종료/stuck) 사람을 pull 해야지, 사람이 폴링하게 두면 안 된다.

## Verified facts (repo, 추측 아님)

- `director/status.py` 가 원자적 스냅샷을 영속한다:
  `{run:{started_at,pass,stopped_reason}, in_flight, recent(bounded 20), stuck, updated_at}`.
  `run.stopped_reason` 은 orchestrator 가 런 종료에 `StatusWriter.finished(reason)` 로 set
  (`run_until_drained`: drained/stuck/max_passes/max_dispatched/poll_failed; `run_once`: pass_complete).
  `read_status` 는 tolerant — 파일 없음(런 없음)/깨짐 → None, raise 안 함.
- `director/watch.py` 가 큐를 tail 하고 미답 요청을 per-request emit(seen-set dedupe, per-line
  flush) → `Monitor` → Director(메인 세션) event-wake(§5). 인자: `--kinds`/`--queue-dir`/
  `--poll`/`--once`. `--kinds` 는 콤마 분리.
- `docs/DIRECTOR.md` §5 step 4 가 이미 taste 를 `PushNotification` 으로 사람에 올린다; §8 은
  on-demand report-up.
- Director 는 메인 세션(D-5). **코드는 done-ness/리포트-가치를 판단하지 않는다** — Director 가
  스냅샷에서 판단으로 작성한다(D-5/D-30 라인 일관).

## Requirements (R1..R6 — 각 항목 사람이 검증 가능)

- **R1 — watch 가 run-terminal 에 runReport 를 emit.** status 스냅샷의 `run.stopped_reason`
  이 비-None(터미널)이 되면 watch 가 `runReport` 이벤트 한 줄을 **런당 정확히 1회**(런 정체성으로
  dedupe) flush. (검증: `run.stopped_reason` 이 None→"drained" 로 바뀐 status.json 에서 watch 가
  runReport 1줄 emit; 재폴링은 추가 emit 0.)
- **R2 — runReport 는 `--kinds` 로 필터 가능.** Director 는 `--kinds turnReview,mergeReview,
  runReport` 로 무장. (검증: `--kinds runReport` 는 런 터미널만 emit, 큐 요청은 안 함.)
- **R3 — watch 의 status 읽기는 read-only + tolerant.** 없음/깨짐 → emit 0, 절대 crash 안 함
  (`read_status` 계약 재사용). (검증: status.json 없음/garbage 에서 watch 계속 돌고 emit 0.)
- **R4 — board 리포팅은 Director 가 따르는 *절차*(DIRECTOR.md), 판단하는 코드 아님.** runReport
  를 받으면 Director 는 `director.status` 를 읽어 digest(런 outcome · done/failed/blocked/
  escalated 카운트 · 무엇이 stuck 이고 왜 · 열린 merge escalation · 사람이 필요한 것)를 작성하고
  `PushNotification` 으로 사람을 pull; taste-vs-handle(§2)이 "조용한 완료" vs "당신이 필요(stuck/
  unblock)"를 가른다. (검증: DIRECTOR.md 절이 이 단계들을 명시; digest/push 를 만드는 코드 없음.)
- **R5 — watched-mode 전용.** un-watched(`--autonomous`, 라이브 Director 없음)는 pull 할 사람이
  없다 → board 리포팅 비적용(이를 요구하는 코드 경로 없음 — watch-emit + Director 절차 둘 다 watched
  루프 구성요소). (검증: 기능이 watch emit + Director 절차에만 살고, un-watched 실행을 바꾸지 않음.)
- **R6 — `python3 plugin/scripts/check.py` GREEN.**

## Design

```
orchestrator.run_until_drained ── finished(reason) ──▶ director-status/status.json (run.stopped_reason set)
                                                              │ (read-only tail)
director.watch ── poll: queue requests + status snapshot ─────┤
   └─ run.stopped_reason 비-None & (started_at,reason) 미관측 ─▶ emit {kind:"runReport", reason, run, summary}
                                                              │ (flushed line)
   Monitor ─▶ Director(메인 세션) wake ─▶ director.status 읽기 ─▶ digest 작성 ─▶ PushNotification(사람)
```

### A. watch 확장 (유일한 코드 변경)
- `director/watch.py` 에 `--status-dir` 추가. 매 폴링에서 큐 패스 뒤 `status.read_status(status_dir)`.
  `run.stopped_reason` 이 비-None 이고 `(run.started_at, stopped_reason)` 가 status-seen 셋에
  없으면 `{kind:"runReport", reason:<stopped_reason>, run:<run dict>, summary:{done/failed/
  blocked/stuck 카운트(recent+stuck 에서 집계)}}` 를 flush emit 하고 seen 에 추가.
- **dedupe 키 `(started_at, stopped_reason)`**: 새 런(새 started_at)은 재-emit; 한 런은
  `finished()` 가 1회라 터미널 1회. 키가 런-재시작을 구분.
- `--kinds` 가 runReport 를 큐 kind 들과 같이 필터(런 터미널은 큐 요청이 아니라 합성 이벤트).
- status 읽기는 `read_status`(tolerant) 그대로 — 없음/깨짐 → emit 안 함, watch 계속 돈다(R3).

### B. Director 절차 (DIRECTOR.md 신규 절 + §5 갱신)
- §5 step 2 의 watch 무장 라인에 `runReport` 추가(`--kinds turnReview,mergeReview,runReport`,
  `--status-dir`).
- 신규 절(예: §9 "Run-level reporting — pull the human"): runReport 를 받으면 (1) `director.status`
  를 읽고, (2) 런 digest 를 작성(outcome · 카운트 · stuck+이유 · 열린 merge escalation · 사람이
  필요한 것), (3) taste-vs-handle(§2)로 판단해 `PushNotification` 으로 사람을 pull(stuck/unblock 은
  "당신이 필요", 깨끗한 drained 는 조용한 "완료" — 또는 사람 선호 시 무음). 코드는 무엇이 pull-worthy
  인지 판단하지 않는다.

### 구성요소 / 파일
- `director/watch.py` — status 스냅샷 tail + runReport emit (유일 코드 변경).
- `docs/DIRECTOR.md` — board-reporting 절차 절 + §5 watch 라인 갱신.
- `tests/test_director_watch.py` (신규 또는 기존) — runReport emit/ dedupe/ --kinds 필터/ tolerant.
- 재사용: `director/status.read_status`(스냅샷 소스), `PushNotification`(pull). orchestrator/
  status.py **변경 0**(orchestrator 는 이미 `finished()` 기록; watch 는 읽기만) — blast radius 최소.

### 에러 / 경계 케이스
- status.json 없음/torn → watch emit 0, 계속 돈다(read_status tolerant, R3).
- 같은 런 재폴링 → seen 셋이 중복 emit 차단(R1). 새 런(새 started_at) → 새 runReport.
- un-watched 런 → Director 없음 → runReport 가 떠도 깨울 메인 세션이 없음(무해; watched 전용 R5).
- `pass_complete`(run_once --once)도 터미널 → emit 됨; Director 가 관련성 판단(축퇴 단일 패스).

## Non-goals (scope fence — YAGNI)

- **heartbeat / 주기적 progress ping.** 명시 기각 — 희소 주의(런-terminal 만 pull).
- **내구성 board/Linear run 기록.** 다른 목적(택하지 않음); 필요해지면 별도 슬라이스.
- **중간 조기-실패-패턴 pull.** terminal-only v1 — 실패 패턴은 Director 가 터미널 digest 에서 판단.
  threshold knob 기반 조기 pull 은 후속(Open Q).
- **리포트-가치를 코드가 판단.** Director 가 작성(D-5/D-30 일관).
- **un-watched 리포팅.** 라이브 사람/Director 없음.
- Phase 5(공유 tracker / observability surface).

## Acceptance criteria

- watch 가 `run.stopped_reason` 터미널 전이에 runReport 정확히 1회 emit; 재폴링 dedupe;
  `--kinds` 필터; 없음/torn 스냅샷에 tolerant(R1–R3).
- DIRECTOR.md 절이 Director 에게 runReport 시 digest 작성 + PushNotification pull 을 안내(R4).
- `python3 plugin/scripts/check.py` GREEN(R6).
- (live, 선택) watched 런이 drained/stuck 으로 끝나면 Director 가 깨어 digest 를 push — 가능하나
  push 자체는 Director prose.

## Decision Log (수렴 결정 + 근거)

- **D-1 목적 = 사람 attention pull(내구성 기록 아님).** unattended 런에서 주의가 정당한 순간에
  사람을 끌어들이는 게 가치 — PRODUCT_SENSE 희소-주의 명제의 run 단위. (사람, 2026-06-16.)
- **D-2 트리거 = run-level inflection, terminal-only emit.** drained/stuck/max/poll_failed; 실패
  패턴은 Director 가 터미널 digest 에서 판단; 중간 조기 pull 은 defer. `run_until_drained` 의
  inflection 은 사실상 런 종료라 terminal-only 가 자연스럽고 가장 단순·scarce-attention 정직.
  (사람, 2026-06-16.)
- **D-3 메커니즘 = director.watch 확장(status 스냅샷 tail).** 기존 event-wake 배관 재사용, 새 queue
  kind 없음, orchestrator 변경 0; Director 가 director.status 에서 digest 작성 + PushNotification.
  (사람, 2026-06-16.)
- **D-4 watched-mode 전용.** un-watched 는 pull 할 라이브 사람/Director 없음(D-1 귀결). (자율.)
- **D-5 코드는 리포트-가치 판단 0 — DIRECTOR.md 절차 + Director 판단.** 오케스트레이션 라인의
  "judge=메인 세션"(D-5/D-30)과 일관; 코드는 신호(watch)만. (자율.)

## Open Questions

- **중간 조기-실패-패턴 pull**(threshold/스텝 knob) — defer; terminal-only 가 "너무 늦게" 알리면 재검토.
- **digest 내용/포맷 풍부함** — Director 의 prose; 실제 런에서 정제.
- watch 가 한 프로세스로 큐+status 둘 다 tail vs 별도 — 1차 한 프로세스(단순); 분리는 부하 시 재검토.
