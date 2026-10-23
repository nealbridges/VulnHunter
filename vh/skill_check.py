"""Mechanical installed-vs-source skill drift detection.

This module answers exactly one question: **does the skill tree installed
at this directory match the source checkout it claims to come from?** It is
a byte comparison plus a recorded-commit comparison. It never decides which
harness is running, never installs anything, and never touches the network.

The split is deliberate (BUILD_A1 plan §2): targeting -- resolving which
directory a particular harness will actually load -- stays operational prose
in the operator skill, because harness root precedence is harness-specific
knowledge and encoding it here would break loader neutrality. This module is
handed a root and verifies it.

Exit contract, matching the operator CLI taxonomy:
  0  every skill installed under the root matches source (bytes and commit)
  1  at least one skill is drifted, missing from source, or unverifiable
  2  invocation error (root missing, source not a checkout)
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

# Install-time markers are written next to the skill tree by install.sh.
# They describe the install, not the skill's content, so they are excluded
# from the content hash. A marker that disagrees with its tree is caught by
# the recorded-commit comparison instead of the hash.
_MARKER_PREFIX = ".installed-from"

# Byte-compiled caches, coverage data, bundled tool venvs, and packaging
# metadata are generated artifacts rather than skill content; including them
# would make identical trees hash differently. Observed on a real install:
# vulnhunter-fix carries .coverage.* and egg-info in its source checkout, a
# rebuilt .venv in the installed copy, and .pytest_cache after any test run
# in place.
#
# The set is deliberately NARROW. An adversarial review found that matching
# ``.coverage*`` as a *prefix* also swallowed ``.coveragerc`` -- real,
# authored skill content -- so that editing it left both trees hashing
# equal. Generated artifacts are matched by exact shape instead:
#   * ``.coverage`` / ``.coverage.<anything>`` (coverage's data files)
#   * ``__pycache__``, tool caches, virtualenvs (whole directories)
#   * ``*.egg-info`` (packaging metadata)
# Anything else under a skill dir counts as content. A generated file that
# sneaks past exclusion merely makes two identical installs hash
# differently (a false positive, safe); a real edit that gets excluded is a
# false negative (unsafe), so the bar for exclusion is high.
_EXCLUDED_DIR_NAMES = frozenset(
    {"__pycache__", ".venv", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".hypothesis"}
)
_EXCLUDED_DIR_SUFFIXES = (".egg-info",)


def _is_excluded_file(name: str) -> bool:
    if name.startswith(_MARKER_PREFIX):
        return True
    # coverage.py writes .coverage and .coverage.<host>.<pid>.<random>.
    # .coveragerc / .coveragerc.d are configuration, not data.
    return name == ".coverage" or (
        name.startswith(".coverage.") and not name.endswith(".coveragerc")
    )


def _is_excluded_dir(name: str) -> bool:
    return name in _EXCLUDED_DIR_NAMES or name.endswith(_EXCLUDED_DIR_SUFFIXES)


def source_locations(source: Path) -> dict[str, Path]:
    """Map installed-skill name -> source directory, mirroring install.sh.

    install.sh ships four skills from the repo root and dynamically sweeps
    ``skills/*/`` for newer operator-procedure skills (install.sh:118-135).
    Mirroring that discovery here keeps the check honest about what is
    actually shipped and where it lives, without hardcoding a list that
    drifts from the installer.
    """
    locations: dict[str, Path] = {}
    for name in ("vulnhunt", "vulnhunt-fix-verify", "vulnhunter-fix", "vulnhunter-run"):
        candidate = source / name
        if (candidate / "SKILL.md").is_file():
            locations[name] = candidate
    skills_dir = source / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                # First entry wins, root-level definitions take precedence.
                locations.setdefault(child.name, child)
    return locations


@dataclass
class SkillCheck:
    """Result of comparing one installed skill against its source."""

    name: str
    installed_commit: str
    source_commit: str
    tree: str  # "match" | "differs" | "missing"
    source_dirty: bool = False
    detail: str = ""
    # True only when bytes match AND the recorded commit equals source HEAD.
    ok: bool = False
    # The commit the matched bytes can be attributed to: source HEAD when the
    # bytes match AND the marker agrees, else "unknown" (provenance unproven).
    # Kept separate from installed_commit so a stale marker cannot make the
    # report claim bytes came from a commit they did not (review finding).
    bytes_from_commit: str = "unknown"

    def line(self) -> str:
        dirty = " dirty" if self.source_dirty else ""
        suffix = f" {self.detail}" if self.detail else ""
        return (
            f"{self.name} installed={self.installed_commit} "
            f"source={self.source_commit}{dirty} tree={self.tree}{suffix}"
        )


@dataclass
class CheckReport:
    """Aggregate result for a root."""

    root: str
    source: str
    skills: list[SkillCheck] = field(default_factory=list)
    # Skills present under the root that did not come from this source.
    # Reported for transparency; they are not drift.
    skipped: int = 0

    @property
    def match(self) -> bool:
        return bool(self.skills) and all(s.ok for s in self.skills)

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "source": self.source,
            "match": self.match,
            "skipped_not_from_source": self.skipped,
            "skills": [
                {
                    "name": s.name,
                    "installed": s.installed_commit,
                    "source": s.source_commit,
                    "tree": s.tree,
                    "source_dirty": s.source_dirty,
                    "ok": s.ok,
                    # The commit the matched bytes are attributable to, or
                    # "unknown" when provenance is unproven. A report must use
                    # this, not "installed", to name the commit its results
                    # came from.
                    "bytes_from": s.bytes_from_commit,
                }
                for s in self.skills
            ],
        }


class SkillCheckError(Exception):
    """Invocation-level failure (exit code 2)."""


def _walk_files(root: Path) -> list[Path]:
    """Return every file under ``root``, sorted, excluding markers and caches.

    **Directory symlinks are followed**, and this is load-bearing rather than
    a detail. ``os.walk`` defaults to ``followlinks=False``, so a symlinked
    subdirectory is listed in ``dirnames`` but never descended into. Before
    this was fixed an adversarial review found the exact hole: a skill whose
    ``scripts/`` was a symlink to a payload directory hashed identically to a
    source skill with no ``scripts/`` at all, so the check returned match and
    exit 0 while a whole tree of new files sat in the installed skill.

    install.sh copies rather than symlinks, so a symlink in an installed tree
    is unusual; but its *content* still has to match, and following is the
    only way to see that content. A symlink that escapes the tree is also a
    reason to compare by content rather than assume.
    """
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=True):
        dirnames[:] = sorted(d for d in dirnames if not _is_excluded_dir(d))
        for name in sorted(filenames):
            if _is_excluded_file(name):
                continue
            found.append(Path(dirpath) / name)
    return found


def tree_hash(root: Path) -> str | None:
    """Deterministic content hash of a skill tree, or None when absent.

    The hash covers relative path + file bytes for every REGULAR file,
    excluding install markers and caches. Sorting the manifest makes the
    result independent of directory traversal order.

    Two guards exist because a skill directory is untrusted input:

    1. **Only regular files are read.** ``read_bytes`` on a FIFO blocks until
       a writer appears, and on ``/dev/zero`` never returns at all -- both
       observed by an adversarial review as a hang with no exit code.
       ``stat`` follows symlinks (so a link to a real file is still hashed,
       which is what we want) while ``S_ISREG`` rejects pipes, sockets and
       character devices up front.
    2. An unreadable regular file (permission denied) is marked
       ``<unreadable>`` rather than silently skipped, so it cannot compare
       equal to a tree where that file was readable.
    """
    if not root.is_dir():
        return None
    digest = hashlib.sha256()
    for path in _walk_files(root):
        try:
            mode = os.stat(path).st_mode
        except OSError:
            continue  # vanished mid-walk
        if not stat.S_ISREG(mode):
            # Not a regular file: nothing streamable to hash. Record that we
            # saw it so the entry is still part of the tree identity.
            rel = path.relative_to(root).as_posix()
            digest.update(rel.encode("utf-8", "surrogateescape"))
            digest.update(b"\0<special>\0")
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8", "surrogateescape"))
        digest.update(b"\0")
        try:
            data = path.read_bytes()
        except OSError:
            # An unreadable file is not a silent skip: mark it distinctly so
            # the hash cannot equal a source tree that could read that file.
            digest.update(b"<unreadable>")
            continue
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
        digest.update(b"\0")
    return digest.hexdigest()


def _git(source: Path, *args: str) -> str | None:
    """Run a git command in ``source``; return stdout or None on failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(source), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def source_commit(source: Path) -> str | None:
    """The source checkout's HEAD commit, or None when it is not a checkout."""
    return _git(source, "rev-parse", "HEAD")


def source_is_dirty(source: Path) -> bool:
    """True when the source checkout has uncommitted changes.

    A dirty source is warned about, not failed: the recorded commit is HEAD,
    and an operator testing a working-tree change is a legitimate state.

    **Fail-safe, not fail-open.** ``_git`` returns None both for "clean" (an
    empty status) and for "could not run git at all" (missing binary, broken
    repo). Treating those the same made an actually-dirty tree look clean and
    then permitted a "match" claim the bytes did not support (review finding).
    An unknowable answer reports dirty: the warning is noise at worst, while a
    false clean is an unproven comparability claim.
    """
    out = _git(source, "status", "--porcelain")
    if out is None:
        return True
    return bool(out)


def read_installed_commit(skill_dir: Path) -> str:
    """The commit recorded at install time, or ``unknown`` when absent.

    Only a full 40/64-character hex object id is accepted. install.sh stamps
    ``git rev-parse HEAD``, which is always a full sha; anything else in the
    file (a ref name someone hand-edited in, a truncated id, a value starting
    with ``-`` that git could read as a flag) is treated as unusable rather
    than passed through to git. A hand-edited marker must not be able to
    forge a match.
    """
    marker = skill_dir / _MARKER_PREFIX
    try:
        value = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if not value:
        return "unknown"
    if len(value) not in (40, 64) or not all(c in "0123456789abcdef" for c in value.lower()):
        return "unknown"
    return value.lower()


def _looks_like_skill(d: Path) -> bool:
    """True when ``d`` is a skill DIRECTORY, i.e. it holds a SKILL.md.

    Uses ``lexists`` rather than ``is_file``: ``is_file`` follows symlinks, so
    a skill whose SKILL.md is a DANGLING link made the whole skill vanish from
    the report -- the root then reported "no skills under" instead of naming
    the broken link (review nit). A broken link is still a SKILL.md entry and
    the skill must be reported so the failure is diagnosable.

    The directory check comes first so a stray SKILL.md *file* sitting at the
    top of a root does not make the root itself look like a skill.
    """
    return d.is_dir() and os.path.lexists(d / "SKILL.md")


def _skill_dirs(root: Path) -> list[Path]:
    """Skill directories under ``root``: children that contain SKILL.md.

    A ``root`` that is itself a single skill directory is also accepted, so
    both ``--root ~/.agents/skills`` and ``--root ~/.agents/skills/vulnhunt``
    work. Subdirectories are preferred: a stray SKILL.md *file* at the top of
    a root holding real skill dirs must not make the root itself look like a
    skill (regression caught by test_stray_skill_md_file_does_not_make_root_a_skill).
    """
    if not root.is_dir():
        return []
    children = sorted(p for p in root.iterdir() if _looks_like_skill(p))
    if children:
        return children
    return [root] if _looks_like_skill(root) else []


def _is_ours(skill_dir: Path, locations: dict[str, Path], source: Path) -> bool:
    """True when this skill came from ``source``.

    A harness skills root routinely holds unrelated skills (observed: ~19
    personal skills alongside the VulnHunter ones in ~/.agents/skills).
    Those are not drift -- they were never installed from this checkout -- and
    must not fail the check. A skill is in scope when either:
      * install.sh would ship it from ``source``, or
      * its marker records a commit this checkout knows about.
    """
    if skill_dir.name in locations:
        return True
    marker = skill_dir / _MARKER_PREFIX
    if not marker.is_file():
        return False
    return _is_known_commit(read_installed_commit(skill_dir), source)


def _is_known_commit(commit: str, source: Path) -> bool:
    """True when ``commit`` is a commit object in ``source``.

    Bounds the check to skills installed from this repository's history
    without assuming the marker file format beyond "it holds a commit id".
    """
    if commit == "unknown":
        return False
    return _git(source, "cat-file", "-e", f"{commit}^{{commit}}") is not None


def check_one(skill_dir: Path, source_skill: Path | None, head: str) -> SkillCheck:
    """Compare a single installed skill against its source directory.

    ``source_skill`` is None when install.sh would not ship this skill: the
    skill is in scope only via its recorded commit, and has no source bytes
    to compare against.
    """
    name = skill_dir.name
    installed = read_installed_commit(skill_dir)

    if source_skill is None:
        return SkillCheck(
            name=name,
            installed_commit=installed,
            source_commit=head,
            tree="missing",
            detail="(no longer shipped by install.sh)",
            ok=False,
        )

    installed_hash = tree_hash(skill_dir)
    source_hash = tree_hash(source_skill)
    if source_hash is None:
        return SkillCheck(
            name=name,
            installed_commit=installed,
            source_commit=head,
            tree="missing",
            detail="(absent from source)",
            ok=False,
        )
    if installed_hash != source_hash:
        return SkillCheck(
            name=name,
            installed_commit=installed,
            source_commit=head,
            tree="differs",
            detail="(content differs from source)",
            ok=False,
        )

    # Bytes match. The recorded commit must also match source HEAD: a tree
    # that matches current source but was recorded against an older commit
    # is still a drifted install unless someone re-ran install.sh.
    if installed == "unknown":
        return SkillCheck(
            name=name,
            installed_commit=installed,
            source_commit=head,
            tree="match",
            detail="(no .installed-from: cannot prove an install)",
            ok=False,
        )
    if installed != head:
        return SkillCheck(
            name=name,
            installed_commit=installed,
            source_commit=head,
            tree="match",
            detail="(content matches but recorded commit does not)",
            ok=False,
        )
    return SkillCheck(
        name=name,
        installed_commit=installed,
        source_commit=head,
        tree="match",
        ok=True,
        # Attribution is only legitimate when the bytes provably ARE HEAD's.
        # A dirty source can have identical uncommitted edits in both trees:
        # bytes match each other, the marker says HEAD, and yet the bytes are
        # not HEAD's blob (review finding). ``check_root`` sets source_dirty
        # after this returns, so the decision is made there.
        bytes_from_commit=head,
    )


def check_root(root: str | Path, source: str | Path) -> CheckReport:
    """Verify every skill under ``root`` that came from ``source``.

    Raises SkillCheckError when the root or source is unusable, or when no
    skill in scope was found -- those are invocation problems or vacuous
    passes, not drift.
    """
    root_path = Path(root).expanduser().resolve()
    source_path = Path(source).expanduser().resolve()

    if not root_path.is_dir():
        raise SkillCheckError(f"skills root not found: {root_path}")
    if not source_path.is_dir():
        raise SkillCheckError(f"source checkout not found: {source_path}")

    head = source_commit(source_path)
    if head is None:
        raise SkillCheckError(f"source is not a git checkout: {source_path}")

    dirty = source_is_dirty(source_path)
    report = CheckReport(root=str(root_path), source=str(source_path))

    candidates = _skill_dirs(root_path)
    if not candidates:
        # An empty root is not a pass: nothing was verified.
        raise SkillCheckError(f"no skills (directories containing SKILL.md) under {root_path}")

    locations = source_locations(source_path)
    if not locations:
        # A checkout with no skill layout is the wrong oracle, not a source of
        # drift. Observed from an adversarial probe: `--source <repo>/vulnhunt`
        # made every skill read "no longer shipped by install.sh" and exit 1,
        # which looks like drift but only means the path was wrong.
        raise SkillCheckError(
            f"{source_path} contains no skills install.sh would ship "
            "(expected vulnhunt/, vulnhunter-run/, ... or skills/*/); "
            "point --source at the checkout root"
        )
    in_scope = [d for d in candidates if _is_ours(d, locations, source_path)]
    if not in_scope:
        # Also fail closed: a root full of unrelated skills proves nothing
        # about this checkout's install.
        raise SkillCheckError(
            f"no skills under {root_path} came from {source_path}; "
            "nothing to verify (check --root and --source)"
        )

    for skill_dir in in_scope:
        result = check_one(skill_dir, locations.get(skill_dir.name), head)
        result.source_dirty = dirty
        if dirty and result.bytes_from_commit != "unknown":
            # A dirty checkout can hold identical uncommitted edits in both
            # the source and the install: the bytes match each other and the
            # marker matches HEAD, yet the bytes are not HEAD's blob. Report
            # attribution as unproven rather than naming a commit they are
            # not from (review finding). This is the assume-unchanged and
            # skip-worktree case too -- git may hide the edit from status, so
            # "dirty" is the only signal we have, and it is conservative.
            result.bytes_from_commit = "unknown"
            if result.ok:
                result.detail = "(bytes match working tree; commit attribution unproven)"
        report.skills.append(result)
    report.skipped = len(candidates) - len(in_scope)
    return report
