"""Build the project site into ``_site/``.

Nothing on the page is typed by hand twice. The command reference comes from
the real argparse parser, the settings table from the ``Config`` dataclass,
the stats line from the source tree, and the sky from a seeded generator, so
every commit gets its own cloud cover.

    python site/build.py            # writes _site/
    python site/build.py --serve    # and serves it on :8000
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from cloud_auto_backup import __version__, cli  # noqa: E402
from cloud_auto_backup.config import Config  # noqa: E402
from cloud_auto_backup.config import load as config_load  # noqa: E402

REPO = "https://github.com/JudeaTablate/cloud-auto-backup"
PROJECT = config_load(environ={}, pyproject=ROOT / "pyproject.toml")


# ---------------------------------------------------------------- sky ----

def cloud_svg(rng: random.Random, uid: str, cx: float, base: float, width: float) -> tuple[str, str]:
    """One soft cumulus: a row of puffs, tallest in the middle, cut flat at the base.

    Returns (clipPath def, cloud markup). The cloud is drawn twice: a shade
    layer nudged down-right for the underside, and the white body on top.
    """
    n = rng.randint(4, 6)
    height = width * rng.uniform(0.26, 0.34)
    puffs = []
    for i in range(n):
        t = (i + 0.5) / n
        r = height * (0.45 + 0.55 * math.sin(math.pi * t)) * rng.uniform(0.85, 1.1)
        x = cx - width / 2 + t * width
        puffs.append(f'<circle cx="{x:.1f}" cy="{base - r * rng.uniform(0.45, 0.7):.1f}" r="{r:.1f}"/>')
    # bigger clouds get a second, smaller tier of puffs so they tower a little
    if width > 200:
        for _ in range(rng.randint(1, 3)):
            r = height * rng.uniform(0.45, 0.7)
            x = cx + rng.uniform(-0.25, 0.25) * width
            puffs.append(f'<circle cx="{x:.1f}" cy="{base - height * rng.uniform(0.9, 1.2):.1f}" r="{r:.1f}"/>')
    left = cx - width / 2 - height
    clip = (f'<clipPath id="cut-{uid}"><rect x="{left:.1f}" y="{base - 3 * height:.1f}" '
            f'width="{width + 2 * height:.1f}" height="{3 * height:.1f}"/></clipPath>')
    body = "".join(puffs)
    cloud = (
        f'<g class="cloud">'
        f'<g class="shade" fill="currentColor" clip-path="url(#cut-{uid})" transform="translate(2 5)">{body}</g>'
        f'<g class="body" clip-path="url(#cut-{uid})">{body}</g></g>'
    )
    return clip, cloud


# the view through the window: a tall frame, drawn once per lap width
SKY_WIDTH = 900
SKY_HEIGHT = 1000

DECKS = (
    # name, base band (y0, y1), width range, clouds per lap, seconds per lap
    ("hi", (210, 300), (120, 190), 4, 200),
    ("mid", (430, 500), (160, 230), 3, 130),
    ("lo", (640, 700), (200, 280), 3, 80),
    ("floor", (880, 910), (260, 360), 6, 55),  # the carpet of cloud below the plane
)


def sky_svg(seed: str, width: int = SKY_WIDTH, height: int = SKY_HEIGHT) -> str:
    """The sky band: three cloud decks drifting left at different speeds.

    Each deck is drawn once, then reused at -width and +width with <use>, so
    sliding it by exactly one width loops without a visible seam. Far decks
    are smaller, paler and blurrier. Stars only show in dark mode.
    """
    rng = random.Random(seed)
    defs = [
        '<linearGradient id="sky-fill" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" class="sky-top"/><stop offset="1" class="sky-bottom"/></linearGradient>',
        '<filter id="soft-hi"><feGaussianBlur stdDeviation="2.2"/></filter>',
        '<filter id="soft-mid"><feGaussianBlur stdDeviation="1"/></filter>',
        '<filter id="soft-lo"><feGaussianBlur stdDeviation="0.6"/></filter>',
        '<filter id="soft-floor"><feGaussianBlur stdDeviation="1.4"/></filter>',
    ]
    stars = "".join(
        f'<circle class="star" cx="{rng.uniform(0, width):.0f}" cy="{rng.uniform(6, height * 0.6):.0f}" '
        f'r="{rng.choice((1.2, 1.6, 2.2))}"/>'
        for _ in range(90)
    )
    decks = []
    for name, (y0, y1), (w0, w1), count, seconds in DECKS:
        slot = width / count
        clouds = []
        for i in range(count):
            clip, cloud = cloud_svg(
                rng, f"{name}{i}", slot * (i + rng.uniform(0.2, 0.8)), rng.uniform(y0, y1), rng.uniform(w0, w1)
            )
            defs.append(clip)
            clouds.append(cloud)
        if name == "floor":  # solid cloud below the carpet, so no sky shows underneath
            clouds.append(f'<rect class="body" x="0" y="{y0 - 6}" width="{width}" height="{height - y0 + 6}"/>')
        decks.append(
            f'<g class="deck deck-{name}" style="--lap:{seconds}s">'
            f'<g id="deck-{name}" filter="url(#soft-{name})">{"".join(clouds)}</g>'
            f'<use href="#deck-{name}" x="{-width}"/><use href="#deck-{name}" x="{width}"/></g>'
        )
    return (
        f'<svg class="sky" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid slice" '
        f'aria-hidden="true" style="--w:{width}px"><defs>{"".join(defs)}</defs>'
        f'<rect class="air" width="{width}" height="{height}" fill="url(#sky-fill)"/>'
        f'<g class="stars">{stars}</g>{"".join(decks)}</svg>'
    )


# ------------------------------------------------------------ content ----

def git(*args: str, default: str = "") -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return default


def python_lines() -> int:
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("tests/*.py"), *HERE.glob("*.py")]
    return sum(len(p.read_text(encoding="utf-8").splitlines()) for p in files)


DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def backup_cron() -> str:
    """The cron expression from the backup workflow, so the page can't drift from it."""
    workflow = ROOT / ".github" / "workflows" / "backup.yml"
    match = re.search(r"cron:\s*['\"]([^'\"]+)['\"]", workflow.read_text(encoding="utf-8"))
    return match.group(1) if match else "0 0 * * 0"


