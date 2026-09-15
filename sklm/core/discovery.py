"""Skill discovery — find the skills a source contains.

Discovery runs against the :class:`~sklm.core.fetch.SourceFiles` interface, so
it works identically for an HTTP-backed GitHub repository and a directory on
disk.  Containers are the repository root, ``skills/``, ``.agents/skills/``,
and ``<dir_name>/skills`` for every agent defined in ``agents.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from sklm.core.fetch import SourceFiles


SKILL_FILENAME = "skill.md"
SKIP_DIRS = frozenset({"node_modules", ".git", "dist", "build", "__pycache__"})
MAX_DEPTH = 3
BASE_CONTAINERS = ("", "skills", ".agents/skills")

_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", re.DOTALL)
_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    """Normalize a human-readable skill name into a kebab-case slug."""
    return _SLUG_STRIP_RE.sub("-", value.strip().lower()).strip("-")


def _is_valid_name(value: str) -> bool:
    """Return True when *value* satisfies the ``Resource.name`` validator."""
    return bool(value) and value.replace("-", "").isalnum()


@dataclass
class DiscoveredSkill:
    """A skill found inside a source.

    Attributes
    ----------
    name:
        The name Sklm stores and links the skill under. This is the skill's
        directory name, or a slugified frontmatter/repository name for a
        skill whose ``SKILL.md`` sits at the source root.
    directory:
        Repo-relative directory holding the skill (``""`` for the root).
    skill_md:
        Repo-relative path to the ``SKILL.md``.
    paths:
        Repo-relative paths of every file belonging to the skill.
    frontmatter_name, description:
        Values parsed from the ``SKILL.md`` frontmatter, when present.
    """

    name: str
    directory: str
    skill_md: str
    paths: list[str] = field(default_factory=list)
    frontmatter_name: Optional[str] = None
    description: Optional[str] = None

    @property
    def aliases(self) -> list[str]:
        """Names that should match this skill in a ``--skill`` request."""
        names = {self.name.lower(), slugify(self.name)}
        if self.frontmatter_name:
            names.add(slugify(self.frontmatter_name))
        return sorted(n for n in names if n)


def parse_frontmatter(text: str) -> dict:
    """Return the YAML frontmatter of a ``SKILL.md``, or an empty dict."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def agent_containers() -> list[str]:
    """Return ``<dir_name>/<skills_subdir>`` for every agent in agents.yaml."""
    try:
        from sklm.agents.registry import AgentRegistry

        registry = AgentRegistry()
    except Exception:
        return []

    containers: list[str] = []
    for agent_id in registry.get_agent_ids():
        config = registry.get_agent_config(agent_id) or {}
        dir_name = config.get("dir_name")
        if not dir_name:
            continue
        subdir = config.get("skills_subdir", "skills")
        containers.append(f"{dir_name}/{subdir}")
    return containers


def containers() -> list[str]:
    """Return the full, de-duplicated list of container directories."""
    ordered: list[str] = []
    for candidate in list(BASE_CONTAINERS) + agent_containers():
        normalized = candidate.strip("/")
        if normalized not in ordered:
            ordered.append(normalized)
    return ordered


def _has_skipped_segment(path: str) -> bool:
    return any(segment in SKIP_DIRS for segment in path.split("/"))


def _container_depth(directory: str, container: str) -> Optional[int]:
    """Return how many levels *directory* sits below *container*, or None."""
    dir_segments = [s for s in directory.split("/") if s]
    if not container:
        return len(dir_segments)
    container_segments = container.split("/")
    if dir_segments[: len(container_segments)] != container_segments:
        return None
    return len(dir_segments) - len(container_segments)


def _within_any_container(directory: str, container_list: list[str]) -> bool:
    for container in container_list:
        depth = _container_depth(directory, container)
        if depth is not None and depth <= MAX_DEPTH:
            return True
    return False


