---
status: draft
last_verified: 2026-06-17
owner: harness
---
# Worker operating-protocol depth (graduated-autonomy slice 1)

[ADR 0002 — graduated autonomy](../memory/adr/0002-graduated-autonomy.md) 의
**첫 번째(선행) 슬라이스**. 근거: [Symphony parity gap](../design-docs/symphony-parity-gap.md)
**gap #5** (agent operating-protocol depth). 원본 운영 매뉴얼
[Symphony `WORKFLOW.md`](../symphony-original/WORKFLOW.md) 의 *stage-agnostic 운영
규율*을 우리 구조로 **수확(harvest)** 한다 — 파일을 포팅하지 않는다. 직접 올라타는 기존 작업:
[dev-stage taxonomy](2026-06-14-dev-stage-taxonomy.md) (per-stage 템플릿 + `TERMINAL_CONTRACT`),
[multi-turn 티켓 실행](2026-06-15-multi-turn-ticket-execution.md) (`report_outcome` 터미널 계약),
[worker self-QA + 직렬 PR-merge](2026-06-16-worker-qa-and-serialized-pr-merge.md) (self-QA 절차 +
PR 자기명세). 부모 로드맵
[symphony-director-orchestration](2026-06-14-symphony-director-orchestration.md).

> **왜 이게 graduated-autonomy 의 *선행*인가.** ADR 0002 는 Director 를 per-turn judge →
> exception-handler 로 옮긴다. 그 auto-continue 차로가 **안전하려면** 워커가 감독 없이도 스스로
> reproduction-first / source-of-truth / PR-feedback-sweep 를 신뢰성 있게 수행해야 한다. 이
> 슬라이스(워커 프로토콜 깊이)가 그 신뢰를 *벌고*, slice 2(selective-escalation decider)가 그걸
> *쓴다*. 그래서 순서가 강제된다.

## 문제 (Problem)

워커가 받는 운영 지침은 얇다. `director/taxonomy.py` 의 per-stage 템플릿은 각 2–5 문장이고,
공유되는 건 `TERMINAL_CONTRACT`(터미널 신호 방법) 하나뿐이다. Symphony 의 `WORKFLOW.md` 가
battle-test 한 **운영 규율**들이 우리 어디에도 박혀 있지 않다:

- **단일 source-of-truth 부재.** 워커가 진행 상태를 한 곳(살아있는 산출 doc)에 모으도록
  지시받지 않는다. 상태가 흩어지면 다음 턴/다음 워커가 현재 상태를 재구성해야 한다.
- **reproduction-first 부재.** impl 워커가 "고치기 전에 현재 동작/버그 신호를 먼저 포착"
  하도록 지시받지 않는다 → fix target 이 암묵적이고, 헛다리 수정이 늘어난다.
- **acceptance 미러링 부재.** 티켓이 들고 온 `Validation`/`Test Plan` 을 ExecPlan 의
  비협상 acceptance 로 끌어오라는 지시가 없다 → 티켓이 명시한 검증이 누락될 수 있다.
