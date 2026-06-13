# ARCHITECTURE.md

Codemap + invariants for {{PROJECT}}. Read this before modifying source.
Grounds the review-arch persona together with `docs/DESIGN.md`.

## Bird's Eye View

<!-- FILL: in a few paragraphs, explain what this repo does, its primary
inputs/outputs, and the highest-level runtime shape. Keep this stable: do not
describe volatile implementation details that will change every sprint. -->

## Code Map

| Path | What it is |
|---|---|
<!-- FILL: top-level map of this repo's real source layout. Answer both:
"where is the thing that does X?" and "what does the thing I am looking at do?"
Name important files, modules, commands, types, and entrypoints. Keep details
behind pointers in docs/ or inline code comments. -->

## Boundaries and API Surfaces

<!-- FILL: public/internal boundaries, generated/runtime boundaries, external
service boundaries, CLI/API/UI boundaries, and the files or types that define
each boundary. Boundaries are where rules change; make them explicit. -->

## Layer Law (dependency direction)

<!-- FILL: the fixed layer set per domain and the allowed dependency direction
(e.g. `types -> config -> repo -> service -> runtime -> ui`). Call out the
absence rules too: which layers must NOT import or know about which others? -->

## Architectural Invariants

1. <!-- FILL: numbered invariants that must never break (boundaries,
   generated-file discipline, portability, data ownership, idempotency...). Many
   important invariants are absences: "X never imports Y", "runtime state never
   lives in docs/", "the model layer never sees UI types". Reviews cite these by
   number. -->

## Cross-Cutting Concerns

<!-- FILL: where logging, configuration, path/env resolution, auth, external
clients, generated files, migrations, and test fixtures enter the system. If a
concern is allowed to cross layers, name the one sanctioned interface. -->

## Data flows

<!-- FILL: the few end-to-end flows that explain how the system works. -->

## Enforcement (Invariant -> FORM)

| Invariant | FORM | Enforced by | Why |
|---|---|---|---|
| <!-- FILL: e.g. "UI never imports repo" --> | <!-- lint / guide-skill / persona / judge / fix-forward --> | <!-- .claude/lints/check_layers.py, .claude/skills/<name>, review persona, etc. --> | <!-- why this medium fits: mechanical, methodology, semantic, or cheap rare drift --> |

<!-- Run the architecture-setup skill to derive this table from the host source.
Do not invent universal app-code rules from the harness; this repo's invariants
belong to this repo. -->
