---
status: draft
last_verified: 2026-06-16
owner: harness
phase: symphony/06-declarative-config
type: product-spec
tags: [director, config, declarative, orchestration]
description: Externalizes orchestration policy scattered across code and CLI flags into a director block in .harness.json so the harness runs in any repo by dropping in a single config, with CLI-over-config-over-default precedence.
---
# Director 선언적 설정 계약 (`.harness.json` `director` 블록)

Symphony 정합 트랙. 원본 [Symphony SPEC](../symphony-original/SPEC.md) §5–6/§6.2
(`WORKFLOW.md` = 정책의 무게중심)의 우리 대응물. 직전
[Symphony parity gap analysis](../design-docs/symphony-parity-gap.md)(gap #4 =
"WORKFLOW.md / §5–6 declarative contract")에서 사람이 고른 다음 수(세 축 중
**externalize policy**)를 spec 으로 떨군다. 부모
로드맵 [symphony-director-orchestration](2026-06-14-symphony-director-orchestration.md)
의 Phase 4 슬라이스는 전부 shipped — 이건 그 위에 얹는 **새 능력**(portability),
re-derivation 아님.

## 문제 (Problem)

오늘 Director 오케스트레이션 정책은 **코드 + CLI 플래그**에 흩어져 있다:

- `director/orchestrator.py` — `DEFAULT_STATE_NAMES`(ready/started/done/failed/blocked
  → Linear 상태명), argparse 기본값(`--team` 필수, `--concurrency 3`,
  `--max-passes 50`, `--max-dispatched 200`, `--read-timeout 30`,
  `--turn-review-timeout 300`, `--done-types completed`, `--codex "codex app-server"`).
- `director/run.py` — `DEFAULT_WORKSPACE_ROOT`, `DEFAULT_MAX_TURNS=8`.
- `director/worker/autonomy.py` — `APPROVAL_POLICY`/`SANDBOX`/`AUTO_REVIEW`/`NETWORK` 상수.
- `director/merger.py` — `DEFAULT_MAX_MERGES=200`, `--poll 1.0`, `--read-timeout 180`.

다른 repo 에서 Director 를 돌리거나(다른 team·다른 Linear 상태명) 한 run 을
튜닝하려면 **코드를 고치거나 긴 플래그 문자열**을 외워야 한다. Symphony 의
무게중심(repo-owned, 버전관리되는 `WORKFLOW.md`)에 해당하는 게 우리에겐 없다 —
"설정 파일 하나 떨구면 어느 repo 에서나 도는 하네스"가 안 된다.

이미 외부화된 것(따라가야 할 grain): `<root>/.harness.json` `worker_policy`
(worker secret boundary; `director/worker/policy.py`), `.env` 의 `LINEAR_API_KEY`.
이 spec 은 그 **같은 파일·같은 grain** 위에 오케스트레이션 정책을 마저 외부화한다.

## 요구사항 (Requirements)

- **R1 — 단일 host-config 파일, JSON.** Director 의 배포/운영 knob 은
  `<root>/.harness.json` 의 `director` 블록에서 읽는다. `worker_policy` 와 같은
  파일·같은 grain(ARCHITECTURE invariant 7: "호스트의 규칙은 호스트가 `.harness.json`
  에 선언"). **YAML 안 씀** — `director/`는 stdlib-only(ARCHITECTURE Host-runtime
  invariant 1, PyYAML=서드파티 금지)이므로 Symphony 의 YAML front matter 대신 stdlib
  `json`. (검증: `.harness.json` 에 `director` 블록을 두고 `python3 -m director.config`
  가 resolve 된 effective 설정을 JSON 으로 출력.)
- **R2 — 외부화 대상(deployment/operational knobs).** 아래 전부 외부화 + 각 knob 에
  내장 기본값: `team`; `states`(ready/started/done/failed/blocked → Linear 상태명);
  `concurrency`/`max_turns`/`max_passes`/`max_dispatched`/`done_types`;
  `read_timeout_s`/`turn_review_timeout_s`; `codex_command`; worker posture
  (`approval_policy`/`sandbox`/`auto_review`/`network`); `paths`
  (`workspace_root`/`queue_dir`/`status_dir`); `merger`(`poll_s`/`read_timeout_s`/
  `max_merges`). (검증: 각 값을 config 로 바꾼 run 의 동작이 그 값으로 바뀐다 — 예:
  `states` 변경 시 그 상태명으로 claim/transition.)
