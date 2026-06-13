# FORM classification rubric

Each candidate invariant gets exactly one FORM. Apply the tests in order.

## Decision

1. **Mechanical AND always-true AND costly-if-missed?**
   - *mechanical*: a script can decide it from the files (import graph, naming
     pattern, presence/absence, a schema relation).
   - *always-true*: not case-by-case; there is one correct answer.
   - *costly-if-missed*: a silent violation causes drift, a security hole, or a
     correctness bug.
   → all three → **deterministic lint**.

2. **How-to-develop guidance?** (No single frozen answer; the right action
   depends on context — where a concern belongs, what to read first, the safe
   sequence for a risky change.)
   → **guide-skill** (a host `.claude/skills/` skill).

3. **Semantic?** (Only meaning can decide it — "the behavior matches the spec",
   "consent is actually enforced".)
   → **judge** (LLM-as-lint; currently deferred) or **persona review** at the
   completion gate. Do NOT fake it with a brittle lint.

4. **Cheap and rare violation?**
   → **fix-forward** — encode nothing; the gate's general lints + review catch it
   if it happens.

The lint count and the skill count are both OUTPUTS of this triage, not quotas.

## Worked example — layered architecture decomposes

"Layered architecture" (Types → Config → Repo → Service → Runtime → UI, with
cross-cutting via one Providers interface) is NOT one FORM. It splits:

| Piece | FORM | Why |
|---|---|---|
| Respect the layers while developing (where a new concern goes, what to touch) | guide-skill | judgment; no frozen answer |
| Dependency direction (no upward import; cross-cutting only via Providers) | **lint** | mechanical (import graph), always-true, one bad import = drift |

The harness applies this split to itself: the layer law
`scripts → skills → agents → hooks` is enforced by **S2** (cross-cutting
resolution only in `harness_lib`) — a real dependency-direction lint — while
*how* to choose a script vs a skill is guidance in `ARCHITECTURE.md`/`DESIGN.md`.
Mirror that split on the host.

## Why not skill-only

A skill enforces by instruction (soft): it works only if the session loads it,
follows it, and doesn't drift mid-task. For a mechanical invariant that one
forgetful session can break, that is insufficient — the gate must intercept it
regardless of what the agent read. At big-codebase scale the agent replicates
existing patterns (the drift the OpenAI harness blog warns about), so the
mechanical floor is load-bearing. Keep lints for the floor; use guide-skills for
the methodology above it. Skill *guides*; lint *guarantees*.
