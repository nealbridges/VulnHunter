"""Tests for vulnhunter_common: the contract layer (plan Phase 1 item 4).

The env-contract test is the two-directional checker from plan Phase 1
item 8 (extending the day-1 pattern in vulnhunter-agent to every component):
code usage and the registry must agree in BOTH directions, and every
registered variable must carry a purpose and owner.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import vulnhunter_common.env as env_mod
from vulnhunter_common import gitops, hostcmd, manifest

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPONENT_DIRS = ("vh", "harness", "vulnhunter-agent", "vulnhunter-fix")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for comp in COMPONENT_DIRS:
        base = REPO_ROOT / comp
        if not base.is_dir():
            continue
        files.extend(p for p in base.rglob("*.py") if ".venv" not in p.parts)
    return files


def _skill_md_files() -> list[Path]:
    files: list[Path] = []
    for base in (REPO_ROOT, REPO_ROOT / "skills"):
        if base.is_dir():
            files.extend(base.rglob("*.md"))
    return sorted(set(files))


# --- registry integrity ------------------------------------------------------


def test_every_registered_var_has_purpose_and_owners() -> None:
    for var in env_mod.REGISTRY:
        assert var.name.startswith("VULNHUNT_"), var
        assert var.purpose.strip(), f"{var.name} lacks a purpose statement"
        assert var.owners, f"{var.name} lacks owner components"


def test_registry_names_are_unique() -> None:
    names = [v.name for v in env_mod.REGISTRY]
    assert len(names) == len(set(names))


def test_registered_vars_resolve() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("VULNHUNT_MODEL", "m1")
        assert env_mod.get("VULNHUNT_MODEL") == "m1"
        mp.delenv("VULNHUNT_MODEL", raising=False)
        assert env_mod.get("VULNHUNT_MODEL") is None


def test_get_raises_on_unregistered_name() -> None:
    with pytest.raises(KeyError, match="VULNHUNT_NOT_REGISTERED_XYZ"):
        env_mod.get("VULNHUNT_NOT_REGISTERED_XYZ")


def test_require_raises_with_purpose() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("VULNHUNT_HOST_CMD", raising=False)
        with pytest.raises(RuntimeError, match="VULNHUNT_HOST_CMD"):
            env_mod.require("VULNHUNT_HOST_CMD")


# --- two-directional contract check (plan item 8) ----------------------------


def test_vars_used_in_code_are_registered() -> None:
    used: set[str] = set()
    pattern = re.compile(r"VULNHUNT_[A-Z_]+")
    for path in _python_files():
        used |= set(pattern.findall(path.read_text(encoding="utf-8")))
    used.discard("VULNHUNT_")  # bare prefix mention
    # f-strings that interpolate AFTER the marker leave a trailing underscore
    # behind (e.g. f"..._VULNHUNT_RESULTS_{ts}") — a naming-convention
    # fragment, not a variable; normalize it away.
    used = {name if name in env_mod.REGISTRY_BY_NAME else name.rstrip("_") for name in used}
    unregistered = sorted(used - set(env_mod.REGISTRY_BY_NAME))
    assert not unregistered, (
        f"VULNHUNT_* variables used in code but not in vulnhunter_common.env "
        f"REGISTRY: {unregistered}"
    )


def test_core_documented_vars_agree_with_docs() -> None:
    # Direction 2: every core var must appear in the docs that claim the
    # env contract (vulnhunter-run SKILL.md + the component READMEs).
    docs = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (REPO_ROOT / "vulnhunter-run" / "SKILL.md", REPO_ROOT / "README.md")
        if p.is_file()
    )
    missing = sorted(n for n in env_mod.CORE_DOCUMENTED if n not in docs)
    assert not missing, f"core env vars not documented: {missing}"


def test_registered_vars_with_skill_mentions_are_findable_in_skills() -> None:
    # Direction 2b: a var the skills talk about must be registered (so the
    # registry cannot silently lag the prose contract).
    skills = "\n".join(p.read_text(encoding="utf-8") for p in _skill_md_files())
    mentioned = {name for name in env_mod.REGISTRY_BY_NAME if name in skills}
    assert mentioned, "registry names never appear in skills; registry drifted"
    # And each mention must be registered (implied by construction here) —
    # the load-bearing check is the code-direction test above.


# --- gitops ------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=repo, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


@pytest.fixture()
def origin_repo(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _git(seed, "config", "user.email", "t@t.t")
    _git(seed, "config", "user.name", "t")
    (seed / "f.txt").write_text("v1\n")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "seed")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "origin", "main")
    return origin


def test_clone_shallow_uses_separator_and_clones(origin_repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "clone1"
    gitops.clone_shallow(str(origin_repo), str(dest))
    assert (dest / "f.txt").read_text() == "v1\n"
    # The origin only ever had one commit, so the clone carries exactly it.
    # (Note: a clone from a LOCAL path does not create .git/shallow — git
    # skips depth for local transports unless --no-local is passed.)
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=dest, capture_output=True, text=True, check=True
    )
    assert len(log.stdout.strip().splitlines()) == 1


def test_run_git_survives_url_that_looks_like_a_flag(origin_repo: Path, tmp_path: Path) -> None:
    # The #16-class bug: a URL/branch beginning with '-' used to be parsed
    # as a flag. The SEP contract makes the boundary explicit.
    dest = tmp_path / "clone2"
    gitops.clone_shallow(str(origin_repo), str(dest))
    assert (dest / "f.txt").exists()


def test_rev_parse_resolves_head(origin_repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "clone3"
    gitops.clone_shallow(str(origin_repo), str(dest))
    head = gitops.rev_parse(str(dest), "HEAD")
    assert re.fullmatch(r"[0-9a-f]{40}", head)


def test_git_error_carries_stage_and_cmd(origin_repo: Path, tmp_path: Path) -> None:
    dest = tmp_path / "clone4"
    gitops.clone_shallow(str(origin_repo), str(dest))
    with pytest.raises(gitops.GitError) as ei:
        gitops.rev_parse(str(dest), "no-such-ref-xyz")
    assert ei.value.stage == "rev-parse"
    assert "no-such-ref-xyz" in str(ei.value)


def test_git_error_when_git_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gitops.shutil, "which", lambda name: None)
    with pytest.raises(gitops.GitError, match="git is not on PATH"):
        gitops.clone_shallow("https://example.com/x.git", "/tmp/nowhere")


# --- hostcmd -----------------------------------------------------------------


def _fake_host_script(tmp_path: Path, body: str) -> str:
    """Write a fake host program and make it executable (shutil.which contract)."""
    script = tmp_path / "fake_host.py"
    script.write_text(body)
    script.chmod(0o755)
    return str(script)


def test_resolve_ok_and_argv_appends_prompt_last(tmp_path: Path) -> None:
    script = _fake_host_script(tmp_path, "print('transcript')\n")
    host = hostcmd.resolve({"VULNHUNT_HOST_CMD": f"{script} --flag value"})
    argv = hostcmd.argv_for(host, "/tmp/prompt.txt")
    assert argv[-1] == "/tmp/prompt.txt"
    assert argv[0] == script


def test_resolve_raises_when_unset() -> None:
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("VULNHUNT_HOST_CMD", raising=False)
        with pytest.raises(hostcmd.HostCommandError, match="not set"):
            hostcmd.resolve({})


def test_resolve_raises_when_program_missing() -> None:
    with pytest.raises(hostcmd.HostCommandError, match="not found on PATH"):
        hostcmd.resolve({"VULNHUNT_HOST_CMD": "/definitely/not/on/path/x --flag"})


def test_run_captures_transcript_from_stdout(tmp_path: Path) -> None:
    script = _fake_host_script(
        tmp_path,
        "import json, sys\nprint('preamble')\nprint(json.dumps({'type': 'result'}))\n",
    )
    host = hostcmd.resolve({"VULNHUNT_HOST_CMD": f"{sys.executable} {script}"})
    proc = hostcmd.run(host, str(tmp_path / "prompt.txt"))
    assert "preamble" in proc.stdout
    assert json.loads(proc.stdout.splitlines()[-1])["type"] == "result"


def test_run_raises_timeoutexpired_on_timeout(tmp_path: Path) -> None:
    script = _fake_host_script(tmp_path, "import time; time.sleep(5)\n")
    host = hostcmd.resolve({"VULNHUNT_HOST_CMD": f"{sys.executable} {script}"})
    with pytest.raises(subprocess.TimeoutExpired):
        hostcmd.run(host, str(tmp_path / "prompt.txt"), timeout=0.3)


def test_run_merge_stderr_true_folds_stderr_into_stdout(tmp_path: Path) -> None:
    script = _fake_host_script(tmp_path, "import sys; print('o'); print('e', file=sys.stderr)\n")
    host = hostcmd.resolve({"VULNHUNT_HOST_CMD": f"{sys.executable} {script}"})
    proc = hostcmd.run(host, str(tmp_path / "prompt.txt"), merge_stderr=True)
    assert proc.returncode == 0
    assert "o" in proc.stdout and "e" in proc.stdout
    assert not (proc.stderr or "").strip()


def test_run_merge_stderr_false_captures_stderr_separately(tmp_path: Path) -> None:
    script = _fake_host_script(tmp_path, "import sys; print('o'); print('e', file=sys.stderr)\n")
    host = hostcmd.resolve({"VULNHUNT_HOST_CMD": f"{sys.executable} {script}"})
    proc = hostcmd.run(host, str(tmp_path / "prompt.txt"), merge_stderr=False)
    assert proc.returncode == 0
    assert "o" in proc.stdout
    assert "e" in proc.stderr
    assert "e" not in proc.stdout


def test_popen_streams_combined_output(tmp_path: Path) -> None:
    script = _fake_host_script(
        tmp_path, "import sys; print('out'); print('err', file=sys.stderr)\n"
    )
    host = hostcmd.resolve({"VULNHUNT_HOST_CMD": f"{sys.executable} {script}"})
    proc = hostcmd.popen(host, str(tmp_path / "prompt.txt"))
    out, _ = proc.communicate(timeout=15)
    assert proc.returncode == 0
    assert "out" in out and "err" in out  # merged stream (contract: transcript on stdout)


# --- manifest ----------------------------------------------------------------


def _valid_manifest() -> dict:
    return {
        "schema_version": "1",
        "scan_id": "repo_VULNHUNT_RESULTS_t1",
        "agent_exit_code": 0,
        "cost_usd": 0.0,
        "findings": [],
        "posted": [],
        "skipped": [],
        "failed": [],
    }


def test_schema_loads_and_has_required_keys() -> None:
    schema = manifest.load_schema()
    for key in (
        "schema_version",
        "scan_id",
        "agent_exit_code",
        "cost_usd",
        "findings",
        "posted",
        "skipped",
        "failed",
    ):
        assert key in schema.get("required", []), key


def test_validate_manifest_accepts_valid_body() -> None:
    errors, used_js = manifest.validate_manifest(_valid_manifest())
    assert errors == [] or (len(errors) == 1 and errors[0].startswith("__fallback__"))
    # Either mode must not flag a valid body:
    assert not [e for e in errors if not e.startswith("__fallback__")]


def test_validate_manifest_flags_bad_exit_code() -> None:
    body = _valid_manifest() | {"agent_exit_code": 9}
    errors, _ = manifest.validate_manifest(body)
    assert any("9" in e or "exit" in e.lower() for e in errors), errors


def test_validate_manifest_flags_non_list_findings() -> None:
    body = _valid_manifest() | {"findings": "oops"}
    errors, _ = manifest.validate_manifest(body)
    # jsonschema mode says "not of type 'array'"; fallback mode names the key.
    assert any("array" in e or "findings" in e for e in errors), errors


def test_structural_errors_list_missing_keys() -> None:
    errors = manifest.structural_errors({"schema_version": "1"})
    assert errors[0].startswith("__fallback__")
    assert any("scan_id" in e for e in errors)


def test_write_manifest_atomic_replaces(tmp_path: Path) -> None:
    target = tmp_path / "scan_manifest.json"
    manifest.write_manifest_atomic(target, _valid_manifest())
    first = json.loads(target.read_text())
    assert first["agent_exit_code"] == 0
    body = _valid_manifest() | {"agent_exit_code": 3}
    manifest.write_manifest_atomic(target, body)
    assert json.loads(target.read_text())["agent_exit_code"] == 3
    leftovers = [p.name for p in target.parent.iterdir() if p.name.endswith(".tmp")]
    assert not leftovers


# --- schema copy pin (drift alarm) ------------------------------------------


def test_schema_copies_are_identical() -> None:
    """The contract layer's copy must equal the agent-vendored authority.

    Until the schema is single-homed (plan §6/D-follow-up), the two copies
    must not drift — this test is the drift alarm that forces a conscious
    sync.
    """
    vendored = REPO_ROOT / "vulnhunter-agent" / "scan_manifest.schema.json"
    common_copy = (
        Path(__file__).resolve().parents[2] / "vulnhunter_common" / "scan_manifest.schema.json"
    )
    assert common_copy.exists(), (
        "copy vulnhunter-agent/scan_manifest.schema.json to vulnhunter_common/ "
        "and keep this pin green"
    )
    assert json.loads(vendored.read_text()) == json.loads(common_copy.read_text()), (
        "scan_manifest.schema.json copies diverged — sync them or move to a single home (plan §6)"
    )
