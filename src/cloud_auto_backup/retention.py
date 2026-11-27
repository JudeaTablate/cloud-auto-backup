"""Decide which old snapshots to drop.

Archive names embed a sortable UTC timestamp, so "newest" is just the
lexicographically largest name. Checksum sidecars follow their archive.
Archives are ``.zip`` for a directory snapshot and ``.bundle`` for a repo.
"""

from __future__ import annotations

import re
from typing import Iterable


def _pattern(prefix: str, ext: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix)}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}{re.escape(ext)}$")


def snapshots(names: Iterable[str], prefix: str, ext: str = ".zip") -> list[str]:
    """Archive names that belong to us, newest first."""
    pat = _pattern(prefix, ext)
    return sorted((n for n in names if pat.match(n)), reverse=True)


def plan_prune(names: Iterable[str], prefix: str, keep: int, ext: str = ".zip") -> list[str]:
    """Names to delete so only ``keep`` snapshots remain. ``keep=0`` keeps all."""
    names = list(names)
    if keep <= 0:
        return []
    doomed = snapshots(names, prefix, ext)[keep:]
    present = set(names)
    out: list[str] = []
    for zip_name in doomed:
        out.append(zip_name)
        if (sidecar := zip_name + ".sha256") in present:
            out.append(sidecar)
    return out