- **PR feedback sweep 부재 (gap #5 의 crown jewel).** 워커가 PR 을 열고 `done` 을 외치기
  전에 PR 의 checks/리뷰/봇 코멘트를 모든 채널에서 쓸어담아 처리/반박하는 규율이 없다.
- **scope-creep 가드 약함.** 범위 밖 개선을 발견했을 때 현재 티켓을 부풀리지 말고 typed
  child 티켓으로 분리하라는 *일반* 규율이 (impl-분할을 빼면) 없다.
- **temp proof edit 처리 부재.** 검증용 임시 편집을 commit 전에 되돌리라는 지시가 없다.

이건 ADR 0002 가 "워커 *출력 품질* 의 lever 이자 graduated-autonomy 의 precondition"
이라고 재분류한 바로 그 간극이다.

## The triage — `WORKFLOW.md` 줄별 keep / adapt / reject (이 스펙의 척추)

ADR 0002 의 four-axis 결정에 비춰, `WORKFLOW.md` 의 각 요소를 우리 구조
(orchestrator 가 보드 쓰기 소유 · 직렬 merger 가 PR 랜딩 · `report_outcome` 터미널 계약 ·
5 typed stage)에 대고 분류한다. **reject 열은 모두 Symphony 의 autonomy 베팅(워커가 보드/머지
소유)에 용접된 것**이고, **adopt 열은 stage-agnostic *craft***다.

| `WORKFLOW.md` 요소 | 판정 | 우리 구조에서 |
|---|---|---|
| Status map · Step 0–4 lifecycle · `update_issue(state:…)` (워커가 In Progress/Human Review/Rework 로 이동) | **reject** | orchestrator 가 보드 쓰기 소유 (ADR 0002). 워커 state 쓰기는 daemon claim/reconcile 와 경합 |
| `land` 스킬 / 워커가 자기 PR 머지 | **reject** | 직렬 merger 가 랜딩 소유 (DIRECTOR.md §7) |
| "Never ask a human / user-input = hard fail" | **reject** | `report_outcome(needs_human)` + watched/escalation Director |
| `## Codex Workpad` **단일 Linear 코멘트** = source of truth | **adapt** | 우리 narrative 의 authoritative home 은 stage 의 **살아있는 repo doc** (research digest / design doc / spec / ExecPlan) → R2. 단 **board-가시 mirror 를 금지하지는 않는다** — 단일 canonical 진행 코멘트(Symphony workpad 적응)는 [ADR 0002 §2b](../memory/adr/0002-graduated-autonomy.md) slice 2 로 deferred(Director 가 물러나면 사람은 board 를 본다). repo doc=권위, board 코멘트=mirror(경쟁 narrative 아님). |
| env-stamp (`<host>:<workdir>@<sha>`) | **reject** | `status.py` 스냅샷 + telemetry 가 이미 workspace/run 추적 (worker-telemetry-capture) |
| **Reproduction-first** (고치기 전 신호 포착) | **adopt** | impl 템플릿 → R4 |
| **Acceptance-criteria / Validation 미러링** (비협상 checkbox) | **adopt** | impl 템플릿 → R5 |
| **PR feedback sweep** (전 채널, 각 코멘트 blocking until 처리/반박) | **adopt — 배치 신중** | impl 의 *pre-handoff* + *on-arrival(이미 PR 붙음)* 경로 → R7. (Symphony 처럼 "Human Review 로 self-이동 직전" 이 아니라, `report_outcome(done)` 직전) |
| **Out-of-scope → 별도 티켓** (scope-creep 금지) | **adopt** | 공유 preamble (typed child + `issueCreate` allowlist) → R3 |
| **Temp proof edit 은 commit 전 revert** | **adopt** | impl 템플릿 → R6 |
| Principal-style **plan self-review** (구현 전) | **이미 보유** | execplan 의 creation-time self-review 가 충족 — 재추가 안 함 (YAGNI) |
| self-QA (spec-compliance + code-quality + tests) · PR 자기명세 | **이미 보유** | [worker-qa 스펙](2026-06-16-worker-qa-and-serialized-pr-merge.md) 이 `_IMPL_TEMPLATE` 에 박음 |
| YAML front matter (tracker/polling/codex/hooks) | **이미 보유** | gap #4 `.harness.json` + `config.py` |

> **★ 핵심 비대칭.** `WORKFLOW.md` 의 길이는 오해를 부른다 — 그 가치의 큰 덩어리는 우리
> 시스템에 *이미* 있다, 단지 **스킬로 factoring** 됐을 뿐이다. impl 템플릿은 이미 "execplan
> 절차를 따르라 / qa 스킬을 따르라 / push 스킬로 PR 을 열라"고 말한다. Symphony 는 스킬
> 시스템이 없어 그 전부를 한 프롬프트에 inline 한다. 그래서 **진짜 net-new 는 좁다**:
> source-of-truth · reproduction-first · acceptance-mirroring · PR-feedback-sweep ·
> no-scope-creep · revert-proof-edits — 어디에도 안 박힌 cross-cutting 규율들.

## 요구사항 (Requirements)

각 R 은 독립적으로 검증 가능하다(사람이 프롬프트 텍스트/주입 동작을 확인). 구현 단계가 아니라
*무엇이 성립해야 하는가*.

- **R1 — 공유 운영-프로토콜 preamble 이 존재하고 모든 dispatch 경로에 주입된다.**
  `taxonomy.WORKER_PROTOCOL`(stage-agnostic)이, 워커의 **첫 턴 프롬프트**에
  `TERMINAL_CONTRACT` 와 **같은 seam**(`drive` 의 first-turn framing, `run.py:201`)에서 주입된다
  → orchestrator·`run.main`·direct-drive 가 모두 받는다. 검증: framed 프롬프트가 preamble 을
  포함; 주입은 단일 지점.
- **R2 — preamble: 단일 살아있는 source-of-truth.** preamble 은 "이 stage 의 산출 doc 이
  plan + progress 의 **유일한** source of truth다; 작업하며 *in-place* 로 갱신하라(항목 체크,
  결정/surprise 즉시 기록); 상태를 Linear 코멘트나 별도 노트로 흩지 마라"를 지시한다.
- **R3 — preamble: no scope-creep → typed child 티켓.** preamble 은 "범위 밖의 의미 있는
  작업을 발견하면 현재 티켓을 부풀리지 말고, 올바른 stage 라벨을 단 별도 child 티켓을
  (`blocked_by`/`related` 적절히) linear 스킬로 만들고 기록하라"를 지시한다.
- **R4 — impl 템플릿: reproduction-first.** `_IMPL_TEMPLATE` 은 "코드를 바꾸기 전에 현재
  동작/이슈 신호를 구체적으로 재현·포착해 ExecPlan 에 기록(명령/출력 또는 결정적 동작)"하라고
  지시한다.
- **R5 — impl 템플릿: acceptance 미러링.** `_IMPL_TEMPLATE` 은 "티켓이 `Validation`/
  `Test Plan`/`Testing` 섹션을 들고 오면 그것을 ExecPlan 의 **비협상** acceptance 항목으로
  미러링하고 done 전에 실행"하라고 지시한다.
- **R6 — impl 템플릿: temp proof edit revert.** `_IMPL_TEMPLATE` 은 "검증용 임시 로컬 편집은
  허용되나 commit 전에 되돌리고 그 사실을 ExecPlan 에 문서화"하라고 지시한다.
- **R7 — impl 템플릿: PR feedback sweep.** `_IMPL_TEMPLATE` 은 두 경로를 지시한다:
  **(a) pre-handoff** — PR 을 연 뒤 `report_outcome(done)` *전에*, PR 의 checks + 모든 채널
  코멘트(top-level / inline review / 봇 / 리뷰 summary)를 쓸어담아 각 actionable 항목을
  *코드·테스트·docs 수정* 또는 *명시적 정당화 반박*으로 처리하고, 변경 후 검증 재실행, 남은
  것이 없고 checks 가 green 일 때까지 반복; **(b) on-arrival** — 워커가 집은 티켓에 이미 PR 이
  붙어 있으면(재-dispatch/rework), 새 작업 전에 그 PR feedback sweep 을 *먼저* 수행.
- **R8 — backward-compatible (regression net).** untyped 티켓은 여전히 raw 프롬프트(+ drive
  가 더하는 preamble + 터미널 계약)를 받는다; `compose_worker_prompt` 의 untyped 경로와
  `TERMINAL_CONTRACT` 의 기존 동작은 불변. 기존 `tests/test_director_taxonomy.py` 가 green 유지.
- **R9 — scope fence (non-regression).** `git diff` 는 `taxonomy.py`·`run.py`(주입)·해당
  테스트·docs 만 건드린다 — `decider.py`(slice 2)·보드-쓰기 소유·`merger.py` 는 불변.

## 설계 (Design)

워커 프롬프트 텍스트 + 단일 주입 seam 만 바꾸는, 한 subsystem(`taxonomy.py` + 그 주입) 슬라이스.

### 1. 공유 운영-프로토콜 preamble — `taxonomy.WORKER_PROTOCOL`

`TERMINAL_CONTRACT` 와 나란한 새 stage-agnostic 상수. 내용은 **딱 두 cross-stage 규율**만
(나머지 수확물은 impl-specific 이라 impl 템플릿에 둠 — YAGNI):

1. **단일 살아있는 source-of-truth** (R2).
2. **no scope-creep → typed child 티켓** (R3).

주입은 `TERMINAL_CONTRACT` 와 같은 first-turn seam 에서: 현재 `with_terminal_contract(prompt)`
가 `"---\nTURN PROTOCOL\n{TERMINAL_CONTRACT}"` 를 덧붙인다. 이를 확장해 framed 첫 턴 프롬프트가
**두 개의 나란한 framing 블록**을 갖게 한다:

```
[stage 템플릿]              # compose_worker_prompt (orchestrator)
TASK:
[티켓 본문]

---
WORKER PROTOCOL            # 신규: WORKER_PROTOCOL (stage-agnostic 운영 규율)
…

---
TURN PROTOCOL              # 기존: TERMINAL_CONTRACT (터미널 신호)
…
```

구현 형태(`with_terminal_contract` 확장 vs 합성 함수 `frame_first_turn` 추가)는 ExecPlan 의
선택; **불변식은 단일 주입 지점**(drive, `run.py:201`)이라 모든 dispatch 경로를 한 번에 덮는다
(R1). 이름 변경 여부도 ExecPlan 재량 — 단, 기존 `with_terminal_contract` 호출부/테스트가 깨지지
않아야 한다(R8).

### 2. impl 템플릿 enrichment — `_IMPL_TEMPLATE` (가장 무거움)

기존 self-QA + PR 자기명세(worker-qa 스펙)는 유지하고, 네 규율을 *추가*한다:
reproduction-first (R4) → acceptance 미러링 (R5) → temp-proof revert (R6) → PR feedback
sweep (R7). 시간 순서로 배치: (reproduce → plan/acceptance 미러 → 구현 → self-QA → PR open →
**feedback sweep** → `report_outcome(done)`).

**다른 템플릿(planning/research/design/spec)은 preamble 만 받고 본문은 안 건드린다** — 그들의
craft 는 이미 충분(research=cite sources, design=core-beliefs/ARCHITECTURE, spec=product-design,
planning=decompose)하고, cross-cutting 이득은 preamble 이 덮는다. (YAGNI — 템플릿 비대화 회피.)

### 3. PR feedback sweep — 우리 경계에서의 배치 (R7)

- **pre-handoff sweep 은 worker 의 *완료 바*** — self-QA 와 같은 *절차*(하드 게이트 아님; done
  은 LLM 판단 유지, worker-qa 스펙과 일관). 워커는 sandbox 의 shell + `push` 스킬 + `gh`/linear
  로 PR 채널을 읽는다(`gh pr view --comments`, `gh api …/pulls/<pr>/comments`, reviews).
- **merger 와의 분리.** merger(`merger.py`)는 *랜딩*(rebase→통합 게이트→squash-merge)을, sweep
  은 *리뷰 피드백 처리*를 — 서로 다른 경계의 다른 관심사. sweep 은 done **전**, merge 는 done
  **후**, merge escalation 은 Director(§7) — 경합 없음. 이 슬라이스는 merger 를 안 건드린다(R9).
- **on-arrival 경로**는 코드 변경 없이 성립한다: 사람이 PR 리뷰 후 티켓을 `ready` 로 되돌리면
  기존 daemon 이 재-claim → dispatch → impl 워커가 "PR 이 이미 붙어 있으면 sweep 먼저"를
  프롬프트로 수행. (새 board state/orchestration 불필요 — 그래서 worker-prompt-only.)

### 4. 테스트 (`tests/test_director_taxonomy.py`)

- preamble 존재 + 모든 dispatch 경로 주입(R1): framed 프롬프트(또는 `drive` 의 first-turn
  input 구성)가 `WORKER_PROTOCOL` 과 `TERMINAL_CONTRACT` 를 둘 다 포함.
- preamble 규율 present (R2/R3), impl 템플릿 규율 present (R4–R7) — 각 핵심 지시 substring/의도.
- regression (R8): untyped `compose_worker_prompt` 불변; `with_terminal_contract` 기존 동작
  (터미널 계약 포함) 유지; 기존 taxonomy 테스트 green.

### 5. 문서

`taxonomy.py` 의 모듈 docstring 에 새 preamble 의 역할을 한 줄 추가하고, 이 스펙 + ADR 0002 가
durable rationale. 별도 worker-protocol.md 는 안 만든다 — **프롬프트가 곧 프로토콜**이고, "왜"
는 스펙/ADR 이 갖는다(YAGNI; docs-tree 비대화 회피).

### 엣지/에러

- **untyped 티켓**: preamble + 터미널 계약은 받고 stage 템플릿은 없음 — 기존과 동일 + 두 규율
  (R8).
- **PR 채널 도달 불가**(no network/gh): sweep 은 절차이므로, 진짜 도구 blocker 면 워커가
  `report_outcome(blocked)`/`needs_human` 으로 평소처럼 라우팅(WORKFLOW.md 의 blocked-access
  hatch 와 같은 정신) — 조용히 건너뛰지 않음.
- **multi-turn**: sweep 은 여러 턴이 걸릴 수 있다(피드백 처리→재검증→반복) — multi-turn 이
  이미 지원; `report_outcome(done)` 은 sweep 이 clean 일 때만.
- **프롬프트 길이**: 규율 추가로 첫 턴 프롬프트가 길어진다 — 규율은 간결하게 유지(작은
  tradeoff, 수용).

## Non-goals (범위 펜스)

- **`decider.py` / selective-escalation** — slice 2. 이 슬라이스는 decider 를 안 건드린다.
- **worker-authority posture raise** (`approval_policy: never` 쪽으로) — slice 2 와 결합.
- **보드-쓰기 소유 변경 / 워커 self-merge / `land`-in-worker** — ADR 0002 가 reject.
- **`WORKFLOW.md` 파일 포팅** · **env-stamp** — triage 의 reject/이미-보유.
- **board-side canonical 진행 코멘트** — 이 슬라이스는 narrative home 을 repo doc 으로 두는
  데까지만(R2); 단일 board-가시 mirror 코멘트는 [ADR 0002 §2b](../memory/adr/0002-graduated-autonomy.md)
  slice 2 로 deferred (decider 변경과 함께 설계 — 사람이 매 턴 판단하지 않을 때 보는 면).
- **Human Review / Rework lifecycle *state*** — 우리는 `report_outcome` + 재-dispatch 로 충분;
  새 board state 안 만든다.
- **non-impl 템플릿 본문 enrichment** — preamble 로 충분 (YAGNI).
- **plan self-review · self-QA 재구현** — execplan/worker-qa 가 이미 보유.

## Acceptance criteria

- R1–R7 이 데모 가능: framed 워커 프롬프트가 공유 preamble 의 두 규율 + impl 의 네 규율을 담고,
  preamble 이 모든 dispatch 경로(orchestrator/run.main/direct)에 주입된다 — 테스트로 확인.
- R8: untyped 경로 + `TERMINAL_CONTRACT` 동작 불변; 기존 taxonomy 테스트 byte-green.
- R9: `git diff` 가 `taxonomy.py`·`run.py`·`tests/test_director_taxonomy.py`·docs 만 — decider/
  merger/board 소유 불변.
- `python3 plugin/scripts/check.py` GREEN.
- ADR 0002 가 cross-link 되고, slice 2(selective-escalation decider)의 precondition 으로 명시.
