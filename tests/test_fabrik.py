"""Tests for Fabrik models, store, core, and CLI."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from fabrik.models import (
    GlobalConfig,
    Link,
    RegistrySource,
    RegistryType,
    Resource,
    ResourceKind,
    ResourceRef,
    TelemetryConfig,
    WorkspaceConfig,
)
from fabrik.store import GlobalStore, FABRIK_HOME
from fabrik.core.workspace import Workspace


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        old_cwd = Path.cwd()
        os.chdir(d)
        yield Path(d)
        os.chdir(old_cwd)


@pytest.fixture
def isolated_store(monkeypatch, temp_dir):
    monkeypatch.setattr("fabrik.store.FABRIK_HOME", temp_dir / ".fabrik-home")
    return GlobalStore()


@pytest.fixture
def fake_skill_dir(temp_dir):
    d = temp_dir / "my-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("# My Skill\nA test skill.")
    return d


@pytest.fixture
def fake_mcp_dir(temp_dir):
    d = temp_dir / "my-mcp"
    d.mkdir()
    (d / "config.yaml").write_text("name: my-mcp\ncommand: python server.py")
    return d


# ─── Models ──────────────────────────────────────────────────────────────────


class TestResourceKind:
    def test_values(self):
        assert ResourceKind.skill.value == "skill"
        assert ResourceKind.mcp.value == "mcp"


class TestResource:
    def test_valid_resource(self):
        r = Resource(
            name="web-scraper",
            kind=ResourceKind.skill,
            source="registry:community",
            path=Path("/tmp/skill"),
        )
        assert r.name == "web-scraper"

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError):
            Resource(
                name="has space",
                kind=ResourceKind.skill,
                source="local",
                path=Path("/tmp/skill"),
            )


class TestResourceRef:
    def test_defaults(self):
        ref = ResourceRef(
            name="test", kind=ResourceKind.skill, origin="global"
        )
        assert ref.linked is False
        assert ref.path is None


class TestWorkspaceConfig:
    def test_round_trip(self, temp_dir):
        config = WorkspaceConfig(agent="opencode")
        config.resources.append(
            ResourceRef(name="s1", kind=ResourceKind.skill, origin="global")
        )
        path = temp_dir / "fabrik.yaml"
        config.to_yaml(path)
        loaded = WorkspaceConfig.from_yaml(path)
        assert loaded.agent == "opencode"
        assert len(loaded.resources) == 1
        assert loaded.resources[0].name == "s1"

    def test_from_yaml_nonexistent(self, temp_dir):
        config = WorkspaceConfig.from_yaml(temp_dir / "nope.yaml")
        assert config.version == 1
        assert config.resources == []


class TestGlobalConfig:
    def test_round_trip(self, temp_dir):
        config = GlobalConfig()
        r = Resource(
            name="s1",
            kind=ResourceKind.skill,
            source="local",
            path=Path("/tmp/s1"),
        )
        config.resources["skill:s1"] = r
        path = temp_dir / "config.yaml"
        config.to_yaml(path)
        loaded = GlobalConfig.from_yaml(path)
        assert "skill:s1" in loaded.resources
        assert loaded.resources["skill:s1"].name == "s1"
        assert loaded.resources["skill:s1"].kind == ResourceKind.skill

    def test_registry_source_round_trip(self, temp_dir):
        src = RegistrySource(
            name="my-reg", type=RegistryType.local, url_or_path="/tmp/reg"
        )
        data = src.model_dump(mode="json")
        loaded = RegistrySource(**data)
        assert loaded.name == "my-reg"
        assert loaded.type == RegistryType.local


# ─── Store Layer ─────────────────────────────────────────────────────────────


class TestGlobalStore:
    def test_init_creates_dirs(self, isolated_store):
        assert isolated_store.root.exists()
        assert isolated_store.skills_dir.exists()
        assert isolated_store.mcps_dir.exists()

    def test_add_resource_skill(self, isolated_store, fake_skill_dir):
        resource = isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "my-skill")
        assert resource.name == "my-skill"
        assert resource.kind == ResourceKind.skill
        assert resource.path.exists()
        assert (resource.path / "SKILL.md").exists()

    def test_add_resource_mcp(self, isolated_store, fake_mcp_dir):
        resource = isolated_store.add_resource(ResourceKind.mcp, fake_mcp_dir, "my-mcp")
        assert resource.name == "my-mcp"
        assert resource.kind == ResourceKind.mcp
        assert (resource.path / "config.yaml").exists()

    def test_add_duplicate_raises(self, isolated_store, fake_skill_dir):
        isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "dup")
        with pytest.raises(FileExistsError):
            isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "dup")

    def test_list_empty(self, isolated_store):
        assert isolated_store.list_resources() == []

    def test_list_resources(self, isolated_store, fake_skill_dir, fake_mcp_dir):
        isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "s1")
        isolated_store.add_resource(ResourceKind.mcp, fake_mcp_dir, "m1")
        all_res = isolated_store.list_resources()
        assert len(all_res) == 2
        skills = isolated_store.list_resources(ResourceKind.skill)
        assert len(skills) == 1
        assert skills[0].name == "s1"

    def test_remove_resource(self, isolated_store, fake_skill_dir):
        isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "to-go")
        isolated_store.remove_resource(ResourceKind.skill, "to-go")
        assert isolated_store.list_resources() == []

    def test_remove_nonexistent_raises(self, isolated_store):
        with pytest.raises(KeyError):
            isolated_store.remove_resource(ResourceKind.skill, "nope")


# ─── Telemetry ────────────────────────────────────────────────────────────────


class TestTelemetryConfig:
    def test_defaults(self):
        cfg = TelemetryConfig()
        assert cfg.enabled is True
        assert cfg.umami_url == "https://analytics.victorbeysseriat.fr"
        assert cfg.website_id == "1cc92fce-83fc-4792-9b02-e28a04810426"

    def test_custom_values(self):
        cfg = TelemetryConfig(
            enabled=False,
            umami_url="https://umami.example.com",
            website_id="abc-123",
        )
        assert cfg.enabled is False
        assert cfg.umami_url == "https://umami.example.com"
        assert cfg.website_id == "abc-123"


class TestGlobalStoreTelemetry:
    def test_get_default_config(self, isolated_store):
        cfg = isolated_store.get_telemetry_config()
        assert cfg.enabled is True
        assert cfg.umami_url == "https://analytics.victorbeysseriat.fr"
        assert cfg.website_id == "1cc92fce-83fc-4792-9b02-e28a04810426"

    def test_set_and_get_config(self, isolated_store):
        original = TelemetryConfig(
            enabled=False,
            umami_url="https://umami.example.com",
            website_id="abc-123",
        )
        isolated_store.set_telemetry_config(original)
        loaded = isolated_store.get_telemetry_config()
        assert loaded.enabled is False
        assert loaded.umami_url == "https://umami.example.com"
        assert loaded.website_id == "abc-123"

    def test_env_overrides(self, isolated_store, monkeypatch):
        monkeypatch.setenv("FABRIK_UMAMI_URL", "https://env.umami.com")
        monkeypatch.setenv("FABRIK_WEBSITE_ID", "env-456")
        cfg = isolated_store.get_telemetry_config()
        assert cfg.umami_url == "https://env.umami.com"
        assert cfg.website_id == "env-456"

    def test_env_disable(self, isolated_store, monkeypatch):
        monkeypatch.setenv("FABRIK_TELEMETRY", "0")
        cfg = isolated_store.get_telemetry_config()
        assert cfg.enabled is False

    def test_env_disable_false(self, isolated_store, monkeypatch):
        monkeypatch.setenv("FABRIK_TELEMETRY", "false")
        cfg = isolated_store.get_telemetry_config()
        assert cfg.enabled is False


class TestWorkspace:
    def test_init_no_dir(self, temp_dir):
        ws = Workspace(temp_dir)
        assert not ws.exists()

    def test_init_creates_structure(self, temp_dir):
        ws = Workspace(temp_dir)
        config = ws.init(agent="opencode")
        assert ws.exists()
        assert config.agent == "opencode"
        assert (temp_dir / ".fabrik").is_dir()
        assert (temp_dir / ".fabrik" / "fabrik.yaml").exists()

    def test_add_and_list_resources(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init()
        ref = ResourceRef(name="s1", kind=ResourceKind.skill, origin="global")
        ws.add_resource(ref)
        resources = ws.list_resources()
        assert len(resources) == 1
        assert resources[0].name == "s1"

    def test_add_duplicate_raises(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init()
        ref = ResourceRef(name="s1", kind=ResourceKind.skill, origin="global")
        ws.add_resource(ref)
        with pytest.raises(ValueError):
            ws.add_resource(ref)

    def test_remove_resource(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init()
        ws.add_resource(ResourceRef(name="s1", kind=ResourceKind.skill, origin="global"))
        ws.remove_resource(ResourceKind.skill, "s1")
        assert ws.list_resources() == []

    def test_links_workflow(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init()
        link = Link(
            name="s1",
            kind=ResourceKind.skill,
            target=Path("/tmp/s1"),
            link_path=Path("/tmp/.fabrik/links/skills/s1"),
        )
        ws.add_link(link)
        assert len(ws.list_links()) == 1
        ws.remove_link(ResourceKind.skill, "s1")
        assert ws.list_links() == []

    def test_linked_flag(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init()
        ref = ResourceRef(name="s1", kind=ResourceKind.skill, origin="global")
        ws.add_resource(ref)
        ws.add_link(
            Link(name="s1", kind=ResourceKind.skill, target=Path("/tmp/s1"), link_path=Path("/tmp/s1"))
        )
        resources = ws.list_resources()
        assert resources[0].linked is True


# ─── Integration: CLI ────────────────────────────────────────────────────────


class TestCLIIntegration:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, temp_dir):
        monkeypatch.setattr("fabrik.store.FABRIK_HOME", temp_dir / ".fabrik-home")
        monkeypatch.setattr("fabrik.core.registry.REGISTRIES_PATH", temp_dir / ".fabrik-home" / "registries.yaml")
        monkeypatch.setattr("fabrik.core.registry.REGISTRY_CACHE", temp_dir / ".fabrik-home" / "cache")
    def test_help(self):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "MCP/Skills manager" in result.output

    def test_version(self):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "fabrik v" in result.output

    def test_init_and_status(self, temp_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Workspace created" in result.output
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Workspace Status" in result.output

    def test_init_with_agent(self, temp_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init", "--agent", "opencode"])
        assert result.exit_code == 0
        assert "opencode" in result.output

    def test_global_add_ls_rm(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        assert result.exit_code == 0
        result = runner.invoke(app, ["global", "ls"])
        assert result.exit_code == 0
        assert "test-skill" in result.output
        result = runner.invoke(app, ["global", "rm", "skill", "test-skill"])
        assert result.exit_code == 0

    def test_add_rm_resource(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        result = runner.invoke(app, ["add", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "Added" in result.output
        result = runner.invoke(app, ["rm", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_link_unlink(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        result = runner.invoke(app, ["link", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "Linked" in result.output
        result = runner.invoke(app, ["unlink", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "Unlinked" in result.output

    def test_info(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        result = runner.invoke(app, ["info", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "test-skill" in result.output

    def test_ls_json(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        result = runner.invoke(app, ["ls", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "test-skill"

    def test_registry_lifecycle(self, temp_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["registry", "add", str(temp_dir), "--name", "test-reg"])
        assert result.exit_code == 0
        result = runner.invoke(app, ["registry", "ls"])
        assert result.exit_code == 0
        assert "test-reg" in result.output

    def test_registry_search(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["registry", "add", str(fake_skill_dir.parent), "--name", "test-reg"])
        result = runner.invoke(app, ["registry", "search", "my-skill"])
        assert result.exit_code == 0

    def test_agent_detect(self, temp_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["agent", "detect"])
        assert result.exit_code == 0

    def test_telemetry_status_active_by_default(self, temp_dir):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["telemetry", "status"])
        assert result.exit_code == 0
        assert "active" in result.output.lower()
        assert "analytics.victorbeysseriat.fr" in result.output

    def test_telemetry_on_off_lifecycle(self, temp_dir, monkeypatch):
        from typer.testing import CliRunner
        from fabrik.cli.main import app
        from fabrik.store import GlobalStore

        monkeypatch.setenv("FABRIK_UMAMI_URL", "https://umami.test")
        monkeypatch.setenv("FABRIK_WEBSITE_ID", "test-id")

        runner = CliRunner()
        result = runner.invoke(app, ["telemetry", "on"])
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()

        store = GlobalStore()
        cfg = store.get_telemetry_config()
        assert cfg.enabled is True

        result = runner.invoke(app, ["telemetry", "off"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()

        cfg = store.get_telemetry_config()
        assert cfg.enabled is False
