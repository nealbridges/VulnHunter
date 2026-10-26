"""A2 — claim typing, executed probes, and the canonical HOLD-UNVERIFIED.

These tests hold the shipped skill text to the A2 contract. They are text
assertions over the markdown the model actually reads, because that text IS the
implementation: there is no Python to unit-test here.

The centrepiece is the Gate 6 replay (§4.2). The real Phase 2b verdict table
from the run that lost the `escapeVisibility` High is committed as a fixture;
the test requires A2's rules, applied to those rows, to produce HOLD-UNVERIFIED
rather than the FALSE POSITIVE that actually shipped.

The over-strictness guard (§4.3) matters just as much: a rule that HOLDs every
structural elimination would turn the report into a wall of unresolved doubt and
teach reviewers to ignore the section.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE2B = REPO_ROOT / "vulnhunt" / "phases" / "phase2b_verify.md"
PHASE3D = REPO_ROOT / "vulnhunt" / "phases" / "phase3d_sweep.md"
PHASE3A = REPO_ROOT / "vulnhunt" / "phases" / "phase3a_build_poc.md"
PHASE4 = REPO_ROOT / "vulnhunt" / "phases" / "phase4_report.md"
SKILL_DOC = REPO_ROOT / "vulnhunt" / "SKILL.md"
PROVISIONER = REPO_ROOT / "skills" / "runtime-provisioner" / "SKILL.md"
FIXTURES = REPO_ROOT / "vulnhunter-agent" / "tests" / "fixtures"

VERDICT_LITERALS = ("CONFIRMED", "FALSE POSITIVE", "HOLD-UNVERIFIED")


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _read_planning_doc(name: str) -> str:
    """Read a `product_docs/` artifact, skipping when it is absent.

    `product_docs/*` is gitignored (see .gitignore:65) except the requirement
    register, so planning docs exist in the author's working tree and NOT in CI.
    A test that hard-fails on one of them is red on the runner for a reason that
    has nothing to do with the shipped skill set. Skip instead, and keep the
    assertion strong when the file is there.
    """
    path = REPO_ROOT / "product_docs" / name
    if not path.is_file():
        pytest.skip(f"{name} is a local-only planning doc (product_docs/* is gitignored)")
    return path.read_text(encoding="utf-8")


def _shipped_markdown() -> list[Path]:
    """Every markdown file the skill set actually ships.

    Deliberately excludes product_docs/ (planning docs, gitignored except the
    register) — those legitimately discuss the vocabulary without defining it
    for a run. Covers the skill dirs that install.sh ships.
    """
    roots = [
        REPO_ROOT / "vulnhunt",
        REPO_ROOT / "skills",
        REPO_ROOT / "vulnhunter-run",
        REPO_ROOT / "vulnhunter-fix",
        REPO_ROOT / "vulnhunter-agent",
        REPO_ROOT / "vulnhunt-fix-verify",
    ]
    found: list[Path] = []
    for root in roots:
        if root.is_dir():
            found.extend(sorted(root.rglob("*.md")))
    return found


def _phase2b() -> str:
    return _read(PHASE2B)


# --------------------------------------------------------------------------
# §4.1 — the claim record exists and names its fields
# --------------------------------------------------------------------------


class TestClaimRecordFields:
    """Every verdict carries the four claim fields (G2.1)."""

    @pytest.mark.parametrize(
        "field",
        ["Closing claim", "Claim type", "Evidence", "Path reasoned about"],
    )
    def test_verdict_table_carries_claim_field(self, field: str) -> None:
        text = _phase2b()
        header = next(
            (ln for ln in text.splitlines() if ln.startswith("| Finding |")),
            None,
        )
        assert header is not None, "verdict table header not found"
        assert field in header, f"{field!r} missing from the verdict table header"

    @pytest.mark.parametrize(
        "value",
        [
            "structural",
            "behavioural",
            "executed-probe",
            "runtime-test",
            "static-trace",
            "existing-test",
        ],
    )
    def test_claim_field_documents_value(self, value: str) -> None:
        assert value in _phase2b(), f"claim typing never defines {value!r}"

    def test_claim_record_required_in_both_directions(self) -> None:
        """A CONFIRMED and an elimination both need the record — not just eliminations."""
        text = _phase2b()
        assert re.search(
            r"every verdict.{0,80}(CONFIRMED.{0,40}eliminat|eliminat.{0,40}CONFIRMED)",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "claim record is not stated to apply to CONFIRMED as well as eliminations"


# --------------------------------------------------------------------------
# §4.1 — the execution rule (G2.2)
# --------------------------------------------------------------------------


class TestExecutionRule:
    """A behavioural claim closes only on executed evidence (G2.2)."""

    def test_behavioural_closes_only_on_execution(self) -> None:
        text = _phase2b()
        assert re.search(
            r"behavioural.{0,200}only by `?(executed-probe|runtime-test)",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "the rule 'behavioural closes only on executed evidence' is absent"

    def test_rule_applies_in_both_directions(self) -> None:
        text = _phase2b()
        window = text[text.find("Execution rule") :][:1500]
        assert re.search(r"both directions", window, re.IGNORECASE), (
            "execution rule does not state that it binds eliminations AND promotions"
        )
        assert "elimination" in window.lower() and (
            "promotion" in window.lower() or "confirm" in window.lower()
        ), "execution rule names only one direction"

    def test_hold_requires_a_named_probe(self) -> None:
        text = _phase2b()
        assert re.search(r"HOLD-UNVERIFIED\s*—\s*probe:", text), (
            "no canonical `HOLD-UNVERIFIED — probe:` line form is specified"
        )

    def test_static_elimination_does_not_need_a_probe(self) -> None:
        """A structural elimination must not be forced to run anything (§4.3)."""
        text = _phase2b()
        assert re.search(
            r"structural.{0,120}(static-trace|no probe|need.{0,10}not|does not)",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "the text does not exempt structural claims from the execution rule"


# --------------------------------------------------------------------------
# §4.1 — the existing-test rule (R4.3 / G2.3)
# --------------------------------------------------------------------------


class TestExistingTestRule:
    """An existing test is evidence of intent, not of behaviour (G2.3/R4.3)."""

    def test_existing_test_is_not_behavioural_evidence(self) -> None:
        text = _phase2b()
        assert re.search(
            r"existing-test.{0,200}(intent|not.{0,30}behaviou?ral)",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "existing-test is not defined as intent-evidence-only"

    def test_built_string_mock_and_output_are_named(self) -> None:
        """The three insufficient evidence shapes must appear IN THE RULE (review round 2).

        The loose version accepted these words from anywhere in the phase file,
        including unrelated prose.
        """
        text = _phase2b()
        start = text.find("#### Existing-test rule")
        assert start != -1
        rule = text[start : start + 1200]
        for phrase in ("built string", "mock return", "output"):
            assert phrase in rule.lower(), (
                f"the existing-test rule does not name {phrase!r} as insufficient evidence"
            )

    def test_escapevisibility_cited_as_canonical_case(self) -> None:
        text = _phase2b()
        assert "escapeVisibility" in text, (
            "the escapeVisibility case is not cited as the canonical example"
        )
        assert "TestInvestigationListQueryEscapesScheduleID" in text, (
            "the specific test that smuggled intent in as evidence is not named"
        )


# --------------------------------------------------------------------------
# §4.1 — routing (G2.2)
# --------------------------------------------------------------------------


class TestHoldRouting:
    """HOLDs route by severity and are never dropped."""

    def test_medium_routes_to_phase3a(self) -> None:
        text = _phase2b()
        assert re.search(r"Medium\+.{0,120}Phase 3a", text, re.IGNORECASE | re.DOTALL), (
            "Medium+ HOLDs are not routed to Phase 3a as probe tasks"
        )

    def test_low_routes_to_unverified_section(self) -> None:
        text = _phase2b()
        assert re.search(r"Low.{0,120}Unverified", text, re.IGNORECASE | re.DOTALL), (
            "Low HOLDs are not routed to the report's Unverified section"
        )

    def test_never_dropped_never_confirmed(self) -> None:
        text = _phase2b()
        window = text[text.find("HOLD routing") :][:1200]
        assert "never" in window.lower(), "HOLD routing does not state a never-rule"
        assert "dropped" in window.lower() or "silently" in window.lower(), (
            "HOLD routing does not forbid silent dropping"
        )


# --------------------------------------------------------------------------
# §4.2 — the Gate 6 replay. This is the acceptance test that matters.
# --------------------------------------------------------------------------


def parse_rules(text: str) -> dict[str, object]:
    """Extract A2's decision procedure FROM THE SHIPPED SKILL TEXT.

    This is the fix for the review blocker: the previous version of this test
    hard-coded a keyword list, so the replay passed even with the execution rule
    deleted from phase2b_verify.md. Now the rules are read out of the prose the
    model actually sees. If the prose stops saying one of these things, parsing
    fails and every replay test fails with it.

    Returns the parts of the rule the replay applies:
      * behavioural_evidence  — evidence types that can close a behavioural claim
      * structural_evidence   — evidence types that can close a structural claim
      * verdict_when_unclosed — what a behavioural claim becomes without executed proof
    """
    rules: dict[str, object] = {}

    # 1. The execution rule must name exactly which evidence closes a behavioural claim.
    m = re.search(
        r"behavioural[^\n]{0,80}claim is closed only by ([^\n]+)",
        text,
        re.IGNORECASE,
    )
    assert m is not None, (
        "phase2b_verify.md no longer states which evidence closes a behavioural claim"
    )
    allowed = re.findall(r"`(executed-probe|runtime-test|static-trace|existing-test)`", m.group(1))
    assert allowed, f"execution rule names no backticked evidence types: {m.group(1)!r}"
    rules["behavioural_evidence"] = set(allowed)

    # 2. A structural claim may close on static-trace, and existing-test is also
    #    acceptable for structural claims (round-7 nit: capturing only
    #    static-trace made the harness HOLD a structural claim the prose allows).
    m2 = re.search(r"`?structural`? claim may close on `(static-trace)`", text)
    assert m2 is not None, "the text no longer permits structural claims to close on static-trace"
    structural_allowed = {m2.group(1)}
    m3 = re.search(r"`(existing-test)` is acceptable evidence for a \*\*structural\*\* claim", text)
    assert m3 is not None, (
        "the text no longer says existing-test is acceptable for a structural claim"
    )
    structural_allowed.add(m3.group(1))
    rules["structural_evidence"] = structural_allowed

    # 3. Anything else leaves the verdict HOLD-UNVERIFIED.
    assert re.search(
        r"(Any other evidence leaves the verdict `?HOLD-UNVERIFIED`?|"
        r"leaves the verdict `?HOLD-UNVERIFIED)`",
        text,
    ), "the text no longer says unclosed behavioural claims become HOLD-UNVERIFIED"
    rules["verdict_when_unclosed"] = "HOLD-UNVERIFIED"

    return rules


def classification_rule(text: str) -> dict[str, object]:
    """Parse the BEHAVIOURAL/STRUCTURAL boundary into an APPLICABLE rule.

    Round-3 review finding: the previous version parsed the sentence and then
    ignored it — a tripwire, not an application. This parses the rule into a
    callable that the classifier actually uses, and the callable's behaviour is
    derived from the parsed words:

      * the rule says a behavioural claim is one whose question is "not decidable
        by re-reading the source in this repository";
      * therefore the classifier asks: does this row cite a deciding fact IN this
        repository? If the parsed rule says behavioural means *not in-repo*,
        then in-repo -> structural and no-in-repo -> behavioural.

    Flip the prose and the predicate flips with it, so mutating the rule text
    changes verdicts instead of silently passing.
    """
    flat = " ".join(text.split())

    m = re.search(
        r"A claim is \*\*behavioural\*\* exactly when.{0,200}?"
        r"\*([^*]+)\*",
        flat,
    )
    assert m is not None, (
        "phase2b_verify.md no longer states the canonical behavioural "
        "classification test; the replay has no rule to apply"
    )
    behavioural_clause = m.group(1)

    m2 = re.search(
        r"A claim is \*\*structural\*\* exactly when (.{0,120}?)"
        r"(?:This is the whole boundary|$)",
        flat,
    )
    assert m2 is not None, (
        "phase2b_verify.md no longer states the structural side of the classification test"
    )
    structural_clause = m2.group(1)

    # Derive the predicate from the rule's wording WITHOUT asserting a direction.
    # The rule must mention re-reading this repo's source; whether it negates
    # that ("not decidable") decides which way the boundary runs. Flip the prose
    # and the verdicts flip; this is what makes the rule real rather than a tripwire.
    assert "re-reading the source in this repository" in behavioural_clause, (
        "the behavioural half of the rule no longer mentions re-reading this "
        f"repository's source; got {behavioural_clause!r}"
    )
    negated = "not decidable" in behavioural_clause

    def classify(cites_in_repo_decider: bool) -> str:
        """Apply the parsed rule to a fact about the row.

        negated=True  (the prose as written): behavioural == NOT decided in-repo,
                      so in-repo decider -> structural.
        negated=False (prose inverted):       behavioural == decided in-repo,
                      so in-repo decider -> behavioural.
        """
        if negated:
            return "structural" if cites_in_repo_decider else "behavioural"
        return "behavioural" if cites_in_repo_decider else "structural"

    return {
        "behavioural": behavioural_clause,
        "structural": structural_clause,
        "negated": negated,
        "classify": classify,
    }


def structural_examples(text: str) -> list[str]:
    """Extract the in-repo deciding facts the skill lists as STRUCTURAL.

    Round-6 nit: the previous version seeded a hardcoded detector and the slice
    it parsed stopped before the examples, so "the regex is anchored" and "the
    ORM parameterizes it" were recognised only by accident. This reads the
    skill's own structural examples from the "The line is *whose* source decides
    it" paragraph, where those illustrations actually live, and uses nothing
    that is not in the prose.

    If the paragraph disappears, this raises — the detector has no list.
    """
    flat = " ".join(text.split())

    # Two paragraphs list structural examples: the "Structural claims are about"
    # definition, and the "whose source decides it" boundary discussion.
    sdef = flat.find("**Structural** claims are about")
    sdef_end = flat.find("**Behavioural** claims are about")
    assert sdef != -1 and sdef_end != -1, (
        "the structural definition block is missing from phase2b_verify.md"
    )

    anchor = flat.find("The line is *whose* source decides it")
    assert anchor != -1, (
        "phase2b_verify.md no longer has the 'whose source decides it' boundary "
        "paragraph; the structural detector has nothing to read"
    )
    stop = flat.find("**The classification test, stated once", anchor)
    assert stop != -1, "the boundary paragraph is not terminated by the classification test"

    block = flat[sdef:sdef_end] + " " + flat[anchor:stop]

    quoted = [q.lower() for q in re.findall(r'"([^"]{4,80})"', block)]
    assert quoted, (
        "neither structural paragraph lists a quoted example; the detector "
        "would have nothing to match"
    )

    phrases: set[str] = set()
    for example in quoted:
        phrases.add(example)
        words = example.split()
        # The distinguishing prefix, e.g. "the regex is anchored" ->
        # "regex is anchored"; "the only writer is the coordinator" ->
        # "only writer is the coordinator". A bare final word is NOT added:
        # generic nouns like "caller" would match unrelated prose.
        if len(words) >= 3:
            phrases.add(" ".join(words[1:4]))

    return sorted(phrases)


def claim_type_of(row: str, boundary: dict[str, object]) -> str:
    """Classify a historical row by APPLYING the parsed rule.

    The only judgement this function makes is the factual one: does the row cite
    a deciding location *in this repository* (a single writer, no handler, an
    unreachable branch)? Everything else — what that means for the verdict — is
    decided by the predicate parsed out of `phase2b_verify.md`.
    """
    classify = boundary.get("classify")
    assert callable(classify), "the classification rule was not parsed from the skill text"

    lowered = row.lower()
    # The structural examples the SKILL itself lists are the detector. Round-5
    # nit: a hand-picked phrase list only recognised rows that happened to use
    # those words, and missed the skill's own examples ("the ORM parameterizes
    # it", "the regex is anchored", "type-constrained"). Parse them from the
    # prose instead, so the detector tracks the skill rather than this file.
    examples = structural_examples(_phase2b())
    cited = [phrase for phrase in examples if phrase in lowered]
    cites_in_repo_decider = bool(cited)
    result = str(classify(cites_in_repo_decider))
    # Round-9 nit: absence of a structural example quietly meant "behavioural".
    # Record WHY so a row classified by absence is visible as such rather than
    # looking like a positive behavioural finding.
    claim_type_of.last_basis = (
        f"cited in-repo example(s): {cited}" if cited else "no quoted structural example cited"
    )
    return result


def evidence_of(row: str) -> str:
    """What evidence the historical row actually used to close the claim."""
    lowered = row.lower()
    if "executed-probe" in lowered or "runtime-test" in lowered:
        return "executed-probe"
    if "test" in lowered or "confirmed by existing test" in lowered:
        return "existing-test"
    return "static-trace"


def equation_terms(
    text: str, lhs_wanted: str | None, prefer: str | None = None
) -> tuple[list[str], list[str]] | None:
    """Extract `A = B + C` accounting identities from the shipped markdown.

    Returns (lhs_terms, rhs_terms) as lowercase-normalised term strings, or None
    if no matching identity is present. `prefer` selects an equation whose left
    side mentions that word, for docs with more than one.
    """
    flat = " ".join(text.split())
    candidates = []
    for line in re.findall(r"[A-Za-z0-9`_ (),+*\-]{10,200}=[^.]{3,200}", flat):
        if "=" not in line:
            continue
        lhs, rhs = line.split("=", 1)
        lhs_terms = [t.strip().strip("`*") for t in re.split(r"\s*\+\s*", lhs) if t.strip()]
        rhs_terms = [t.strip().strip("`*") for t in re.split(r"\s*\+\s*", rhs) if t.strip()]
        rhs_terms = [t for t in rhs_terms if t and t.lower() not in {"if", "and"}]
        # The equation is a single sentence; trailing prose after the last term
        # must not be absorbed into it. Trim each term at the first sentence
        # boundary or markdown emphasis break.
        rhs_terms = [re.split(r"\. |\*\*| is a column", t)[0].strip() for t in rhs_terms]
        # A term is a short noun phrase. Anything longer than ~8 words has
        # absorbed prose and would silently contribute a wrong value.
        rhs_terms = [t for t in rhs_terms if t and len(t.split()) <= 8]
        candidates.append((lhs_terms, rhs_terms))
    if not candidates:
        return None
    for lhs_terms, rhs_terms in candidates:
        joined = " ".join(lhs_terms).lower()
        if lhs_wanted and lhs_wanted.lower() in joined:
            return lhs_terms, rhs_terms
        if prefer and prefer.lower() in joined:
            return lhs_terms, rhs_terms
    return candidates[0]


def apply_rules(row: str, rules: dict[str, object], boundary: dict[str, str] | None = None) -> str:
    """Apply the PARSED skill rules to a historical row.

    This is the whole point: the verdict comes from the rule the skill text
    states, not from a list in this file. Delete the rule from the prose and the
    replay fails.
    """
    if boundary is None:
        boundary = classification_rule(_phase2b())
    ctype = claim_type_of(row, boundary)
    evidence = evidence_of(row)

    allowed = (
        rules["behavioural_evidence"] if ctype == "behavioural" else rules["structural_evidence"]
    )
    assert isinstance(allowed, set)

    if evidence in allowed:
        return "FALSE POSITIVE"  # the claim was closed with permitted evidence
    # Evidence type not permitted for this claim type -> the verdict cannot stand.
    return str(rules["verdict_when_unclosed"])


class TestGate6Replay:
    """The run that lost the escapeVisibility High must now HOLD, not eliminate."""

    @pytest.fixture(scope="class")
    @staticmethod
    def rows() -> list[str]:
        text = _read(FIXTURES / "gate6_phase2b_elimination.md")
        return [ln for ln in text.splitlines() if ln.startswith("| VULN-")]

    @pytest.fixture(scope="class")
    @staticmethod
    def rules() -> dict[str, object]:
        return parse_rules(_phase2b())

    @pytest.fixture(scope="class")
    @staticmethod
    def boundary() -> dict[str, str]:
        return classification_rule(_phase2b())

    def test_classification_boundary_is_parsed_from_prose(self, boundary: dict[str, str]) -> None:
        """The behavioural/structural line comes from the skill text, not from this file."""
        assert "behavioural" in boundary and "structural" in boundary
        assert "re-reading" in boundary["behavioural"]

    def test_rules_are_parsed_from_the_shipped_text(self, rules: dict[str, object]) -> None:
        """The replay source of truth is the skill prose, and it excludes existing-test."""
        assert "executed-probe" in rules["behavioural_evidence"]
        assert "runtime-test" in rules["behavioural_evidence"]
        assert "existing-test" not in rules["behavioural_evidence"], (
            "the skill text permits existing-test to close a behavioural claim — the defect is back"
        )
        assert "static-trace" not in rules["behavioural_evidence"], (
            "the skill text permits static-trace to close a behavioural claim — the defect is back"
        )

    def test_fixture_has_the_two_historical_rows(self, rows: list[str]) -> None:
        assert len(rows) == 2, f"expected 2 historical rows, got {len(rows)}"
        joined = "\n".join(rows)
        assert "VULN-001" in joined and "VULN-002" in joined

    @pytest.mark.parametrize("index", [0, 1])
    def test_escapevisibility_rows_classify_as_hold(
        self, rows: list[str], rules: dict[str, object], index: int
    ) -> None:
        """Both rows are behavioural claims closed by reasoning — neither is a false positive."""
        verdict = apply_rules(rows[index], rules)
        assert verdict == "HOLD-UNVERIFIED", (
            f"row {index} classified as {verdict}; A2 requires HOLD-UNVERIFIED. "
            "The historical run shipped a FALSE POSITIVE here."
        )

    def test_the_rows_really_are_behavioural(
        self, rows: list[str], boundary: dict[str, str]
    ) -> None:
        """Both rows argue about library behaviour, so the behavioural rule is the one that applies."""
        for row in rows:
            assert claim_type_of(row, boundary) == "behavioural", (
                "a fixture row classified as structural; the rule under test would not apply"
            )

    def test_the_rows_evidence_really_is_insufficient(self, rows: list[str]) -> None:
        """Both rows close on static reasoning / an existing test, never on a probe."""
        for row in rows:
            assert evidence_of(row) in {"static-trace", "existing-test"}, (
                "a fixture row already used executed evidence; it could not demonstrate the defect"
            )

    def test_the_cited_evidence_is_existing_test(self, rows: list[str]) -> None:
        """VULN-002's cited evidence is a built-string test — the canonical trap."""
        row = rows[1]
        assert "TestInvestigationListQueryEscapesScheduleID" in row
        assert evidence_of(row) == "existing-test", (
            "the row cites a test, so its evidence type must resolve to existing-test"
        )

    def test_row_002_names_the_closing_claim(self, rows: list[str]) -> None:
        """The row states the behavioural claim that the probe must settle."""
        row = rows[1]
        assert "escapeVisibility" in row
        assert "literal" in row.lower(), (
            "the closing claim (the literal cannot be terminated) is not stated"
        )

    def test_replay_passes_for_the_right_reason(self, rows: list[str]) -> None:
        """Guard against a fixture written to match the rule rather than the real case.

        The rows must be genuine historical eliminations: they must say FALSE
        POSITIVE (what actually shipped) and must argue about string content.
        If a future editor "fixes" the fixture by pre-marking it HOLD, this fails.
        """
        for row in rows:
            assert "FALSE POSITIVE" in row, (
                "fixture row no longer records the historical FALSE POSITIVE verdict"
            )
            assert "HOLD-UNVERIFIED" not in row, (
                "fixture was edited to say HOLD-UNVERIFIED; it must stay historical"
            )
            assert "escapeVisibility" in row, (
                "fixture row lost the escapeVisibility reasoning that makes it behavioural"
            )

    def test_rules_discriminate(
        self, rows: list[str], rules: dict[str, object], boundary: dict[str, str]
    ) -> None:
        """The replay must FAIL if the rule were removed — prove it is not vacuous.

        A procedure that returned HOLD for everything would also make the replay
        pass. These two mutations show it does not.
        """
        # Mutation 1: same behavioural row, but a probe ran. Now it may eliminate.
        assert apply_rules(rows[1] + " executed-probe", rules) == "FALSE POSITIVE", (
            "procedure HOLDs even when a probe ran; the execution rule is not applied"
        )
        # Mutation 2: a structural row closed on static-trace. No probe needed.
        structural = (
            "| VULN-009 | Yes | No - the only writer is the coordinator at "
            "engine.go:441 | N/A | N/A | 3/3 | FALSE POSITIVE |"
        )
        assert claim_type_of(structural, boundary) == "structural"
        assert apply_rules(structural, rules, boundary) == "FALSE POSITIVE", (
            "procedure HOLDs a structural elimination; that is the over-strictness failure"
        )

    def test_replay_row_would_have_shipped_as_false_positive(
        self, rows: list[str], rules: dict[str, object], boundary: dict[str, str]
    ) -> None:
        """Without A2 this row is FALSE POSITIVE — i.e. the test catches a real regression."""
        # The historical verdict, read from the row itself, is the wrong answer
        # under A2. This is the exact loss A2 closes.
        assert "FALSE POSITIVE" in rows[1]
        assert apply_rules(rows[1], rules, boundary) != "FALSE POSITIVE"


