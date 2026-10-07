"""Owner of the ``scan_manifest.schema.json`` contract (plan Phase 1 item 4c).

Layer: CONTRACT (plan §2.2). Today the schema file lives at
``vulnhunter-agent/scan_manifest.schema.json`` and is vendored/consumed by
the agent runtime (``agent/manifest.py``, ``agent/verify_runner.py``) and
duplicated by ``vh``'s stub writer (which hand-rolled its checks — plan
§2.1 finding 4). This module gives every consumer one API:

- :func:`load_schema` — the contract, with the agent-vendored path as the
  authority and a same-bytes pin test guarding the copy
  (``tests/test_vulnhunter_common.py::test_schema_copies_are_identical``).
- :func:`validate_manifest` — real JSON-Schema validation when the
  ``jsonschema`` package is importable; a structural fallback otherwise
  (never a silent pass: the fallback is announced by the returned errors
  list via a ``__fallback__`` marker entry).
- :func:`write_manifest_atomic` — tmp-file + os.replace commit, the
  pattern both writers already used.

Deliberate scope note (§3.0 principle 4): this module validates *shape*;
it does not interpret findings. Judgment stays in the skills/runtime.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_SCHEMA_PATH = REPO_ROOT / "vulnhunter-agent" / "scan_manifest.schema.json"

_SCHEMA_KEYS = (
    "schema_version",
    "scan_id",
    "agent_exit_code",
    "cost_usd",
    "findings",
    "posted",
    "skipped",
    "failed",
)


def load_schema() -> dict[str, Any]:
    """The authoritative scan_manifest schema, as data."""
    return json.loads(AGENT_SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_manifest(body: Any) -> tuple[list[str], bool]:
    """Validate a manifest body. Returns (errors, used_jsonschema).

    With ``jsonschema`` importable, errors are schema-accurate (including
    per-finding required fields). Without it, a structural check runs —
    key presence, list-ness, exit-code domain, scan_id shape — and the
    first returned error is the ``__fallback__`` marker so callers can
    tell the modes apart. Nothing here mutates ``body``.
    """
    try:
        import jsonschema  # noqa: PLC0415 — optional heavy dep, imported lazily
    except ImportError:
        return structural_errors(body), False
    validator_cls = jsonschema.validators.validator_for(load_schema())
    validator = validator_cls(load_schema())
    errors = sorted(validator.iter_errors(body), key=lambda e: list(e.absolute_path))
    return [e.message for e in errors], True


def structural_errors(body: Any) -> list[str]:
    """Structural pre-flight used when jsonschema is unavailable.

    Weaker than the schema (no per-finding field checks) but deterministic.
    """
    errors: list[str] = ["__fallback__: jsonschema unavailable; structural checks only"]
    if not isinstance(body, dict):
        errors.append("manifest must be an object")
        return errors
    for key in _SCHEMA_KEYS:
        if key not in body:
            errors.append(f"missing key: {key}")
    version = body.get("schema_version")
    if version != "1":
        errors.append('schema_version must be "1"')
    scan_id = body.get("scan_id")
    if not (isinstance(scan_id, str) and "_VULNHUNT_RESULTS_" in scan_id):
        errors.append("scan_id must contain _VULNHUNT_RESULTS_")
    exit_code = body.get("agent_exit_code")
    if exit_code not in (0, 1, 2, 3, 4):
        errors.append("agent_exit_code must be one of 0,1,2,3,4")
    cost = body.get("cost_usd")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
        errors.append("cost_usd must be a number >= 0")
    for key in ("findings", "posted", "skipped", "failed"):
        if not isinstance(body.get(key), list):
            errors.append(f"{key} must be a list")
    return errors


def write_manifest_atomic(path: Path, body: dict[str, Any]) -> Path:
    """Write ``body`` as JSON at ``path`` via tmp-file + os.replace (atomic)."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n")
    os.replace(tmp, path)
    return path
