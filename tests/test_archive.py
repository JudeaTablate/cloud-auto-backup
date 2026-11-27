import hashlib
import zipfile
from datetime import datetime

import pytest

from cloud_auto_backup import archive


@pytest.fixture
def tree(tmp_path):
    src = tmp_path / "src"
    (src / ".git").mkdir(parents=True)
    (src / ".git" / "HEAD").write_text("ref")
    (src / "pkg" / "__pycache__").mkdir(parents=True)
    (src / "pkg" / "__pycache__" / "x.pyc").write_bytes(b"\0")
    (src / "pkg" / "mod.py").write_text("print('hi')")
    (src / "README.md").write_text("# hi")
    (src / "old.zip").write_bytes(b"zip")
    return src


def test_name_is_sortable():
    assert archive.archive_name("b", datetime(2026, 2, 5, 9, 3)) == "b_2026-02-05_09-03.zip"


def test_build_skips_excluded(tree, tmp_path):
    snap = archive.build(tree, tmp_path / "out", "b.zip", [".git", "__pycache__", "*.zip"])
    with zipfile.ZipFile(snap.zip_path) as zf:
        assert sorted(zf.namelist()) == ["README.md", "pkg/mod.py"]
    assert snap.files == 2


def test_checksum_sidecar(tree, tmp_path):
    snap = archive.build(tree, tmp_path / "out", "b.zip", [])
    expected = hashlib.sha256(snap.zip_path.read_bytes()).hexdigest()
    assert snap.sha256 == expected
    assert snap.checksum_path.read_text() == f"{expected}  b.zip\n"


def test_refuses_to_write_inside_source(tree):
    with pytest.raises(ValueError):
        archive.build(tree, tree / "out", "b.zip", [])
