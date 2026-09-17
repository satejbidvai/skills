---
name: post-pr-review
disable-model-invocation: true
---

**Prerequisites**: Run `/pr-review <PR URL>` first in this conversation.

**Steps**

1. **Resolve the review mode** from the user's request as `draft` or `submitted`. Default to `submitted`.

2. **Parse the metadata header** from the `/pr-review` output. Look for the HTML comment:

   ```
   <!-- pr:{owner}/{repo}/{pr_number} sha:{headSha} -->
   ```

   Extract `owner`, `repo`, `pr_number`, and `headSha`. If not found, tell the user to run `/pr-review` first.

3. **Collect findings** from the `/pr-review` output. For each finding, extract:
   - `file`: from the `## \`web/...\`` heading
   - `line`: from the `Line N:` prefix, or `null` if the finding used `[not-in-diff]`
   - `body`: the finding text

   Findings without a file heading (PR-wide comments) go into the review `body`.

4. **Validate lines against the diff** — read `/tmp/pr-review-diff.json` (already written by `/pr-review`). Build a set of valid `{path, line}` pairs from the diff hunks. For each finding:
   - Line is in the valid set → inline comment: `{ path, line, side: "RIGHT", body }`
   - Path exists in the PR but line is not in the diff (or was `[not-in-diff]`) → **goes into the review `body`** under the file path heading (GitHub's API does not support file-level comments on reviews)
   - No path → goes into the review `body`

5. **Build the review payload** at `/tmp/pr-review.json`:
   - `commit_id`: the `headSha`
   - `body`: body-level findings formatted as file path headings (`**\`path/to/file.ts\`**`) followed by the finding text. Empty (`""`) if no body-level findings.
   - `comments`: only inline comments from step 4 (never use `subject_type: "file"` — the API rejects it)
   - **Strip prefixes from each comment body before posting:** remove `Line N:` (the inline placement makes it redundant), remove `nit:` and `Question:` prefixes
   - **Do not add any prefix or attribution** to the review body or comments (no "[Comment made with Cursor]" or similar)
   - For `draft`, omit the `event` field. This creates a PENDING review.
   - For `submitted`, set `"event": "COMMENT"`. This submits the review immediately.

6. **Create the review**:

   ```bash
   gh api repos/{owner}/{repo}/pulls/{pr_number}/reviews -X POST --input /tmp/pr-review.json
   ```

7. **Report** the review mode, the number of inline comments, and the number of findings in the review body. For `draft`, remind the user to open GitHub and click "Submit review" to make it visible.
