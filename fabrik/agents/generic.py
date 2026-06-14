"""Generic adapter for standard AI agents.

Serves any agent that follows the ``<project_root>/.<dir_name>/skills/``
pattern.  No per-agent subclass required.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from fabrik.agents.base import AgentAdapter
from fabrik.models import Link


class GenericAdapter(AgentAdapter):
    """Config-driven adapter serving any agent with a standard layout."""

    def __init__(self, agent_id: str, config: dict) -> None:
        self.agent_id = agent_id
        self.dir_name = config["dir_name"]
        self.skills_subdir = config.get("skills_subdir", "skills")

    def detect(self, project_root: Path) -> bool:
        return (project_root / self.dir_name).is_dir()

    def get_skills_path(self, project_root: Path) -> Path:
        return project_root / self.dir_name / self.skills_subdir

    def sync(
        self,
        project_root: Path,
        linked_skills: list[Link],
    ) -> None:
        skills_path = self.get_skills_path(project_root)
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
