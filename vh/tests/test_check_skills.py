"""Tests for vh.skill_check: installed-vs-source skill drift detection.

The build plan (product_docs/BUILD_A1_drift_check.md §4) requires unit tests
per its §4.1 table, CLI tests per §4.2, a real-repo regression per §4.3, and
the adversarial cases in §4.4 to live in the suite rather than in the prose.

Every test here builds a real git checkout in tmp_path rather than mocking git,
because the claim under test is "a recorded commit can be compared to HEAD".
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from vh import cli, skill_check

# --- fixtures ---------------------------------------------------------------


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


def _make_source(tmp_path: Path, skills: tuple[str, ...] = ("vulnhunt",)) -> Path:
    """A real git checkout containing the named skills, committed."""
    source = tmp_path / "source"
    source.mkdir()
    _git(source, "init", "-q")
    _git(source, "config", "user.email", "t@example.com")
    _git(source, "config", "user.name", "Test")
    for name in skills:
        (source / name).mkdir()
        (source / name / "SKILL.md").write_text(f"---\nname: {name}\n---\nbody\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-qm", "init")
    return source


def _install(source: Path, root: Path, skill: str, *, marker: str | None = None) -> Path:
    """Copy a skill into an installed root, optionally writing a marker."""
    import shutil

    dst = root / skill
    shutil.copytree(source / skill, dst)
    if marker is not None:
        (dst / ".installed-from").write_text(marker + "\n")
    return dst


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    return _make_source(tmp_path)


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    r = tmp_path / "skills"
    r.mkdir()
    return r


def _head(source: Path) -> str:
    return _git(source, "rev-parse", "HEAD")


# --- §4.1 matching tree passes ----------------------------------------------


def test_matching_tree_passes(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    report = skill_check.check_root(root, source)
    assert report.match is True
    assert report.skills[0].tree == "match"
    assert report.skills[0].ok is True


def test_matching_tree_exits_zero(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 0


# --- §4.1 sha mismatch fails ------------------------------------------------


def test_sha_mismatch_fails(source: Path, root: Path) -> None:
    # Bytes identical, recorded commit stale: still drifted.
    stale = _git(source, "rev-parse", "HEAD~0")
    _install(source, root, "vulnhunt", marker=stale)
    # Move source forward so HEAD no longer equals the marker.
    (source / "vulnhunt" / "SKILL.md").write_text("---\nname: vulnhunt\n---\nbody2\n")
    # Keep installed bytes matching the NEW source, so only the commit differs.
    import shutil

    shutil.copy(source / "vulnhunt" / "SKILL.md", root / "vulnhunt" / "SKILL.md")
    _git(source, "commit", "-qam", "change")
    report = skill_check.check_root(root, source)
    assert report.match is False
    assert report.skills[0].tree == "match"
    assert report.skills[0].installed_commit == stale
    assert report.skills[0].ok is False
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 1


def test_sha_mismatch_fails_against_older_head(source: Path, root: Path) -> None:
    # The Gate 1/6 shape: installed records an older commit than source HEAD.
    old = _head(source)
    _install(source, root, "vulnhunt", marker=old)
    (source / "vulnhunt" / "SKILL.md").write_text("---\nname: vulnhunt\n---\nnewer\n")
    _git(source, "commit", "-qam", "newer")
    report = skill_check.check_root(root, source)
    assert report.match is False
    assert report.skills[0].installed_commit == old
    assert report.skills[0].source_commit == _head(source)
    assert report.skills[0].installed_commit != report.skills[0].source_commit


# --- §4.1 byte drift fails --------------------------------------------------


def test_byte_drift_fails(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    # One byte changed in the installed copy; marker still matches HEAD.
    path = root / "vulnhunt" / "SKILL.md"
    path.write_text(path.read_text().replace("body", "bodX"))
    report = skill_check.check_root(root, source)
    assert report.match is False
    assert report.skills[0].tree == "differs"
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 1


def test_byte_drift_one_byte(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    path = root / "vulnhunt" / "SKILL.md"
    data = bytearray(path.read_bytes())
    data[0] ^= 0x01  # flip a single bit
    path.write_bytes(bytes(data))
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "differs"


# --- §4.1 missing marker is not a pass --------------------------------------


def test_missing_installed_from_is_not_a_pass(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=None)
    report = skill_check.check_root(root, source)
    assert report.skills[0].installed_commit == "unknown"
    assert report.skills[0].ok is False
    assert report.match is False


def test_marker_must_be_a_full_sha(source: Path, root: Path) -> None:
    """A hand-edited marker cannot forge a match.

    Only a full 40/64-hex object id is accepted; ref names, truncated ids and
    flag-like values are treated as unknown rather than passed to git.
    """
    head = _head(source)
    installed = _install(source, root, "vulnhunt", marker=source.name)  # a ref-like name
    assert skill_check.read_installed_commit(installed) == "unknown"
    report = skill_check.check_root(root, source)
    assert report.skills[0].ok is False

    for bad in ("main", "--all", head[:12], head + "extra"):
        installed.joinpath(".installed-from").write_text(bad + "\n")
        assert skill_check.read_installed_commit(installed) == "unknown", bad

    installed.joinpath(".installed-from").write_text(head.upper() + "\n")
    assert skill_check.read_installed_commit(installed) == head


def test_empty_installed_from_is_not_a_pass(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker="")
    report = skill_check.check_root(root, source)
    assert report.skills[0].installed_commit == "unknown"
    assert report.skills[0].ok is False


# --- §4.1 missing source skill fails ---------------------------------------


def test_missing_source_skill_fails(tmp_path: Path) -> None:
    # A skill in scope (its marker names a commit this repo knows) but no
    # longer shipped by install.sh: no source bytes to compare.
    source = _make_source(tmp_path, skills=("vulnhunt",))
    root = tmp_path / "skills"
    root.mkdir()
    _install(source, root, "vulnhunt", marker=_head(source))
    extra = root / "ghost"
    extra.mkdir()
    (extra / "SKILL.md").write_text("---\nname: ghost\n---\n")
    (extra / ".installed-from").write_text(_head(source) + "\n")
    report = skill_check.check_root(root, source)
    ghost = next(s for s in report.skills if s.name == "ghost")
    assert ghost.tree == "missing"
    assert ghost.ok is False


# --- §4.1 markers excluded from hash ---------------------------------------


def test_markers_excluded_from_hash(source: Path, root: Path) -> None:
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    (installed / ".installed-from").write_text("deadbeef\n")
    (installed / ".installed-from-url").write_text("owner/repo\n")
    after = skill_check.tree_hash(installed)
    assert before == after


def test_marker_change_does_not_affect_tree_match(source: Path, root: Path) -> None:
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    (installed / ".installed-from-url").write_text("someone/else\n")
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "match"


# --- §4.1 pycache excluded --------------------------------------------------


def test_pycache_excluded(source: Path, root: Path) -> None:
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    cache = installed / "__pycache__"
    cache.mkdir()
    (cache / "mod.cpython-312.pyc").write_bytes(b"\x00\x01\x02")
    assert skill_check.tree_hash(installed) == before


def test_coverage_files_excluded(source: Path, root: Path) -> None:
    # Observed on a real install: vulnhunter-fix carries .coverage.* files in
    # source that were never copied, which made the trees hash differently.
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    (installed / ".coverage.host.pid1234.XYZ").write_text("data")
    assert skill_check.tree_hash(installed) == before


def test_venv_excluded(source: Path, root: Path) -> None:
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    venv = installed / ".venv" / "bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("#!/bin/sh\n")
    assert skill_check.tree_hash(installed) == before


def test_pytest_cache_excluded(source: Path, root: Path) -> None:
    # Observed on a real install: running tests in place leaves .pytest_cache.
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    cache = installed / ".pytest_cache"
    cache.mkdir()
    (cache / "README.md").write_text("cache")
    assert skill_check.tree_hash(installed) == before


def test_egg_info_excluded(source: Path, root: Path) -> None:
    # Observed on a real install: editable-install metadata is copied by
    # install.sh and would otherwise make two identical trees hash differently.
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    egg = installed / "c1_vulnhunter_fix.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_text("meta")
    assert skill_check.tree_hash(installed) == before


def test_mode_bits_are_outside_the_hash(source: Path, root: Path) -> None:
    """Documented limitation: losing the executable bit does not fail the check.

    The hash covers relative path + bytes only. Pinned as a known gap rather
    than left implicit, so a future reader does not assume mode is covered.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    os.chmod(installed / "SKILL.md", 0o644)
    assert skill_check.tree_hash(installed) == before


