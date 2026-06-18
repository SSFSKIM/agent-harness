---
status: draft
last_verified: 2026-06-16
owner: harness
type: product-spec
tags: [director, observability, dashboard, telemetry]
description: A stdlib-only local read-only web view over the existing status snapshot and pending queue that serves run state as JSON and re-renders via a polling vanilla-JS page for live current-run observability.
---
# Director observability dashboard (라이브 read-only 웹 뷰)

Phase 5(optional)의 **observability surface**. 부모 spec:
[Symphony 티켓 오케스트레이션 + 중앙 Director](2026-06-14-symphony-director-orchestration.md)
(line 199 "Phase 5 — 공유 tracker + observability surface"). 직전
[orchestration-visibility](2026-06-15-director-orchestration-visibility.md) 가
"라이브 dashboard / TUI / web observability" 를 명시적으로 Phase 5 로 미뤘다(line 208).
이 슬라이스가 그 미뤄둔 항목 중 **observability 만** 집어 짓는다 (공유 tracker / GitHub
Issues 어댑터는 별도 — 이번 범위 밖, 사람 결정 2026-06-16).

> **상태/재배치 (2026-06-16):** 이 renderer 는
> [worker telemetry capture](2026-06-16-worker-telemetry-capture.md) **뒤로 재배치**됐다.
> renderer richness 는 producer state 에 묶이므로(렌더러는 데이터의 하류), 먼저 telemetry 를
> 풍부하게(토큰/런타임/rate-limit) 만들고 이 renderer 가 그 consumer 가 된다. 그때 이 뷰는
> 구조 그림(in-flight/stuck/recent/pending)에 더해 비용/usage 까지 렌더한다.
>
> **Symphony 정렬(SPEC §13.7, Elixir Phoenix LiveView):** 이 spec 의 데이터 엔드포인트는
> `GET /api/v1/state`(버전드 read-only 네임스페이스, 향후 `/api/v1/<ticket>` drill-down 여지),
> 미정의 라우트→`404`·정의된 라우트의 잘못된 메서드→**`405`**, 에러는 `{"error":{"code",
> "message"}}` 봉투, state payload 에 `counts`+`generated_at` 블록. 루프백 bind 기본 +
> "dashboard MUST NOT be REQUIRED for correctness"(§13.4)는 우리 D-2/D-5 와 동일 — Symphony 가
> 같은 자세를 명문화. `POST /api/v1/refresh` 는 Symphony 의 daemon poll 트리거라 우리 세션-구동
> orchestrator 엔 비적용(N/A). (본문 §의 `/api/snapshot` 표기는 이 정렬로 대체.)
>
> **구체 계약 (이 빌드, 2026-06-16 — telemetry producer 出荷 후):** 데이터 엔드포인트는
> `GET /api/v1/state`. view dict =
> `{run, in_flight, stuck, recent, pending[{request_id,ticket_id,kind,summary}],
> counts{in_flight,stuck,recent,pending}, generated_at}`. `run`/`in_flight`/`stuck`/
> `recent` 는 스냅샷 **pass-through** 라, telemetry 슬라이스의 producer 필드가 그대로
> 흐른다 — 렌더러가 새로 계산할 게 없다: `run.codex_totals{input,output,total,
> seconds_running}` · `run.rate_limits`(또는 null) · `recent[].tokens{input,output,
> total}|null` · `recent[].session_id` · `recent[].last_message`. 클라이언트가 이
> 비용/usage 를 헤더(런 누계 토큰 · runtime · rate-limit)와 recent 행(티켓별 토큰)에
> 렌더한다 — 이게 "telemetry 뒤로 재배치" 가 회수하는 가치다. 라우팅: 미정의 라우트→`404`,
> 정의된 라우트의 잘못된 메서드→`405`, 둘 다 `{"error":{"code","message"}}` 봉투(JSON).

기존 `director.status` 스냅샷 + `director.watch` 이벤트 스트림 위에 **사람이 브라우저에서
런을 직접 들여다보는** read-only 뷰를 더한다. 오늘 사람은 Director 가 narrate 해줄 때만
오케스트레이션을 본다(D-5); 이 뷰는 사람이 **수동적으로 직접** "지금 워커들이 뭘 하나"
를 훑는 surface 다 — taste 결정과 구별되는 ambient 모니터링.

## Problem (오늘 무엇이 불만족인가 — observable)

1. **오케스트레이션 그림에 사람-facing surface 가 없다.** `director.status` 는 스냅샷을
   영속하지만 소비자는 코드(인라인 Director, `director.watch`)뿐이다. 사람이 "지금 전체
   상황"을 보려면 Director 에게 물어 narrate 시키거나 `python3 -m director.status` 의
   raw JSON 을 직접 읽어야 한다 — glance-able 한 라이브 뷰가 없다.
