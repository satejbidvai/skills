---
name: pr-review
description: Review a PR using Satej's personal review standards
disable-model-invocation: true
---

Review a pull request against my review standards using specialized sub-agents that run in parallel, then merge and deduplicate findings.

**Input**: The argument after `/pr-review` is the GitHub PR URL. Optionally, a second sentence can provide focus context (e.g., "focus on the new dialog component").

**Voice** — include in every sub-agent prompt:

Write like a friendly senior engineer reviewing a teammate's PR. Be direct, concise, and conversational. Say "this" not "this code block." Vary your phrasing — no two comments should sound templated. When you're unsure, express it naturally ("I think," "looks like," "not sure if this was intentional") — never use structured confidence markers. Explain "why" only when the reason isn't obvious or common knowledge — don't bloat comments with explanations everyone already knows. No praise, no emojis. One or two sentences per comment, max.

**Steps**

1. **Parse the PR URL** to extract `owner`, `repo`, and `pr_number`.

2. **Fetch PR context** — run these in parallel:

   ```bash
   # PR metadata (title, description, labels, branch, HEAD SHA)
   gh pr view {pr_number} --repo {owner}/{repo} --json title,body,labels,headRefName,headRefOid

   # Changed files with diffs
   gh api repos/{owner}/{repo}/pulls/{pr_number}/files --paginate --jq '.[] | {filename, status, patch}' > /tmp/pr-review-diff.json
   ```

   Then annotate every diff line with its real new-file line number, so sub-agents copy line numbers instead of counting from `@@` headers:

   ```bash
   python3 - <<'PY'
   import json, re
   files = [json.loads(l) for l in open('/tmp/pr-review-diff.json') if l.strip()]
   out = []
   for f in files:
       out.append(f"### FILE: {f['filename']} ({f['status']})")
       newln = None
       for l in (f.get('patch') or '').split('\n'):
           m = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)', l)
           if m:
               newln = int(m.group(1)); out.append(l); continue
           if newln is None:
               out.append(l); continue
           if l.startswith('-'):              # removed line — no new-file number
               out.append(f"      {l}")
           else:                              # added/context line — prefix real new-file line number
               out.append(f"{newln:>6} {l}"); newln += 1
       out.append('')
   open('/tmp/pr-review-annotated.txt', 'w').write('\n'.join(out))
   PY
   ```

   Pass the **annotated** diffs (from `/tmp/pr-review-annotated.txt`) to sub-agents.

3. **Filter to web-relevant files only** — skip files outside `web/` unless the PR is explicitly about root config. Focus on `.ts`, `.tsx`, `.css`, `.mjs`, `.json` changes. Skip generated files (`*.gen.*`).

4. **Build an intent brief** — a short summary (3-5 sentences) of:
   - What this PR is doing (from title, body, labels)
   - Which areas of the codebase it touches
   - Any focus context the user provided

   This brief is passed to every sub-agent so they understand the PR's purpose.

5. **Classify changed files** into two groups:
   - **Test files**: `*.test.*`, `*.spec.*`
   - **Source files**: everything else

6. **Spawn review sub-agents in parallel** using the Task tool. Each sub-agent receives the Voice instructions, the intent brief, its assigned **annotated** file diffs, the shared severity/format definitions below, and only the review rules for its domain.
   - **Code Quality Agent** — gets source file diffs + Code Quality Rules
   - **Intent & UX Agent** — gets source file diffs + Intent & UX Rules
   - **Testing Agent** — gets test file diffs + Testing Rules. **Skip entirely if no test files in the PR.**
   - **Architecture Agent** (`readonly: true`) — gets all file diffs + codebase access. No rules from this file — its job is to search the codebase for existing solutions, patterns, or utilities that overlap with or duplicate what the PR introduces. Flag only when the approach itself is wrong or when existing codebase utilities/patterns should be used instead.

   **Tool restrictions for sub-agents:**
   - Code Quality, Intent & UX, and Testing agents must include this instruction: "All diffs you need are provided below. Do NOT use Read, Grep, or Glob tools — work exclusively from the diffs in this prompt."
   - Architecture Agent must include this instruction: "The PR diffs are provided below for reference. You MUST search the broader codebase to find existing patterns, utilities, or solutions that overlap with what the PR introduces. Use Read, Grep, and Glob freely."

   Each sub-agent prompt must include:

   **Severity tags (internal — used by sub-agents only, translated at merge time):**
   - `[blocking]` — Must fix. Bugs, incorrect patterns, violations of core conventions.
   - `[suggestion]` — Should consider. Better abstractions, cleaner patterns, architectural improvements.
   - `[nit]` — Minor. Naming, formatting, small simplifications.
   - `[question]` — Needs clarification. Intent unclear, seems unrelated, or potentially unintentional.

   **Output format for each sub-agent** — return findings grouped by file path, each as:
   `- [severity] Line N: description`
   `N` is the number printed to the **left of the line you're flagging** in the annotated diff — copy it verbatim, do not count or compute it. If the code isn't in any diff hunk (no number on the left), use `[not-in-diff]` instead of a line number.

