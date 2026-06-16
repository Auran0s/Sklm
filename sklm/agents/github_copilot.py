"""GitHub Copilot adapter.

Copilot uses a non-standard directory (``.github/skills/``) and is never
auto-detected because ``.github/`` exists in virtually every GitHub-hosted
project.
"""

from __future__ import annotations

from pathlib import Path

from sklm.agents._sync import sync_skills
from sklm.agents.base import AgentAdapter
from sklm.models import Link


GITHUB_COPILOT_DIR = ".github"


class GitHubCopilotAdapter(AgentAdapter):
    """Adapter for GitHub Copilot (explicit activation only)."""

    def __init__(self, agent_id: str = "github-copilot") -> None:
        self.agent_id = agent_id

    def detect(self, project_root: Path) -> bool:
        return False

    def get_skills_path(self, project_root: Path) -> Path:
        return project_root / GITHUB_COPILOT_DIR / "skills"

    def sync(
        self,
        project_root: Path,
        linked_skills: list[Link],
    ) -> None:
        sync_skills(linked_skills, self.get_skills_path(project_root), self.agent_id)
