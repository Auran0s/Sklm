"""Fabrik API — main facade for all operations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fabrik.models import Link, ResourceKind, ResourceRef
from fabrik.store import GlobalStore
from fabrik.core.workspace import Workspace
from fabrik.core.registry import RegistryManager, RegistrySource
from fabrik.core.crud import (
    add_resource_to_workspace,
    remove_resource_from_workspace,
    list_workspace_resources,
    get_resource_info,
)
from fabrik.core.linking import (
    link_resource as _link_resource,
    unlink_resource as _unlink_resource,
    detect_broken_links,
    repair_links,
)
from fabrik.agents.base import AgentAdapter
from fabrik.agents.opencode import OpencodeAdapter


class Fabrik:
    """Main API for Fabrik operations."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.global_store = GlobalStore()
        self.workspace = Workspace(self.project_root)
        self.registry_manager = RegistryManager()
        self._agent: Optional[AgentAdapter] = None

    def init_workspace(self, agent: Optional[str] = None) -> str:
        if agent:
            detected = agent
        else:
            detected = self._detect_agent()
        self.workspace.init(agent=detected)
        # Prepare agent infrastructure directories
        if agent:
            adapter = self._find_adapter_by_name(agent)
        else:
            adapter = self._detect_agent_adapter()
        if adapter:
            adapter.sync(self.project_root, [], [])
        return detected

    def set_agent(self, agent: str) -> str:
        self.workspace.set_agent(agent)
        return agent

    def get_status(self) -> dict:
        config = self.workspace.load_config()
        resources = config.resources
        links = config.links
        broken = detect_broken_links(self.workspace)
        return {
            "agent": config.agent,
            "total_resources": len(resources),
            "skills": len([r for r in resources if r.kind == ResourceKind.skill]),
            "mcps": len([r for r in resources if r.kind == ResourceKind.mcp]),
            "total_links": len(links),
            "linked_skills": len([l for l in links if l.kind == ResourceKind.skill]),
            "linked_mcps": len([l for l in links if l.kind == ResourceKind.mcp]),
            "broken_links": len(broken),
            "broken_link_details": broken,
        }

    def repair_broken_links(self) -> dict:
        repaired, still_broken = repair_links(self.workspace, self.global_store)
        return {"repaired": repaired, "still_broken": still_broken}

    # ── Resource CRUD ────────────────────────────────────────────────────

    def add(self, kind: ResourceKind, name: str) -> ResourceRef:
        ref = add_resource_to_workspace(
            self.workspace, self.global_store, self.registry_manager, kind, name
        )
        existing = self.global_store.get_resource(kind, ref.name)
        if not existing and ref.path:
            self.global_store.add_resource(kind, ref.path, ref.name)
        _link_resource(self.workspace, self.global_store, kind, ref.name)
        try:
            self.agent_sync()
        except RuntimeError:
            pass
        return ref

    def remove(self, kind: ResourceKind, name: str) -> ResourceRef:
        ref = remove_resource_from_workspace(self.workspace, kind, name)
        try:
            self.agent_sync()
        except RuntimeError:
            pass
        return ref

    def list(self, kind: Optional[ResourceKind] = None) -> list[ResourceRef]:
        if kind and kind == ResourceKind.mcp:
            kind_filter = ResourceKind.mcp
        elif kind:
            kind_filter = ResourceKind.skill
        else:
            kind_filter = None
        return list_workspace_resources(self.workspace, kind_filter)

    def info(self, kind: ResourceKind, name: str) -> Optional[ResourceRef]:
        return get_resource_info(self.workspace, self.global_store, kind, name)

    # ── Linking ──────────────────────────────────────────────────────────

    def link(self, kind: ResourceKind, name: str) -> Link:
        return _link_resource(self.workspace, self.global_store, kind, name)

    def unlink(self, kind: ResourceKind, name: str) -> None:
        _unlink_resource(self.workspace, kind, name)

    # ── Global Store ─────────────────────────────────────────────────────

    def global_add(self, kind: ResourceKind, path: str, name: Optional[str] = None):
        return self.global_store.add_resource(kind, Path(path), name)

    def global_ls(self, kind: Optional[ResourceKind] = None):
        return self.global_store.list_resources(kind)

    def global_rm(self, kind: ResourceKind, name: str):
        return self.global_store.remove_resource(kind, name)

    # ── Registry ─────────────────────────────────────────────────────────

    def registry_add(self, url_or_path: str, name: Optional[str] = None) -> RegistrySource:
        path = Path(url_or_path)
        is_git = path.suffix == ".git" or "github.com" in url_or_path
        source_name = name or path.name.replace(".git", "")
        src = RegistrySource(
            name=source_name,
            type="git" if is_git else "local",
            url_or_path=url_or_path,
        )
        self.registry_manager.add_source(src)
        return src

    def registry_ls(self) -> dict[str, RegistrySource]:
        return self.registry_manager.list_sources()

    def registry_search(
        self,
        query: str,
        registry: Optional[str] = None,
        type_filter: Optional[ResourceKind] = None,
    ):
        return self.registry_manager.search(query, registry, type_filter)

    # ── Agent ────────────────────────────────────────────────────────────

    def get_agent(self) -> Optional[AgentAdapter]:
        if self._agent is None:
            self._agent = self._detect_agent_adapter()
        return self._agent

    def agent_sync(self, dry_run: bool = False) -> dict:
        agent = self.get_agent()
        if not agent:
            raise RuntimeError("No agent detected. Run 'fabrik init' first.")
        links = self.workspace.list_links()
        linked_skills = [l for l in links if l.kind == ResourceKind.skill]
        linked_mcps = [l for l in links if l.kind == ResourceKind.mcp]
        if dry_run:
            return {
                "agent": type(agent).__name__,
                "skills_to_add": [l.name for l in linked_skills],
                "mcps_to_add": [l.name for l in linked_mcps],
            }
        agent.sync(self.project_root, linked_skills, linked_mcps)
        return {"agent": type(agent).__name__, "synced": True}

    def agent_detect(self) -> Optional[str]:
        adapter = self._detect_agent_adapter()
        if adapter:
            return type(adapter).__name__.replace("Adapter", "").lower()
        return None

    # ── Internal ─────────────────────────────────────────────────────────

    def _detect_agent(self) -> str:
        adapters: list[AgentAdapter] = [OpencodeAdapter()]
        for adapter in adapters:
            if adapter.detect(self.project_root):
                return type(adapter).__name__.replace("Adapter", "").lower()
        return "none"

    def _detect_agent_adapter(self) -> Optional[AgentAdapter]:
        adapters: list[AgentAdapter] = [OpencodeAdapter()]
        for adapter in adapters:
            if adapter.detect(self.project_root):
                return adapter
        return None

    def _find_adapter_by_name(self, agent_name: str) -> Optional[AgentAdapter]:
        """Instantiate an adapter by its canonical name, bypassing detection."""
        adapters: list[type[AgentAdapter]] = [OpencodeAdapter]
        for adapter_cls in adapters:
            name = adapter_cls.__name__.replace("Adapter", "").lower()
            if name == agent_name:
                return adapter_cls()
        return None
