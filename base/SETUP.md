# SETUP — bring this base to life

This folder is the **agent-harness strict base**: the complete, self-describing
documentation-and-governance system a project adopts, with nothing project-specific
filled in yet. Open any file and it teaches how to write itself; the `{{PROJECT}}`,
`{{TODAY}}`, and `<!-- FILL -->` markers are the only blanks you supply.

It is a **reference + starting point**, not a gated repo as-is (the docs carry
`{{TODAY}}` markers, not real dates, and `docs/generated/` is regenerated at
adoption, not shipped). Bring it to life in two halves — the **method** travels into
your repo; the **Director** stays centralized and reaches out.

## What's here

```
AGENTS.md            the single front door — read it first; it is the operating manual
CLAUDE.md            3-line pointer to AGENTS.md (for Claude Code / the plugin)
ARCHITECTURE.md      redirects to the architecture-setup skill (don't hand-fill)
.harness.json        host config ({} = all defaults); marks a harness host
docs/
  CHARTER.md         top-level intent — the project's Big Picture (FILL)
  PLANS.md           the ExecPlan methodology (how work is planned + gated)
  DESIGN.md          the design principles the lints/personas enforce
  PRINCIPLES.md      the human's externalized decision-taste (the Director consults it)
  KNOWLEDGE_FORMAT.md  the frontmatter/link contract docs are authored against
  PRODUCT_SENSE.md   what to escalate to the human vs. decide autonomously
  QUALITY_SCORE.md   the self-graded component scorecard
  RELIABILITY.md     numbered runtime invariants (R-rules)
  SECURITY.md        the threat model (T-rules)
  design-docs/       core-beliefs.md + agent-harness.md (the installed machine) + index
  adr/               architecture decision records + index
  product-specs/     the "what" (specs) + index
  exec-plans/        active/ + completed/ + tech-debt-tracker.md
  references/        external-API / source digests (llms.txt convention) + index
  logs.md            on-demand milestone narrative
```

The **machine** (the `agent-harness` Claude Code plugin: the `execplan`,
`harness-lint`, `docs-tree`, `docs-nav`, `product-design`, `harness-init`,
`architecture-setup`, and `garden` skills + the review-persona agents + the
`check.py` gate) is **referenced, not copied** — `docs/design-docs/agent-harness.md`
indexes it. You install it once; this base does not vendor it.

## Half 1 — make this base your project's method

1. **Install the machine.** Add the `agent-harness` plugin from its Claude Code
   marketplace. That is what supplies the skills, the review personas, and the
   `check.py` gate this base assumes.
2. **Scaffold (or adopt) into your repo.** Run the `harness-init` skill in your
   project. It renders these same seed templates into your repo with `{{PROJECT}}`
   and `{{TODAY}}` substituted, creates `docs/generated/`, installs the
   `.git/hooks/pre-commit` gate, and regenerates the component inventory — i.e. it
   produces a *live, gate-GREEN* version of this tree. (Inspecting this folder shows
   you exactly what you'll get.)
3. **Fill the blanks.** Author `docs/CHARTER.md` (your Big Picture), set
   `docs/PRINCIPLES.md` to your real decision-taste, and resolve every
   `<!-- FILL -->` marker. Run the `architecture-setup` skill to produce
   `ARCHITECTURE.md` (don't hand-fill it).
4. **Run the gate.** `python3 <plugin>/scripts/check.py` must be GREEN before each
   commit (the pre-commit hook runs it for you). Green = commit allowed; that is the
   whole contract.

From here, `AGENTS.md` is your operating manual — follow it.

## Half 2 — point the centralized Director at your project

The **Director is not copied into your repo.** It runs *from the agent-harness
checkout* (that repo is the orchestrator) and aims at your project's Linear board +
git repo: Codex workers clone your repo into a scratch workspace, do the work, and
open PRs against it. Two halves, two distribution models — the method (above)
travels to your repo; the Director stays central and reaches out.

To stand it up, follow the **runbook `docs/DIRECTOR_RUNBOOK.md`** in the agent-harness
repo (its command-first stand-up; `.claude/DIRECTOR.md` is the behavioral half — how the
Director judges). In short: install the `codex` CLI and an
authenticated `gh` (`GH_TOKEN`); connect the Linear MCP + `LINEAR_API_KEY`; add a
`director` block to *that repo's* `.harness.json` aiming at your team
(`"team": "$DIRECTOR_TEAM"`), your board's column names, and a workspace
`after_create` clone hook for your repo; then launch the watched orchestrator. Keep
secrets in `.env` / `$VAR`, never committed.

**Validate safely first:** real workers open real PRs and the merger really
squash-merges, so dry-run against a disposable copy of your repo + a throwaway board
before aiming at anything you care about.
