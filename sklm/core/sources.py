"""Source parsing — turn a user-supplied source string into a structured form.

A *source* is anything that identifies where skills come from: a GitHub
shorthand (``owner/repo``), a repository URL, a direct path inside a
repository, or a local filesystem path.  This module performs no I/O — it only
classifies and normalizes the string so the fetch layer knows what to do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class SourceParseError(ValueError):
    """Raised when a string cannot be interpreted as a source."""


@dataclass
class ParsedSource:
    """A normalized description of where skills should be fetched from.

    Attributes
    ----------
    type:
        ``"github"`` for a public GitHub repository, ``"local"`` for a
        filesystem path, ``"git"`` for any other git remote.
    url:
        The clone URL for git sources, or the resolved path for local sources.
    ref:
        Git ref (branch, tag, or commit) to check out, when one was supplied.
    subpath:
        Path within the repository to restrict discovery to.
    skill_filter:
        Skill name supplied inline (``owner/repo@skill``), used as the
        default selection when no explicit flag is given.
    owner, repo:
        Populated for GitHub sources so the HTTP layer can address the API.
    """

    type: str
    url: str
    ref: Optional[str] = None
    subpath: Optional[str] = None
    skill_filter: Optional[str] = None
    owner: Optional[str] = None
    repo: Optional[str] = None

    @property
    def is_github(self) -> bool:
        return self.type == "github"

    @property
    def is_local(self) -> bool:
        return self.type == "local"

    @property
    def display(self) -> str:
        """A short human-readable form used in messages and metadata."""
        if self.is_github and self.owner and self.repo:
            return f"{self.owner}/{self.repo}"
        return self.url


# ─── Patterns ────────────────────────────────────────────────────────────────

_GITHUB_TREE_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)"
    r"(?:\.git)?/tree/(?P<ref>[^/]+)(?:/(?P<path>.+?))?/?$"
)
_GITHUB_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)"
    r"(?:\.git)?/?$"
)
_SHORTHAND_AT_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/@]+?)@(?P<skill>.+)$"
)
_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[^/]+)/(?P<repo>[^/@]+?)(?:\.git)?(?:/(?P<path>.+?))?/?$"
)

_DRIVE_RE = re.compile(r"^[a-zA-Z]:[/\\]")
_SCHEME_RE = re.compile(r"^(?:https?|ssh|git)://", re.IGNORECASE)
_SSH_SHORTHAND_RE = re.compile(r"^git@[^:]+:.+")


def is_local_path(value: str) -> bool:
    """Return True when *value* denotes a filesystem path."""
    if not value:
        return False
    if value in (".", ".."):
        return True
    if value.startswith("./") or value.startswith("../"):
        return True
    if value.startswith(".\\") or value.startswith("..\\"):
        return True
    if _DRIVE_RE.match(value):
        return True
    if value.startswith("/") or value.startswith("\\"):
        return True
    return False


def looks_like_source(value: str) -> bool:
    """Return True when *value* should be treated as a source.

    This is the predicate that disambiguates ``sklm add <source>`` from
    ``sklm add <name>``.  Resource names are kebab-case and therefore never
    contain a slash, a URL scheme, an SSH prefix, or a path prefix, so the
    two forms cannot collide.
    """
    if not value:
        return False
    value = value.strip()
    if not value:
        return False
    if is_local_path(value):
        return True
    if _SCHEME_RE.match(value) or _SSH_SHORTHAND_RE.match(value):
        return True
    if ":" in value:
        # e.g. "my-registry:my-skill" — a scoped resource name, not a source.
        return False
    if "/" in value:
        return True
    return False


def sanitize_subpath(subpath: str) -> str:
    """Normalize a subpath and reject traversal segments.

    Raises
    ------
    SourceParseError
        If the subpath contains a ``..`` segment or is absolute.
    """
    normalized = subpath.replace("\\", "/").strip("/")
    if not normalized:
        return ""
    if normalized.startswith("/") or _DRIVE_RE.match(normalized):
        raise SourceParseError(f"Unsafe subpath '{subpath}': absolute paths are not allowed")
    for segment in normalized.split("/"):
        if segment == "..":
            raise SourceParseError(
                f"Unsafe subpath '{subpath}': path traversal segments are not allowed"
            )
    return normalized


def _split_fragment(value: str) -> tuple[str, Optional[str], Optional[str]]:
    """Split a trailing ``#<ref>@<skill>`` fragment off *value*."""
    hash_index = value.find("#")
    if hash_index < 0:
        return value, None, None
    body = value[:hash_index]
    fragment = value[hash_index + 1:]
    if not fragment:
        return value, None, None
    at_index = fragment.find("@")
    if at_index < 0:
        return body, fragment, None
    ref = fragment[:at_index]
    skill = fragment[at_index + 1:]
    return body, (ref or None), (skill or None)


def _github(owner: str, repo: str, ref: Optional[str], subpath: Optional[str],
            skill_filter: Optional[str]) -> ParsedSource:
    return ParsedSource(
        type="github",
        url=f"https://github.com/{owner}/{repo}.git",
        ref=ref,
        subpath=subpath,
        skill_filter=skill_filter,
        owner=owner,
        repo=repo,
    )


def parse_source(value: str) -> ParsedSource:
    """Classify *value* into a :class:`ParsedSource`.

    Supported forms: GitHub shorthand (``owner/repo``), GitHub shorthand with
    a subpath or ``@skill`` filter, full GitHub URLs, GitHub tree URLs
    (``…/tree/<ref>/<path>``), a ``#<ref>@<skill>`` fragment on any git-like
    source, local filesystem paths, and any other git remote URL.

    Raises
    ------
    SourceParseError
        If *value* is empty or is a bare word that is not a source.
    """
    if value is None or not str(value).strip():
        raise SourceParseError("Source must not be empty")

    raw = str(value).strip()

    if is_local_path(raw):
        return ParsedSource(type="local", url=str(Path(raw).expanduser().resolve()))

    body, ref, skill_filter = _split_fragment(raw)
    if body.startswith("github:"):
        body = body[len("github:"):]

    match = _GITHUB_TREE_RE.match(body)
    if match:
        subpath = match.group("path")
        return _github(
            match.group("owner"),
            match.group("repo"),
            match.group("ref") or ref,
            sanitize_subpath(subpath) if subpath else None,
            skill_filter,
        )

    match = _GITHUB_REPO_RE.match(body)
    if match:
        return _github(
            match.group("owner"),
            match.group("repo"),
            ref,
            None,
            skill_filter,
        )

    if _SCHEME_RE.match(body) or _SSH_SHORTHAND_RE.match(body):
        return ParsedSource(type="git", url=body, ref=ref, skill_filter=skill_filter)

    match = _SHORTHAND_AT_RE.match(body)
    if match:
        return _github(
            match.group("owner"),
            match.group("repo"),
            ref,
            None,
            skill_filter or match.group("skill"),
        )

    match = _SHORTHAND_RE.match(body)
    if match:
        subpath = match.group("path")
        return _github(
            match.group("owner"),
            match.group("repo"),
            ref,
            sanitize_subpath(subpath) if subpath else None,
            skill_filter,
        )

    raise SourceParseError(
        f"'{value}' is not a recognized source. Use 'owner/repo', a repository "
        "URL, or a local path."
    )
