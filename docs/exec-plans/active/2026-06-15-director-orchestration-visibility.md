---
status: active
last_verified: 2026-06-15
owner: harness
base_commit: 733c0b5c4c0eee3276c9361be997a479f939ed77
review_level: standard
---
# Director 오케스트레이션 가시성 → 인라인 escalation — build

## Goal
오케스트레이터가 in-memory 로만 갖던 런 상태(in-flight·attempt·wave·stuck·recent
outcomes)를 디스크의 **atomic 스냅샷**으로 영속화하고, Director(메인 Claude 세션)가
Python read-API + 스킬로 그 그림을 끌어 쓴다. 관찰 가능한 done: `--mock` 멀티-티켓 런(강제
fail+retry 한 건 + stuck/blocked 한 건 포함)이 `.claude/harness/director-status/status.json`
을 남기고 — 런 도중 읽으면 in-flight 가 phase/attempt/wave 와 함께, 종료 후 읽으면
stuck(blocker reason) + recent terminal outcomes 가 보인다. `director.status.context_for(req)`
가 pending 큐 요청을 그 티켓의 오케스트레이션 entry(wave/attempt/형제/직전-실패/stuck)로
join 한다. status writer 를 끄면 오케스트레이터 per-ticket summary 출력이 **byte-identical**
이다(가시성은 read-only 계측). 새 스킬이 메인 세션에게 *언제* 그림을 읽고 taste-vs-handle
guideline 을 적용하는지 규정한다. `python3 plugin/scripts/check.py` GREEN.

## Context
- Spec(설계 소유, 재유도 금지):
  `docs/product-specs/2026-06-15-director-orchestration-visibility.md`
  — Problem, R1–R9, Design(status.py 스키마·orchestrator 결선·스킬), Non-goals, Acceptance,
  D-30..D-37. 이 plan 은 그 spec 의 **build** 만 소유한다.
- 부모: `docs/product-specs/2026-06-14-symphony-director-orchestration.md`(Phase 4, D-5).
  직전 슬라이스: `docs/product-specs/2026-06-14-worker-authority-guardrail.md`(이 spec 이
  그 escalate-to-Director seam 을 닫음).
- 현 코드:
  - `director/orchestrator.py` — `_dispatch_wave`(`in_flight` 집합·`attempts` 맵·`submit`/
    reconcile 루프), `run_until_drained`(`passes`·`stuck`·`results`), `main`(상태를 stdout
    print 후 버림). **여기에 injectable status writer 결선.** reconcile/전이는 메인 스레드의
    `while futures: wait(... FIRST_COMPLETED)` 루프에서 순차 실행(워커는 ThreadPool, 콜백은
    메인 스레드 → status 모델 갱신에 lock 불요).
  - `director/director_min.py` — `pending()`/`answer()` + `decide`(unattended/test seam,
    docstring 이 명시). **무수정**: 판단 로직을 심지 않는다(R8).
  - `director/queue/` — 요청/answer JSONL I/O(harness atomic write 패턴). status 표면은 그
    옆 `.claude/harness/director-status/` 에 산다(큐 계약 불변, D-34).
  - `director/board/linear.py` — Director READ adapter(coarse: state/comment 만; wave/attempt
    없음 — 그래서 status 표면이 필요).
- 게이트: `python3 plugin/scripts/check.py`(structure/docs lint + 216 tests; 신규 스킬은
  lint_structure 통과 필요).
- 용어: **snapshot** = "지금 무엇이 참인가"를 한 번의 parse 로 답하는 단일 JSON 파일(append-only
  event-log 아님). **in-flight** = claim 됐고 아직 terminal 이 아닌 티켓. **wave** =
  `run_until_drained` 의 re-poll pass 번호. **join(`context_for`)** = bare 큐 요청을 `ticket_id`
  로 스냅샷에 이어 오케스트레이션 맥락을 입히는 read 측 함수(= spec 의 "context 주입기").
  **behavior-neutral** = writer off 시 dispatch/reconcile/summary 출력이 byte-identical.

## Approach (self-generated alternatives)
- A: **단일 atomic 스냅샷 + injectable writer + read-API/스킬**(spec D-32 채택). 오케스트레이터
   전이마다 in-memory 모델을 갱신해 `status.json` 을 temp→`os.replace` 로 원자적 재기록;
   Director 는 `read_status`/`context_for` 로 읽음. — 최소 변경, DI grain(`tool_executor`/
   `http_post`) 일치, "지금" 을 한 번에 답함, behavior-neutral 보장 쉬움.
- B: **append-only JSONL event-log 을 Director 가 tail.** 풍부한 히스토리, 그러나 매 read 마다
   이벤트를 fold 해 current in-flight 를 재유도해야 하고, 부분 라인/torn-read 를 매번 처리.
   "지금 상태" 질의가 비싸짐. — A 의 bounded `recent` tail 이 히스토리 필요를 per-read fold
   없이 덮음.
