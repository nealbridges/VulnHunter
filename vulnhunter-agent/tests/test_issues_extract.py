"""Tests for issues_extract: Haiku response parsing, file discovery, key computation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agent import _llm
from agent import issues_extract as extract_mod
from agent.issues_extract import (
    SOURCE_CANDIDATES,
    SOURCE_README,
    _compute_vulnfix_key,
    _discover_finding_files,
    _scan_date_from_dir,
    candidate_writeup_paths,
    extract_findings,
    load_report_material,
)

from tests._helpers import FakeTokenManager as _TM


@pytest.fixture
def fake_results_dir(tmp_path: Path) -> Path:
    """Build a results directory with README + poc + exploit_tests."""
    results = tmp_path / "myrepo_VULNHUNT_RESULTS_opus47_2026-06-23-141824"
    results.mkdir()
    (results / "README.md").write_text("# Report\n\nFindings: see summary table.\n")
    poc = results / "poc"
    poc.mkdir()
    (poc / "VULN-001_demo.py").write_text("# poc")
    tests = results / "exploit_tests"
    tests.mkdir()
    (tests / "test_vuln_001.py").write_text("# test")
    return results


def _stub_llm(monkeypatch: pytest.MonkeyPatch, response: dict | Exception) -> None:
    async def fake(**kwargs: Any) -> Any:
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(extract_mod._llm, "call_json_with_fallback", fake)


class TestComputeVulnfixKey:
    def test_stable(self) -> None:
        a = _compute_vulnfix_key("src/x.py:1", "CWE-89", "rc")
        b = _compute_vulnfix_key("src/x.py:1", "CWE-89", "rc")
        assert a == b
        assert len(a) == 16

    def test_changes_with_input(self) -> None:
        a = _compute_vulnfix_key("src/x.py:1", "CWE-89", "rc")
        b = _compute_vulnfix_key("src/x.py:2", "CWE-89", "rc")
        assert a != b


class TestScanDateFromDir:
    def test_extracts_date(self) -> None:
        assert _scan_date_from_dir("repo_VULNHUNT_RESULTS_opus47_2026-06-23-141824") == "2026-06-23"

    def test_falls_back_to_today(self) -> None:
        out = _scan_date_from_dir("no-timestamp")
        assert len(out) == 10  # YYYY-MM-DD


class TestDiscoverFiles:
    def test_finds_poc_and_test(self, fake_results_dir: Path) -> None:
        files = _discover_finding_files(fake_results_dir)
        # Files are normalized to the canonical zero-padded VULN-NNN form
        # regardless of the source filename (VULN-1 vs VULN-001 vs vuln_1).
        assert "VULN-001" in files
        sample = files["VULN-001"]
        assert "poc" in sample
        assert "exploit_test" in sample


class TestCandidateWriteups:
    def test_collects_sg_results_candidates_and_toplevel(self, tmp_path: Path) -> None:
        results = tmp_path / "scan"
        (results / "results").mkdir(parents=True)
        (results / "candidates").mkdir()
        sg = results / "results" / "sg-1_inj_results.md"
        extra = results / "results" / "notes.md"
        cand = results / "candidates" / "sg-1_entrypoint.md"
        top = results / "sg-9_log_results.md"
        readme = results / "README.md"
        empty = results / "results" / "empty.md"
        for path, body in (
            (sg, "sg"),
            (extra, "extra"),
            (cand, "cand"),
            (top, "top"),
            (readme, "readme must be skipped"),
            (empty, ""),
        ):
            path.write_text(body)
        paths = candidate_writeup_paths(results)
        names = [p.name for p in paths]
        assert names == [
            "sg-1_inj_results.md",
            "empty.md",
            "notes.md",
            "sg-1_entrypoint.md",
            "sg-9_log_results.md",
        ]
        assert readme not in paths

    def test_dedupes_overlapping_globs(self, tmp_path: Path) -> None:
        results = tmp_path / "scan"
        (results / "results").mkdir(parents=True)
        sg = results / "results" / "sg-1_inj_results.md"
        sg.write_text("one")
        paths = candidate_writeup_paths(results)
        assert paths == [sg]

    def test_load_report_material_prefers_readme(self, tmp_path: Path) -> None:
        results = tmp_path / "scan"
        (results / "results").mkdir(parents=True)
        (results / "README.md").write_text("# Confirmed report\n")
        (results / "results" / "sg-1_inj_results.md").write_text("candidate")
        text, source = load_report_material(results)
        assert source == SOURCE_README
        assert "Confirmed report" in text

    def test_load_report_material_concatenates_candidates(self, tmp_path: Path) -> None:
        results = tmp_path / "scan"
        (results / "results").mkdir(parents=True)
        (results / "results" / "sg-1_inj_results.md").write_text("INJ write-up")
        (results / "results" / "sg-2_nav_results.md").write_text("NAV write-up")
        text, source = load_report_material(results)
        assert source == SOURCE_CANDIDATES
        assert "BEGIN results/sg-1_inj_results.md" in text
        assert "INJ write-up" in text
        assert "NAV write-up" in text

    def test_load_report_material_raises_when_nothing_usable(self, tmp_path: Path) -> None:
        results = tmp_path / "scan"
        results.mkdir()
        (results / "README.md").write_text(" \n")
        with pytest.raises(FileNotFoundError, match="no Phase 2 candidate"):
            load_report_material(results)


class TestExtractFindings:
    async def test_happy_path(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_llm(
            monkeypatch,
            {
                "findings": [
                    {
                        "id": "VULN-001",
                        "title": "SQL injection",
                        "cwe": "CWE-89",
                        "cwe_name": "SQLi",
                        "severity": "High",
                        "location": "src/db.py:42",
                        "root_cause": "unparameterized",
                        "data_flow": "body→query",
                        "entry_point": "POST /users",
                        "exploit_description": "read all rows",
                        "exploit_impact": "data disclosure",
                        "fix_strategy": "parameterize",
                        "severity_rationale": "PII disclosure",
                    }
                ]
            },
        )

        report = await extract_findings(fake_results_dir, populated_agent_config, _TM())
        assert len(report.findings) == 1
        f = report.findings[0]
        assert f.id == "VULN-001"
        assert f.cwe == "CWE-89"
        assert f.poc_path is not None  # discovered from filesystem
        assert f.exploit_test_path is not None
        assert len(f.vulnfix_key) == 16

    async def test_skips_findings_without_id(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_llm(
            monkeypatch,
            {"findings": [{"id": "", "title": "no id", "cwe": "CWE-1"}]},
        )

        report = await extract_findings(fake_results_dir, populated_agent_config, _TM())
        assert report.findings == []

    async def test_missing_findings_list_raises(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _stub_llm(monkeypatch, {"not_findings": []})

        with pytest.raises(_llm.LLMError, match="findings"):
            await extract_findings(fake_results_dir, populated_agent_config, _TM())

    async def test_missing_readme_raises(
        self,
        tmp_path: Path,
        populated_agent_config: Any,
    ) -> None:
        empty = tmp_path / "no_readme_dir"
        empty.mkdir()

        with pytest.raises(FileNotFoundError, match="no Phase 2 candidate"):
            await extract_findings(empty, populated_agent_config, _TM())

    async def test_extracts_from_phase2_candidates_when_readme_missing(
        self,
        tmp_path: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        results = tmp_path / "myrepo_VULNHUNT_RESULTS_2026-06-23-141824"
        (results / "results").mkdir(parents=True)
        (results / "results" / "sg-1_inj_results.md").write_text(
            "#### [VULN-001] SQL injection in login\n"
            "- **Class**: CWE-89: SQL Injection\n"
            "- **Location**: src/db.py:42\n"
            "- **Root Cause**: unparameterized query\n"
        )
        poc = results / "poc"
        poc.mkdir()
        (poc / "VULN-001_demo.py").write_text("# poc")
        captured: dict[str, Any] = {}

        async def fake(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return {
                "findings": [
                    {
                        "id": "VULN-001",
                        "title": "SQL injection in login",
                        "cwe": "CWE-89",
                        "cwe_name": "SQLi",
                        "severity": "High",
                        "location": "src/db.py:42",
                        "root_cause": "unparameterized",
                        "data_flow": "body→query",
                        "entry_point": "POST /login",
                        "exploit_description": "read all rows",
                        "exploit_impact": "data disclosure",
                        "fix_strategy": "",
                        "severity_rationale": "PII disclosure",
                    }
                ]
            }

        monkeypatch.setattr(extract_mod._llm, "call_json_with_fallback", fake)
        report = await extract_findings(results, populated_agent_config, _TM())
        assert report.source == SOURCE_CANDIDATES
        assert len(report.findings) == 1
        assert report.findings[0].id == "VULN-001"
        assert report.findings[0].poc_path is not None
        assert "Phase 2" in captured["system"]
        assert "sg-1_inj_results.md" in captured["user"]
        assert "SQL injection in login" in captured["user"]

    async def test_readme_wins_when_candidates_also_exist(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        results_sub = fake_results_dir / "results"
        results_sub.mkdir()
        (results_sub / "sg-1_inj_results.md").write_text("#### [VULN-009] should not be used\n")
        captured: dict[str, Any] = {}

        async def fake(**kwargs: Any) -> Any:
            captured.update(kwargs)
            return {"findings": []}

        monkeypatch.setattr(extract_mod._llm, "call_json_with_fallback", fake)
        report = await extract_findings(fake_results_dir, populated_agent_config, _TM())
        assert report.source == SOURCE_README
        assert "Confirmed finding" in captured["user"]
        assert "should not be used" not in captured["user"]
        assert "Candidate Output Format" not in captured["system"]

    async def test_empty_readme_falls_back_to_candidates(
        self,
        tmp_path: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        results = tmp_path / "empty_readme_dir"
        results.mkdir()
        (results / "README.md").write_text("   \n")
        (results / "candidates").mkdir()
        (results / "candidates" / "sg-2_nav.md").write_text(
            "#### [VULN-002] IDOR on allocations\n- **Location**: routes.js:16\n"
        )
        _stub_llm(monkeypatch, {"findings": []})
        report = await extract_findings(results, populated_agent_config, _TM())
        assert report.source == SOURCE_CANDIDATES


class _FakeAudit:
    """Captures emit_audit records for assertions."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def emit_audit(self, record: dict) -> None:
        self.records.append(record)

    def emit_finding(self, record: dict) -> None:  # pragma: no cover
        pass


