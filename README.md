# skills

[![skills.sh](https://skills.sh/b/satejbidvai/skills)](https://skills.sh/satejbidvai/skills)

My personal agent skills, installable across Claude Code and other agents via [skills.sh](https://skills.sh).

## Install

```bash
npx skills add satejbidvai/skills
```

## Skills

All skills are user-invoked only (`disable-model-invocation: true`).

### PR review workflow

- **pr-review** — Review a PR against my personal review standards using parallel sub-agents, then merge and deduplicate findings.
- **post-pr-review** — Post a completed `/pr-review` as a draft (PENDING) review on GitHub.
- **update-pr-review** — Learn from PR comments to discover gaps in the `pr-review` rules and propose targeted updates.

These encode opinionated frontend (TypeScript / React / React Query) review standards. Read each `SKILL.md` and adapt it to your own stack.

### Other

- **how** — Explore and explain "how does X work?" questions. Produces architectural explanations with optional critique mode for identifying structural issues. Adapted from [cursor/plugins](https://github.com/cursor/plugins/tree/HEAD/pstack/skills/how).

## Local development

This repo is the source of truth. `scripts/link-skills.sh` symlinks each skill into `~/.agents/skills/` (and `~/.claude/skills/`), so edits here are instantly live; `git push` publishes them.