- C: **오케스트레이터가 HTTP/IPC 엔드포인트로 상태 노출, Director 가 질의.** 라이브하지만 서버/
   포트/lifecycle 추가. 부모 spec 이 Director seam 을 네트워크 위에 얹는 것을 명시적으로 거부
   (symphony D-2: HTTP 층은 resume 불가/over-built). 단일-프로세스 로컬 하네스에 과대.
- **Chosen: A** — spec D-32 미러. B 의 히스토리는 A 의 `recent` tail 로, C 의 라이브성은 로컬
  파일 + 메인 세션 read 로 충분. YAGNI + 로컬-파일 grain.

## Assumptions & open questions (self-interrogation)
- Assumption: orchestrator 의 reconcile/전이 콜백은 **메인 스레드**에서 순차 실행된다
  (`_dispatch_wave` 의 `while futures: wait(...)` + reconcile 가 메인; 워커만 ThreadPool) →
  status in-memory 모델 갱신에 lock 불요. 틀리면(콜백이 워커 스레드에서) lock 추가. [orchestrator.py
  코드로 확인됨 — reconcile 는 메인 while 루프.]
- Assumption: 동일 파일시스템에서 temp→`os.replace` 가 POSIX rename 원자성으로 torn-read 를
  막는다(temp 를 같은 dir 에 생성). 표준 보장.
- Assumption: `recent` tail 기본 N=20 이 oversee/리포트 깊이로 충분(spec Open Question) → 상수
  한 줄로 fix-forward.
- Open: status dir 위치(`.claude/harness/director-status/` vs `director-queue/` 하위) → **자율
  해소: 별도 `director-status/`** (큐 계약을 더럽히지 않음; D-34). Decision log 기록.
- Open: 스킬 이름/배치 + guideline 이 스킬 본문 vs 짧은 docs/ 룰 → **M3 에서 `docs-tree` 스킬로
  자율 확정**(human ask 아님).
- Open(taste 만 escalate): 없음 — 여기의 모든 포크는 mechanical/design 이고 spec 에서 이미
  확정. 사람 escalation 없음.

## Milestones

- **M1 — status 표면 모듈(순수, 단위 검증).** `director/status.py` 신규: 스냅샷 스키마,
  `StatusWriter`(전이 메서드 `claimed`/`dispatched`/`terminal`/`wave`/`stuck`/`finished` 가
  in-memory 모델 갱신 → temp→`os.replace` atomic 재기록; `recent` 는 마지막 N bound),
  `NoopStatusWriter`(모든 메서드 no-op, 라이브러리 기본값), `read_status(base=None)`(부재/부분
  기록 시 None), `context_for(request, base=None)`(ticket_id 로 join → ticket entry·
  siblings_in_flight·recent_for_ticket·run·stuck). 끝에 존재: `tests/test_director_status.py`
  — atomic write(쓰기/읽기 인터리브가 항상 valid JSON; temp→replace 경로), read_status(부재→
  None / 정상→dict), `context_for` join(형제·직전-fail·stuck 을 담음), writer on→파일 생김/
  Noop→파일 없음. run: `python3 -m pytest tests/test_director_status.py -q`. expect: 전부 PASS,
  스냅샷 round-trip, join 이 맥락을 정확히 입힘.

- **M2 — 오케스트레이터 결선(behavior-neutral 계측) + end-to-end join.** `director/orchestrator.py`
  수정: `_dispatch_wave`·`run_until_drained` 에 `status=None`(→`NoopStatusWriter`) 추가;
  전이에 콜백 — claim 성공 직후 `status.claimed(ticket, wave, attempt)`, `submit` →
  `status.dispatched`, reconcile terminal → `status.terminal(ticket, summary)`, retry 재제출 →
  attempt 증가, 각 poll → `status.wave(passes)`, stuck 검출 → `status.stuck(list)`, 종료 →
  `status.finished(stopped_reason)`. writer 쓰기 실패는 삼켜 로그만(dispatch 절대 안 막음).
  `main` 이 실제 `StatusWriter` 기본 on 구성 + `--no-status` opt-out. 끝에 존재: `--mock`
  멀티-티켓(강제 fail+retry + stuck/blocked) 런이 기대 스냅샷을 남김; **writer off 시 per-ticket
  summary byte-identical**; 실제 스냅샷 + seed 한 pending 요청에 `context_for` 가 wave/attempt/
  형제/직전-fail/stuck 을 입혀 반환(R5 end-to-end). `tests/test_director_orchestrator.py` 보강.
  run: `python3 plugin/scripts/check.py`. expect: GREEN; 스냅샷이 런 도중 in-flight, 종료 후
  stuck+recent; on/off summary 동등.