def describe_cron(cron: str) -> str:
    """'0 0 * * 0' -> 'every Sunday at 00:00 UTC' (handles the shapes we use)."""
    minute, hour, _, _, dow = cron.split()
    when = f"{int(hour):02d}:{int(minute):02d}\u00a0UTC"
    day = "every day" if dow == "*" else f"every {DAYS[int(dow) % 7]}"
    return f"{day} at\u00a0{when}"


def status(commit: str) -> str:
    """The plain-language bar at the top: what runs, where, and which build this is."""
    cfg = Config()
    kept = "keeps everything" if cfg.keep == 0 else f"keeps the last {cfg.keep}"
    cron = backup_cron()
    return (
        f'<span class="live"><i aria-hidden="true"></i>{html.escape(describe_cron(cron)[0].upper() + describe_cron(cron)[1:])}'
        f' &rarr; <code>{html.escape(cfg.target)}</code>, {kept}</span>'
        f'<span>next run in <b data-countdown>&hellip;</b></span>'
        f'<span class="build">v{__version__} &middot; build <a href="{REPO}/commit/{commit}">{commit[:7] or "local"}</a></span>'
    )


def command_reference() -> str:
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    rows = []
    for name, p in sub.choices.items():
        opts = [
            a for a in p._actions
            if a.option_strings and "--help" not in a.option_strings
        ]
        flags = "".join(
            f"<li><code>{html.escape(', '.join(a.option_strings))}</code>"
            f"<span>{html.escape(a.help or '')}</span></li>"
            for a in opts
        )
        rows.append(
            f'<details class="cmd"{" open" if name == "run" else ""}>'
            f"<summary><code>cab {name}</code><span>{html.escape(p.description or '')}</span></summary>"
            f'<ul class="flags">{flags}</ul></details>'
        )
    return "\n".join(rows)


