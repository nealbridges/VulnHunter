"""The one git implementation for VulnHunter Python runtimes.

Layer: CONTRACT+RUNTIME (plan §2.2, Phase 1 item 4a). Before this module,
~13 near-duplicate "clone a repo" implementations existed across ``vh``,
``harness``, and ``vulnhunter-agent``, differing in depth handling, option
ordering, auth, and error reporting — a fix in one (the ``--``
end-of-options separator, the depth flag) did not propagate.

Everything here:
- passes ``--`` before URLs and refs (fixes the URL-looks-like-an-option
  class of bugs),
- treats ``git`` as a resolved absolute path (Bandit B607 hygiene),
- reports failures as :class:`GitError` with the stage, command, and
  captured stderr — callers turn that into their own UX.

The generic workhorse is :func:`run_git`. Thin wrappers cover the common
intents (:func:`clone_shallow`, :func:`fetch_commit`, :func:`rev_parse`,
:func:`has_git`). Migration note: components may keep their own process
handling (streaming drains, timers) — this module covers process *setup*
and error taxonomy, not I/O pumping.
"""

from __future__ import annotations

import shutil
import subprocess


class GitError(RuntimeError):
    """A git operation failed. ``stage`` says which operation; ``cmd`` and
    ``stderr`` carry the evidence for the caller to report or log."""

    def __init__(
        self,
        stage: str,
        cmd: list[str],
        returncode: int | None = None,
        stderr: str = "",
    ) -> None:
        self.stage = stage
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        detail = stderr.strip() or f"exit {returncode}"
        super().__init__(f"git {stage} failed: {detail} (cmd: {cmd!r})")


#: End-of-options separator. Compose git argv with this between the flag
#: section and the "act on" section (URL/ref/path) so no URL or branch name
#: can ever be parsed as a flag (the #16-class bug).
SEP = "--"


def has_git() -> str | None:
    """Absolute path of git, or None when absent (mirrors shutil.which)."""
    return shutil.which("git")


def run_git(
    args: list[str],
    *,
    stage: str,
    cwd: str | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """Run ``git <args>`` with the end-of-options separator applied.

    ``--`` separates options from the "what to act on" section (URL, ref,
    path). The separator placement is the CALLER's job via :data:`SEP`:
    compose commands as ``["clone", "--depth", "1", SEP, url, dest]`` so
    the boundary is explicit and reviewable — no magic insertion (an
    auto-inserted ``--`` is how subtle flag/argument parsing bugs happen).
    """
    git = has_git()
    if not git:
        raise GitError(stage, ["git", *args], None, "git is not on PATH")
    argv = [git, *args]
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitError(stage, argv, None, f"timed out after {timeout}s") from exc
    if check and proc.returncode != 0:
        raise GitError(stage, argv, proc.returncode, proc.stderr or proc.stdout)
    return proc


def clone_shallow(url: str, dest: str, *, depth: int = 1) -> None:
    """Shallow-clone ``url`` into ``dest`` (the dominant pattern x13)."""
    run_git(["clone", "--depth", str(depth), SEP, url, dest], stage="clone")


def fetch_commit(repo_dir: str, commit_hash: str) -> None:
    """Fetch one exact commit at depth 1 (the fast path in harness/clone)."""
    run_git(
        ["fetch", "--depth", "1", "origin", SEP, commit_hash], stage="fetch-commit", cwd=repo_dir
    )


def rev_parse(repo_dir: str, rev: str) -> str:
    """Resolve ``rev`` inside ``repo_dir``; raises GitError when unknown."""
    proc = run_git(["rev-parse", "--verify", rev], stage="rev-parse", cwd=repo_dir)
    return proc.stdout.strip()
