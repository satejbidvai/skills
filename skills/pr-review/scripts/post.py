"""Post merged findings as one GitHub review, then remove the review worktree.

Run prep.py with the same --out first. This reads meta.json (head SHA, worktree) and files.json (diff lines).

findings.json: [{"path": "src/a.ts", "line": 12, "body": "..."}, ...]. Use "line": null for code not in the diff.
A finding whose line is in the diff becomes an inline comment. Every other finding goes into the review body
under a **`path`** heading. Leading severity tags and `Line N:` prefixes are removed from each body.

GitHub can return a 502 or 504 after creating a large review. Then this prints "posted".
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True  # keep __pycache__ out of the skill folder

from common import commentable_lines, die, gh, parse_pr_url, read_json, run

PREFIX = re.compile(r"^(\[(blocking|suggestion|nit|question)\]\s*|(nit|question):\s*|Line \d+(?:[-–]\d+)?:\s*)", re.I)
AMBIGUOUS_POST = re.compile(r"HTTP (502|504)\b", re.I)


def clean(body: str) -> str:
    body = body.strip()
    while PREFIX.match(body):
        body = PREFIX.sub("", body, count=1).strip()
    return body


def clean_up(meta: dict) -> list[str]:
    root = meta.get("repo_root")
    if not root:
        return []
    messages = []
    if meta.get("worktree"):
        result = run(["git", "worktree", "remove", "--force", meta["worktree"]], cwd=root)
        if result.returncode == 0:
            messages.append(f"worktree removed: {meta['worktree']}")
        else:
            messages.append(f"worktree not removed: {result.stderr.strip()[:200]}")
    for key in ("head_ref", "base_ref"):
        if meta.get(key):
            result = run(["git", "update-ref", "-d", meta[key]], cwd=root)
            if result.returncode != 0:
                messages.append(f"ref not removed: {meta[key]}: {result.stderr.strip()[:200]}")
    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="GitHub PR URL")
    parser.add_argument("findings", help="path to findings.json")
    parser.add_argument("--out", required=True, help="work directory used by prep.py")
    parser.add_argument("--draft", action="store_true", help="leave the review PENDING")
    parser.add_argument("--dry-run", action="store_true", help="write review.json, do not post")
    args = parser.parse_args()

    repo, number = parse_pr_url(args.url)
    out = Path(args.out).resolve()
    meta = read_json(out / "meta.json")
    if (meta["repo"], meta["number"]) != (repo, number):
        die(f"{out} holds PR {meta['repo']}#{meta['number']}, not {repo}#{number}")
    valid = {f["path"]: commentable_lines(f["patch"]) for f in read_json(out / "files.json")}

    findings = read_json(Path(args.findings))
    if not isinstance(findings, list):
        die("findings.json must be a JSON array of {path, line, body}")

    inline = []
    moved: dict[str, list[str]] = defaultdict(list)
    moved_lines = []
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            die(f"findings.json item {index} must be an object")
        path = finding.get("path") or ""
        line = finding.get("line")
        raw_body = finding.get("body")
        if not isinstance(path, str):
            die(f"findings.json item {index} path must be a string")
        if line is not None and (not isinstance(line, int) or isinstance(line, bool)):
            die(f"findings.json item {index} line must be an integer or null")
        if not isinstance(raw_body, str):
            die(f"findings.json item {index} body must be a string")
        body = clean(raw_body)
        if not body:
            die(f"findings.json item {index} body must not be empty")
        if isinstance(line, int) and line in valid.get(path, ()):
            inline.append({"path": path, "line": line, "side": "RIGHT", "body": body})
        else:
            moved[path].append(body)
            moved_lines.append(f"  body: {path or '(general)'}" + (f":{line} (not in diff)" if line else ""))

    review_body = "\n\n".join(
        "\n".join(([f"**`{path}`**"] if path else []) + [f"- {body}" for body in bodies])
        for path, bodies in moved.items()
    )
    if not review_body and not inline:
        review_body = "No issues found."
    payload = {"commit_id": meta["sha"], "body": review_body, "comments": inline}
    if not args.draft:
        payload["event"] = "COMMENT"
    payload_file = out / "review.json"
    payload_file.write_text(json.dumps(payload))

    mode = "draft" if args.draft else "submitted"
    print(f"{mode}: {len(inline)} inline, {len(moved_lines)} in body -> {payload_file}")
    if moved_lines:
        print("\n".join(moved_lines))
    if args.dry_run:
        return

    current = json.loads(gh([
        "pr", "view", str(number), "--repo", repo, "--json", "headRefOid",
    ]))["headRefOid"]
    if current != meta["sha"]:
        print(
            f"warning: the PR head moved from {meta['sha']} to {current}; "
            "posting the review on the prepared commit",
            file=sys.stderr,
        )

    result = run([
        "gh", "api", f"repos/{repo}/pulls/{number}/reviews", "-X", "POST",
        "--input", str(payload_file), "--jq", ".html_url",
    ])
    message = (result.stderr or result.stdout).strip()
    if result.returncode != 0:
        if "pending review" in message.lower():
            die("you already have a pending review on this PR. Submit or delete it on GitHub, then run post.py again.")
        if not AMBIGUOUS_POST.search(message):
            die(f"review create failed: {message[:500]}")
        print(f"posted (GitHub timed out after creating the review: {message[:120]}).")
    else:
        print(result.stdout.strip())
    if args.draft:
        print('PENDING: open GitHub and click "Submit review" to publish it.')
    for status in clean_up(meta):
        print(status)


if __name__ == "__main__":
    main()
