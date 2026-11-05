---
name: pr-review
disable-model-invocation: true
---

Review a pull request against my review standards using specialized sub-agents that run in parallel, merge and deduplicate findings, then post them as a GitHub review.

**Input**: The argument after `/pr-review` is the GitHub PR URL. Optionally, a second sentence can provide focus context (e.g., "focus on the new dialog component") or the review mode (`draft` or `submitted`, default `submitted`).

**Work directory**: `{dir}` is the absolute path of your scratchpad directory (`/tmp` if you have none).

**Voice** — include in every sub-agent prompt:

Write like a friendly senior engineer reviewing a teammate's PR. Be direct, concise, and conversational. Say "this" not "this code block." Vary your phrasing — no two comments should sound templated. When you're unsure, express it naturally ("I think," "looks like," "not sure if this was intentional") — never use structured confidence markers. Explain "why" only when the reason isn't obvious or common knowledge — don't bloat comments with explanations everyone already knows. No praise, no emojis. One or two sentences per comment, max.

**Steps**

1. **Prepare the PR**:

   ```bash
   python3 scripts/prep.py {pr_url} --out {dir}
   ```

   It writes the annotated source and test diffs to `{dir}/pr-review-src.txt` and `{dir}/pr-review-test.txt`. It also prints the PR context and worktree path and status needed by later steps. It skips generated and large data files and lists them. If a skipped file matters to the PR, read it in the worktree.

2. **Build an intent brief**: a short summary (3-5 sentences) of:
   - What this PR does (from title, body, labels)
   - Which areas of the codebase it touches
   - Any focus context the user gave

3. **Spawn review sub-agents in parallel.** If the PR changes no application source (only CI, config, scripts, or docs), skip this step and review the diff yourself with the same severity tags. Each sub-agent gets the Voice block word for word, the intent brief, the path of its diff file, the shared severity and format definitions below, and only the review rules for its domain.
   - **Code Quality Agent**: `pr-review-src.txt` + Code Quality Rules
   - **Intent & UX Agent**: `pr-review-src.txt` + Intent & UX Rules
   - **Testing Agent**: `pr-review-test.txt` + Testing Rules. **Skip it if the PR has no test files.**
   - **Architecture Agent** (`readonly: true`): both diff files + codebase access. No rules from this file. Its job is to search the codebase for existing solutions, patterns, or utilities that overlap with or duplicate what the PR adds. Flag only when the approach itself is wrong or when existing utilities or patterns should be used instead.

   **Tool restrictions for sub-agents:**
   - Code Quality, Intent & UX, and Testing agents get this instruction: "Read only your diff file. Do NOT use Grep or Glob. Work only from that diff."
   - Architecture Agent gets this instruction: "Read the PR diffs from your diff files. You MUST search the codebase in `{dir}/pr-<n>/` (the PR head) to find existing patterns, utilities, or solutions that overlap with what the PR adds. Use Read, Grep, and Glob freely. Do not search outside that folder." If step 1 skipped the worktree, tell it to search the current checkout and to remember that it is not the PR head.

   Each sub-agent prompt must include:

   **Severity tags:**
   - `[blocking]` — Must fix. Bugs, incorrect patterns, violations of core conventions.
   - `[suggestion]` — Should consider. Better abstractions, cleaner patterns, architectural improvements.
   - `[nit]` — Minor. Naming, formatting, small simplifications.
   - `[question]` — Needs clarification. Intent unclear, seems unrelated, or potentially unintentional.

   **Output format for each sub-agent** — return findings grouped by file path, each as:
   `- [severity] Line N: description`
   `N` is the number printed to the **left of the line you're flagging** in the annotated diff — copy it verbatim, do not count or compute it. If the code isn't in any diff hunk (no number on the left), use `[not-in-diff]` instead of a line number.

   Wait for the completion notice of each sub-agent. Do not schedule wakeups or poll for results.

4. **Merge and verify findings** from all sub-agents:
   - If two agents flagged the same code for the same issue, merge them into one finding with the higher severity and keep both perspectives.
   - Verify each `[blocking]` and `[suggestion]` finding against the code at the PR head (`{dir}/pr-<n>/`, or the diff if step 1 skipped the worktree) and, for library behavior, against its source in `node_modules`. Keep a finding that you confirmed. Drop a finding that the code disproves. If you cannot confirm a finding that still matters, post it as a question, not as `[blocking]`.
   - Cut each comment to one or two sentences, as the Voice requires.
   - Sort by severity: blocking first, then suggestions, nits, questions.
   - Write the findings to `{dir}/findings.json` as `[{"path", "line", "body"}]`. `line` is `null` for `[not-in-diff]`. Add no attribution such as "[Comment made with Cursor]."

