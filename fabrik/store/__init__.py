"""Global store — manages ~/.fabrik/ directory."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from fabrik.models import GlobalConfig, Resource, ResourceKind, TelemetryConfig


FABRIK_HOME = Path.home() / ".fabrik"


class GlobalStore:
    """Manages the global Fabrik store at ~/.fabrik/."""

    def __init__(self) -> None:
        self.root = FABRIK_HOME
        self.store_dir = self.root / "store"
        self.skills_dir = self.store_dir / "skills"
        self.mcps_dir = self.store_dir / "mcps"
        self.config_path = self.root / "config.yaml"
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.mcps_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> GlobalConfig:
        return GlobalConfig.from_yaml(self.config_path)

    def _save_config(self, config: GlobalConfig) -> None:
        config.to_yaml(self.config_path)

    def _type_dir(self, kind: ResourceKind) -> Path:
        return self.skills_dir if kind == ResourceKind.skill else self.mcps_dir

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
        del config.resources[key]
        self._save_config(config)

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
