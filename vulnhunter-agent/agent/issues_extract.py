"""Extract findings from a VulnHunter results directory via Haiku.

Prefers ``README.md`` (the Phase 4 report). If that file is missing or empty
but Phase 2 candidate write-ups are on disk, those files are concatenated and
extracted instead so ``--issues`` can still file what the hunt produced.

The agent never re-reads finding text in its own context (see CLAUDE.md);
extraction is delegated to Haiku and the structured JSON it returns is
what the rest of the issues stage operates on.

PoC and exploit-test paths come from filesystem enumeration, not the LLM,
so the model can't hallucinate file locations.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import _llm
from .auth import TokenProvider
from .config import AgentConfig

if TYPE_CHECKING:
    from .audit import AuditWriter

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Finding:
    """Structured representation of one confirmed VulnHunter finding."""

    id: str  # VULN-NNN — scan-local; never put in issue title.
    title: str
    cwe: str  # e.g. "CWE-89"
    cwe_name: str  # e.g. "SQL Injection"
    severity: str
    location: str
    root_cause: str
    data_flow: str
    entry_point: str
    exploit_description: str
    exploit_impact: str
    fix_strategy: str
    severity_rationale: str
    poc_path: str | None = None
    exploit_test_path: str | None = None
    # 16-char SHA-256 prefix over (location, cwe, root_cause). Stable
    # across scans so re-runs collide on the same vulnerability even if
    # VulnHunter renumbers VULN-IDs between scans.
    vulnfix_key: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SOURCE_README = "readme"
SOURCE_CANDIDATES = "candidates"


@dataclass(frozen=True)
class ExtractedReport:
    findings: list[Finding]
    scan_date: str  # YYYY-MM-DD; used in issue body footer
    results_dir_name: str  # used in <!-- vulnhunt-results-dir: ... --> marker
    # "readme" when Phase 4 wrote README.md; "candidates" when extraction
    # assembled Phase 2 write-ups because that report was missing.
    source: str = SOURCE_README


_SCAN_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})-\d{6}")
# Match both VULN-NNN (canonical) and vuln_NNN (alt form used by exploit-test
# files in some report formats).
_VULN_FILE_RE = re.compile(r"VULN[-_](\d+)", re.IGNORECASE)


_FINDING_SCHEMA = """{
  "findings": [
    {
      "id": "VULN-001",
      "title": "Short human-readable title (no CWE prefix, no severity)",
      "cwe": "CWE-89",
      "cwe_name": "SQL Injection",
      "severity": "Critical|High|Medium|Low",
      "location": "src/path/file.py:42",
      "root_cause": "One-sentence description of the underlying defect.",
      "data_flow": "Source → ... → sink description.",
      "entry_point": "HTTP route, function, or other public surface.",
      "exploit_description": "What an attacker can do (1-3 sentences). Describe behavior, not exploit code.",
      "exploit_impact": "Concrete consequence (data disclosure, RCE, account takeover, etc.).",
      "fix_strategy": "One-sentence summary of the proposed fix from the report.",
      "severity_rationale": "Why this severity (impact + reachability)."
    }
  ]
}"""

_EXTRACTOR_SYSTEM = f"""You extract VulnHunter scan findings from a Markdown report \
into strict JSON. You return ONLY a JSON object — no prose, no code fences, no commentary.

The report has a summary table near the top with columns including a Status \
column. ONLY findings whose status is "Confirmed" are in scope; ignore \
"Code Smells", "Observations", "Defense in Depth", "Informational", or any \
finding marked anything other than "Confirmed".

For each confirmed finding, locate its detail section (typically `## VULN-NNN: ...` \
or similar) and read the field table and prose subsections to fill in the schema below.

Schema (always emit every key; use empty string "" if a field cannot be \
determined from the report — never invent values):

{_FINDING_SCHEMA}
"""

_EXTRACTOR_SYSTEM_CANDIDATES = f"""You extract VulnHunter scan findings from Phase 2 \
candidate write-ups into strict JSON. You return ONLY a JSON object — no prose, \
no code fences, no commentary.

The Phase 4 README.md was not written. The material below is assembled from \
trace-agent result files (typically `results/sg-*_*.md` and `candidates/*.md`). \
These are candidate write-ups, not a confirmed report.

IN SCOPE: every candidate that uses the Candidate Output Format \
(`#### [VULN-NNN] Title` with Gate 0–3, Location, Class, Severity, Data Flow, \
Root Cause) and was not eliminated.
OUT OF SCOPE: SAFE, NO-MATCH, DESIGN-INTENT, dead-code, and inventory rows \
that have no write-up.

Map fields as follows:
- id: the VULN-NNN from the heading
- title: the heading title
- cwe / cwe_name: from **Class** (e.g. CWE-89: SQL Injection)
- severity: from **Severity**
- location: from **Location**
- root_cause: from **Root Cause**
- data_flow: from **Data Flow**
- entry_point: from **Entry Point**
- exploit_description: from **Exploitability** and Gate 3 (what the attacker gains)
- exploit_impact: the outcome Gate 3 / severity implies
- fix_strategy: empty string unless the write-up proposes a fix
- severity_rationale: from **Severity** plus Gate 2a/3

