---
status: active
last_verified: 2026-06-16
owner: harness
base_commit: a6d8537b392ab298e94663af2b437700f74a7d7e
review_level: standard
---
# 워커 self-QA + 직렬화된 PR-merge (build)

## Goal
워커가 impl 티켓을 **self-QA(spec/code/test) + PR 생성**까지 절차로 끝내고(게이트 아님), 그
PR 이 **직렬화된 merge queue → 단일 PR-merger** 로 하나씩 main 에 랜딩된다. Observable:
1. impl-typed 워커 프롬프트가 QA+PR 절차를 포함하고, `director/workspace_skills/qa/` 스킬이
   smoke/e2e/Playwright 방법론 + 미설치 graceful fallback 을 담는다.
2. `report_outcome(done)` 은 어떤 QA 게이트에도 막히지 않는다(LLM 판단; multi-turn R4 보존).
3. ready 인 PR N개가 **순차로** 랜딩(매번 최신 main rebase→통합 게이트→squash-merge), 절대 동시 아님.
4. 충돌/red/taste 인 PR → merger 가 **Director 로 escalate**(단일 인간 surface), 조용히 머지 안 함.
5. merger 는 새 turn 머신을 안 만들고 `director/run.py::drive` + `director/decider` 를 재사용(diff).
6. `python3 plugin/scripts/check.py` GREEN.

## Context
- **Design owner (먼저 읽기):**
  `docs/product-specs/2026-06-16-worker-qa-and-serialized-pr-merge.md` (R1–R9, D-46..D-53).
  이 plan 은 *build* 만; design 재유도 금지.
- **재사용:** `director/run.py::drive`(multi-turn 루프 — merger 가 호출만, 수정 안 함),
  `director/decider.py`(Director decider / 코드 decider), `director/queue`(요청/답 채널, atomic),
  worker 스킬 `director/workspace_skills/{land,pull,push}`(squash-merge/rebase/PR — gh CLI),
  `director/taxonomy.py`(impl 템플릿), `docs/DIRECTOR.md`(머지 escalation 처리 절 추가 대상).
- **Verified (스펙):** Playwright/e2e 가 워커 샌드박스에서 실행됨(라이브, 이 세션) — e2e 는 워커
  self-QA 에 둔다(D-52). 워커는 홈 `~/.codex/skills` + 워크스페이스 vendored 스킬을 본다.
- **코디네이션:** 병렬 secret-boundary ExecPlan 이 `director/run.py`/`app_server.py`/`policy.py`/
  `SECURITY.md` 를 worktree 에서 다룸. 이 plan 의 편집 대상은 그와 **disjoint**(merger 는 drive 를
  *import* 만). 커밋은 내 경로만 stage; in-flight 파일 편집 회피.

## Approach (self-generated alternatives)
Design 은 스펙이 소유(D-46..D-53) → 여기선 실행 선택만.
- **merger 형태:** A) `director/merger.py` = 직렬 단일-소비자 drain 이 PR 당 `drive(land-agent)` 호출
  (스펙 D-50/D-53). B) 워커-self-merge(기각, D-53). C) mechanical happy-path(deferred, D-53). **A 채택.**
- **merge 신호 경로:** A) 워커가 done+PR 시 `mergeRequest` 를 `director/queue` 에 enqueue(기존 큐 재사용).
  B) 별도 파일 큐. **A 채택**(큐 atomic/idempotent 계약 재사용).
- **merger 기동:** 이벤트-구동(`director.watch` 류로 mergeRequest tail) vs 폴링 drain. **1차 = 단순
  drain 루프**(`run_until_drained` 류); 이벤트-구동은 후속(스펙 Open Q).

## Assumptions & open questions (self-interrogation)
- **Assumption — `drive` 의 public 시그니처가 secret-boundary 작업에도 안정.** merger 는 drive 를
  호출만 하므로 그쪽 `_prepare(env=…)` 내부 변경에 영향 없음. *깨지면:* drive 호출부만 조정.
