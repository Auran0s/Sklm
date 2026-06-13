"""Workspace — manages .fabrik/ in the current project."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fabrik.models import (
    Link,
    ResourceKind,
    ResourceRef,
    WorkspaceConfig,
)


FABRIK_DIR_NAME = ".fabrik"


class Workspace:
    """Manages a project-level Fabrik workspace."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or Path.cwd()).resolve()
        self.fabrik_dir = self.root / FABRIK_DIR_NAME
        self.config_path = self.fabrik_dir / "fabrik.yaml"
        self.links_dir = self.fabrik_dir / "links"
        self.local_dir = self.fabrik_dir / "local"

    def exists(self) -> bool:
        return self.fabrik_dir.is_dir()

    def set_agent(self, agent: str) -> None:
        config = self.load_config()
        config.agent = agent
        self._save_config(config)

    def init(self, agent: str = "none") -> WorkspaceConfig:
        self.fabrik_dir.mkdir(parents=True, exist_ok=True)
        self.links_dir.mkdir(parents=True, exist_ok=True)
        (self.links_dir / "skills").mkdir(exist_ok=True)
        (self.links_dir / "mcps").mkdir(exist_ok=True)
        self.local_dir.mkdir(parents=True, exist_ok=True)
        (self.local_dir / "skills").mkdir(exist_ok=True)
        (self.local_dir / "mcps").mkdir(exist_ok=True)
        config = WorkspaceConfig(agent=agent)
        self._save_config(config)
        return config

    def load_config(self) -> WorkspaceConfig:
        return WorkspaceConfig.from_yaml(self.config_path)

    def _save_config(self, config: WorkspaceConfig) -> None:
        config.to_yaml(self.config_path)

    def add_resource(self, ref: ResourceRef) -> None:
        config = self.load_config()
        for r in config.resources:
            if r.name == ref.name and r.kind == ref.kind:
                raise ValueError(
                    f"Resource '{ref.kind.value}:{ref.name}' already exists in workspace"
                )
        config.resources.append(ref)
        self._save_config(config)

    def remove_resource(self, kind: ResourceKind, name: str) -> Optional[ResourceRef]:
        config = self.load_config()
        for i, r in enumerate(config.resources):
            if r.name == name and r.kind == kind:
                removed = config.resources.pop(i)
                self._save_config(config)
                return removed
        raise KeyError(f"Resource '{kind.value}:{name}' not found in workspace")

    def list_resources(self, kind: Optional[ResourceKind] = None) -> list[ResourceRef]:
        config = self.load_config()
        link_names = {(l.kind, l.name) for l in config.links}
        resources = []
        for r in config.resources:
            r.linked = (r.kind, r.name) in link_names
            resources.append(r)
        if kind:
            return [r for r in resources if r.kind == kind]
        return resources

    def get_resource(self, kind: ResourceKind, name: str) -> Optional[ResourceRef]:
        config = self.load_config()
        for r in config.resources:
            if r.name == name and r.kind == kind:
                r.linked = any(
                    l.name == name and l.kind == kind for l in config.links
                )
                return r
        return None

    def add_link(self, link: Link) -> None:
        config = self.load_config()
        for l in config.links:
            if l.name == link.name and l.kind == link.kind:
                return
        config.links.append(link)
        self._save_config(config)

    def remove_link(self, kind: ResourceKind, name: str) -> Optional[Link]:
        config = self.load_config()
        for i, l in enumerate(config.links):
            if l.name == name and l.kind == kind:
                removed = config.links.pop(i)
                self._save_config(config)
                return removed
        return None

    def list_links(self) -> list[Link]:
        config = self.load_config()
        return list(config.links)

    def get_link(self, kind: ResourceKind, name: str) -> Optional[Link]:
        config = self.load_config()
        for l in config.links:
            if l.name == name and l.kind == kind:
                return l
        return None