2. **unattended watched 런을 곁눈질할 방법이 없다.** 런이 도는 동안 사람이 다른 창에서
   "in-flight 몇 개·뭐가 stuck·최근 결과" 를 ambient 하게 보고 싶어도, Director 세션에
   들어가 묻는 것 말고는 surface 가 없다. PRODUCT_SENSE 의 희소-주의 명제상, 사람이
   원할 때 **무비용으로 훑는** 채널이 빠져 있다.
3. visibility spec 이 surface 를 "스냅샷 파일 + read-API + 스킬" 로만 의도적으로 한정하고
   (line 208), 라이브 UI 를 Phase 5 로 미뤘다. 그 미뤄둔 가치를 이제 회수한다.

## Verified facts (repo, 추측 아님)

- `director/status.py:188` `read_status(base=None) -> dict|None` — tolerant: 파일 없음
  (런 없음)/깨짐 → None, raise 안 함. 스냅샷 스키마:
  `{run:{started_at,pass,stopped_reason}, in_flight[{ticket_id,identifier,phase,attempt,
  wave,started_at}], recent(bounded 20)[{ticket_id,ticket,status,final_state,attempts,
  turns}], stuck[{ticket,blocked_by[{id,state_type}]}], updated_at}`. 스냅샷은 단일 atomic
  `status.json`(temp+os.replace) — reader 가 torn read 를 절대 안 본다.
- `director/queue/__init__.py:192` `read_pending(base=None) -> list[dict]` — 미답 요청
  (= Director 가 act 해야 할 work surface). 요청 shape `{request_id, ticket_id, kind,
  payload, ...}`. kind: commandApproval/fileChange/userInput/elicitation/turnReview/
  mergeRequest/mergeReview.
- 두 read API 모두 `base=` override 를 받고 default 는 `.claude/harness/director-status`
  / `.claude/harness/director-queue`. 둘 다 순수 read — 부르는 쪽을 mutate 안 함.
- **프로젝트는 stdlib-only.** `pyproject.toml`/`requirements.txt` 없음; `director/` 어디에도
  third-party import 없음(json/urllib.request/select/threading/http... 전부 stdlib).
  테스트는 `python3 -m unittest discover`. → 새 surface 도 stdlib-only 여야 grain 유지
  (core-beliefs "boring tech / 의존 내장"). textual/rich/flask/fastapi 배제 — http.server
  (web) 또는 curses(TUI)만 후보였고, 사람이 web 선택(D-1).
- `director.status`/`director.watch`/`director.merger` 는 모두 `python3 -m director.<mod>`
  CLI 패턴 + `--status-dir`/`--queue-dir` 인자. 이 슬라이스도 같은 패턴(`director.dashboard`).

## Requirements (R1..R6 — 각 항목 사람이 검증 가능)

- **R1 — `python3 -m director.dashboard` 가 stdlib http.server 로 127.0.0.1:<port> 에
  read-only 대시보드를 띄운다.** (검증: 起動 후 `GET /` → 200 `text/html`; `GET /api/
  snapshot` → 200 `application/json`; 미정의 라우트 → 404.)
- **R2 — `GET /api/snapshot` = `build_view(status_dir, queue_dir)` 의 JSON.** view dict:
  `{run:<run>|None, in_flight, stuck, recent, pending[{request_id,ticket_id,kind,summary}],
  generated_at}`. `pending[].summary` 는 payload 에서 kind 별 best-effort(turnReview→
  final_message, mergeReview/mergeRequest→pr/note, 그 외→kind). (검증: 실 `StatusWriter`
  스냅샷 + `append_request` 한 pending 요청에서 view dict 가 스키마대로; summary 가 kind 별로 채워짐.)
- **R3 — read-only + tolerant.** status.json 없음(런 없음)/torn → `run:null`, 그래도 200
  (`read_status` 계약 재사용); pending 은 큐에서 독립적으로. request-derived 파일 경로 없음
  (고정 2개 라우트) → path traversal 표면 0; 어떤 요청도 디스크를 mutate 안 함. (검증: 런
  없음/garbage status.json 에서 `build_view` 가 `run:null` 로 valid; GET 외 메서드/미정의
  경로 → 404, 서버 안 죽음.)
- **R4 — 라이브 = 클라이언트 폴링(SSE 아님).** 페이지의 vanilla JS 가 ~1s 마다 `/api/
  snapshot` 을 fetch → DOM 재렌더(프레임워크 0). (검증: 스냅샷이 바뀌면 페이지가 새로고침
  없이 갱신; 폴 간격은 코드 상수.)
- **R5 — blast radius 최소: 기존 모듈 변경 0.** 신규 `director/dashboard.py` +
  `tests/test_director_dashboard.py` + `docs/DIRECTOR.md` 절. `status.py`/`watch.py`/
  `orchestrator.py`/`queue` **미변경**. (검증: diff 가 기존 런타임 모듈을 안 건드림.)
