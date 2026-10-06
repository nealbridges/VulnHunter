"""Shared extractor for normative (MUST/SHALL/SHOULD) statements in skills.

Used by tests/test_skill_contracts.py to build the requirement register, and
by the register-generation entry point (python -m agent._skill_contract).
Neutrality note (BUILD_PLAN §4.5a): the skills are an operational methodology,
not a skill pack — the extractor's job is to keep the methodology's promises
enumerated and stable, so any change to a promise is a deliberate, reviewable
act.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Files whose normative statements become register requirements. Prompt-only
# skill trees are scanned wholesale; exclude anything obviously private.
SCAN_GLOBS = (
    "vulnhunt/**/*.md",
    "vulnhunter-fix/SKILL.md",
    "vulnhunter-fix/prompts/*.md",
    "vulnhunter-fix/references/*.md",
    "vulnhunt-fix-verify/*.md",
    "vulnhunt-fix-verify/phases/*.md",
    "vulnhunter-run/*.md",
    "skills/*/SKILL.md",          # new-generation skills (operator procedures)
    "skills/*/phases/*.md",
    "skills/*/references/*.md",
)

# A requirement = one sentence containing a normative keyword. The skills use
# both the RFC-2119 uppercase convention (MUST/SHALL/SHOULD) and prose-lowercase
# ("must", "should") with the same binding intent; the extractor is
# case-insensitive and records the keyword AS WRITTEN (the register's `Keyword`
# column shows e.g. `MUST` vs `must`). Sentence split on `. ` / `.\n` / `; `
# boundaries is intentionally simple: the skills write one requirement per
# sentence. Multi-clause sentences yield one requirement each (acceptable —
# the register's value is enumeration + stability, not perfect segmentation).
NORMATIVE_RE = re.compile(
    r"\b(MUST(?:\s+NOT)?|SHALL(?:\s+NOT)?|SHOULD(?:\s+NOT)?|"
    r"must(?:\s+not)?|shall(?:\s+not)?|should(?:\s+not)?)\b"
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z`(])|\n\n+")

# Requirement IDs: VH-<AREA>-<NNN>, assigned in first-seen scan order and
# persisted in the register so they stay stable across runs. Ordered
# longest-prefix-first so `vulnhunt-fix-verify` routes to VER, not HUNT.
# `skills/runtime-provisioner` etc. route by their basename under skills/.
AREA_BY_PREFIX = {
    "vulnhunter-fix": "FIX",
    "vulnhunt-fix-verify": "VER",
    "vulnhunter-run": "RUN",
    "skills/runtime-provisioner": "RUN",
    "vulnhunt": "HUNT",
}


@dataclass(frozen=True)
class Requirement:
    req_id: str
    source: str          # repo-relative file path
    line: int            # 1-based line of the sentence start
    keyword: str         # MUST / SHALL / SHOULD (with optional NOT)
    text: str            # the sentence


def _sentences(text: str) -> list[tuple[int, str]]:
    """Yield (1-based line of the sentence's FIRST character, sentence).

    Implementation: walk the text with an offset cursor; a sentence begins at
    the first non-blank character after the previous boundary and ends at the
    next boundary (or EOF). This keeps line numbers exact even when sentences
    span wrapped markdown lines or blank-line-separated blocks.
    """
    out: list[tuple[int, str]] = []
    pos = 0
    n = len(text)
    while pos < n:
        # skip to first non-whitespace char (start of the sentence)
        while pos < n and text[pos] in " \t\r\n":
            pos += 1
            if text[pos - 1] == "\n":
                pass  # newline(s) consumed; line counting handled below
        if pos >= n:
            break
        start_line = text.count("\n", 0, pos) + 1
        # find the sentence end: next boundary (`. ` / `.\n` / `; ` / blank block)
        end = pos
        while end < n:
            ch = text[end]
            if ch in ".;":
                # boundary only if followed by whitespace/EOF (not "e.g.", "0.5")
                nxt = text[end + 1: end + 3]
                if end + 1 >= n or nxt[:1] in (" ", "\t", "\r", "\n", "") or (
                    nxt[:1] == "\n" and nxt[1:2] == "\n"
                ):
                    end += 1
                    break
                end += 1
                continue
            if ch == "\n" and text[end + 1: end + 2] == "\n":
                end += 2  # blank line: paragraph break without punctuation
                break
            end += 1
        sentence = " ".join(text[pos:end].split())
        if sentence:
            out.append((start_line, sentence))
        pos = end
    return out


def extract_requirements() -> list[Requirement]:
    """Scan the shipped skills and return every normative sentence."""
    requirements: list[Requirement] = []
    counters: dict[str, int] = {}
    for pattern in SCAN_GLOBS:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            area = next((a for prefix, a in AREA_BY_PREFIX.items()
                         if rel == prefix or rel.startswith(prefix + "/")), "MISC")
            text = path.read_text(encoding="utf-8")
            captured = False
            for line_no, sentence in _sentences(text):
                match = NORMATIVE_RE.search(sentence)
                if match:
                    captured = True
                    counters[area] = counters.get(area, 0) + 1
                    requirements.append(Requirement(
                        req_id=f"VH-{area}-{counters[area]:03d}",
                        source=rel,
                        line=line_no,
                        keyword=match.group(1),
                        text=sentence,
                    ))
            # Definition tables: rows of a "mapping" table whose first cell is a
            # SHOUTY_CODE define the vocabulary (e.g. the verdict mapping in
            # phase2_verify.md). These are requirements even without normative
            # keywords — the table *defines* the contract. One requirement per
            # row, keyword column `defines`, line = the row's line in the file.
            if captured is False or True:  # tables are additive, not exclusive
                requirements.extend(_definition_table_rows(rel, path, counters, area))
    return requirements


def _definition_table_rows(
    rel: str, path: Path, counters: dict[str, int], area: str
) -> list[Requirement]:
    """Capture `| `CODE` | condition |` rows under a mapping/`Verdict` heading.

    A row qualifies when the line is a markdown table row, its first cell is a
    SHOUTY code token, and the nearest preceding heading contains 'mapping' or
    'Verdict'. These rows define the vocabulary the rest of the skill (and the
    register) rely on, so they belong in the register with keyword `defines`.
    """
    out: list[Requirement] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    heading_ok = False
    for idx, line in enumerate(lines, start=1):
        if line.startswith("#"):
            heading_ok = bool(re.search(r"mapping|verdict", line, re.I))
            continue
        row = re.match(r"^\|\s*`?([A-Z][A-Z_]{2,})`?\s*\|", line)
        if not (row and heading_ok):
            continue
        condition = line.split("|")[2].strip() if line.count("|") >= 2 else ""
        counters[area] = counters.get(area, 0) + 1
        out.append(Requirement(
            req_id=f"VH-{area}-{counters[area]:03d}",
            source=rel,
            line=idx,
            keyword="defines",
            text=f"{row.group(1)} — {condition}"[:400],
        ))
    return out


def render_register(requirements: list[Requirement]) -> str:
    """Render the private requirement register (product_docs/)."""
    lines = [
        "# VulnHunter skill requirement register (PRIVATE)",
        "",
        "Generated by `vulnhunter-agent/agent/_skill_contract.py` —",
        "do not edit by hand; regenerate and commit the result.",
        "Every entry is a normative statement (MUST/SHALL/SHOULD) found in a",
        "shipped skill file. A change to a skill's normative text must update",
        "the register in the same commit (enforced by test_skill_contracts.py).",
        "",
        "| ID | File:Line | Keyword | Requirement |",
        "|---|---|---|---|",
    ]
    for r in requirements:
        text = r.text.replace("|", "\\|")
        lines.append(f"| {r.req_id} | `{r.source}:{r.line}` | {r.keyword} | {text} |")
    lines.append("")
    lines.append(f"Total requirements: {len(requirements)}")
    lines.append("")
    return "\n".join(lines) + "\n"


def register_path() -> Path:
    return REPO_ROOT / "product_docs" / "skill_requirements.md"


def write_register() -> Path:
    """Regenerate the private register and return its path."""
    path = register_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_register(extract_requirements()), encoding="utf-8")
    return path


if __name__ == "__main__":
    print(f"wrote {write_register()}")
