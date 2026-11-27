"""A thin, testable wrapper around the ``rclone`` binary.

Everything goes through :class:`Rclone.run`, so tests can swap in a fake
runner instead of touching a real remote.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

Runner = Callable[[Sequence[str]], str]


class RcloneError(RuntimeError):
    pass


def _subprocess_runner(args: Sequence[str]) -> str:
    try:
        done = subprocess.run(args, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RcloneError("rclone is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        raise RcloneError(exc.stderr.strip() or f"rclone exited with {exc.returncode}") from exc
    return done.stdout


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size: int
    modified: str


@dataclass
class Rclone:
    binary: str = "rclone"
    runner: Runner = _subprocess_runner
    dry_run: bool = False

    def run(self, *args: str, mutating: bool = False) -> str:
        cmd = [self.binary, *args]
        if mutating and self.dry_run:
            cmd.append("--dry-run")
        return self.runner(cmd)

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def upload(self, files: Sequence[Path], target: str) -> None:
        for path in files:
            self.run("copyto", str(path), f"{target.rstrip('/')}/{path.name}", mutating=True)

    def list(self, target: str) -> list[RemoteFile]:
        raw = self.run("lsjson", target, "--files-only")
        return [
            RemoteFile(item["Name"], int(item.get("Size", 0)), item.get("ModTime", ""))
            for item in json.loads(raw or "[]")
        ]

    def delete(self, target: str, name: str) -> None:
        self.run("deletefile", f"{target.rstrip('/')}/{name}", mutating=True)
