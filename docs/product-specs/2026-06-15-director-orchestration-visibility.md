---
status: draft
last_verified: 2026-06-15
owner: harness
---
# Director 오케스트레이션 가시성 → 인라인 taste-vs-handle escalation

Phase 4 (자율 Director) 의 **두 번째 슬라이스**. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(로드맵 Phase 4). 직전 슬라이스
[Worker authority guardrail](2026-06-14-worker-authority-guardrail.md) 가 열어둔 seam —
default-deny 의 `reason` 을 Director 승인으로 올리는 "escalate-to-Director" 경로(D-24,
그 spec 의 Open Question) — 을 이 슬라이스가 닫는다. 동시에 부모 spec 의 Open Question
"taste-vs-handle 경계의 구체적 정책(무엇을 사람에게 올리나)" 을 해소한다.

**재슬라이싱(사람, 이 세션).** 부모 로드맵의 Phase 4 순서는 guardrail → *taste-vs-handle
escalation policy* → *loop/scheduled oversee + reporting* → PR-merge 였다. 이 슬라이스는
escalation policy 슬라이스를 **가시성 우선(visibility-first)** 으로 다시 잡으면서, 다음
슬라이스의 *read/reporting 표면* 만 앞으로 당겨온다(자율 loop/scheduling 자체는 여전히
다음 슬라이스). 이유는 Problem 이 보여준다: escalation 판단의 품질은 정책 문장이 아니라
Director 가 보는 **상황 그림**에 달려 있다.

## Problem (오늘 무엇이 불만족인가 — observable)

Director 는 별도 daemon 이 아니라 사람이 대화하는 그 Claude Code 세션이고(D-5), 워커의
비-taste 질문을 인라인으로 흡수하며 taste 만 사람에게 올린다(부모 RV2, PRODUCT_SENSE
escalation rule, AGENTS.md "Escalate only on judgment"). 그런데 **그 인라인 판단을 떠받칠
오케스트레이션 read 표면이 repo 에 없다.**

관찰 가능한 사실:
- 오케스트레이터(`director/orchestrator.py`)는 **별도 프로세스**(`python -m
  director.orchestrator`)로 돌면서 풍부한 상태를 계산한다 — `_dispatch_wave` 의
  `in_flight` 집합과 `attempts` 맵, `run_until_drained` 의 `passes`·`stuck`(blocker 별
  `state_type` 포함)·per-ticket `results`(completed/failed/retried/claim_failed). 그러나
  이 상태는 **stdout 으로 print 되고 프로세스 종료와 함께 사라진다**(`main`, orchestrator.py
  의 `print(json.dumps(...))` 라인들). 중간에 질의 가능한 영속 표면이 **전혀 없다**.
- Director(메인 세션)가 읽을 수 있는 것은 둘뿐이다: **board**(`director/board/linear.py` —
  이슈 state/comment; eventually-consistent 하지만 coarse: "In Progress" 는 보여도 "wave 2,
  attempt 2, 4분째, 형제 DEMO-4 도 실행 중" 은 못 봄)와 **요청 큐**(`director_min.pending()`
  — 각 요청은 `{request_id, ticket_id, session_id, kind, payload, workspace_path}` 로 고립돼
  있어 `ticket_id` 는 있지만 그 티켓을 **둘러싼 오케스트레이션 맥락**은 없음).

