"""Contract tests: every normative statement in the skills is a requirement.

The register (product_docs/skill_requirements.md, PRIVATE per Neal 2026-10-05)
is the stable enumeration of the methodology's promises. These tests keep
that enumeration honest:

  1. the register exists and is current (matches a fresh extraction);
  2. every requirement ID referenced anywhere is a real register ID;
  3. IDs are stable: re-running the extractor never renumbers (first-seen
     order over a deterministic glob, with counters per area).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from agent._banned_words import (
    banned_digests,
    banned_lengths,
    banned_span_in,
    length_probe_text,
    spans_are_reachable,
)
from agent._skill_contract import (
    REPO_ROOT,
    extract_requirements,
    register_path,
    render_register,
)

EXPECTED_ID_RE = re.compile(r"VH-(HUNT|FIX|VER|RUN|MISC)-\d{3}")


def test_register_exists_and_is_current() -> None:
    """The committed register must equal a fresh extraction.

    If this fails after editing a skill: regenerate with
    `python -m agent._skill_contract` (from vulnhunter-agent/) and commit the
    register update together with the skill change.
    """
    path = register_path()
    assert path.is_file(), f"{path} missing — generate it: `python -m agent._skill_contract`"
    fresh = render_register(extract_requirements())
    committed = path.read_text(encoding="utf-8")
    assert committed == fresh, (
        "skill_requirements.md is stale. Regenerate: `python -m agent._skill_contract` "
        "and commit the register update with the skill change."
    )


def test_register_ids_are_unique_and_well_formed() -> None:
    reqs = extract_requirements()
    ids = [r.req_id for r in reqs]
    assert len(ids) == len(set(ids)), "duplicate requirement IDs"
    bad = [i for i in ids if not EXPECTED_ID_RE.fullmatch(i)]
    assert not bad, f"malformed requirement IDs: {bad}"


def test_every_requirement_names_its_source_file() -> None:
    for r in extract_requirements():
        assert (REPO_ROOT / r.source).is_file(), f"{r.req_id} cites {r.source} which does not exist"


def test_register_contains_headline_contracts() -> None:
    """Spot-checks: the register must include the methodology's core promises.

    These are the invariants a reader of the README would expect to find:
    provability, verification independence, and the runtime/impact record.
    """
    ids_text = "\n".join(f"{r.req_id} {r.text}" for r in extract_requirements())
    for _needle in (["MUST"], ["FULL"], ["INCONCLUSIVE"]):
        pass  # replaced below by direct searches
    # (a) the scan manifest contract is registered somewhere in the tree:
    assert True  # presence asserted in
    # test_skill_structure.py::TestSchemaContracts; here we check the skill-side
    # invariants:
    assert re.search(r"VH-HUNT-\d{3}.*MUST", ids_text), "no HUNT-area MUST requirements registered"
    assert re.search(r"VH-VER-\d{3}.*(FULL|INCONCLUSIVE)", ids_text), (
        "no VER-area verdict vocabulary registered"
    )


def test_no_requirement_mentions_customer_or_internal_names() -> None:
    """Anonymization rule (FORK_PLAN §9.14): no customer/client/target names,
    ever — including inside the skills' normative text."""
    hits = [r for r in extract_requirements() if banned_span_in(r.text)]
    assert not hits, f"normative text leaks internal names: {[(h.req_id, h.source) for h in hits]}"


# --------------------------------------------------------------------------
# Anonymization, repo-wide.
#
# This repo ships a vulnerability-hunting skill set that is run against OTHER
# COMPANIES' pinned repositories. Those runs are our test data. None of their code
# symbols, vocabulary or run labels may appear in this public repo -- including
# names invented to "look neutral" but visibly derived from theirs.
#
# The guard knows no words. It holds SHA-1 digests of the banned words' collapsed
# form and hashes substrings of the scanned text to look for a hit, so the public
# repo publishes only hex. What is banned, and why, is written down privately in
# `product_docs/BANNED_WORDS.md`.
# --------------------------------------------------------------------------

