"""Generic adapter for standard AI agents.

Serves any agent that follows the ``<project_root>/.<dir_name>/skills/``
pattern.  No per-agent subclass required.
"""

from __future__ import annotations

from pathlib import Path

from sklm.agents._sync import sync_skills
from sklm.agents.base import AgentAdapter
from sklm.models import Link


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
        sync_skills(linked_skills, self.get_skills_path(project_root), self.agent_id)
