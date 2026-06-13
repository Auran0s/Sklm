"""OpenCode agent adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fabrik.agents.base import AgentAdapter


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
        linked_skills: list[str],
        linked_mcps: list[str],
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

    def _sync_skills(self, opencode_dir: Path, linked_skills: list[str]) -> None:
        skills_path = opencode_dir / "skills"
        skills_path.mkdir(parents=True, exist_ok=True)
        existing = {p.name for p in skills_path.iterdir() if p.is_dir()}
        for skill_name in linked_skills:
            if skill_name not in existing:
                skill_dir = skills_path / skill_name
                skill_dir.mkdir(parents=True, exist_ok=True)
        for name in existing:
            if name not in linked_skills:
                import shutil
                shutil.rmtree(skills_path / name)

    def _sync_mcps(self, opencode_dir: Path, linked_mcps: list[str]) -> None:
        mcps_path = opencode_dir / "mcps"
        mcps_path.mkdir(parents=True, exist_ok=True)
        existing = {p.name for p in mcps_path.iterdir() if p.is_dir()}
        for mcp_name in linked_mcps:
            if mcp_name not in existing:
                mcp_dir = mcps_path / mcp_name
                mcp_dir.mkdir(parents=True, exist_ok=True)
        for name in existing:
            if name not in linked_mcps:
                import shutil
                shutil.rmtree(mcps_path / name)
