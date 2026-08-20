---
name: finishing-touch
disable-model-invocation: true
---

Apply finishing touches to all changes in the current branch. Auto-fix mechanical issues, tighten unnecessary code, flag judgment calls, and verify nothing was broken.

You are the orchestrator. Gather the diff, spawn sub-agents, apply their auto-fixes, present their flagged items, and verify. Keep your context lean — sub-agents carry the analysis weight.

## Steps

### 1. Gather the diff

```bash
git diff origin/main...HEAD > /tmp/finishing-touch-diff.txt
```

Annotate each diff line with its real file line number so sub-agents can reference exact locations:

```bash
python3 - <<'PY'
import re

lines = open('/tmp/finishing-touch-diff.txt').read().split('\n')
out, newln = [], None

for l in lines:
    fm = re.match(r'^diff --git a/(.*) b/(.*)', l)
    if fm:
        out.append(f'\n### FILE: {fm.group(2)}')
        newln = None; continue
    m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)', l)
    if m:
        newln = int(m.group(1)); out.append(l); continue
    if newln is None:
        out.append(l); continue
    if l.startswith('-'):
        out.append(f'      {l}')
    else:
        out.append(f'{newln:>6} {l}'); newln += 1

open('/tmp/finishing-touch-annotated.txt', 'w').write('\n'.join(out))
PY
```

### 2. Classify and detect

From the annotated diff, identify:

- **Source files**: `.ts`, `.tsx`, `.css`, `.mjs`
- **Markdown files**: `.md`, `.mdx`
- **Test files**: `*.test.*`, `*.spec.*`
- **Skip**: generated files (`*.gen.*`), lock files, binary assets

Scan source file diffs for **user-facing text** — string literals in JSX, toast calls, error messages, dialog titles, placeholders, form labels, empty state copy. Note whether any exist. This determines whether the Copy Agent spawns.

### 3. Read convention sources

Read these once. Their contents go into sub-agent prompts.

| Source                                           | Extract                                         | For                                            |
| ------------------------------------------------ | ----------------------------------------------- | ---------------------------------------------- |
| `../pr-review/SKILL.md` (relative to this skill) | Code Quality Rules + Intent & UX Rules sections | Tighten Agent                                  |
| `impeccable` skill, `reference/clarify.md`       | Entire file                                     | Copy Agent (only if user-facing text detected) |

### 4. Spawn sub-agents in parallel

Launch all applicable sub-agents in a **single message**. Each gets the annotated diff for its assigned files and its instructions below.

---

#### Tighten Agent

Gets all file diffs (source + markdown + test). **Read-only** — works exclusively from the provided diffs.

Prompt:

