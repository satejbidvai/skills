"""Fetch a PR for review.

Writes to --out:
  meta.json              repo, number, head SHA, worktree path (read by post.py)
  files.json             GitHub changed-file patches used for inline line checks (read by post.py)
  pr-review-src.txt      annotated source diffs
  pr-review-test.txt     annotated test diffs (*.test.*, *.spec.*)
  pr-<n>/                detached worktree at the PR head, when run inside a checkout of the PR's repo

In the annotated diffs, each added or context line starts with its new-file line number.
Removed lines have no number. GitHub patches are authoritative; a local diff fills only missing patches.
Generated files (lockfiles, *.gen.*, *.min.*, *.map, *.snap) and JSON files with over 400 changed lines are skipped.
Prints the PR header, the file split, the skipped files, and the PR body.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep __pycache__ out of the skill folder

from common import HUNK, diff_lines, die, gh, parse_pr_url, run

TEST_FILE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$")
GENERATED = re.compile(
    r"(^|/)(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?)$|\.(gen|min)\.|\.(map|snap)$"
)
LARGE_DATA_LINES = 400


def skip_reason(file: dict) -> str | None:
    if GENERATED.search(file["path"]):
        return "generated"
    if file["path"].endswith(".json") and int(file["additions"]) + int(file["deletions"]) > LARGE_DATA_LINES:
        return "large data file"
    return None


def annotate(file: dict) -> str:
    out = [f"### FILE: {file['path']} ({file['status']})"]
    if not file["patch"]:
        return "\n".join([*out, "[patch unavailable: binary or too large for the GitHub files API]"]) + "\n"
    if file.get("patch_source") == "local":
        out.append("[local fallback patch: findings will be posted in the review body]")
    line = None
    for raw in diff_lines(file["patch"]):
        hunk = HUNK.match(raw)
        if hunk:
            line = int(hunk.group(1))
            out.append(raw)
        elif line is None:
            if raw.startswith("Binary files"):  # skip git's diff/index/---/+++ header lines
                out.append(raw)
        elif raw.startswith("\\"):
            out.append(raw)
        elif raw.startswith("-"):
            out.append(f"       {raw}")
        else:
            out.append(f"{line:>6} {raw}")
            line += 1
    return "\n".join(out) + "\n"


def find_remote(repo: str) -> tuple[str, str] | None:
    """Return (repo root, remote name) when the current directory is a checkout of `repo`."""
    root = run(["git", "rev-parse", "--show-toplevel"])
    if root.returncode != 0:
        return None
    pattern = re.compile(rf"github\.com[:/]{re.escape(repo)}(\.git)?/?$", re.I)
    for name in run(["git", "remote"]).stdout.split():
        if pattern.search(run(["git", "remote", "get-url", name]).stdout.strip()):
            return root.stdout.strip(), name
    return None


def parse_name_status(raw: str) -> list[dict]:
    fields = raw.split("\0")
    files = []
    index = 0
    statuses = {
        "A": "added", "C": "copied", "D": "removed", "M": "modified",
        "R": "renamed", "T": "changed", "U": "unmerged", "X": "unknown",
    }
    while index < len(fields) and fields[index]:
        code = fields[index]
        index += 1
        if code[0] in ("R", "C"):
            previous, path = fields[index:index + 2]
            index += 2
        else:
            previous, path = None, fields[index]
            index += 1
        files.append({"path": path, "previous_path": previous, "status": statuses.get(code[0], code)})
    return files


def parse_numstat(raw: str) -> list[tuple[str, str]]:
    fields = raw.split("\0")
    counts = []
    index = 0
    while index < len(fields) and fields[index]:
        additions, deletions, path = fields[index].split("\t", 2)
        index += 1
        if not path:
            index += 2  # old and new paths for a rename or copy
        counts.append((additions, deletions))
    return counts


def local_files(root: str, base: str, head: str, paths: list[str]) -> list[dict]:
    command = ["git", "diff", "--no-ext-diff", "--no-textconv", "--find-renames", base, head]
    pathspec = ["--", *paths]
    status = run([*command, "--name-status", "-z", *pathspec], cwd=root)
    numstat = run([*command, "--numstat", "-z", *pathspec], cwd=root)
    patch = run([*command, "--patch", "--no-color", "--unified=3", *pathspec], cwd=root)
    if any(result.returncode != 0 for result in (status, numstat, patch)):
        return []

    files = parse_name_status(status.stdout)
    counts = parse_numstat(numstat.stdout)
    patches = [part for part in re.split(r"(?m)(?=^diff --git )", patch.stdout) if part]
    if len(files) != len(counts) or len(files) != len(patches):
        return []
    for file, (additions, deletions), file_patch in zip(files, counts, patches):
        file.update({"additions": additions, "deletions": deletions, "patch": file_patch})
    return files


def make_worktree(
    found: tuple[str, str] | None, repo: str, number: int, head_sha: str, out: Path,
) -> tuple[str | None, str]:
    if not found:
        return None, f"worktree: skipped (current directory is not a checkout of {repo}); using GitHub file patches"
    root, remote = found
    worktree = out / f"pr-{number}"
    run(["git", "worktree", "prune"], cwd=root)
    previous = out / "meta.json"
    if previous.exists():
        old = json.loads(previous.read_text())
        old_root = old.get("repo_root") or root
        if old.get("worktree") and (old["worktree"] != str(worktree) or old_root != root):
            run(["git", "worktree", "remove", "--force", old["worktree"]], cwd=old_root)
        for key in ("head_ref", "base_ref"):
            if old.get(key):
                run(["git", "update-ref", "-d", old[key]], cwd=old_root)
    if worktree.exists():
        run(["git", "worktree", "remove", "--force", str(worktree)], cwd=root)
        if worktree.exists():
            die(f"{worktree} exists and is not a worktree. Remove it or use another --out.")
    head_ref = f"refs/pr-review/{number}/head"
    fetch = run(["git", "fetch", "-q", remote, f"+pull/{number}/head:{head_ref}"], cwd=root)
    if fetch.returncode != 0:
        die(f"git fetch PR head failed: {fetch.stderr.strip()[:300]}")
    if run(["git", "rev-parse", head_ref], cwd=root).stdout.strip() != head_sha:
        die("the PR head moved while preparing it. Run prep.py again.")
    # Skip hooks: the checkout is PR code, and repo hooks (lefthook) are slow and not needed to read files.
    add = run(
        ["git", "-c", "core.hooksPath=/dev/null", "worktree", "add", "-q", "--detach", str(worktree), head_ref],
        cwd=root,
    )
    if add.returncode != 0:
        die(f"git worktree add failed: {add.stderr.strip()[:300]}")
    return str(worktree), f"worktree: {worktree} (PR head, read-only; post.py removes it)"


def missing_patches(found: tuple[str, str], number: int, base_name: str, paths: list[str]) -> tuple[list[dict], str | None]:
    """Diff only the files GitHub returned no patch for. A failure here leaves those files without a patch."""
    root, remote = found
    head_ref = f"refs/pr-review/{number}/head"
    base_ref = f"refs/pr-review/{number}/base"
    if run(["git", "fetch", "-q", remote, f"+refs/heads/{base_name}:{base_ref}"], cwd=root).returncode != 0:
        return [], None
    merge_base = run(["git", "merge-base", base_ref, head_ref], cwd=root)
    if merge_base.returncode != 0:
        return [], base_ref
    return local_files(root, merge_base.stdout.strip(), head_ref, paths), base_ref


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="GitHub PR URL")
    parser.add_argument("--out", required=True, help="work directory")
    args = parser.parse_args()

    repo, number = parse_pr_url(args.url)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    view = json.loads(
        gh(["pr", "view", str(number), "--repo", repo, "--json",
            "title,body,labels,author,headRefName,baseRefName,headRefOid,isDraft"])
    )
    head_sha = view["headRefOid"]
    api_files = [
        json.loads(line)
        for line in gh([
            "api", "--paginate", f"repos/{repo}/pulls/{number}/files",
            "--jq", '.[] | {path: .filename, status, additions, deletions, patch: (.patch // "")}',
        ]).split("\n")
        if line.strip()
    ]
    found = find_remote(repo)
    worktree, worktree_line = make_worktree(found, repo, number, head_sha, out)
    local, base_ref = [], None
    missing = [
        file["path"]
        for file in api_files
        if not file["patch"] and not skip_reason(file)
    ]
    if worktree and found and missing:
        local, base_ref = missing_patches(found, number, view["baseRefName"], missing)
    local_by_path = {file["path"]: file for file in local}
    review_files = []
    for file in api_files:
        review_file = dict(file)
        fallback = local_by_path.get(file["path"])
        if not review_file["patch"] and fallback and fallback["patch"]:
            review_file["patch"] = fallback["patch"]
            review_file["patch_source"] = "local"
        review_files.append(review_file)

    kept = [f for f in review_files if not skip_reason(f)]
    skipped = [(f["path"], skip_reason(f)) for f in review_files if skip_reason(f)]
    tests = [f for f in kept if TEST_FILE.search(f["path"])]
    sources = [f for f in kept if not TEST_FILE.search(f["path"])]

    (out / "files.json").write_text(json.dumps(api_files))
    (out / "pr-review-src.txt").write_text("\n".join(annotate(f) for f in sources))
    (out / "pr-review-test.txt").write_text("\n".join(annotate(f) for f in tests))
    (out / "meta.json").write_text(json.dumps({
        "repo": repo, "number": number, "sha": head_sha,
        "worktree": worktree, "repo_root": found[0] if found else None,
        "head_ref": f"refs/pr-review/{number}/head" if worktree else None,
        "base_ref": base_ref,
    }))

    def row(f: dict) -> str:
        return f"  {f['status'][0].upper()} +{f['additions']} -{f['deletions']} {f['path']}"

    labels = ", ".join(label["name"] for label in view["labels"])
    body = re.sub(r"<!--[\s\S]*?-->", "", view["body"] or "").strip()
    lines = [
        f"#{number}{' DRAFT' if view['isDraft'] else ''} {view['title']}",
        f"@{view['author']['login']} {view['headRefName']} -> {view['baseRefName']}"
        + (f"  labels: {labels}" if labels else ""),
        f"head: {head_sha}",
        f"src ({len(sources)}) -> {out / 'pr-review-src.txt'}",
        *map(row, sources),
        f"test ({len(tests)}) -> {out / 'pr-review-test.txt'}",
        *map(row, tests),
    ]
    if skipped:
        lines += [f"skipped ({len(skipped)}):", *(f"  {path} [{reason}]" for path, reason in skipped)]
    lines += [worktree_line, "body:", body or "(empty)"]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
