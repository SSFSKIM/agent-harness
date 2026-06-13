# Host ARCHITECTURE.md authoring guide

`ARCHITECTURE.md` is not another general docs page. It is the host repo's
mental map: the short, durable document that helps a new contributor answer
"where should I change X?" before reading the whole codebase.

## Why this file exists

The hard part for an occasional contributor is usually not how to change the
code after finding the right place. The hard part is where to change the code.
A core developer has a mental map and jumps to the right area; a newcomer reads
files linearly and pays the navigation tax. `ARCHITECTURE.md` exists to transfer
that map.

This is not "write more docs" advice. Keep this file low-effort and
high-leverage: short enough that every recurring contributor and future agent
will actually read it, stable enough that it does not go stale every sprint, and
specific enough to answer "where's the thing that does X?".

## Principles

- Keep it short and stable. Prefer facts unlikely to change often. Do not try to
  mirror every implementation detail; revisit it a couple of times a year. Also
  update it when a real architectural boundary changes.
- Start from a bird's-eye view: what the system accepts, what it produces, and
  what major runtime shape it has.
- Write a code map, not an encyclopedia: a map of a country, not an atlas of
  every state. Name directories, important files, commands, modules, types, and
  entrypoints, but push detailed algorithms to lower-level docs or inline
  comments.
- Name important entities rather than over-linking them. Direct links to exact
  lines and volatile paths go stale; stable names let future agents find the
  current implementation and nearby related code. Use symbol search, file
  search, and ripgrep instead of maintaining brittle deep links.
- Name boundaries explicitly. Boundaries are hard to infer by browsing files:
  API Boundary modules, public/internal boundaries, generated/runtime boundaries,
  external service boundaries, and layer boundaries.
- Call out absences. Many architecture rules are "X must never depend on Y" or
  "state of kind Z never lives under path P"; those rules are invisible unless
  the architecture doc says them.
- Add cross-cutting concerns after the code map: configuration, path/env
  resolution, logging, auth, external clients, generated files, migrations, and
  test fixtures. If a concern may cross layers, name the sanctioned interface.
- Use the writing process to inspect the source layout. If the things that sit
  next to each other in the code map are far apart in `tree`, or unrelated
  concerns are adjacent on disk, record the tension as a limitation or plan a
  cleanup.

## Host exploration procedure

1. Inventory top-level files and directories: README, source roots, package
   manifests, build/test config, generated directories, runtime state, app entry
   points, CLI commands, UI routes, API routes, jobs, and migrations.
2. Trace two or three representative flows end to end. Prefer flows a maintainer
   actually changes: request -> handler -> domain/service -> persistence,
   CLI command -> parser -> action -> output, or UI event -> state -> API.
3. Identify the ground state and derived state when the app has them: stored
   inputs, config, external facts, generated artifacts, cached/runtime state,
   and outputs. Good architecture docs explain which modules own each kind.
4. Derive the layer law from code that already exists. Do not import the
   harness's own `scripts -> skills -> agents -> hooks` law into the host unless
   the host really has that shape.
5. Mark API Boundary surfaces: library entrypoints, server routes, command-line
   commands, UI/public component boundaries, data schemas, and plugin/extension
   seams. Rules at boundaries are different; write the boundary contract rather
   than assuming it is obvious from filenames.
6. List candidate invariants while reading. Include both positive rules ("all
   schema parsing lives in X") and absence rules ("UI never imports repo").
7. Classify each invariant through FORM after the map is written: lint,
   guide-skill, persona/judge, or fix-forward.

## Section contract

- **Bird's Eye View:** a few paragraphs that orient the system.
- **Code Map:** coarse modules/directories and what each does. Answer "where is
  the thing that does X?"
- **Boundaries and API Surfaces:** places where rules change or external callers
  interact with the system.
- **Layer Law:** dependency direction and forbidden edges.
- **Architectural Invariants:** numbered rules reviews can cite.
- **Cross-Cutting Concerns:** sanctioned locations/interfaces for concerns that
  otherwise leak everywhere.
- **Data flows:** a few end-to-end flows that explain how the system works.
- **Enforcement:** Invariant -> FORM table showing which medium holds each rule.

## Anti-patterns

- Copying the harness self-host `ARCHITECTURE.md` into the host. The host needs
  its own map.
- Listing every file. If the document becomes an atlas, it will go stale.
- Writing a guide to how each module works internally. That belongs in deeper
  design docs, runbooks, or inline documentation. `ARCHITECTURE.md` explains the
  coarse map and boundaries.
- Hiding important absences because "the code already implies it." Future agents
  copy existing patterns; absent dependencies need written names.
- Stuffing active plans or sprint state into the architecture doc. Use
  `docs/exec-plans/` and `docs/memory/progress/current.md` for volatile work.
- Encoding app-specific rules in the portable plugin. The machine provides the
  method and gate substrate; host rules live in the host repo.

## Example shape

Use the rust-analyzer style as a pattern, not a template to copy: a short
bird's-eye view, a code map with one heading per coarse component, explicit
Architecture Invariant callouts under the relevant components, API Boundary
labels where callers enter or rules change, then cross-cutting concerns after
the map.
