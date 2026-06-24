# skills

[![skills.sh](https://skills.sh/b/satejbidvai/skills)](https://skills.sh/satejbidvai/skills)

My personal agent skills, installable across Claude Code and other agents via [skills.sh](https://skills.sh).

## Install

```bash
npx skills add satejbidvai/skills
```

## Skills

A coupled PR-review workflow:

- **pr-review** — Review a PR against my personal review standards using parallel sub-agents, then merge and deduplicate findings.
- **post-pr-review** — Post a completed `/pr-review` as a draft (PENDING) review on GitHub.
- **update-pr-review** — Learn from PR comments to discover gaps in the `pr-review` rules and propose targeted updates.

All three are user-invoked only (`disable-model-invocation: true`).

These encode opinionated frontend (TypeScript / React / React Query) review standards. Read each `SKILL.md` and adapt it to your own stack.

## Local development

This repo is the source of truth. `scripts/link-skills.sh` symlinks each skill into `~/.agents/skills/` (and `~/.claude/skills/`), so edits here are instantly live; `git push` publishes them.
