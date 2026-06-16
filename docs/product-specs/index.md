---
status: stable
last_verified: 2026-06-14
owner: harness
---
# Product specs

- agent-harness v1 design spec: `../superpowers/specs/2026-06-12-agent-harness-v1-design.md`
  — two layers (OpenAI harness-engineering reproduction + memory loop),
  human touchpoints, build phases, success criteria.
- [Product Design 단계 + entry decision](2026-06-14-product-design-phase.md)
  — ExecPlan 앞단의 spec 단계 + 작업 시작 전 세 갈래 entry decision(throwaway /
  Product Design / ExecPlan). methodology spec.
- [Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
  — 티켓 DAG 를 조직 구조로 삼는 multi-agent 개발 능력. Director=Claude Code /
  worker=codex app-server, Symphony 사양 Python 재구현. Phase 1(approval→Director→
  resume seam) 상세 + Phase 2–5 로드맵. (parent)
- [오케스트레이터 — poll→dispatch→reconcile 루프](2026-06-14-orchestrator-dispatch-loop.md)
  — 위 로드맵 Phase 2 후반. ready 티켓을 poll 해 N개 워커에 동시 dispatch, 결과를
  board 로 reconcile 하는 thin·watched 첫 컷. 큐 동시성 안전화 포함.
- [DAG-aware 연속 오케스트레이션](2026-06-14-dag-aware-orchestration.md)
  — Phase 3a. `blocked_by` 를 존중하는 연속 re-poll(wave) 루프: ready 그리고 blocker 가
  전부 done 인 티켓만 dispatch, 완료가 의존을 unblock, 워커-생성 티켓을 집음. board-as-truth,
  cycle/stuck 검출, bounded·watched. (3b dev-stage taxonomy 는 별도.)
- [Dev-stage taxonomy](2026-06-14-dev-stage-taxonomy.md)
  — Phase 3b. 티켓 type(planning/research/design/spec/impl)을 하네스 doc 파이프라인 단계에
  매핑: type→methodology+산출 doc+typed 자식. type=Linear 라벨, prompt 라우팅(순수 함수),
  worker-driven 분해, 3a DAG 가 정렬. 하네스가 자신을 돌리는 typed 티켓 DAG(RV1).
- [Worker authority guardrail](2026-06-14-worker-authority-guardrail.md)
  — Phase 4 첫 슬라이스 + 하드 선행조건. 워커의 `linear_graphql` 를 mutation root-field
  allowlist(default-deny)로 묶는다: reads 무제한, allowlisted forward-only mutation 만 통과,
  파괴적/미지 mutation 은 Linear 로 나가기 전 로컬 거부. 서버 parser 와 정렬된 최소 GraphQL
  분류기. un-watched dispatch 전에 사람 키로 보드를 파괴하지 못하게(tracker line 49, T10).
- [Director 오케스트레이션 가시성 → 인라인 taste-vs-handle escalation](2026-06-15-director-orchestration-visibility.md)
  — Phase 4 둘째 슬라이스. escalation judge = 별도 헤드리스 프로세스가 아니라 인라인 메인
  세션(D-5). 오케스트레이터가 in-memory 로만 갖던 상태(in-flight·attempt·wave·stuck)를 atomic
  스냅샷으로 영속화하고, Director 가 read-API + 스킬로 끌어 쓴다. 요청↔오케스트레이션
  join(`context_for`)이 bare 큐 요청을 상황 그림으로 감싸 인라인 판단을 떠받친다 — 정책은 그 위
  얇은 guideline. guardrail 의 escalate-to-Director seam + 부모의 taste 정책 Open Question 해소.
- [Multi-turn 티켓 실행 — Director-driven continuation + worker-proposed status](2026-06-15-multi-turn-ticket-execution.md)
  — Phase 4. orchestrator 의 "한 턴 → `completed→Done` 코드 매핑"이 틀렸음을 교정: 티켓 하나는
  여러 턴에 걸치고, 턴 종료 ≠ 티켓 완료. 워커가 structured outcome(continuing/done/blocked+children/
  needs_human) 제안 → Director 가 집행·검수(watched) 또는 워커 신뢰·auto-continue(un-watched).
  코드는 done-ness 판단 0. multi-turn continuation feasibility live 검증(2턴/1thread 맥락 유지).
  Phase 2 reconcile 재설계, reporting/PR-merge 보다 선행.
- [워커 self-QA + 직렬화된 PR-merge](2026-06-16-worker-qa-and-serialized-pr-merge.md)
  — Phase 4 꼬리. 워커가 self-QA(spec-compliance + code-quality + task-specific 테스트)를 *절차*로
  끝내고 PR+자기명세를 만든다(하드 게이트 아님 — minimal blocking gates; done 은 LLM 판단 유지).
  done+QA 된 PR 은 *직렬화된 merge queue* 에 들어가 단일 PR-merger 가 하나씩 rebase→얇은 통합 체크
  →squash-merge(`land`); 충돌/위험/taste 만 Director 경유(단일 인간 surface)로 escalate. 동시
  머지 thrash 를 단일 소비자로 제거. merger 는 `drive`+decider 재사용(새 turn 머신 0). multi-turn
  의 미뤄둔 "done-is-really-done" + visibility 의 "terminal sanity-check" 을 닫음. Playwright-in-
  sandbox 실행 가능성은 ExecPlan PoC.
- [Director board reporting (run-level pull)](2026-06-16-director-board-reporting.md)
  — Phase 4 로드맵의 "board 리포팅". 목적 = 사람 attention pull(내구성 기록 아님): unattended
  watched 런이 종료 국면(drained/stuck/max/poll_failed)에 닿으면 `director.watch` 가 status
  스냅샷을 tail 해 `runReport` 이벤트를 emit → event-woken Director 가 `director.status` 로
  digest 를 작성해 `PushNotification` 으로 사람을 끌어들인다. terminal-only emit(중간 조기 pull
  defer), watched 전용, 코드는 리포트-가치 판단 0(DIRECTOR.md 절차). watch + doc 만 — orchestrator
  변경 0.
- [Worker telemetry capture (Symphony-grade) into status.json](2026-06-16-worker-telemetry-capture.md)
  — Phase 5 observability 트랙, **renderer 의 선행**. renderer richness 는 producer state 에
  묶이므로 데이터를 먼저 풍부하게: Symphony 가 추적하는 운영 telemetry(per-ticket 토큰·
  turn_count·session_id, run-level codex_totals·seconds_running·rate_limits; SPEC §4.1.6/
  §4.1.8/§13.5)를 **턴/디스패치 경계**에서 포착해 `status.json` 에 영속. app_server 가 codex
  스트림에서 usage 추출(tolerant, 없으면 None) → drive 가 per-ticket 누적(절대총량, anti-
  double-count) → orchestrator 가 terminal 에서 기록 + run aggregate. status.py 변경은 additive
  (lock-free 단일 writer 유지; 라이브 in-flight accrual = Layer 2 defer). §13.5 회계 규칙 채택.
- [Director observability dashboard (라이브 read-only 웹 뷰)](2026-06-16-director-observability-dashboard.md)
  — Phase 5(optional)의 observability surface. visibility spec 이 미뤄둔 "라이브 dashboard /
  web observability"(line 208)를 회수: 기존 `director.status` 스냅샷 + `queue.read_pending`
  위에 stdlib `http.server` 로 127.0.0.1 read-only 웹 뷰를 얹는다. `GET /api/v1/state` =
  순수 `build_view(status_dir,queue_dir)` JSON(in-flight/stuck/recent/pending + counts),
  인라인 vanilla-JS 페이지가 ~1s 폴로 재렌더. read-only(act 는 Director 경유), 폴링(SSE 아님),
  current-run only, stdlib-only. 기존 모듈 변경 0 — 신규 `director/dashboard.py` + 테스트 +
  DIRECTOR.md 절. (공유 tracker / GitHub Issues 어댑터는 범위 밖.) **재배치(2026-06-16): worker
  telemetry capture 가 선행 — renderer 는 그 풍부해진 데이터의 consumer.**
- [Director 선언적 설정 계약 (`.harness.json` `director` 블록)](2026-06-16-director-declarative-config.md)
  — Symphony 정합 트랙(SPEC §5–6/§6.2, `WORKFLOW.md` 대응). 코드+CLI 플래그에 흩어진
  오케스트레이션 정책(team·states·concurrency·posture·paths·merger knob)을 `worker_policy`
  와 **같은 `.harness.json`** 의 `director` 블록(stdlib json, YAML 아님)으로 외부화 →
  "설정 하나 떨구면 어느 repo 에서나 도는" 하네스. methodology(템플릿/계약)는 코드 유지(D-56);
  precedence CLI>config>default(D-58); `$VAR` indirection; load-once(daemon reload 아님 — D-55,
  episodic 모델); 부재 fail-open / malformed fail-loud(D-57, 첫 워커 spawn 전). 신규
  `director/config.py`(pure, explicit `root=`) + `python3 -m director.config` effective-config
  surface. gap analysis 가 고른 다음 수.
