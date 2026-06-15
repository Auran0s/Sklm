"""Agent registry — loads agent definitions from YAML, resolves adapters."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from sklm.agents.base import AgentAdapter


class AgentRegistry:
    """Data-driven registry of supported AI agents.

    Loads agent definitions from ``agents.yaml`` and provides adapter
    resolution, detection, and listing.
    """

    def __init__(self, config_path: Optional[Path] = None) -> None:
        self.config_path = config_path or (Path(__file__).parent / "agents.yaml")
        self._agents: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        with open(self.config_path) as f:
            data = yaml.safe_load(f)
        self._agents = (data or {}).get("agents", {})

    def detect_first(self, project_root: Path) -> Optional[str]:
        """Detect the first active agent by checking for agent dirs in order."""
        for agent_id, config in self._agents.items():
            if config.get("detect") == "explicit":
                continue
            if (project_root / config["dir_name"]).is_dir():
                return agent_id
        return None

    def detect(self, project_root: Path) -> list[str]:
        """Return all detected agent IDs whose config directories exist."""
        detected: list[str] = []
        for agent_id, config in self._agents.items():
            if config.get("detect") == "explicit":
                continue
            if (project_root / config["dir_name"]).is_dir():
                detected.append(agent_id)
        return detected

    def detect_adapter(self, project_root: Path) -> Optional[AgentAdapter]:
        """Detect active agent and return its adapter instance."""
        agent_id = self.detect_first(project_root)
        if agent_id:
            return self.get_adapter(agent_id)
        return None

    def detect_all_adapters(self, project_root: Path) -> list[AgentAdapter]:
        """Return adapters for all detected agent directories."""
        return [self.get_adapter(aid) for aid in self.detect(project_root) if self.get_adapter(aid)]

    def get_adapter(self, agent_id: str) -> Optional[AgentAdapter]:
        """Return an adapter instance for the given agent ID."""
        from sklm.agents.generic import GenericAdapter

        config = self._agents.get(agent_id)
        if not config:
            return None
        if agent_id == "github-copilot":
            from sklm.agents.github_copilot import GitHubCopilotAdapter
            return GitHubCopilotAdapter()
        return GenericAdapter(agent_id, config)

    def list_agents(self, project_root: Path) -> list[dict]:
        """Return a list of all agents with their active status."""
        result: list[dict] = []
        for agent_id, config in self._agents.items():
            dir_name = config["dir_name"]
            result.append({
                "id": agent_id,
                "dir": dir_name,
                "detect": config.get("detect", "dir_exists"),
                "active": (project_root / dir_name).is_dir(),
            })
        return result

    def get_agent_ids(self) -> list[str]:
        """Return the list of all known agent IDs."""
        return list(self._agents.keys())

    def get_agent_config(self, agent_id: str) -> Optional[dict]:
        """Return the config dict for a given agent ID."""
        return self._agents.get(agent_id)
