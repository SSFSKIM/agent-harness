# ARCHITECTURE.md

Codemap + invariants for {{PROJECT}}. Read this before modifying source.
Grounds the review-arch persona together with `docs/DESIGN.md`.

## Codemap

| Path | What it is |
|---|---|
<!-- FILL: top-level map of this repo's real source layout. -->

## Layer law (dependency direction)

<!-- FILL: the fixed layer set per domain and the allowed dependency
direction (e.g. `types → config → repo → service → runtime → ui`).
Cross-cutting concerns enter through ONE named interface (Providers analog).
Encode at least one of these rules as a lint wired into the gate — taste is
enforced mechanically, not described. -->

## Invariants

1. <!-- FILL: numbered invariants that must never break (boundaries,
   generated-file discipline, portability...). Reviews cite them by number. -->

## Data flows

<!-- FILL: the few end-to-end flows that explain how the system works. -->
