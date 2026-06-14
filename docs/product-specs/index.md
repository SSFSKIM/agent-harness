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
