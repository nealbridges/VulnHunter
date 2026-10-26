#!/usr/bin/env python3
"""Refuse a commit whose staged diff or message names a private scan identifier.

Why this exists: once a client string reaches a commit, GitHub serves that commit by SHA
forever. Rewriting history fixes the shipped tree but cannot retract the served commit --
`refs/pull/*` is read-only and unreachable objects stay served. The only cheap defence is
not to commit the string in the first place.

THIS FILE CONTAINS NO PLAINTEXT IDENTIFIER. It imports the repo's digest-only guard, so the
same property that keeps `agent/_banned_words.py` publishable keeps this hook publishable:
a regex listing the words would publish the very words it screens for.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

# Resolve the repo root via git, not via __file__: the script is copied into .git/hooks/, so
# its own location says nothing about where the package lives. A hook must work from anywhere.
_ROOT = subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
).stdout.strip()
sys.path.insert(0, str(pathlib.Path(_ROOT or ".") / "vulnhunter-agent"))

from agent._banned_words import banned_span_in  # noqa: E402

# `vulnhunter-fix` has its own gate numbering that happens to share a label with a scan run;
# it is excluded from every scan for that reason. This hook follows the same rule.
EXCLUDED_PREFIXES = ("vulnhunter-fix/",)
# The guard module is hex and prose about words; scanning it would be self-referential noise.
EXEMPT_FILES = {"vulnhunter-agent/agent/_banned_words.py"}


def _staged_text() -> str:
    """The CONTENT that would be committed, minus the exempt paths.

    Read the staged blob, not the diff. A diff shows deleted lines with a leading `-`, and those
    lines do not ship -- screening them would refuse a commit that only REMOVES a banned word,
    which is exactly backwards. What ships is the tree the commit would create.
    """
    paths = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()
    keep = [p for p in paths if not p.startswith(EXCLUDED_PREFIXES) and p not in EXEMPT_FILES]
    chunks: list[str] = []
    for rel in keep:
        blob = subprocess.run(
            ["git", "show", f":{rel}"], capture_output=True, text=True, check=False
        ).stdout
        chunks.append(blob)
    return "\n".join(chunks)


def main(argv: list[str]) -> int:
    problems: list[str] = []
    diff = _staged_text()
    if banned_span_in(diff):
        problems.append("staged diff")
    if len(argv) > 1:
        message = pathlib.Path(argv[1]).read_text(errors="replace")
        if banned_span_in(message):
            problems.append("commit message")
    if not problems:
        return 0
    print(
        "COMMIT REJECTED: a private scan identifier would enter permanent history.", file=sys.stderr
    )
    print(
        "GitHub serves every commit it has received by SHA forever, and history rewrite",
        file=sys.stderr,
    )
    print(
        "cannot retract a served commit. Found in: " + ", ".join(problems) + "\n", file=sys.stderr
    )
    print(
        "The matched word is recorded privately in product_docs/BANNED_WORDS.md.", file=sys.stderr
    )
    print("Rename it there, or rename it in the commit.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
