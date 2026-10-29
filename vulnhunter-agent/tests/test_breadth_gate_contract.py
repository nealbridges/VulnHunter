"""Breadth-gate wiring contract: the prose names the commands and outcomes.

Presence only. Whether a model follows the prose is settled by scan runs.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HUNT_SKILL = REPO_ROOT / "vulnhunt" / "SKILL.md"
PHASE1 = REPO_ROOT / "vulnhunt" / "phases" / "phase1_recon.md"
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
    assert "re-dispatch it once" in step
    assert "second exit 1 stops the scan" in step
    assert "recon must not rewrite it" in step
    assert "exit 2: NOT RUN" in step
    assert STOPPED in step
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


def test_run_skill_marks_stopped_scan() -> None:
    text = _read(RUN_SKILL)
    assert "# VulnHunter scan STOPPED" in text
    assert "--exit-code 1" in text