- **R3 — 코드에 남는 것(methodology/mechanism).** dev-stage 템플릿(`taxonomy.py`),
  `TERMINAL_CONTRACT`, queue 스키마, disposition kinds, reconcile 로직,
  `policy._BASE_NAMES`, label→type priority 는 **외부화하지 않는다** — 이건 하네스
  *자신의* institution(AGENTS.md→product-design→execplan 방법론)이고, 호스트는
  하네스를 설치하면 그 방법론을 *산다*. (검증: config 에 이 키들이 없고, 없어도 동작.)
- **R4 — precedence = CLI 플래그(explicit) > `.harness.json` `director` > 내장 기본값.**
  CLI 플래그는 commit 된 config 의 ad-hoc override(`harness_lib.gate_command` 의
  "env var > `.harness.json` 값"과 동형). (검증: 같은 knob 을 config 와 CLI 양쪽에 주면
  CLI 가 이긴다.)
- **R5 — `$VAR` indirection.** config 의 string scalar 값이 정확히 `$NAME` 또는
  `${NAME}` 형태면 환경변수로 resolve(빈 값 → missing 취급 — Symphony 의 api_key 규칙
  §5.3.1). secret 을 커밋 없이 참조(예: `"team": "$DIRECTOR_TEAM"`, codex 토큰).
  임의 문자열 안의 부분 치환은 안 함(Symphony §6.1: "값이 명시적으로 `$VAR` 일 때만").
  (검증: `"team": "$DIRECTOR_TEAM"` 가 env 에서 채워진다.)
- **R6 — load-once(daemon reload 아님).** 설정은 프로세스 startup 에 **1회** 읽고,
  변경은 **다음 run** 에 반영된다. Symphony §6.2 의 hot-reload 는 never-restart daemon
  의 affordance 인데, 우리는 episodic(`run_until_drained` → exit; gap analysis 에서
  daemon 은 고르지 *않은* 축)이라 재시작이 곧 reload 다 — 같은 운영 경험을 file-watch
  복잡도 없이 얻는다. (검증: run *도중* 파일을 바꿔도 그 run 은 안 바뀌고, 다음 run 은
  바뀐다.) daemon 트랙이 생기면 그때 reload hook 을 단다(아래 Non-goals).
- **R7 — validation: 부재는 fail-open, malformed 는 fail-loud.** `director` 블록
  **부재** → 문서화된 기본값으로 정상 동작(`gate_config` 의 fail-open-to-defaults 와
  동형). 블록이 **있는데 malformed**(잘못된 타입, 미지 상태명) → **fail LOUD**(raise,
  **첫 워커 spawn 전** startup error — `orchestrator.resolve_states` 가 이미 가진
  "fail before launching any worker" 규율과 동형). 근거: 잘못된 team/state 로 조용히
  *엉뚱한 티켓*을 claim/transition 하는 건 board 파괴 — 부재(=기본값 의도)와 달리
  present-but-broken 은 반드시 surface. (`worker_policy` 가 malformed 에 fail-loud,
  gate_config 가 fail-open 인 것과 같은 "위험에 따라 규율을 고른다" 원칙.) (검증:
  malformed `director` 블록 → 명확한 startup error, 워커 0 spawn; 부재 → 기본값 정상.)

## 설계 (Design)

**신규 `director/config.py` (pure, stdlib, explicit `root=`).** Host-runtime
invariant 2(ambient state 금지, explicit `base=`/`root=`)·invariant 4(pure core,
thin transport)를 따른다 — 로직은 socket/subprocess 없이 단위테스트되는 순수 함수,
`main()`/argparse 가 wiring.

