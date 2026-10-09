"""Single source of truth for ``VULNHUNT_*`` environment variables.

Layer: CONTRACT (plan §2.2). Every variable the Python runtimes read is
declared here as data — name, purpose, owner component, and where the
authoritative handling lives — plus typed accessors used by the runtimes.

Rationale (plan §2.1 finding 1): ``VULNHUNT_DIR`` was referenced 49 times
across the skills and defined by no Python code; nothing checked that the
harness, the skills, and the operator CLI agreed. This module is the
anti-drift device: ``tests/test_env_contract.py`` pins code usage and skill
documentation against REGISTRY in both directions.

Skill prose is NEVER edited by tooling (§3.0 principle 1); this module is
the code side of the agreement, and gaps surface as test failures.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

OWNER_VH = "vh"
OWNER_HARNESS = "harness"
OWNER_AGENT = "vulnhunter-agent"
OWNER_FIX = "vulnhunter-fix"
OWNER_SKILLS = "skills (prompt-level convention)"


@dataclass(frozen=True)
class EnvVar:
    """One ``VULNHUNT_*`` variable, declared as data (plan Phase 1 item 5)."""

    name: str
    purpose: str
    owners: tuple[str, ...]
    default: str | None = None
    required: bool = False


REGISTRY: tuple[EnvVar, ...] = (
    # --- paths and installation layout ---
    EnvVar(
        "VULNHUNT_SKILLS_DIR",
        "Root directory the installed skills live under (per-harness; no ~/.claude-style guessing).",
        (OWNER_VH, OWNER_HARNESS, OWNER_AGENT, OWNER_FIX, OWNER_SKILLS),
    ),
    EnvVar(
        "VULNHUNT_AGENTS_DIR",
        "Directory the harness scans for agent definitions (e.g. agents/vulnhunter.md).",
        (OWNER_VH, OWNER_AGENT, OWNER_SKILLS),
    ),
    EnvVar(
        "VULNHUNT_BIN_DIR",
        "Directory install.sh writes the vh launcher into (default ~/.local/bin).",
        (OWNER_VH, OWNER_SKILLS),
    ),
    EnvVar(
        "VULNHUNT_DIR",
        "Absolute results directory of the current scan: <target>/<basename>_VULNHUNT_RESULTS_<timestamp>. Set by the harness prompt for the skills; consumed by skills and runtimes.",
        (OWNER_SKILLS, OWNER_AGENT, OWNER_HARNESS),
    ),
    EnvVar(
        "VULNHUNT_RESULTS",
        "The results directory (the _VULNHUNT_RESULTS_ marker is also the glob the agent uses to find prior scan dirs).",
        (OWNER_SKILLS, OWNER_AGENT, OWNER_HARNESS),
    ),
    EnvVar(
        "VULNHUNT_SCAN_ALLOWED_TOOLS",
        "Restricts the toolset a scan run may use (agent-side tool gating).",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_TLS_SSL_CERT_PATH",
        "Custom CA bundle path for TLS verification in component HTTP calls.",
        (OWNER_AGENT,),
    ),
    # --- host execution ---
    EnvVar(
        "VULNHUNT_HOST_CMD",
        "The harness's headless one-shot. argv = shlex.split(value) + [prompt_file]; the program writes its transcript to stdout. Owned by hostcmd (vulnhunter_common) for resolution/spawn/timeout.",
        (OWNER_VH, OWNER_HARNESS, OWNER_AGENT, OWNER_SKILLS),
    ),
    # --- model selection ---
    EnvVar(
        "VULNHUNT_MODEL",
        "Model id the harness runs the hunt with; also recorded into benchmark state for reproducibility (Phase 3 item 15).",
        (OWNER_HARNESS, OWNER_AGENT),
    ),
    EnvVar(
        "VULNHUNT_ANTHROPIC_MODEL",
        "Model override for the agent runtime when it talks to Anthropic directly.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_ANTHROPIC_API_KEY",
        "API key for direct Anthropic access from the agent runtime.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_ANTHROPIC_AUTH_MODE",
        "Auth mode for the agent runtime (e.g. bedrock_sigv4).",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_ANTHROPIC_AWS_REGION",
        "AWS region for Bedrock-backed runs of the agent runtime.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_ANTHROPIC_AWS_PROFILE",
        "AWS profile for Bedrock-backed runs of the agent runtime.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_ANTHROPIC_BEDROCK_BASE_URL",
        "Base URL override for Bedrock-backed runs.",
        (OWNER_AGENT,),
    ),
    # --- agent configuration and GitHub credentials ---
    EnvVar(
        "VULNHUNT_AGENT_CONFIG",
        "Path to the agent's TOML config (default: agent/config.toml).",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_GITHUB_SCAN_TOKEN",
        "GitHub token used by the scan/reporting side.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_GITHUB_REPORTS_TOKEN",
        "GitHub token used for publishing reports/issues.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_GITHUB_BROKER_TOKEN_DIR",
        "Directory of broker-issued GitHub tokens, keyed per role/run.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_OAUTH_CLIENT_ID",
        "OAuth client id for GitHub app flows in the agent runtime.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_OAUTH_CLIENT_SECRET",
        "OAuth client secret for GitHub app flows in the agent runtime.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_OAUTH_TOKEN_ENDPOINT",
        "OAuth token endpoint override for GitHub app flows.",
        (OWNER_AGENT,),
    ),
    # --- publish / results handling ---
    EnvVar(
        "VULNHUNT_PUBLISH_ENABLED",
        "Enables the agent's publish stage (push results to the remote repo).",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_LOGGING_PER_TURN_USAGE",
        "Enables per-turn usage logging in the agent runtime.",
        (OWNER_AGENT,),
    ),
    EnvVar(
        "VULNHUNT_LOGGING_RETRIES", "Enables retry-logging in the agent runtime.", (OWNER_AGENT,)
    ),
    # --- fix pipeline ---
    EnvVar(
        "VULNHUNT_BRANCH",
        "Branch naming input for the fix skill: '<branch> [<short-sha]>' (vulnhunt/SKILL.md).",
        (OWNER_SKILLS,),
    ),
    EnvVar(
        "VULNHUNT_BASE_URL",
        "Base URL override used by the fix pipeline's remote checks.",
        (OWNER_FIX,),
    ),
    EnvVar(
        "VULNHUNT_PROMPT_PREAMBLE",
        "Extra preamble text prepended to fix-pipeline prompts.",
        (OWNER_FIX,),
    ),
)

REGISTRY_BY_NAME: dict[str, EnvVar] = {v.name: v for v in REGISTRY}

# Variables the skills document as the installation/env contract (vulnhunter-
# run SKILL.md and the component READMEs). The two-directional checker in
# tests/test_env_contract.py pins this core set against documentation.
CORE_DOCUMENTED = frozenset(
    {
        "VULNHUNT_SKILLS_DIR",
        "VULNHUNT_AGENTS_DIR",
        "VULNHUNT_BIN_DIR",
        "VULNHUNT_HOST_CMD",
        "VULNHUNT_MODEL",
    }
)


def get(name: str, default: str | None = None) -> str | None:
    """os.environ.get against the registry-validated name.

    Raises KeyError for an unregistered name — the point of the registry is
    that every read goes through a documented variable.
    """
    if name not in REGISTRY_BY_NAME:
        raise KeyError(f"VULNHUNT var not registered: {name} (vulnhunter_common.env)")
    return os.environ.get(name, default)


def require(name: str) -> str:
    """Get a registry-validated variable or raise a descriptive error."""
    value = get(name)
    if not value:
        raise RuntimeError(
            f"{name} is required but not set — see vulnhunter_common.env.REGISTRY "
            f"for its contract ({REGISTRY_BY_NAME[name].purpose})"
        )
    return value
