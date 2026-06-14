"""Global store — manages ~/.fabrik/ directory."""

from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from fabrik.models import GlobalConfig, Resource, ResourceKind, SourceMetadata, TelemetryConfig


FABRIK_HOME = Path.home() / ".fabrik"
SOURCE_META_FILENAME = ".fabrik-source.yaml"


class GlobalStore:
    """Manages the global Fabrik store at ~/.fabrik/."""

    def __init__(self) -> None:
        self.root = FABRIK_HOME
        self.store_dir = self.root / "store"
        self.skills_dir = self.store_dir / "skills"
        self.config_path = self.root / "config.yaml"
        self.cache_dir = self.root / "cache"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> GlobalConfig:
        return GlobalConfig.from_yaml(self.config_path)

    def _save_config(self, config: GlobalConfig) -> None:
        config.to_yaml(self.config_path)

    def _type_dir(self, kind: ResourceKind) -> Path:
        return self.skills_dir

    def add_resource(
        self, kind: ResourceKind, source_path: Path, name: Optional[str] = None
    ) -> Resource:
        src = source_path.resolve()
        if not src.exists():
            raise FileNotFoundError(f"Resource not found: {src}")
        name = name or src.name
        dest = self._type_dir(kind) / name
        if dest.exists():
            raise FileExistsError(f"Resource '{name}' already exists in global store")
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        resource = Resource(
            name=name,
            kind=kind,
            source=str(src),
            path=dest,
        )
        config = self._load_config()
        config.resources[f"{kind.value}:{name}"] = resource
        self._save_config(config)
        return resource

    def remove_resource(self, kind: ResourceKind, name: str) -> None:
        key = f"{kind.value}:{name}"
        config = self._load_config()
        if key not in config.resources:
            raise KeyError(f"Resource '{name}' not found in global store")
        dest = self._type_dir(kind) / name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        self.remove_source_metadata(kind, name)
        del config.resources[key]
        self._save_config(config)

    def add_resource_from_git(
        self,
        kind: ResourceKind,
        name: str,
        repo_url: str,
        subdir: Optional[str] = None,
        ref: str = "HEAD",
    ) -> Resource:
        from fabrik.core.registry import RegistryManager

        registry = RegistryManager()
        cache_path = registry.clone_or_fetch(repo_url, name, ref=ref)

        if subdir:
            src = cache_path / subdir
        else:
            # Try standard layouts in priority order:
            # 1. skills/<name> subdirectory (multi-skill repo)
            # 2. repo root (single-skill repo with SKILL.md at root)
            # 3. <name> subdirectory (repo with nested subdir of same name)
            candidate = cache_path / "skills" / name
            if candidate.exists():
                src = candidate
            elif (cache_path / "SKILL.md").exists():
                src = cache_path
            else:
                src = cache_path / name

        if not src.exists() or not src.is_dir():
            raise FileNotFoundError(
                f"Skill directory '{name}' not found at expected path '{src}' in repo '{repo_url}'."
            )

        dest = self._type_dir(kind) / name
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.copytree(src, dest)

        resource = Resource(
            name=name,
            kind=kind,
            source=repo_url,
            path=dest,
        )
        config = self._load_config()
        config.resources[f"{kind.value}:{name}"] = resource
        self._save_config(config)

        self.save_source_metadata(
            kind,
            name,
            SourceMetadata(
                source_repo=repo_url,
                source_subdir=str(subdir or f"skills/{name}"),
                installed_at=datetime.now(timezone.utc).isoformat(),
                ref=ref,
            ),
        )
        return resource

    def _source_meta_path(self, kind: ResourceKind, name: str) -> Path:
        return self._type_dir(kind) / name / SOURCE_META_FILENAME

    def save_source_metadata(self, kind: ResourceKind, name: str, meta: SourceMetadata) -> None:
        meta_path = self._source_meta_path(kind, name)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        with open(meta_path, "w") as f:
            yaml.dump(meta.model_dump(mode="json"), f, default_flow_style=False)

    def get_source_metadata(self, kind: ResourceKind, name: str) -> Optional[SourceMetadata]:
        meta_path = self._source_meta_path(kind, name)
        if not meta_path.exists():
            return None
        with open(meta_path) as f:
            data = yaml.safe_load(f)
        if not data:
            return None
        return SourceMetadata(**data)

    def remove_source_metadata(self, kind: ResourceKind, name: str) -> None:
        meta_path = self._source_meta_path(kind, name)
        if meta_path.exists():
            meta_path.unlink()

    def list_resources(self, kind: Optional[ResourceKind] = None) -> list[Resource]:
        config = self._load_config()
        resources = list(config.resources.values())
        if kind:
            resources = [r for r in resources if r.kind == kind]
        return sorted(resources, key=lambda r: r.name)

    def get_resource(self, kind: ResourceKind, name: str) -> Optional[Resource]:
        config = self._load_config()
        return config.resources.get(f"{kind.value}:{name}")

    def get_telemetry_config(self) -> TelemetryConfig:
        config = self._load_config()
        cfg = config.telemetry

        if "FABRIK_TELEMETRY" in os.environ:
            enabled = os.environ["FABRIK_TELEMETRY"] not in (
                "0",
                "false",
                "no",
                "off",
                "",
            )
        else:
            enabled = cfg.enabled

        return TelemetryConfig(
            enabled=enabled,
            umami_url=os.environ.get("FABRIK_UMAMI_URL") or cfg.umami_url,
            website_id=os.environ.get("FABRIK_WEBSITE_ID") or cfg.website_id,
        )

    def set_telemetry_config(self, cfg: TelemetryConfig) -> None:
        config = self._load_config()
        config.telemetry = cfg
        self._save_config(config)
