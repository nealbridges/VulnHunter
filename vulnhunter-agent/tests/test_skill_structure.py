"""Structural contract tests for VulnHunter's shipped skills.

These tests enforce the FORMAT CONTRACT that any harness's skill loader can
consume — not any single harness's conventions. The loader contract (as
exhibited by e.g. Cyber-Frost Harness's SkillLibrary, and by Claude Code's
skills directory) requires:

  1. <skills_root>/<name>/SKILL.md exists, with YAML frontmatter containing
     at least `name` and `description`;
  2. frontmatter `name` equals the directory name;
  3. files a skill references (phases/, references/, templates/, prompts/)
     exist in the repo.

VulnHunter ships three skills (vulnhunt, vulnhunter-fix, vulnhunt-fix-verify)
plus the vulnhunter-run operator skill. This module locates the repo root
relative to this file, so the tests run from any checkout.

Normative-text requirements (MUST/SHALL/SHOULD extraction) live in
test_skill_contracts.py; the shared extractor is agent/_skill_contract.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# (skill directory name, shipped files that must exist)
SKILLS = [
    "vulnhunt",
    "vulnhunter-fix",
    "vulnhunt-fix-verify",
    "vulnhunter-run",
]

REQUIRED_TOP_LEVEL = {
    "vulnhunt": {"SKILL.md", "README.md", "phases/phase1_recon.md",
                 "phases/phase2_shared.md", "phases/phase2b_verify.md",
                 "phases/phase4_report.md"},
    "vulnhunter-fix": {"SKILL.md", "README.md"},
    "vulnhunt-fix-verify": {"SKILL.md", "README.md"},
    "vulnhunter-run": {"SKILL.md"},
}

FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)


def _skill_root(skill: str) -> Path:
    return REPO_ROOT / skill


def _frontmatter_fields(skill: str) -> dict:
    """Parse SKILL.md frontmatter.

    Uses a real YAML parser when importable (the correct semantics for the
    format contract — frontmatter IS YAML), with the line-based fallback for
    environments without PyYAML. The naive line parser (as used by some
    harness loaders, e.g. Cyber-Frost Harness's SkillLibrary) only accepts
    single-line `key: value` pairs; that constraint is asserted separately
    for the `name`/`description` keys, which is why the shipped skills keep
    those two single-line.
    """
    path = REPO_ROOT / skill / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    assert match, f"{skill}/SKILL.md: missing YAML frontmatter block"
    block = match.group(1)
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        pass
    else:
        fields = yaml.safe_load(block)
        assert isinstance(fields, dict), f"{skill}: frontmatter is not a mapping"
        return fields
    fields: dict = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "- ")):
            continue  # comments and list items have no scalar role here
        if line.startswith((" ", "-")):
            continue  # nested structure: handled by the YAML path when present
        key, sep, value = line.partition(":")
        assert sep, f"{skill}/SKILL.md: frontmatter line not `key: value`: {line!r}"
        fields[key.strip()] = value.strip().strip("\"'")
    return fields


@pytest.mark.parametrize("skill", SKILLS)
class TestSkillFormatContract:
    """The format contract ANY harness loader needs (see module docstring)."""

    def test_skill_md_exists(self, skill: str) -> None:
        assert (REPO_ROOT / skill / "SKILL.md").is_file(), (
            f"{skill}/SKILL.md missing — the skill is not installable"
        )

    def test_frontmatter_has_name_and_description(self, skill: str) -> None:
        fields = _frontmatter_fields(skill)
        assert fields.get("name"), f"{skill}: frontmatter missing `name`"
        assert fields.get("description"), f"{skill}: frontmatter missing `description`"

    def test_name_and_description_are_single_line_safe(self, skill: str) -> None:
        """Naive loaders (line-partition based, e.g. Cyber-Frost's current
        SkillLibrary) raise on colon-less or folded lines. The two keys every
        loader must surface (name, description) therefore must survive a
        line-partition parse: keep them single-line in the shipped files."""
        text = (REPO_ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
        match = FRONTMATTER_RE.match(text)
        assert match, f"{skill}: missing frontmatter"
        for line in match.group(1).splitlines():
            if re.match(r"^(name|description):", line):
                # the key line itself is `key: value` — safe. A folded
                # (`key: >`) or empty-value form would break naive loaders.
                assert not re.match(r"^(name|description):\s*(>|$)", line), (
                    f"{skill}: `{line}` uses a folded/empty value — naive "
                    "loaders can't read it; keep name/description single-line"
                )

    def test_frontmatter_name_matches_directory(self, skill: str) -> None:
        fields = _frontmatter_fields(skill)
        assert fields["name"] == skill, (
            f"{skill}: frontmatter name {fields['name']!r} != directory {skill!r}"
        )

    def test_required_files_present(self, skill: str) -> None:
        required = REQUIRED_TOP_LEVEL.get(skill, set())
        missing = [p for p in required if not (REPO_ROOT / skill / p).is_file()]
        assert not missing, f"{skill}: missing shipped files: {missing}"

    def test_no_unresolved_relative_md_links(self, skill: str) -> None:
        """Every relative .md link inside the skill tree must resolve.

        Exception: links using the runtime placeholder convention (paths
        containing `VULN-<n>` / `NNN`) — phase4_report.md illustrates the
        link FORMAT with a concrete example (`poc/VULN-001_desc.md`), but
        `poc/` and `exploit_tests/` are runtime output directories, populated
        per-scan; the skill tree ships the pattern, not the instance.
        """
        broken: list[str] = []
        placeholder = re.compile(r"VULN-\d|NNN")
        for md in (REPO_ROOT / skill).rglob("*.md"):
            for target in re.findall(r"\]\(([^)#\s]+\.md)\)", md.read_text(encoding="utf-8")):
                if "://" in target:  # absolute URL — not a repo-relative link
                    continue
                if placeholder.search(target):
                    continue  # illustrative example of the runtime layout
                resolved = (md.parent / target).resolve()
                if not resolved.is_file():
                    broken.append(f"{md.relative_to(REPO_ROOT)} -> {target}")
        assert not broken, f"{skill}: dead relative links: {broken}"


class TestHarnessNeutrality:
    """Skills claim harness portability — assert no harness-isms leak back in.

    The methodology is host-agnostic; the format contract is the standard.
    A harness-specific literal is allowed only in files whose job is to name
    the harness (READMEs, env-contract docs), not in the procedure itself.
    """

    # Files where harness names are documentation (allowed):
    ALLOWED = re.compile(r"(README\.md$|SKILL\.md$)")

    # Literals that betray a single-harness assumption in procedure text:
    FORBIDDEN = [
        (re.compile(r"\bclaude-opus-\d"), "pinned model literal"),
        (re.compile(r"\bthe Claude CLI\b"), "Claude CLI as the only CLI"),
    ]

    @pytest.mark.parametrize("skill", ["vulnhunt", "vulnhunt-fix-verify",
                                       "vulnhunter-run"])
    def test_procedure_files_stay_harness_neutral(self, skill: str) -> None:
        """Prompt-only skills must not hardcode one harness in procedure text."""
        offenders: list[str] = []
        for md in (REPO_ROOT / skill).rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            for pattern, why in self.FORBIDDEN:
                for match in pattern.finditer(text):
                    line_no = text[: match.start()].count("\n") + 1
                    offenders.append(f"{md.relative_to(REPO_ROOT)}:{line_no} {why}: {match.group(0)!r}")
        assert not offenders, f"{skill}: harness-isms in procedure files: {offenders}"

    def test_vulnhunter_fix_env_contract_documented(self) -> None:
        """Every VULNHUNT_* var referenced in code/scripts must be in the README
        env table (or the install docs), and vice versa for the core set."""
        skill_dir = REPO_ROOT / "vulnhunter-fix"
        used: set[str] = set()
        for py in skill_dir.rglob("*.py"):
            used |= set(re.findall(r"VULNHUNT_[A-Z_]+", py.read_text(encoding="utf-8")))
        for md in skill_dir.rglob("*.md"):
            used |= set(re.findall(r"VULNHUNT_[A-Z_]+", md.read_text(encoding="utf-8")))
        used.discard("VULNHUNT_")  # bare prefix mention
        # The core contract every consumer needs (README "Environment contract"):
        core = {"VULNHUNT_SKILLS_DIR", "VULNHUNT_AGENTS_DIR", "VULNHUNT_BIN_DIR",
                "VULNHUNT_HOST_CMD", "VULNHUNT_MODEL"}
        undocumented = {var for var in used
                        if var not in core
                        and not self._mentioned_in_docs(var)}
        assert not undocumented, (
            f"vulnhunter-fix: VULNHUNT_* vars used but not documented: {sorted(undocumented)}"
        )

    def _mentioned_in_docs(self, var: str) -> bool:
        docs = list((REPO_ROOT / "vulnhunter-fix").rglob("*.md"))
        docs.append(REPO_ROOT / "README.md")
        return any(var in d.read_text(encoding="utf-8") for d in docs if d.is_file())


class TestSchemaContracts:
    """The agent's JSON schemas are cross-harness contracts — keep them valid."""

    def test_schemas_are_valid_json_with_fork_home(self) -> None:
        import json
        for schema_name in ("scan_manifest.schema.json",
                            "verify_disposition.schema.json"):
            path = REPO_ROOT / "vulnhunter-agent" / schema_name
            schema = json.loads(path.read_text(encoding="utf-8"))
            assert schema.get("$id"), f"{schema_name}: missing $id"
            assert schema.get("x-fork-home") == "https://github.com/nealbridges/VulnHunter", (
                f"{schema_name}: x-fork-home missing or wrong"
            )