def test_file_symlink_to_outside_is_hashed(source: Path, root: Path) -> None:
    """A file replaced by a symlink outside the skill must still be hashed.

    Round-2 review blocker (claimed): the hash would "keep only is_file()"
    targets and drop the link. Pinned here so the claim stays settled --
    ``read_bytes`` follows the link, so attacker content changes the hash and
    the skill is reported as drift.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    evil = root.parent / "evil.md"
    evil.write_text("ATTACKER CONTROLLED\n")
    (installed / "SKILL.md").unlink()
    (installed / "SKILL.md").symlink_to(evil)
    assert skill_check.tree_hash(installed) != skill_check.tree_hash(source / "vulnhunt")
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "differs"
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 1


def test_symlink_loop_does_not_hang_or_crash(source: Path, root: Path) -> None:
    """A cyclic symlink inside a skill must be bounded, not a crash.

    Round-2 claimed a symlink loop raised OSError out of os.walk. Pinned so
    either behaviour change is caught.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    (installed / "loop").symlink_to(installed)
    assert skill_check.tree_hash(installed) is not None  # returns, does not raise


def test_unreadable_file_is_marked_not_skipped(source: Path, root: Path) -> None:
    """An unreadable file is marked distinctly, never silently skipped.

    Round-3 review: the earlier version chmod'd to 0o644 and asserted the hash
    was unchanged, so deleting the OSError handler would have left it green.
    This version pins the branch by driving it directly -- a readable file and
    the same file made to raise on read must not hash the same.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    target = installed / "secret.md"
    target.write_text("contents")
    readable = skill_check.tree_hash(installed)
    assert readable is not None

    real_read_bytes = Path.read_bytes

    def deny(self):
        if self.name == "secret.md":
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_bytes(self)

    with mock.patch.object(Path, "read_bytes", deny):
        unreadable = skill_check.tree_hash(installed)
    assert unreadable is not None
    assert unreadable != readable, "<unreadable> marker must change the hash"


def test_fifo_does_not_hang(source: Path, root: Path) -> None:
    """A FIFO in a skill must not block forever (round-3 blocker).

    read_bytes on a FIFO waits for a writer; on /dev/zero it never returns.
    Both produced a hang with no exit code before this guard existed.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    fifo = installed / "pipe"
    os.mkfifo(fifo)
    assert skill_check.tree_hash(installed) is not None