결과: 워커가 mid-turn 에 approval/input 요청(또는 guardrail 의 default-deny reason)을
Director 큐로 올리면, Director 는 **맥락에 눈먼 채** 답한다 — 이 티켓이 몇 번째 wave·attempt
인지, 지금 무엇이 같이 돌고 있는지, 이 티켓이 이미 한 번 실패했는지, 런이 stuck 인지/왜인지를
보지 못한다. 바로 그 맥락이 **기계적 답("응, 테스트 돌려")** 과 **taste escalation("이 티켓은
두 번 실패한 끝에 데이터를 지우려 한다 — 사람")** 을 가르는 정보다. 가시성이 없으면 인라인
판단(D-5)은 under-informed 이고, escalation 시 사람에게 주는 리포트도 충실할 수 없다.

핵심: escalation **정책**이 얇아도 되는 이유는 Director 가 이미 taste 경계를 안다는 데 있다
(PRODUCT_SENSE). 모자란 건 **그 경계를 잘 적용할 상황 그림**이다. 그래서 이 슬라이스는
가시성을 만들고, 정책은 그 위 얇은 guideline 으로 얹는다.

## Requirements (R1..R9 — 각 항목 사람이 검증 가능)

- **R1 — 영속 status 스냅샷.** 오케스트레이터는 의미 있는 전이마다(claim · dispatch ·
  terminal reconcile · wave 경계 · stuck · run 종료) **현재 상태 스냅샷**을 디스크에
  기록한다. 스냅샷은 in-flight 티켓(phase/attempt/wave/started_at), 최근 종료 결과의 bounded
  tail, stuck 리스트(blocker 별 state_type), run-level(시작/현재 pass/stopped_reason)을 담는다.
  (검증: `--mock` 멀티-티켓 런 도중 파일을 읽으면 in-flight 가, 종료 후 읽으면 stuck +
  recent 가 보인다.)
- **R2 — torn-read 불가(atomic).** 스냅샷 쓰기는 write-temp + `os.replace` 로 원자적이다 —
  쓰는 중에 읽는 Director 는 절대 깨진 JSON 을 보지 않는다(RELIABILITY 의 mark-before-act /
  atomic write grain). (검증: 쓰기와 인터리브된 읽기가 항상 valid JSON; 또는 temp→rename 경로
  단언.)
- **R3 — writer 는 injectable, 기본 on, off 시 동작 불변.** status writer 는 오케스트레이터에
  주입되며(`tool_executor`/`http_post`/`decide` 와 같은 DI grain), 라이브러리 함수 기본은
  no-op(테스트가 디스크 없이 결정적), `main` 이 실제 writer 를 기본 on 으로 구성한다. writer 가
  off 일 때 오케스트레이터의 dispatch/reconcile/요약 출력은 **byte-identical** 이다 — 가시성은
  read-only 계측이지 제어 흐름 변경이 아니다. (검증: writer on/off 두 런의 per-ticket summary
  가 동일.)
- **R4 — Python read-API.** Director(메인 세션)가 스냅샷을 구조화해 읽는 `read_status()` 가
  있다. 파일 부재/부분 기록 시 None/안전 기본값을 돌려준다(런이 아직 없거나 끝난 상태도 합법).
  (검증: 스냅샷 유무 양쪽에서 호출이 합리적 값을 반환.)
- **R5 (핵심) — 요청↔오케스트레이션 join.** 큐 요청 하나를 그 티켓의 오케스트레이션 entry 로
  잇는 `context_for(request)` 가 있다: 해당 티켓의 in-flight entry(phase/attempt/wave),
  **함께 도는 형제 티켓**, **이 티켓의 직전 종료 결과**(예: 이전 attempt 의 fail), run-level
  stuck. 큐 요청 스키마는 바꾸지 않는다 — 스냅샷이 join 의 단일 진실원이다. (검증: 스냅샷 +
  pending 요청을 seed 하면 join 된 맥락이 wave/attempt/형제/직전-실패를 담아 나온다.)
- **R6 — 통신 surface = 스킬.** 메인 Claude 세션이 이 그림을 **실제로 끌어 쓰는** 에이전트-
  facing 표면이 있다(스킬 — Python read-API 를 호출). 스킬은 *언제/어떻게* Director 가 그림을
  참조하고(큐 요청에 답하기 전, oversee 중, 사람 리포트 작성 시) 아래 guideline 을 적용하는지를
  규정한다. (검증: 스킬 문서가 read-API 호출 + guideline 적용 절차를 담는다.)
- **R7 — 얇은 taste-vs-handle guideline.** multi-agent 세팅용 escalation 경계를 PRODUCT_SENSE
  의 escalation rule 에 정박해 명시한다: **handle-inline**(기계적/문서화된 답 — guardrail·docs
  가 이미 정한 것, 재시도로 풀릴 mechanical 실패, ticket-type 에 routine 한 승인) vs.
  **escalate**(docs 가 안 덮는 product-direction/taste 포크, 워커 guardrail 너머의 비가역/
  outward-facing, 그리고 **오케스트레이션 맥락이 드러내는 패턴** — 반복 실패 끝의 비정상 요청,
  stuck 을 강제 돌파하려는 요청). **fail-safe 기본: taste 여부가 진짜 불확실하면 escalate.**
  이 판단은 인라인 Director 가 따르는 guideline 이지 별도 프로세스가 아니다. (검증: guideline
  문서가 결정 규칙 + 맥락의 역할 + worked example 을 담고, 같은 요청이 고립 시 handle 이지만
  패턴 속에선 escalate 임을 보인다.)
- **R8 — `decide` 콜러블은 unattended/test seam 으로만 유지.** `director_min.auto_respond` 의
  `decide` 는 그 docstring 대로 unattended 런/테스트 전용이며 production escalation 판단을
  대체하지 않는다. 이 슬라이스는 `decide` 를 production 헤드리스 judge 로 승격시키지 않는다
  (D-30). (검증: director_min docstring/계약이 그대로, real 경로는 인라인 메인 세션 + 스킬.)
- **R9 — 보안: 새 live exec surface 없음.** status 표면은 오케스트레이터가 쓰고 Director 가 읽는
  **로컬 read-only 파일**뿐 — outward-facing 동작도, 사람 키 사용도 없다. 따라서 이 슬라이스는
  SECURITY.md 에 새 위협/ live-surface 항목을 **추가하지 않으며** 완료 게이트가 review-security
  를 돌지 않는다(AGENTS.md §5 / SECURITY.md status 노트: live surface 만 security review).
  (검증: SECURITY.md 무변경 정당화가 이 spec 에 기록됨; 추가된 코드가 네트워크/키 사용 없음.)

## Design

### 경계의 위치와 형태

가시성은 **read-only 계측**이다 — 오케스트레이터의 dispatch/reconcile/DAG/concurrency
의미를 건드리지 않고(R3), 이미 존재하는 전이 지점에 스냅샷 쓰기 한 줄을 끼운다. Director 의
read 측은 기존 큐 dir 계열의 영속 표면 + 메인 세션이 그걸 끌어 쓰는 스킬이다. 새 블로킹 경로
없음, 새 권한 없음.

### 구성요소 / 파일

**신규 `director/status.py` — status 표면(스키마 + atomic write + read-API + join).**
큐 모듈(`director/queue`)과 같은 결의 순수 I/O 모듈.
- **스냅샷 스키마**(`.claude/harness/director-status/status.json`):
  ```
  {
    "run":       {"started_at": <iso>, "pass": <int>, "stopped_reason": <str|null>},
    "in_flight": [{"ticket_id", "identifier", "phase": "claimed"|"running"|"retrying",
                   "attempt": <int>, "wave": <int>, "started_at": <iso>}],
    "recent":    [{"ticket", "status": "completed"|"failed"|"claim_failed",
                   "final_state", "attempts": <int>}],   // bounded tail (last N)
    "stuck":     [{"ticket", "blocked_by": [{"id", "state_type"}]}],
    "updated_at": <iso>
  }
  ```
- `class StatusWriter` (또는 동등 함수군) — 전이 이벤트를 받아 in-memory 모델을 갱신하고
  `status.json` 을 **atomic**(temp 파일 write → `os.replace`)으로 재기록(R1/R2). 메서드는
  오케스트레이터의 전이에 대응: `claimed(ticket, wave, attempt)`, `dispatched(ticket)`,
  `terminal(ticket, summary)`, `wave(pass_no)`, `stuck(list)`, `finished(stopped_reason)`.
  `recent` 는 마지막 N(예: 20)으로 bound — cross-run 히스토리/메트릭 아님(Non-goal).
- `NoopStatusWriter` — 모든 메서드 no-op. 라이브러리 함수 기본값(R3, 결정적 테스트).
- `read_status(base=None) -> dict | None` — 스냅샷 parse; 부재/부분 기록 시 None(R4).
- `context_for(request: dict, base=None) -> dict` — 요청을 `ticket_id` 로 스냅샷에 join(R5):
  ```
  {"ticket": <in_flight entry | null>,
   "siblings_in_flight": [<다른 in_flight entries>],
   "recent_for_ticket": [<recent 중 같은 ticket 의 직전 결과>],
   "run": {...}, "stuck": [...]}
  ```
  이것이 "context 주입기" — bare 요청을 오케스트레이션 그림으로 감싸 Director 가 in-situ 판단.

**수정 `director/orchestrator.py` — injectable writer 결선(R1/R3).**
- `_dispatch_wave`·`run_until_drained` 에 `status=None` 키워드 추가; None → `NoopStatusWriter`.
- 전이 콜백 삽입: `claim` 성공 직후 → `status.claimed(...)`; `submit` → `status.dispatched(...)`;
  `reconcile` 종료 outcome → `status.terminal(...)`; retry 재제출 → attempt 증가 반영;
  `run_until_drained` 의 각 poll → `status.wave(passes)`, stuck 검출 → `status.stuck(...)`,
  종료 → `status.finished(stopped_reason)`. 모든 콜백은 dispatch 결과에 영향 없음(R3).
- `main` 이 실제 `StatusWriter` 를 기본 on 으로 구성, `--no-status` 로만 opt-out.

**신규 스킬 `.claude/skills/director-oversight/SKILL.md` — 통신 surface + guideline(R6/R7).**
(배치 확정, ExecPlan: 이 스킬은 director/ 서브시스템 특정 = host app-code 라 portable
`plugin/skills/` 가 아니라 **host guide-skill** `.claude/skills/` 에 산다 — ARCHITECTURE
invariant 7. 따라서 S6 lint(plugin/skills 만 스캔) 범위 밖이고, gitignore 는 `.claude/harness/`
만 제외하므로 정상 추적된다.)
- 메인 Claude 세션용: 큐 요청에 답하기 전 `director.status.context_for(req)` 를 부르고,
  oversee/리포트 시 `read_status()` 를 부르는 절차.
- **얇은 taste-vs-handle guideline**(PRODUCT_SENSE escalation rule 에 정박):
  - **Handle inline** — 답이 기계적이거나 문서화돼 있음: guardrail·docs 가 이미 정한 승인,
    재시도로 풀릴 mechanical 실패(오케스트레이터 retry-once 에 맡김), ticket-type 에 routine 한
    sandbox 내 command/file 승인, doc 에서 답이 도출되는 input 질문.
  - **Escalate(taste)** — product-direction/taste 포크(요청이 settled 방향의 *실행*이 아니라
    방향 *선택*을 요구), 워커 guardrail 너머의 비가역/outward-facing(allowlisted 라도 실세계
    비가역 효과는 사람이 소유 — publish/merge/외부 state 삭제), 그리고 **맥락이 드러내는 패턴**:
    이미 실패/retry 한 티켓이 비정상·파괴적 요청을 냄, 런이 stuck 인데 요청이 blocker 를 강제
    돌파하려 함, 형제들이 systemic 문제를 드러냄. (가시성의 값: 같은 요청이 고립 시 handle 이나
    패턴 속에선 escalate.)
  - **Fail-safe 기본:** taste 여부가 진짜 불확실하면 escalate. 사람 시간은 희소하지만, 잘못된
    자율 taste 결정이 한 번의 escalation 보다 비싸다. 이것은 guardrail 의 fail-closed 에 대응하는
    **판단-측 fail-safe** 다 — 단, 별도 프로세스가 아니라 인라인 Director 의 추론 안에 산다.

**무수정(의도) `director/director_min.py`.** `pending`/`answer` 계약과 `decide`(unattended/
test seam) 그대로(R8). 메인 세션은 스킬을 통해 `context_for` 를 참조해 답을 결정한다 —
director_min 에 판단 로직을 심지 않는다.

**테스트** `tests/test_director_status.py`(신규): atomic write(temp→replace, torn-read 없음),
read_status(부재/정상), `context_for` join(형제·직전-실패·stuck), writer on/off 동등성.
`tests/test_director_orchestrator.py`(보강): `--mock` 멀티-티켓(강제 fail+retry, stuck/blocked
포함) 런이 기대 스냅샷을 남기고, status off 시 summary byte-identical.

### 에러 / 경계 케이스

- 스냅샷 부재(런 시작 전/직후) → `read_status` None, `context_for` 는 ticket=null + 빈 형제로
  graceful(R4). Director 는 "오케스트레이션 정보 없음"을 그림의 일부로 받아 판단.
- writer 쓰기 실패(디스크/권한) → 가시성은 best-effort: 예외를 삼켜 로그만 남기고 dispatch 를
  **절대** 막지 않는다(R3 의 read-only 계측 원칙; board 쓰기 best-effort 와 같은 grain).
- 동시 read/write → atomic replace 가 보장(R2). reader 는 lock 불필요.
- stuck/None state_type → 부모 `run_until_drained` 가 이미 not-done blocker 를 추려 stuck 에
  담으므로(orchestrator.py) 그 shape 를 그대로 스냅샷에 흘린다.
- 멀티 워커 동시 terminal → writer 는 오케스트레이터 단일 프로세스의 메인 루프(`wait(...
  FIRST_COMPLETED)`)에서 순차 호출되므로 in-memory 모델 갱신에 race 없음(워커는 thread pool 이나
  reconcile/콜백은 메인 스레드).

## Non-goals (scope fence — YAGNI)

- **헤드리스 escalation judge.** escalation 을 위한 별도 `claude -p` 프로세스를 만들지 않는다.
  판단은 인라인 메인 세션이 한다(D-5/D-30). 헤드리스는 좁고 stateless 한 *classifier*(imprint,
  guardrail 의 GraphQL op 분류기)의 도구지 넓고 맥락-풍부한 *judgment* 의 도구가 아니다.
- **판단-층 입력 demarcation / prompt-injection 방어(구 T6/T7).** prompt injection 은 AI 에이전트
  보안 커널이 막는다고 가정(사람, 이 세션). 인라인 Director 는 워커 요청 raw 콘텐츠를 신뢰
  맥락으로 읽는다. 하드 경계는 결정적 guardrail(T10)이지 판단 층이 아니다(D-35).
- **워커 측 context map / 탐색.** codex 워커가 배정 이슈를 위해 어떤 컨텍스트를 탐색할지 주입하는
  thin context map 은 후속(사람, 이 세션 — "지금은 아님")(D-36).
- **자율 un-watched / scheduled oversee 루프.** 이 슬라이스는 Director 에게 *그림*(read 표면)을
  준다. 그 그림을 주기적으로 폴링하는 자율 loop/scheduling 은 다음 슬라이스. 이 슬라이스는
  watched/메인-세션 Director 가 지금 바로 쓸 수 있다.
- **라이브 dashboard / TUI / web observability.** 표면은 스냅샷 파일 + read-API + 스킬뿐. UI 는
  Phase 5(observability surface).
- **Cross-run 히스토리 / 메트릭 영속.** 스냅샷은 현재 런; `recent` 는 bounded tail. durable
  analytics·별도 append-only event-log 파일 없음(필요해지면 후속).
- **사람에게 push/notification 채널.** Director 는 세션 내에서 surface 한다 — 외부 알림 채널
  없음(범위 밖).
- **오케스트레이터 제어 흐름/concurrency/DAG 의미 변경.** 가시성은 read-only 계측; dispatch 동작
  byte-identical(R3).

## Acceptance criteria (spec 만족의 demonstrable 조건)

- `--mock` 멀티-티켓 런(강제 fail+retry 한 건, stuck/blocked 한 건 포함)이 `status.json` 을
  남기고: 런 도중 읽으면 in-flight 가 phase/attempt/wave 와 함께, 종료 후 읽으면 stuck(blocker
  reason) + recent terminal outcomes 가 보인다(R1).
- 쓰기와 인터리브된 읽기가 항상 valid JSON(torn-read 없음); 쓰기 경로가 temp→`os.replace`(R2).
- status writer on/off 두 런의 per-ticket summary 출력이 byte-identical(R3).
- `read_status()` 가 스냅샷 유무 양쪽에서 합리적 값(정상 dict / None)을 반환(R4).
- 스냅샷 + pending 요청을 seed 하면 `context_for(req)` 가 그 티켓의 wave/attempt + 형제 in-flight
  + 직전 fail + stuck 을 담아 반환(R5).
- 스킬 문서가 read-API 호출 시점 + taste-vs-handle guideline + worked example(고립 handle /
  패턴 escalate)을 담는다(R6/R7).
- director_min 의 `decide` 가 unattended/test seam 으로 유지되고 real 경로는 인라인 메인 세션 +
  스킬(R8). 헤드리스 judge 없음.
- SECURITY.md 무변경(새 live exec surface 없음) — 이 spec 에 정당화 기록(R9).
- 부모 spec 의 Phase 4 "taste-vs-handle" Open Question 과 guardrail spec 의 "escalate-to-Director
  경로" Open Question 이 이 spec 으로 해소·링크됨.
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log (수렴 결정 + 근거)

- **D-30 Judge = 인라인 Director, 헤드리스 프로세스 아님.** escalation 결정은 사람이 대화하는
  메인 Claude 세션(D-5)에 산다 — 별도 `claude -p` judge 없음. 근거: 격리는 *좁고 stateless 한
  classifier*(imprint, guardrail GraphQL op 분류기 — untrusted 입력 위)에 맞고, *넓고 맥락-풍부한
  judgment* 에게선 판단을 좋게 만드는 바로 그 맥락을 굶긴 뒤 재직렬화 비용까지 물린다. 두 층:
  결정적 fail-closed guardrail(코드) vs. 확률적 fail-safe judgment(인라인). (사람 결정, 이 세션.)
- **D-31 Substance = 오케스트레이션 가시성; policy = 그 위 얇은 guideline.** Director 는 이미 taste
  경계를 안다(PRODUCT_SENSE); 모자란 건 라이브 상황 그림이다. 그래서 이 슬라이스는 read 표면을
  만들고 짧은 guideline 을 얹는다 — decision engine 이 아니라. (사람, 이 세션.)
- **D-32 Status 표면 = 단일 atomic 스냅샷(+ bounded recent tail), 하네스 status dir, injectable
  writer.** 스냅샷이 "지금 무엇이 참인가"(요청을 맥락 속에서 판단하는 데 Director 가 필요로 하는
  것)를 답하고, bounded tail 이 가벼운 리포팅을 덮는다 — 별도 event-log 파일/DB 없음(YAGNI).
  injectable 로 DI grain 유지 + 결정적 테스트; 기본 on(real), None=off. write-temp→replace 로
  torn-read 없음(RELIABILITY).
- **D-33 Director read = Python read-API + 스킬(통신 surface).** 스킬이 에이전트-facing 표면(메인
  세션이 *언제/어떻게* 그림을 참조하고 guideline 을 적용하는지)이고 Python 이 메커니즘. layer
  law(scripts 위 skills)와 D-5(표면은 메인 세션을 *위한* 것)에 정합.
- **D-34 요청↔오케스트레이션 join 은 참조로, payload 복제 아님.** 큐 요청은 기존 스키마(`ticket_id`)
  유지; read-API 가 스냅샷에 join. 근거: 오케스트레이션 상태의 단일 진실원, 요청은 thin 유지,
  Phase 1 큐 계약 churn 없음.
- **D-35 판단-층 입력 demarcation 폐기(구 T6/T7).** prompt injection 은 에이전트 보안 커널이
  처리한다고 가정(사람, 이 세션); 인라인 Director 는 워커 요청 raw 콘텐츠를 신뢰 맥락으로 읽는다.
  하드 경계는 결정적 guardrail(T10)에 남고 판단 층엔 없다. 이 슬라이스는 새 live exec surface 가
  없어 SECURITY.md 에 위협을 추가하지 않는다(read-only 로컬 파일).
- **D-36 워커 context 탐색 연기.** thin 워커-측 context map 은 후속 가능; 이 슬라이스 아님(사람,
  이 세션).
- **D-37 escalation policy 슬라이스를 visibility-first 로 재슬라이싱.** 부모 로드맵의 *taste-vs-
  handle escalation policy* 슬라이스를 가시성 우선으로 다시 잡고, 다음 슬라이스의 read/reporting
  표면만 앞으로 당김(자율 loop/scheduling 은 여전히 다음). 근거: 정책 품질이 상황 그림에 종속
  (Problem). (사람, 이 세션.)

## Open Questions

- ~~스킬 정확한 이름/배치~~ → **해소(ExecPlan):** host guide-skill
  `.claude/skills/director-oversight/SKILL.md`(host app-code 특정, layer law / ARCHITECTURE
  invariant 7). guideline 은 스킬 본문에 산다(별도 docs/ 룰 불필요 — 얇음).
- status 표면 위치: `.claude/harness/director-status/` vs 기존 `director-queue/` 하위. 사소 —
  ExecPlan/RELIABILITY 가 확정.
- **자율(un-watched) scheduled Director loop 가 오는 다음 슬라이스**에선 사람이 지켜보지 않는
  상태로 Director 가 행동하므로 security review 가 필요할 수 있다. 이 슬라이스는 사람을 loop 안에
  유지(watched/메인 세션)하므로 그 review 없이 출하 가능 — 다음 슬라이스에서 재평가.
- `recent` tail 길이 N 의 기본값(20 가정) — 실제 oversee/리포트가 요구하는 깊이로 ExecPlan 에서
  조정.
