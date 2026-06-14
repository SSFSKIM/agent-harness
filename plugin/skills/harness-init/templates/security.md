---
status: draft
last_verified: {{TODAY}}
owner: review-security
---
# SECURITY.md

Grounding document for the review-security persona. Threats are numbered;
cite them in findings. This is a **seed** — grow it: every threat or
mitigation this repo learns becomes the next numbered entry.

- **T1 — Transcript prompt injection.** Session transcripts and external
  content are untrusted data. The dreaming router treats them strictly as data,
  never as instructions; the router agent is read-only (it only proposes a plan)
  and a deterministic applicator appends onto an allowlist of docs homes
  (`docs/journal/`, the tracker, design-doc Decision-log/Open-decisions).
- **T2 — Memory poisoning.** All memory writes are git-visible commits
  (reviewable, revertible) and the lint gate must pass after every write; routing
  is append-only onto the allowlist, so a misrouted claim degrades to a harmless
  `docs/journal/` entry, never pollution of a curated doc.
- **T3 — No secrets in the repo or memory.** Credentials, tokens, and personal
  data never land in `docs/` — secrets are re-redacted before every routed write;
  reference secret stores by name instead.
