import json
import subprocess
from pathlib import Path

import pytest

from cloud_auto_backup import cli, github, mirror
from cloud_auto_backup.archive import Snapshot
from cloud_auto_backup.config import Config
from cloud_auto_backup.remote import Rclone


def repo_json(name, owner="ja", **kw):
    return {"name": name, "full_name": f"{owner}/{name}", "owner": {"login": owner},
            "clone_url": f"https://github.com/{owner}/{name}.git", "private": kw.get("private", False),
            "fork": kw.get("fork", False), "archived": kw.get("archived", False), "size": 10,
            "pushed_at": "2026-11-01T00:00:00Z"}


class FakeAPI:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def __call__(self, url, headers):
        self.calls.append((url, headers))
        i = len(self.calls) - 1
        nxt = {"Link": f'<https://api.github.com/page{i + 1}>; rel="next"'} if i + 1 < len(self.pages) else {}
        return json.dumps(self.pages[i]).encode(), nxt


def test_list_follows_pages_and_filters():
    api = FakeAPI([
        [repo_json("b"), repo_json("fork1", fork=True), repo_json("other", owner="someone")],
        [repo_json("A", private=True), repo_json("old", archived=True)],
    ])
    repos = github.list_repos("Ja", "tok", fetch=api)
    assert [r.name for r in repos] == ["A", "b", "old"]
    assert repos[0].private
    assert "/user/repos" in api.calls[0][0]
    assert api.calls[0][1]["Authorization"] == "Bearer tok"


def test_list_without_token_uses_public_endpoint():
    api = FakeAPI([[repo_json("pub")]])
    github.list_repos("ja", None, fetch=api)
    url, headers = api.calls[0]
    assert "/users/ja/repos" in url and "Authorization" not in headers


def test_forks_opt_in():
    api = FakeAPI([[repo_json("f", fork=True)]])
    assert [r.name for r in github.list_repos("ja", None, forks=True, fetch=api)] == ["f"]


def test_token_goes_in_header_env_not_url():
    env = mirror.git_env("secret-token")
    assert "secret-token" not in json.dumps({k: v for k, v in env.items() if k.startswith("GIT_CONFIG_VALUE")})
    assert env["GIT_CONFIG_VALUE_0"].startswith("Authorization: Basic ")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "GIT_CONFIG_COUNT" not in mirror.git_env(None) or mirror.git_env(None).get("GIT_CONFIG_COUNT") != "1"


@pytest.fixture
def local_repo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    run = lambda *a: subprocess.run(["git", "-C", str(src), *a], check=True, capture_output=True)
    run("init", "-q", "-b", "main")
    (src / "f.txt").write_text("hi")
    run("add", ".")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one")
    run("branch", "feature")
    run("tag", "v1")
    return src


def test_bundle_is_restorable(local_repo, tmp_path):
    snap = mirror.bundle(str(local_repo), tmp_path / "work", "src_2026-01-01_00-00.bundle")
    assert snap.zip_path.exists() and snap.checksum_path.read_text().startswith(snap.sha256)
    restored = tmp_path / "restored"
    subprocess.run(["git", "clone", "-q", str(snap.zip_path), str(restored)], check=True)
    assert (restored / "f.txt").read_text() == "hi"
    refs = subprocess.run(["git", "-C", str(restored), "ls-remote", str(snap.zip_path)],
                          capture_output=True, text=True, check=True).stdout
    assert "refs/heads/feature" in refs and "refs/tags/v1" in refs


class FakeRemote:
    def __init__(self, existing=()):
        self.files, self.calls = set(existing), []

    def __call__(self, args):
        self.calls.append(list(args))
        if args[1] == "copyto":
            self.files.add(args[3])
        elif args[1] == "lsjson":
            prefix = args[2].rstrip("/") + "/"
            return json.dumps([{"Name": f[len(prefix):], "Size": 1} for f in self.files if f.startswith(prefix)])
        elif args[1] == "deletefile":
            self.files.discard(args[2])
        return ""


def fake_bundle(fail=()):
    def bundle(url, workdir, name, token):
        if any(f in url for f in fail):
            raise mirror.MirrorError("fatal: Refusing to create empty bundle." if "empty" in url else "boom")
        workdir.mkdir(parents=True, exist_ok=True)
        out = workdir / name
        out.write_bytes(b"bundle")
        side = workdir / (name + ".sha256")
        side.write_text("x")
        return Snapshot(out, side, "x", 1, 6)
    return bundle


def test_repos_uploads_each_and_prunes_per_repo():
    old = [f"gdrive:Backups/repos/a/a_2025-01-0{i}_00-00.bundle" for i in range(1, 4)]
    remote = FakeRemote(old)
    repos = [github.Repo("a", "ja/a", "https://github.com/ja/a.git", False, False, False, 1, ""),
             github.Repo("b", "ja/b", "https://github.com/ja/b.git", True, False, False, 1, "")]
    cfg = Config(github_user="ja", keep=2)
    code = cli.cmd_repos(cfg, Rclone(runner=remote), token="t",
                         list_repos=lambda *a, **k: repos, bundle=fake_bundle())
    assert code == 0
    a_files = sorted(f for f in remote.files if "/repos/a/" in f and f.endswith(".bundle"))
    assert len(a_files) == 2 and a_files[0].endswith("2025-01-03_00-00.bundle")
    assert any("/repos/b/b_" in f for f in remote.files)


def test_empty_repo_skipped_other_failure_reported():
    repos = [github.Repo(n, f"ja/{n}", f"https://github.com/ja/{n}.git", False, False, False, 1, "")
             for n in ("empty", "broken", "ok")]
    remote = FakeRemote()
    code = cli.cmd_repos(Config(github_user="ja", keep=0), Rclone(runner=remote), token="",
                         list_repos=lambda *a, **k: repos, bundle=fake_bundle(fail=("empty", "broken")))
    assert code == 1
    assert any("/repos/ok/" in f for f in remote.files)
    assert not any("/repos/empty/" in f for f in remote.files)


def test_repos_needs_a_user():
    with pytest.raises(ValueError):
        cli.cmd_repos(Config(), Rclone(runner=FakeRemote()), token="")
