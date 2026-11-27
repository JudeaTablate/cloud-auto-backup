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

## Back up every repo on your account

```sh
export CAB_GITHUB_TOKEN=github_pat_...   # optional: needed for private repos
cab repos --github-user JudeaTablate --keep 8
```

Each repo is mirror-cloned (every branch, tag and ref) and packed into one
`git bundle`, uploaded with a `.sha256` to `Backups/repos/<name>/`, and pruned
to the newest `--keep`. Forks are skipped unless you pass `--forks`.

Restore one:

```sh
rclone copy gdrive:Backups/repos/my-repo/my-repo_2026-11-29_00-00.bundle .
git clone my-repo_2026-11-29_00-00.bundle my-repo
```

### Token for private repos

1. GitHub → Settings → Developer settings → Personal access tokens →
   **Fine-grained tokens** → Generate new token.
2. Repository access: **All repositories**.
3. Permissions → Repository permissions → **Contents: Read-only**
   (Metadata: Read-only is added automatically). Nothing else.
4. In this repo: Settings → Secrets and variables → Actions → New repository
   secret, name **`BACKUP_GITHUB_TOKEN`**, paste the token.

The token is only ever read from the environment and sent to git as an HTTP
header; it is never written to a URL, a file or the logs.

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
| `github_user` | `CAB_GITHUB_USER` | (none) |
| `forks`   | `CAB_FORKS`   | `false`        |

Verify a download with `sha256sum -c repo_backup_*.zip.sha256`.

## GitHub Actions

`.github/workflows/backup.yml` runs weekly. It needs one secret,
`RCLONE_CONFIG`, holding the contents of your `rclone.conf`, and optionally
`BACKUP_GITHUB_TOKEN` (see above) so `cab repos` can include private repos. Trigger it by hand
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
  github.py      list the account's repos (REST API)
  mirror.py      mirror-clone a repo into a .bundle
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
