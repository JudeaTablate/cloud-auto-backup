# cloud-auto-backup

Zip a repository, write a SHA-256 next to it, and ship both to Google Drive
(or any [rclone](https://rclone.org/) remote) every Sunday. Old snapshots get
pruned so the folder doesn't grow forever.

Site: <https://judeatablate.github.io/cloud-auto-backup/>

```
00:00:04  packed   repo_backup_2026-11-29_00-00.zip  (37 files, 48.2 KB)
00:00:04  sha256   9f2c...e41a
00:00:07  uploaded -> gdrive:Backups
00:00:08  pruned   repo_backup_2026-10-04_00-00.zip
```

## Use it

```sh
pip install git+https://github.com/JudeaTablate/cloud-auto-backup
rclone config          # create a remote, e.g. "gdrive"
cab run --dry-run      # preview
cab run                # archive, upload, prune
cab list               # what's on the remote
cab prune --keep 4
cab config             # print resolved settings
```

`python backup.py` still works and means `cab run`.

## Settings

Lowest to highest priority: defaults, `[tool.cab]` in `pyproject.toml`,
`CAB_*` environment variables, command-line flags.

| key       | env           | default        |
|-----------|---------------|----------------|
| `remote`  | `CAB_REMOTE`  | `gdrive`       |
| `folder`  | `CAB_FOLDER`  | `Backups`      |
| `source`  | `CAB_SOURCE`  | `.`            |
| `keep`    | `CAB_KEEP`    | `8` (0 = all)  |
| `prefix`  | `CAB_PREFIX`  | `repo_backup`  |
| `exclude` | `CAB_EXCLUDE` | `.git`, caches, `*.zip` |
| `dry_run` | `CAB_DRY_RUN` | `false`        |

Verify a download with `sha256sum -c repo_backup_*.zip.sha256`.

## GitHub Actions

`.github/workflows/backup.yml` runs weekly. It needs one secret,
`RCLONE_CONFIG`, holding the contents of your `rclone.conf`. Trigger it by hand
from the Actions tab, with an optional dry run.

`.github/workflows/pages.yml` builds the site with `python site/build.py` and
deploys it to GitHub Pages (Settings -> Pages -> Source: GitHub Actions).

## Layout

```
src/cloud_auto_backup/
  config.py      settings + precedence
  archive.py     zip, excludes, sha256 sidecar
  remote.py      rclone wrapper (swappable runner for tests)
  retention.py   which snapshots to drop
  cli.py         `cab` command
site/build.py    static site generator (stdlib only)
tests/           pytest, no network
```

## Develop

```sh
pip install -e ".[dev]"
pytest
python site/build.py --serve
```
