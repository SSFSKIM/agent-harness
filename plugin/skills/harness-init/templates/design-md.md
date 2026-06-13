---
status: draft
last_verified: {{TODAY}}
owner: review-arch
---
# DESIGN.md — taste rules for this repo

Grounding document for the review-arch persona (with `ARCHITECTURE.md`).
This is a **seed** — grow it: every taste correction given twice becomes a
rule here or a lint (feedback twice → promote).

- Lint/check failures must carry their own FIX instruction — error output is
  injected into agent context, so it doubles as the correction signal.
- Review personas use this file as taste authority, not as blinders. They may
  block on written rules or demonstrable bugs; unwritten preferences become
  proposed rule additions.
- Docs governance is tiered: machine-critical docs and harness-managed roots
  (`design-docs`, `exec-plans`, `memory`, `product-specs`) are strict;
  host-owned business/marketing/research docs are flexible unless opted into
  `.harness.json` `managed_doc_roots` or `doc_governance: strict`.
- Plugin component inventory/coverage are advisory for external-plugin hosts
  unless opted into `.harness.json` strictness.
- <!-- FILL: this repo's component taste rules — naming, structure, file
  size, error-message style. Keep each rule enforceable on sight; promote
  the stable ones into lints wired into the gate. -->
