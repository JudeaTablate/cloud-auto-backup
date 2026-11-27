"""Where settings come from.

Precedence, lowest to highest:

1. built-in defaults
2. ``[tool.cab]`` in ``pyproject.toml`` (looked up from the source dir)
3. ``CAB_*`` environment variables (``CAB_REMOTE``, ``CAB_KEEP`` ...)
4. command-line flags
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Mapping

DEFAULT_EXCLUDES = (".git", "__pycache__", ".pytest_cache", "*.pyc", ".venv", "venv", "*.zip")


@dataclass(frozen=True)
class Config:
    remote: str = "gdrive"
    folder: str = "Backups"
    source: Path = Path(".")
    keep: int = 8
    prefix: str = "repo_backup"
    exclude: tuple[str, ...] = field(default=DEFAULT_EXCLUDES)
    dry_run: bool = False
    github_user: str = ""
    forks: bool = False

    @property
    def target(self) -> str:
        """The rclone destination, e.g. ``gdrive:Backups``."""
        folder = self.folder.strip("/")
        return f"{self.remote}:{folder}" if folder else f"{self.remote}:"

    def merged(self, overrides: Mapping[str, Any]) -> "Config":
        """Return a copy with the non-``None`` overrides applied."""
        known = {f.name for f in fields(self)}
        clean = {k: v for k, v in overrides.items() if k in known and v is not None}
        return replace(self, **_coerce(clean))


def _coerce(values: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in values.items():
        if key == "source":
            value = Path(value)
        elif key == "keep":
            value = int(value)
            if value < 0:
                raise ValueError("keep must be >= 0 (0 disables pruning)")
        elif key == "exclude":
            if isinstance(value, str):
                value = [p for p in value.split(",")]
            value = tuple(p.strip() for p in value if p.strip())
        elif key in ("dry_run", "forks"):
            value = value if isinstance(value, bool) else str(value).lower() in {"1", "true", "yes"}
        out[key] = value
    return out


def from_pyproject(path: Path) -> dict[str, Any]:
    """Read ``[tool.cab]`` from a pyproject file; missing file or table -> ``{}``."""
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return dict(data.get("tool", {}).get("cab", {}))


def from_env(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Collect ``CAB_<NAME>`` variables, e.g. ``CAB_KEEP=4``."""
    environ = os.environ if environ is None else environ
    names = {f.name for f in fields(Config)}
    return {
        key[4:].lower(): value
        for key, value in environ.items()
        if key.startswith("CAB_") and key[4:].lower() in names
    }


def load(
    cli: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
    pyproject: Path | None = None,
) -> Config:
    cli = dict(cli or {})
    env = from_env(environ)
    source = Path(cli.get("source") or env.get("source") or ".")
    file_values = from_pyproject(pyproject or source / "pyproject.toml")
    return Config().merged(file_values).merged(env).merged(cli)
