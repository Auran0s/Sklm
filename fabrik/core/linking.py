"""Linking logic — manage symlinks between global store and project workspace."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fabrik.models import Link, ResourceKind
from fabrik.store import GlobalStore
from fabrik.core.workspace import Workspace


def link_resource(
    workspace: Workspace,
    global_store: GlobalStore,
    kind: ResourceKind,
    name: str,
) -> Link:
    resource = global_store.get_resource(kind, name)
    if not resource:
        raise FileNotFoundError(
            f"Resource '{kind.value}:{name}' not found in global store. "
            f"Add it first with 'fabrik global add {kind.value} <path>'"
        )
    link_dir = workspace.links_dir / f"{kind.value}s" / name
    link_dir.parent.mkdir(parents=True, exist_ok=True)
    if link_dir.exists():
        raise FileExistsError(f"Link already exists for '{kind.value}:{name}'")
    os.symlink(resource.path, link_dir, target_is_directory=resource.path.is_dir())
    link = Link(
        name=name,
        kind=kind,
        target=resource.path,
        link_path=link_dir,
    )
    workspace.add_link(link)
    return link


def unlink_resource(
    workspace: Workspace,
    kind: ResourceKind,
    name: str,
) -> None:
    link_dir = workspace.links_dir / f"{kind.value}s" / name
    if link_dir.exists():
        if link_dir.is_symlink():
            link_dir.unlink()
        else:
            import shutil
            shutil.rmtree(link_dir)
    workspace.remove_link(kind, name)


def detect_broken_links(
    workspace: Workspace,
) -> list[Link]:
    broken: list[Link] = []
    for link in workspace.list_links():
        target = link.link_path
        if not target.exists():
            broken.append(link)
    return broken


def repair_links(
    workspace: Workspace,
    global_store: GlobalStore,
) -> tuple[list[Link], list[Link]]:
    broken = detect_broken_links(workspace)
    repaired: list[Link] = []
    still_broken: list[Link] = []
    for link in broken:
        resource = global_store.get_resource(link.kind, link.name)
        if resource:
            unlink_resource(workspace, link.kind, link.name)
            repaired.append(link_resource(workspace, global_store, link.kind, link.name))
        else:
            still_broken.append(link)
    return repaired, still_broken
