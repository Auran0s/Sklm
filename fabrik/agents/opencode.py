"""OpenCode agent adapter."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fabrik.agents.base import AgentAdapter
from fabrik.models import Link


OPENER_DIR_NAME = ".opencode"
OPENER_CONFIG_NAME = "opencode.json"


class OpencodeAdapter(AgentAdapter):
    """Adapter for the OpenCode AI agent."""

    def detect(self, project_root: Path) -> bool:
        return (project_root / OPENER_DIR_NAME).is_dir()

    def get_skills_path(self, project_root: Path) -> Path:
        return project_root / OPENER_DIR_NAME / "skills"

    def get_mcps_path(self, project_root: Path) -> Path:
        return project_root / OPENER_DIR_NAME / "mcps"

    def sync(
        self,
        project_root: Path,
        linked_skills: list[Link],
        linked_mcps: list[Link],
    ) -> None:
        opencode_dir = project_root / OPENER_DIR_NAME
        config_path = opencode_dir / OPENER_CONFIG_NAME
        if not config_path.exists():
            config: dict[str, Any] = {}
        else:
            with open(config_path) as f:
                config = json.load(f)

        self._sync_skills(opencode_dir, linked_skills)
        self._sync_mcps(opencode_dir, linked_mcps)

    def _sync_skills(self, opencode_dir: Path, linked_skills: list[Link]) -> None:
        skills_path = opencode_dir / "skills"
        skills_path.mkdir(parents=True, exist_ok=True)

        # Copy content from global store for each linked skill
        for link in linked_skills:
            target_dir = skills_path / link.name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(link.target, target_dir)

        # Remove skills that are no longer linked
        linked_names = {l.name for l in linked_skills}
        for existing in list(skills_path.iterdir()):
            if existing.is_dir() and existing.name not in linked_names:
                shutil.rmtree(existing)

    def _sync_mcps(self, opencode_dir: Path, linked_mcps: list[Link]) -> None:
        mcps_path = opencode_dir / "mcps"
        mcps_path.mkdir(parents=True, exist_ok=True)

        # Copy content from global store for each linked MCP
        for link in linked_mcps:
            target_dir = mcps_path / link.name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(link.target, target_dir)

        # Remove MCPs that are no longer linked
        linked_names = {l.name for l in linked_mcps}
        for existing in list(mcps_path.iterdir()):
            if existing.is_dir() and existing.name not in linked_names:
                shutil.rmtree(existing)
