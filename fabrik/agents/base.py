"""Agent adapter base class."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from fabrik.models import Link


class AgentAdapter(ABC):
    """Abstract base class for AI agent configuration adapters."""

    @abstractmethod
    def detect(self, project_root: Path) -> bool:
        """Detect if this agent is active in the given project."""
        ...

    @abstractmethod
    def get_skills_path(self, project_root: Path) -> Path:
        """Return the path where skills are stored for this agent."""
        ...

    @abstractmethod
    def get_mcps_path(self, project_root: Path) -> Path:
        """Return the path where MCP configs are stored for this agent."""
        ...

    @abstractmethod
    def sync(self, project_root: Path, linked_skills: list[Link], linked_mcps: list[Link]) -> None:
        """Synchronize linked resources with the agent's configuration."""
        ...
