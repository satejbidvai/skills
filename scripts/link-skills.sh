#!/usr/bin/env bash
set -euo pipefail

# Symlinks every skill in this repo into the local agent skill directories so
# this working copy is the live source of truth. Edit a SKILL.md here and it is
# instantly live in your agents; `git push` publishes it. Do NOT `npx skills add`
# your own repo on this machine — that replaces these symlinks with frozen copies.

REPO="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS_DIR="$HOME/.agents/skills"   # neutral hub, read by every agent
CLAUDE_DIR="$HOME/.claude/skills"   # Claude Code's per-skill symlinks

mkdir -p "$AGENTS_DIR" "$CLAUDE_DIR"

find "$REPO/skills" -name SKILL.md -not -path '*/node_modules/*' -print0 |
while IFS= read -r -d '' skill_md; do
  src="$(dirname "$skill_md")"
  name="$(basename "$src")"

  # Canonical hub -> this repo
  ln -sfn "$src" "$AGENTS_DIR/$name"
  # Claude Code -> hub (matches the convention used by the skills CLI)
  ln -sfn "../../.agents/skills/$name" "$CLAUDE_DIR/$name"

  echo "linked $name"
done