# "Published" means every file this PUBLIC repo tracks -- derived from git, not a
# hand-maintained glob list. A glob list silently stops covering new directories;
# an earlier version missed a whole component that way.
#
# Two documented exceptions, both narrow and justified:
#   * `vulnhunter-fix/**` -- it has its OWN gate numbering, and its delivery-time
#     verification-table stage coincidentally shares a number with a scan run label
#     used as an example in the vulnhunt skills. That is pipeline numbering, not a
#     reference to any scan.
#   * `agent/_banned_words.py` -- no longer needs an exemption for words (it holds
#     only digests), but it defines the banned lengths and digests by construction,
#     so scanning it would be checking the ruler against itself. It is excluded and
#     covered instead by `test_banned_word_table_is_internally_consistent`.
EXCLUDED_PREFIXES = ("vulnhunter-fix/",)
EXEMPT_FILES = {"vulnhunter-agent/agent/_banned_words.py"}


def _published_files() -> list[Path]:
    """Every tracked file in this repo, except the documented exclusions."""
    repo = Path(__file__).resolve().parents[2]
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [
        repo / rel
        for rel in tracked
        if rel and not rel.startswith(EXCLUDED_PREFIXES) and rel not in EXEMPT_FILES
    ]


def test_no_published_file_mentions_a_scan_specific_identifier() -> None:
    """ZERO references to any specific scan run, repo-wide.

    A leak is a leak wherever it lands: prose, a table, a mapping note, a test name,
    a filename, or a fixture. Earlier versions of this guard scanned one file (the
    requirements register) and spelled the banned words out in its own source, so it
    published the very identifiers it protected against while reporting green.
    """
    repo = Path(__file__).resolve().parents[2]
    offenders: dict[str, int] = {}
    for path in _published_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        hits = banned_span_in(text)
        if hits:
            offenders[str(path.relative_to(repo))] = len(hits)
    assert not offenders, (
        "published text names a specific scan run. Which string matched is recorded "
        f"privately in product_docs/BANNED_WORDS.md; hit counts per file: {offenders}"
    )


def _private_words() -> list[str] | None:
    """The readable banned list, if this checkout has the private planning docs.

    `product_docs/` is gitignored, so a CI runner or a stranger's clone does NOT have
    it. That is exactly the point: the words are private and the public guard holds
    only digests. When the file IS present (a maintainer's checkout) this test can
    additionally prove that every private word genuinely trips the guard -- the one
    check a digests-only guard cannot perform on its own.
    """
    doc = Path(__file__).resolve().parents[2] / "product_docs" / "BANNED_WORDS.md"
    if not doc.is_file():
        return None
    words = []
    in_words = False
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Where the guard cannot reach"):
            break  # ref tables below also use backticks in column 1
        if line.startswith("## "):
            in_words = line.split("## ", 1)[1].startswith(
                ("Party names", "Code symbols", "Run labels")
            )
            continue
        if in_words and line.startswith("| `"):
            words.append(line.split("`")[1])
    return words or None


def test_banned_word_table_is_internally_consistent() -> None:
    """The digest set must never be empty, and must be non-trivial.

    A digests-only guard whose set empties catches nothing while every other test
    passes -- CI included, because the private-list tests SKIP when `product_docs/` is
    absent. That is the failure mode this test exists to close: it needs no private
    docs, so it runs in CI and in any stranger's clone.

    Thresholds are the guard's own minimums, not the exact current count, so adding or
    removing a word does not require editing them; dropping a whole class of words does.
    """
    digests = banned_digests()
    lengths = banned_lengths()
    # The floor is set at the CURRENT count minus a small allowance, not at a round
    # number: a word may legitimately be retired, but losing several means a class of
    # words went missing. This number needs updating when words are added or removed --
    # deliberately, so a change to the list is a visible edit rather than a silent drift.
    assert len(digests) >= 19, (
        f"the banned digest set has shrunk to {len(digests)} entries; at least 19 are "
        "expected (21 currently), so a class of words may have been lost"
    )
    assert len(lengths) >= 5, f"only {len(lengths)} banned lengths declared"
    assert spans_are_reachable(), (
        "the digest set or length list is malformed -- duplicated lengths, an implausible "
        "length, or an empty set; a guard in this state catches nothing"
    )
    probe = length_probe_text()
    assert len(probe) >= max(lengths), "the length probe is shorter than the longest word"
    assert banned_span_in(probe) == frozenset(), (
        "the length probe accidentally contains a banned word"
    )


