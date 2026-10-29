"""Fail-closed breadth gate for phase 1 (plan §3.4, D2-D10).

Read-only: it parses `phase1_output.md` and the scaffold file, prints findings
and returns an exit code. It never writes.
"""

from __future__ import annotations

import contextlib
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


_RULES.update(
    {
        "P2-NO-RESULTS": ("fail", "results/ is missing or empty", "dispatch the phase 2 agents"),
        "P2-TOO-FEW": (
            "fail",
            "result files ({count}) < 3 x partitions ({partitions}) + 1",
            "dispatch the missing class groups",
        ),
        "P2-UNDISPOSITIONED": (
            "fail",
            "input #{number} has no disposition line",
            "add a disposition line for input #{number}",
        ),
        "P2B-NO-OUTPUT": ("fail", "phase2b_output.md is missing", "run the phase 2b verifier"),
        "P2B-COLUMNS": (
            "fail",
            "verdict table lacks: {columns}",
            "add the required verdict columns",
        ),
        "P2B-UNPROBED": (
            "fail",
            "behavioural {verdict} closes on {evidence}",
            "run the probe (executed-probe or runtime-test) or mark HOLD-UNVERIFIED",
        ),
        "P2B-HOLD-NO-PROBE": (
            "fail",
            "HOLD-UNVERIFIED row has no Evidence",
            "write the probe that would settle the claim",
        ),
        "P3-NO-OUTPUT": (
            "fail",
            "phase3_output.md is missing or has no assignment rows",
            "run the phase 3 subagent",
        ),
        "P3-NO-POC": (
            "fail",
            "{vuln} has no PoC and no exploit test",
            "write poc/{vuln}_*.md and exploit_tests/test_vuln_*.py",
        ),
        "P3-NO-RUNTIME": (
            "fail",
            "PoC has no Runtime: line",
            "record the Runtime: line from phase 2b",
        ),
        "P4-NO-README": ("fail", "README.md is missing", "write the report"),
        "P4-NO-UNVERIFIED": (
            "fail",
            "no '## Unverified' heading",
            "always print '## Unverified' (body none when empty)",
        ),
        "P4-HOLD-DROPPED": (
            "fail",
            "HOLD {candidate} appears nowhere in README.md",
            "place the HOLD in Unverified, a confirmed row, or a FALSE POSITIVE row",
        ),
        "P4-NO-HEADER": ("fail", "README header lacks: {columns}", "add the missing header fields"),
    }
)

_VERDICTS = (
    "CANDIDATE",
    "SAFE",
    "DESIGN-INTENT",
    "HOLD-UNVERIFIED",
    "NO-MATCH",
    "CROSS-CLASS",
)
# Matched anywhere in a line, so bullets, numbering, bold and table cells all count.
_DISPOSITION = re.compile(
    r"\b(CANDIDATE|SAFE|DESIGN-INTENT|HOLD-UNVERIFIED|NO-MATCH|CROSS-CLASS)\b"
    r"[*_`\s]*\(\s*input\s*#\s*(\d+)",
    re.I,
)
_CLOSING = ("FALSE POSITIVE", "SAFE", "ELIMINATED")
_RUNTIME = re.compile(r"^\s*(?:[-*>#]+\s*)?(?:\*\*)?Runtime(?:\*\*)?\s*:", re.I)
_CANDIDATE_ID = re.compile(r"\b[A-Z][A-Z0-9]*-\d+\b")
_REQUIRED_2B = ("Closing claim", "Claim type", "Evidence", "Path reasoned about", "Verdict")


def _read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _inventory_numbers(results: Path) -> list[tuple[int, int]]:
    text = _read(results / "phase1_output.md")
    lines = text.splitlines()
    bounds = _inventory_bounds(lines)
    if bounds is None:
        return []
    found: list[tuple[int, int]] = []
    for _, header, rows in _tables(lines, bounds[0], bounds[1]):
        lower = [cell.lower() for cell in header]
        if "#" not in lower:
            continue
        number_cell = lower.index("#")
        for line_number, cells in rows:
            if len(cells) > number_cell:
                with contextlib.suppress(ValueError):
                    found.append((line_number, int(cells[number_cell])))
    return found


def _result_files(results: Path) -> list[Path]:
    directory = results / "results"
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.glob("*_results.md") if path.is_file())