@pytest.mark.skipif(not Path("/dev/zero").exists(), reason="no /dev/zero")
def test_char_device_symlink_does_not_hang(source: Path, root: Path) -> None:
    """A symlink to an infinite stream must not hang the hash."""
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    (installed / "zero").symlink_to("/dev/zero")
    assert skill_check.tree_hash(installed) is not None


def test_fifo_is_recorded_in_tree_identity(source: Path, root: Path) -> None:
    """A special file changes the hash: it is part of the tree's identity."""
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    os.mkfifo(installed / "pipe")
    assert skill_check.tree_hash(installed) != before


def test_source_that_is_a_file_is_invocation_error(root: Path, tmp_path: Path) -> None:
    """--source pointing at a file is a usage error (exit 2), not a traceback."""
    afile = tmp_path / "afile"
    afile.write_text("hi")
    (root / "vulnhunt").mkdir()
    (root / "vulnhunt" / "SKILL.md").write_text("x")
    assert cli.main(["check-skills", "--root", str(root), "--source", str(afile)]) == 2


def test_source_not_a_repo_is_invocation_error(root: Path, tmp_path: Path) -> None:
    """--source pointing at a non-repo directory is a usage error (exit 2)."""
    plain = tmp_path / "plain"
    plain.mkdir()
    (root / "vulnhunt").mkdir()
    (root / "vulnhunt" / "SKILL.md").write_text("x")
    assert cli.main(["check-skills", "--root", str(root), "--source", str(plain)]) == 2


