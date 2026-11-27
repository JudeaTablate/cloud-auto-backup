"""Command-line entry point: ``cab run | list | prune | config``."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path
from typing import Sequence

import os

from . import __version__, archive, config, github, mirror, retention
from .remote import Rclone, RcloneError

log = logging.getLogger("cab")


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def cmd_run(cfg: config.Config, rclone: Rclone) -> int:
    """Archive the source tree, upload it, then prune old snapshots."""
    name = archive.archive_name(cfg.prefix)
    with tempfile.TemporaryDirectory(prefix="cab-") as tmp:
        snap = archive.build(cfg.source, Path(tmp), name, cfg.exclude)
        log.info("packed   %s  (%d files, %s)", snap.zip_path.name, snap.files, human(snap.size))
        log.info("sha256   %s", snap.sha256)
        rclone.upload([snap.zip_path, snap.checksum_path], cfg.target)
        log.info("uploaded -> %s%s", cfg.target, "  [dry-run]" if cfg.dry_run else "")
    if cfg.keep:
        cmd_prune(cfg, rclone)
    return 0


def cmd_list(cfg: config.Config, rclone: Rclone) -> int:
    """Show the snapshots currently on the remote, newest first."""
    files = {f.name: f for f in rclone.list(cfg.target)}
    names = retention.snapshots(files, cfg.prefix)
    if not names:
        log.info("no snapshots at %s", cfg.target)
        return 0
    for n in names:
        print(f"{n}  {human(files[n].size):>9}  {files[n].modified}")
    return 0


def cmd_prune(cfg: config.Config, rclone: Rclone) -> int:
    """Delete everything but the newest --keep snapshots."""
    names = [f.name for f in rclone.list(cfg.target)]
    doomed = retention.plan_prune(names, cfg.prefix, cfg.keep)
    for name in doomed:
        rclone.delete(cfg.target, name)
        log.info("pruned   %s%s", name, "  [dry-run]" if cfg.dry_run else "")
    if not doomed:
        log.info("retain   nothing to prune (keep=%d)", cfg.keep)
    return 0


def cmd_repos(cfg: config.Config, rclone: Rclone, *, token: str | None = None,
              list_repos=github.list_repos, bundle=mirror.bundle) -> int:
    """Back up every GitHub repo you own: mirror, bundle, upload, prune each."""
    if not cfg.github_user:
        raise ValueError("set github_user ([tool.cab], CAB_GITHUB_USER or --github-user)")
    token = token if token is not None else os.environ.get("CAB_GITHUB_TOKEN") or None
    repos = list_repos(cfg.github_user, token, forks=cfg.forks)
    scope = "public + private" if token else "public only (no CAB_GITHUB_TOKEN)"
    log.info("github   %d repos for %s, %s", len(repos), cfg.github_user, scope)
    stamp = archive.archive_name("x").removeprefix("x_").removesuffix(".zip")
    failed = 0
    for repo in repos:
        target = f"{cfg.target.rstrip('/')}/repos/{repo.name}"
        name = f"{repo.name}_{stamp}.bundle"
        try:
            with tempfile.TemporaryDirectory(prefix="cab-repo-") as tmp:
                snap = bundle(repo.clone_url, Path(tmp), name, token)
                rclone.upload([snap.zip_path, snap.checksum_path], target)
            log.info("bundled  %-28s %9s -> %s%s", repo.name, human(snap.size), target,
                     "  [dry-run]" if cfg.dry_run else "")
        except mirror.MirrorError as exc:
            if "empty" in str(exc).lower():
                log.info("skipped  %-28s (empty repo)", repo.name)
                continue
            failed += 1
            log.error("failed   %-28s %s", repo.name, exc)
            continue
        if cfg.keep:
            names = [f.name for f in rclone.list(target)]
            for old in retention.plan_prune(names, repo.name, cfg.keep, ext=".bundle"):
                rclone.delete(target, old)
                log.info("pruned   %s%s", old, "  [dry-run]" if cfg.dry_run else "")
    log.info("done     %d backed up, %d failed", len(repos) - failed, failed)
    return 1 if failed else 0


def cmd_config(cfg: config.Config, rclone: Rclone) -> int:
    """Print the resolved settings and exit."""
    for key, value in vars(cfg).items():
        if isinstance(value, tuple):
            value = ", ".join(value)
        print(f"{key:<8} = {value}")
    print(f"{'target':<8} = {cfg.target}")
    return 0


COMMANDS = {"run": cmd_run, "repos": cmd_repos, "list": cmd_list, "prune": cmd_prune, "config": cmd_config}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cab",
        description="Zip a directory, checksum it, and ship it to an rclone remote.",
    )
    parser.add_argument("--version", action="version", version=f"cab {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print errors")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for name, fn in COMMANDS.items():
        p = sub.add_parser(name, help=fn.__doc__.splitlines()[0], description=fn.__doc__)
        p.add_argument("--remote", help="rclone remote name (default: gdrive)")
        p.add_argument("--folder", help="folder on the remote (default: Backups)")
        p.add_argument("--source", help="directory to back up (default: .)")
        p.add_argument("--keep", type=int, help="snapshots to keep, 0 = keep all (default: 8)")
        p.add_argument("--prefix", help="archive name prefix (default: repo_backup)")
        p.add_argument("--exclude", help="comma-separated glob patterns to skip")
        p.add_argument("-n", "--dry-run", action="store_true", default=None,
                       help="show what would change on the remote without changing it")
        if name in ("repos", "config"):
            p.add_argument("--github-user", help="GitHub account whose repos to back up")
            p.add_argument("--forks", action="store_true", default=None, help="include forked repos")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.ERROR if args.quiet else logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    command = args.command or "run"
    overrides = {k: v for k, v in vars(args).items() if k not in {"command", "quiet"}}
    try:
        cfg = config.load(overrides)
        return COMMANDS[command](cfg, Rclone(dry_run=cfg.dry_run))
    except (RcloneError, github.GitHubError, ValueError, OSError) as exc:
        log.error("error    %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
