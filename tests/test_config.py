from pathlib import Path

import pytest

from cloud_auto_backup import config


def test_defaults():
    cfg = config.load(environ={}, pyproject=Path("/nonexistent"))
    assert cfg.target == "gdrive:Backups"
    assert cfg.keep == 8


def test_precedence(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.cab]\nremote = "file-remote"\nkeep = 3\nfolder = "a"\n'
    )
    cfg = config.load(
        cli={"source": str(tmp_path), "folder": "from-cli"},
        environ={"CAB_KEEP": "5"},
    )
    assert cfg.remote == "file-remote"   # pyproject
    assert cfg.keep == 5                 # env beats pyproject
    assert cfg.folder == "from-cli"      # cli beats everything
    assert cfg.target == "file-remote:from-cli"


def test_exclude_from_string():
    cfg = config.Config().merged({"exclude": ".git, node_modules ,"})
    assert cfg.exclude == (".git", "node_modules")


def test_negative_keep_rejected():
    with pytest.raises(ValueError):
        config.Config().merged({"keep": -1})


def test_unknown_env_ignored():
    assert config.from_env({"CAB_NOPE": "x", "CAB_REMOTE": "s3"}) == {"remote": "s3"}
