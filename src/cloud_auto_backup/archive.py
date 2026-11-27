"""Build the zip.

The archive is always written *outside* the tree being archived (a temp dir
by default), so it can never end up zipping itself. Each archive gets a
``.sha256`` sidecar in the same format ``sha256sum -c`` understands.
"""

from __future__ import annotations

import fnmatch
import hashlib
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

STAMP_FORMAT = "%Y-%m-%d_%H-%M"


@dataclass(frozen=True)
class Snapshot:
    zip_path: Path
    checksum_path: Path
    sha256: str
    files: int
    size: int


def archive_name(prefix: str, when: datetime | None = None) -> str:
    when = when or datetime.now(timezone.utc)
    return f"{prefix}_{when.strftime(STAMP_FORMAT)}.zip"


def is_excluded(rel: Path, patterns: Iterable[str]) -> bool:
    """True if any path component, or the whole relative path, matches."""
    text = rel.as_posix()
    for pattern in patterns:
        if fnmatch.fnmatch(text, pattern):
            return True
        if any(fnmatch.fnmatch(part, pattern) for part in rel.parts):
            return True
    return False


def iter_files(root: Path, exclude: Iterable[str]) -> Iterator[Path]:
    """Yield files under ``root`` (sorted, so archives are reproducible)."""
    exclude = tuple(exclude)
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and not path.is_symlink() and not is_excluded(rel, exclude):
            yield path


def sha256_of(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def build(source: Path, out_dir: Path, name: str, exclude: Iterable[str]) -> Snapshot:
    source = source.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = (out_dir / name).resolve()
    if zip_path.is_relative_to(source):
        raise ValueError(f"refusing to write {zip_path} inside the source tree {source}")

    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in iter_files(source, exclude):
            zf.write(path, path.relative_to(source).as_posix())
            count += 1

    digest = sha256_of(zip_path)
    checksum_path = zip_path.with_name(zip_path.name + ".sha256")
    checksum_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return Snapshot(zip_path, checksum_path, digest, count, zip_path.stat().st_size)
