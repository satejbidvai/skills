from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

RETRYABLE = re.compile(r"HTTP 5\d\d|secondary rate limit|stream error|couldn't respond to your request in time", re.I)
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def parse_pr_url(url: str) -> tuple[str, int]:
    match = re.search(r"github\.com/([^/]+/[^/]+)/pull/(\d+)", url)
    if not match:
        die(f"not a GitHub PR URL: {url}")
    return match.group(1), int(match.group(2))


def run(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True)


def gh(args: list[str], retries: int = 4) -> str:
    """Run gh. Retry on 5xx and secondary rate limits, which GitHub returns on big PRs."""
    for attempt in range(1, retries + 1):
        result = run(["gh", *args])
        if result.returncode == 0:
            return result.stdout
        message = (result.stderr or result.stdout).strip()
        if attempt == retries or not RETRYABLE.search(message):
            die(f"gh {' '.join(args[:3])} failed: {message[:500]}")
        time.sleep(attempt * 5)
    return ""


def read_json(path: Path) -> object:
    if not path.exists():
        die(f"{path} not found. Run scripts/prep.py with the same --out first.")
    return json.loads(path.read_text())


def diff_lines(patch: str) -> list[str]:
    """Split a patch on newlines only. str.splitlines() also splits on \\r, \\f and \\u2028 inside a line."""
    lines = patch.split("\n")
    return lines[:-1] if lines and lines[-1] == "" else lines


def commentable_lines(patch: str) -> set[int]:
    """New-file lines that GitHub accepts for a RIGHT-side inline comment."""
    lines: set[int] = set()
    line = None
    for raw in diff_lines(patch):
        hunk = HUNK.match(raw)
        if hunk:
            line = int(hunk.group(1))
        elif line is not None and not raw.startswith(("-", "\\")):
            lines.add(line)
            line += 1
    return lines
