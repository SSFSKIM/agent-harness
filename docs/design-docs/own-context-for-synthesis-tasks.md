---
status: stable
last_verified: 2026-06-28
owner: harness
type: knowledge
tags: [agents, orchestration, methodology]
description: For a holistic review / comparison / synthesis task, read the full material into your own context rather than delegating extraction to summarizer subagents; delegate only breadth-sweep find/locate work.
---
# Own the context for synthesis tasks

A field note promoted from session memory. For a **holistic review / gap analysis
/ comparison / synthesis** task, read the full material into your **own** context
rather than fanning out to summarizer subagents.

**Why:** the deliverable of a synthesis task *is* the comparison, and the
interesting gaps only surface when both models are co-resident in one head. A
summarizer subagent decides what mattered when it compresses — but you don't know
what matters until you've seen both sides side by side, so delegation throws away
exactly the nuance that makes the analysis valuable. Cost is rarely the blocker
here (a spec + a subsystem is tens of k tokens).

## The line

> **Sweep-and-conclude → delegate. Read-deeply-and-synthesize → own it.**

Delegation (an Agent/Explore fan-out) is still right for breadth-sweep
"find / locate / does-this-exist" work where you only need the conclusion, not the
material. It is wrong when the conclusion *is* the cross-reading. (This page is
itself an instance: deciding where each promoted memory belongs in the corpus is a
synthesis call, so it was owned, not fanned out.)
