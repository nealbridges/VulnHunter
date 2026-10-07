"""Regression tests for vh.cli write-manifest (GitHub-reported bugs).

Covers the report that ``--exit-code N`` was ignored: ``_manifest_body``
overwrote the caller-supplied exit code with a README-derived one, and
``findings`` was hardcoded to ``[]`` regardless of input.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vh import cli


@pytest.fixture()
def results_dir(tmp_path: Path) -> Path:
    d = tmp_path / "repo_VULNHUNT_RESULTS_test"
    d.mkdir()
    return d


def _read_manifest(results: Path) -> dict:
    loaded: dict = json.loads((results / "scan_manifest.json").read_text())
    return loaded


def _run(results: Path, *extra: str) -> int:
    return cli.main(["write-manifest", str(results), *extra])


# --- --exit-code is honored -------------------------------------------------


def test_explicit_exit_code_zero_wins(results_dir: Path) -> None:
    assert _run(results_dir, "--exit-code", "0") == 0
    body = _read_manifest(results_dir)
    assert body["agent_exit_code"] == 0


def test_explicit_exit_code_one_wins_without_readme(results_dir: Path) -> None:
    # No README at all: the old code forced 1 anyway, so this alone does not
    # prove the flag works. Its value is paired with the next test.
    assert _run(results_dir, "--exit-code", "1") == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 1


def test_explicit_exit_code_beats_nonempty_readme(results_dir: Path) -> None:
    # The core regression: a non-empty README used to force exit code 0 and
    # silently discard the operator-provided value.
    (results_dir / "README.md").write_text("# findings live here\n")
    assert _run(results_dir, "--exit-code", "3") == 0
    body = _read_manifest(results_dir)
    assert body["agent_exit_code"] == 3


def test_explicit_exit_code_zero_with_empty_readme(results_dir: Path) -> None:
    (results_dir / "README.md").write_text("")
    assert _run(results_dir, "--exit-code", "0") == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 0


def test_out_of_range_exit_code_clamps_to_one(results_dir: Path) -> None:
    assert _run(results_dir, "--exit-code", "9") == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 1


def test_negative_exit_code_clamps_to_one(results_dir: Path) -> None:
    assert _run(results_dir, "--exit-code", "-2") == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 1


# --- omitted flag keeps the README-derived behavior --------------------------


def test_omitted_flag_nonempty_readme_derives_zero(results_dir: Path) -> None:
    (results_dir / "README.md").write_text("report body\n")
    assert _run(results_dir) == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 0


def test_omitted_flag_no_readme_derives_one(results_dir: Path) -> None:
    assert _run(results_dir) == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 1


def test_omitted_flag_empty_readme_derives_one(results_dir: Path) -> None:
    (results_dir / "README.md").write_text("")
    assert _run(results_dir) == 0
    assert _read_manifest(results_dir)["agent_exit_code"] == 1


# --- schema shape is preserved ----------------------------------------------


def test_manifest_schema_fields_present(results_dir: Path) -> None:
    assert _run(results_dir, "--exit-code", "2") == 0
    body = _read_manifest(results_dir)
    for key in (
        "schema_version",
        "scan_id",
        "agent_exit_code",
        "cost_usd",
        "findings",
        "posted",
        "skipped",
        "failed",
    ):
        assert key in body
    assert body["schema_version"] == "1"
    assert body["scan_id"] == results_dir.name
    assert body["cost_usd"] == 0


def test_findings_is_list(results_dir: Path) -> None:
    # The stub writer never populates findings (the agent-side writer does),
    # but the key must remain a list so the shared schema still validates.
    assert _run(results_dir, "--exit-code", "0") == 0
    assert _read_manifest(results_dir)["findings"] == []


def test_bad_results_dir_name_rejected(tmp_path: Path) -> None:
    d = tmp_path / "not-a-results-dir"
    d.mkdir()
    assert cli.main(["write-manifest", str(d), "--exit-code", "0"]) == 2
    assert not (d / "scan_manifest.json").exists()


# --- _manifest_body direct unit checks ---------------------------------------


def test_manifest_body_explicit_none_derives(results_dir: Path) -> None:
    body = cli._manifest_body(results_dir, None)
    assert body["agent_exit_code"] == 1  # no README


def test_manifest_body_explicit_value_preserved(results_dir: Path) -> None:
    assert cli._manifest_body(results_dir, 4)["agent_exit_code"] == 4