def test_source_pointing_at_a_subdirectory_is_invocation_error(tmp_path: Path) -> None:
    """--source at a repo subdirectory has no skill layout: exit 2, not silent drift."""
    src = _make_source(tmp_path, skills=("vulnhunt",))
    root = tmp_path / "skills"
    root.mkdir()
    _install(src, root, "vulnhunt", marker=_head(src))
    assert cli.main(["check-skills", "--root", str(root), "--source", str(src / "vulnhunt")]) == 2


def test_ordinary_content_still_counts(source: Path, root: Path) -> None:
    # Guard against over-broad filtering: real content changes the hash.
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    before = skill_check.tree_hash(installed)
    (installed / "SKILL.md").write_text("changed")
    assert skill_check.tree_hash(installed) != before


# --- §4.1 order independence ------------------------------------------------


def test_hash_is_order_independent(source: Path, root: Path) -> None:
    """Traversal order must not affect the hash.

    The earlier version of this test created both trees in the SAME file
    order, so it could not detect an ordering bug at all -- the review caught
    that. This version forces os.walk to hand back entries in reversed order
    and asserts the hash is unchanged, which is what "order-independent"
    actually claims.
    """
    a = root / "a"
    a.mkdir()
    (a / "SKILL.md").write_text("one")
    (a / "ref.md").write_text("two")
    (a / "sub").mkdir()
    (a / "sub" / "deep.md").write_text("three")
    baseline = skill_check.tree_hash(a)
    assert baseline is not None

    real_walk = os.walk

    def reversed_walk(*args, **kwargs):
        for dirpath, dirnames, filenames in real_walk(*args, **kwargs):
            yield dirpath, list(reversed(dirnames)), list(reversed(filenames))

    with mock.patch.object(skill_check.os, "walk", reversed_walk):
        assert skill_check.tree_hash(a) == baseline


def test_hash_changes_with_content(source: Path, root: Path) -> None:
    d = root / "c"
    d.mkdir()
    (d / "SKILL.md").write_text("one")
    h1 = skill_check.tree_hash(d)
    (d / "SKILL.md").write_text("two")
    assert skill_check.tree_hash(d) != h1


# --- §4.1 invocation errors -------------------------------------------------