class TestModelFallbackAudit:
    async def test_scan_model_hop_emits_model_fallback(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # haiku+sonnet exhausted -> escalate to scan-session model, which succeeds.
        async def fb(**_k: Any) -> Any:
            raise _llm.LLMError("haiku+sonnet down")

        async def cj(**_k: Any) -> Any:
            return {"findings": []}

        monkeypatch.setattr(extract_mod._llm, "call_json_with_fallback", fb)
        monkeypatch.setattr(extract_mod._llm, "call_json", cj)
        aw = _FakeAudit()
        await extract_findings(fake_results_dir, populated_agent_config, _TM(), audit_writer=aw)
        fbk = [r for r in aw.records if r["event_type"] == "model_fallback"]
        assert len(fbk) == 1
        assert fbk[0]["from_model"] == populated_agent_config.issues.sonnet_model
        assert fbk[0]["to_model"] == populated_agent_config.anthropic.model
        assert fbk[0]["stage"] == "extract"

    async def test_all_tiers_exhausted_emits_model_unavailable_and_raises(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Every tier fails -> emit model_unavailable, then propagate the error.
        async def fb(**_k: Any) -> Any:
            raise _llm.LLMError("haiku+sonnet down")

        async def cj(**_k: Any) -> Any:
            raise _llm.LLMError("scan-model down")

        monkeypatch.setattr(extract_mod._llm, "call_json_with_fallback", fb)
        monkeypatch.setattr(extract_mod._llm, "call_json", cj)
        aw = _FakeAudit()
        with pytest.raises(_llm.LLMError):
            await extract_findings(fake_results_dir, populated_agent_config, _TM(), audit_writer=aw)
        un = [r for r in aw.records if r["event_type"] == "model_unavailable"]
        assert len(un) == 1
        assert un[0]["from_model"] == populated_agent_config.anthropic.model

    async def test_no_event_when_primary_succeeds(
        self,
        fake_results_dir: Path,
        populated_agent_config: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def ok(**_k: Any) -> Any:
            return {"findings": []}

        monkeypatch.setattr(extract_mod._llm, "call_json_with_fallback", ok)
        aw = _FakeAudit()
        await extract_findings(fake_results_dir, populated_agent_config, _TM(), audit_writer=aw)
        assert aw.records == []