5. **Post the review**:

   ```bash
   python3 scripts/post.py {pr_url} {dir}/findings.json --out {dir}
   ```

   Add `--draft` for draft mode.

6. **Report** the review link, the review mode, the number of inline comments, and the number of findings in the review body. For `draft`, remind the user to open GitHub and click "Submit review" to make it visible.

---

## Code Quality Rules

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
- **Don't create custom query keys or hand-write a `queryFn`** when generated `queryOptions` already provide them.

### Component Architecture

- **Break large conditional blocks** into sub-components for readability.
- **Reduce state count.** Flag components with many `useState` calls. Ask:
  - Can related states be combined into one object?
  - Can React Query handle loading/error/data states instead?
  - Can state be derived from existing data instead of synced?
- **No boolean props to switch behavior.** Prefer enums or `mode: 'view' | 'edit'` so the pattern scales when a third option appears.
- **Keep domain logic out of shared/common components.** Flag domain-specific branches in a component meant to be generic — push them to the caller.
- **Make required props required.** If every caller needs a callback, require it instead of accepting a no-op. If the behavior is optional, omit the no-op or split the component.
- **Don't pass hooks as props.** Flag and question this pattern.
- **Hooks should never be called conditionally.** This violates the Rules of Hooks.

### Avoid `useEffect` When React Patterns Suffice

- **Adjust state during render** instead of syncing with `useEffect` — see React docs: "You Might Not Need an Effect".
- **Use `key` to reset component state** instead of `useEffect` watching a prop.
- **Derive values during render** instead of storing them in state and syncing with effects.

### Use Existing Abstractions

- **Before writing any utility function**, check the codebase helpers and existing dependencies, and flag reinventions. These libraries cover most common needs: `es-toolkit`, `react-use`, `use-debounce`, `date-fns` / `date-fns-tz`, `fast-equals`.
- **Prefer a schema-driven form abstraction** (react-hook-form + Zod style) over manual form state built from `useState`/`useRef` + hand-rolled validation.
- **Single source of truth for derived values.** If the same non-trivial derivation or fallback is repeated across call sites, extract it into one helper/selector — or compute it once at the parent/data boundary and pass it down — so a site can't be missed.

**Key internal abstractions:**

- **Domain form fields** (`InputField`, `RichTextEditorField`, `CheckboxField`, etc. from `@/components/form-field/`) — not raw Radix inputs inside `FormField`.

### Naming Conventions

- **`use` prefix is reserved for hooks.** Never name a regular function `useSomething`.
- **Schemas start with capital letters** (e.g., `const UserSchema = z.object({...})`).
- **Constants use `SCREAMING_SNAKE_CASE`.**
- **UI-only keys use `camelCase`**, even if BE sends `snake_case`.
- **Destructure and rename loading states** from different queries so it's clear which query they belong to (e.g., `isPending: isAccountLoading` and `isPending: isContactLoading`).
- **Name functions/types for their domain**, not their implementation. Avoid generic names like `isIAMPending` when `isAdminPermissionsLoading` is clearer.
- **Flag confusingly similar names** in the same scope — sibling functions or variables should be immediately distinguishable without reading their implementations.

### Static Values Outside Render

- **Move constant arrays, objects, regex, and templates outside components/functions** if they don't depend on props/state.
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

### Questioning Intent

- **Unrelated changes** — flag as `[question]` only a separate feature, fix, or refactor that belongs in its own PR. Do NOT flag small, harmless changes (formatting, reordering).
- **Removed code** — if code, comments, or components are deleted (not moved), ask if it was intentional.
- **Changed logic flow** — if a component's rendering _conditions_ or _data flow_ changed and it seems unrelated to the PR's purpose, ask if it was intentional. Do NOT question visual/styling changes.
- **Templated content** — when a file is clearly derived from another adapter/domain, flag user-facing strings, variable names, or domain references that weren't updated to match the new context.

### Code Hygiene

- **Remove `console.log`** and debug statements.
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

- **Never mock components.** Tests should render real components.
- **Never mock helper functions.** Let the real implementation run.
- **Avoid `getByTestId`, `querySelector`, and `data-testid`.** Prefer accessible queries: `getByRole`, `getByText`, `getByLabelText`, `getByPlaceholderText`.
- **No manual timeouts** (`setTimeout`, hardcoded delays) in tests. Use `expect.poll`, `waitFor`, or Vitest's async utilities.
- **Prefer `userEvent.type`** over `fireEvent.change` for typing interactions.
- **No mocking `useRouter`, `useParams`** unless verified as the recommended approach.