def test_root_missing_is_invocation_error(source: Path, tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(skill_check.SkillCheckError):
        skill_check.check_root(missing, source)
    assert cli.main(["check-skills", "--root", str(missing), "--source", str(source)]) == 2


def test_source_missing_is_invocation_error(root: Path, tmp_path: Path) -> None:
    missing = tmp_path / "nosource"
    assert cli.main(["check-skills", "--root", str(root), "--source", str(missing)]) == 2


def test_source_not_git_is_invocation_error(root: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "vulnhunt").mkdir()
    (plain / "vulnhunt" / "SKILL.md").write_text("x")
    (root / "vulnhunt").mkdir()
    (root / "vulnhunt" / "SKILL.md").write_text("x")
    assert cli.main(["check-skills", "--root", str(root), "--source", str(plain)]) == 2


def test_empty_root_is_invocation_error(source: Path, root: Path) -> None:
    # Empty root must not pass vacuously.
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 2


def test_root_with_only_unrelated_skills_is_invocation_error(source: Path, root: Path) -> None:
    # A root full of skills that never came from this source proves nothing.
    other = root / "some-personal-skill"
    other.mkdir()
    (other / "SKILL.md").write_text("x")
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 2


# --- §4.1 warn-only ---------------------------------------------------------


def test_warn_only_prints_but_exits_zero(source: Path, root: Path, capsys) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    (root / "vulnhunt" / "SKILL.md").write_text("drifted")
    code = cli.main(["check-skills", "--root", str(root), "--source", str(source), "--warn-only"])
    out = capsys.readouterr().out
    assert code == 0
    assert "tree=differs" in out


# --- §4.4 adversarial cases -------------------------------------------------

_SYMLINKS_SUPPORTED = hasattr(Path, "symlink_to")


@pytest.mark.skipif(not _SYMLINKS_SUPPORTED, reason="platform without symlinks")
def test_symlinked_tree_is_followed_and_matches(source: Path, root: Path) -> None:
    """A symlink to source resolves to identical bytes.

    Pinned behaviour per plan §4.4: follow the symlink. install.sh copies
    rather than symlinks, so a symlink is unusual but its *content* still has
    to match; following keeps a symlinked-but-identical tree from passing on
    a technicality while still catching a symlink to the WRONG tree.
    """
    root.mkdir(exist_ok=True)
    link = root / "vulnhunt"
    link.symlink_to(source / "vulnhunt")
    (source / "vulnhunt" / ".installed-from").write_text(_head(source) + "\n")
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "match"


def test_symlinked_directory_is_followed_and_detected(source: Path, root: Path) -> None:
    """A directory symlink INSIDE a skill must not hide its contents.

    Regression for the review blocker: os.walk defaults to followlinks=False,
    so a skill whose ``scripts/`` was a symlink hashed identically to a source
    skill with no ``scripts/`` at all -- match, exit 0, whole tree invisible.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    payload = root.parent / "payload"
    payload.mkdir()
    (payload / "pwn.py").write_text("evil\n")
    (installed / "scripts").symlink_to(payload)
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "differs", (
        "a symlinked directory's files must be part of the hash"
    )
    assert skill_check.tree_hash(installed) != skill_check.tree_hash(source / "vulnhunt")


def test_symlinked_directory_matching_source_is_ok(tmp_path: Path) -> None:
    """Following symlinks must not manufacture drift for identical content.

    Source and install both keep a real ``scripts/`` directory; the install
    additionally holds its content behind a symlink at the same relative
    path. Same relative paths, same bytes, so the hashes must agree -- the
    symlink is a storage detail, not a content difference.
    """
    src = _make_source(tmp_path, skills=("vulnhunt",))
    scripts = src / "vulnhunt" / "scripts"
    scripts.mkdir()
    (scripts / "run.sh").write_text("echo hi\n")
    _git(src, "add", "-A")
    _git(src, "commit", "-qm", "add scripts")
    root = tmp_path / "skills"
    root.mkdir()
    installed = _install(src, root, "vulnhunt", marker=_head(src))
    # Keep the same relative path but make the directory a symlink.
    external = tmp_path / "external-scripts"
    (installed / "scripts").rename(external)
    (installed / "scripts").symlink_to(external)
    report = skill_check.check_root(root, src)
    assert report.skills[0].tree == "match"
    assert skill_check.tree_hash(installed) == skill_check.tree_hash(src / "vulnhunt")


def test_coveragerc_is_content_not_data(source: Path, root: Path) -> None:
    """Regression: matching '.coverage*' as a prefix swallowed .coveragerc.

    A coverage config file is authored skill content; editing it must change
    the hash.
    """
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    cfg = installed / ".coveragerc"
    cfg.write_text("[run]\nbranch = True\n")
    before = skill_check.tree_hash(installed)
    assert skill_check._is_excluded_file(".coveragerc") is False
    cfg.write_text("[run]\nbranch = False\n")
    assert skill_check.tree_hash(installed) != before


def test_coverage_data_files_are_excluded() -> None:
    """coverage's real data files stay excluded."""
    for name in (".coverage", ".coverage.host.pid1234.XYZ"):
        assert skill_check._is_excluded_file(name) is True


def test_dirty_source_differing_skill_fails(tmp_path: Path) -> None:
    """An uncommitted skill edit makes the installed copy differ -> exit 1.

    The earlier version of this test only asserted ``source_dirty`` and
    claimed bytes still matched; that was wrong, because the new file exists
    in source only. This pins the actual behaviour and the exit code.
    """
    src = _make_source(tmp_path, skills=("vulnhunt",))
    root = tmp_path / "skills"
    root.mkdir()
    _install(src, root, "vulnhunt", marker=_head(src))
    (src / "vulnhunt" / "extra.md").write_text("uncommitted\n")
    report = skill_check.check_root(root, src)
    assert report.skills[0].source_dirty is True
    assert report.skills[0].tree == "differs"
    assert cli.main(["check-skills", "--root", str(root), "--source", str(src)]) == 1


def test_dirty_source_matching_skill_passes_but_is_marked(source: Path, root: Path, capsys) -> None:
    """A dirty source whose skill still matches exits 0 and reports dirty.

    The dirty marker is the signal that the recorded commit equals HEAD but
    the bytes are the working tree -- the report must not claim 'yes' on it.
    """
    _install(source, root, "vulnhunt", marker=_head(source))
    (source / "README.md").write_text("unrelated uncommitted edit\n")
    code = cli.main(["check-skills", "--root", str(root), "--source", str(source)])
    out = capsys.readouterr().out
    assert code == 0
    assert "dirty" in out


def test_root_that_is_one_skill_dir_is_supported(source: Path, root: Path) -> None:
    """--root may point at a single skill directory (review minor)."""
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    report = skill_check.check_root(installed, source)
    assert report.match is True


def test_root_with_other_name_is_reported_missing(source: Path, root: Path) -> None:
    """A root whose basename is not a shipped skill name is not silently ok."""
    installed = _install(source, root, "vulnhunt", marker=_head(source))
    installed.rename(root / "not-vulnhunt")
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "missing"
    assert report.match is False


def test_crlf_change_is_caught(source: Path, root: Path) -> None:
    """No newline normalization: bytes are bytes."""
    _install(source, root, "vulnhunt", marker=_head(source))
    path = root / "vulnhunt" / "SKILL.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "differs"


def test_unicode_change_is_caught(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    (root / "vulnhunt" / "SKILL.md").write_text("café\n")
    report = skill_check.check_root(root, source)
    assert report.skills[0].tree == "differs"


def test_empty_dir_without_skill_md_is_ignored(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    (root / "not-a-skill").mkdir()
    report = skill_check.check_root(root, source)
    assert report.match is True
    assert [s.name for s in report.skills] == ["vulnhunt"]


# --- S4 loader neutrality ---------------------------------------------------


def test_skill_check_has_no_harness_literals() -> None:
    """S4: no claude/grok/dsh literals in the drift-check implementation."""
    text = Path(skill_check.__file__).read_text()
    lowered = text.lower()
    for literal in ("claude", "grok", "dsh"):
        assert literal not in lowered, f"harness literal {literal!r} in skill_check.py"


def test_bytes_from_commit_is_unknown_when_marker_disagrees(source: Path, root: Path) -> None:
    """Provenance must not name a commit the bytes do not come from.

    Round-4 minor: a stale install whose bytes happen to equal HEAD was
    reporting HEAD as the installed commit. ``ok`` is False there, and
    ``bytes_from_commit`` must stay "unknown" so a report cannot claim the
    bytes came from HEAD.
    """
    old = _head(source)
    _install(source, root, "vulnhunt", marker=old)
    (source / "vulnhunt" / "SKILL.md").write_text("---\nname: vulnhunt\n---\nnewer\n")
    import shutil

    shutil.copy(source / "vulnhunt" / "SKILL.md", root / "vulnhunt" / "SKILL.md")
    _git(source, "commit", "-qam", "newer")
    report = skill_check.check_root(root, source)
    skill = report.skills[0]
    assert skill.tree == "match"
    assert skill.ok is False
    assert skill.bytes_from_commit == "unknown", (
        "bytes match the working tree but the marker names a different commit"
    )


def test_bytes_from_commit_is_head_on_a_proven_match(source: Path, root: Path) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    report = skill_check.check_root(root, source)
    assert report.skills[0].ok is True
    assert report.skills[0].bytes_from_commit == _head(source)


def test_dirty_check_fails_safe_when_git_is_missing(source: Path) -> None:
    """A missing git binary must not read as a clean tree (round-4 minor)."""
    with mock.patch.object(skill_check, "_git", return_value=None):
        assert skill_check.source_is_dirty(source) is True


def test_dirty_source_never_proves_commit_attribution(tmp_path: Path) -> None:
    """Identical uncommitted edits must not be attributed to HEAD.

    Round-5 minor: source and install held the SAME uncommitted edit, so the
    bytes matched each other and the marker matched HEAD -- yet HEAD's blob
    was different. ``bytes_from_commit`` named HEAD anyway. Provenance must
    be "unknown" whenever the source is dirty.
    """
    src = _make_source(tmp_path, skills=("vulnhunt",))
    root = tmp_path / "skills"
    root.mkdir()
    _install(src, root, "vulnhunt", marker=_head(src))
    # Same uncommitted edit on both sides.
    (src / "vulnhunt" / "SKILL.md").write_text("UNCOMMITTED\n")
    (root / "vulnhunt" / "SKILL.md").write_text("UNCOMMITTED\n")
    report = skill_check.check_root(root, src)
    skill = report.skills[0]
    assert skill.tree == "match"
    assert skill.source_dirty is True
    assert skill.bytes_from_commit == "unknown", (
        "bytes match the working tree, not the commit the marker names"
    )


def test_dangling_skill_md_is_reported_not_silently_dropped(tmp_path: Path) -> None:
    """A skill whose SKILL.md is a broken link must appear in the report."""
    src = _make_source(tmp_path, skills=("vulnhunt",))
    root = tmp_path / "skills"
    root.mkdir()
    installed = _install(src, root, "vulnhunt", marker=_head(src))
    installed.joinpath("SKILL.md").unlink()
    installed.joinpath("SKILL.md").symlink_to(tmp_path / "nowhere")
    # The skill is still a skill directory; it must be reported as drift.
    assert [p.name for p in skill_check._skill_dirs(root)] == ["vulnhunt"]
    report = skill_check.check_root(root, src)
    assert [s.name for s in report.skills] == ["vulnhunt"]
    assert report.skills[0].ok is False


def test_stray_skill_md_file_does_not_make_root_a_skill(tmp_path: Path) -> None:
    """A SKILL.md FILE at the top of a root must not turn the root into a skill."""
    root = tmp_path / "root"
    (root / "vulnhunt").mkdir(parents=True)
    (root / "vulnhunt" / "SKILL.md").write_text("x")
    (root / "SKILL.md").write_text("I am a file, not a skill directory")
    assert [p.name for p in skill_check._skill_dirs(root)] == ["vulnhunt"]


def test_root_is_required_and_has_no_default() -> None:
    """S3: the check cannot guess a root, so --root must be required."""
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["check-skills", "--source", "/tmp/whatever"])


# --- §4.2 CLI ---------------------------------------------------------------


def test_help_lists_verb(capsys) -> None:
    # argparse exits rather than returning for --help, so assert on the exit
    # code and the printed usage.
    with pytest.raises(SystemExit) as exc:
        cli.main(["check-skills", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "check-skills" in out
    assert "--root" in out
    assert "--source" in out
    assert "--warn-only" in out


def test_exit_codes_documented_by_behavior(source: Path, root: Path) -> None:
    """Exit taxonomy 0/1/2 as the module documents: pass, drift, invocation."""
    _install(source, root, "vulnhunt", marker=_head(source))
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 0
    (root / "vulnhunt" / "SKILL.md").write_text("drift")
    assert cli.main(["check-skills", "--root", str(root), "--source", str(source)]) == 1
    assert cli.main(["check-skills", "--root", "/nope", "--source", str(source)]) == 2


def test_help_names_required_flags(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["check-skills", "--help"])
    out = capsys.readouterr().out
    assert "--root" in out
    assert "--source" in out


def test_json_summary_shape(source: Path, root: Path, capsys) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    code = cli.main(["check-skills", "--root", str(root), "--source", str(source), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) >= {"root", "source", "match", "skills"}
    skill = payload["skills"][0]
    assert set(skill) >= {"name", "installed", "source", "tree"}
    assert skill["name"] == "vulnhunt"
    assert skill["tree"] == "match"


def test_json_reports_mismatch(source: Path, root: Path, capsys) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    (root / "vulnhunt" / "SKILL.md").write_text("drift")
    code = cli.main(["check-skills", "--root", str(root), "--source", str(source), "--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["match"] is False
    assert payload["skills"][0]["ok"] is False


def test_text_mode_names_skipped_unrelated_skills(source: Path, root: Path, capsys) -> None:
    _install(source, root, "vulnhunt", marker=_head(source))
    other = root / "unrelated"
    other.mkdir()
    (other / "SKILL.md").write_text("x")
    code = cli.main(["check-skills", "--root", str(root), "--source", str(source)])
    out = capsys.readouterr().out
    assert code == 0
    assert "did not come from this source" in out


# --- §4.3 real-repo regression ---------------------------------------------


@pytest.mark.integration
def test_installed_roots_match_source_today() -> None:
    """The local harness roots should match what was COMMITTED at HEAD.

    Skips when a root is absent. This is the test that would have caught the
    Gate 1/6 drift (skills 7 commits behind) on the day it happened.

    Compares against a HEAD export rather than the working tree on purpose:
    a developer's in-progress skill edit must not read as install drift.
    That choice has a cost an adversarial review called out -- it cannot go
    red while ``vh check-skills --source .`` (the command operators actually
    run) is failing on the same tree. So the working-tree question is pinned
    separately by ``test_working_tree_check_reports_dirty_or_matches``
    below: this test answers "is the install right", that one answers "does
    the tool report honestly about the tree as it stands".

    A root that exists but raises SkillCheckError now FAILS rather than being
    swallowed: a root present on disk whose check cannot run is a real
    problem, not a skip.
    """
    repo = Path(__file__).resolve().parents[2]
    roots = [
        Path.home() / ".agents" / "skills",
        Path.home() / ".claude" / "skills",
        Path.home() / ".rap-grok" / "skills",
    ]
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        head_export = Path(tmp) / "head"
        export = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(head_export), "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if export.returncode != 0:
            pytest.skip(f"could not create HEAD worktree: {export.stderr.strip()}")
        try:
            for root in roots:
                if not root.is_dir():
                    continue
                try:
                    report = skill_check.check_root(root, head_export)
                except skill_check.SkillCheckError as exc:
                    # A root that exists but cannot be checked is a failure,
                    # not a silent skip (review finding).
                    pytest.fail(f"{root}: check could not run: {exc}")
                checked += 1
                drifted = [s for s in report.skills if not s.ok]
                if drifted:
                    detail = "; ".join(
                        f"{s.name}: tree={s.tree} installed={s.installed_commit} "
                        f"source={s.source_commit}"
                        for s in drifted
                    )
                    pytest.fail(f"{root} does not match source HEAD: {detail}")
        finally:
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force", str(head_export)],
                capture_output=True,
                text=True,
                check=False,
            )
    if checked == 0:
        pytest.skip("no local harness skill roots to check")


@pytest.mark.integration
def test_working_tree_check_reports_dirty_or_matches() -> None:
    """``vh check-skills --source .`` must report honestly about THIS tree.

    This is the counterpart to the HEAD comparison above. The tool compares
    installed bytes against the working tree, so a developer mid-edit will
    legitimately see drift; what must NOT happen is the tool claiming a clean
    pass while bytes differ. The invariant pinned here is the one that
    matters: if the command exits 0, every reported skill matched and the
    dirty flag is visible in the output.
    """
    repo = Path(__file__).resolve().parents[2]
    root = Path.home() / ".agents" / "skills"
    if not root.is_dir():
        pytest.skip("no local harness skill root")
    try:
        report = skill_check.check_root(root, repo)
    except skill_check.SkillCheckError as exc:
        pytest.skip(f"root not usable from this checkout: {exc}")
    dirty = skill_check.source_is_dirty(repo)
    for skill in report.skills:
        if not skill.ok:
            continue
        assert skill.tree == "match"
        # A skill cannot be "ok" on bytes we cannot prove match the commit.
        if dirty:
            assert skill.source_dirty is True, "dirty source must be surfaced on the line"
    # The tool must never report match while a skill tree differs.
    if report.match:
        assert all(s.tree in ("match",) for s in report.skills)
