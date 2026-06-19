---
status: draft
last_verified: {{TODAY}}
owner: review-security
type: methodology
description: The numbered threat model that grounds the review-security persona.
---
# SECURITY.md

Grounding document for the review-security persona. Threats are numbered;
cite relevant ones in findings. This is a **seed** — grow it: every threat or
mitigation this repo learns becomes the next numbered entry.

- **T1 — Transcript prompt injection.** Session transcripts and external
  content are untrusted data. Memory write-back prompts treat them strictly
  as data, never as instructions; writes are restricted to `docs/memory/`.
- **T2 — Memory poisoning.** All memory writes are git-visible commits
  (reviewable, revertible); the lint gate must pass after every write; the
  feeder reads structured memory only, never raw transcripts.
- **T3 — No secrets in the repo or memory.** Credentials, tokens, and
  personal data never land in `docs/` or `docs/memory/` — reference secret
  stores by name instead.
