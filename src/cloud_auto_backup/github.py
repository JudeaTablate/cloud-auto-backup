"""List a GitHub account's repositories with nothing but the standard library.

With a token (``CAB_GITHUB_TOKEN``), ``/user/repos`` returns every repo the
token can read, private ones included, filtered to the ones the account
owns. Without a token, ``/users/<name>/repos`` returns public repos only.
"""

from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterator

API = "https://api.github.com"
Fetch = Callable[[str, dict[str, str]], tuple[bytes, dict[str, str]]]


class GitHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class Repo:
    name: str
    full_name: str
    clone_url: str
    private: bool
    fork: bool
    archived: bool
    size_kb: int
    pushed_at: str


def _urllib_fetch(url: str, headers: dict[str, str]) -> tuple[bytes, dict[str, str]]:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:200]
        if exc.code == 401:
            raise GitHubError("GitHub rejected the token (401). Is CAB_GITHUB_TOKEN valid and unexpired?") from exc
        raise GitHubError(f"GitHub API {exc.code} for {url.split('?')[0]}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise GitHubError(f"could not reach GitHub: {exc.reason}") from exc


def _next_link(headers: dict[str, str]) -> str | None:
    link = next((v for k, v in headers.items() if k.lower() == "link"), "")
    match = re.search(r'<([^>]+)>;\s*rel="next"', link)
    return match.group(1) if match else None


def list_repos(
    owner: str,
    token: str | None = None,
    *,
    forks: bool = False,
    archived: bool = True,
    fetch: Fetch = _urllib_fetch,
) -> list[Repo]:
    """Every repo ``owner`` owns, sorted by name, following pagination."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "cloud-auto-backup"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        url: str | None = f"{API}/user/repos?affiliation=owner&per_page=100"
    else:
        url = f"{API}/users/{owner}/repos?type=owner&per_page=100"

    repos: list[Repo] = []
    while url:
        body, resp_headers = fetch(url, headers)
        for item in json.loads(body):
            if item["owner"]["login"].lower() != owner.lower():
                continue
            if item.get("fork") and not forks:
                continue
            if item.get("archived") and not archived:
                continue
            repos.append(Repo(
                name=item["name"],
                full_name=item["full_name"],
                clone_url=item["clone_url"],
                private=bool(item.get("private")),
                fork=bool(item.get("fork")),
                archived=bool(item.get("archived")),
                size_kb=int(item.get("size", 0)),
                pushed_at=item.get("pushed_at") or "",
            ))
        url = _next_link(resp_headers)
    return sorted(repos, key=lambda r: r.name.lower())


def iter_names(repos: list[Repo]) -> Iterator[str]:
    for r in repos:
        yield f"{r.full_name}{' (private)' if r.private else ''}"
