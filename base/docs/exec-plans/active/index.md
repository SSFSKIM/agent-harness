---
status: active
last_verified: {{TODAY}}
owner: harness
---
# Active ExecPlans

In-flight ExecPlans live here, one file per plan (`YYYY-MM-DD-<slug>.md`). To
start one, copy the plan skeleton embedded in `docs/PLANS.md` (or just use the
`execplan` skill, which scaffolds it for you and runs the completion gate). When
a plan's completion gate passes, the skill `git mv`s it to `../completed/`.

`exec-plans/` is not an indexed category — plans are not registered in this
file; the live picture is the derived `nav.py roadmap`. This `index.md` is a
lifecycle guide, not a listing, and exists so the directory is self-describing.