> You are doing a final tighten pass on code changes. Identify two kinds of findings:
>
> **Auto-fixes** (mechanical, safe to apply without approval):
>
> - Narration comments — the comment says what the code already says. Test: delete the comment and read the code. If it conveys the same information, the comment is narration.
> - AI slop — visual section dividers (`// ========`, `/* --- SECTION --- */`), over-structured comment blocks, boilerplate headers no human would write.
> - AI-tell vocabulary in comments and markdown: delve, landscape, tapestry, showcase, foster, garner, underscore, pivotal, crucial, enhance, intricate, leverage, utilize, facilitate, robust. Rewrite in plain language.
> - Unused imports.
> - `console.log` / `debugger` statements.
> - Implementation-scaffolding TODOs/FIXMEs where the work is complete.
> - Whitespace-only changes (merge noise).
>
> **Flagged items** (judgment calls, present for approval):
>
> - Comment language — suggest STE (Simplified Technical English) rewrites for poorly-worded comments. Short, active voice, explain why not what.
> - Markdown language — same STE standard for `.md` / `.mdx` changes.
> - Naming — suggest better names for files, functions, variables, components when the current name is unclear or misleading.
> - Unnecessary code — `useMemo`, `useCallback`, `useEffect` that could be derived state, handlers, or key remounts. Prematurely extracted functions that should be inlined.
> - Simplification — if-else chains that should be early returns, manual validation that should be Zod, overly complex expressions.
> - Barrel files — `index.ts` whose sole purpose is re-exporting.
>
> Also apply these convention rules to the diff:
>
> [INSERT the Code Quality Rules and Intent & UX Rules sections you read in step 3]
>
> All diffs are provided below. Do NOT use Read, Grep, or Glob tools — work exclusively from the diffs.
>
> **Output format** — group by file, auto-fixes first, then flagged items:
>
> ```
> ## `path/to/file.tsx`
>
> ### Auto-fix
> - Line 42: Remove narration comment: `// Set the state to loading`
> - Line 18: Remove unused import: `import { foo } from 'bar'`
>
> ### Flag
> - Line 55 [naming]: `handleStuff` is vague → `handleFormSubmit`
> - Line 33 [tighten]: `useMemo` wrapping static data → move to module level
> - Line 78 [comment]: Rewrite "This function serves as the handler for..." → "Handles session expiry by..."
> ```
>
> If a file has no findings, skip it.

---

#### Copy Agent (conditional)

**Only spawn if step 2 detected user-facing text.** Gets source file diffs that contain user-facing strings. Read-only.

Prompt:

> Review every user-facing string in the diff for clarity and quality: button labels, toast messages, error messages, dialog titles, placeholders, empty state text, form labels, tooltips.
>
> Apply these copy principles:
>
> [INSERT the clarify reference you read in step 3]
>
> Use STE — short, active, plain. For each string that could be clearer, more concise, or more helpful, suggest a rewrite.
>
> All diffs are provided below. Do NOT use Read, Grep, or Glob tools — work exclusively from the diffs.
>
> **Output format:**
>
> ```
> ## `path/to/file.tsx`
>
> - Line 55 [copy]: "An error occurred while processing your request" → "Could not save changes. Try again."
> - Line 72 [copy]: "Submit" → "Send message" (name the action and object)
> ```
>
> If no improvements are needed, return "No copy findings."

---

#### Completeness Agent

Gets source file diffs. **Has codebase access** — must search for existing patterns.

Prompt:

> Check every component in the diff that handles async data for missing UI states.
>
> A component handles async data if it uses `useQuery`, `useMutation`, `useSuspenseQuery`, receives data props that could be undefined/empty, or fetches data in any way.
>
> For each such component, check:
>
> 1. **Error state** — what the user sees when the request fails.
> 2. **Loading state** — what the user sees while the request is pending.
> 3. **Empty state** — what the user sees when the data array/object is empty.
>
> Search the codebase for how similar components handle these states. Suggest patterns that match existing code — reference the specific file and component.
>
> The PR diffs are provided below. You MUST search the broader codebase for existing error/loading/empty state patterns. Use Read, Grep, and Glob freely.
>
> **Output format:**
>
> ```
> ## `path/to/file.tsx`
>
> - Line 12 [missing error]: Uses `useQuery` with no error handling. See `OrdersPage` (`src/pages/orders-page.tsx`) for the pattern.
> - Line 12 [missing empty]: No empty state when data array has zero items.
> ```
>
> If all components handle their states, return "No completeness findings."

---

### 5. Apply auto-fixes

Take every auto-fix from the Tighten Agent and apply the changes directly. These are mechanical and safe — no approval needed.

### 6. Present flagged items

Collect all flagged items from every sub-agent into a single numbered list, grouped by category:

| Category     | Source             | What it covers                          |
| ------------ | ------------------ | --------------------------------------- |
| Comments     | Tighten Agent      | STE rewrites, missing context           |
| Copy         | Copy Agent         | User-facing text improvements           |
| Naming       | Tighten Agent      | Files, functions, variables, components |
| Tighten      | Tighten Agent      | Unnecessary code, simplification        |
| Completeness | Completeness Agent | Missing error/loading/empty states      |
| Convention   | Tighten Agent      | pr-review rule violations               |

Present the full list. Wait for the user to decide on each item before applying.

Report: "Applied N auto-fixes across M files. K items flagged for your review."

**Done when:** every file in `git diff origin/main...HEAD` has been reviewed by a sub-agent, auto-fixes are applied, and flagged items are presented.
