"""Registry management — discover resources from named sources."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Optional

import yaml

from sklm.models import RegistrySource, RegistryType, Resource, ResourceKind


# Filesystem-safe pattern: only allow alphanumeric, hyphens, underscores
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


REGISTRIES_PATH = Path.home() / ".sklm" / "registries.yaml"
REGISTRY_CACHE = Path.home() / ".sklm" / "cache"


class RegistryManager:
    """Manages registry sources and resource discovery."""

    def __init__(self) -> None:
        self.registries_path = REGISTRIES_PATH
        self.cache_dir = REGISTRY_CACHE
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_sources(self) -> dict[str, RegistrySource]:
        if not self.registries_path.exists():
            return {}
        with open(self.registries_path) as f:
            data = yaml.safe_load(f)
        if not data or "registries" not in data:
            return {}
        return {name: RegistrySource(**src) for name, src in data["registries"].items()}

    def _save_sources(self, sources: dict[str, RegistrySource]) -> None:
        data = {"registries": {name: src.model_dump(mode="json") for name, src in sources.items()}}
        self.registries_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registries_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False)

    def add_source(self, source: RegistrySource) -> None:
        sources = self._load_sources()
        if source.name in sources:
            raise FileExistsError(f"Registry '{source.name}' already exists")
        if source.type == RegistryType.git:
            self.clone_or_fetch(source.url_or_path, source.name)
        sources[source.name] = source
        self._save_sources(sources)

    def list_sources(self) -> dict[str, RegistrySource]:
        return self._load_sources()

    def clone_or_fetch(self, url: str, name: str, ref: str = "HEAD") -> Path:
        """Clone or update a git repository into the cache directory.

        Args:
            url: Git remote URL to clone/fetch.
            name: Local cache directory name (e.g. registry name or repo slug).
            ref: Git ref to checkout after clone/fetch (default: HEAD).

        Returns:
            Path to the cached repository root.

        Raises:
            ValueError: If the git operation fails, the URL is not a valid git repo,
                or the operation times out, or the name contains unsafe characters.
        """
        if not _SAFE_NAME_RE.match(name):
            raise ValueError(
                f"Unsafe registry name '{name}': only letters, numbers, hyphens, "
                "and underscores are allowed."
            )
        repo_cache = self.cache_dir / name
        if repo_cache.exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(repo_cache), "pull", "--ff-only"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                raise ValueError(
                    f"Timed out updating cached repo '{name}' from {url}"
                )
            if result.returncode != 0:
                raise ValueError(
                    f"Failed to update cached repo '{name}' from {url}: {result.stderr.strip()}"
                )
            if ref != "HEAD":
                result = subprocess.run(
                    ["git", "-C", str(repo_cache), "checkout", "--", ref],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise ValueError(
                        f"Failed to checkout ref '{ref}' in '{name}': {result.stderr.strip()}"
                    )
        else:
            try:
                result = subprocess.run(
                    ["git", "clone", "--depth", "1", "--single-branch", "--", url, str(repo_cache)],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except subprocess.TimeoutExpired:
                raise ValueError(
                    f"Timed out cloning '{url}'"
                )
            if result.returncode != 0:
                raise ValueError(
                    f"Failed to clone '{url}': {result.stderr.strip()}"
                )
            if ref != "HEAD":
                result = subprocess.run(
                    ["git", "-C", str(repo_cache), "checkout", "--", ref],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise ValueError(
                        f"Failed to checkout ref '{ref}' in '{name}': {result.stderr.strip()}"
                    )
        return repo_cache

    def _scan_directory(self, path: Path) -> list[Resource]:
        resources: list[Resource] = []
        if not path.is_dir():
            return resources

        def _collect(dir_path: Path) -> None:
            for entry in sorted(dir_path.iterdir()):
                if entry.is_dir() and (entry / "SKILL.md").exists():
                    resources.append(
                        Resource(
                            name=entry.name,
                            kind=ResourceKind.skill,
                            source=str(entry),
                            path=entry.resolve(),
                        )
                    )

        _collect(path)
        skills_subdir = path / "skills"
        if skills_subdir.is_dir():
            _collect(skills_subdir)

        return resources

    def search(
        self,
        query: str,
        registry_filter: Optional[str] = None,
        type_filter: Optional[ResourceKind] = None,
    ) -> list[tuple[str, Resource]]:
        results: list[tuple[str, Resource]] = []
        sources = self._load_sources()
        query_lower = query.lower()
        for name, source in sources.items():
            if registry_filter and name != registry_filter:
                continue
            registry_resources = self._resources_from_source(source)
            for resource in registry_resources:
                if type_filter and resource.kind != type_filter:
                    continue
                if query_lower in resource.name.lower() or query_lower in resource.source.lower():
                    results.append((name, resource))
        return results

    def _resources_from_source(self, source: RegistrySource) -> list[Resource]:
        if source.type == RegistryType.local:
            return self._scan_directory(Path(source.url_or_path).expanduser())
        elif source.type == RegistryType.git:
            repo_cache = self.cache_dir / source.name
            if repo_cache.exists():
                return self._scan_directory(repo_cache)
        return []