- **R6 — `python3 plugin/scripts/check.py` GREEN.**

## Design

```
 browser ──poll ~1s──▶ GET /api/snapshot ──▶ build_view(status_dir, queue_dir)
                                                  │
                          status.read_status() ◀──┤  run/in_flight/stuck/recent (tolerant→None)
                          queue.read_pending()  ◀──┘  미답 요청 = pending Q
 browser ◀──── JSON ────────────────────────────┘
   └─ thin vanilla JS 가 DOM 재렌더 (프레임워크 없음)

 GET /  ──▶ 인라인 HTML 페이지(문자열 상수: CSS + ~30줄 폴러 JS)
 그 외   ──▶ 404
```

### A. `build_view(status_dir, queue_dir) -> dict` — 순수·테스트 가능한 코어
- `status.read_status(base=status_dir)`(tolerant) + `queue.read_pending(base=queue_dir)`
  를 읽어 **정규화된 view dict** 반환. 이것이 로직의 거의 전부 — HTTP 층은 이 위 얇은 shim.
- `run` 은 스냅샷의 `run`(없으면 None). `in_flight`/`stuck`/`recent` 는 스냅샷 그대로
  pass-through(렌더는 클라이언트). `pending` 은 `read_pending` 을 `{request_id, ticket_id,
  kind, summary}` 로 축약 — summary 는 payload 에서 kind 별 tolerant 추출(키 없으면 빈 문자열).
- `generated_at` = view 생성 시각(iso). 클라이언트가 "마지막 갱신" 표시에 사용.
- 테스트가 이 함수를 **소켓 없이** 검증(데이터 구조 assert; HTML scrape 아님) — 이게 JSON-
  endpoint+client-render 를 고른 testability lever.

### B. HTTP 핸들러 — 얇은 shim (`http.server`)
- `ThreadingHTTPServer` + `BaseHTTPRequestHandler`. 라우트 **2개 고정**:
  - `GET /` → 인라인 HTML 문자열, `text/html`.
  - `GET /api/snapshot` → `json.dumps(build_view(status_dir, queue_dir))`, `application/json`.
  - 그 외 경로/메서드 → 404.
- 핸들러는 status_dir/queue_dir 를 **서버 생성 시 클로저/속성으로** 받는다(요청에서 파생 안
  함 — traversal 0). `log_message` override 로 조용히.
- bind `127.0.0.1` 만(LAN 노출 안 함). `--port`(default 8787), `--status-dir`/`--queue-dir`
  override(다른 CLI 와 동형).

### C. 인라인 페이지 (HTML/CSS/JS 문자열 상수)
- 단일 HTML 문자열: 미니멀 CSS(다크, terminal-ish) + `setInterval(fetch('/api/snapshot'),
  ~1000ms)` → DOM 재렌더. 프레임워크/번들러/외부 asset 0(전부 인라인, offline OK).
- 렌더: 헤더(run#/pass/started_at/터미널 배지 if stopped_reason) · in-flight(ticket·phase·
  attempt/wave) · stuck(ticket ← blocker ids) · recent(✓/✗ by status) · pending Q(kind·
  ticket·summary). `run:null` → "no active run"(+ pending 있으면 그래도 표시).

### 구성요소 / 파일
- `director/dashboard.py` (신규) — `build_view`, 핸들러, `serve(port, status_dir, queue_dir)`,
  `main(argv)`(`python3 -m director.dashboard`, `--port`/`--status-dir`/`--queue-dir`).
- `tests/test_director_dashboard.py` (신규) — `build_view` 단위(실 스냅샷+pending, no-run/None,
  summary by kind) + HTTP smoke(포트 0 bind, urllib GET `/api/snapshot`→JSON, `/`→200 html,
  `/nope`→404).
- `docs/DIRECTOR.md` — 신규 절 "Watching a run live (the observability dashboard)": 사람이
  `python3 -m director.dashboard` 를 옆 창/브라우저로 띄워 런을 훑는다(read-only; act 는
  Director 경유).
- 재사용: `status.read_status`(스냅샷), `queue.read_pending`(pending). status.py/watch.py/
  orchestrator/queue **변경 0**.

### 에러 / 경계 케이스
- status.json 없음/torn → `read_status` None → view `run:null`, 200(R3). 페이지는 "no
  active run", pending 큐는 독립 표시.
- 빈 큐 → `pending:[]`. 빈 스냅샷 필드 → 빈 배열.
- GET 외 메서드/미정의 경로 → 404, 서버 계속.
- 포트 점유 → bind 에러를 명확히 surface(즉시 실패, 무한 retry 안 함).
- 병렬 세션은 같은 `status.json` 을 공유(repo 당 단일) — 대시보드는 그 파일만 렌더(정확히
  현재 진실). 멀티-런/멀티-status-dir 종합 뷰는 비-목표(Open Q).

