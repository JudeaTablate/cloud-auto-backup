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

REPO = "https://github.com/JudeaTablate/cloud-auto-backup"


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
        puffs.append(f'<circle cx="{x:.1f}" cy="{base - r * 0.55:.1f}" r="{r:.1f}"/>')
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


DECKS = (
    # name, base band (y0, y1), width range, clouds per lap, seconds per lap
    ("hi", (80, 110), (70, 115), 6, 140),
    ("mid", (135, 165), (120, 175), 4, 90),
    ("lo", (190, 218), (170, 240), 3, 55),
)


def sky_svg(seed: str, width: int = 1200, height: int = 230) -> str:
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
        '<filter id="soft-lo"><feGaussianBlur stdDeviation="0.4"/></filter>',
    ]
    stars = "".join(
        f'<circle class="star" cx="{rng.uniform(0, width):.0f}" cy="{rng.uniform(6, height * 0.6):.0f}" '
        f'r="{rng.choice((0.6, 0.8, 1.1))}"/>'
        for _ in range(70)
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
        decks.append(
            f'<g class="deck deck-{name}" style="--lap:{seconds}s">'
            f'<g id="deck-{name}" filter="url(#soft-{name})">{"".join(clouds)}</g>'
            f'<use href="#deck-{name}" x="{-width}"/><use href="#deck-{name}" x="{width}"/></g>'
        )
    return (
        f'<svg class="sky" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMax slice" '
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


def metar(commit: str, now: datetime) -> str:
    """The status strip, written like an aviation weather report."""
    cfg = Config()
    tests = len(list(ROOT.glob("tests/test_*.py")))
    return (
        f"METAR CAB {now:%d%H%M}Z AUTO {commit[:7].upper() or 'LOCAL'} "
        f"V{__version__.replace('.', '')} FEW030 SCT045 BKN080 "
        f"RMK KEEP{cfg.keep:02d} PY{python_lines()}L T{tests:02d} CAVOK"
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
    }
    return json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")


def build(out: Path) -> Path:
    now = datetime.now(timezone.utc)
    commit = git("rev-parse", "HEAD")
    seed = commit or hashlib.sha1(now.isoformat().encode()).hexdigest()
    page = Template((HERE / "template.html").read_text(encoding="utf-8")).substitute(
        version=__version__,
        metar=html.escape(metar(commit, now)),
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
    shutil.copy(HERE / "style.css", out / "style.css")
    shutil.copytree(HERE / "js", out / "js")
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
