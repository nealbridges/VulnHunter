"""Breadth-gate wiring contract: the prose names the commands and outcomes.

Presence only. Whether a model follows the prose is settled by scan runs.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HUNT_SKILL = REPO_ROOT / "vulnhunt" / "SKILL.md"
PHASE1 = REPO_ROOT / "vulnhunt" / "phases" / "phase1_recon.md"
PHASE2 = REPO_ROOT / "vulnhunt" / "phases" / "phase2_hunt.md"
PHASE4 = REPO_ROOT / "vulnhunt" / "phases" / "phase4_report.md"
RUN_SKILL = REPO_ROOT / "vulnhunter-run" / "SKILL.md"

STOPPED = "# VulnHunter scan STOPPED: breadth gate failed"


def _read(path: Path) -> str:
    assert path.is_file(), f"missing {path}"
    return path.read_text(encoding="utf-8")


def _step(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def test_step_2a_names_gate_commands_and_outcomes() -> None:
    step = _step(_read(HUNT_SKILL), "A. Phase 1 - Recon", "B. Phase 2 - Hunt")
    assert "vh scaffold-inputs" in step
    assert "vh check-phase 1" in step
    assert re.search(r"re-dispatch\s+it once", step)
    assert "second exit 1 stops the scan" in step
    assert "recon must not rewrite it" in step
    assert "exit 2: NOT RUN" in step
    assert "# VulnHunter scan STOPPED: phase <n> gate failed" in step
    for status in ("PASS", "FAIL (<rules>)", "NOT RUN (<reason>)", "NOT ENFORCED (<reason>)"):
        assert status in step


def test_phase1_recon_states_scaffold_start_and_variable_rule() -> None:
    text = _read(PHASE1)
    assert "inputs_scaffold.md" in text
    assert "exactly one backticked name" in text
    assert "Sibling input rule" in text
    assert "completeness check below" in text
    assert re.search(r"^#### Input Inventory$", text, re.MULTILINE) is not None


def test_phase4_report_has_gate_fields() -> None:
    text = _read(PHASE4)
    assert "**Inputs**: scaffold <N> / inventoried <M>" in text
    assert "**Breadth gate**: <status>" in text
    assert "**Report gate**: <status>" in text


def test_each_gated_step_names_its_command() -> None:
    text = _read(HUNT_SKILL)
    assert "vh check-phase 2 " in _step(text, "B. Phase 2 - Hunt", "C. Phase 2b - Verify")
    assert "vh check-phase 2b " in _step(text, "C. Phase 2b - Verify", "D. Phase 3a+3b+3c")
    assert "vh check-phase 3 " in _step(text, "D. Phase 3a+3b+3c", "E. Phase 3d - Sweep")
    assert "vh check-phase 3 " in _step(text, "E. Phase 3d - Sweep", "3. **Write report**")
    assert "vh check-phase 4 " in _step(text, "3. **Write report**", "### What the report contains")


def test_outcome_rule_stated_once() -> None:
    text = _read(HUNT_SKILL)
    assert text.count("**Gate outcome rule (all phases).**") == 1
    step_a = _step(text, "A. Phase 1 - Recon", "B. Phase 2 - Hunt")
    assert "re-dispatch" in step_a and "second exit 1 stops the scan" in step_a
    assert "# VulnHunter scan STOPPED: phase <n> gate failed" in step_a
    for start, end in (
        ("B. Phase 2 - Hunt", "C. Phase 2b - Verify"),
        ("C. Phase 2b - Verify", "D. Phase 3a+3b+3c"),
        ("D. Phase 3a+3b+3c", "E. Phase 3d - Sweep"),
        ("E. Phase 3d - Sweep", "3. **Write report**"),
        ("3. **Write report**", "### What the report contains"),
    ):
        assert "apply the gate outcome rule from step 2.A" in _step(text, start, end)


def test_phase2_states_disposition_line_format() -> None:
    text = _read(PHASE2)
    assert "starting with the verdict word and `(input #N`" in text
    assert "CANDIDATE (input #12" in text


def test_run_skill_marks_stopped_scan() -> None:
    text = _read(RUN_SKILL)
    assert "# VulnHunter scan STOPPED" in text
    assert "--exit-code 1" in text
