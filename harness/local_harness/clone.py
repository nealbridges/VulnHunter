"""Clone repositories at specific commit hashes for benchmarking.

Git call sites route through vulnhunter_common.gitops (the shared
implementation: absolute git path resolution, the explicit
end-of-options separator, and the GitError taxonomy) while keeping this
module's own strategy logic and timeout semantics.
"""

import os
import shutil
import subprocess

from vulnhunter_common import gitops

from .config import CLONE_BASE_DIR, CLONE_TIMEOUT


def parse_source_url(source_code_url):
    """Parse a benchmark source_code URL into (repo_url, commit_hash).

    Format: https://github.com/{org}/{repo}/tree/{commit_hash}
    """
    parts = source_code_url.rstrip("/").split("/")
    # parts: ['https:', '', 'github.com', org, repo, 'tree', commit_hash]
    repo_url = "/".join(parts[:5])
    commit_hash = parts[-1]
    repo_name = parts[4]
    return repo_url, repo_name, commit_hash


def target_dir_name(repo_name, commit_hash):
    """Generate a unique directory name for a repo at a specific commit."""
    return f"{repo_name}_{commit_hash[:8]}"


def is_at_commit(target_dir, commit_hash):
    """Check if an existing clone is at the expected commit."""
    try:
        result = gitops.run_git(
            ["rev-parse", "HEAD"],
            stage="rev-parse",
            cwd=target_dir,
            check=False,
            timeout=10,
        )
        return result.returncode == 0 and result.stdout.strip().startswith(commit_hash[:8])
    except (gitops.GitError, subprocess.TimeoutExpired, OSError):
        return False


def clone_at_commit(repo_url, commit_hash, target_dir):
    """Clone a repo at a specific commit hash.

    Strategy:
    1. Reuse if target exists at correct commit
    2. Fast path: git fetch --depth=1 origin <hash>
    3. Fallback: full clone + checkout

    Returns (target_dir, error_msg|None).
    """
    if os.path.isdir(target_dir):
        if is_at_commit(target_dir, commit_hash):
            print(f"  [clone] Reusing existing clone at correct commit: {target_dir}")
            return (target_dir, None)
        else:
            print(f"  [clone] Removing clone at wrong commit: {target_dir}")
            shutil.rmtree(target_dir)

    os.makedirs(CLONE_BASE_DIR, exist_ok=True)

    # Fast path: fetch single commit at depth=1
    print(f"  [clone] Trying fast fetch of {commit_hash[:8]} from {repo_url} ...")
    try:
        os.makedirs(target_dir, exist_ok=True)
        init = gitops.run_git(["init"], stage="init", cwd=target_dir, check=False, timeout=10)
        remote = gitops.run_git(
            ["remote", "add", "origin", gitops.SEP, repo_url],
            stage="remote-add",
            cwd=target_dir,
            check=False,
            timeout=10,
        )
        if init.returncode == 0 and remote.returncode == 0:
            result = gitops.run_git(
                ["fetch", "--depth=1", "origin", gitops.SEP, commit_hash],
                stage="fetch",
                cwd=target_dir,
                check=False,
                timeout=CLONE_TIMEOUT,
            )
            if result.returncode == 0:
                checkout = gitops.run_git(
                    ["checkout", "FETCH_HEAD"],
                    stage="checkout",
                    cwd=target_dir,
                    check=False,
                    timeout=30,
                )
                if checkout.returncode == 0:
                    print(f"  [clone] Fast fetch succeeded: {target_dir}")
                    return (target_dir, None)
    except (gitops.GitError, subprocess.TimeoutExpired, OSError):
        pass

    # Fast path failed — clean up and try full clone
    if os.path.isdir(target_dir):
        shutil.rmtree(target_dir)

    print("  [clone] Fast fetch failed, falling back to full clone ...")
    try:
        result = gitops.run_git(
            ["clone", gitops.SEP, repo_url, target_dir],
            stage="clone",
            check=False,
            timeout=CLONE_TIMEOUT,
        )
        if result.returncode != 0:
            error = result.stderr.strip() or f"git clone exited {result.returncode}"
            return (target_dir, error)

        # NOTE: git-checkout grammar is `git checkout [<tree-ish>] -- <pathspec>`.
        # A commit hash after `--` is parsed as a PATHSPEC and fails ("did not
        # match any file(s) known to git") — so the hash goes BEFORE the
        # separator (and may be followed by an empty pathspec). A hex SHA can
        # never start with '-', so no flag-ambiguity risk here.
        checkout = gitops.run_git(
            ["checkout", commit_hash, gitops.SEP],
            stage="checkout",
            cwd=target_dir,
            check=False,
            timeout=30,
        )
        if checkout.returncode != 0:
            error = checkout.stderr.strip() or f"git checkout exited {checkout.returncode}"
            return (target_dir, error)

        print(f"  [clone] Full clone + checkout succeeded: {target_dir}")
        return (target_dir, None)

    except subprocess.TimeoutExpired:
        return (target_dir, f"clone timed out after {CLONE_TIMEOUT}s")
    except (gitops.GitError, OSError) as e:
        return (target_dir, f"git unavailable: {e}")


def shallow_clone(url, target_dir, re_clone=False):
    """Shallow-clone a repo at HEAD (depth=1).

    Returns (target_dir, error_msg|None).
    """
    if os.path.isdir(target_dir):
        if not re_clone:
            print(f"  [clone] Reusing existing clone: {target_dir}")
            return (target_dir, None)
        print(f"  [clone] Removing existing clone (re-clone): {target_dir}")
        shutil.rmtree(target_dir)

    os.makedirs(os.path.dirname(target_dir), exist_ok=True)

    print(f"  [clone] Cloning {url} ...")
    try:
        result = gitops.run_git(
            ["clone", "--depth", "1", gitops.SEP, url, target_dir],
            stage="clone",
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return (target_dir, "clone timed out after 120s")
    except (gitops.GitError, OSError) as e:
        return (target_dir, f"git unavailable: {e}")

    if result.returncode != 0:
        error = result.stderr.strip() or f"git clone exited {result.returncode}"
        return (target_dir, error)

    return (target_dir, None)
