---
name: update-pr-review
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

   # Thread resolution state (resolved/outdated) — high-signal verdicts
   gh api graphql -f query='query($o:String!,$r:String!,$n:Int!){repository(owner:$o,name:$r){pullRequest(number:$n){reviewThreads(first:100){nodes{isResolved isOutdated comments(first:1){nodes{databaseId}}}}}}}' -f o={owner} -f r={repo} -F n={pr_number} > /tmp/pr-threads.json
   ```

   After fetching, **thread the comments** — group every reply to its parent via `in_reply_to_id`, and attach each thread's `isResolved`/`isOutdated` state. Keep the PR author's and other people's replies; they carry the **verdict**. Only discard automated bot/CI/coverage comments. Split what remains into two sets:
   - **My comments** — top-level comments authored by the authenticated user, each with its reply thread and resolution state. The **verdict** on a comment is read from these signals, in order of trust: (1) the author's **reply text**, (2) whether the **flagged code actually changed** (`isOutdated` is a hint that it did; confirm against the latest diff when it matters), (3) `isResolved` last. Authors routinely fix code without clicking "Resolve," so an **unresolved thread is not a rebuttal** — never infer "wrong" or "ignored" from missing resolution alone.
   - **Others' comments** — top-level comments from other human reviewers, which teach the skill new standards.

3. **Read the current `pr-review` skill's `SKILL.md`** (locate the `pr-review` skill; do not assume a fixed path).

4. **Audit my own comments against their verdicts.** For each of my comments, read the **verdict** (reply text first, then whether the code changed, then resolution — see step 2) and classify:
   - **Accepted / fixed** → a "done"-style reply, or the flagged code changed. The rule (if any) behind the comment held up. No change.
   - **Confirmed as a question** → verification comment that checked out. No change.
   - **No reply and code unchanged** → genuinely ambiguous; don't guess. Treat as no signal rather than a rebuttal.
   - **Rebutted** → the author defended the pattern or called the comment wrong *in a reply*. Now make the distinction that governs this whole skill: **did a rule drive the comment, or not?**
     - A `/pr-review` rule produced it → candidate to soften (feed into category B below).
     - No rule drove it — a reasonable one-off miss on info the reviewer couldn't see → **expected; propose nothing.** A wrong comment is only a skill defect when a wrong rule caused it.

5. **Analyze others' comments** looking for signals in these categories (also absorb any rule-driven rebuttals from step 4):

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

6. **Present findings** grouped by category (A–G above). For each finding:
   - Quote the relevant comment (author, file, line if available)
   - State the current rule (or lack thereof)
   - Propose the specific change to the `pr-review` `SKILL.md` (add / modify / remove / re-severity)
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

7. **Ask for confirmation** before making any changes. Present a numbered list of all proposed changes and ask which ones to apply. Wait for my response.

8. **Apply confirmed changes** to the `pr-review` skill's `SKILL.md`:
   - For new rules: add them under the most appropriate existing section, or create a new section if none fits.
   - For modified rules: edit the specific bullet in place.
   - For removed rules: delete the bullet (or section if empty).
   - For severity changes: note the new severity expectation in the rule text.
   - Preserve the existing formatting, heading structure, and style.

9. **Output a changelog** summarizing what was updated:
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
