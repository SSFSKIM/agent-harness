---
status: stable
last_verified: 2026-06-21
owner: harness
type: log
description: Append-only, milestone-grained project log — how the docs system and the project evolved over time, read on-demand (not auto-loaded into context).
---
# Logs — project & docs-system evolution

> **What this is.** A light, append-only narrative of how the project and its
> docs system changed, at **milestone grain** — an ExecPlan completion, an ADR, a
> docs-system restructure. Not a per-commit ledger (git is that) and **not
> auto-loaded** into session context (read it on demand). Newest first. Link the
> related spec / ADR / plan where it adds value; links are optional, not a tax.
>
> Durable *decisions* live in [`adr/`](adr/index.md); deferred work and open
> questions live in [`exec-plans/tech-debt-tracker.md`](exec-plans/tech-debt-tracker.md);
> mechanical change is in git history. This file is the human-readable "how did we
> get here" that those three don't tell on their own.

## 2026-06-21 — Packaging: strict-base docs + guidance enrichment (Slice 2)

The harness-init seed-template layer became the self-describing strict base
(packaging
[Slice 2](product-specs/2026-06-21-harness-packaging-portable-template.md)).
Added a `PRINCIPLES.md` template (the human's externalized decision-taste the
central Director reads at a fork), dedicated guided indexes for `references/`
(why external-API/`llms.txt` digests exist) and `product-specs/`, and lifecycle
`index.md` guides for `exec-plans/active|completed`. The `ARCHITECTURE.md`
template became a **redirect** to the `architecture-setup` skill rather than a
hand-fill skeleton — the same no-drift principle (point, don't copy) that kept
the plan skeleton single-sourced in `PLANS.md`. `scaffold.py` wires the five new
seeds and trims `TOP_INDEXES` to `("adr",)`. A fresh scaffold now gates GREEN
with every doc teaching how to write itself.

## 2026-06-21 — Packaging: memory subsystem retired (Slice 1)

The disabled feeder→imprint→dream memory loop was **retired** in favor of native
Claude Code memory (packaging
[Slice 1](product-specs/2026-06-21-harness-packaging-portable-template.md)). Deleted
the feeder/imprint scripts, the `dream` skill, the `dreamer` agent, and the
`MEMORY.md` bootloader; removed `docs/memory/`. Durable knowledge was re-homed:
ADRs surfaced to [`adr/`](adr/index.md), the `recursion-guard` knowledge page moved
to `design-docs/`, and the old `openq/`+`limitations/` folded into the
[tech-debt tracker](exec-plans/tech-debt-tracker.md). `progress/current.md` was
replaced by this `logs.md`. `tidy_stop` (the gate-on-stop safety net) was kept, with
its activation sentinel re-pointed off `MEMORY.md` to `.harness.json`.
