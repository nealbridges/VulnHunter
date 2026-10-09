"""The one ``VULNHUNT_HOST_CMD`` launcher for VulnHunter Python runtimes.

Layer: CONTRACT+RUNTIME (plan §2.2, Phase 1 item 4b). Before this module
the launch logic existed three times with divergent semantics:

- ``vh/cli.py::cmd_host``        — no timeout, no capture contract
- ``harness/local_harness/scan.py`` — streams stdout, Timer-based kill
- ``harness/.../analyze_misses.py`` — fixed 1200s timeout, captured output

The contract they implement (vulnhunter-run/SKILL.md): the value of
``VULNHUNT_HOST_CMD`` is shlex-split, the prompt file path is appended as
the LAST argument, and the program writes its transcript to stdout.
:func:`resolve` centralizes value resolution/validation;
:func:`popen`/:func:`run` centralize spawn + timeout + the streaming
drain pattern (so a chatty child cannot deadlock on an unread pipe).
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass


class HostCommandError(RuntimeError):
    """``VULNHUNT_HOST_CMD`` is unset, unresolvable, or not executable."""


@dataclass(frozen=True)
class HostCommand:
    """A resolved host command: the argv prefix and the program path."""

    argv_prefix: tuple[str, ...]
    program: str


def resolve(environ: dict[str, str] | None = None) -> HostCommand:
    """Resolve ``VULNHUNT_HOST_CMD`` into an argv prefix (hostcmd contract).

    Raises :class:`HostCommandError` when unset, when the first token is
    not an executable on PATH, or when it resolves to something
    non-executable. Callers append the prompt file path as the last
    argument before spawning.
    """
    env = os.environ if environ is None else environ
    raw = env.get("VULNHUNT_HOST_CMD", "").strip()
    if not raw:
        raise HostCommandError(
            "VULNHUNT_HOST_CMD is not set. Set it to your harness's headless "
            "one-shot. The prompt file path is appended as the last argument."
        )
    parts = shlex.split(raw)
    if not parts:
        raise HostCommandError("VULNHUNT_HOST_CMD is empty after parsing")
    program = parts[0]
    if not shutil.which(program):
        raise HostCommandError(f"VULNHUNT_HOST_CMD program not found on PATH: {program!r}")
    return HostCommand(argv_prefix=tuple(parts), program=program)


def argv_for(host: HostCommand, prompt_file: str) -> list[str]:
    """Full argv: host tokens + the prompt file path appended LAST (contract)."""
    return [*host.argv_prefix, prompt_file]


def popen(
    host: HostCommand,
    prompt_file: str,
    *,
    cwd: str | None = None,
    merge_stderr: bool = True,
) -> subprocess.Popen:
    """Spawn the host command with the streaming-drain-safe pipe setup.

    stdout is a pipe the caller must drain; stderr is merged into it by
    default (an undrained stderr pipe deadlocks a chatty child past
    ~64 KB — the deadlock scan.py's comment documents). There is no
    ``timeout`` here: a :class:`~subprocess.Popen` cannot time itself out;
    callers either enforce it around the drain (scan.py's Timer) or use
    :func:`run`, which raises :class:`subprocess.TimeoutExpired`.
    """
    argv = argv_for(host, prompt_file)
    return subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True,
        cwd=cwd,
    )


def run(
    host: HostCommand,
    prompt_file: str,
    *,
    cwd: str | None = None,
    timeout: float | None = None,
    merge_stderr: bool = True,
) -> subprocess.CompletedProcess:
    """Run to completion. Raises :class:`subprocess.TimeoutExpired` on
    timeout — the caller decides the timeout semantics (analyze_misses
    uses a fixed budget; scan.py streams).

    ``merge_stderr`` honors the same drain-safety rule as :func:`popen`:
    with the default ``True`` the child's stderr is folded into
    ``stdout`` (so nothing blocks on a full stderr pipe); with ``False``
    stderr is captured separately on ``CompletedProcess.stderr``.
    """
    argv = argv_for(host, prompt_file)
    return subprocess.run(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )
