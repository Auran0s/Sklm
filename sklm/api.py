"""Sklm API — main facade for all operations."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console

from sklm.models import Link, ResourceKind, ResourceRef
from sklm.store import GlobalStore
from sklm.core.workspace import Workspace
from sklm.core.registry import RegistryManager, RegistrySource
from sklm.core.crud import (
    add_resource_to_workspace,
    remove_resource_from_workspace,
    list_workspace_resources,
    get_resource_info,
)
from sklm.core.linking import (
    link_resource as _link_resource,
    unlink_resource as _unlink_resource,
    detect_broken_links,
    repair_links,
)
from sklm.agents.base import AgentAdapter
from sklm.agents.registry import AgentRegistry

console = Console()


class Sklm:
    """Main API for Sklm operations."""

    def __init__(self, project_root: Optional[Path] = None) -> None:
        self.project_root = (project_root or Path.cwd()).resolve()
        self.global_store = GlobalStore()
        self.workspace = Workspace(self.project_root)
        self.registry_manager = RegistryManager()
        self.agent_registry = AgentRegistry()
        self._agents: Optional[list[AgentAdapter]] = None

    def init_workspace(self, agents: Optional[list[str]] = None) -> list[str]:
        if agents is not None:
            detected = agents
        else:
            detected = self._detect_agents()
        self.workspace.init(agents=detected)
        if detected and detected != ["none"]:
            for agent_name in detected:
                adapter = self._find_adapter_by_name(agent_name)
                if adapter:
                    adapter.sync(self.project_root, [])
        return detected

    def set_agent(self, agent: str) -> str:
        self.workspace.set_agents([agent])
        return agent

    def get_status(self) -> dict:
        config = self.workspace.load_config()
        resources = config.resources
        links = config.links
        broken = detect_broken_links(self.workspace)
        external_skills_path = Path.home() / ".agents" / "skills"
        external_skills_count = 0
        if external_skills_path.exists():
            external_skills_count = len([
                d for d in external_skills_path.iterdir()
                if d.is_dir() and (d / "SKILL.md").exists()
            ])
        return {
            "agents": config.agents,
            "total_resources": len(resources),
            "skills": len([r for r in resources if r.kind == ResourceKind.skill]),
            "total_links": len(links),
            "linked_skills": len([l for l in links if l.kind == ResourceKind.skill]),
            "broken_links": len(broken),
            "broken_link_details": broken,
            "external_skills_count": external_skills_count,
        }

    def repair_broken_links(self) -> dict:
        repaired, still_broken = repair_links(self.workspace, self.global_store)
        return {"repaired": repaired, "still_broken": still_broken}

    # ── Install / Uninstall ───────────────────────────────────────────────

    def install(
        self,
        kind: ResourceKind,
        name: str,
        from_url: Optional[str] = None,
        subdir: Optional[str] = None,
    ) -> ResourceRef:
        if from_url:
            resource = self.global_store.add_resource_from_git(
                kind, name, from_url, subdir=subdir
            )
            return ResourceRef(
                name=resource.name,
                kind=resource.kind,
                origin=from_url,
                linked=False,
                path=resource.path,
            )
        ref = add_resource_to_workspace(
            self.workspace, self.global_store, self.registry_manager, kind, name
        )
        existing = self.global_store.get_resource(kind, ref.name)
        if not existing and ref.path:
            self.global_store.add_resource(kind, ref.path, ref.name)
        return ResourceRef(
            name=ref.name,
            kind=ref.kind,
            origin=ref.origin,
            linked=False,
            path=ref.path,
        )

    def uninstall(self, kind: ResourceKind, name: str) -> None:
        linked = False
        try:
            _unlink_resource(self.workspace, kind, name)
            linked = True
        except (KeyError, FileNotFoundError):
            pass
        self.global_store.remove_resource(kind, name)

    def migrate(
        self,
        kind: ResourceKind,
        name: Optional[str] = None,
        source_path: Optional[Path] = None,
    ) -> list[tuple[ResourceRef, Path]]:
        if source_path is not None:
            source_dir = source_path.resolve()
        else:
            source_dir = Path.home() / ".agents" / f"{kind.value}s"
        if not source_dir.exists():
            raise FileNotFoundError(f"No resources found at {source_dir}")
        results: list[tuple[ResourceRef, Path]] = []
        if name:
            src = source_dir / name
            if not src.exists() or not (src / "SKILL.md").exists():
                raise FileNotFoundError(f"Resource '{name}' not found in {source_dir}")
            resource = self.global_store.add_resource(kind, src, name)
            results.append((
                ResourceRef(
                    name=resource.name,
                    kind=resource.kind,
                    origin=str(src),
                    linked=False,
                    path=resource.path,
                ),
                src,
            ))
        else:
            for d in sorted(source_dir.iterdir()):
                if not d.is_dir():
                    continue
                if not (d / "SKILL.md").exists():
                    continue
                try:
                    resource = self.global_store.add_resource(kind, d)
                    results.append((
                        ResourceRef(
                            name=resource.name,
                            kind=resource.kind,
                            origin=str(d),
                            linked=False,
                            path=resource.path,
                        ),
                        d,
                    ))
                except FileExistsError:
                    continue
        return results

    # ── Resource CRUD ────────────────────────────────────────────────────

    def add(
        self,
        kind: ResourceKind,
        name: str,
        from_url: Optional[str] = None,
        subdir: Optional[str] = None,
    ) -> ResourceRef:
        if from_url:
            ref = self.install(kind, name, from_url=from_url, subdir=subdir)
            self.workspace.add_resource(ref)
        else:
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
            console.print(
                "[yellow]⚠[/] Skill installed but no agent configured — "
                "not synced to any agent directory."
            )
            console.print(
                "   Run [bold]sklm init --agent <name>[/] to configure an agent."
            )
        return ref

    def remove(self, kind: ResourceKind, name: str) -> ResourceRef:
        ref = remove_resource_from_workspace(self.workspace, kind, name)
        try:
            self.agent_sync()
        except RuntimeError:
            console.print(
                "[yellow]⚠[/] Skill removed but no agent configured — "
                "agent directory not cleaned."
            )
            console.print(
                "   Run [bold]sklm init --agent <name>[/] to configure an agent."
            )
        return ref

    def list(self, kind: Optional[ResourceKind] = None) -> list[ResourceRef]:
        return list_workspace_resources(self.workspace, kind)

    def info(self, kind: ResourceKind, name: str) -> Optional[ResourceRef]:
        return get_resource_info(self.workspace, self.global_store, kind, name)

    # ── Linking (internal) ───────────────────────────────────────────────

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

    def list_agents(self) -> list[dict]:
        return self.agent_registry.list_agents(self.project_root)

    def get_agent(self) -> Optional[AgentAdapter]:
        agents = self.get_agents()
        return agents[0] if agents else None

    def get_agents(self) -> list[AgentAdapter]:
        if self._agents is not None:
            return self._agents
        resolved: list[AgentAdapter] = []
        seen: set[str] = set()
        for adapter in self.agent_registry.detect_all_adapters(self.project_root):
            resolved.append(adapter)
            seen.add(type(adapter).__name__.replace("Adapter", "").lower())
        config = self.workspace.load_config()
        for agent_name in config.agents:
            if agent_name == "none" or agent_name in seen:
                continue
            adapter = self._find_adapter_by_name(agent_name)
            if adapter:
                resolved.append(adapter)
                seen.add(agent_name)
        self._agents = resolved
        return self._agents

    def agent_sync(self, dry_run: bool = False) -> dict:
        self._agents = None
        agents = self.get_agents()
        if not agents:
            raise RuntimeError("No agent detected. Run 'sklm init' first.")
        links = self.workspace.list_links()
        linked_skills = [l for l in links if l.kind == ResourceKind.skill]
        if dry_run:
            return {
                "agents": [type(a).__name__ for a in agents],
                "skills_to_add": [l.name for l in linked_skills],
            }
        for agent in agents:
            agent.sync(self.project_root, linked_skills)
        return {"agents": [type(a).__name__ for a in agents], "synced": True}

    def agent_detect(self) -> Optional[str]:
        adapter = self._detect_agent_adapter()
        if adapter:
            return type(adapter).__name__.replace("Adapter", "").lower()
        return None

    # ── Internal ─────────────────────────────────────────────────────────

    def _detect_agents(self) -> list[str]:
        detected = self.agent_registry.detect(self.project_root)
        return detected or ["none"]

    def _detect_agent_adapter(self) -> Optional[AgentAdapter]:
        return self.agent_registry.detect_adapter(self.project_root)

    def _find_adapter_by_name(self, agent_name: str) -> Optional[AgentAdapter]:
        return self.agent_registry.get_adapter(agent_name)
