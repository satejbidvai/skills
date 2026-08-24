---
name: finishing-touch
disable-model-invocation: true
---

Apply finishing touches to all changes in the current branch. Apply small fixes. Ask about medium and large items. Verify nothing was broken.

You are the orchestrator. Keep your context lean. You own the Size gate.

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

Scan source file diffs for **user-facing text**: string literals in JSX, toast calls, error messages, dialog titles, placeholders, form labels, empty state copy. Note whether any exist.

### 3. Read convention sources

Read these once. Insert each extract into the matching prompt.

| Source                                           | Extract                                         | For                                            |
| ------------------------------------------------ | ----------------------------------------------- | ---------------------------------------------- |
| `../pr-review/SKILL.md` (relative to this skill) | Code Quality Rules + Intent & UX Rules sections | Tighten Agent                                  |
| `impeccable` skill, `reference/clarify.md`       | Entire file                                     | Copy Agent (only if user-facing text detected) |

### 4. Spawn sub-agents in parallel

Launch all applicable sub-agents in a **single message**. Each gets the annotated diff for its assigned files and its instructions below.

---

#### Tighten Agent

Gets all file diffs (source + markdown + test). **Read-only.** Works exclusively from the provided diffs.

Prompt:

> You are doing a final tighten pass on code changes. Find issues of these kinds. Propose a concrete rewrite for each. Tag each finding with its kind.
>
> - `[narration]` The comment says what the code already says. Test: delete the comment and read the code. If it conveys the same information, the comment is narration.
> - `[slop]` Visual section dividers (`// ========`, `/* --- SECTION --- */`), over-structured comment blocks, boilerplate headers no human would write.
> - `[vocab]` AI-tell vocabulary in comments and markdown: delve, landscape, tapestry, showcase, foster, garner, underscore, pivotal, crucial, enhance, intricate, leverage, utilize, facilitate, robust. Rewrite in plain language.
> - `[unused-import]` Unused imports.
> - `[debug]` `console.log` / `debugger` statements.
> - `[todo]` Implementation-scaffolding TODOs/FIXMEs where the work is complete.
> - `[whitespace]` Whitespace-only changes (merge noise).
> - `[comment]` STE (Simplified Technical English) rewrites for poorly-worded comments. Short, active voice, explain why not what.
> - `[markdown]` Same STE standard for `.md` / `.mdx` changes.
> - `[naming]` Better names for files, functions, variables, components when the current name is unclear or misleading.
> - `[tighten]` `useMemo`, `useCallback`, `useEffect` that could be derived state, handlers, or key remounts. Prematurely extracted functions that should be inlined. If-else chains that should be early returns, manual validation that should be Zod, overly complex expressions.
> - `[barrel]` `index.ts` whose sole purpose is re-exporting.
>
> Also apply these convention rules to the diff. Tag each finding `[convention]`:
>
> [INSERT the Code Quality Rules and Intent & UX Rules sections you read in step 3]
>
> All diffs are provided below. Work exclusively from the diffs. Do not use Read, Grep, or Glob tools.
>
> **Output format.** Group by file. One list. Kind tag on every line:
>
> ```
> ## `path/to/file.tsx`
>
> - Line 42 [narration]: Remove comment `// Set the state to loading`
> - Line 18 [unused-import]: `import { foo } from 'bar'`
> - Line 61 [comment]: Rewrite to STE: "Handles session expiry by..."
> - Line 20 [naming]: local `data` → `orders`
> - Line 55 [naming]: exported `StuffPanel` → `OrderFilters`
> - Line 33 [tighten]: `useMemo` wrapping fetched data → derive during render
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
> Use STE: short, active, plain. For each string that could be clearer, more concise, or more helpful, suggest a rewrite. Tag each finding `[copy]`.
>
> All diffs are provided below. Work exclusively from the diffs. Do not use Read, Grep, or Glob tools.
>
> **Output format.** Group by file. One list:
>
> ```
> ## `path/to/file.tsx`
>
> - Line 55 [copy]: "Please click the button below to continue" → "Continue"
> - Line 72 [copy]: "Submit" → "Send message" (names the action)
> ```
>
> If no improvements are needed, return "No copy findings."

---

#### Completeness Agent

Gets source file diffs. **Has codebase access.** Must search for existing patterns.

Prompt:

> Check every component in the diff that handles async data for missing UI states.
>
> A component handles async data if it uses `useQuery`, `useMutation`, `useSuspenseQuery`, receives data props that could be undefined/empty, or fetches data in any way.
>
> For each such component, check:
>
> 1. **Error state.** What the user sees when the request fails. Tag `[missing-error]`.
> 2. **Loading state.** What the user sees while the request is pending. Tag `[missing-loading]`.
> 3. **Empty state.** What the user sees when the data array/object is empty. Tag `[missing-empty]`.
>
> Search the codebase for how similar components handle these states. Suggest patterns that match existing code. Reference the specific file and component.
>
> The PR diffs are provided below. Search the broader codebase for existing error/loading/empty state patterns. Use Read, Grep, and Glob freely.
>
> **Output format.** Group by file. One list:
>
> ```
> ## `path/to/file.tsx`
>
> - Line 12 [missing-error]: Uses `useQuery` with no error handling. See `OrdersPage` (`src/pages/orders-page.tsx`) for the pattern.
> - Line 12 [missing-empty]: No empty state when data array has zero items.
> ```
>
> If all components handle their states, return "No completeness findings."

---

### 5. Sort and apply

Classify every finding as **auto** or **ask** using the Size gate. Then apply every auto.

#### Size gate

Every finding is **auto** or **ask**.

**Kind defaults.** Use these first:

- **auto:** `narration`, `slop`, `vocab`, `unused-import`, `debug`, `todo`, `whitespace`
- **ask:** `missing-error`, `missing-loading`, `missing-empty`

**Remaining kinds** (`comment`, `markdown`, `naming`, `copy`, `tighten`, `barrel`, `convention`):

**Auto** means small: one obvious rewrite, local to the hunk, no product or architecture choice.

**Ask** means medium or large: more than one valid fix, or the fix changes what the user sees, names, or how the code is shaped.

When size is unclear, use these bounds:

| Auto                                          | Ask                                                           |
| --------------------------------------------- | ------------------------------------------------------------- |
| One correct form                              | Two valid names, wordings, or shapes                          |
| Local variable, comment, or import            | Exported name, file name, or component name                   |
| String meaning stays the same                 | Meaning, tone, or the user's next action changes              |
| Drop dead code or a wrapper that does nothing | Restructure control flow, extract, or inline across functions |
| Unused barrel file                            | Barrel file that other files import                           |

**Done with this step when:** every finding is auto or ask, and every auto is applied.

### 6. Present asks

Collect remaining asks into a single numbered list, grouped by category:

| Category     | Kinds                                               | What it covers                     |
| ------------ | --------------------------------------------------- | ---------------------------------- |
| Comments     | `comment`, `markdown`                               | Comment or markdown wording        |
| Copy         | `copy`                                              | User-facing text                   |
| Naming       | `naming`                                            | Files, exports, components         |
| Tighten      | `tighten`, `barrel`                                 | Restructuring, simplification      |
| Completeness | `missing-error`, `missing-loading`, `missing-empty` | Missing error/loading/empty states |
| Convention   | `convention`                                        | pr-review rule violations          |

Present the list. Stop. Apply an item only after the user decides.

Report: "Applied N autos across M files. K items to decide."

**Done when:** every file in `git diff origin/main...HEAD` has been reviewed by a sub-agent, autos are applied, and asks are presented.
