"""Fail-closed breadth gate for phase 1 (plan §3.4, D2-D10).

Read-only: it parses `phase1_output.md` and the scaffold file, prints findings
and returns an exit code. It never writes.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_SEPARATOR = re.compile(r"^:?-{3,}:?$")
_BACKTICK = re.compile(r"^`([^`]*)`$")
_PACKS = re.compile(r"^Packs:\s*(.*)$")


@dataclass
class Finding:
    rule: str
    severity: str
    file: str
    line: int
    message: str
    fix: str

    def line_text(self) -> str:
        label = "FAIL" if self.severity == "fail" else "WARN"
        return f"{label} {self.rule} {self.file}:{self.line} {self.message} | fix: {self.fix}"

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "fix": self.fix,
        }


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(_SEPARATOR.match(cell) for cell in cells)


def _tables(
    lines: list[str], start: int, end: int
) -> list[tuple[int, list[str], list[tuple[int, list[str]]]]]:
    found = []
    index = start
    while index < end - 1:
        if lines[index].strip().startswith("|") and _is_separator(lines[index + 1]):
            header = _cells(lines[index])
            rows = []
            row = index + 2
            while row < end and lines[row].strip().startswith("|"):
                rows.append((row + 1, _cells(lines[row])))
                row += 1
            found.append((index + 1, header, rows))
            index = row
        else:
            index += 1
    return found


def _inventory_bounds(lines: list[str]) -> tuple[int, int] | None:
    start = level = 0
    for index, line in enumerate(lines):
        heading = _HEADING.match(line)
        if heading and "input inventory" in heading.group(2).lower():
            start, level = index + 1, len(heading.group(1))
            break
    else:
        return None
    for index in range(start, len(lines)):
        heading = _HEADING.match(lines[index])
        if heading and len(heading.group(1)) <= level:
            return start, index
    return start, len(lines)


def _grouped(cell: str) -> bool:
    match = _BACKTICK.fullmatch(cell.strip())
    if not match:
        return True
    inner = match.group(1)
    return not inner or "," in inner or any(char.isspace() for char in inner)


def _scaffold(path: Path) -> tuple[str | None, int | None]:
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    packs = None
    for line in lines:
        match = _PACKS.match(line)
        if match:
            packs = match.group(1).strip()
            break
    rows = sum(len(table_rows) for _, _, table_rows in _tables(lines, 0, len(lines)))
    return packs, rows


_RULES: dict[str, tuple[str, str, str]] = {
    "P1-NO-OUTPUT": ("fail", "phase1_output.md is missing", "write phase1_output.md from recon"),
    "P1-NO-INVENTORY": ("fail", "no Input Inventory data rows", "add a numbered inventory table"),
    "P1-NO-SCAFFOLD": ("fail", "scaffold file is missing or unusable", "run `vh scaffold-inputs`"),
    "P1-FORMAT": (
        "fail",
        "table lacks a '#' or 'Variable' column",
        "add '#' and 'Variable' columns",
    ),
    "P1-GROUPED-ROW": (
        "fail",
        "Variable cell {cell!r} is not exactly one backticked name",
        "split into one row per variable; use `N/A` when none",
    ),
    "P1-THIN": (
        "fail",
        "inventory rows ({inventory}) < scaffold rows ({scaffold})",
        "add a row for every scaffold row not yet inventoried",
    ),
    "P1-EMPTY-SCAFFOLD": (
        "warn",
        "scaffold has 0 rows; thin check skipped",
        "confirm the repo has no extractable input sites",
    ),
    "P1-NO-PACK": (
        "warn",
        "no pack matched this repository; thin check skipped",
        "recon still enumerates inputs by hand",
    ),
}


def _emit(
    findings: list[Finding],
    rule: str,
    line: int = 0,
    file: str = "phase1_output.md",
    **values: object,
) -> None:
    severity, message, fix = _RULES[rule]
    findings.append(
        Finding(rule, severity, file, line, message.format(**values), fix.format(**values))
    )


def _inventory(lines: list[str], bounds: tuple[int, int]) -> tuple[list[Finding], int]:
    findings: list[Finding] = []
    data_rows = 0
    for header_line, header, rows in _tables(lines, bounds[0], bounds[1]):
        lower = [cell.lower() for cell in header]
        if "#" not in lower or "variable" not in lower:
            _emit(findings, "P1-FORMAT", header_line)
            continue
        number_cell, variable_cell = lower.index("#"), lower.index("variable")
        for line_number, cells in rows:
            if len(cells) <= max(number_cell, variable_cell):
                continue
            try:
                int(cells[number_cell])
            except ValueError:
                continue
            data_rows += 1
            cell = cells[variable_cell]
            if _grouped(cell):
                _emit(findings, "P1-GROUPED-ROW", line_number, cell=cell)
    return findings, data_rows


def check(results: Path, scaffold_path: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    output = results / "phase1_output.md"
    packs, scaffold_rows = _scaffold(scaffold_path)
    scaffold_file = scaffold_path.name
    inventory_rows: int | None = None
    skip_thin = False
    if not scaffold_path.is_file() or not packs:
        _emit(findings, "P1-NO-SCAFFOLD", file=scaffold_file)
        scaffold_rows = None
        skip_thin = True
    elif packs == "none":
        _emit(findings, "P1-NO-PACK", file=scaffold_file)
        skip_thin = True
    elif scaffold_rows == 0:
        _emit(findings, "P1-EMPTY-SCAFFOLD", file=scaffold_file)
        skip_thin = True

    if not output.is_file():
        _emit(findings, "P1-NO-OUTPUT")
    else:
        lines = output.read_text(encoding="utf-8", errors="replace").splitlines()
        bounds = _inventory_bounds(lines)
        if bounds is None:
            _emit(findings, "P1-NO-INVENTORY")
        else:
            table_findings, inventory_rows = _inventory(lines, bounds)
            findings.extend(table_findings)
            if inventory_rows == 0:
                _emit(findings, "P1-NO-INVENTORY")

    if (
        not skip_thin
        and scaffold_rows is not None
        and inventory_rows is not None
        and inventory_rows < scaffold_rows
    ):
        _emit(findings, "P1-THIN", inventory=inventory_rows, scaffold=scaffold_rows)

    passed = not any(f.severity == "fail" for f in findings)
    summary = {
        "phase": "1",
        "passed": passed,
        "scaffold_rows": scaffold_rows,
        "inventory_rows": inventory_rows,
        "violations": [f.as_dict() for f in findings],
    }
    return findings, summary


def run(phase: str, results: Path, scaffold: Path | None, as_json: bool) -> int:
    if phase != "1":
        print(f"phase {phase}: not implemented", file=sys.stderr)
        return 2
    if not results.is_dir():
        print(f"results dir not found: {results}", file=sys.stderr)
        return 2
    findings, summary = check(results, scaffold or results / "inputs_scaffold.md")
    if as_json:
        print(json.dumps(summary))
    else:
        for finding in findings:
            print(finding.line_text())
        scaffold_count = summary["scaffold_rows"] if summary["scaffold_rows"] is not None else "-"
        inventory_count = (
            summary["inventory_rows"] if summary["inventory_rows"] is not None else "-"
        )
        print(f"inputs: scaffold {scaffold_count} / inventoried {inventory_count}")
    return 0 if summary["passed"] else 1
