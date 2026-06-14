"""Workspace — manages .sklm/ in the current project."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from sklm.models import (
    Link,
    ResourceKind,
    ResourceRef,
    WorkspaceConfig,
)


SKLM_DIR_NAME = ".sklm"


class Workspace:
    """Manages a project-level Sklm workspace."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = (root or Path.cwd()).resolve()
        self.sklm_dir = self.root / SKLM_DIR_NAME
        self.config_path = self.sklm_dir / "sklm.yaml"
        self.links_dir = self.sklm_dir / "links"

    def exists(self) -> bool:
        return self.sklm_dir.is_dir()

    def set_agent(self, agent: str) -> None:
        config = self.load_config()
        config.agent = agent
        self._save_config(config)

    def init(self, agent: str = "none") -> WorkspaceConfig:
        self.sklm_dir.mkdir(parents=True, exist_ok=True)
        self.links_dir.mkdir(parents=True, exist_ok=True)
        (self.links_dir / "skills").mkdir(exist_ok=True)
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
