import json

from cloud_auto_backup import cli
from cloud_auto_backup.config import Config
from cloud_auto_backup.remote import Rclone


class FakeRemote:
    def __init__(self, names=()):
        self.calls = []
        self.names = list(names)

    def __call__(self, args):
        self.calls.append(list(args))
        if args[1] == "lsjson":
            return json.dumps([{"Name": n, "Size": 1, "ModTime": ""} for n in self.names])
        return ""


def test_run_uploads_zip_and_checksum(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    fake = FakeRemote()
    cfg = Config(source=tmp_path, keep=0, prefix="t")
    assert cli.cmd_run(cfg, Rclone(runner=fake)) == 0
    uploaded = [c[3] for c in fake.calls if c[1] == "copyto"]
    assert len(uploaded) == 2
    assert uploaded[0].startswith("gdrive:Backups/t_") and uploaded[0].endswith(".zip")
    assert uploaded[1].endswith(".zip.sha256")


def test_dry_run_flag_reaches_rclone(tmp_path):
    fake = FakeRemote(["t_2026-01-01_00-00.zip", "t_2026-01-02_00-00.zip"])
    cfg = Config(source=tmp_path, keep=1, prefix="t", dry_run=True)
    cli.cmd_prune(cfg, Rclone(runner=fake, dry_run=True))
    deletes = [c for c in fake.calls if c[1] == "deletefile"]
    assert deletes == [["rclone", "deletefile", "gdrive:Backups/t_2026-01-01_00-00.zip", "--dry-run"]]


def test_missing_rclone_is_a_clean_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "")
    assert cli.main(["list", "--source", str(tmp_path)]) == 1


def test_human_sizes():
    assert cli.human(512) == "512 B"
    assert cli.human(2048) == "2.0 KB"