- **Assumption — `land` 스킬을 쥔 Codex 에이전트가 drive 레인에서 rebase/충돌해소/squash-merge 를
  수행**(스킬이 이미 그 절차). *깨지면:* M4 라이브에서 드러남 → 스킬/프롬프트 보강.
- **Open — 라이브 머지 대상:** 하네스 master 에 실제 PR 을 머지하면 위험 → **M4 는 scratch 로컬
  repo**(두 브랜치, rebase+gate+merge 직렬)로 serializer 메커닉 검증; 전체 gh PR 라운드트립(원격
  필요)은 별도. 자율 결정(비-taste).
- **Open — 티켓 done vs merge 상태:** 워커 done=작업 완료(D-49); 머지는 하류. board 에 "merging"
  상태 안 만들고 1차 진행, reporting 필요 시 재검토.
- **Open — 의존 PR 순서:** FIFO(ready)+매번 최신 main rebase; sibling 미머지로 통합 게이트 fail 이면
  재큐/escalate. M2 에서 확정.

## Milestones

- **M1 — 워커 self-QA 절차 + qa 스킬.** `director/taxonomy.py::_IMPL_TEMPLATE` 를 확장: 구현 뒤
  (a) 호스트 게이트 green, (b) spec/code self-review, (c) task-specific 테스트 작성·실행(UI 면
  `playwright`/`playwright-cli`, 미설치면 smoke/unit fallback), (d) PR 생성+자기명세, 그 다음
  report_outcome(done). 신규 `director/workspace_skills/qa/SKILL.md` (테스트 방법론 + fallback +
  spec acceptance↔테스트 연결). `push` 스킬의 PR body 에 자기명세 템플릿(R2 필드). 끝에 존재:
  impl 프롬프트가 QA+PR 절차를 담고 qa 스킬이 vendored 설치됨. 실행:
  `python3 -m unittest discover -s tests -p "test_director_taxonomy.py"` (+ 새 어서션: 합성된
  impl 프롬프트에 QA/PR 단계 문자열) ; 기대: green, `install_workspace_skills` 가 `qa/` 도 깐다.
- **M2 — 직렬 merge queue + `director/merger.py`.** `director/queue` 에 `mergeRequest` kind +
  enqueue helper. `director/merger.py`: 단일-소비자 drain — queue 에서 PR 하나 pop → `drive` 로
  land-에이전트를 terminal 까지(스펙 R9; 충돌/red/taste turn-end 는 Director decider 로) → 다음.
  단일 소비자라 직렬화 자동(R4). 끝에 존재: merger 가 mock land-에이전트로 N개 PR 을 순차 처리하고
  escalation 을 Director 큐로 라우팅. 실행: `python3 -m unittest discover -s tests -p
  "test_director_merger.py"` ; 기대: N ready → 직렬(동시성 카운터로 ≤1 검증), 충돌 시 escalate
  disposition, 무한 안 돔.
- **M3 — Director 통합 + DIRECTOR.md.** merger escalation 을 Director 가 받는 경로(`mergeReview`
  류 큐 kind 또는 escalate 재사용) + `director_min` helper(필요 시) + `docs/DIRECTOR.md` 머지
  escalation 처리 절. 끝에 존재: 머지 충돌이 Director 큐에 뜨고 Director 가 답/사람escalate. 실행:
  관련 유닛 + `python3 plugin/scripts/check.py` GREEN; 기대: merger→Director 단일 surface(diff 로
  사람 직통 경로 없음 확인, R7).