Schema (always emit every key; use empty string "" if a field cannot be \
determined — never invent values):

{_FINDING_SCHEMA}
"""


def _scan_date_from_dir(results_dir_name: str) -> str:
    m = _SCAN_DATE_RE.search(results_dir_name)
    if m:
        return m.group(1)
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _compute_vulnfix_key(location: str, cwe: str, root_cause: str) -> str:
    """SHA-256 prefix used as a cross-scan idempotency marker.

    Same convention as vulnhunter-fix so future tooling can correlate.
    """
    raw = f"{location}|{cwe}|{root_cause}".encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _canonical_vuln_id(raw_number: str) -> str:
    """Normalize a VULN-NNN identifier to zero-padded 3-digit form.

    Files in poc/ and exploit_tests/ may use ``VULN-1``, ``VULN-01``,
    ``VULN-001``, or ``vuln_001``; the LLM emits one canonical form
    in its JSON. Normalize both sides so the lookup is unambiguous.
    """
    return f"VULN-{int(raw_number):03d}"


def _discover_finding_files(results_dir: Path) -> dict[str, dict[str, str]]:
    """Map canonical VULN-NNN → {poc, exploit_test} from filesystem enumeration."""
    out: dict[str, dict[str, str]] = {}
    for sub, key in [("poc", "poc"), ("exploit_tests", "exploit_test")]:
        d = results_dir / sub
        if not d.exists():
            continue
        for f in d.iterdir():
            m = _VULN_FILE_RE.search(f.name)
            if not m:
                continue
            out.setdefault(_canonical_vuln_id(m.group(1)), {})[key] = str(f)
    return out


def _add_unique_paths(out: list[Path], seen: set[Path], paths: list[Path]) -> None:
    for path in paths:
        if not path.is_file() or path.name == "README.md":
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(path)


def candidate_writeup_paths(results_dir: Path) -> list[Path]:
    """Phase 2 write-ups the hunter leaves when Phase 4 never ran.

    Order: ``results/sg-*_*.md``, other ``results/*.md``, ``candidates/*.md``,
    then top-level ``sg-*_*.md``. README.md is never included.
    """
    out: list[Path] = []
    seen: set[Path] = set()
    results_sub = results_dir / "results"
    if results_sub.is_dir():
        _add_unique_paths(out, seen, sorted(results_sub.glob("sg-*_*.md")))
        _add_unique_paths(out, seen, sorted(results_sub.glob("*.md")))
    candidates_sub = results_dir / "candidates"
    if candidates_sub.is_dir():
        _add_unique_paths(out, seen, sorted(candidates_sub.glob("*.md")))
    _add_unique_paths(out, seen, sorted(results_dir.glob("sg-*_*.md")))
    return out


def load_report_material(results_dir: Path) -> tuple[str, str]:
    """Return ``(markdown, source)`` for extraction.

    Prefers a non-empty ``README.md``. Otherwise concatenates Phase 2
    candidate write-ups. Raises ``FileNotFoundError`` when neither exists.
    """
    readme = results_dir / "README.md"
    if readme.is_file():
        text = readme.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            return text, SOURCE_README

    paths = candidate_writeup_paths(results_dir)
    chunks: list[str] = []
    for path in paths:
        body = path.read_text(encoding="utf-8", errors="replace")
        if not body.strip():
            continue
        rel = path.relative_to(results_dir).as_posix()
        chunks.append(f"----- BEGIN {rel} -----\n{body}\n----- END {rel} -----")
    if chunks:
        logger.warning(
            "README.md missing or empty in %s; extracting from %d Phase 2 candidate write-up(s)",
            results_dir,
            len(chunks),
        )
        return "\n\n".join(chunks), SOURCE_CANDIDATES

    raise FileNotFoundError(
        f"README.md not found in {results_dir} and no Phase 2 candidate "
        "write-ups were found under results/, candidates/, or sg-*_*.md"
    )


def _coerce_finding(raw: dict[str, Any], files: dict[str, dict[str, str]]) -> Finding:
    """Build a Finding dataclass, filling in optional fields with ''."""
    fid = str(raw.get("id", "")).strip()
    # Look up files by canonical id so callers don't have to care
    # whether the LLM emitted "VULN-1" or "VULN-001".
    canonical = ""
    m = re.search(r"VULN[-_](\d+)", fid, re.IGNORECASE)
    if m:
        canonical = _canonical_vuln_id(m.group(1))
    related = files.get(canonical, {}) if canonical else {}
    location = str(raw.get("location", "")).strip()
    cwe = str(raw.get("cwe", "")).strip()
    root_cause = str(raw.get("root_cause", "")).strip()
    return Finding(
        id=fid,
        title=str(raw.get("title", "")).strip(),
        cwe=cwe,
        cwe_name=str(raw.get("cwe_name", "")).strip(),
        severity=str(raw.get("severity", "")).strip(),
        location=location,
        root_cause=root_cause,
        data_flow=str(raw.get("data_flow", "")).strip(),
        entry_point=str(raw.get("entry_point", "")).strip(),
        exploit_description=str(raw.get("exploit_description", "")).strip(),
        exploit_impact=str(raw.get("exploit_impact", "")).strip(),
        fix_strategy=str(raw.get("fix_strategy", "")).strip(),
        severity_rationale=str(raw.get("severity_rationale", "")).strip(),
        poc_path=related.get("poc"),
        exploit_test_path=related.get("exploit_test"),
        vulnfix_key=_compute_vulnfix_key(location, cwe, root_cause),
    )


def _user_message(content: str, source: str) -> str:
    if source == SOURCE_CANDIDATES:
        instruction = (
            "Extract every in-scope candidate write-up from the Phase 2 files below. "
            "Return strict JSON matching the schema in the system prompt."
        )
    else:
        instruction = (
            "Extract every Confirmed finding from the report below. Return strict JSON "
            "matching the schema in the system prompt. Report begins after the marker."
        )
    return f"{instruction}\n\n----- BEGIN REPORT -----\n{content}\n----- END REPORT -----\n"


async def extract_findings(
    results_dir: Path,
    config: AgentConfig,
    token_manager: TokenProvider,
    *,
    cost_tracker: _llm.CostStats | None = None,
    audit_writer: AuditWriter | None = None,
) -> ExtractedReport:
    """Extract findings from ``results_dir``.

    Uses ``README.md`` when present and non-empty; otherwise concatenates
    Phase 2 candidate write-ups. Falls back to Sonnet on any LLM transport /
    parse failure. Raises ``LLMError`` (from ``_llm``) if both models fail.
    Raises ``FileNotFoundError`` when neither a report nor candidate files
    exist — that is not a clean scan.
    """
    content, source = load_report_material(results_dir)
    system = _EXTRACTOR_SYSTEM_CANDIDATES if source == SOURCE_CANDIDATES else _EXTRACTOR_SYSTEM
    user_msg = _user_message(content, source)

    try:
        parsed = await _llm.call_json_with_fallback(
            primary_model=config.issues.haiku_model,
            fallback_model=config.issues.sonnet_model,
            system=system,
            user=user_msg,
            config=config,
            token_manager=token_manager,
            cost_tracker=cost_tracker,
            stage="extract",
            audit_writer=audit_writer,
        )
    except _llm.LLMError as exc:
        # Both haiku + sonnet failed (typically because they're not
        # provisioned on this Bedrock deployment — see GH#48). Fall back
        # to the scan session's model, which we know works on this
        # account because the scan itself completed. More expensive but
        # unblocks the pipeline.
        logger.warning(
            "[extract] Haiku+Sonnet fallback exhausted (%s); retrying with scan-session model %s",
            exc,
            config.anthropic.model,
        )
        if audit_writer is not None:
            from .audit import build_model_fallback

            audit_writer.emit_audit(
                build_model_fallback(
                    app_id=config.audit.app_id,
                    actor=config.audit.actor,
                    from_model=config.issues.sonnet_model,
                    to_model=config.anthropic.model,
                    stage="extract",
                    reason=str(exc),
                    report_id=results_dir.name,
                )
            )
        try:
            parsed = await _llm.call_json(
                model=config.anthropic.model,
                system=system,
                user=user_msg,
                config=config,
                token_manager=token_manager,
                cost_tracker=cost_tracker,
                stage="extract-scan-fallback",
            )
        except _llm.LLMError as final_exc:
            # Final tier failed too — no model in the chain is available.
            if audit_writer is not None:
                from .audit import build_model_unavailable

                audit_writer.emit_audit(
                    build_model_unavailable(
                        app_id=config.audit.app_id,
                        actor=config.audit.actor,
                        from_model=config.anthropic.model,
                        stage="extract",
                        reason=str(final_exc),
                        report_id=results_dir.name,
                    )
                )
            raise

    raw_findings = parsed.get("findings") if isinstance(parsed, dict) else None
    if not isinstance(raw_findings, list):
        raise _llm.LLMError(f"extractor returned no 'findings' list (got {type(parsed).__name__})")

    files = _discover_finding_files(results_dir)
    findings = []
    for raw in raw_findings:
        if not isinstance(raw, dict):
            logger.warning("Skipping non-object finding in extractor output: %r", raw)
            continue
        if not raw.get("id"):
            logger.warning("Skipping finding with no id: %r", raw)
            continue
        findings.append(_coerce_finding(raw, files))

    return ExtractedReport(
        findings=findings,
        scan_date=_scan_date_from_dir(results_dir.name),
        results_dir_name=results_dir.name,
        source=source,
    )