## Non-goals (scope fence — YAGNI)

- **SSE / 서버 push.** v1 은 클라이언트 폴링 — 스냅샷이 single source of truth 라 1s 재독이
  trivial·견고; long-lived stream/subprocess 없음. SSE 는 1s 폴이 laggy 하면 후속 upgrade.
- **write / action path.** read-only. pending turnReview/mergeReview 를 **브라우저에서 답하지
  않는다** — act 는 Director 경유(D-5; status.py 의 "never a gate" 자세). actionable
  대시보드(human-bound 항목을 UI 에서 답)는 잘 fence 된 별 슬라이스(사람 결정 2026-06-16).
- **cross-run 히스토리 / 메트릭 영속.** visibility spec 의 명시 non-goal(line 210); `recent`
  는 bounded tail. 대시보드는 현재 런 그림만.
- **auth / non-localhost bind.** 로컬 read-only instrument(127.0.0.1, no auth).
- **JS / CSS 프레임워크, 번들러, 외부 asset.** vanilla·인라인만(stdlib-only grain).
- **GitHub Issues 어댑터 / 공유 tracker.** Phase 5 의 다른 절반 — 이번 범위 밖(사람 결정).

## Acceptance criteria

- `python3 -m director.dashboard` 가 127.0.0.1:<port> 에 뜨고 `GET /`→200 html,
  `GET /api/snapshot`→200 json, 미정의 라우트→404 (R1).
- `build_view` 가 실 스냅샷+pending 요청에서 스키마대로 view dict; no-run→`run:null`;
  pending summary 가 kind 별 채워짐 (R2).
- 없음/torn status.json + 빈 큐에 tolerant(200, run:null); request-derived 경로 없음 (R3).
- 페이지가 ~1s 폴로 새로고침 없이 갱신; SSE 없음 (R4).
- diff 가 status.py/watch.py/orchestrator/queue 미변경; 신규 파일 + DIRECTOR.md 절만 (R5).
- `python3 plugin/scripts/check.py` GREEN (R6).
- (live, 선택) 실제 watched 런 중 브라우저에서 in-flight/stuck/recent/pending 이 라이브로 보임.

## Decision Log (수렴 결정 + 근거)

- **D-1 form = local web dashboard (stdlib http.server).** 대안 terminal TUI(curses) / pretty
  CLI digest 검토. 브라우저는 "useful in many senses"(둘째 모니터·폰·공유) + curses 보다 단순·
  견고(raw-mode/resize/teardown 상태기계 없음); stdlib http.server 로 의존 0 유지. (사람, 2026-06-16.)
- **D-2 read-only v1, act 경로 없음.** status.py 의 "read-only instrument, never a gate" +
  D-5(사람은 Director 를 steer, Director 가 큐를 답)를 보존; localhost write surface(CSRF/origin)
  + act-before-consume 불변식 회피. actionable 은 별 슬라이스. (사람, 2026-06-16.)
- **D-3 라이브 = 폴링, SSE 아님(v1).** 스냅샷이 single source of truth — 1s 재독이 trivial·
  bulletproof; keep-alive stream 없음. SSE 는 latency 체감 시 additive upgrade. (자율, 미반대.)
- **D-4 current-run only.** cross-run analytics 는 visibility non-goal(line 210); recent 는
  bounded tail. (자율 — 기존 non-goal 귀결.)
- **D-5 bind 127.0.0.1, no auth.** 로컬 read-only instrument; LAN 노출/인증은 비-목표. (자율.)
- **D-6 JSON endpoint + client render(서버 HTML 렌더 아님).** 테스트가 데이터 구조를 assert
  (HTML scrape 아님) → 로직 거의 전부가 소켓 없이 검증; 핸들러는 ~10줄 shim. (자율 — testability.)

## Open Questions

- **SSE upgrade 시점** — 1s 폴이 실사용에서 laggy 하면 watch 스트림→SSE 로 전환(코어 view 함수
  재사용). 1차는 폴.
- **actionable 대시보드 후속 슬라이스** — human-bound 항목(escalate 된 turnReview/mergeReview)을
  UI 에서 답하는 write 경로. write surface fencing(origin check, act-before-consume) 설계 필요.
- **멀티-런 / 멀티 status-dir 종합 뷰** — 1차는 단일 status.json(현재 런). 여러 동시 런을 한 뷰에
  모으는 건 후속(병렬 세션 공유-인덱스 맥락과 함께).
- **digest/요약 풍부함** — 1차 렌더는 스냅샷 필드 직역; 실제 런에서 정제.