- **M4 — 라이브 wire-pin(scratch repo).** scratch 로컬 git repo 에 두 브랜치(텍스트 비충돌이지만
  함께 빌드 깨는 케이스 포함) → merger 가 **순차로** rebase+통합 게이트+merge, 하나는 통합 게이트
  red 로 escalate. 끝에 존재: serializer 가 individually-clean-together-broken 을 통합 게이트로
  잡는 transcript(Outcomes 보관). 실행: scratch 스크립트(미커밋); 기대: 순차 머지 + red 케이스
  escalate. (전체 gh PR 라운드트립은 원격 필요 — 별도/후속.)

## Progress log
- [x] (2026-06-16) M1 — `taxonomy._IMPL_TEMPLATE` 에 self-QA(host gate·spec/code self-review·
  task-specific 테스트 via `qa` 스킬·PR+자기명세) 절차 추가(게이트 아님; report_outcome(done) 전).
  신규 `director/workspace_skills/qa/SKILL.md`(테스트 방법론 + Playwright/fallback + PR 자기명세
  템플릿). 테스트: impl 프롬프트가 SELF-QA/qa/PR/report_outcome(done) 담음 + `qa/` 가 vendored
  설치됨. (PR 자기명세는 push 스킬 대신 qa 스킬 + impl 템플릿에 둠 — push 는 generic 유지, 실행 선택.)
- [x] (2026-06-16) M2 — `director/queue` 에 `mergeRequest` kind + `append_merge_request`
  helper(요청을 work-queue 로 재사용 — answer = 소비 마커, request_id `merge|<ticket>` 로
  idempotent). `director/merger.py`: 단일-소비자 `drain` — 오래된 PR pop → land 프롬프트로
  `run.drive`(decider 재사용, D-50) → `classify`(terminal done=merged, 그 외 escalated,
  크래시=failed) → answer 로 소비 → 다음. 직렬화는 루프 구조상 자동(≤1 in-flight), 무한루프는
  "매 아이템 반드시 소비"로 보장(`max_merges` belt-and-suspenders). `director_min.auto_respond`
  가 `mergeRequest` 도 skip(고정정책 responder 가 머지를 조용히 소비 못 하게). 테스트
  9개(FIFO·≤1 동시·escalate/stuck/blocked·크래시=failed·max_merges 바운드·idempotent·
  auto_respond skip·real `run.drive`+mock worker → merged). 게이트 GREEN(286).
  실행: `python3 -m unittest discover -s tests -p "test_director_merger.py"`.
- [ ] M3 — Director 머지 escalation 통합 + DIRECTOR.md.
- [ ] M4 — scratch repo 라이브 직렬-머지 wire-pin.

## Surprises & discoveries

## Decision log
- 2026-06-16: merger 는 `drive`/`decider` 재사용(스펙 D-50/D-53) — run.py 수정 0, secret-boundary
  작업과 disjoint.
- 2026-06-16: M4 라이브는 scratch 로컬 repo(하네스 master 에 실제 머지 안 함) — serializer 메커닉만
  검증, 전체 gh 라운드트립은 후속.
- 2026-06-16 (M2): mergeRequest 는 기존 큐를 work-queue 로 재사용 — 별도 파일 큐 안 만듦. answer
  부재=pending, 머거가 처리 후 answer 작성=소비. 단일 소비자라 직렬화는 자동(락/카운터 불요).
- 2026-06-16 (M2): 머거는 escalate/failed 도 **소비**(answer 작성)해서 1-pass 가 항상 종료 —
  escalation 은 `drain` 반환값으로 surface, Director 재주입/재큐는 M3. (consume-and-surface 가
  무한루프 없이 단일-패스 바운드를 보장하는 선택.)
- 2026-06-16 (M2): enqueue 호출부(워커 done+PR → mergeRequest) 와이어링은 M3(Director 통합)로
  — M2 는 helper 존재 + 머거 drain 만. 머거 decider 기본값=`autonomous_decide`(land 스킬이 충돌
  자체해소; needs_human 만 escalate), watched 는 호출부가 `make_queue_decider` 주입.

## Feedback (from completion gate)

## Outcomes & retrospective