def check2(results: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    files = _result_files(results)
    if not files:
        _emit(findings, "P2-NO-RESULTS", file="results")
    partitions = (
        list((results / "partitions").glob("*_data.md"))
        if (results / "partitions").is_dir()
        else []
    )
    if files and len(files) < 3 * len(partitions) + 1:
        _emit(findings, "P2-TOO-FEW", file="results", count=len(files), partitions=len(partitions))
    seen: set[int] = set()
    for path in files:
        for line in _read(path).splitlines():
            match = _DISPOSITION.search(line)
            if match:
                seen.add(int(match.group(2)))
    if files and not seen:
        _emit(findings, "P2-NO-RESULTS", file="results")
    for line_number, number in _inventory_numbers(results):
        if number not in seen:
            _emit(findings, "P2-UNDISPOSITIONED", line_number, number=number)
    return findings, _summary("2", findings)


def _verdict_tables(lines: list[str]) -> list[tuple[list[str], list[tuple[int, list[str]]]]]:
    return [
        (header, rows)
        for _, header, rows in _tables(lines, 0, len(lines))
        if "verdict" in [cell.lower() for cell in header]
    ]


def _plain(cell: str) -> str:
    return cell.replace("*", "").replace("`", "").strip()


def _mentions(text: str, candidate: str) -> bool:
    # Match the candidate's id (VULN-001, C-3) on a numeric boundary; else the whole cell.
    found = _CANDIDATE_ID.search(candidate)
    if found:
        return re.search(rf"(?<![\w-]){re.escape(found.group(0))}(?!\d)", text) is not None
    return candidate in text


def check2b(results: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    output = results / "phase2b_output.md"
    if not output.is_file():
        _emit(findings, "P2B-NO-OUTPUT")
        return findings, _summary("2b", findings)
    # Every verdict table counts, so a decoy table cannot hide the real one; at least one
    # must carry the full column set.
    tables = _verdict_tables(_read(output).splitlines())
    complete = [
        (header, rows)
        for header, rows in tables
        if all(name.lower() in [cell.lower() for cell in header] for name in _REQUIRED_2B)
    ]
    if not complete:
        lower = [cell.lower() for cell in tables[0][0]] if tables else []
        missing = [name for name in _REQUIRED_2B if name.lower() not in lower]
        _emit(findings, "P2B-COLUMNS", file="phase2b_output.md", columns=", ".join(missing))
        return findings, _summary("2b", findings)
    for header, rows in complete:
        _check_2b_rows(findings, header, rows)
    return findings, _summary("2b", findings)


def _check_2b_rows(
    findings: list[Finding], header: list[str], rows: list[tuple[int, list[str]]]
) -> None:
    lower = [cell.lower() for cell in header]
    claim_cell, evidence_cell = lower.index("claim type"), lower.index("evidence")
    verdict_cell = lower.index("verdict")
    for line_number, cells in rows:
        if len(cells) <= max(claim_cell, evidence_cell, verdict_cell):
            continue
        claim, evidence = _plain(cells[claim_cell]).lower(), _plain(cells[evidence_cell])
        verdict = _plain(cells[verdict_cell]).upper().rstrip(".")
        if (
            claim.startswith(("behavioural", "behavioral"))
            and any(verdict == word or verdict.startswith(word + " ") for word in _CLOSING)
            and not evidence.lower().startswith(("executed-probe", "runtime-test"))
        ):
            _emit(
                findings,
                "P2B-UNPROBED",
                line_number,
                file="phase2b_output.md",
                verdict=verdict,
                evidence=evidence or "(empty)",
            )
        if "HOLD-UNVERIFIED" in verdict and not evidence:
            _emit(findings, "P2B-HOLD-NO-PROBE", line_number, file="phase2b_output.md")


def _assignment_rows(lines: list[str]) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for _, header, rows in _tables(lines, 0, len(lines)):
        lower = [cell.lower() for cell in header]
        if "vuln-nnn" not in lower or "severity" not in lower:
            continue
        id_cell = lower.index("vuln-nnn")
        for line_number, cells in rows:
            if len(cells) > id_cell:
                found.append((line_number, cells[id_cell].strip()))
    return found


def _named(results: Path, directory: str, pattern: str) -> bool:
    folder = results / directory
    return folder.is_dir() and any(
        path.is_file() and re.fullmatch(pattern, path.name) for path in folder.iterdir()
    )


def check3(results: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    output = results / "phase3_output.md"
    if not output.is_file():
        _emit(findings, "P3-NO-OUTPUT")
        return findings, _summary("3", findings)
    lines = _read(output).splitlines()
    assignments = _assignment_rows(lines)
    tables = [rows for _, _, rows in _tables(lines, 0, len(lines)) if rows]
    if not assignments and not tables:
        _emit(findings, "P3-NO-OUTPUT")
    for line_number, vuln in assignments:
        if not vuln:
            continue
        test_id = "test_" + vuln.lower().replace("-", "_")
        poc = _named(results, "poc", rf"^{re.escape(vuln)}(?!\d).*\.md$")
        test = _named(results, "exploit_tests", rf"^{re.escape(test_id)}(?!\d).*\.(py|sh)$")
        if not poc and not test:
            _emit(findings, "P3-NO-POC", line_number, file="phase3_output.md", vuln=vuln)
    folder = results / "poc"
    if folder.is_dir():
        for path in sorted(folder.glob("VULN-*.md")):
            text = _read(path)
            if (
                not any(_RUNTIME.match(line) for line in text.splitlines())
                and "Static PoC" not in text
            ):
                _emit(findings, "P3-NO-RUNTIME", file=f"poc/{path.name}")
    return findings, _summary("3", findings)


def _heading_present(lines: list[str], text: str) -> bool:
    return any(
        (match := _HEADING.match(line))
        and len(match.group(1)) == 2
        and text.lower() in match.group(2).lower()
        for line in lines
    )


def check4(results: Path) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    readme = results / "README.md"
    if not readme.is_file():
        _emit(findings, "P4-NO-README", file="README.md")
        return findings, _summary("4", findings)
    text = _read(readme)
    lines = text.splitlines()
    if not _heading_present(lines, "unverified"):
        _emit(findings, "P4-NO-UNVERIFIED", file="README.md")
    missing = [field for field in ("**Inputs**:", "**Breadth gate**:") if field not in text]
    if missing:
        _emit(findings, "P4-NO-HEADER", file="README.md", columns=", ".join(missing))
    for header, rows in _verdict_tables(_read(results / "phase2b_output.md").splitlines()):
        lower = [cell.lower() for cell in header]
        finding_cell = lower.index("finding") if "finding" in lower else 0
        verdict_cell = lower.index("verdict")
        for _, cells in rows:
            if len(cells) <= max(finding_cell, verdict_cell):
                continue
            candidate = _plain(cells[finding_cell])
            if "HOLD-UNVERIFIED" in cells[verdict_cell].upper() and (
                not candidate or not _mentions(text, candidate)
            ):
                _emit(findings, "P4-HOLD-DROPPED", file="README.md", candidate=candidate)
    return findings, _summary("4", findings)


def _summary(phase: str, findings: list[Finding]) -> dict:
    return {
        "phase": phase,
        "passed": not any(finding.severity == "fail" for finding in findings),
        "scaffold_rows": None,
        "inventory_rows": None,
        "violations": [finding.as_dict() for finding in findings],
    }


_CHECKS = {"2": check2, "2b": check2b, "3": check3, "4": check4}


def run(phase: str, results: Path, scaffold: Path | None, as_json: bool) -> int:
    if phase != "1" and phase not in _CHECKS:
        print(f"phase {phase}: not implemented", file=sys.stderr)
        return 2
    if not results.is_dir():
        print(f"results dir not found: {results}", file=sys.stderr)
        return 2
    if phase == "1":
        findings, summary = check(results, scaffold or results / "inputs_scaffold.md")
    else:
        findings, summary = _CHECKS[phase](results)
    if as_json:
        print(json.dumps(summary))
    else:
        for finding in findings:
            print(finding.line_text())
        if phase == "1":
            scaffold_count = (
                summary["scaffold_rows"] if summary["scaffold_rows"] is not None else "-"
            )
            inventory_count = (
                summary["inventory_rows"] if summary["inventory_rows"] is not None else "-"
            )
            print(f"inputs: scaffold {scaffold_count} / inventoried {inventory_count}")
        else:
            rules = ", ".join(sorted({finding.rule for finding in findings}))
            print(f"phase {phase}: {'PASS' if summary['passed'] else f'FAIL ({rules})'}")
    return 0 if summary["passed"] else 1
