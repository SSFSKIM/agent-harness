---
status: draft
last_verified: 2026-06-20
owner: harness
type: product-spec
phase: knowledge-format/06-enforced-keys
tags: [knowledge-format, lint, governance, okf]
description: Flip KF's permissive-on-optional stance into an enforced governance layer (KF v2.0) — type + description become required, phase is required on product-specs, and resource/supersedes/phase are validated when present; OKF stays permissive because it is a general exchange format, ours is a single enforced working memory.
---
# Format governance — escalate navigation keys to checked rules (KF v2.0)

## Problem

KF v1.0–v1.2 adopted Google OKF's recommended keys (`type`/`tags`/`resource`/
`title`/`description`, then `phase`/`supersedes`) as **optional**, with the lint
permissive on them — the deliberate "permissive on optional, strict on required"
asymmetry. That asymmetry is right *for OKF's objective* (a general exchange
format across an untrusted boundary, where a consumer must never reject). **It is
the wrong default for us.** We are not an exchange format — we are a single
actor's **enforced, fresh working memory**, and the navigation axes
(`type`/`description`/`phase`) are load-bearing: when they are absent the corpus
silently loses navigability (a type-less page vanishes from `catalog`; an unphased
spec vanishes from the roadmap — exactly the dogfooding bug that hid two plans
from their own map). Permissiveness *created* the propagation gap that needed a
manual backfill after the master merge. For us, a **governance layer that enforces
the navigational contract at commit** is a feature, not a violation of the format.

So: flip the stance. Escalate the load-bearing keys from optional to **checked
rules** — graded by what the corpus can sustain (the data forbids blanket-requiring
every key; `resource` is on 1/99 pages by design, `phase` on 30/99).

## Requirements

