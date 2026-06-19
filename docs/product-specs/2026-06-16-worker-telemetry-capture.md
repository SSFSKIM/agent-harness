---
status: stable
last_verified: 2026-06-16
owner: harness
phase: symphony/05-telemetry
type: product-spec
tags: [worker, telemetry, observability, status]
description: Captures Symphony-grade operational telemetry (per-ticket tokens, turn counts, session ids, run-level codex totals and rate limits) at turn and dispatch boundaries and persists it additively into status.json as the data producer ahead of the renderer.
---
# Worker telemetry capture (Symphony-grade) into status.json

Phase 5(optional)의 **observability** 트랙. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md).
이 슬라이스는 [observability dashboard](2026-06-16-director-observability-dashboard.md)
(renderer)의 **선행 조건**이다 — renderer 의 richness 는 producer state 에 묶이므로
(렌더러는 데이터의 하류), 먼저 **데이터(telemetry)를 풍부하게** 만든다. 풍부해진
`status.json` 은 즉시 유용하다: 인라인 Director 가 읽고, `python3 -m director.status`
가 덤프하고, 이후 어떤 surface(dashboard·digest·board-report)든 공짜로 풍부해진다.

OpenAI Symphony 가 추적하는 운영 telemetry — per-session 토큰·런타임·rate-limit·
turn_count·last_event(SPEC §4.1.6/§4.1.8/§13.3/§13.5) — 를 우리 모델에 맞게 **턴/디스패치
경계에서** 포착해 `status.json` 에 영속한다. 오라클: 로컬 `docs/symphony-original/SPEC.md`
(gitignored vendored 사본) + `/tmp/symphony-research`.

## Problem (오늘 무엇이 불만족인가 — observable)

1. **telemetry 를 0 포착한다.** `director/` 어디에도 토큰/usage/rate-limit 영속이 없다
   (유일한 "token" 히트는 무관 — authority.py 의 GraphQL 토크나이저, land_watch.py 의 429
   탐지). 워커의 `app_server.run_turn` 은 codex 스트림의 모든 notification 을 읽지만
   (`on_event` 경로) usage 이벤트를 추출하지 않고 버린다.
2. **"이 런이 무엇을 쓰고 있나"를 볼 수 없다.** 사람/Director 가 런의 비용(토큰)·런타임·
   rate-limit 여유를 알 길이 없다 — Symphony 대시보드의 핵심 가치(§13.3 snapshot:
   running rows + codex_totals + rate_limits)가 우리엔 데이터 자체가 없어 불가능.
3. visibility spec 이 라이브 dashboard 를 Phase 5 로 미뤘는데(line 208), 그 dashboard 가
   풍부하려면 **먼저 producer 가 풍부해야 한다**. renderer 를 먼저 지으면 thin 데이터 위
   thin UI 가 된다 — 그래서 이 슬라이스가 renderer 보다 선행(사람 결정 2026-06-16 pivot).

## Verified facts (repo, 추측 아님)

- `director/worker/app_server.py:230` `run_turn(thread_id, text, ...) -> {status, turn_id,
  final_message}`. 턴 스트림의 모든 notification 을 읽고(`on_event` 으로도 흘림, line 262),
  `item/completed`→agentMessage 만 추출한다. usage notification 은 **본다, 버린다**. 방어
  패턴 `agent_message_text`(line 61)는 codex-cli 0.139.0 에 live-pin 됨 — usage 추출도 같은
  패턴(tolerant, 없으면 None).
- `director/run.py:123` `drive(...)` 는 한 thread 에서 multi-turn 루프를 돌고 disposition 을
  `{turns, turn_id, final_message, thread_id}` 로 enrich 해 **한 번** 반환. `thread_id`/
  `turn_id`(→session_id), `turns`(→turn_count), `final_message`(→last_message) 가 이미 손에
  있다. `_prepare` 는 현재 `on_event` 를 wiring 하지 않음(no-op 기본).
- `director/orchestrator.py:240` 워커는 `ThreadPoolExecutor` 에서 실행(`dispatch`→`drive` 가
  **워커 스레드**). main loop 가 `wait(FIRST_COMPLETED)`(line 283) 후 **main 스레드**에서
  `status.dispatched/terminal/...`(line 251/258/297) 호출. → 워커 스레드의 `on_event` 는
  StatusWriter 를 싸게 mid-turn 갱신 불가(cross-thread). 경계 포착이 자연스럽고 lock-free 유지.
