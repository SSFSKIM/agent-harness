# Vendored from OpenAI Symphony (Apache-2.0)

The worker skills here (`commit`, `push`, `pull`, `land` + `land_watch.py`,
`linear`, `debug`) are copied verbatim from
[openai/symphony](https://github.com/openai/symphony) `.codex/skills/`, licensed
under Apache-2.0 (see that repo's `LICENSE` and `NOTICE`).

They are installed into a per-ticket worker workspace's `.codex/skills/` (by
`director/run.py:install_workspace_skills`) so the Codex worker knows how to use
git/PR flows and the client-advertised `linear_graphql` tool. This directory is a
template set, not skills for the agent-harness repo itself.
