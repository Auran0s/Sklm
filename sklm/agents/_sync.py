"""Shared sync logic with variant overlay support.

Consolidates the sync pattern duplicated across GenericAdapter,
GitHubCopilotAdapter, and OpencodeAdapter into a single module.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sklm.models import Link


def sync_skills(
    linked_skills: list[Link],
    skills_path: Path,
    agent_id: str,
) -> None:
    """Sync all linked skills, applying variant overlays per-agent.

    Creates ``skills_path`` if needed, then for each linked skill:
    copies the base skill directory (excluding ``variants/``) and overlays
    ``variants/<agent_id>/`` if present.  Finally removes any directories
    in ``skills_path`` that are no longer linked.
    """
    skills_path.mkdir(parents=True, exist_ok=True)
    for link in linked_skills:
        _sync_skill(link, skills_path, agent_id)
    linked_names = {l.name for l in linked_skills}
    for existing in skills_path.iterdir():
        if existing.is_dir() and existing.name not in linked_names:
            shutil.rmtree(existing)


def _sync_skill(link: Link, skills_path: Path, agent_id: str) -> None:
    """Copy a single skill with optional variant overlay."""
    target_dir = skills_path / link.name
    if target_dir.exists():
        shutil.rmtree(target_dir)

    skill_root = link.target.resolve()

    def _ignore_root_variants(src_dir: str, names: list[str]) -> set[str]:
        if Path(src_dir).resolve() == skill_root:
            return {"variants"}
        return set()

    shutil.copytree(skill_root, target_dir, ignore=_ignore_root_variants)

    variant_dir = skill_root / "variants" / agent_id
    if variant_dir.is_dir():
        _overlay(variant_dir, target_dir)


def _overlay(src: Path, dst: Path) -> None:
    """Recursively merge *src* into *dst* — src files win, dst-only files survive."""
    for item in src.iterdir():
        dest_item = dst / item.name
        if item.is_dir():
            dest_item.mkdir(exist_ok=True)
            _overlay(item, dest_item)
        else:
            shutil.copy2(item, dest_item)


def get_variant_names(skill_path: Path) -> list[str]:
    """Return agent IDs for which variants exist under *skill_path*."""
    variants_dir = skill_path / "variants"
    if not variants_dir.is_dir():
        return []
    return sorted(
        p.name for p in variants_dir.iterdir() if p.is_dir()
    )