- `load_director_config(root=None) -> DirectorConfig`:
  1. `root` 미지정 시 `policy.discover_root()` 재사용(`.harness.json` 소유 host root —
     worker_policy 와 같은 탐색).
  2. `.harness.json` 읽기 → `director` 키 추출. 부재(파일/키) → 전부 기본값(R7).
  3. `DEFAULTS` 머지 → `$VAR` resolve(R5) → 타입 검증(malformed raise, R7).
  4. frozen dataclass `DirectorConfig`(typed accessors: `.team`, `.states`,
     `.concurrency`, `.posture`(approval_policy/sandbox/auto_review/network), …)
     반환. dict 보다 dataclass: 오타난 키 접근이 AttributeError 로 즉시 터짐.
- **`DEFAULTS` = 기본값의 single source of truth**(config.py 한곳). 기존 상수
  (`autonomy.APPROVAL_POLICY`·`SANDBOX`, `orchestrator.DEFAULT_STATE_NAMES`,
  `run.DEFAULT_*`)는 이 기본값을 가리키도록 정리한다. 정확한 상수 재배치(순환 import
  회피: config 가 orchestrator 를 import 하면 안 됨 → 기본값을 config 가 소유하고
  orchestrator 가 config 를 읽음)는 ExecPlan 이 확정 — spec 은 "기본값 한곳, 모듈은
  config 를 읽는다"만 못박는다.
- **wiring.** `orchestrator.main`/`merger.main`/`run.main` 의 argparse 기본값을 `None`
  sentinel 로 바꾸고, 각 knob 을 `resolve(cli_value, cfg_value, default)`(R4)로 결정.
  `board` 의 team/states, `_command()` 의 codex_command + posture(autonomy)도 config
  에서 끌어온다. 기존 함수 시그니처(`run_once`/`drive`/`dispatch`)는 그대로 — config 는
  `main()` 경계에서만 풀리고 아래로는 값으로 전달(현 구조 유지, 코어 0 변경).
- **operator 표면 `python3 -m director.config [--root R]`** — resolve 된 effective
  config 를 JSON 으로 출력("지금 뭐로 도나" 확인용). DIRECTOR.md §1 / dashboard 에서
  링크. read-only debugging surface.

**`.harness.json` `director` 블록 스키마(문서화).**
```jsonc
"director": {
  "team": "TEAM_ID",                 // 또는 "$DIRECTOR_TEAM" (R5). orchestrator 에 필수
  "states": {                        // 논리상태 → Linear workflow 상태명 (없으면 기본)
    "ready": "Todo", "started": "In Progress", "done": "Done",
    "failed": null, "blocked": null  // null = 그 상태 없음 → started 유지 + comment
  },
  "concurrency": 3, "max_turns": 8,
  "max_passes": 50, "max_dispatched": 200,
  "done_types": ["completed"],
  "read_timeout_s": 30, "turn_review_timeout_s": 300,
  "codex_command": "codex app-server",
  "worker": {                        // posture (기본 = 현 autonomy.py 값, T11 문서화 값)
    "approval_policy": "on-request", "sandbox": "workspace-write",
    "auto_review": true, "network": true
  },
  "paths": {                         // 미지정 시 현 기본 경로
    "workspace_root": null, "queue_dir": null, "status_dir": null
  },
  "merger": {"poll_s": 1.0, "read_timeout_s": 180, "max_merges": 200}
}
```

**에러/경계 케이스.**
- malformed(타입 불일치, posture 미지 값) → `load_director_config` 가 raise →
  `main()` 이 startup 에서 비정상 종료(워커 0 spawn). 상태명 *존재* 검증은
  `resolve_states` 가 board read 후 수행(이미 있음) — config 는 *타입*만, 둘 다 첫 워커
  전에 fail.
- `$VAR` 빈/미설정 → missing 취급: optional knob 은 기본값/플래그로 폴백, **required
  `team`** 이 끝내 missing 이면 명확한 startup error("team not configured").
