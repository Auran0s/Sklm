"""Linking logic — manage links between the global store and a project workspace."""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path
from typing import Optional

from sklm.models import Link, ResourceKind
from sklm.store import GlobalStore
from sklm.core.workspace import Workspace


# Windows ERROR_PRIVILEGE_NOT_HELD: raised by os.symlink when the process does
# not hold SeCreateSymbolicLinkPrivilege (Developer Mode off, not elevated).
_WINDOWS_PRIVILEGE_NOT_HELD = 1314

# errno values that mean "this platform will not create a symlink here".
_SYMLINK_UNSUPPORTED_ERRNOS = frozenset({
    errno.EPERM,
    errno.EACCES,
    errno.ENOTSUP,
    errno.EINVAL,
})


def symlinks_unsupported(exc: OSError) -> bool:
    """Return True when *exc* means the platform will not create symlinks.

    Windows without Developer Mode raises ``WinError 1314``; other platforms
    surface the refusal through one of the errno values above.
    """
    if getattr(exc, "winerror", None) == _WINDOWS_PRIVILEGE_NOT_HELD:
        return True
    return exc.errno in _SYMLINK_UNSUPPORTED_ERRNOS


def _copy_into(source: Path, dest: Path) -> None:
    """Copy *source* to *dest* — the fallback when symlinks are unavailable."""
    if source.is_dir():
        shutil.copytree(source, dest)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


def link_resource(
    workspace: Workspace,
    global_store: GlobalStore,
    kind: ResourceKind,
    name: str,
) -> Link:
    resource = global_store.get_resource(kind, name)
    if not resource:
        raise FileNotFoundError(
            f"Resource '{kind.value}:{name}' not found in global store."
        )
    link_dir = workspace.links_dir / f"{kind.value}s" / name
    link_dir.parent.mkdir(parents=True, exist_ok=True)
    if link_dir.exists():
        raise FileExistsError(f"Link already exists for '{kind.value}:{name}'")
    try:
        os.symlink(resource.path, link_dir, target_is_directory=resource.path.is_dir())
    except OSError as exc:
        if not symlinks_unsupported(exc):
            raise
        # Symlinks need a privilege this process does not hold (Windows without
        # Developer Mode). Copy instead so the install still completes.
        _copy_into(resource.path, link_dir)
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
    """Return links whose stored skill or workspace entry is missing.

    The store target is checked as well as the workspace entry, because the
    entry may be a copy rather than a symlink when the platform cannot create
    symlinks.
    """
    broken: list[Link] = []
    for link in workspace.list_links():
        if not link.target.exists() or not link.link_path.exists():
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
