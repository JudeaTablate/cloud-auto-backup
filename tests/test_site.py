"""Smoke tests for site/build.py: it builds, and what it bakes in is right."""

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def site():
    spec = importlib.util.spec_from_file_location("site_build", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def page(site, tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    index = site.build(out)
    return out, index.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "cron, text",
    [
        ("0 0 * * 0", "every Sunday at 00:00 UTC"),
        ("30 18 * * 3", "every Wednesday at 18:30 UTC"),
        ("0 6 * * *", "every day at 06:00 UTC"),
    ],
)
def test_describe_cron(site, cron, text):
    assert site.describe_cron(cron) == text


def test_cron_matches_workflow(site):
    workflow = (ROOT / ".github" / "workflows" / "backup.yml").read_text()
    assert f'"{site.backup_cron()}"' in workflow


def test_sky_is_seeded_and_loops(site):
    a, b = site.sky_svg("abc"), site.sky_svg("abc")
    assert a == b != site.sky_svg("xyz")
    for name, *_ in site.DECKS:
        assert f'href="#deck-{name}" x="-1200"' in a and f'href="#deck-{name}" x="1200"' in a


def test_no_template_placeholders_left(page):
    _, html = page
    assert not re.search(r"\$[a-z_]+", html.split('id="cab-data"')[0])


def test_assets_copied(page):
    out, _ = page
    for rel in ["style.css", "js/live.js", "js/terminal.js", "js/planner.js", ".nojekyll"]:
        assert (out / rel).exists(), rel


def test_terminal_data_matches_cli(page):
    from cloud_auto_backup import __version__
    from cloud_auto_backup.config import Config

    _, html = page
    raw = re.search(r'<script type="application/json" id="cab-data">(.*?)</script>', html, re.S).group(1)
    data = json.loads(raw)
    assert data["version"] == __version__
    assert set(data["help"]) == {"cab", "run", "list", "prune", "config"}
    assert data["defaults"]["keep"] == Config().keep
    assert "usage: cab" in data["help"]["cab"]


def test_every_section_has_a_tape_mark(page):
    _, html = page
    sections = set(re.findall(r'<section id="([^"]+)"', html))
    marks = set(re.findall(r'data-fl="([^"]+)"', html))
    assert sections == marks
