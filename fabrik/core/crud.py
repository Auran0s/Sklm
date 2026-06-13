"""Resource CRUD — manage resource references in the workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fabrik.models import ResourceKind, ResourceRef
from fabrik.core.workspace import Workspace
from fabrik.core.registry import RegistryManager
from fabrik.store import GlobalStore


def add_resource_to_workspace(
    workspace: Workspace,
    global_store: GlobalStore,
    registry_manager: RegistryManager,
    kind: ResourceKind,
    name: str,
) -> ResourceRef:
    ref = _resolve_resource(global_store, registry_manager, kind, name)
    workspace.add_resource(ref)
    return ref


def remove_resource_from_workspace(
    workspace: Workspace,
    kind: ResourceKind,
    name: str,
    force: bool = False,
) -> ResourceRef:
    ref = workspace.get_resource(kind, name)
    if not ref:
        raise KeyError(f"Resource '{kind.value}:{name}' not found in workspace")
    if ref.linked and not force:
        raise RuntimeError(
            f"Resource '{kind.value}:{name}' is linked. Use --force to unlink and remove."
        )
    if ref.linked and force:
        from fabrik.core.linking import unlink_resource
        unlink_resource(workspace, kind, name)
    return workspace.remove_resource(kind, name)


def list_workspace_resources(
    workspace: Workspace,
    kind: Optional[ResourceKind] = None,
) -> list[ResourceRef]:
    return workspace.list_resources(kind)


def get_resource_info(
    workspace: Workspace,
    global_store: GlobalStore,
    kind: ResourceKind,
    name: str,
) -> Optional[ResourceRef]:
    ref = workspace.get_resource(kind, name)
    if not ref:
        ref_global = global_store.get_resource(kind, name)
        if ref_global:
            ref = ResourceRef(
                name=ref_global.name,
                kind=ref_global.kind,
                origin=str(ref_global.path),
                linked=False,
                path=ref_global.path,
            )
    return ref


def _resolve_resource(
    global_store: GlobalStore,
    registry_manager: RegistryManager,
    kind: ResourceKind,
    name: str,
) -> ResourceRef:
    if ":" in name:
        registry_name, resource_name = name.split(":", 1)
        results = registry_manager.search(resource_name, registry_filter=registry_name, type_filter=kind)
        if results:
            _, resource = results[0]
            return ResourceRef(
                name=resource.name,
                kind=resource.kind,
                origin=f"registry:{registry_name}",
                linked=False,
                path=resource.path,
            )
        raise FileNotFoundError(f"Resource '{name}' not found in registry '{registry_name}'")
    resource = global_store.get_resource(kind, name)
    if resource:
        return ResourceRef(
            name=resource.name,
            kind=resource.kind,
            origin="global",
            linked=False,
            path=resource.path,
        )
    results = registry_manager.search(name, type_filter=kind)
    if results:
        reg_name, resource = results[0]
        return ResourceRef(
            name=resource.name,
            kind=resource.kind,
            origin=f"registry:{reg_name}",
            linked=False,
            path=resource.path,
        )
    path = Path(name)
    if path.exists():
        return ResourceRef(
            name=path.name,
            kind=kind,
            origin="local",
            linked=False,
            path=path.resolve(),
        )
    raise FileNotFoundError(
        f"Resource '{kind.value}:{name}' not found in global store, registries, or local path"
    )
