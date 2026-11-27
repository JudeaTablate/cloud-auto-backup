from cloud_auto_backup import retention

NAMES = [
    "b_2026-01-01_00-00.zip", "b_2026-01-01_00-00.zip.sha256",
    "b_2026-01-08_00-00.zip", "b_2026-01-08_00-00.zip.sha256",
    "b_2026-01-15_00-00.zip",
    "notes.txt", "other_2020-01-01_00-00.zip",
]


def test_snapshots_newest_first():
    assert retention.snapshots(NAMES, "b") == [
        "b_2026-01-15_00-00.zip", "b_2026-01-08_00-00.zip", "b_2026-01-01_00-00.zip",
    ]


def test_prune_drops_oldest_with_sidecar():
    assert retention.plan_prune(NAMES, "b", keep=2) == [
        "b_2026-01-01_00-00.zip", "b_2026-01-01_00-00.zip.sha256",
    ]


def test_keep_zero_keeps_everything():
    assert retention.plan_prune(NAMES, "b", keep=0) == []
