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
  resume seam) 상세 + Phase 2–5 로드맵.
