"""GitHub Copilot adapter.

Copilot uses a non-standard directory (``.github/skills/``) and is never
auto-detected because ``.github/`` exists in virtually every GitHub-hosted
project.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sklm.agents.base import AgentAdapter
from sklm.models import Link


GITHUB_COPILOT_DIR = ".github"


class GitHubCopilotAdapter(AgentAdapter):
    """Adapter for GitHub Copilot (explicit activation only)."""

    def detect(self, project_root: Path) -> bool:
        return False

    def get_skills_path(self, project_root: Path) -> Path:
        return project_root / GITHUB_COPILOT_DIR / "skills"

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