def settings_table() -> str:
    out = []
    for f in dataclasses.fields(Config):
        default = f.default if f.default is not dataclasses.MISSING else f.default_factory()  # type: ignore[misc]
        if isinstance(default, tuple):
            default = ", ".join(default)
        out.append(
            f"<tr><td><code>{f.name}</code></td><td><code>CAB_{f.name.upper()}</code></td>"
            f"<td>{html.escape(str(default))}</td></tr>"
        )
    return "\n".join(out)


def public_repos(user: str) -> list[dict]:
    """The account's public repos for the terminal demo; falls back offline."""
    from cloud_auto_backup import github

    try:
        repos = github.list_repos(user, None)
    except Exception:  # offline or rate-limited: the demo still works
        return [{"name": "cloud-auto-backup", "kb": 120}]
    return [{"name": r.name, "kb": max(r.size_kb, 8)} for r in repos] or [{"name": "cloud-auto-backup", "kb": 120}]


def terminal_data() -> str:
    """Everything the in-browser terminal needs, straight from the real code."""
    os.environ["COLUMNS"] = "78"  # argparse wraps to this
    parser = cli.build_parser()
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    defaults = Config()
    files = git("ls-files").splitlines()
    payload = {
        "version": __version__,
        "help": {"cab": parser.format_help(), **{n: p.format_help() for n, p in sub.choices.items()}},
        "defaults": {
            "remote": defaults.remote, "folder": defaults.folder, "source": str(defaults.source),
            "keep": defaults.keep, "prefix": defaults.prefix, "exclude": ", ".join(defaults.exclude),
        },
        "files": len(files) or 30,
        "ls": sorted({f.split("/")[0] + ("/" if "/" in f else "") for f in files}),
        "github_user": PROJECT.github_user,
        "repos": public_repos(PROJECT.github_user) if PROJECT.github_user else [],
    }
    return json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")


ASSETS = ("style.css", "js/live.js", "js/terminal.js", "js/planner.js")


def fingerprint(rel: str) -> str:
    """'js/live.js' -> 'js/live.3f9a1c2b7e.js', named after the file's content.

    GitHub Pages lets browsers cache assets for 10 minutes, so a browser could
    pair fresh HTML with a stale stylesheet. Content-hashed names make every
    change a new URL, so HTML and assets always match.
    """
    digest = hashlib.sha256((HERE / rel).read_bytes()).hexdigest()[:10]
    stem, dot, ext = rel.rpartition(".")
    return f"{stem}.{digest}{dot}{ext}"


def build(out: Path) -> Path:
    now = datetime.now(timezone.utc)
    commit = git("rev-parse", "HEAD")
    seed = commit or hashlib.sha1(now.isoformat().encode()).hexdigest()
    urls = {rel: fingerprint(rel) for rel in ASSETS}
    page = Template((HERE / "template.html").read_text(encoding="utf-8")).substitute(
        css=urls["style.css"],
        js_live=urls["js/live.js"],
        js_terminal=urls["js/terminal.js"],
        js_planner=urls["js/planner.js"],
        version=__version__,
        status=status(commit),
        sky=sky_svg(seed),
        commands=command_reference(),
        settings=settings_table(),
        repo=REPO,
        commit=commit[:7] or "local",
        built=now.strftime("%Y-%m-%d %H:%M UTC"),
        pylines=python_lines(),
        cron=backup_cron(),
        termdata=terminal_data(),
        schedule=describe_cron(backup_cron()),
    )
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / "index.html").write_text(page, encoding="utf-8")
    for rel, url in urls.items():
        (out / url).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HERE / rel, out / url)
    (out / ".nojekyll").touch()
    return out / "index.html"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    index = build(args.out)
    print(f"built {index.relative_to(ROOT) if index.is_relative_to(ROOT) else index}")
    if args.serve:
        import functools
        import http.server

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=args.out)
        print("serving http://localhost:8000")
        http.server.ThreadingHTTPServer(("", 8000), handler).serve_forever()


if __name__ == "__main__":
    main()
