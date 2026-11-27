"""Turn a GitHub repo into one restorable file.

``git clone --mirror`` copies every branch, tag and ref; ``git bundle
create --all`` packs that into a single ``.bundle`` file. Restoring is just
``git clone repo_2026-11-29_00-00.bundle``.

The token never goes into a URL or onto disk: it is passed to git as an
HTTP header through environment config, so it can't leak into logs or
``.git/config``.
"""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .archive import Snapshot, sha256_of

Runner = Callable[[Sequence[str], dict[str, str]], None]


class MirrorError(RuntimeError):
    pass


def _run(args: Sequence[str], env: dict[str, str]) -> None:
    try:
        subprocess.run(args, check=True, capture_output=True, text=True, env=env)
    except FileNotFoundError as exc:
        raise MirrorError("git is not installed or not on PATH") from exc
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or "").strip().splitlines()
        raise MirrorError(msg[-1] if msg else f"git exited with {exc.returncode}") from exc


def git_env(token: str | None) -> dict[str, str]:
    """Environment for git: never prompt, and authenticate via header if we have a token."""
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token:
        basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"Authorization: Basic {basic}",
        })
    return env


def bundle(clone_url: str, workdir: Path, name: str, token: str | None = None,
           run: Runner = _run) -> Snapshot:
    """Mirror ``clone_url`` into ``workdir`` and write ``name`` (a .bundle) plus its .sha256."""
    workdir.mkdir(parents=True, exist_ok=True)
    mirror = workdir / (name + ".git")
    out = workdir / name
    env = git_env(token)
    run(["git", "clone", "--quiet", "--mirror", clone_url, str(mirror)], env)
    run(["git", "-C", str(mirror), "bundle", "create", "--quiet", str(out), "--all"], env)
    digest = sha256_of(out)
    checksum = out.with_name(out.name + ".sha256")
    checksum.write_text(f"{digest}  {out.name}\n", encoding="utf-8")
    refs = 0
    packed = mirror / "packed-refs"
    if packed.exists():
        refs = sum(1 for line in packed.read_text().splitlines() if line and line[0] not in "#^")
    return Snapshot(out, checksum, digest, refs, out.stat().st_size)