- **M3 — 소비 표면: 스킬 + 얇은 guideline.** `docs-tree` 스킬로 배치 확정 후 신규 스킬
  (`plugin/skills/<director-oversight>/SKILL.md`): 메인 세션이 큐 요청에 답하기 전
  `director.status.context_for(req)` 를, oversee/리포트 시 `read_status()` 를 부르는 절차 +
  **얇은 taste-vs-handle guideline**(handle-inline: guardrail·docs 가 정한 것·mechanical 실패·
  routine 승인 / escalate: product-direction·비가역 outward-facing·**맥락이 드러내는 패턴** /
  fail-safe: 불확실하면 escalate). worked example ≥1: 같은 요청이 고립 시 handle 이나 패턴
  (두 번 실패한 티켓의 파괴적 요청, stuck 강제 돌파) 속에선 escalate. `decide` 는 unattended/
  test seam 으로 유지(R8) — 스킬이 real 경로. 끝에 존재: lint-clean 스킬 + guideline 문서.
  run: `python3 plugin/scripts/check.py`. expect: GREEN(structure/docs lint 통과), 스킬이
  read-API 호출 시점 + 결정 규칙 + worked example 을 담음.

## Progress log
- [x] (2026-06-15) plan created; base_commit 733c0b5; review_level standard(review-arch +
      review-reliability; security 제외 — spec R9, 새 live exec surface 없음/read-only 로컬 파일).
- [x] (2026-06-15) M1 done. `director/status.py`: `StatusWriter`(claimed/dispatched/retrying/
      terminal/wave/stuck/finished → in-memory 모델 → temp+`os.replace` atomic 재기록),
      `NoopStatusWriter`(`__getattr__` no-op), `read_status`(부재/unparseable→None),
      `context_for`(ticket_id join → ticket/siblings/recent_for_ticket/run/stuck). 큐 모듈의
      atomic-write 결 미러. `tests/test_director_status.py` 11 PASS(인터리브 torn-read 가드 +
      join 의 형제·직전-fail·stuck). 커밋 23d8a06. (227 tests GREEN.)
- [x] (2026-06-15) M2 done. `director/orchestrator.py`: `_dispatch_wave`(`status=None`→Noop,
      `wave` 인자)가 claim→`status.claimed`, submit→`status.dispatched`, retry→`status.retrying`,
      terminal/claim_failed→`status.terminal`; `run_until_drained`(`status` 명시 인자)가
      pass→`status.wave`, stuck→`status.stuck`, 종료→`status.finished`. `main` 이 실제 writer
      기본 on + `--no-status`/`--status-dir` opt-out/override. `tests/test_director_orchestrator.py`
      +6: off→summary byte-identical(R3), mid-run in-flight, stuck+finished 스냅샷, retry attempt
      bump(1→2), `context_for` 가 실 orchestrator 스냅샷을 읽음(R5 e2e), main `--status-dir` 스냅샷.
      기존 MainCliTest 3 은 `--no-status`(opt-out 증명 + repo 오염 방지). check.py GREEN(233).
- [x] (2026-06-15) M3 done. 배치 확정(docs-tree + layer law): 이 스킬은 host 특정(director/
      서브시스템)이라 portable `plugin/skills/` 가 아니라 **host guide-skill** `.claude/skills/
      director-oversight/SKILL.md`(ARCHITECTURE invariant 7). `director/status.py` 에 read CLI
      추가(`python3 -m director.status` / `--request <json>`) — 스킬이 부를 구체 명령(layer
      law: skill 이 script 실행 지시). SKILL.md: read 절차 + 얇은 taste-vs-handle guideline
      (handle/escalate/fail-safe) + join 이 같은 요청을 뒤집는 worked example + D-5/D-30 인라인-
      judge 노트 + `decide`=test-only(R8). `tests/test_director_status.py` +1(CLI dump/join).
      check.py GREEN(234). lint 영향 없음(`.claude/skills/` 는 S6 범위 밖, gitignore 는
      `.claude/harness/` 만).

## Surprises & discoveries

## Decision log
- 2026-06-15: review_level = standard(review-arch + review-reliability). 새 영속 read 표면 +
  DI 결선(arch) + atomic write/behavior-neutrality/best-effort 실패(reliability)가 touched risk.
  **security 제외** — status 표면은 read-only 로컬 파일뿐(네트워크·사람 키 없음), 새 live exec
  surface 아님(spec R9/D-35). PRODUCT_SENSE "throughput beats ceremony" — 과다 review 회피.
- 2026-06-15: status dir = 별도 `.claude/harness/director-status/`(큐 계약 불변, D-34).
- 2026-06-15: 헤드리스 judge 폐기(D-30)는 코드 변경이 아니라 *비추가* — director_min 무수정,
  `claude -p` escalation 경로를 만들지 않음으로써 충족.
- 2026-06-15: 스킬 배치 = `.claude/skills/director-oversight/`(host guide-skill), `plugin/skills/`
  아님. 근거: layer law — `plugin/` 은 portable Machine, 이 스킬은 director/ 서브시스템(host
  app-code) 특정. ARCHITECTURE invariant 7 의 "host guide-skills under `.claude/skills/`". 부수:
  S6 lint(plugin/skills 만 스캔)·gitignore(`.claude/harness/` 만) 영향 없음 → 정상 추적.
- 2026-06-15: 스킬↔read-API seam = `director/status.py` 의 `python3 -m director.status [--request]`
  CLI. 근거: skill 이 ad-hoc `-c` one-liner 대신 구체 명령을 부르도록(layer law: skill→script).

## Feedback (from completion gate)

## Outcomes & retrospective
