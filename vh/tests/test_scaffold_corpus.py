"""Public acceptance: the JS/TS pack against two pinned OWASP apps.

Skipped unless VH_CORPUS_DIR points at checkouts of the pinned commits. The
test does not fetch; see plan §6 for the one-time checkout commands.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from vh.scaffold import PACKS, scan_repo

pytestmark = pytest.mark.integration

PINS = {
    "NodeGoat": "c5cb68a7084e4ae7dcc60e6a98768720a81841e8",
    "juice-shop": "a520e158cb65c43d24e2c55d84f09b05a2511a03",
    "WebGoat": "5142935bf7c279882c3b0fc0ecec42c447de6fd5",
}
FLOORS = {"NodeGoat": 25, "juice-shop": 182, "WebGoat": 228}
ANCHORS = [
    ("NodeGoat", "path param", "app/routes/allocations.js", 17, "userId"),
    ("NodeGoat", "query param", "app/routes/allocations.js", 20, "threshold"),
    ("juice-shop", "body field", "routes/login.ts", 34, "email"),
    (
        "juice-shop",
        "client query param",
        "frontend/src/app/search-result/search-result.component.ts",
        136,
        "q",
    ),
    (
        "WebGoat",
        "query param",
        "src/main/java/org/owasp/webgoat/lessons/pathtraversal/ProfileUpload.java",
        41,
        "fullName",
    ),
]


def _corpus() -> Path:
    raw = os.environ.get("VH_CORPUS_DIR")
    if not raw:
        pytest.skip("VH_CORPUS_DIR is not set")
    return Path(raw)


def _checkout(name: str) -> Path:
    root = _corpus() / name
    head = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if head.returncode != 0 or head.stdout.strip() != PINS[name]:
        pytest.skip(f"{name} is not at {PINS[name]}")
    return root


def test_scaffold_rows_meet_floor() -> None:
    for name, floor in FLOORS.items():
        result = scan_repo(_checkout(name), PACKS)
        assert len(result.rows) >= floor, f"{name}: {len(result.rows)} rows < floor {floor}"


@pytest.mark.parametrize(("app", "source_type", "file", "line", "variable"), ANCHORS)
def test_public_anchor_present(
    app: str, source_type: str, file: str, line: int, variable: str
) -> None:
    result = scan_repo(_checkout(app), PACKS)
    hits = [
        row
        for row in result.rows
        if row.file == file
        and row.variable == variable
        and row.source_type == source_type
        and abs(row.line - line) <= 3
    ]
    assert hits, f"{app}: no {source_type} {variable} at {file}:{line}"
