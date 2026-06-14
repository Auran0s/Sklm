"""OpenCode agent adapter."""

from __future__ import annotations

import shutil
from pathlib import Path

from fabrik.agents.base import AgentAdapter
from fabrik.models import Link


OPENER_DIR_NAME = ".opencode"


class OpencodeAdapter(AgentAdapter):
    """Adapter for the OpenCode AI agent."""

    def detect(self, project_root: Path) -> bool:
        return (project_root / OPENER_DIR_NAME).is_dir()

    def get_skills_path(self, project_root: Path) -> Path:
        return project_root / OPENER_DIR_NAME / "skills"

    def sync(
        self,
        project_root: Path,
        linked_skills: list[Link],
    ) -> None:
        opencode_dir = project_root / OPENER_DIR_NAME
        self._sync_skills(opencode_dir, linked_skills)

    def _sync_skills(self, opencode_dir: Path, linked_skills: list[Link]) -> None:
        skills_path = opencode_dir / "skills"
        skills_path.mkdir(parents=True, exist_ok=True)

        for link in linked_skills:
            target_dir = skills_path / link.name
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(link.target, target_dir)

        linked_names = {l.name for l in linked_skills}
        for existing in list(skills_path.iterdir()):
            if existing.is_dir() and existing.name not in linked_names:
                shutil.rmtree(existing)
