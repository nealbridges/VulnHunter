"""Language packs that produce the input scaffold.

A3a registers the JS/TS pack only. New packs are added by appending to PACKS;
the walker and the gate do not change (plan D8).
"""

from __future__ import annotations

from .common import Pack, Row, ScanResult, render, scan_repo
from .ts import PACK as _ts

PACKS: list[Pack] = [_ts]

__all__ = ["PACKS", "Pack", "Row", "ScanResult", "render", "scan_repo"]
