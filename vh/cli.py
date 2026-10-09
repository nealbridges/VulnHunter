"""Deterministic operator commands for a VulnHunter run.

The host harness runs the hunt. This module clones, writes and checks the
scan manifest, and launches whatever headless command that harness already
uses. It does not import a model SDK and it does not name a harness.

The manifest this module writes is a stub: it records the agent exit code
and schema shape, but never findings. Findings are populated by the
agent-side writer (vulnhunter-agent), which extracts them from the scan
README against the same schema.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from vulnhunter_common import gitops, hostcmd, manifest

_SCAN_ID = re.compile(r"^.+_VULNHUNT_RESULTS_.+$")
_EXIT_OK = {0, 1, 2, 3, 4}


def cmd_clone(args: argparse.Namespace) -> int:
    url = args.url
    if url.startswith("-"):
        print("refusing a URL that looks like an option", file=sys.stderr)
        return 2
    dest = Path(args.dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        if not args.reclone:
            print(f"clone already exists: {dest}", file=sys.stderr)
            return 2
        shutil.rmtree(dest)
    try:
        # gitops owns the argv contract (the -- separator before the URL)
        # and the error taxonomy; depth is part of the shallow-clone pattern.
        gitops.clone_shallow(url, str(dest), depth=args.depth)
    except gitops.GitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def _results_dirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    found = [p for p in root.iterdir() if p.is_dir() and _SCAN_ID.match(p.name)]
    return sorted(found)


def cmd_find_results(args: argparse.Namespace) -> int:
    found = _results_dirs(Path(args.root))
    if not found:
        print(f"no *_VULNHUNT_RESULTS_* directory under {args.root}", file=sys.stderr)
        return 1
    for path in found:
        print(path)
    return 0


def _manifest_body(results: Path, exit_code: int | None) -> dict:
    # An explicit --exit-code wins. When omitted, derive one from the scan
    # README: a non-empty report means the hunt ran, anything else is a miss.
    if exit_code is None:
        readme = results / "README.md"
        exit_code = 0 if readme.is_file() and readme.stat().st_size > 0 else 1
    if exit_code not in _EXIT_OK:
        exit_code = 1
    return {
        "schema_version": "1",
        "scan_id": results.name,
        "agent_exit_code": exit_code,
        "cost_usd": 0,
        "findings": [],
        "posted": [],
        "skipped": [],
        "failed": [],
    }


def _validate(body: dict) -> list[str]:
    """Validate a manifest body: schema + corpus conventions.

    Delegates the schema contract to vulnhunter_common.manifest — real
    JSON-Schema validation when jsonschema is importable, the announced
    structural fallback otherwise. On top of the schema floor, the
    corpus convention (plan §3.0: the corpus is the acceptance set) adds
    the stricter scan_id naming rule the results layout depends on.
    """
    errors, used_jsonschema = manifest.validate_manifest(body)
    errors = [e for e in errors if not e.startswith("__fallback__")]
    if not used_jsonschema:
        # Fallback mode: mirror the checks the schema would enforce.
        for key in ("schema_version", "scan_id", "agent_exit_code", "cost_usd"):
            if key not in body:
                errors.append(f"missing {key}")
        if body.get("schema_version") != "1":
            errors.append('schema_version must be "1"')
        if body.get("agent_exit_code") not in _EXIT_OK:
            errors.append("agent_exit_code must be 0, 1, 2, 3, or 4")
        cost = body.get("cost_usd")
        if not isinstance(cost, (int, float)) or isinstance(cost, bool) or cost < 0:
            errors.append("cost_usd must be a number >= 0")
        for key in ("findings", "posted", "skipped", "failed"):
            if not isinstance(body.get(key), list):
                errors.append(f"{key} must be an array")
    scan_id = body.get("scan_id") if isinstance(body, dict) else None
    if not isinstance(scan_id, str) or not _SCAN_ID.match(scan_id):
        errors.append("scan_id must match .+_VULNHUNT_RESULTS_.+")
    return errors


def cmd_write_manifest(args: argparse.Namespace) -> int:
    results = Path(args.results).resolve()
    if not results.is_dir() or not _SCAN_ID.match(results.name):
        print("results dir must be named <repo>_VULNHUNT_RESULTS_<label>", file=sys.stderr)
        return 2
    body = _manifest_body(results, args.exit_code)
    errors = _validate(body)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 2
    target = results / "scan_manifest.json"
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n")
    os.replace(tmp, target)
    print(target)
    return 0


def cmd_validate_manifest(args: argparse.Namespace) -> int:
    path = Path(args.manifest)
    if path.is_dir():
        path = path / "scan_manifest.json"
    try:
        body = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read manifest: {exc}", file=sys.stderr)
        return 2
    errors = _validate(body)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"ok {path}")
    return 0


def cmd_host(args: argparse.Namespace) -> int:
    # hostcmd owns the VULNHUNT_HOST_CMD contract: shlex-split, prompt file
    # appended LAST, transcript on the child's stdout. vh keeps its
    # prompt-exists pre-check and the historical no-timeout behavior (the
    # harness-side launcher owns timeouts); a --timeout flag is a follow-up,
    # not a silent change.
    try:
        host = hostcmd.resolve()
    except hostcmd.HostCommandError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    prompt = Path(args.prompt)
    if not prompt.is_file():
        print(f"prompt file not found: {prompt}", file=sys.stderr)
        return 2
    proc = subprocess.run(hostcmd.argv_for(host, str(prompt.resolve())))
    return proc.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vh")
    sub = parser.add_subparsers(dest="cmd", required=True)

    clone = sub.add_parser("clone", help="shallow-clone a repo")
    clone.add_argument("url")
    clone.add_argument("--dest", required=True)
    clone.add_argument("--depth", type=int, default=1)
    clone.add_argument("--reclone", action="store_true")
    clone.set_defaults(func=cmd_clone)

    find = sub.add_parser("find-results", help="print *_VULNHUNT_RESULTS_* directories")
    find.add_argument("root")
    find.set_defaults(func=cmd_find_results)

    write = sub.add_parser("write-manifest", help="write a schema-shaped scan_manifest.json")
    write.add_argument("results")
    write.add_argument(
        "--exit-code",
        type=int,
        default=None,
        help="agent exit code to record (0-4). When omitted, it is "
        "derived from the scan README: non-empty means 0, otherwise 1.",
    )
    write.set_defaults(func=cmd_write_manifest)

    check = sub.add_parser("validate-manifest", help="check a scan_manifest.json")
    check.add_argument("manifest")
    check.set_defaults(func=cmd_validate_manifest)

    host = sub.add_parser("host", help="run $VULNHUNT_HOST_CMD with a prompt file")
    host.add_argument("prompt")
    host.set_defaults(func=cmd_host)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    func = args.func
    # argparse stores the handler as Any (set_defaults(**kwargs)); the
    # annotation documents the contract every cmd_* honors: return int.
    return int(func(args))