# --------------------------------------------------------------------------
# §4.3 — over-strictness guard: structural eliminations must NOT be HOLDed
# --------------------------------------------------------------------------


class TestOverStrictnessGuard:
    """The rule must not force a probe onto every structural elimination."""

    def test_structural_exemption_is_explicit(self) -> None:
        text = _phase2b()
        assert re.search(
            r"structural.{0,200}(static-trace|closed by|no probe|not manufacture)",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "the text never states that structural claims close on static-trace alone"

    def test_do_not_manufacture_a_probe(self) -> None:
        text = _phase2b()
        assert re.search(r"do not manufacture|not manufacture", text, re.IGNORECASE), (
            "no guard sentence prevents inventing probes for structural findings"
        )

    def test_structural_example_survives(self) -> None:
        """The shipped template still shows a structural elimination closed without a probe.

        Review finding: the original version compared a whitespace-stripped string
        against a pattern containing a space, so its first branch could never
        match — it passed only via the fallback. This parses the actual example row.
        """
        text = _phase2b()
        rows = [ln for ln in text.splitlines() if ln.startswith("| VULN-002 |")]
        assert rows, "the worked VULN-002 example row was lost from the template"
        row = rows[0]
        assert "structural" in row, "the worked example no longer demonstrates a structural claim"
        assert "static-trace" in row, "the structural example no longer closes on static-trace"
        assert "FALSE POSITIVE" in row, "the structural example no longer eliminates"
        assert "HOLD-UNVERIFIED" not in row, (
            "the structural example is now HOLDed — that is the over-strictness failure"
        )

    def test_most_eliminations_are_structural(self) -> None:
        """The text acknowledges structural eliminations are legitimate and common."""
        text = _phase2b()
        assert re.search(
            r"structural claims are legitimate|legitimate and common|most eliminations",
            text,
            re.IGNORECASE,
        ), "the text does not affirm that structural eliminations are the normal case"


# --------------------------------------------------------------------------
# §4.4 — canonical HOLD-UNVERIFIED glossary (G2.6)
# --------------------------------------------------------------------------


class TestCanonicalGlossary:
    """HOLD-UNVERIFIED is defined exactly once, in vulnhunt/SKILL.md."""

    def test_glossary_defines_hold_unverified(self) -> None:
        text = _read(SKILL_DOC)
        assert "HOLD-UNVERIFIED" in text, "HOLD-UNVERIFIED is not defined in vulnhunt/SKILL.md"
        anchor = text.find("Verdict vocabulary")
        assert anchor != -1, "the verdict vocabulary section is missing from vulnhunt/SKILL.md"
        window = text[anchor : anchor + 3500]
        assert re.search(r"neither confirmed nor refuted|cannot settle|does not know", window), (
            "the glossary does not say what a HOLD epistemically means"
        )

    def test_glossary_distinguishes_inconclusive(self) -> None:
        text = _read(SKILL_DOC)
        anchor = text.find("Verdict vocabulary")
        assert anchor != -1
        window = text[anchor : anchor + 3500]
        assert "INCONCLUSIVE" in window, (
            "HOLD-UNVERIFIED is not explicitly distinguished from fix-verify's INCONCLUSIVE"
        )
        assert re.search(
            r"INCONCLUSIVE.{0,400}(location|no longer exists|nothing left)",
            window,
            re.IGNORECASE | re.DOTALL,
        ), "the INCONCLUSIVE distinction is not explained (location gone, not question open)"

    def test_glossary_distinguishes_code_smell(self) -> None:
        text = _read(SKILL_DOC)
        anchor = text.find("Verdict vocabulary")
        assert anchor != -1
        window = text[anchor : anchor + 3500]
        assert re.search(
            r"(not.{0,20}Code Smell|Code Smell.{0,200}not)",
            window,
            re.IGNORECASE | re.DOTALL,
        ), "HOLD-UNVERIFIED is not distinguished from a Code Smell"

    def test_glossary_is_the_single_definition(self) -> None:
        """No OTHER shipped skill file may redefine HOLD-UNVERIFIED.

        Review finding: the first version only checked four hand-picked files.
        This searches every markdown file the skills ship, so a second definition
        appearing anywhere (a new phase, the fix skills, vulnhunter-run) is caught.
        """
        restaters = []
        for path in _shipped_markdown():
            if path == SKILL_DOC:
                continue  # the canonical glossary itself
            text = path.read_text(encoding="utf-8")
            if "HOLD-UNVERIFIED" not in text:
                continue
            # Redefinition patterns: "HOLD-UNVERIFIED is a/an X", "HOLD-UNVERIFIED
            # means X", "X means HOLD-UNVERIFIED".
            # Round-10 nit: a backticked token splits "`HOLD-UNVERIFIED` is a",
            # so the pattern missed a second definition. Allow the markdown.
            if re.search(
                r"`?HOLD-UNVERIFIED`? is (a|an)\b|`?HOLD-UNVERIFIED`? means\b"
                r"|\bmeans `?HOLD-UNVERIFIED",
                text,
            ):
                restaters.append(str(path.relative_to(REPO_ROOT)))
        assert not restaters, (
            "these files redefine HOLD-UNVERIFIED instead of deferring to the "
            f"canonical glossary in vulnhunt/SKILL.md: {restaters}"
        )

    def test_glossary_is_reachable_from_phase_files(self) -> None:
        """A phase that emits HOLD must point the reader at the canonical definition."""
        for path in (PHASE2B, PHASE3A, PHASE4, PROVISIONER):
            text = _read(path)
            if "HOLD-UNVERIFIED" not in text:
                continue
            assert "vulnhunt/SKILL.md" in text or "canonical" in text.lower(), (
                f"{path.name} uses HOLD-UNVERIFIED without pointing at the glossary"
            )

    def test_hold_is_not_a_third_vocabulary(self) -> None:
        """The three vocabularies are named and kept distinct."""
        text = _read(SKILL_DOC) + _read(PHASE2B)
        for literal in VERDICT_LITERALS:
            assert literal in text, f"{literal} is missing from the vocabulary"


# --------------------------------------------------------------------------
# §4.4 — provisioner probe ladder (G2.4/G2.5)
# --------------------------------------------------------------------------


class TestProvisionerLadder:
    """The probe ladder is cheapest-sufficient-first and the reimpl is not a probe."""

    def test_ladder_ordered_correctly(self) -> None:
        text = _read(PROVISIONER)
        call = text.find("Call the real function")
        parser = text.find("downstream parser")
        container = text.find("Only then the container")
        assert call != -1 and parser != -1 and container != -1, (
            "the three rungs are not all present"
        )
        assert call < parser < container, (
            "probe ladder is out of order; must be call → parse → container"
        )

    def test_reimplementation_is_not_a_probe(self) -> None:
        """A parser reimplementation must be explicitly disqualified (review round 2).

        The round-1 fix kept an alternation that matched the bare token
        `static-trace` anywhere in the file, so deleting the disqualification
        sentence still passed. This now requires the sentence itself.
        """
        text = _read(PROVISIONER)
        assert re.search(
            r"A \*\*reimplementation\*\* of the parser does not count as a probe",
            text,
        ), "the disqualification sentence is missing or reworded beyond recognition"
        window = text[text.find("A **reimplementation** of the parser") :][:400]
        assert "static-trace" in window, (
            "the disqualification sentence no longer explains WHY a reimplementation "
            "is static-trace rather than a probe"
        )

    def test_ladder_precedes_container_preference(self) -> None:
        """Probe depth must be decided BEFORE container choice (plan §3.2/§4.1).

        A reviewer caught the first version of this test asserting the opposite:
        it required the ladder to appear *after* the Docker preference list,
        while the plan says the ladder goes above it, so that probe depth
        constrains the container choice rather than being an afterthought.
        """
        text = _read(PROVISIONER)
        ladder = text.find("Cheapest-sufficient-first probe ladder")
        docker = text.find("**Docker container**")
        assert ladder != -1 and docker != -1
        assert ladder < docker, (
            "the ladder must appear ABOVE the container preference list, so that "
            "probe depth constrains the sandbox choice (plan §3.2)"
        )

    def test_payload_discipline_positions_tails_grammar(self) -> None:
        text = _read(PROVISIONER)
        for phrase in (
            "interpolation position",
            "survive the sanitizer",
            "valid in the target grammar",
        ):
            assert phrase in text.lower(), f"payload discipline does not mention {phrase!r}"

    def test_rejection_is_not_safety(self) -> None:
        text = _read(PROVISIONER)
        assert re.search(r"rejection is not safety", text, re.IGNORECASE), (
            "the 'rejected payload is not proof of safety' rule is absent"
        )
        assert "before the value was interpreted" in text.lower(), (
            "the rule does not carve out rejection-before-interpretation as genuine evidence"
        )

    def test_static_runtime_only_for_structural(self) -> None:
        text = _read(PROVISIONER)
        assert re.search(
            r"static.{0,160}only for a STRUCTURAL|behavioural claim recorded as `?static`?",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "the provisioner still permits `Runtime: static` on a behavioural claim"

    def test_runtime_line_has_hold_form(self) -> None:
        text = _read(PROVISIONER)
        assert "Runtime: HOLD-UNVERIFIED" in text, (
            "the Runtime line has no HOLD form, so a behavioural HOLD has nothing to record"
        )

    def test_no_contradiction_between_container_and_probe(self) -> None:
        """Step 3 must not demand a container for a claim the ladder already closed."""
        text = _read(PROVISIONER)
        step3 = text[text.find("## Step 3") :][:900]
        assert re.search(r"unless|already settled", step3, re.IGNORECASE), (
            "Step 3 still says 'container, no exceptions' while the ladder allows in-process"
        )


# --------------------------------------------------------------------------
# §4.4 — report + phase3a integration
# --------------------------------------------------------------------------


class TestReportIntegration:
    """HOLDs reach the report and Phase 3a intake."""

    def test_phase4_has_unverified_section(self) -> None:
        text = _read(PHASE4)
        assert "## Unverified" in text or "Unverified section" in text, (
            "the report template has no Unverified section"
        )

    def test_unverified_never_counted_confirmed(self) -> None:
        text = _read(PHASE4)
        window = text[text.find("Unverified section") :][:2000]
        assert re.search(r"never counted as confirmed|excludes HOLDs", window, re.IGNORECASE), (
            "the Unverified section does not say HOLDs are excluded from the confirmed count"
        )

    def test_unverified_requires_probe(self) -> None:
        text = _read(PHASE4)
        window = text[text.find("Unverified section") :][:2500]
        assert "probe" in window.lower(), (
            "Unverified entries are not required to name the probe that would settle them"
        )

    def test_phase4_lists_unverified_in_report_contents(self) -> None:
        text = _read(SKILL_DOC)
        assert re.search(r"Unverified", text), (
            "vulnhunt/SKILL.md does not list the Unverified section among report contents"
        )

    def test_phase3a_has_hold_intake(self) -> None:
        text = _read(PHASE3A)
        assert "HOLD-UNVERIFIED intake" in text, "Phase 3a has no HOLD intake table"
        assert "Probe required" in text, "Phase 3a does not carry the probe forward"

    def test_phase3a_resolves_hold_by_execution_only(self) -> None:
        text = _read(PHASE3A)
        start = text.find("### HOLD-UNVERIFIED intake")
        assert start != -1, "the HOLD-UNVERIFIED intake section heading is missing"
        window = text[start:][:2500]
        assert re.search(
            r"do not promote.{0,120}reading code|not.{0,40}on the strength of reading code",
            window,
            re.IGNORECASE | re.DOTALL,
        ), "Phase 3a could still resolve a HOLD by reading code"

    def test_phase3a_promotion_updates_evidence_field(self) -> None:
        text = _read(PHASE3A)
        start = text.find("### HOLD-UNVERIFIED intake")
        assert start != -1
        window = text[start:][:2500]
        assert "executed-probe" in window, (
            "promotion does not require updating the claim record to executed-probe"
        )


# --------------------------------------------------------------------------
# §4.4 — no regression to the vocabulary (scope guard, plan §2)
# --------------------------------------------------------------------------


class TestScopeGuard:
    """A2 must not rename existing literals or add a phase."""

    def test_existing_verdict_literals_unchanged(self) -> None:
        text = _read(PHASE2B)
        for literal in ("CONFIRMED", "FALSE POSITIVE"):
            assert literal in text, f"{literal} was renamed away"

    def test_no_new_phase_directory(self) -> None:
        """A2 is skill-text work: no new phase file may appear (plan §2, §8)."""
        phases = sorted(p.name for p in (REPO_ROOT / "vulnhunt" / "phases").iterdir())
        expected = sorted(
            [
                "phase1_recon.md",
                "phase2_class_inj.md",
                "phase2_class_log.md",
                "phase2_class_nav.md",
                "phase2_hunt.md",
                "phase2_shared.md",
                "phase2b_verify.md",
                "phase3a_build_poc.md",
                "phase3b_measure_impact.md",
                "phase3c_fixes.md",
                "phase3d_sweep.md",
                "phase4_report.md",
            ]
        )
        assert phases == expected, f"phase set changed; A2 adds no phase. Got {phases}"

    def test_no_new_agent_directory(self) -> None:
        for unexpected in ("vulnhunter-claim-typing", "vulnhunter-verify"):
            assert not (REPO_ROOT / unexpected).exists(), (
                f"A2 added a new component directory: {unexpected}"
            )


# --------------------------------------------------------------------------
# §4.2 positive control — a hunt-time BREAKOUT is also a behavioural claim
# --------------------------------------------------------------------------


class TestPromotionPositiveControl:
    """The rule binds promotions too, not just eliminations (plan §4.2, review finding).

    The Gate 6 replay covers the elimination direction. This covers the other:
    a hunter who claims "the payload DOES break out" is making a behavioural
    claim about the parser, and equally may not close it on reading a string.
    Without this, A2 would only ever catch false negatives and would let
    false positives (promotions) through.
    """

    def test_promotion_requires_execution(self) -> None:
        text = _phase2b()
        window = text[text.find("#### Execution rule") :][:1400]
        assert re.search(r"both directions", window, re.IGNORECASE), (
            "the execution rule does not state it binds promotions as well as eliminations"
        )
        assert re.search(r"promotion", window, re.IGNORECASE), (
            "the execution rule never names the promotion direction"
        )

    def test_unprobed_promotion_is_hold_not_confirmed(self) -> None:
        """A behavioural promotion with only static reasoning cannot be CONFIRMED."""
        text = _phase2b()
        window = text[text.find("#### Execution rule") :][:1400]
        assert re.search(
            r"(promotion|confirm).{0,200}HOLD-UNVERIFIED|HOLD-UNVERIFIED.{0,200}(promotion|confirm)",
            window,
            re.IGNORECASE | re.DOTALL,
        ), "an unprobed behavioural promotion is not required to be HOLD-UNVERIFIED"

    def test_breakout_claim_is_behavioural(self) -> None:
        """The text classifies 'the payload breaks out' as behavioural explicitly."""
        text = _phase2b()
        assert re.search(
            r"payload breaks out|breaks out.{0,80}behavioural|behavioural.{0,80}breaks out",
            text,
            re.IGNORECASE | re.DOTALL,
        ), "the text does not explicitly classify a breakout claim as behavioural"


# --------------------------------------------------------------------------
# The classification rule is APPLIED, not merely parsed (round-3 blocker)
# --------------------------------------------------------------------------


class TestRuleIsApplied:
    """Prove the parsed rule drives behaviour, rather than being decorative.

    Round-3 review finding: `boundary` was parsed and then ignored. A tripwire
    only proves the prose exists; it does not prove the prose decides anything.
    Round-4 questioned whether the flip acts on the shipped rule; the tests below
    assert that the object being flipped IS the parsed shipped rule, by checking
    its base behaviour matches what the prose says.
    These tests flip the rule in memory and require the verdict to flip with it.
    If the predicate is hard-coded, they fail.
    """

    @staticmethod
    def _flipped(rule: dict[str, object]) -> dict[str, object]:
        """Invert the predicate the SHIPPED rule parsed into.

        Round-4 review asked whether this flips a one-off copy rather than the
        shipped rule. It flips the predicate that the shipped prose produced —
        `test_rule_flip_uses_the_shipped_predicate` below proves the base object
        is the parsed rule, not a hand-built stub.
        """
        classify = rule["classify"]
        assert callable(classify)

        def inverted(cites_in_repo_decider: bool) -> str:
            answer = classify(cites_in_repo_decider)
            return "structural" if answer == "behavioural" else "behavioural"

        return {**rule, "classify": inverted}

    def test_rule_flip_uses_the_shipped_predicate(self) -> None:
        """The object being flipped is the rule parsed from the shipped prose."""
        text = _phase2b()
        real = classification_rule(text)
        # The base predicate must answer the same way the prose says it should.
        classify = real["classify"]
        assert callable(classify)
        assert classify(True) == "structural", (
            "the shipped prose says an in-repo deciding fact is structural; the "
            "parsed predicate disagrees, so it is not derived from the prose"
        )
        assert real["negated"] is True
        # And flipping THAT predicate must change those answers.
        flipped = self._flipped(real)
        assert flipped["classify"](True) == "behavioural"
        assert flipped["classify"](False) == "structural"

    def test_in_repo_decider_goes_structural_under_the_written_rule(self) -> None:
        """The rule as written makes an in-repo deciding fact structural."""
        real = classification_rule(_phase2b())
        assert real["negated"] is True, (
            "the written rule should be the negated form (behavioural == NOT decided in-repo)"
        )
        classify = real["classify"]
        assert callable(classify)
        assert classify(True) == "structural"
        assert classify(False) == "behavioural"

    def test_negation_is_read_from_the_prose(self) -> None:
        """Inverting the sentence in memory changes which direction the predicate runs."""
        text = _phase2b()
        # The prose wraps across lines, so operate on the flattened form.
        flat = " ".join(text.split())
        inverted_text = flat.replace(
            "*not decidable by re-reading the source in this repository*",
            "*decidable by re-reading the source in this repository*",
        )
        assert inverted_text != flat, "the rule sentence was not found to invert"
        real = classification_rule(text)
        inv = classification_rule(inverted_text)
        assert real["negated"] is True and inv["negated"] is False, (
            "the parser did not notice the negation being removed from the rule"
        )
        classify_inv = inv["classify"]
        assert callable(classify_inv)
        assert classify_inv(True) == "behavioural", (
            "inverted rule should treat an in-repo deciding fact as behavioural"
        )


# --------------------------------------------------------------------------
# S6 — HOLDs survive the report's count checks (round-3 blocker)
# --------------------------------------------------------------------------


class TestHoldSurvivesCountChecks:
    """A HOLD must not be dropped by the orchestrator's instance-count equation.

    Round-3 blocker: `vulnhunt/SKILL.md` cross-checks candidates against
    "confirmed + eliminated/downgraded". With no HOLD bucket, any run holding a
    finding fails the check and the reviewer is told they dropped instances they
    did not drop. Phase 2b routing said "not dropped", but the count equation
    contradicted it — the drop happened at the last gate, in the orchestrator.
    """

    def test_instance_count_equation_includes_holds(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("cross-check instance counts")
        assert i != -1, "the instance-count cross-check is missing from vulnhunt/SKILL.md"
        window = " ".join(text[i : i + 1400].split())
        assert "Held" in window, (
            "the instance-count equation has no Held bucket — a held finding makes "
            "the counts unsatisfiable"
        )
        assert re.search(r"not part of `Candidates`", window), (
            "the equation does not separate Held from Candidates, so a HOLD is counted twice"
        )

    def test_summary_table_count_mentions_holds(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("count the HOLDs separately")
        assert i != -1, "the summary-table count check does not separately account for HOLDs"
        window = text[i : i + 800]
        assert "Unverified" in window and "promoted" in window.lower(), (
            "the HOLD accounting does not name both destinations (open vs promoted)"
        )

    def test_hold_is_a_disposition_not_a_drop(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("cross-check instance counts")
        window = " ".join(text[i : i + 1400].split())
        assert re.search(r"disposition like any", window, re.IGNORECASE), (
            "the count equation does not explain why a HOLD belongs in the audit count"
        )


# --------------------------------------------------------------------------
# S6 — HOLDs must not be dropped at the Phase 3 boundary (round-5 majors)
# --------------------------------------------------------------------------


class TestHoldCrossesPhase3:
    """A HOLD must survive from 2b into 3a, and the tally must match Phase 4's.

    Round-5 majors: (1) the orchestrator's HOLD tally had two buckets while
    Phase 4's reconciliation has three, so a disproved HOLD would be mislabelled
    as dropped; (2) phase2b still said only CONFIRMED findings proceed to Phase 3,
    which drops Medium+ HOLDs before Phase 3a can settle them.
    """

    def test_orchestrator_tally_has_three_buckets(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("count the HOLDs separately")
        assert i != -1, "the orchestrator HOLD tally is missing"
        window = text[i : i + 1200]
        assert "(c)" in window, (
            "the orchestrator tally names only two destinations; a disproved HOLD "
            "has no bucket and would be reported as dropped"
        )
        assert "DISPROVED" in window.upper(), "the third bucket does not name disproof"
        assert "verification table" in window.lower(), (
            "the disproof bucket does not say where the finding goes"
        )

    def test_orchestrator_tally_matches_phase4_reconciliation(self) -> None:
        """Both texts must describe the same three buckets."""
        skill = _read(SKILL_DOC)
        report = _read(PHASE4)
        for label, text in (("SKILL.md", skill), ("phase4_report.md", report)):
            assert "Unverified" in text
            assert "promoted" in text.lower() or "promotion" in text.lower()
            assert "disprov" in text.lower(), (
                f"{label} does not have a disproof bucket in its HOLD accounting"
            )

    def test_holds_proceed_to_phase3a(self) -> None:
        text = _read(PHASE2B)
        i = text.find("Drop all FALSE POSITIVE findings")
        assert i != -1
        window = text[i : i + 900]
        assert "HOLD-UNVERIFIED" in window, (
            "phase2b still says only CONFIRMED findings proceed to Phase 3 — "
            "Medium+ HOLDs are dropped before 3a can settle them"
        )
        assert re.search(r"HOLD.{0,120}Phase 3a", window, re.IGNORECASE | re.DOTALL), (
            "the closing rule does not route HOLDs to Phase 3a"
        )

    def test_phase3a_opening_admits_holds(self) -> None:
        text = _read(PHASE3A)
        opening = text[:1200]
        assert "HOLD-UNVERIFIED" in opening, (
            "phase3a's context line still says CONFIRMED findings only"
        )

    def test_orchestrator_launch_names_holds(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("Read confirmed findings")
        assert i != -1, "the Phase 3a launch line is missing"
        window = text[i : i + 300]
        assert "HOLD" in window, (
            "the Phase 3a launch instruction does not name HOLDs among its inputs"
        )

    def test_zero_confirmed_with_open_holds_is_not_code_quality_only(self) -> None:
        """A run with zero confirmed but open HOLDs must report the HOLDs."""
        text = _read(PHASE2B)
        i = text.find("If zero CONFIRMED findings survive")
        assert i != -1, (
            "phase2b does not distinguish 'zero confirmed, no holds' from "
            "'zero confirmed, holds open'"
        )
        window = text[i : i + 500]
        assert "Unverified" in window, (
            "the zero-confirmed rule does not send open HOLDs to the Unverified section"
        )


# --------------------------------------------------------------------------
# S6 — the last gates must not dispose of a HOLD (round-6 majors)
# --------------------------------------------------------------------------


class TestNoGateDiscardsAHold:
    """Every gate between Phase 2b and the report must admit HOLDs.

    Round-6 findings: (1) a zero-CONFIRMED run still took the early exit and
    skipped Phase 3a, so its HOLDs never got a probe; (2) Phase 4 admitted only
    HOLDs that "survived Phase 3a", which is exactly the HOLDs that did NOT need
    its protection; (3) the validation rule disposed of unproven findings as
    "Potential", a silent third way to lose a HOLD.
    """

    def test_early_exit_requires_zero_holds_too(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("If the audit ends early")
        assert i != -1, "the early-exit sentence is missing from vulnhunt/SKILL.md"
        window = text[i : i + 900]
        assert re.search(r"zero CONFIRMED.{0,60}zero HOLD", window, re.IGNORECASE | re.DOTALL), (
            "the early exit is still described as 'zero findings', which is true for a "
            "zero-CONFIRMED run with open HOLDs that must still reach Phase 3a"
        )
        assert re.search(
            r"does\s+\*\*not\*\*\s+end early|does not end early", window, re.IGNORECASE
        ), "the text does not say a zero-CONFIRMED run with HOLDs fails to end early"

    def test_phase4_admits_holds_without_phase3a(self) -> None:
        text = _read(PHASE4)
        i = text.find("Every `HOLD-UNVERIFIED` finding")
        assert i != -1
        window = text[i : i + 1200]
        assert re.search(r"never reached Phase 3a|did not survive Phase 3a", window), (
            "Phase 4 still admits only HOLDs that survived Phase 3a, so an unrunnable "
            "probe silently drops the finding"
        )
        assert "unrunnable" in window.lower() or "could not run" in window.lower(), (
            "Phase 4 does not say that an unrunnable probe still belongs in Unverified"
        )

    def test_report_banner_includes_unverified(self) -> None:
        text = _read(PHASE4)
        opening = text[:600]
        assert "Unverified" in opening, (
            "the report context banner still names only confirmed findings, code smells "
            "and the inventory"
        )

    def test_validation_rule_does_not_dispose_holds_as_potential(self) -> None:
        text = _read(PHASE4)
        i = text.find("VALIDATION RULE")
        assert i != -1
        window = text[i : i + 2200]
        assert "HOLD-UNVERIFIED" in window, (
            "the validation rule only offers 'downgraded to Potential or eliminated', "
            "which loses a HOLD whose probe was unrunnable"
        )
        assert "Unverified" in window, (
            "the validation rule does not route unrunnable probes to the Unverified section"
        )

    def test_prove_it_rule_distinguishes_structural_from_behavioural(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("**Prove it**")
        assert i != -1
        window = text[i : i + 700]
        assert "structural" in window.lower() and "behavioural" in window.lower(), (
            "the Prove-it principle does not distinguish a static-trace structural PoC "
            "from an executed behavioural PoC"
        )

    def test_structural_claim_closes_on_existing_test(self) -> None:
        """The prose allows existing-test for structural claims; the harness must too.

        Round-7 nit: `parse_rules` captured only static-trace, so a structural
        claim closed by an existing test was wrongly HOLDed. The over-strictness
        control row also avoided the word "test", so this path was untested.
        """
        rules = parse_rules(_phase2b())
        boundary = classification_rule(_phase2b())
        row = (
            "| VULN-010 | Yes | No - the only writer is the coordinator; "
            "existing test TestNoUserWrites proves the path is unreachable | "
            "N/A | N/A | 3/3 | FALSE POSITIVE |"
        )
        assert claim_type_of(row, boundary) == "structural"
        assert evidence_of(row) == "existing-test"
        assert apply_rules(row, rules, boundary) == "FALSE POSITIVE", (
            "a structural claim closed by an existing test was wrongly HOLDed"
        )

    def test_structural_detector_reads_the_prose(self) -> None:
        """The detector's phrases must come from the skill, not from this file."""
        text = _phase2b()
        phrases = structural_examples(text)
        for example in (
            "the only writer is the coordinator",
            "the regex is anchored",
            "the orm parameterizes it",
        ):
            assert example in phrases, (
                f"the structural detector did not pick up {example!r} from the skill prose"
            )
        # Generic words must not have crept in as bare seeds.
        assert "caller" not in phrases, (
            "a bare generic noun is in the detector and will match unrelated prose"
        )


# --------------------------------------------------------------------------
# S6 — the phases AROUND 2b must apply claim typing too (round-7 majors)
# --------------------------------------------------------------------------


class TestPhaseSurroundsApplyClaimTyping:
    """Claim typing must hold at the sweep and at Phase 3 completion.

    Round-7 majors: (1) Phase 3 completion required populated poc/ dirs, so a
    HOLD-only run never reached the report and would be relaunched forever;
    (2) sweep triage disposed of an unproven behavioural instance as MITIGATED
    with no HOLD outcome — the Gate 6 mistake reproduced in a file A2 never
    touched.
    """

    def test_phase3_completion_allows_hold_only_runs(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("Verify `${VULNHUNT_DIR}/phase3_output.md` exists")
        assert i != -1, "the Phase 3 completion check is missing"
        window = text[i : i + 800]
        assert re.search(r"all HOLD|no confirmed", window, re.IGNORECASE), (
            "Phase 3 completion still requires a populated poc/ directory, so a "
            "HOLD-only run never reaches the report"
        )
        assert "relaunch" in window.lower() or "failed phase" in window.lower(), (
            "the text does not tell the orchestrator not to treat an empty poc/ as failure"
        )

    def test_sweep_triage_has_a_hold_outcome(self) -> None:
        text = _read(PHASE3D)
        assert "Triage verdict" in text, "the sweep triage verdict list is missing"
        i = text.find("Triage verdict")
        window = text[i : i + 900]
        assert "HOLD-UNVERIFIED" in window, (
            "sweep triage offers only CANDIDATE/MITIGATED/DEV-ONLY — an unproven "
            "behavioural instance has nowhere to go but Mitigated or eliminated"
        )

    def test_sweep_states_mitigated_requires_structural_claim(self) -> None:
        text = _read(PHASE3D)
        i = text.find("A mitigation is only")
        assert i != -1, (
            "the sweep does not distinguish a structural mitigation from a "
            "behavioural one it has not executed"
        )
        window = text[i : i + 700]
        assert "structural" in window.lower()
        assert re.search(r"sanitizer|parser|library|framework", window, re.IGNORECASE), (
            "the sweep does not name the dependency-behaviour case as the HOLD case"
        )

    def test_sweep_fail_path_routes_to_unverified(self) -> None:
        text = _read(PHASE3D)
        i = text.find("Instances that pass the full pipeline")
        assert i != -1
        window = text[i : i + 1600]
        assert "Unverified" in window, (
            "a held sweep instance is not routed to the report's Unverified section"
        )
        assert "claim typing" in window.lower(), (
            "the sweep does not apply claim typing before disposing of an instance"
        )

    def test_report_checklist_names_the_unverified_section(self) -> None:
        text = _read(PHASE4)
        i = text.find("After the header, include")
        assert i != -1
        window = text[i : i + 1000]
        assert "Unverified" in window, (
            "the report's entry-point checklist can be completed without ever "
            "producing the Unverified section"
        )

    def test_report_cross_checks_unverified_against_phase2b(self) -> None:
        text = _read(PHASE4)
        i = text.find("Cross-check before writing")
        assert i != -1, "the report does not cross-check the Unverified count"
        window = text[i : i + 900]
        assert "Phase 2b HOLD total" in window, (
            "the cross-check does not require the Unverified entries to reconcile "
            "against the Phase 2b HOLD count"
        )


# --------------------------------------------------------------------------
# S6 — deferral, stopping, sweep accounting, mock scope (round-8 majors)
# --------------------------------------------------------------------------


class TestHoldAccountingIsComplete:
    """Every way a HOLD can legitimately leave the flow must be stated.

    Round-8 majors: (1) Phase 4 was forbidden until every HOLD was settled, so a
    Low HOLD deferred by severity could never be reported; (2) the stopping rule
    filed "downstream mitigations" as Code Smells — the Gate 6 elimination with
    the HOLD label stripped off; (3) the sweep's mandatory table had no column
    for a held instance, so a sweep HOLD either mis-filed as Mitigated or
    stalled Phase 4 via Remaining > 0.
    """

    def test_low_hold_may_be_deferred_to_the_report(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("Low-severity HOLDs")
        assert i != -1, (
            "Phase 4's precondition does not exempt deferred Low HOLDs, so a Low "
            "HOLD can never reach the Unverified section"
        )
        window = text[i : i + 700]
        assert "deferred" in window.lower()
        assert re.search(r"terminal disposition|settled", window, re.IGNORECASE), (
            "the text does not say a deferred Low HOLD counts as a terminal disposition"
        )

    def test_stopping_rule_splits_structural_from_behavioural(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("Do not soften criteria to maintain output")
        assert i != -1
        window = text[i : i + 1900]
        assert "claim-typing" in window.lower() or "claim typing" in window.lower(), (
            "the stopping rule disposes of downstream mitigations without applying claim typing"
        )
        assert "HOLD-UNVERIFIED" in window, (
            "the stopping rule never mentions HOLD, so a behavioural mitigation "
            "becomes a Code Smell"
        )
        assert re.search(r"dependency", window, re.IGNORECASE), (
            "the stopping rule does not name the dependency-behaviour case"
        )

    def test_stopping_rule_says_hold_is_not_a_code_smell(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("A HOLD is never a Code Smell")
        assert i != -1, "the stopping rule does not state that a HOLD is not a Code Smell"

    def test_sweep_table_can_represent_a_hold(self) -> None:
        text = _read(PHASE3D)
        i = text.find("| Root Cause |")
        assert i != -1, "the mandatory sweep table is missing"
        header = text[i : text.find("\n", i)]
        assert "Held" in header, (
            "the sweep table has no Held column, so a HOLD-UNVERIFIED instance "
            "cannot be accounted for and will be mis-filed as Mitigated"
        )

    def test_sweep_remaining_is_unaccounted_not_held(self) -> None:
        text = _read(PHASE3D)
        i = text.find("`Remaining` is *unaccounted*")
        assert i != -1, (
            "the sweep does not distinguish Remaining (unaccounted) from Held "
            "(accounted), so a held instance stalls the report"
        )
        window = " ".join(text[i : i + 400].split())
        assert "does not block" in window.lower(), (
            "the text does not say a populated Held column does not block the report"
        )

    def test_sweep_held_reconciles_with_unverified(self) -> None:
        text = _read(PHASE3D)
        i = text.find("Held instances must reconcile")
        assert i != -1, "the sweep does not reconcile Held instances with the report"
        window = text[i : i + 700]
        assert "Unverified" in window

    def test_executed_mock_does_not_close_a_behavioural_claim(self) -> None:
        text = _read(PROVISIONER)
        i = text.find("What EXECUTED-MOCK settles")
        assert i != -1, "the provisioner does not say what a mock does and does not settle"
        window = text[i : i + 900]
        assert "does **not** close a" in window or "does not close a" in window, (
            "the text does not say a mock alone does not close a behavioural claim"
        )
        assert "HOLD-UNVERIFIED" in window, "a mock-only run is not routed to HOLD-UNVERIFIED"


# --------------------------------------------------------------------------
# S6 — the accounting equations must be mutually satisfiable (round-9 majors)
# --------------------------------------------------------------------------


class TestAccountingEquationsReconcile:
    """The count checks must be arithmetically satisfiable, not just present.

    Round-9 major: the orchestrator equation counted Unverified HOLDs inside the
    sweep Candidates column while the sweep table put the same HOLDs in a
    disjoint Held column. Worked through, the two together forced Held == 0, so
    the very HOLDs the Held column was added to represent could not be reported
    without failing a mandatory check. The round-8 tests only grepped for
    substrings, which is why they stayed green.
    """

    def test_orchestrator_equation_does_not_double_count_holds(self) -> None:
        text = _read(SKILL_DOC)
        i = text.find("cross-check instance counts")
        assert i != -1
        window = " ".join(text[i : i + 1400].split())
        assert re.search(r"Candidates = confirmed .*eliminated.*Held", window, re.IGNORECASE), (
            "the orchestrator equation is not stated as an arithmetic identity"
        )
        assert re.search(r"not part of `Candidates`", window), (
            "the text does not say Held is separate from Candidates, so the same HOLD "
            "is counted twice and the equation becomes unsatisfiable"
        )

    def test_orchestrator_equation_parses_and_closes(self) -> None:
        """Parse the equation OUT OF SKILL.md and check it closes arithmetically.

        Round-10 major: the previous "worked example" asserted literal integers
        and never opened SKILL.md, so deleting the equation left it green. This
        reads the shipped identity, extracts its terms, and evaluates it.
        """
        text = _read(SKILL_DOC)
        eq = equation_terms(text, "Candidates")
        assert eq is not None, "the orchestrator's instance-count identity was not found"
        lhs, rhs = eq
        assert "candidates" in " ".join(lhs).lower(), (
            f"left side should name Candidates, got {lhs!r}"
        )
        # The right side must include a Held disposition term.
        assert any("held" in t.lower() for t in rhs), (
            f"the equation's right side has no Held term: {rhs}"
        )
        # Round-11 nit: a polluted parse would have closed on prose that happened
        # to contain a word the value-mapper knew. Every term must be a short
        # noun phrase with no sentence punctuation.
        for term in rhs:
            assert len(term.split()) <= 8, f"term absorbed prose: {term!r}"
            assert not re.search(r"[.|]", term) or "Code Smell" in term, (
                f"term contains sentence punctuation: {term!r}"
            )

        # Worked example: 2 candidates of a root cause, 1 confirmed, 1 held,
        # 0 eliminated. The parsed equation must close on those numbers.
        recognised = {
            "candidate": 2,
            "confirmed": 1,
            "held": 1,
            "eliminat": 0,
            "downgrad": 0,
            "code smell": 0,
        }

        def value(term: str) -> int:
            low = term.lower()
            for key, number in recognised.items():
                if key in low:
                    return number
            # Round-12 nit: an unrecognised short term silently mapped to 0 and
            # could make a broken equation look like it closed. Fail instead.
            raise AssertionError(
                f"equation term {term!r} is not one this test knows how to value; "
                "add it to `recognised` rather than letting it default to 0"
            )

        sum_lhs = sum(value(t) for t in lhs)
        sum_rhs = sum(value(t) for t in rhs)
        assert sum_lhs == 2, f"left side should evaluate to 2 candidates, got {sum_lhs}"
        assert sum_rhs == sum_lhs, (
            f"the parsed equation does not close: RHS {rhs} sums to {sum_rhs}, not {sum_lhs}"
        )

    def test_report_reconcile_parses_and_closes(self) -> None:
        """Parse the sweep/report HOLD reconciliation and check it closes."""
        text = _read(PHASE3D)
        eq = equation_terms(text, None, prefer="Unverified")
        assert eq is not None, "the sweep HOLD reconciliation equation was not found"
        lhs, rhs = eq
        # A run with 2 sweep Held and 1 Phase 2b HOLD, all still open, must close.
        values = {
            "Unverified": 2 + 1,
            "promoted": 0,
            "disproved": 0,
            "Phase2bHOLD": 1,
            "sweepHeld": 2,
        }

        def value(term: str) -> int:
            low = term.lower()
            if "phase 2b" in low:
                return values["Phase2bHOLD"]
            if "sweep" in low and "held" in low:
                return values["sweepHeld"]
            for key in values:
                if key.lower() in low:
                    return values[key]
            return 0

        sum_lhs = sum(value(t) for t in lhs)
        sum_rhs = sum(value(t) for t in rhs)
        assert sum_lhs == sum_rhs, (
            f"the reconciliation does not close when sweep Held > 0: "
            f"LHS {lhs} = {sum_lhs}, RHS {rhs} = {sum_rhs}"
        )

    def test_sweep_reconcile_uses_one_equality_not_a_sum(self) -> None:
        text = _read(PHASE3D)
        i = text.find("Held instances must reconcile")
        assert i != -1
        window = " ".join(text[i : i + 900].split())
        assert re.search(r"do not add them together", window, re.IGNORECASE), (
            "the sweep reconcile still reads as a sum of two independent pools"
        )
        assert re.search(r"Phase 2b HOLDs \+ sweep Held", window), (
            "the reconcile does not use the single combined total"
        )

    def test_phase4_hold_reconcile_still_names_three_buckets(self) -> None:
        text = _read(PHASE4)
        i = text.find("Cross-check before writing")
        assert i != -1
        window = " ".join(text[i : i + 900].split())
        assert "Phase 2b HOLD total" in window


class TestEveryDispositionPathAppliesClaimTyping:
    """Round-9 majors: Phase 2 and Phase 4 could still dispose of a behavioural claim."""

    def test_injection_gate_does_not_close_behavioural_by_reading_source(self) -> None:
        text = _read(REPO_ROOT / "vulnhunt" / "phases" / "phase2_class_inj.md")
        i = text.find("Empirically verify what the sanitizer does")
        assert i != -1, "the injection sanitizer-verification block is missing"
        window = " ".join(text[i : i + 1600].split())
        assert "behavioural" in window.lower(), (
            "the injection gate still treats (a) reading the sanitizer source as "
            "sufficient, which is the Gate 6 elimination"
        )
        assert "HOLD" in window, (
            "the injection gate does not route an unsettled behavioural claim to HOLD"
        )

    def test_phase4_does_not_file_dependency_questions_as_code_smells(self) -> None:
        text = _read(PHASE4)
        i = text.find("dependency's")
        assert i != -1
        window = " ".join(text[max(0, i - 700) : i + 900].split())
        assert re.search(r"internal code to confirm", window), (
            "the dependency-CVE passage is not where expected"
        )
        assert "HOLD-UNVERIFIED" in window, (
            "Phase 4 still files a dependency-internals question as a Code Smell, "
            "contradicting the stopping rule"
        )


# --------------------------------------------------------------------------
# Round-9 minor/nit: mock scope and the classification basis
# --------------------------------------------------------------------------


class TestMockAndClassificationHonesty:
    def test_step5_mock_does_not_satisfy_claim_settlement(self) -> None:
        text = _read(PROVISIONER)
        i = text.find('satisfies the "must execute something" requirement')
        assert i != -1, (
            "Step 5's checklist lets EXECUTED-MOCK pass as a completed Medium+ "
            "hand-off, so a mock-only behavioural claim is never HOLDed"
        )
        window = " ".join(text[i : i + 700].split())
        assert "HOLD-UNVERIFIED" in window, (
            "the checklist does not require EXECUTED-MOCK claims to also carry a HOLD line"
        )

    def test_classification_records_its_basis(self) -> None:
        """A row classified behavioural by ABSENCE must say so."""
        text = _phase2b()
        boundary = classification_rule(text)
        rows = [
            ln
            for ln in _read(FIXTURES / "gate6_phase2b_elimination.md").splitlines()
            if ln.startswith("| VULN-")
        ]
        for row in rows:
            claim_type_of(row, boundary)
            basis = getattr(claim_type_of, "last_basis", "")
            assert basis, "classification did not record why it decided"
            # These rows cite no quoted structural example, so the basis must say so
            # rather than looking like a positive behavioural finding.
            assert "no quoted structural example" in basis or "cited in-repo" in basis


# --------------------------------------------------------------------------
# Round-10 majors/minor/nit
# --------------------------------------------------------------------------


class TestOptionBReachesTheConsumer:
    def test_injection_option_b_feeds_output_to_the_real_consumer(self) -> None:
        """Option (b) must exercise the consumer, not just print the sanitizer's output.

        Round-10 major: the text allowed option (b) as a close path while option
        (b)'s own example (`node -e 'console.log(xss(x))'`) only shows what the
        sanitizer returns — option (a) in executable form. escapeVisibility could
        still be marked SAFE before Phase 2b.
        """
        text = _read(REPO_ROOT / "vulnhunt" / "phases" / "phase2_class_inj.md")
        i = text.find("must feed the sanitizer's OUTPUT")
        assert i != -1, (
            "the injection gate does not require option (b) to feed the sanitizer's "
            "output to the real consumer"
        )
        window = " ".join(text[i : i + 900].split())
        assert re.search(r"real consumer|actual parser|parser/builder", window), (
            "option (b) is not tied to the downstream consumer"
        )
        assert "HOLD-UNVERIFIED" in window, (
            "the text does not say what to do when option (b) cannot reach the consumer"
        )


class TestRuntimeFormsAreCoherent:
    def test_step4_allows_mock_plus_hold_on_one_line(self) -> None:
        """Step 4 ("one form") and Step 5 ("also HOLD") must not contradict."""
        text = _read(PROVISIONER)
        i = text.find("Every finding MUST carry a Runtime line")
        assert i != -1
        window = " ".join(text[i : i + 1100].split())
        assert "mutually exclusive" in window.lower(), (
            "Step 4 does not say the Runtime forms are mutually exclusive"
        )
        assert re.search(r"EXECUTED-MOCK.{0,500}HOLD-UNVERIFIED", window), (
            "Step 4 does not show the combined mock+HOLD form, contradicting Step 5"
        )

    def test_glossary_uniqueness_tolerates_markdown(self) -> None:
        """A backticked token must still be caught as a redefinition."""
        pattern = re.compile(
            r"`?HOLD-UNVERIFIED`? is (a|an)\b|`?HOLD-UNVERIFIED`? means\b"
            r"|\bmeans `?HOLD-UNVERIFIED"
        )
        assert pattern.search("`HOLD-UNVERIFIED` is a recorded fact"), (
            "the definition regex misses a backticked redefinition"
        )
        assert not pattern.search("A HOLD is a recorded fact (see the vocabulary)")


# --------------------------------------------------------------------------
# Round-11: the UPSTREAM gates must apply claim typing too
# --------------------------------------------------------------------------


PHASE2_SHARED = REPO_ROOT / "vulnhunt" / "phases" / "phase2_shared.md"
PHASE2_INJ = REPO_ROOT / "vulnhunt" / "phases" / "phase2_class_inj.md"


class TestUpstreamGatesApplyClaimTyping:
    """Gates before Phase 2b must not eliminate a behavioural claim on read-source.

    Round-11 majors: (1) the injection gate's operative option (b) still
    prescribed printing the sanitizer's own return value, contradicting the
    paragraph above it; (2) the hunt-wide Gate 2b eliminated on read-source with
    no HOLD branch, so the claim never became an Unverified item.

    These are the earliest gates in the pipeline, which is what makes them
    dangerous: an elimination here is never re-examined, because Phase 2b only
    re-verifies candidates.
    """

    def test_shared_gate2b_has_a_hold_branch(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("If effective, context-matched defense exists")
        assert i != -1, "the Gate 2b elimination sentence is missing"
        window = " ".join(text[i : i + 1200].split())
        assert "structural" in window.lower(), (
            "Gate 2b eliminates a defense without distinguishing structural from behavioural claims"
        )
        assert "HOLD-UNVERIFIED" in window, (
            "Gate 2b has no HOLD branch, so a behavioural claim is eliminated at the "
            "earliest gate and never re-examined"
        )
        assert re.search(r"parser|template engine|ORM|auto-escap|parameteris", window), (
            "Gate 2b does not name the dependency-behaviour case"
        )

    def test_injection_option_b_block_requires_the_consumer(self) -> None:
        text = _read(PHASE2_INJ)
        i = text.find("**(b) Construct a test expression**")
        assert i != -1, "the operative option (b) block is missing"
        window = " ".join(text[i : i + 1400].split())
        assert re.search(r"real consumer|actual query builder|parser", window), (
            "option (b)'s own block still only prints the sanitizer's return value, "
            "contradicting the paragraph that condemns exactly that"
        )
        assert "console.log" in window, "the example one-liner should still be shown"

    def test_runtime_form_is_decided_by_claim_type_not_runnability(self) -> None:
        text = _read(PROVISIONER)
        i = text.find("Claim type decides the runtime")
        assert i != -1, (
            "Step 2 still equates 'cannot be exercised' with 'structural', letting an "
            "unrunnable dependency reclassify itself out of being run"
        )
        window = " ".join(text[i : i + 1100].split())
        assert "HOLD-UNVERIFIED" in window
        assert re.search(r"never `static`|never static", window), (
            "the text does not say a behavioural claim that cannot run is HOLD, not static"
        )


# --------------------------------------------------------------------------
# Round-12: the pre-gate terminals must carry a HOLD (the earliest drop points)
# --------------------------------------------------------------------------


PHASE2_HUNT = REPO_ROOT / "vulnhunt" / "phases" / "phase2_hunt.md"


class TestPreGateTerminalsCarryHolds:
    """Round-12 majors: the trace outcome and hunt aggregation had no HOLD slot.

    (1) phase2_shared's trace outcome (b) declared an input SAFE on a behavioural
        sanitizer claim, before any gate ran, and Phase 2b never reopens SAFE.
    (2) hunt aggregation's disposition set had no HOLD-UNVERIFIED, so a HOLD
        written at Gate 2b was folded into SAFE or treated as missing.
    These are the earliest points a finding can be lost, which is why they matter
    most: everything downstream only sees candidates.
    """

    def test_trace_terminal_splits_structural_from_behavioural(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("(b) is proven sanitized or type-constrained")
        assert i != -1, "the trace outcome (b) is missing"
        window = " ".join(text[i : i + 900].split())
        assert "structural" in window.lower(), (
            "trace outcome (b) declares SAFE without distinguishing structural from "
            "behavioural mitigation"
        )
        assert "HOLD-UNVERIFIED" in window, (
            "trace outcome (b) has no HOLD branch, so a behavioural sanitizer claim "
            "is marked SAFE before any gate and never revisited"
        )

    def test_trace_defense_reading_is_structured_only(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("Empirically verify what the defense does")
        assert i != -1
        window = " ".join(text[i : i + 1400].split())
        assert "structural" in window.lower() and "HOLD-UNVERIFIED" in window, (
            "the operative MUST still says reading the defense source confirms it "
            "blocks the attack, with no behavioural caveat"
        )

    def test_hunt_aggregation_has_a_hold_disposition(self) -> None:
        text = _read(PHASE2_HUNT)
        i = text.find("Merge input dispositions")
        assert i != -1, "the hunt aggregation block is missing"
        window = " ".join(text[i : i + 1800].split())
        assert "HOLD-UNVERIFIED" in window, (
            "hunt aggregation has no HOLD-UNVERIFIED disposition, so a Gate 2b HOLD "
            "is folded into SAFE or treated as missing"
        )
        assert re.search(r"HOLD beats SAFE", window, re.IGNORECASE), (
            "the aggregation does not state precedence between HOLD and SAFE"
        )

    def test_phase2b_manifest_admits_holds(self) -> None:
        text = _read(PHASE2B)
        i = text.find("Candidate Manifest")
        assert i != -1
        window = " ".join(text[i : i + 1400].split())
        assert "HOLD-UNVERIFIED entries from Phase 2" in window, (
            "the candidate manifest counts only CANDIDATE entries, so a HOLD from "
            "aggregation is excluded from the verification target"
        )

    def test_planning_doc_defers_to_glossary(self) -> None:
        text = _read_planning_doc("EXPERIMENT_judge_replay_prompt.md")
        i = text.find("- `HOLD-UNVERIFIED`")
        assert i != -1
        window = text[i : i + 300]
        assert "vulnhunt/SKILL.md" in window, (
            "the planning doc restates the HOLD definition instead of deferring to "
            "the canonical glossary"
        )


# --------------------------------------------------------------------------
# Round-13: HOLD must be REACHABLE by the trace agent and TERMINAL at Gate 2b
# --------------------------------------------------------------------------


class TestHoldIsReachableAndTerminal:
    """Round-13 majors: round 12 added a HOLD slot nothing could actually use.

    (1) the trace agent's return vocabulary had no HOLD-UNVERIFIED, so the
        aggregation slot was unreachable and a behavioural claim was coerced to
        SAFE; (2) a HOLD recorded at Gate 2b was not terminal — the next sentence
        sent every non-elimination into Gate 3, which could replace it with a
        Code Smell or an elimination on impact grounds.

    A slot that cannot be reached is not a fix; that is why these tests check the
    vocabulary and the control flow, not just the presence of a sentence.
    """

    def test_trace_agent_return_vocabulary_includes_hold(self) -> None:
        text = _read(PHASE2_HUNT)
        i = text.find("For each input, return:")
        assert i != -1, "the trace agent's return vocabulary is missing"
        window = " ".join(text[i : i + 1400].split())
        assert "HOLD-UNVERIFIED" in window, (
            "the trace agent cannot return HOLD-UNVERIFIED, so the aggregation slot "
            "added for it is unreachable and the claim is coerced to SAFE"
        )

    def test_inventory_enum_includes_hold(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("Record the disposition")
        assert i != -1, "the inventory disposition enum is missing"
        window = " ".join(text[i : i + 1500].split())
        assert "HOLD-UNVERIFIED" in window, (
            "the inventory enum has only CANDIDATE/SAFE/DESIGN-INTENT, so a HOLD "
            "recorded during tracing has no legal value to be written as"
        )

    def test_hold_is_terminal_at_gate2b(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("If not eliminated, proceed to Gate 3")
        assert i != -1, "the Gate 2b -> Gate 3 transition is missing"
        window = " ".join(text[i : i + 700].split())
        assert re.search(r"HOLD-UNVERIFIED.{0,120}terminal", window, re.IGNORECASE | re.DOTALL), (
            "a HOLD is forwarded into Gate 3, where it can be re-dispositioned as a "
            "Code Smell or eliminated on impact grounds"
        )

    def test_gate3_codesmell_requires_a_run(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("Gate 3: Does the attacker gain a NEW capability")
        assert i != -1
        window = " ".join(text[i : i + 900].split())
        assert re.search(r"only if you actually ran", window, re.IGNORECASE), (
            "Gate 3 files a code smell without distinguishing a HOLD whose probe "
            "never ran from a finding whose exploit test ran and failed"
        )

    def test_sanitizer_coverage_match_is_not_proof_for_behavioural(self) -> None:
        """A character-coverage match must not force SAFE on a behavioural claim."""
        text = _read(PHASE2_SHARED)
        i = text.find("Sanitizer-sink match check")
        assert i != -1
        window = " ".join(text[i : i + 1800].split())
        assert "HOLD-UNVERIFIED" in window, (
            "a coverage match sends the input to SAFE unconditionally; the quote-"
            "doubling sanitizer that covered quotes still failed in Gate 6"
        )

    def test_safe_reason_sanitized_requires_structural(self) -> None:
        text = _read(PHASE2_SHARED)
        i = text.find("Record the disposition")
        window = " ".join(text[i : i + 1500].split())
        assert re.search(r"sanitized` reason is only valid when.{0,80}structural", window), (
            "a `sanitized` SAFE reason is accepted without checking that the claim is structural"
        )


# --------------------------------------------------------------------------
# Round-14 residues (APPROVE was returned; these clear the remaining nits)
# --------------------------------------------------------------------------


class TestRound14Residues:
    def test_fixture_column_note_names_the_real_columns(self) -> None:
        text = _read(FIXTURES / "gate6_phase2b_elimination.md")
        i = text.find("Column note")
        assert i != -1
        window = " ".join(text[i : i + 900].split())
        assert "All call sites checked?" in window, (
            "the fixture note claims a 'Runtime decision' column the original table "
            "did not have; the real column was 'All call sites checked?'"
        )
        assert "no" in window.lower() and "Runtime" in window, (
            "the note should say explicitly that Runtime decision is A2's new column"
        )

    def test_report_inventory_checklist_admits_holds(self) -> None:
        text = _read(PHASE4)
        i = text.find("as a completeness artifact")
        assert i != -1
        window = " ".join(text[max(0, i - 200) : i + 400].split())
        assert "HOLD-UNVERIFIED" in window, (
            "the resolved-inventory checklist lists only CANDIDATE/SAFE/DESIGN-INTENT, "
            "so a HOLD input has no legal value"
        )

    def test_injection_option_c_holds_when_behavioural_and_unrunnable(self) -> None:
        text = _read(PHASE2_INJ)
        i = text.find("(c) If you cannot read the source")
        assert i != -1
        window = " ".join(text[i : i + 1400].split())
        assert "HOLD-UNVERIFIED" in window, (
            "option (c) sends an unrunnable behavioural claim to Gate 3 as a live "
            "candidate instead of recording a HOLD"
        )
        assert re.search(r"rung 2|rung 3|container", window), (
            "option (c) does not name the probe rung that would settle it"
        )

    def test_provisioner_hold_is_one_line_not_two(self) -> None:
        text = _read(PROVISIONER)
        i = text.find("behavioural finding not yet executed")
        assert i != -1
        window = " ".join(text[i : i + 700].split())
        assert re.search(r"SAME Runtime line|not as\s+a second", window), (
            "Step 5 asks for a second Runtime: line while Step 4 says one line"
        )

    def test_experiment_prompt_does_not_restate_the_definition(self) -> None:
        text = _read_planning_doc("EXPERIMENT_judge_replay_prompt.md")
        i = text.find("- `HOLD-UNVERIFIED`")
        assert i != -1
        window = text[i : text.find("\n", i)]
        assert "here it means" not in window, (
            "the experiment prompt says it is not restating the definition, then restates it"
        )
        assert (
            "adds one requirement" in window.lower()
            or "on top of that definition" in window.lower()
        )


class TestEmptyUnverifiedSectionIsExplicit:
    """BUILD_B3 §4.3: an empty Unverified section must still appear with `none`.

    Round-14/merge review found A2 said "omit the section when there are no
    HOLDs", which collides with the plan B3 is built against: an omitted section
    is indistinguishable from a forgotten one.
    """

    def test_empty_section_is_printed_with_none(self) -> None:
        text = _read(PHASE4)
        i = text.find("If there are no HOLDs")
        assert i != -1, "the empty-Unverified rule is missing"
        window = " ".join(text[i : i + 800].split())
        assert re.search(r"still print the section", window, re.IGNORECASE), (
            "the report still omits the section when empty, contradicting B3 §4.3"
        )
        assert "`none`" in window, "the text does not say what to print"
        assert "omit" not in window.split(".")[0].lower() or "still print" in window.lower()


class TestUnverifiedSectionRulesAreConsistent:
    """Merge round 2: the checklist said omit-when-empty while the section rule said print-none.

    Both sentences described the same section and disagreed. Whichever the report
    writer read second won, so the outcome was down to reading order.
    """

    def test_checklist_and_section_rule_agree(self) -> None:
        text = _read(PHASE4)
        flat = " ".join(text.split())

        # The checklist line, bounded to its own bullet: the next bullet starts at
        # "- The resolved input inventory", and a fixed window would bleed into it.
        i = flat.find("- The `## Unverified` section for every open")
        assert i != -1, "the entry-point checklist line for Unverified is missing"
        end = flat.find("- The resolved input inventory", i)
        assert end != -1, "the bullet after the Unverified checklist line is missing"
        checklist = flat[i:end]

        # The dedicated section rule
        j = flat.find("If there are no HOLDs")
        assert j != -1, "the no-HOLDs rule is missing"
        section = flat[j : j + 600]

        # "omit" may appear in the justification ("an omitted section is
        # ambiguous"); what must not appear is an instruction to omit.
        assert not re.search(r"omit it|omit the section", checklist, re.IGNORECASE), (
            "the checklist still instructs the writer to omit the section when empty, "
            "contradicting the section rule that says to print it with `none`"
        )
        assert "always print" in checklist.lower(), "the checklist does not say to always print it"
        assert "`none`" in checklist
        assert "`none`" in section