- **R1 — `type` required (blanket).** Every governed *content* page must declare
  `type` (reserved spines `index.md`/`MEMORY.md` are exempt — they are listings,
  not navigable concept-pages, consistent with nav's `RESERVED`).
  Value stays **free/extensible** (no vocabulary restriction — a new `type` adds no
  lint change; OKF's "tolerate unknown *values*" is kept, only *presence* is
  enforced). Corpus cost: 0 (99/99 already present). Verifiable: a governed page
  with no `type` FAILs the gate.
- **R2 — `description` required (blanket).** Every governed *content* page (same
  spine exemption as R1) must declare a non-empty `description`. Corpus cost: 3
  plans to backfill. Verifiable: a page with no `description` FAILs.
- **R3 — `phase` required on `product-spec`.** A `product-spec` must declare
  `phase` (it is an initiative anchor; the roadmap is then complete by
  construction, and `exec-plan`s inherit phase via the `implements` edge — so
  `phase` is **not** required on `exec-plan`, avoiding a 44-page redundant
  backfill). Corpus cost: 0 (29/29 specs already phased). Verifiable: a
  `product-spec` with no `phase` FAILs; an `exec-plan` without one does not.
- **R4 — Validate-if-present (resolve / well-formed), never presence-required.**
  - `resource`: if it is a repo-relative path (not an `http(s)://` URL), the path
    must exist (mirrors D5 for links). Absent is fine (abstract pages).
  - `supersedes`: each declared `.md` target must resolve (like D5). Absent is fine.
  - `phase`: if present on *any* page, it must be well-formed —
    `<initiative>/<NN>-<slug>` or a bare `<initiative>` (the roadmap grammar).
  Verifiable: a page with `resource: nope.py` (missing) or `supersedes: gone.md`
  or `phase: //bad` FAILs; valid/absent ones pass.
- **R5 — KF v2.0 + reframed conformance.** `KNOWLEDGE_FORMAT.md` (and the host
  template) bump to **v2.0** (a conformance-breaking change: new required keys).
  §5 conformance and the §intro asymmetry are reframed: the optional/required line
  moves — `type`/`description`/spec-`phase` join the enforced contract; `tags`/
  `title` stay optional; `resource`/`supersedes`/`phase`-elsewhere are
  validate-if-present. §7 (OKF relationship) explains *why we diverge*: OKF
  optimizes permissive exchange, KF optimizes an enforced single-actor memory.
- **R6 — Migration keeps the gate GREEN.** The rule additions and the backfill
  land together. Self-host corpus: backfill 3 plan `description`s (type 99/99,
  spec-phase 29/29, the 1 `resource` resolves — already conform). Ported hosts:
  seed `type`+`description` into the doc templates that lacked them (else a fresh
  scaffold FAILs D11), plus the ExecPlan template's `description:`. Verifiable:
  `python3 plugin/scripts/check.py` GREEN on the full corpus, and `test_scaffold`
  (a fresh host lints GREEN) passes.
- **R7 — Portability (belief 13).** The rules live in `plugin/scripts/lint_docs.py`
  (travel to every host); `KNOWLEDGE_FORMAT.md` host template carries the same
  v2.0 contract; the `harness-init` doc templates already emit `type`/`description`
  (and `phase` for specs) so a freshly scaffolded host is GREEN. Verifiable:
  `tests/test_scaffold.py` (fresh host lints GREEN) stays green.

## Design

**Components & changes**

| Artifact | Change |
|---|---|
| `plugin/scripts/lint_docs.py` | Extend the required-key check: add `type` + `description` to the blanket-required set (a new D-rule, e.g. **D11** "navigation keys", kept distinct from D3's governance core so failures read clearly). Add the conditional `phase`-on-`product-spec` check. Add validate-if-present checks for `resource` (path exists), `supersedes` (targets resolve), `phase` (grammar). All keyed off the parsed frontmatter; reuse the D5 resolver for path checks. |
| `docs/KNOWLEDGE_FORMAT.md` (+ host template) | KF v2.0: move `type`/`description` to §2.1 (required), document the conditional `phase` rule + the validate-if-present rules in §2.2/§5, reframe the asymmetry + §7 OKF divergence. |
| backfill | Add `description` to the 2 pages lacking it (`exec-plans/completed/2026-06-19-charter-and-progress-map.md`, `…map-depth-pivots-followups.md`). Metadata-only — no `last_verified` bump. |
| `tests/test_lint_docs.py` | Cases: missing `type`/`description` FAIL; `product-spec` missing `phase` FAILs but `exec-plan` does not; bad `resource`/`supersedes`/`phase` FAIL; valid/absent pass. |

**Contracts**
- The new checks run only on **governed** pages (same scope as D3 — exempt trees,
  `.harnessignore`, and the `generated/`/`superpowers/` exemptions are unchanged).
- Reserved spines (`index.md`, `MEMORY.md`) and the entry maps keep their current
  treatment (they are not governed content pages for D3 today; same here).
- `resource` URL values are exempt from the existence check (a URL is not a repo
  path); only repo-relative paths are checked — mirrors `nav.drift`/D5.

## Non-goals

- **NG1 — No vocabulary restriction on `type`.** Presence is enforced; the value
  stays free/extensible (kept OKF's tolerate-unknown for *values*).
- **NG2 — `phase` not required on `exec-plan`.** Plans inherit phase via the
  `implements` edge; requiring it on 45 plans is redundant + a heavy backfill.
- **NG3 — `tags` and `title` stay optional.** `tags` is a cross-cutting facet
  (legitimately absent on some pages); `title` is an H1 override (rare). Not
  load-bearing enough to force.
- **NG4 — No new value-shape rules beyond grammar/resolution.** e.g. no enforced
  `description` length, no `status` value re-check beyond what D3/D4 already do.
- **NG5 — nav stays advisory.** This escalates the *lint* (commit gate). `nav.py`
  (`catalog`/`roadmap`/`map`/…) remains read-only and never gates (NG unchanged).

## Acceptance criteria

1. A governed *content* page (reserved spines `index.md`/`MEMORY.md` exempt)
   missing `type` or `description` FAILs the gate; a `product-spec` missing `phase`
   FAILs; an `exec-plan` missing `phase` does **not**.
2. A page with a missing-file `resource`, an unresolvable `supersedes`, or a
   malformed `phase` FAILs; valid or absent ones pass.
3. `KNOWLEDGE_FORMAT.md` + host template read **KF v2.0** with the reframed
   required/optional/validate-if-present split and the OKF-divergence rationale.
4. After backfilling the 2 descriptions, `python3 plugin/scripts/check.py` is GREEN
   on the full corpus; `tests/test_lint_docs.py` + `tests/test_scaffold.py` pass.
5. The new rules ship in `plugin/scripts/lint_docs.py` (portable); a fresh
   `scaffold` produces a GREEN host.