7. **Merge findings** from all sub-agents:
   - If two agents flagged the same code for the same underlying issue, merge into one finding with the higher severity and note both perspectives.
   - Sort by severity: blocking first, then suggestions, nits, questions.
   - **Translate severity tags to final format:** strip the `[blocking]` and `[suggestion]` prefixes entirely (no prefix in output). Convert `[nit]` to `nit:` and `[question]` to `Question:`.

8. **Output the review** in the format specified at the bottom. Prepend a metadata header as the very first line of the review output (before any findings):
   ```
   <!-- pr:{owner}/{repo}/{pr_number} sha:{headSha} -->
   ```
   This is invisible in chat and used by `/post-pr-review` to extract PR metadata.

---

## Code Quality Rules

_Assigned to the Code Quality Agent. Covers TypeScript patterns, React Query, component design, and codebase conventions._

### TypeScript Strictness

- **No `as` assertions.** Flag every use of `as`. Suggest Zod parsing, type guards, or fixing the upstream type instead.
- **No `any`.** Flag every `any`. Suggest proper types, generics, or `unknown` with narrowing.
- **No unnecessary `unknown`.** If the shape is known, type it properly.
- **Type constants and config objects** so typos are caught at compile time, not runtime.
- **Prefer exhaustive `switch`** over if/else chains so TypeScript catches unmatched cases when types expand.
- **No fallback on exhaustively-typed lookups.** If a const map covers all possible keys, don't add `??` fallback — it's dead code that hides type gaps.

### React Query Is the Only Way to Call APIs

- **Never call SDK/API directly** in components or event handlers. Always use `useQuery` / `useMutation` from React Query.
- **Use `select`** to transform query data instead of `useMemo` on the raw response.
- **Use `variables` from `useMutation`** to track submitted values instead of a separate `useState`.
- **Use `combine` with `useQueries`** when merging multiple queries.
- **Prefer query invalidation** over optimistic updates unless there's a clear UX justification.
- **Don't create custom query keys** when generated `queryOptions` already provide them.

### Component Architecture

- **Break large conditional blocks** into sub-components for readability.
- **Reduce state count.** Flag components with many `useState` calls. Ask:
  - Can related states be combined into one object?
  - Can React Query handle loading/error/data states instead?
  - Can state be derived from existing data instead of synced?
- **No boolean props to switch behavior.** Prefer enums or `mode: 'view' | 'edit'` so the pattern scales when a third option appears.
- **Make required props required.** Don't make a prop optional and pass a no-op — make it optional or split the component.
- **Don't pass hooks as props.** Flag and question this pattern.
- **Hooks should never be called conditionally.** This violates the Rules of Hooks.

### Avoid `useEffect` When React Patterns Suffice

- **Adjust state during render** instead of syncing with `useEffect` — see React docs: "You Might Not Need an Effect".
- **Use `key` to reset component state** instead of `useEffect` watching a prop.
- **Derive values during render** instead of storing them in state and syncing with effects.

### Use Existing Abstractions

- **Before writing any utility function**, check the project's existing dependencies. These libraries cover most common needs: `es-toolkit`, `react-use`, `use-debounce`, `date-fns` / `date-fns-tz`, `fast-equals`.

**Key internal abstractions:**

- **Domain form fields** (`InputField`, `RichTextEditorField`, `CheckboxField`, etc. from `@/components/form-field/`) — not raw Radix inputs inside `FormField`.
- Flag any case where existing codebase helpers or dependencies are being reinvented.

### Naming Conventions

- **`use` prefix is reserved for hooks.** Never name a regular function `useSomething`.
- **Schemas start with capital letters** (e.g., `const UserSchema = z.object({...})`).
- **Constants use `SCREAMING_SNAKE_CASE`.**
- **UI-only keys use `camelCase`**, even if BE sends `snake_case`.
- **Destructure and rename loading states** from different queries so it's clear which query they belong to (e.g., `isPending: isAccountLoading` and `isPending: isContactLoading`).
- **Name functions/types for their domain**, not their implementation. Avoid generic names like `isIAMPending` when `isAdminPermissionsLoading` is clearer.
- **Flag confusingly similar names** in the same scope — sibling functions or variables should be immediately distinguishable without reading their implementations.

