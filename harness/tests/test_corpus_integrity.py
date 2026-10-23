"""Integrity checks for the shipped benchmark corpus and its validator.

Runs with no network, no model, and no cloning.
"""

import json
import os

import local_harness.benchmark.run as run

GROUND_TRUTH_DIR = os.path.join(
    os.path.dirname(__file__), "..", "local_harness", "benchmark", "ground_truth"
)


def _load_corpus():
    """Load all *.json files from ground_truth/ the same way the runner does."""
    results = []
    for name in sorted(os.listdir(GROUND_TRUTH_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(GROUND_TRUTH_DIR, name)
        with open(path) as f:
            results.append((name, json.load(f)))
    return results


def test_shipped_corpus_passes_validator():
    benchmarks = _load_corpus()
    assert benchmarks, "No corpus files found in ground_truth/"
    names = [name for name, _ in benchmarks]
    assert "EXAMPLE.json" not in names
    assert "juice-shop.json" in names
    assert "WebGoat.json" in names
    assert "NodeGoat.json" in names
    assert run.validate_benchmarks(benchmarks) == []


def test_template_is_not_a_json_corpus_file():
    assert os.path.isfile(os.path.join(GROUND_TRUTH_DIR, "EXAMPLE.json.template"))
    assert not os.path.isfile(os.path.join(GROUND_TRUTH_DIR, "EXAMPLE.json"))


def test_finding_ids_globally_unique():
    seen = {}
    duplicates = []
    for filename, findings in _load_corpus():
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            fid = finding.get("finding_id")
            if fid is None:
                continue
            if fid in seen:
                duplicates.append(f"{fid} appears in both {seen[fid]} and {filename}")
            else:
                seen[fid] = filename
    assert duplicates == [], "Duplicate finding IDs:\n" + "\n".join(duplicates)
    assert len(seen) == 6


def test_validate_rejects_non_dict_entry():
    errors = run.validate_benchmarks([("bad.json", ["not-a-dict"])])
    assert any("JSON object" in e for e in errors)


def test_validate_rejects_non_list_file():
    errors = run.validate_benchmarks([("bad.json", {"finding_id": "X"})])
    assert any("JSON array" in e for e in errors)


def test_validate_rejects_missing_fields():
    errors = run.validate_benchmarks([("bad.json", [{"finding_id": "X", "type": "SQLi"}])])
    assert any("missing required fields" in e for e in errors)
    assert any("source_code" in e and "description" in e for e in errors)


def test_validate_rejects_blank_fields():
    errors = run.validate_benchmarks(
        [
            (
                "bad.json",
                [
                    {
                        "finding_id": "  ",
                        "type": "SQLi",
                        "description": "x",
                        "source_code": "https://github.com/a/b/tree/abcdef1",
                    }
                ],
            )
        ]
    )
    assert any("missing required fields" in e for e in errors)


def test_validate_rejects_blob_url():
    errors = run.validate_benchmarks(
        [
            (
                "bad.json",
                [
                    {
                        "finding_id": "X-001",
                        "type": "SQLi",
                        "description": "test",
                        "source_code": "https://github.com/org/repo/blob/abc123/file.py",
                    }
                ],
            )
        ]
    )
    assert any("source_code" in e for e in errors)


def test_validate_rejects_short_commit():
    errors = run.validate_benchmarks(
        [
            (
                "bad.json",
                [
                    {
                        "finding_id": "X-001",
                        "type": "SQLi",
                        "description": "test",
                        "source_code": "https://github.com/org/repo/tree/abc",
                    }
                ],
            )
        ]
    )
    assert any("source_code" in e for e in errors)


def test_validate_rejects_duplicate_ids_across_files():
    finding = {
        "finding_id": "SHARED-001",
        "type": "SQLi",
        "description": "test",
        "source_code": "https://github.com/org/repo/tree/abcdef1234567",
    }
    errors = run.validate_benchmarks([("a.json", [finding]), ("b.json", [dict(finding)])])
    assert any("duplicate finding_id 'SHARED-001'" in e for e in errors)


def test_validate_accepts_trailing_slash_on_tree_url():
    errors = run.validate_benchmarks(
        [
            (
                "ok.json",
                [
                    {
                        "finding_id": "OK-001",
                        "type": "SQLi",
                        "description": "test",
                        "source_code": "https://github.com/org/repo/tree/abcdef1234567/",
                    }
                ],
            )
        ]
    )
    assert errors == []
