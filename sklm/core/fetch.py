"""Fetch layer — resolve a parsed source into readable skill files.

Two transports implement the same :class:`SourceFiles` interface:

* :class:`HttpGithubSource` reads a public GitHub repository through the
  GitHub Trees API and ``raw.githubusercontent.com``, so no ``git`` binary is
  required.
* :class:`DiskSource` reads a local directory, or a repository that the git
  fallback cloned into the cache.

Discovery is written once against the interface, so it does not care which
transport produced the bytes.
"""

from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Mapping, Optional

from sklm.core.sources import ParsedSource

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"
HTTP_TIMEOUT = 30

#: Signature of the injectable HTTP transport used by :class:`HttpGithubSource`.
HttpGet = Callable[[str, Mapping[str, str]], "tuple[int, bytes]"]


class SourceFetchError(Exception):
    """Raised when a source cannot be fetched."""


class GitUnavailableError(SourceFetchError):
    """Raised when a source needs git but no ``git`` executable is available."""


class HttpSourceUnavailable(SourceFetchError):
    """Raised when the HTTP path cannot serve a source.

    Callers treat this as a signal to fall back to the git transport rather
    than as a user-facing failure.
    """


def require_git() -> str:
    """Return the path to the ``git`` executable, or raise.

    Raises
    ------
    GitUnavailableError
        If no ``git`` executable can be found on PATH.
    """
    git = shutil.which("git")
    if not git:
        raise GitUnavailableError(
            "git is required to install from this source, but no 'git' "
            "executable was found on PATH. Install git from "
            "https://git-scm.com/downloads and try again, or use a public "
            "GitHub source such as 'owner/repo', which Sklm downloads over "
            "HTTPS without git."
        )
    return git


def _github_token() -> Optional[str]:
    """Return an explicit GitHub token from the environment, if any."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or None


def _default_http_get(url: str, headers: Mapping[str, str]) -> "tuple[int, bytes]":
    """Perform an HTTP GET with the standard library."""
    request = urllib.request.Request(url, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class SourceFiles(ABC):
    """Read-only access to the files of a source repository."""

    @abstractmethod
    def list_paths(self) -> list[str]:
        """Return every file path in the source, repo-relative, forward slashes."""

    @abstractmethod
    def read_bytes(self, path: str) -> bytes:
        """Return the contents of *path* (repo-relative)."""

    def materialize(self, dest: Path, skill_dir: str, paths: list[str]) -> None:
        """Write *paths* into *dest*, stripping the *skill_dir* prefix.

        Parameters
        ----------
        dest:
            Directory that becomes the installed skill.
        skill_dir:
            Repo-relative directory holding the skill (``""`` for repo root).
        paths:
            Repo-relative file paths belonging to the skill.
        """
        prefix = f"{skill_dir}/" if skill_dir else ""
        for path in paths:
            relative = path[len(prefix):] if prefix and path.startswith(prefix) else path
            if not relative:
                continue
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.read_bytes(path))


class DiskSource(SourceFiles):
    """A source backed by a directory on disk (local path or git cache)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def list_paths(self) -> list[str]:
        paths: list[str] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            base = Path(dirpath)
            for filename in filenames:
                paths.append((base / filename).relative_to(self.root).as_posix())
        return sorted(paths)

    def read_bytes(self, path: str) -> bytes:
        return (self.root / path).read_bytes()


class HttpGithubSource(SourceFiles):
    """A public GitHub repository read over HTTPS, without git."""

    def __init__(
        self,
        owner: str,
        repo: str,
        ref: Optional[str] = None,
        *,
        token: Optional[str] = None,
        http_get: Optional[HttpGet] = None,
    ) -> None:
        self.owner = owner
        self.repo = repo
        self.ref = ref or "HEAD"
        self._token = token if token is not None else _github_token()
        self._http_get: HttpGet = http_get or _default_http_get
        self._paths: Optional[list[str]] = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "sklm-cli",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _load_tree(self) -> list[str]:
        url = (
            f"{GITHUB_API}/repos/{self.owner}/{self.repo}/git/trees/"
            f"{urllib.parse.quote(self.ref, safe='')}?recursive=1"
        )
        try:
            status, body = self._http_get(url, self._headers())
        except Exception as exc:  # network failure, DNS, timeout, ...
            raise HttpSourceUnavailable(
                f"Could not reach the GitHub API for {self.owner}/{self.repo}: {exc}"
            ) from exc

        if status in (403, 429):
            raise HttpSourceUnavailable(
                f"GitHub API rate limit reached for {self.owner}/{self.repo}"
            )
        if status in (401, 404):
            raise HttpSourceUnavailable(
                f"GitHub repository {self.owner}/{self.repo} is not publicly readable"
            )
        if status != 200:
            raise HttpSourceUnavailable(
                f"GitHub API returned HTTP {status} for {self.owner}/{self.repo}"
            )

        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise HttpSourceUnavailable(
                f"GitHub API returned an unreadable tree for {self.owner}/{self.repo}"
            ) from exc

        if data.get("truncated"):
            raise HttpSourceUnavailable(
                f"GitHub tree listing for {self.owner}/{self.repo} was truncated"
            )
        return [
            entry["path"]
            for entry in data.get("tree", [])
            if entry.get("type") == "blob" and entry.get("path")
        ]

    def list_paths(self) -> list[str]:
        if self._paths is None:
            self._paths = self._load_tree()
        return self._paths

    def read_bytes(self, path: str) -> bytes:
        quoted = urllib.parse.quote(path)
        url = (
            f"{GITHUB_RAW}/{self.owner}/{self.repo}/"
            f"{urllib.parse.quote(self.ref, safe='')}/{quoted}"
        )
        headers = {"User-Agent": "sklm-cli"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        status, body = self._http_get(url, headers)
        if status != 200:
            raise SourceFetchError(
                f"Failed to download '{path}' from {self.owner}/{self.repo} (HTTP {status})"
            )
        return body


def _git_source(parsed: ParsedSource) -> DiskSource:
    """Clone (or update) a git source into the cache and wrap it."""
    from sklm.core.registry import RegistryManager
    from sklm.store import url_to_repo_slug

    require_git()
    registry = RegistryManager()
    slug = url_to_repo_slug(parsed.url)
    cache_path = registry.clone_or_fetch(parsed.url, slug, ref=parsed.ref or "HEAD")
    return DiskSource(cache_path)


def resolve_source(
    parsed: ParsedSource,
    *,
    http_get: Optional[HttpGet] = None,
    token: Optional[str] = None,
) -> SourceFiles:
    """Return a :class:`SourceFiles` for *parsed*.

    Public GitHub sources use the HTTP transport. Everything else — private
    repositories, non-GitHub hosts, SSH URLs, and generic git remotes — uses
    the git fallback. When the HTTP transport cannot serve a source it falls
    back to git as well.

    Raises
    ------
    SourceFetchError
        If the source cannot be resolved by any transport.
    """
    if parsed.is_local:
        root = Path(parsed.url)
        if not root.is_dir():
            raise SourceFetchError(f"Local source '{parsed.url}' is not a directory")
        return DiskSource(root)

    if parsed.is_github and parsed.owner and parsed.repo:
        source = HttpGithubSource(
            parsed.owner, parsed.repo, parsed.ref, token=token, http_get=http_get
        )
        try:
            # The tree is loaded lazily, so probe it here to decide whether the
            # HTTP transport can serve this source before committing to it.
            source.list_paths()
        except HttpSourceUnavailable:
            pass
        else:
            return source

    return _git_source(parsed)
