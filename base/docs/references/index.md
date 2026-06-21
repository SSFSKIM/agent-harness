---
status: active
last_verified: {{TODAY}}
owner: harness
---
# References — index

External-API facts and source digests live here: the docs an LLM needs but
cannot infer — third-party API contracts, library/tool behavior, file-format
specs, vendored `llms.txt` digests. Keep them close to the code that depends on
them so a session can ground itself without re-reading upstream docs (this is
where most "the model guessed the API wrong" failures are prevented).

Convention: one `*.llms.txt` digest per external surface (the `llms.txt`
convention — a compact, LLM-oriented summary of an external doc set). Prefer a
trimmed digest over a full mirror, and record the source URL + fetch date inside
the file so staleness is visible.

Every page in this directory must be registered here with a one-line
description (lint D8).

No pages yet.
