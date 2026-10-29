"""Language packs that produce the input scaffold.

Registry order is ts, go, python, java. Packs that need repo-wide type
information implement ``prepare(repo)``; the package-level ``scan_repo``
wraps the core walker so that hook runs before any file is scanned.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from .common import Pack, Row, ScanResult, render
from .common import scan_repo as _scan_repo
from .go import PACK as _go
from .java import PACK as _java
from .python import PACK as _python
from .ts import PACK as _ts

PACKS: list[Pack] = [_ts, _go, _python, _java]


def scan_repo(repo: Path | str, packs: Sequence[Pack]) -> ScanResult:
    for pack in packs:
        prepare = getattr(pack, "prepare", None)
        if prepare is not None:
            prepare(Path(repo))
    result = _scan_repo(Path(repo), packs)
    order = [pack.name for pack in packs]
    result.packs = sorted(result.packs, key=order.index)
    return result


__all__ = ["PACKS", "Pack", "Row", "ScanResult", "render", "scan_repo"]
