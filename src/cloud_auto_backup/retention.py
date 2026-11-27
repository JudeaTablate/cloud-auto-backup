"""Decide which old snapshots to drop.

Archive names embed a sortable UTC timestamp, so "newest" is just the
lexicographically largest name. Checksum sidecars follow their zip.
"""

from __future__ import annotations

import re
from typing import Iterable

def _pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix)}_\d{{4}}-\d{{2}}-\d{{2}}_\d{{2}}-\d{{2}}\.zip$")


def snapshots(names: Iterable[str], prefix: str) -> list[str]:
    """Zip names that belong to us, newest first."""
    pat = _pattern(prefix)
    return sorted((n for n in names if pat.match(n)), reverse=True)


def plan_prune(names: Iterable[str], prefix: str, keep: int) -> list[str]:
    """Names to delete so only ``keep`` snapshots remain. ``keep=0`` keeps all."""
    names = list(names)
    if keep <= 0:
        return []
    doomed = snapshots(names, prefix)[keep:]
    present = set(names)
    out: list[str] = []
    for zip_name in doomed:
        out.append(zip_name)
        if (sidecar := zip_name + ".sha256") in present:
            out.append(sidecar)
    return out