- `director/status.py:68` `StatusWriter` 는 **main 스레드 단일 writer, lock 없음**(docstring
  명시). snapshot 스키마: `run{started_at,pass,stopped_reason}`, `in_flight[{ticket_id,
  identifier,phase,attempt,wave,started_at}]`, `recent(≤20)[{ticket_id,ticket,status,
  final_state,attempts,turns}]`, `stuck`, `updated_at`. `NoopStatusWriter` + `read_status`/
  `context_for` 는 tolerant. flush 는 best-effort(write 실패 swallow, R3 "visibility never
  blocks dispatch").
- **Symphony telemetry 모델(SPEC, vendored):** §4.1.6 Live Session(session_id, last_event/
  timestamp/message, codex_input/output/total_tokens, last_reported_*, turn_count); §4.1.8
  codex_totals(토큰+seconds_running) + codex_rate_limits(latest); §13.3 snapshot rows;
  §13.5 accounting rules(아래 R5).

## Requirements (R1..R8 — 각 항목 사람이 검증 가능)

- **R1 — app_server 가 usage 를 추출.** tolerant `extract_usage(method, params)` 가 codex 의
  **절대 thread 토큰 총량**(`thread/tokenUsage/updated` / `total_token_usage` 류)을 lenient
  필드매칭으로 뽑고 delta 류(`last_token_usage`)는 무시. `run_turn` 이 `{…, usage:{input,
  output,total}|None, rate_limits:<payload>|None}` 반환. usage 이벤트 없음(mock/구버전)→None.
  (검증: 단위 — 절대-총량 이벤트→totals, delta 이벤트→무시/None, 없음→None, 필드명 변형 허용;
  run_turn — mock 이 usage notification emit 시 result.usage 채워짐, 안 emit 시 None.)
- **R2 — drive 가 per-ticket telemetry 누적.** disposition 에 telemetry 블록:
  `{tokens:{input,output,total}|None, turn_count, session_id:"<thread>-<turn>", last_message,
  rate_limits}`. 토큰은 thread 절대총량이라 **마지막 턴의 절대총량 = 티켓 총량**(합산 아님,
  §13.5 anti-double-count). (검증: multi-turn mock — tokens 가 최신 절대총량이지 합이 아님;
  session_id/turn_count/last_message/rate_limits 채워짐.)
- **R3 — orchestrator 가 per-ticket 기록 + run aggregate 누적.** 기존 `status.terminal` 콜
  사이트(main 스레드)에서 disposition 의 telemetry 를 summary 에 fold → recent[].tokens/
  session_id/last_message 기록; run-level `codex_totals`(토큰 delta vs last-reported 누적) +
  최신 `rate_limits` + 누적-종료 seconds. (검증: 2-티켓 런 — recent[] 각각 tokens, run.
  codex_totals = 합, seconds_running 증가.)
- **R4 — status.json 스키마는 additive.** recent[] += `tokens`/`session_id`/`last_message`;
  `snapshot()['run']` += `codex_totals{input,output,total,seconds_running}` + `rate_limits`.
  `seconds_running` 은 snapshot 시점 **live 집계**(누적-종료 + Σ in_flight active-elapsed,
  §13.5). NoopStatusWriter + read_status/context_for + 기존 318 테스트 **불변**. (검증: 스냅샷에
  새 필드; telemetry 없는 경로 → 필드 부재/0, 스냅샷 valid; 기존 테스트 green.)
- **R5 — §13.5 accounting 준수.** ① 절대 thread 총량 우선, delta(`last_token_usage`) 무시;
  ② 절대총량은 last-reported 대비 delta 로 aggregate 에 더해 **double-count 방지**; ③ generic
  `usage` 맵을 이벤트 타입이 정의하지 않는 한 누적으로 취급 안 함; ④ runtime 은 render-time
  live 집계(연속 background ticking 불요). (검증: 같은 절대총량 재보고가 aggregate 를 부풀리지
  않음; delta-style payload 가 totals 를 오염 안 함.)
- **R6 — telemetry 는 instrumentation, 절대 gate 아님.** 추출/누적 실패는 swallow(StatusWriter
  best-effort 와 동형) — 깨진/없는 usage 이벤트가 턴이나 dispatch 를 **절대 실패시키지 않음**
  (status.py R3 "visibility never blocks dispatch" 의 telemetry 판). (검증: malformed usage
  payload → telemetry None/불변, 턴 정상 completed.)
- **R7 — bonus deep-link `url`(조건부).** ticket 이 url 을 가지면 in_flight/recent 에 영속
  (§13.3 + Elixir 링크). ticket 모델이 url 을 안 나르면 **이 필드만 defer**(날조 금지 —
  ExecPlan 에서 board/linear 확인). (검증: url 있는 ticket→영속, 없으면 부재.)
- **R8 — `python3 plugin/scripts/check.py` GREEN.**

## Design

```
codex stream ──usage notifications──▶ app_server.run_turn: extract_usage(tolerant)
                                          │ returns {status,turn_id,final_message, usage, rate_limits}
   drive(): per-ticket 누적 (§13.5 절대총량, track-vs-last-reported)
            disposition += telemetry{tokens, turn_count, session_id, last_message, rate_limits}
                                          │ (워커 스레드 → 한 번 반환)
   orchestrator (main 스레드, future 완료 시):
        status.terminal(ticket, summary + telemetry) + run aggregate 누적
                                          ▼
   status.py StatusWriter ──▶ status.json:
        recent[].{tokens, session_id, last_message}   run.{codex_totals(+seconds_running), rate_limits}
```

### A. app_server.py — wire-level usage 추출
- `extract_usage(method, params) -> dict|None`: codex 의 절대 thread 토큰 총량을 lenient 매칭
  (§13.5 common field names)으로 뽑음; delta 류는 None. 순수 함수 — 단위 테스트 용이.
- `run_turn` 의 notification 루프(현 line 260-275)에서 usage/rate-limit 이벤트를 만나면 최신값을
  보관, 반환 dict 에 `usage`/`rate_limits` 추가. agentMessage 추출 로직(존속)과 나란히.
- 정확한 method/필드명은 codex-cli 에 **live-pin**(agentMessage 처럼) — ExecPlan PoC. 없으면 None.

### B. drive() — per-ticket 누적
- 턴마다 `run_turn` 결과의 절대총량을 보관 → 티켓 totals = 최신 절대총량(§13.5). session_id =
  `<thread_id>-<turn_id>`, turn_count = `turns`, last_message = `final_message`, rate_limits =
  최신. disposition 에 `telemetry` 블록 추가(터미널/escalate/stuck/failed 모든 종류에 base 로).

### C. orchestrator.py — 기록 + 집계
- `status.terminal` 콜 사이트에서 summary 에 telemetry fold. run aggregate(StatusWriter 상태)에
  토큰 delta(vs ticket last-reported) 누적, 최신 rate_limits, 종료 ticket 의 runtime 초를 누적.
- 기존 summary dict 에 additive — 새 콜 경로 없음.

### D. status.py — additive 스키마 + StatusWriter
- StatusWriter 에 aggregate 상태 `_codex_totals{input,output,total, seconds_ended}`, `_rate_limits`.
  `terminal()` 가 telemetry 를 받아 recent 엔트리에 tokens/session_id/last_message 기록 + aggregate
  누적(또는 별 `record_usage` 헬퍼). `snapshot()` 의 run 에 `codex_totals`(seconds_running =
  seconds_ended + Σ(now - in_flight.started_at), §13.5 live) + `rate_limits`.
- 전부 additive: NoopStatusWriter 그대로 no-op; read_status/context_for 는 새 필드를 그냥 통과.

### E. bonus deep-link url
- in_flight/recent 엔트리에 `ticket.get("url")` 있으면 영속. board/linear 가 url 을 나르는지
  ExecPlan 에서 확인 — 안 나르면 이 필드만 defer(R7).

### 구성요소 / 파일
- `director/worker/app_server.py` — `extract_usage` + `run_turn` 반환 확장.
- `director/run.py` — `drive` 누적 + disposition telemetry.
- `director/orchestrator.py` — terminal 콜 사이트 telemetry fold + run aggregate.
- `director/status.py` — StatusWriter aggregate + snapshot 스키마(additive).
- `director/worker/_mock_app_server.py` — 한 시나리오에서 usage notification emit(테스트용).
- `tests/` — extract_usage 단위 + run_turn/drive/orchestrator/status 통합 + backward-compat.

### 에러 / 경계 케이스
- usage 이벤트 부재/malformed → None/불변, 턴·dispatch 정상(R6).
- thread 절대총량이 더 낮게 보고(이상) → 음수 delta 방지(0 으로 clamp).
- in_flight 가 0 → seconds_running = seconds_ended.
- 기존 telemetry-없는 호출 경로(단위 테스트 등) → 필드 부재/0, 스냅샷 valid(R4).

## Non-goals (scope fence — YAGNI)

- **live in-flight 토큰 accrual(Layer 2).** 실행 중 티켓의 토큰이 실시간 ticking — 워커→
  StatusWriter thread-safe 채널(lock/atomic per-ticket 파일) 필요, status.py lock-free 불변식
  위배. defer(사람 결정 boundary-capture).
- **web renderer(dashboard).** [observability-dashboard](2026-06-16-director-observability-dashboard.md)
  슬라이스 — 이 데이터의 consumer 로 **재배치**(이 슬라이스가 선행).
- **cross-run 히스토리/메트릭 영속.** codex_totals 는 current-run; recent 는 bounded tail.
- **humanized event summaries(§13.6).** raw 필드만.
- **restart 간 telemetry 영속.** in-memory aggregate(Symphony §14.3 와 동일).
- **rate_limits 의 표현/파싱.** 최신 payload 를 raw 로 보관만; presentation 은 후속.

## Acceptance criteria

- `extract_usage` 가 절대총량→totals / delta→무시 / 없음→None / 필드변형 허용(R1·R5).
- `run_turn` 이 usage/rate_limits 반환(mock usage 이벤트), 없으면 None(R1).
- `drive` 가 per-ticket telemetry(최신 절대총량·session_id·turn_count·last_message·rate_limits)
  를 disposition 에 실음(R2).
- 2-티켓 런에서 recent[].tokens 각각 + run.codex_totals 합 + seconds_running live 증가(R3·R4).
- status.json 새 필드 additive; telemetry-없는 경로 valid; NoopStatusWriter + 기존 318 테스트
  green(R4·R6).
- malformed usage → 턴/ dispatch 정상(R6); url 조건부(R7); check.py GREEN(R8).
- (live, 선택) 실 codex 런에서 status.json 에 실제 토큰/seconds/rate_limits 가 채워짐.

## Decision Log (수렴 결정 + 근거)

- **D-1 producer-before-renderer pivot.** renderer richness 는 producer state 에 묶임 — thin
  데이터 위 thin UI. 데이터를 먼저 풍부하게 하면 Director/status/모든 미래 surface 가 즉시
  풍부. dashboard 는 이 데이터의 consumer 로 재배치. (사람, 2026-06-16.)
- **D-2 boundary capture, not live stream.** 워커는 ThreadPool 스레드, StatusWriter 는 main-스레드
  lock-free 단일 writer; drive 는 dispatch 당 한 번 반환. mid-turn 라이브는 cross-thread 채널이
  필요(불변식 위배)→Layer 2. 경계 포착이 lock-free 유지하며 비용/턴_count/세션/aggregate 의
  대부분 가치를 포착. (사람, 2026-06-16.)
- **D-3 Symphony §13.5 accounting.** 절대 thread 총량 우선, delta 무시, track-vs-last-reported,
  live runtime 집계. 검증된 회계 규칙을 그대로 채택(재구현 안 함). (grounding, SPEC §13.5.)
- **D-4 additive 스냅샷, backward-compat.** recent[].tokens/session, run.codex_totals/rate_limits;
  기존 reader/테스트/NoopStatusWriter 불변. (자율.)
- **D-5 usage 이벤트 shape 는 live-pin(ExecPlan PoC), tolerant extractor None-when-absent.**
  agentMessage 가 codex-cli 0.139.0 에 pin 된 것과 동형; 프로토콜 변동 시 조용히 degrade. (자율.)
- **D-6 telemetry 는 절대 gate 아님.** 추출/누적 실패 swallow — status.py R3 "visibility never
  blocks dispatch" 의 telemetry 판. (자율.)
- **D-7 url deep-link 조건부/deferrable.** ticket 모델이 url 을 안 나르면 이 필드만 defer(날조
  금지). (자율.)

## Open Questions

- **codex usage notification 의 정확한 method/필드명** — ExecPlan PoC 로 live-pin(agentMessage→
  codex-cli 0.139.0 처럼). 1차는 tolerant 매칭 + mock.
- **ticket 모델이 `url` 을 나르나** — board/linear 확인; 안 나르면 url 필드 defer(R7).
- **per-turn(터미널 대비) in-flight 토큰 가시성** — boundary v1 은 터미널; per-turn push 는 Layer 2.
- **rate_limits payload shape** — codex-specific; 최신 raw 보관, presentation 은 후속.
