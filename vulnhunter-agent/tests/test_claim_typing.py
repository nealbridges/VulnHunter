"""Claim typing, executed probes, and the canonical HOLD-UNVERIFIED.

The skill text is the implementation, so these are contract tests: each one
asserts that a rule the pipeline depends on is stated at the site that needs it.
They check presence, not wording, so the prose can be edited freely as long as
the rule survives. Whether a model *follows* the rules is settled by real scan
runs, not by pytest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASES = REPO_ROOT / "vulnhunt" / "phases"
SKILL_DOC = REPO_ROOT / "vulnhunt" / "SKILL.md"
PROVISIONER = REPO_ROOT / "skills" / "runtime-provisioner" / "SKILL.md"
FIXTURE = REPO_ROOT / "vulnhunter-agent" / "tests" / "fixtures" / "phase2b_elimination_rows.md"

HOLD = "HOLD-UNVERIFIED"
CLAIM_FIELDS = ("Closing claim", "Claim type", "Evidence", "Path reasoned about")
CLOSING_EVIDENCE = {"executed-probe", "runtime-test"}


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _phase(name: str) -> str:
    return _read(PHASES / name)


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.DOTALL) is not None


def _table_header(text: str, first_cell: str) -> list[str]:
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == first_cell:
            return cells
    raise AssertionError(f"no table whose first header cell is {first_cell!r}")


def _table_rows(text: str, first_cell: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    header = _table_header(text, first_cell)
    start = next(
        i for i, ln in enumerate(lines) if ln.strip().strip("|").split("|")[0].strip() == first_cell
    )
    rows = []
    for line in lines[start + 2 :]:
        if not line.strip().startswith("|"):
            break
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(dict(zip(header, cells, strict=True)))
    return rows


# --- Invariant 1: every 2b verdict carries the four claim fields ---------------


def test_phase2b_table_has_claim_columns() -> None:
    header = _table_header(_phase("phase2b_verify.md"), "Finding")
    for field in CLAIM_FIELDS:
        assert field in header, f"Phase 2b verdict table lacks {field!r}"


def test_phase2b_example_rows_fill_claim_fields() -> None:
    for row in _table_rows(_phase("phase2b_verify.md"), "Finding"):
        for field in CLAIM_FIELDS:
            assert row[field] not in ("", "N/A"), f"{row['Finding']}: empty {field!r}"


# --- Invariant 2: behavioural claims need execution; existing-test is intent ---


def test_execution_rule_present() -> None:
    text = _phase("phase2b_verify.md")
    assert _has(
        text, r"behavioural.{0,40}claim is closed only by `executed-probe` or `runtime-test`"
    )
    assert _has(text, r"both directions"), "execution rule must cover eliminations and promotions"


def test_existing_test_rule_present() -> None:
    text = _phase("phase2b_verify.md")
    assert _has(text, r"built string.{0,40}mock return.{0,80}`existing-test`.{0,40}intent")


def test_reimplementation_is_not_a_probe() -> None:
    assert _has(_read(PROVISIONER), r"reimplementation.{0,40}not a probe")


# --- Invariant 3: one definition, distinct from INCONCLUSIVE and Code Smell -----


def test_hold_defined_once_in_skill_doc() -> None:
    shipped = list((REPO_ROOT / "vulnhunt").rglob("*.md")) + [PROVISIONER]
    defining = [p for p in shipped if f"**{HOLD}** —" in _read(p)]
    assert defining == [SKILL_DOC], f"{HOLD} must be defined only in SKILL.md, found {defining}"


def test_hold_not_a_synonym() -> None:
    text = _read(SKILL_DOC)
    assert "INCONCLUSIVE" in text and _has(text, r"not.{0,80}Code Smell")


def test_structural_and_behavioural_defined() -> None:
    text = _read(SKILL_DOC)
    assert _has(text, r"\*\*structural\*\*.{0,200}re-reading the source")
    assert _has(text, r"\*\*behavioural\*\*.{0,200}executing it")


# --- Invariant 4: a HOLD survives every gate it passes through -----------------

HOLD_SITES = {
    "phase2_hunt.md": r"HOLD-UNVERIFIED\*\* \(input #",
    "phase2_shared.md": r"HOLD-UNVERIFIED\*\* \(input #",
    "phase2_class_inj.md": r"record \*\*HOLD-UNVERIFIED\*\*",
    "phase2b_verify.md": r"HOLD-UNVERIFIED entries from Phase 2 are candidates too",
    "phase3a_build_poc.md": r"HOLD-UNVERIFIED intake",
    "phase3d_sweep.md": r"\*\*HOLD-UNVERIFIED\*\* \(with the probe",
    "phase4_report.md": r"## The Unverified section",
}


@pytest.mark.parametrize("site", sorted(HOLD_SITES))
def test_hold_in_every_disposition_site(site: str) -> None:
    assert _has(_phase(site), HOLD_SITES[site]), f"{site} no longer carries HOLD"


def test_aggregation_precedence() -> None:
    text = _phase("phase2_hunt.md")
    assert _has(text, r"HOLD\s+beats SAFE") and _has(text, r"CANDIDATE beats HOLD")


def test_hold_is_terminal_at_trace_gate() -> None:
    assert _has(_phase("phase2_shared.md"), r"unless you recorded HOLD-UNVERIFIED.{0,40}terminal")


def test_sweep_has_held_column() -> None:
    assert "Held" in _table_header(_phase("phase3d_sweep.md"), "Root Cause")


def test_inventory_lists_hold_disposition() -> None:
    assert _has(_phase("phase4_report.md"), r"CANDIDATE / SAFE / DESIGN-INTENT / HOLD-UNVERIFIED")


def test_orchestrator_counts_and_stopping_rule() -> None:
    text = _read(SKILL_DOC)
    assert "Candidates = confirmed findings + eliminated/downgraded to Code Smell + Held" in text
    assert _has(text, r"Zero CONFIRMED is not zero findings")
    assert _has(text, r"HOLD-UNVERIFIED items are reported, not dropped")


# --- Invariant 5: routing by severity; Unverified section always printed ------


def test_hold_routing_by_severity() -> None:
    text = _phase("phase2b_verify.md")
    assert _has(text, r"Medium\+ potential.{0,10}→ Phase 3a")
    assert _has(text, r"Low potential.{0,10}→ the report's Unverified section")


def test_unverified_section_crosscheck_and_none_body() -> None:
    text = _phase("phase4_report.md")
    assert _has(text, r"Cross-check before writing")
    assert _has(text, r"`## Unverified` followed by `none`")


# --- Invariant 6: probe ladder before the container preference ----------------


def test_probe_ladder_precedes_container_preference() -> None:
    text = _read(PROVISIONER)
    ladder = text.find("Probe ladder")
    container = text.find("**Docker container**")
    assert -1 < ladder < container, "probe ladder must come before the sandbox preference"


# --- Invariant 7: structural eliminations are not forced to HOLD ---------------


def test_structural_elimination_allowed() -> None:
    assert _has(
        _phase("phase2b_verify.md"), r"structural.{0,10}claim may close on\s+`static-trace` alone"
    )


# --- Replay on the invented fixture --------------------------------------------


def _expected_verdict(claim_type: str, evidence: str) -> str:
    """The execution rule as stated in Phase 2b (asserted present above)."""
    if claim_type == "behavioural" and evidence not in CLOSING_EVIDENCE:
        return HOLD
    return "as recorded"


def test_fixture_rows_carry_claim_fields() -> None:
    for row in _table_rows(_read(FIXTURE), "Finding"):
        assert row["Claim type"] in ("structural", "behavioural")
        assert row["Evidence"] in CLOSING_EVIDENCE | {"static-trace", "existing-test"}


def test_fixture_behavioural_eliminations_replay_to_hold() -> None:
    fixture = _read(FIXTURE)
    expected = {r["Row"]: r["Expected verdict"] for r in _table_rows(fixture, "Row")}
    for row in _table_rows(fixture, "Finding"):
        assert row["Verdict"] == "FALSE POSITIVE", "fixture rows record the wrong verdict"
        finding_id = row["Finding"].split()[0]
        verdict = _expected_verdict(row["Claim type"], row["Evidence"])
        assert verdict == HOLD == expected[finding_id], f"{finding_id} should replay to HOLD"


# --- Shipped prose carries no run history ---------------------------------------


def test_no_run_history_in_shipped_prose() -> None:
    shipped = list((REPO_ROOT / "vulnhunt").rglob("*.md")) + [PROVISIONER]
    for path in shipped:
        assert not _has(_read(path), r"field run"), f"{path.name} narrates a past run"
