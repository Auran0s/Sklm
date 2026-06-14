"""Pydantic data models for Sklm."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator


class ResourceKind(str, Enum):
    skill = "skill"


class RegistryType(str, Enum):
    local = "local"
    git = "git"


class AgentKind(str, Enum):
    opencode = "opencode"
    claude = "claude"
    cursor = "cursor"
    windsurf = "windsurf"
    gemini = "gemini"
    cline = "cline"
    amazon_q = "amazon-q"
    github_copilot = "github-copilot"


class Resource(BaseModel):
    name: str = Field(description="Unique identifier (kebab-case)")
    kind: ResourceKind = Field(description="Type of resource")
    source: str = Field(description="Provenance (registry:name, local, path)")
    path: Path = Field(description="Absolute path to the resource")
    meta: dict[str, Any] = Field(default_factory=dict, description="Metadata")

    @field_validator("name")
    @classmethod
    def name_must_be_kebab(cls, v: str) -> str:
        if not v.replace("-", "").isalnum():
            raise ValueError("name must be kebab-case")
        return v


class ResourceRef(BaseModel):
    name: str = Field(description="Resource name")
    kind: ResourceKind = Field(description="Resource type")
    origin: str = Field(description="Where it came from: global, local, registry:name")
    linked: bool = Field(default=False, description="Whether a link exists")
    path: Optional[Path] = Field(default=None, description="Resolved path")


class Link(BaseModel):
    name: str = Field(description="Resource name")
    kind: ResourceKind = Field(description="Resource type")
    target: Path = Field(description="Target path in global store")
    link_path: Path = Field(description="Symlink path in workspace")


class RegistrySource(BaseModel):
    name: str = Field(description="Unique registry name")
    type: RegistryType = Field(description="local or git")
    url_or_path: str = Field(description="Filesystem path or git URL")
    description: Optional[str] = Field(default=None)

    @field_validator("name")
    @classmethod
    def name_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("registry name must not contain spaces")
        return v


class WorkspaceConfig(BaseModel):
    version: int = Field(default=1)
    agent: str = Field(default="none", description="Active agent name")
    resources: list[ResourceRef] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)

    @field_validator("agent")
    @classmethod
    def agent_must_be_known(cls, v: str) -> str:
        if v == "none":
            return v
        try:
            AgentKind(v)
        except ValueError:
            known = ", ".join(m.value for m in AgentKind)
            raise ValueError(
                f"Unknown agent '{v}'. Known agents: {known}"
            )
        return v

    @classmethod
    def from_yaml(cls, path: Path) -> "WorkspaceConfig":
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data) if data else cls()

    def to_yaml(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)


class SourceMetadata(BaseModel):
    source_repo: str
    source_subdir: str
    installed_at: str
    ref: str = "HEAD"


class TelemetryConfig(BaseModel):
    enabled: bool = Field(default=True, description="Enable telemetry")
    umami_url: str = Field(
        default="https://analytics.victorbeysseriat.fr",
        description="Umami instance URL",
    )
    website_id: str = Field(
        default="1cc92fce-83fc-4792-9b02-e28a04810426",
        description="Umami website UUID",
    )


class GlobalConfig(BaseModel):
    version: int = Field(default=1)
    registries: dict[str, RegistrySource] = Field(default_factory=dict)
    resources: dict[str, Resource] = Field(default_factory=dict)
    telemetry: TelemetryConfig = Field(default_factory=TelemetryConfig)

    @classmethod
    def from_yaml(cls, path: Path) -> "GlobalConfig":
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data) if data else cls()

    def to_yaml(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)