- 부재 `.harness.json` / 부재 `director` 블록 → 전부 기본값(현 동작과 byte-identical).
- **보안.** posture 외부화는 호스트가 *더 조이는* 방향만 의미 있게 연다(network off,
  `untrusted`로 회귀 = fail-safe). 기본값은 현 문서화된 값(SECURITY.md T11) 유지 —
  config 가 boundary 를 *넓히는* 신규 위험은 없다(network on 이 이미 기본).
  `worker_policy`(secret boundary)는 **이 블록이 건드리지 않는다** — 별도 키로 그대로.

## 비목표 (Non-goals)

- **dev-stage 템플릿/프롬프트 본문 외부화.** 방법론(코드 유지, R3). 다만 **가장 유력한
  future extension**: 호스트가 단계/템플릿을 커스터마이즈하려면 별도 spec(여기선 YAGNI).
- **hot-reload / file-watch**(Symphony §6.2). daemon 트랙(gap analysis 의 고르지 않은
  축)으로 defer — R6. daemon 이 생기면 그 spec 이 reload hook 을 단다.
- **일반 임의-문자열 `$VAR` 치환.** 정확히 `$NAME`/`${NAME}` scalar 만(R5).
- **`worker_policy` 통합/변경.** 이미 외부화됨 — 그대로 둔다.
- **새 tracker adapter / GitHub Issues** — 범위 밖.

## 수용 기준 (Acceptance)

- `.harness.json` `director` 블록으로 team·states·concurrency·posture 를 주면
  `python3 -m director.config` 가 resolve 된 effective config 를 출력(R1).
- **코드/플래그 편집 0**으로 config 만 바꿔 다른 team·다른 상태명·다른 concurrency 로
  orchestrator 가 돈다 — `MockBoard` 의 상태명을 config 로 매핑해 claim/transition 이
  그 상태명을 쓰는 것으로 검증(R2).
- 같은 knob 을 config 와 CLI 양쪽에 주면 **CLI 가 이긴다**(R4).
- malformed `director` 블록 → 명확한 startup error + 워커 0 spawn; 부재 → 기본값으로
  정상(R7).
- `"team": "$DIRECTOR_TEAM"` 가 env 에서 채워진다(R5).
- run *도중* config 변경은 무시되고 *다음* run 에 반영(R6).
- `python3 plugin/scripts/check.py` GREEN.

## Decision Log

- **D-54 파일 형식 = `.harness.json` JSON 블록(별도 WORKFLOW 파일 아님).** stdlib-only
  (PyYAML 금지)가 Symphony 의 YAML front matter 를 배제 → stdlib `json`. 그리고
  `worker_policy`·`lint_cmd`/`test_cmd` 가 이미 `.harness.json` 에 사는 선례 +
  ARCHITECTURE invariant 7("호스트 규칙은 `.harness.json`")이 같은 파일을 가리킨다.
  단일 host-config 파일이 두 개로 갈라지는 것보다 낫다.
- **D-55 load-once(reload 아님).** 사람이 고른 축이 daemon 이 아니라 config-externalize
  였고, 우리는 episodic 이라 재시작=reload. Symphony §6.2 reload 는 daemon affordance —
  episodic 모델에선 payoff 없는 file-watch 복잡도(+ watched-Director turn-end 모델과
  충돌). daemon 트랙이 생기면 그때.
- **D-56 외부화 = deployment/operational knob 만, methodology 는 코드.** mechanism-vs-
  deployment-policy 로 가른다(ARCHITECTURE inv 7 의 "mechanism vs host policy"와 동형):
  team/states/concurrency/posture/paths = 배포 정책(외부화), 템플릿/계약/큐 스키마 =
  하네스 institution(코드).
- **D-57 validation = 부재 fail-open, malformed fail-loud.** 부재는 "기본값 써라"라는
  정당한 상태(gate_config 처럼); present-but-broken 은 board 를 파괴할 수 있는 operator
  오류라 반드시 surface(worker_policy 처럼), 첫 워커 spawn 전에.
- **D-58 precedence CLI > config > default.** gate_command 의 env>file 와 동형 —
  commit 된 config 가 베이스, CLI 는 한 run 짜리 ad-hoc override.
