---
name: update-pr-review
description: Learn from PR comments to improve the /pr-review skill
disable-model-invocation: true
---

Analyze comments on a reviewed PR to discover patterns, corrections, or gaps in the `/pr-review` skill's rules — then propose targeted updates.

**Input**: The argument after `/update-pr-review` is the GitHub PR URL.

**Steps**

1. **Parse the PR URL** to extract `owner`, `repo`, and `pr_number`.

2. **Fetch PR comments** using GitHub CLI (run all four in parallel):
   ```bash
   # Get the authenticated user's login
   gh api user --jq '.login' > /tmp/pr-review-user.txt

   # Review comments (inline on diffs)
   gh api repos/{owner}/{repo}/pulls/{pr_number}/comments --paginate > /tmp/pr-review-comments.json

   # Issue-level comments (top-level conversation)
   gh api repos/{owner}/{repo}/issues/{pr_number}/comments --paginate > /tmp/pr-issue-comments.json

   # Review summaries (approve/request-changes bodies)
   gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews --paginate > /tmp/pr-reviews.json
   ```

   After fetching, **filter all comments to only those authored by the authenticated user**. Discard comments from other reviewers, bots, and the PR author.

3. **Read the current `pr-review` skill's `SKILL.md`** (locate the `pr-review` skill; do not assume a fixed path).

4. **Analyze every comment** looking for signals in these categories:

   **A. Missing rules** — The reviewer flagged something the `/pr-review` command has no rule for.
   - Example: Reviewer says "avoid nested ternaries" but there's no rule about ternary nesting.

   **B. Rules that are too strict** — The reviewer explicitly approved or defended a pattern that `/pr-review` would flag.
   - Example: A rule says "no `as` assertions" but the reviewer accepted `as const` in a specific context.

   **C. Rules that are too loose** — The reviewer flagged something more specific than existing rules cover.
   - Example: There's a generic "use React Query" rule but the reviewer also enforces specific `staleTime` / `gcTime` defaults.

   **D. Wrong severity** — The reviewer treated something as blocking that `/pr-review` considers a nit, or vice versa.
   - Example: `/pr-review` treats schema naming as `[nit]` but the reviewer consistently requests changes for it.

   **E. Missing abstractions** — The reviewer pointed to codebase utilities, components, or patterns that aren't listed in "Use Existing Abstractions".
   - Example: Reviewer says "use `formatCurrency` helper" but it's not in the review rules.

   **F. Outdated rules** — Comments suggest a rule no longer applies (deprecated API, removed utility, changed convention).

   **G. New patterns** — The reviewer enforces a coding pattern or convention not captured anywhere in the rules.

   Ignore comments that are:
   - Pure discussion / questions without a clear standard
   - One-off situational feedback that wouldn't generalize
   - Automated bot comments (CI, linters, coverage)

5. **Present findings** grouped by category (A–G above). For each finding:
   - Quote the relevant comment (author, file, line if available)
   - State the current rule (or lack thereof)
   - Propose the specific change to `pr-review.md` (add / modify / remove / re-severity)
   - Mark confidence: `high` (clear pattern, multiple signals) or `medium` (single instance but strong signal)

   Format:
   ```
   ### [Category] Finding title

   **Comment**: "@reviewer on `file.tsx` L42: 'Don't use `useMemo` here — this is a static array, move it outside the component.'"
   **Current rule**: "Move constant arrays ... outside components" (Static Values Outside Render)
   **Gap**: Rule exists but doesn't mention `useMemo` wrapping static data specifically.
   **Proposed change**: Add bullet: "Flag `useMemo` wrapping static data that should just be a module-level constant."
   **Confidence**: high
   ```

6. **Ask for confirmation** before making any changes. Present a numbered list of all proposed changes and ask which ones to apply. Wait for my response.

7. **Apply confirmed changes** to the `pr-review` skill's `SKILL.md`:
   - For new rules: add them under the most appropriate existing section, or create a new section if none fits.
   - For modified rules: edit the specific bullet in place.
   - For removed rules: delete the bullet (or section if empty).
   - For severity changes: note the new severity expectation in the rule text.
   - Preserve the existing formatting, heading structure, and style.

8. **Output a changelog** summarizing what was updated:
   ```
   ## Changes applied to /pr-review

   - **Added** "Avoid nested ternaries" rule under Component Architecture
   - **Updated** Static Values section to also flag `useMemo` on constants
   - **Added** `formatCurrency` to Use Existing Abstractions
   ```

---

## Guidelines

- **No changes is a valid outcome.** If the comments don't reveal any gaps, incorrect rules, or new patterns, say so and stop. Don't force-fit changes just to produce output.
- **Be conservative.** Only propose changes backed by concrete evidence from the comments. Don't invent rules from thin air.
- **Generalize, don't copy.** Turn specific feedback into reusable rules. "Don't use `dayjs` here, use `formatRelativeDate`" becomes a rule about using the codebase's date formatting utilities.
- **Respect the voice.** The review rules are written in a direct, imperative style. Match that tone in any additions.
- **One finding per issue.** Don't bundle multiple unrelated observations into one finding.
- **Deduplicate.** If multiple comments point to the same gap, consolidate into one finding with all supporting quotes.