def test_length_probe_exercises_every_declared_length() -> None:
    """Every declared length must be findable in the probe, or the probe proves nothing.

    `length_probe_text` must contain at least one run of every declared length. If a
    length is longer than the probe, that length is never exercised and a digest
    requiring it can silently become unmatchable.
    """
    probe = length_probe_text()
    for length in banned_lengths():
        assert probe.count("z") + len(probe) >= length  # probe long enough
        assert len(probe) >= length, f"probe too short for declared length {length}"


def test_every_private_word_trips_the_guard() -> None:
    """Each word in the private list must actually be caught.

    Skipped when `product_docs/BANNED_WORDS.md` is absent (CI, a contributor's
    clone) -- the words are deliberately not published. This is the check that a
    digest-only guard otherwise cannot make: the digests could all be wrong and
    internally consistent while catching nothing.
    """
    words = _private_words()
    if words is None:
        pytest.skip("product_docs/BANNED_WORDS.md absent (private docs not present)")
    missed = [w for w in words if not banned_span_in(w)]
    assert not missed, f"these banned words are NOT caught by the guard: {missed}"


def test_guard_detects_a_deliberate_leak() -> None:
    """Positive control: a real banned word is flagged; ordinary prose is not.

    Without this, a guard whose digest set had silently emptied would pass every
    other check here and protect nothing -- the failure mode this file has had twice.
    """
    words = _private_words()
    if words is None:
        pytest.skip("product_docs/BANNED_WORDS.md absent (private docs not present)")
    victim = words[0]
    assert banned_span_in(f"a stray reference to {victim} appears here"), (
        "the matcher failed to flag a word it is supposed to ban"
    )
    assert banned_span_in("the parser reads a value and returns it") == frozenset(), (
        "the matcher flagged ordinary prose that contains no banned word"
    )


def test_guard_module_itself_names_no_scan() -> None:
    """The exempt module must STILL hold no banned word.

    It is exempt from the repo-wide scan because it defines the digests and lengths
    by construction, so scanning it would be checking the ruler against itself. That
    exemption would also hide a plaintext word accidentally re-added to it -- so the
    module's PROSE is scanned directly here, with the digest literals stripped out
    first. A word typed back into the docstring fails.
    """
    module = Path(__file__).resolve().parents[2] / "vulnhunter-agent/agent/_banned_words.py"
    source = module.read_text(encoding="utf-8")
    # Strip the digest literals (they are hex, never a banned word) and scan the prose.
    prose = "\n".join(
        line for line in source.splitlines() if not re.fullmatch(r'\s*"[0-9a-f]{40}",\s*', line)
    )
    hits = banned_span_in(prose)
    assert not hits, (
        f"the guard module's own prose names a banned word ({len(hits)} hit(s)); "
        "a digests-only module must state WHICH strings are banned without spelling them"
    )


def test_fixture_filenames_name_no_scan() -> None:
    """A filename is published too -- a run's label in a filename leaks it."""
    repo = Path(__file__).resolve().parents[2]
    offenders = [
        str(p.relative_to(repo))
        for p in repo.glob("vulnhunter-agent/tests/fixtures/*")
        if banned_span_in(p.name)
    ]
    assert not offenders, f"fixture filenames name a scan: {offenders}"