### Static Values Outside Render

- **Move constant arrays, objects, regex, and templates outside components/functions** if they don't depend on props/state. They get recreated on every render otherwise.
- Flag `useMemo` wrapping static data that should just be a module-level constant.

### React Query State Semantics

- **`isLoading` vs `isPending` vs `isFetching`** — flag redundant checks. `isFetching` is true during all fetches; `isPending || isFetching` is redundant unless `enabled: false` is used.
- **Use `isLoading`** (which is `isPending && isFetching`) for initial load states instead of combining flags manually.

### Don't Mutate Props

- If a function receives an array or object parameter, copy it before modifying. Never mutate arguments directly.

### Prefer Modern APIs

- **`toSorted()`** over `sort()` (avoids mutation).
- **`replaceAll()`** over chained `replace()`.
- **`Array.from()`** over push loops when building arrays.
- **`array.at(-1)`** over `array[array.length - 1]`.
- **Destructuring** over repeated property access.
- **Default parameters** over `??` chains in function bodies — push defaults to the signature or type definition.

---

## Intent & UX Rules

_Assigned to the Intent & UX Agent. Covers questioning intent, code hygiene, UX patterns, and URL state._

### Questioning Intent

- **Unrelated changes** — flag files/hunks that seem unrelated to the PR's purpose as `[question]`.
- **Removed code** — if code, comments, or components are deleted, ask if it was intentional.
- **Changed logic flow** — if a component's rendering _conditions_ or _data flow_ changed and it seems unrelated to the PR's purpose, ask if it was intentional. Do NOT question visual/styling changes.
- **Templated content** — when a file is clearly derived from another adapter/domain, flag user-facing strings, variable names, or domain references that weren't updated to match the new context.

### Code Hygiene

- **Remove `console.log`** and debug statements.
- **Remove unused state, setters, interfaces, imports, variables.**
- **Remove commented-out code.** Use version control, not comments, to preserve old code.
- **Flag unnecessary re-exports.** If a module's only purpose is `export { X } from './other'` and callers could import directly, question whether the indirection layer is justified.
- **Don't keep "will use later" code.** Dead code should be deleted.
- **Fix typos** in user-facing strings and variable names.
- **Add comments for non-obvious code** — regex patterns, workarounds, and intentional `refetchOnWindowFocus: false` overrides should have a comment explaining why.

### UX Awareness

- **Inline errors for forms**, not toasts. Toast is for async operations, not form validation.
- **`!important` in Tailwind** — always flag and ask why it's needed. It almost never is.
- **Arbitrary Tailwind values** like `[13px]` — prefer extending the Tailwind config with design tokens.

### NUQS (URL State)

- **Use `nuqs` for all URL state.** Don't use `useSearchParams` or manual query string parsing.
- **Use the correct parser** — e.g., `parseAsBoolean` for booleans instead of comparing strings like `edit === "true"`.
- **Define query state schemas adjacent to the route file.**
- **`setQueryStates` supports partial updates** — no need to spread `...prev`.

---

## Testing Rules

_Assigned to the Testing Agent. Only used when the PR contains test files (`*.test.*`, `*.spec.*`)._

- **Never mock components.** Tests should render real components.
- **Never mock helper functions.** Let the real implementation run.
- **Avoid `getByTestId`, `querySelector`, and `data-testid`.** Prefer accessible queries: `getByRole`, `getByText`, `getByLabelText`, `getByPlaceholderText`.
- **No manual timeouts** (`setTimeout`, hardcoded delays) in tests. Use `expect.poll`, `waitFor`, or Vitest's async utilities.
- **Prefer `userEvent.type`** over `fireEvent.change` for typing interactions.
- **No mocking `useRouter`, `useParams`** unless verified as the recommended approach.

---

## Output Format

Group findings by file path. Within each file, list findings in order of severity (blocking first, then suggestions, nits, questions). Use this format:

```
## `web/components/example/example-component.tsx`

- Line 42: Using `as Status` here — a type guard would be safer.

- Line 18: This would read cleaner with `select` in useQuery instead of the extra `useMemo`.

- nit: Line 7: Schema name should be `FormSchema`.

- Question: Line 55: The progress bar got removed — intentional?
```

If a file has no findings, skip it entirely.