def discover_skills(
    files: SourceFiles,
    subpath: Optional[str] = None,
    default_name: Optional[str] = None,
) -> list[DiscoveredSkill]:
    """Return every skill contained in *files*.

    Parameters
    ----------
    files:
        The source to read.
    subpath:
        Restrict discovery to this subtree. The subpath becomes the root for
        depth purposes, so a skill nested two levels under it is still found.
    default_name:
        Fallback name for a skill whose ``SKILL.md`` is at the source root,
        used when the frontmatter has no ``name``.
    """
    all_paths = files.list_paths()
    prefix = subpath.strip("/") + "/" if subpath and subpath.strip("/") else ""

    if prefix:
        visible = [p for p in all_paths if p.startswith(prefix)]
    else:
        visible = list(all_paths)

    container_list = containers()

    # Collect candidate SKILL.md files, keyed by their original directory.
    candidates: dict[str, str] = {}
    for path in visible:
        relative = path[len(prefix):] if prefix else path
        if Path(relative).name.lower() != SKILL_FILENAME:
            continue
        if _has_skipped_segment(relative):
            continue
        relative_dir = str(Path(relative).parent.as_posix())
        if relative_dir == ".":
            relative_dir = ""
        if not _within_any_container(relative_dir, container_list):
            continue
        original_dir = str(Path(path).parent.as_posix())
        if original_dir == ".":
            original_dir = ""
        candidates.setdefault(original_dir, path)

    # Shallower SKILL.md shadows anything nested beneath it.
    accepted: dict[str, str] = {}
    candidate_dirs = set(candidates)
    for directory, skill_md in candidates.items():
        parts = [s for s in directory.split("/") if s]
        ancestors = {"/".join(parts[: i]) for i in range(len(parts))}
        if ancestors & candidate_dirs:
            continue
        accepted[directory] = skill_md

    results: list[DiscoveredSkill] = []
    for directory, skill_md in accepted.items():
        try:
            text = files.read_bytes(skill_md).decode("utf-8", errors="replace")
        except Exception:
            text = ""
        meta = parse_frontmatter(text)
        frontmatter_name = meta.get("name") if isinstance(meta.get("name"), str) else None
        description = meta.get("description") if isinstance(meta.get("description"), str) else None

        if directory:
            raw_name = directory.split("/")[-1]
            # A skill is named after its directory. Directories that are not
            # already kebab-case (e.g. "foo_bar") are slugified so the name
            # satisfies the Resource.name validator.
            name = raw_name if _is_valid_name(raw_name) else slugify(raw_name)
        else:
            name = (
                slugify(frontmatter_name)
                if frontmatter_name
                else (slugify(default_name) if default_name else "skill")
            )

        if directory:
            file_prefix = f"{directory}/"
            member_paths = [p for p in all_paths if p.startswith(file_prefix)]
        else:
            member_paths = list(all_paths)

        results.append(
            DiscoveredSkill(
                name=name,
                directory=directory,
                skill_md=skill_md,
                paths=member_paths,
                frontmatter_name=frontmatter_name,
                description=description,
            )
        )

    return sorted(results, key=lambda s: s.name)


def select_skills(
    skills: list[DiscoveredSkill],
    requested: Optional[list[str]] = None,
    all_: bool = False,
) -> list[DiscoveredSkill]:
    """Filter *skills* by an explicit request.

    Raises
    ------
    ValueError
        If *requested* names do not match any discovered skill.
    """
    if all_:
        return list(skills)
    if not requested:
        return list(skills)

    selected: list[DiscoveredSkill] = []
    matched: set[str] = set()
    for wanted in requested:
        wanted_slug = slugify(wanted)
        hits = [
            s
            for s in skills
            if wanted_slug in s.aliases or s.name.lower() == wanted.lower()
        ]
        if not hits:
            available = ", ".join(sorted(s.name for s in skills)) or "none"
            raise ValueError(
                f"No skill named '{wanted}' in this source. Available skills: {available}"
            )
        for hit in hits:
            if hit.name not in matched:
                matched.add(hit.name)
                selected.append(hit)
    return selected
