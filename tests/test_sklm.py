"""Tests for Sklm models, store, core, and CLI."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from sklm.models import (
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
from sklm.store import GlobalStore, SKLM_HOME
from sklm.core.workspace import Workspace


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
    monkeypatch.setattr("sklm.store.SKLM_HOME", temp_dir / ".sklm-home")
    return GlobalStore()


@pytest.fixture
def fake_skill_dir(temp_dir):
    d = temp_dir / "my-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("# My Skill\nA test skill.")
    return d





# ─── Models ──────────────────────────────────────────────────────────────────


class TestResourceKind:
    def test_values(self):
        assert ResourceKind.skill.value == "skill"


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
        config = WorkspaceConfig(agents=["opencode"])
        config.resources.append(
            ResourceRef(name="s1", kind=ResourceKind.skill, origin="global")
        )
        path = temp_dir / "sklm.yaml"
        config.to_yaml(path)
        loaded = WorkspaceConfig.from_yaml(path)
        assert loaded.agents == ["opencode"]
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


class TestNestedSkillResolution:
    """Tests pour add_resource_from_git avec structures imbriquées."""

    def _make_repo(self, root: Path, skill_paths: dict[str, str]) -> Path:
        """Helper: crée une fausse arborescence de repo cloné.
        skill_paths = { "rel/path/to/skill_dir": "SKILL.md content", ... }
        """
        for rel_path, content in skill_paths.items():
            d = root / rel_path
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(content)
        return root

    def test_finds_nested_skill_two_levels(self, isolated_store, temp_dir):
        """skills/<category>/<name>/SKILL.md doit être trouvé."""
        from sklm.models import ResourceKind

        cache_dir = isolated_store.cache_dir / "test-nested-2"
        self._make_repo(cache_dir, {
            "skills/seo/entity-seo": "# Entity SEO",
        })
        with unittest.mock.patch("sklm.core.registry.RegistryManager") as MockReg:
            MockReg.return_value.clone_or_fetch.return_value = cache_dir
            resource = isolated_store.add_resource_from_git(
                ResourceKind.skill, "entity-seo", "https://github.com/test/repo"
            )
        assert resource.name == "entity-seo"
        assert resource.path.exists()
        assert (resource.path / "SKILL.md").read_text() == "# Entity SEO"

    def test_finds_nested_skill_three_levels(self, isolated_store, temp_dir):
        """skills/<cat>/<sub>/<name>/SKILL.md doit être trouvé."""
        from sklm.models import ResourceKind

        cache_dir = isolated_store.cache_dir / "test-nested-3"
        self._make_repo(cache_dir, {
            "skills/paid-ads/platforms/reddit-ads": "# Reddit Ads",
        })
        with unittest.mock.patch("sklm.core.registry.RegistryManager") as MockReg:
            MockReg.return_value.clone_or_fetch.return_value = cache_dir
            resource = isolated_store.add_resource_from_git(
                ResourceKind.skill, "reddit-ads", "https://github.com/test/repo"
            )
        assert resource.name == "reddit-ads"
        assert resource.path.exists()
        assert (resource.path / "SKILL.md").read_text() == "# Reddit Ads"

    def test_flat_structure_still_takes_priority(self, isolated_store, temp_dir):
        """skills/<name>/ (flat) doit être prioritaire sur skills/<cat>/<name>/."""
        from sklm.models import ResourceKind

        cache_dir = isolated_store.cache_dir / "test-priority"
        self._make_repo(cache_dir, {
            "skills/my-skill": "# Flat Skill",
            "skills/category/my-skill": "# Nested Skill",
        })
        with unittest.mock.patch("sklm.core.registry.RegistryManager") as MockReg:
            MockReg.return_value.clone_or_fetch.return_value = cache_dir
            resource = isolated_store.add_resource_from_git(
                ResourceKind.skill, "my-skill", "https://github.com/test/repo"
            )
        assert (resource.path / "SKILL.md").read_text() == "# Flat Skill"

    def test_not_found_error_lists_available(self, isolated_store, temp_dir):
        """Quand aucun skill n'est trouvé, le message doit lister les disponibles."""
        from sklm.models import ResourceKind

        cache_dir = isolated_store.cache_dir / "test-not-found"
        self._make_repo(cache_dir, {
            "skills/seo/entity-seo": "# Entity SEO",
            "skills/seo/on-page": "# On Page SEO",
            "skills/channels/email/email-marketing": "# Email Marketing",
        })
        with unittest.mock.patch("sklm.core.registry.RegistryManager") as MockReg:
            MockReg.return_value.clone_or_fetch.return_value = cache_dir
            with pytest.raises(FileNotFoundError) as exc:
                isolated_store.add_resource_from_git(
                    ResourceKind.skill, "nonexistent", "https://github.com/test/repo"
                )
        msg = str(exc.value)
        assert "entity-seo" in msg
        assert "on-page" in msg
        assert "email-marketing" in msg
        assert "--subdir" in msg

    def test_source_subdir_reflects_nested_path(self, isolated_store, temp_dir):
        """source_subdir dans les métadonnées doit refléter le chemin réel."""
        from sklm.models import ResourceKind

        cache_dir = isolated_store.cache_dir / "test-subdir-meta"
        self._make_repo(cache_dir, {
            "skills/seo/entity-seo": "# Entity SEO",
        })
        with unittest.mock.patch("sklm.core.registry.RegistryManager") as MockReg:
            MockReg.return_value.clone_or_fetch.return_value = cache_dir
            isolated_store.add_resource_from_git(
                ResourceKind.skill, "entity-seo", "https://github.com/test/repo"
            )
        meta = isolated_store.get_source_metadata(ResourceKind.skill, "entity-seo")
        assert meta is not None
        assert meta.source_subdir == "skills/seo/entity-seo"


class TestGlobalStore:
    def test_init_creates_dirs(self, isolated_store):
        assert isolated_store.root.exists()
        assert isolated_store.skills_dir.exists()

    def test_add_resource_skill(self, isolated_store, fake_skill_dir):
        resource = isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "my-skill")
        assert resource.name == "my-skill"
        assert resource.kind == ResourceKind.skill
        assert resource.path.exists()
        assert (resource.path / "SKILL.md").exists()

    def test_add_duplicate_raises(self, isolated_store, fake_skill_dir):
        isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "dup")
        with pytest.raises(FileExistsError):
            isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "dup")

    def test_list_empty(self, isolated_store):
        assert isolated_store.list_resources() == []

    def test_list_resources(self, isolated_store, fake_skill_dir):
        isolated_store.add_resource(ResourceKind.skill, fake_skill_dir, "s1")
        all_res = isolated_store.list_resources()
        assert len(all_res) == 1
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
        monkeypatch.setenv("SKLM_UMAMI_URL", "https://env.umami.com")
        monkeypatch.setenv("SKLM_WEBSITE_ID", "env-456")
        cfg = isolated_store.get_telemetry_config()
        assert cfg.umami_url == "https://env.umami.com"
        assert cfg.website_id == "env-456"

    def test_env_disable(self, isolated_store, monkeypatch):
        monkeypatch.setenv("SKLM_TELEMETRY", "0")
        cfg = isolated_store.get_telemetry_config()
        assert cfg.enabled is False

    def test_env_disable_false(self, isolated_store, monkeypatch):
        monkeypatch.setenv("SKLM_TELEMETRY", "false")
        cfg = isolated_store.get_telemetry_config()
        assert cfg.enabled is False


class TestUmamiTracker:
    """Tests for UmamiTracker.track_command enriched error fields."""

    def _make_tracker(self, active=True):
        from sklm.telemetry import UmamiTracker
        return UmamiTracker(
            umami_url="https://umami.test" if active else "",
            website_id="test-id" if active else "",
            enabled=active,
        )

    def test_error_fields_included(self):
        tracker = self._make_tracker()
        tracker._send_event = lambda name, data: None
        events: list[dict] = []

        def fake_send(event_name, custom_data):
            events.append(custom_data)

        tracker._send_event = fake_send
        tracker.track_command(
            "test-cmd", success=False, duration_ms=100,
            error_type="ValueError", error_message="bad value", traceback="  File test.py, line 1",
        )
        assert len(events) == 1
        data = events[0]
        assert data["error"] == "ValueError"
        assert data["error_message"] == "bad value"
        assert data["traceback"] == "  File test.py, line 1"
        assert data["success"] is False

    def test_no_error_fields_on_success(self):
        tracker = self._make_tracker()
        events: list[dict] = []

        def fake_send(event_name, custom_data):
            events.append(custom_data)

        tracker._send_event = fake_send
        tracker.track_command(
            "test-cmd", success=True, duration_ms=100,
            error_type=None, error_message="should not appear", traceback="should not appear",
        )
        assert len(events) == 1
        data = events[0]
        assert "error_message" not in data
        assert "traceback" not in data
        assert "error" not in data

    def test_no_error_fields_when_omitted(self):
        tracker = self._make_tracker()
        events: list[dict] = []

        def fake_send(event_name, custom_data):
            events.append(custom_data)

        tracker._send_event = fake_send
        tracker.track_command("test-cmd", success=False, duration_ms=100, error_type="KeyError")
        assert len(events) == 1
        data = events[0]
        assert data["error"] == "KeyError"
        assert "error_message" not in data
        assert "traceback" not in data


class TestCLIErrorTelemetry:
    """Tests that CLI error chain (raise from) and run() capture work correctly."""

    def test_run_extracts_cause_from_system_exit(self, monkeypatch):
        """run() extracts error_type, error_message, and traceback from __cause__."""
        import traceback
        from sklm.cli.main import run

        events: list[dict] = []

        def fake_track_command(command, success, duration_ms, error_type=None,
                               error_message=None, traceback=None, dry_run=False):
            events.append(dict(
                command=command, success=success, error_type=error_type,
                error_message=error_message, traceback=traceback,
            ))

        tracker = MagicMock()
        tracker.track_command.side_effect = fake_track_command
        monkeypatch.setattr("sklm.cli.main._tracker_start", 1000.0)
        monkeypatch.setattr("sklm.cli.main._tracker_command", "test-cmd")
        monkeypatch.setattr("sklm.cli.main.get_tracker", lambda: tracker)

        original_app = None
        def failing_app():
            try:
                raise ValueError("something went wrong")
            except ValueError as e:
                raise SystemExit(1) from e

        monkeypatch.setattr("sklm.cli.main.app", failing_app)
        try:
            run()
        except SystemExit:
            pass

        assert len(events) == 1
        data = events[0]
        assert data["success"] is False
        assert data["error_type"] == "ValueError"
        assert "something went wrong" in data["error_message"]

    def test_raise_typer_exit_from_e_chains_exception(self):
        """Verify raise typer.Exit(1) from e sets __cause__ properly."""
        import typer
        try:
            try:
                raise FileNotFoundError("resource not found")
            except FileNotFoundError as e:
                raise typer.Exit(1) from e
        except typer.Exit as e:
            cause = getattr(e, "__cause__", None)
            assert cause is not None
            assert isinstance(cause, FileNotFoundError)
            assert "resource not found" in str(cause)


class TestWorkspace:
    def test_init_no_dir(self, temp_dir):
        ws = Workspace(temp_dir)
        assert not ws.exists()

    def test_init_creates_structure(self, temp_dir):
        ws = Workspace(temp_dir)
        config = ws.init(agents=["opencode"])
        assert ws.exists()
        assert config.agents == ["opencode"]
        assert (temp_dir / ".sklm").is_dir()
        assert (temp_dir / ".sklm" / "sklm.yaml").exists()

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
            link_path=Path("/tmp/.sklm/links/skills/s1"),
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


# ─── Agent Registry ───────────────────────────────────────────────────────────


class TestAgentRegistry:
    def test_loads_all_agents(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        registry = AgentRegistry()
        agents = registry.get_agent_ids()
        assert len(agents) == 8
        assert "opencode" in agents
        assert "claude" in agents
        assert "cursor" in agents
        assert "windsurf" in agents
        assert "gemini" in agents
        assert "cline" in agents
        assert "amazon-q" in agents
        assert "github-copilot" in agents

    def test_detect_returns_none_when_no_agent_dir(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        registry = AgentRegistry()
        assert registry.detect(temp_dir) == []

    def test_detect_opencode(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        (temp_dir / ".opencode").mkdir()
        registry = AgentRegistry()
        assert registry.detect(temp_dir) == ["opencode"]

    def test_detect_priority_order(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        (temp_dir / ".opencode").mkdir()
        (temp_dir / ".claude").mkdir()
        registry = AgentRegistry()
        assert registry.detect(temp_dir) == ["opencode", "claude"]

    def test_get_adapter_returns_generic(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        registry = AgentRegistry()
        adapter = registry.get_adapter("cursor")
        from sklm.agents.generic import GenericAdapter
        assert isinstance(adapter, GenericAdapter)

    def test_get_adapter_handles_github_copilot(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        registry = AgentRegistry()
        adapter = registry.get_adapter("github-copilot")
        from sklm.agents.github_copilot import GitHubCopilotAdapter
        assert isinstance(adapter, GitHubCopilotAdapter)

    def test_get_adapter_returns_none_for_unknown(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        registry = AgentRegistry()
        assert registry.get_adapter("nonexistent") is None

    def test_list_agents_shows_active(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        (temp_dir / ".cursor").mkdir()
        registry = AgentRegistry()
        agents = registry.list_agents(temp_dir)
        cursor = [a for a in agents if a["id"] == "cursor"][0]
        assert cursor["active"] is True
        opencode = [a for a in agents if a["id"] == "opencode"][0]
        assert opencode["active"] is False

    def test_detect_adapter_returns_adapter(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        (temp_dir / ".claude").mkdir()
        registry = AgentRegistry()
        adapter = registry.detect_adapter(temp_dir)
        from sklm.agents.generic import GenericAdapter
        assert isinstance(adapter, GenericAdapter)

    def test_copilot_not_auto_detected(self, temp_dir):
        from sklm.agents.registry import AgentRegistry
        (temp_dir / ".github").mkdir()
        registry = AgentRegistry()
        assert registry.detect(temp_dir) == []


# ─── GenericAdapter ──────────────────────────────────────────────────────────


class TestGenericAdapter:
    def test_detect(self, temp_dir):
        from sklm.agents.generic import GenericAdapter
        (temp_dir / ".cursor").mkdir()
        adapter = GenericAdapter("cursor", {"dir_name": ".cursor"})
        assert adapter.detect(temp_dir) is True

    def test_no_detect_without_dir(self, temp_dir):
        from sklm.agents.generic import GenericAdapter
        adapter = GenericAdapter("cursor", {"dir_name": ".cursor"})
        assert adapter.detect(temp_dir) is False

    def test_get_skills_path(self, temp_dir):
        from sklm.agents.generic import GenericAdapter
        adapter = GenericAdapter("cursor", {"dir_name": ".cursor"})
        assert adapter.get_skills_path(temp_dir) == temp_dir / ".cursor" / "skills"

    def test_sync_creates_skills(self, temp_dir):
        from sklm.agents.generic import GenericAdapter
        from sklm.models import Link, ResourceKind
        skill_dir = temp_dir / "source-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test")
        link = Link(
            name="test-skill",
            kind=ResourceKind.skill,
            target=skill_dir,
            link_path=skill_dir,
        )
        adapter = GenericAdapter("cursor", {"dir_name": ".cursor"})
        adapter.sync(temp_dir, [link])
        assert (temp_dir / ".cursor" / "skills" / "test-skill" / "SKILL.md").exists()

    def test_sync_removes_unlinked(self, temp_dir):
        from sklm.agents.generic import GenericAdapter
        from sklm.models import Link, ResourceKind
        skill_dir = temp_dir / "source-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Test")
        link = Link(
            name="test-skill",
            kind=ResourceKind.skill,
            target=skill_dir,
            link_path=skill_dir,
        )
        adapter = GenericAdapter("cursor", {"dir_name": ".cursor"})
        adapter.sync(temp_dir, [link])
        assert (temp_dir / ".cursor" / "skills" / "test-skill").exists()
        adapter.sync(temp_dir, [])
        assert not (temp_dir / ".cursor" / "skills" / "test-skill").exists()


# ─── GitHubCopilotAdapter ────────────────────────────────────────────────────


class TestGitHubCopilotAdapter:
    def test_detect_always_false(self, temp_dir):
        from sklm.agents.github_copilot import GitHubCopilotAdapter
        (temp_dir / ".github").mkdir()
        adapter = GitHubCopilotAdapter()
        assert adapter.detect(temp_dir) is False

    def test_get_skills_path(self, temp_dir):
        from sklm.agents.github_copilot import GitHubCopilotAdapter
        adapter = GitHubCopilotAdapter()
        assert adapter.get_skills_path(temp_dir) == temp_dir / ".github" / "skills"


# ─── Agent Kind ───────────────────────────────────────────────────────────────


class TestAgentKind:
    def test_known_agents(self):
        from sklm.models import AgentKind
        assert AgentKind("opencode") == AgentKind.opencode
        assert AgentKind("claude") == AgentKind.claude
        assert AgentKind("cursor") == AgentKind.cursor
        assert AgentKind("windsurf") == AgentKind.windsurf
        assert AgentKind("gemini") == AgentKind.gemini
        assert AgentKind("cline") == AgentKind.cline
        assert AgentKind("amazon-q") == AgentKind.amazon_q
        assert AgentKind("github-copilot") == AgentKind.github_copilot

    def test_unknown_agent_raises(self):
        from sklm.models import AgentKind
        with pytest.raises(ValueError):
            AgentKind("nonexistent-agent")

    def test_workspace_config_validates_agent(self, temp_dir):
        from sklm.models import WorkspaceConfig
        config = WorkspaceConfig(agents=["claude"])
        assert config.agents == ["claude"]

    def test_workspace_config_rejects_unknown(self, temp_dir):
        from sklm.models import WorkspaceConfig
        with pytest.raises(ValueError, match="Unknown agent"):
            WorkspaceConfig(agents=["nonexistent-agent"])

    def test_workspace_config_accepts_none(self, temp_dir):
        from sklm.models import WorkspaceConfig
        config = WorkspaceConfig(agents=["none"])
        assert config.agents == ["none"]


# ─── Multi-agent / Tests additionnels ──────────────────────────────────────


class TestMultiAgentWorkspaceConfig:
    def test_default_agents_list(self):
        config = WorkspaceConfig()
        assert config.agents == ["none"]

    def test_single_agent(self):
        config = WorkspaceConfig(agents=["opencode"])
        assert config.agents == ["opencode"]

    def test_multiple_agents(self):
        config = WorkspaceConfig(agents=["opencode", "claude"])
        assert config.agents == ["opencode", "claude"]

    def test_rejects_unknown_agent(self):
        with pytest.raises(ValueError, match="Unknown agent"):
            WorkspaceConfig(agents=["nonexistent"])

    def test_accepts_none_in_list(self):
        config = WorkspaceConfig(agents=["none"])
        assert config.agents == ["none"]

    def test_yaml_round_trip_multiple(self, temp_dir):
        config = WorkspaceConfig(agents=["cursor", "gemini"])
        path = temp_dir / "sklm.yaml"
        config.to_yaml(path)
        loaded = WorkspaceConfig.from_yaml(path)
        assert loaded.agents == ["cursor", "gemini"]

    def test_strips_none_when_real_agents_present(self):
        config = WorkspaceConfig(agents=["none", "opencode"])
        assert config.agents == ["opencode"]

    def test_strips_none_from_mixed_list(self):
        config = WorkspaceConfig(agents=["none", "opencode", "claude"])
        assert config.agents == ["opencode", "claude"]

    def test_normalizes_empty_list_to_none(self):
        config = WorkspaceConfig(agents=[])
        assert config.agents == ["none"]

    def test_collapses_duplicate_none(self):
        config = WorkspaceConfig(agents=["none", "none"])
        assert config.agents == ["none"]


class TestMultiAgentWorkspace:
    def test_set_agents_replaces(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init()
        ws.set_agents(["cursor", "gemini"])
        config = ws.load_config()
        assert config.agents == ["cursor", "gemini"]

    def test_add_agent(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init(agents=["opencode"])
        ws.add_agent("claude")
        config = ws.load_config()
        assert config.agents == ["opencode", "claude"]

    def test_add_agent_idempotent(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init(agents=["opencode"])
        ws.add_agent("opencode")
        config = ws.load_config()
        assert config.agents == ["opencode"]

    def test_remove_agent(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init(agents=["opencode", "claude"])
        ws.remove_agent("claude")
        config = ws.load_config()
        assert config.agents == ["opencode"]

    def test_remove_agent_raises_if_not_found(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init(agents=["opencode"])
        with pytest.raises(KeyError):
            ws.remove_agent("nonexistent")

    def test_add_agent_to_none_workspace_strips_sentinel(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init(agents=["none"])
        ws.add_agent("opencode")
        config = ws.load_config()
        assert config.agents == ["opencode"]

    def test_remove_last_agent_resets_to_none(self, temp_dir):
        ws = Workspace(temp_dir)
        ws.init(agents=["opencode"])
        ws.remove_agent("opencode")
        config = ws.load_config()
        assert config.agents == ["none"]


class TestMultiAgentCLI:
    """CLI tests for multi-agent init, add/remove, warnings."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, temp_dir):
        monkeypatch.setattr("sklm.store.SKLM_HOME", temp_dir / ".sklm-home")
        monkeypatch.setattr("sklm.core.registry.REGISTRIES_PATH", temp_dir / ".sklm-home" / "registries.yaml")
        monkeypatch.setattr("sklm.core.registry.REGISTRY_CACHE", temp_dir / ".sklm-home" / "cache")
        monkeypatch.setattr("sklm.cli.main._sklm", None)

    def test_init_repeatable_agent(self, temp_dir):
        """sklm init --agent opencode --agent claude doit configurer les deux."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init", "--agent", "opencode", "--agent", "claude"])
        assert result.exit_code == 0
        assert "opencode" in result.output
        assert "claude" in result.output
        from sklm.api import Sklm
        f = Sklm()
        config = f.workspace.load_config()
        assert config.agents == ["opencode", "claude"]

    def test_init_multiple_agents_syncs_dirs(self, temp_dir):
        """sklm init --agent opencode --agent claude doit créer les deux dossiers skills."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init", "--agent", "opencode", "--agent", "claude"])
        assert result.exit_code == 0
        assert (temp_dir / ".opencode" / "skills").is_dir()
        assert (temp_dir / ".claude" / "skills").is_dir()

    def test_init_prompt_cancel(self, temp_dir):
        """sklm init (sans --agent, sans dossier) avec cancel → agents: none."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init"], input="c\n")
        assert result.exit_code == 0
        assert "none" in result.output
        from sklm.api import Sklm
        f = Sklm()
        config = f.workspace.load_config()
        assert config.agents == ["none"]

    def test_init_prompt_selects_one(self, temp_dir):
        """sklm init (sans --agent, sans dossier) avec choix 1 → opencode."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init"], input="1\n")
        assert result.exit_code == 0
        assert "opencode" in result.output
        from sklm.api import Sklm
        f = Sklm()
        config = f.workspace.load_config()
        assert config.agents == ["opencode"]
        assert (temp_dir / ".opencode" / "skills").is_dir()

    def test_agent_add_command(self, temp_dir):
        """sklm agent add claude après init doit configurer Claude."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init", "--agent", "opencode"])
        result = runner.invoke(app, ["agent", "add", "claude"])
        assert result.exit_code == 0
        from sklm.api import Sklm
        f = Sklm()
        config = f.workspace.load_config()
        assert "claude" in config.agents
        assert (temp_dir / ".claude" / "skills").is_dir()

    def test_agent_add_unknown(self, temp_dir):
        """sklm agent add unknown doit échouer."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init", "--agent", "opencode"])
        result = runner.invoke(app, ["agent", "add", "nonexistent"])
        assert result.exit_code != 0
        assert "Unknown" in result.output

    def test_agent_remove_command(self, temp_dir):
        """sklm agent remove claude après add doit retirer Claude de la config."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init", "--agent", "opencode", "--agent", "claude"])
        result = runner.invoke(app, ["agent", "remove", "claude"])
        assert result.exit_code == 0
        from sklm.api import Sklm
        f = Sklm()
        config = f.workspace.load_config()
        assert config.agents == ["opencode"]

    def test_add_warns_when_no_agent(self, temp_dir, fake_skill_dir):
        """sklm add sans agent configuré doit afficher un avertissement."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"], input="c\n")
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        result = runner.invoke(app, ["add", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "no agent configured" in result.output.lower() or "Warning" in result.output

    def test_rm_warns_when_no_agent(self, temp_dir, fake_skill_dir):
        """sklm rm sans agent configuré doit afficher un avertissement."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"], input="c\n")
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        result = runner.invoke(app, ["rm", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "no agent configured" in result.output.lower() or "Warning" in result.output


# ─── Integration: CLI ────────────────────────────────────────────────────────


class TestCLIIntegration:
    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, temp_dir):
        monkeypatch.setattr("sklm.store.SKLM_HOME", temp_dir / ".sklm-home")
        monkeypatch.setattr("sklm.core.registry.REGISTRIES_PATH", temp_dir / ".sklm-home" / "registries.yaml")
        monkeypatch.setattr("sklm.core.registry.REGISTRY_CACHE", temp_dir / ".sklm-home" / "cache")
        monkeypatch.setattr("sklm.cli.main._sklm", None)

    def test_help(self):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Skills manager" in result.output

    def test_version(self):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "sklm v" in result.output

    def test_init_and_status(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "Workspace created" in result.output
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "Workspace Status" in result.output

    def test_init_with_agent(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init", "--agent", "opencode"])
        assert result.exit_code == 0
        assert "opencode" in result.output
        assert "Agents" in result.output

    def test_global_ls_rm(self, temp_dir, fake_skill_dir, monkeypatch):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        from sklm.api import Sklm
        from sklm.models import ResourceKind
        runner = CliRunner()
        f = Sklm()
        f.global_add(ResourceKind.skill, fake_skill_dir, "test-skill")
        result = runner.invoke(app, ["global", "ls"])
        assert result.exit_code == 0
        assert "test-skill" in result.output
        result = runner.invoke(app, ["global", "rm", "skill", "test-skill"])
        assert result.exit_code == 0

    def test_add_rm_resource(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["add", "skill", str(fake_skill_dir)])
        assert result.exit_code == 0
        assert "Added" in result.output
        result = runner.invoke(app, ["rm", "skill", fake_skill_dir.name])
        assert result.exit_code == 0
        assert "Removed" in result.output

    def test_info(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        from sklm.api import Sklm
        from sklm.models import ResourceKind
        runner = CliRunner()
        runner.invoke(app, ["init"])
        f = Sklm()
        f.global_add(ResourceKind.skill, fake_skill_dir, "test-skill")
        runner.invoke(app, ["add", "skill", "test-skill"])
        result = runner.invoke(app, ["info", "skill", "test-skill"])
        assert result.exit_code == 0
        assert "test-skill" in result.output

    def test_ls_json(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        from sklm.api import Sklm
        from sklm.models import ResourceKind
        runner = CliRunner()
        runner.invoke(app, ["init"])
        f = Sklm()
        f.global_add(ResourceKind.skill, fake_skill_dir, "test-skill")
        runner.invoke(app, ["add", "skill", "test-skill"])
        result = runner.invoke(app, ["ls", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["name"] == "test-skill"

    def test_registry_lifecycle(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["registry", "add", str(temp_dir), "--name", "test-reg"])
        assert result.exit_code == 0
        result = runner.invoke(app, ["registry", "ls"])
        assert result.exit_code == 0
        assert "test-reg" in result.output

    def test_registry_search(self, temp_dir, fake_skill_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["registry", "add", str(fake_skill_dir.parent), "--name", "test-reg"])
        result = runner.invoke(app, ["registry", "search", "my-skill"])
        assert result.exit_code == 0

    def test_agent_detect(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["agent", "detect"])
        assert result.exit_code == 0

    def test_agent_list_contains_agents(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert "opencode" in result.output
        assert "claude" in result.output
        assert "github-copilot" in result.output

    def test_agent_list_json(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["agent", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 8
        ids = [a["id"] for a in data]
        assert "opencode" in ids
        assert "github-copilot" in ids

    def test_agent_list_shows_active(self, temp_dir):
        (temp_dir / ".cursor").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["agent", "list"])
        assert result.exit_code == 0
        assert "ACTIVE" in result.output
        assert "cursor" in result.output

    def test_telemetry_status_active_by_default(self, temp_dir):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["telemetry", "status"])
        assert result.exit_code == 0
        assert "active" in result.output.lower()
        assert "analytics.victorbeysseriat.fr" in result.output

    def test_telemetry_on_off_lifecycle(self, temp_dir, monkeypatch):
        from typer.testing import CliRunner
        from sklm.cli.main import app
        from sklm.store import GlobalStore

        monkeypatch.setenv("SKLM_UMAMI_URL", "https://umami.test")
        monkeypatch.setenv("SKLM_WEBSITE_ID", "test-id")

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

    def test_telemetry_ping_success(self, temp_dir, monkeypatch):
        from unittest.mock import Mock
        from typer.testing import CliRunner
        from sklm.cli.main import app

        monkeypatch.setenv("SKLM_UMAMI_URL", "https://umami.test")
        monkeypatch.setenv("SKLM_WEBSITE_ID", "test-id")
        monkeypatch.setattr("sklm.telemetry.umami.new_event", Mock(return_value={}))

        runner = CliRunner()
        result = runner.invoke(app, ["telemetry", "ping"])
        assert result.exit_code == 0
        assert "succeeded" in result.output.lower()

    def test_telemetry_ping_failure(self, temp_dir, monkeypatch):
        from unittest.mock import Mock
        from typer.testing import CliRunner
        from sklm.cli.main import app

        monkeypatch.setenv("SKLM_UMAMI_URL", "https://umami.test")
        monkeypatch.setenv("SKLM_WEBSITE_ID", "test-id")
        monkeypatch.setattr("sklm.telemetry.umami.new_event", Mock(side_effect=RuntimeError("Connection refused")))

        runner = CliRunner()
        result = runner.invoke(app, ["telemetry", "ping"])
        assert result.exit_code == 1
        assert "failed" in result.output.lower()

    def test_init_creates_agent_dirs(self, temp_dir):
        """sklm init doit créer les dossiers de l'agent détecté."""
        # Simuler un projet OpenCode
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert (temp_dir / ".opencode" / "skills").is_dir()

    def test_init_creates_agent_dirs_with_flag(self, temp_dir):
        """sklm init --agent opencode doit créer les dossiers même sans .opencode/."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init", "--agent", "opencode"])
        assert result.exit_code == 0
        assert (temp_dir / ".opencode" / "skills").is_dir()

    def test_add_copies_skill_content(self, temp_dir, fake_skill_dir):
        """sklm add doit copier le contenu du skill dans .opencode/skills/<name>/."""
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        result = runner.invoke(app, ["add", "skill", "test-skill"])
        assert result.exit_code == 0
        agent_skill_dir = temp_dir / ".opencode" / "skills" / "test-skill"
        assert agent_skill_dir.is_dir()
        assert (agent_skill_dir / "SKILL.md").exists()
        assert (agent_skill_dir / "SKILL.md").read_text() == "# My Skill\nA test skill."

    def test_rm_removes_agent_skill(self, temp_dir, fake_skill_dir):
        """sklm rm doit supprimer le dossier skill de l'agent."""
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        agent_skill_dir = temp_dir / ".opencode" / "skills" / "test-skill"
        assert agent_skill_dir.is_dir()
        result = runner.invoke(app, ["rm", "skill", "test-skill"])
        assert result.exit_code == 0
        assert not agent_skill_dir.exists()

    def test_agent_sync_updates_content(self, temp_dir, fake_skill_dir):
        """sklm agent sync doit copier le contenu dans l'agent."""
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        assert (temp_dir / ".opencode" / "skills" / "test-skill" / "SKILL.md").exists()
        runner.invoke(app, ["rm", "skill", "test-skill"])
        assert not (temp_dir / ".opencode" / "skills" / "test-skill").exists()
        runner.invoke(app, ["add", "skill", "test-skill"])
        assert (temp_dir / ".opencode" / "skills" / "test-skill" / "SKILL.md").exists()
        assert (temp_dir / ".opencode" / "skills" / "test-skill" / "SKILL.md").read_text() == "# My Skill\nA test skill."

    def test_install_command_help(self, temp_dir):
        """sklm install --help doit afficher l'aide."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["install", "--help"])
        assert result.exit_code == 0
        assert "Install" in result.output

    def test_backward_compat_opencode_yaml(self, temp_dir):
        """Existing agent: opencode in YAML should load without error (ignored)."""
        from sklm.models import WorkspaceConfig
        path = temp_dir / "sklm.yaml"
        path.write_text("agent: opencode\nversion: 1\nresources: []\nlinks: []\n")
        config = WorkspaceConfig.from_yaml(path)
        assert config.agents == ["none"]
        assert config.version == 1

    def test_backward_compat_init_opencode(self, temp_dir):
        """sklm init in a project with .opencode/ should work."""
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "opencode" in result.output
        assert "Agents" in result.output

    def test_add_with_from_flag(self, temp_dir):
        """sklm add --help doit mentionner --from."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["add", "--help"])
        assert result.exit_code == 0
        assert "--from" in result.output

    def test_uninstall_command(self, temp_dir, fake_skill_dir):
        """sklm uninstall doit supprimer un skill du store."""
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        result = runner.invoke(app, ["uninstall", "skill", "test-skill", "--force"])
        assert result.exit_code == 0
        assert "Uninstalled" in result.output

    def test_uninstall_linked_skill(self, temp_dir, fake_skill_dir):
        """sklm uninstall d'un skill lié doit demander confirmation."""
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        runner.invoke(app, ["global", "add", "skill", str(fake_skill_dir), "--name", "test-skill"])
        runner.invoke(app, ["add", "skill", "test-skill"])
        # sans --force, avec input "y"
        result = runner.invoke(app, ["uninstall", "skill", "test-skill"], input="y\n")
        assert result.exit_code == 0
        assert "Uninstalled" in result.output

    def test_migrate_command(self, temp_dir):
        """sklm migrate doit importer depuis ~/.agents/."""
        agents_skills = Path.home() / ".agents" / "skills"
        agents_skills.mkdir(parents=True, exist_ok=True)
        test_skill_dir = agents_skills / "test-agent-skill"
        test_skill_dir.mkdir(exist_ok=True)
        (test_skill_dir / "SKILL.md").write_text("# Agent Skill\nFrom skills.sh")
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["migrate", "skill", "test-agent-skill"])
        assert result.exit_code == 0
        assert "Migrated" in result.output
        # cleanup
        import shutil
        shutil.rmtree(test_skill_dir)

    def test_migrate_from_registry(self, temp_dir):
        """sklm migrate --from-registry doit importer depuis un registry local."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        reg_path = temp_dir / "test-registry"
        reg_path.mkdir()
        skill_dir = reg_path / "reg-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Registry Skill")
        runner.invoke(app, ["registry", "add", str(reg_path), "--name", "test-local-reg"])
        result = runner.invoke(app, ["migrate", "--from-registry", "test-local-reg"])
        assert result.exit_code == 0
        assert "Migrated" in result.output
        assert "reg-skill" in result.output

    def test_migrate_from_registry_not_found(self, temp_dir):
        """sklm migrate --from-registry avec un nom inconnu doit échouer."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["migrate", "--from-registry", "does-not-exist"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_migrate_from_git_registry_errors(self, temp_dir):
        """sklm migrate --from-registry avec un registry git doit échouer."""
        import yaml
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        reg_path = temp_dir / ".sklm-home" / "registries.yaml"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        reg_data = {
            "registries": {
                "git-reg": {
                    "name": "git-reg", "type": "git",
                    "url_or_path": "https://github.com/test/repo.git",
                }
            }
        }
        with open(reg_path, "w") as f:
            yaml.dump(reg_data, f, default_flow_style=False)
        result = runner.invoke(app, ["migrate", "--from-registry", "git-reg"])
        assert result.exit_code != 0
        assert "git registry" in result.output.lower()

    def test_migrate_force_cleanup(self, temp_dir):
        """sklm migrate --force-cleanup doit supprimer les sources."""
        agents_skills = Path.home() / ".agents" / "skills"
        agents_skills.mkdir(parents=True, exist_ok=True)
        test_skill_dir = agents_skills / "test-force-clean-skill"
        test_skill_dir.mkdir(exist_ok=True)
        (test_skill_dir / "SKILL.md").write_text("# Force Cleanup")
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["migrate", "skill", "test-force-clean-skill", "--force-cleanup"])
        assert result.exit_code == 0
        assert "Deleted" in result.output
        assert not test_skill_dir.exists()

    def test_migrate_no_cleanup(self, temp_dir):
        """sklm migrate --no-cleanup doit préserver les sources."""
        agents_skills = Path.home() / ".agents" / "skills"
        agents_skills.mkdir(parents=True, exist_ok=True)
        test_skill_dir = agents_skills / "test-no-clean-skill"
        test_skill_dir.mkdir(exist_ok=True)
        (test_skill_dir / "SKILL.md").write_text("# No Cleanup")
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["migrate", "skill", "test-no-clean-skill", "--no-cleanup"])
        assert result.exit_code == 0
        assert "no-cleanup" in result.output
        assert test_skill_dir.exists()
        import shutil
        shutil.rmtree(test_skill_dir)

    def test_migrate_non_interactive_message(self, temp_dir):
        """sklm migrate en mode non-interactif affiche le message de conservation."""
        agents_skills = Path.home() / ".agents" / "skills"
        agents_skills.mkdir(parents=True, exist_ok=True)
        test_skill_dir = agents_skills / "test-non-int-skill"
        test_skill_dir.mkdir(exist_ok=True)
        (test_skill_dir / "SKILL.md").write_text("# Non-interactive")
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["migrate", "skill", "test-non-int-skill"])
        assert result.exit_code == 0
        assert "Non-interactive mode" in result.output
        assert test_skill_dir.exists()
        import shutil
        shutil.rmtree(test_skill_dir)

    def test_migrate_interactive_yes(self, temp_dir, monkeypatch):
        """_prompt_cleanup avec confirmation yes supprime les sources."""
        import sys
        from pathlib import Path
        from sklm.models import ResourceKind, ResourceRef
        from sklm.cli.main import _prompt_cleanup
        test_dir = temp_dir / "int-yes-src"
        test_dir.mkdir()
        ref_src = [
            (ResourceRef(name="test", kind=ResourceKind.skill, origin=str(test_dir)), test_dir)
        ]
        monkeypatch.delenv("SKLM_NO_INTERACTIVE", raising=False)
        with unittest.mock.patch.object(sys.stdout, "isatty", return_value=True), \
             unittest.mock.patch("sklm.cli.main.typer.confirm", return_value=True):
            _prompt_cleanup(ref_src, force_cleanup=False, no_cleanup=False)
        assert not test_dir.exists()

    def test_migrate_interactive_no(self, temp_dir, monkeypatch):
        """_prompt_cleanup avec confirmation no preserve les sources."""
        import sys
        from sklm.models import ResourceKind, ResourceRef
        from sklm.cli.main import _prompt_cleanup
        test_dir = temp_dir / "int-no-src"
        test_dir.mkdir()
        ref_src = [
            (ResourceRef(name="test", kind=ResourceKind.skill, origin=str(test_dir)), test_dir)
        ]
        monkeypatch.delenv("SKLM_NO_INTERACTIVE", raising=False)
        with unittest.mock.patch.object(sys.stdout, "isatty", return_value=True), \
             unittest.mock.patch("sklm.cli.main.typer.confirm", return_value=False):
            _prompt_cleanup(ref_src, force_cleanup=False, no_cleanup=False)
        assert test_dir.exists()
        import shutil
        shutil.rmtree(test_dir)

    def test_migrate_api_returns_tuples(self, temp_dir):
        """Sklm.migrate() retourne list[tuple[ResourceRef, Path]]."""
        from sklm.models import ResourceKind, ResourceRef
        from sklm.api import Sklm
        agents_skills = Path.home() / ".agents" / "skills"
        agents_skills.mkdir(parents=True, exist_ok=True)
        test_skill_dir = agents_skills / "api-tuple-test"
        test_skill_dir.mkdir(exist_ok=True)
        (test_skill_dir / "SKILL.md").write_text("# API Tuple Test")
        f = Sklm()
        result = f.migrate(ResourceKind.skill, "api-tuple-test")
        assert len(result) == 1
        ref, src = result[0]
        assert isinstance(ref, ResourceRef)
        assert isinstance(src, Path)
        assert ref.name == "api-tuple-test"
        assert src == test_skill_dir
        import shutil
        shutil.rmtree(test_skill_dir)

    def test_link_unlink_not_in_cli(self, temp_dir):
        """sklm link et unlink ne doivent PAS être des commandes accessibles."""
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["link", "skill", "test"], input="n\n")
        assert result.exit_code != 0
        result = runner.invoke(app, ["unlink", "skill", "test"], input="n\n")
        assert result.exit_code != 0

    def test_install_api(self, temp_dir):
        """Sklm.install() avec --from doit appeler add_resource_from_git."""
        from sklm.api import Sklm
        from sklm.models import ResourceKind
        f = Sklm()
        mock_resource = MagicMock()
        mock_resource.name = "test-skill"
        mock_resource.kind = ResourceKind.skill
        mock_resource.path = Path("/tmp/test")
        with unittest.mock.patch.object(f.global_store, "add_resource_from_git") as mock_add:
            mock_add.return_value = mock_resource
            ref = f.install(ResourceKind.skill, "test-skill", from_url="https://github.com/test/repo")
            mock_add.assert_called_once()
            assert ref.name == "test-skill"
            assert ref.origin == "https://github.com/test/repo"

    def test_add_from_url_calls_install(self, temp_dir):
        """Sklm.add() avec from_url doit appeler install()."""
        from sklm.api import Sklm
        from sklm.models import ResourceKind
        ref = MagicMock()
        ref.name = "test-skill"
        ref.kind = ResourceKind.skill
        (temp_dir / ".opencode").mkdir()
        f = Sklm()
        f.init_workspace(["none"])
        with unittest.mock.patch.object(f, "install") as mock_install:
            mock_install.return_value = ref
            with unittest.mock.patch("sklm.api._link_resource") as mock_link:
                mock_link.return_value = MagicMock()
                with unittest.mock.patch.object(f, "agent_sync") as mock_sync:
                    mock_sync.return_value = {"agent": "test", "synced": True}
                    f.add(ResourceKind.skill, "test-skill", from_url="https://github.com/test/repo")
                    mock_install.assert_called_once_with(
                        ResourceKind.skill, "test-skill",
                        from_url="https://github.com/test/repo", subdir=None
                    )

    def test_status_warns_external_skills(self, temp_dir):
        """sklm status doit avertir si des skills externes sont détectés."""
        agents_skills = Path.home() / ".agents" / "skills"
        agents_skills.mkdir(parents=True, exist_ok=True)
        test_skill_dir = agents_skills / "test-warning-skill"
        test_skill_dir.mkdir(exist_ok=True)
        (test_skill_dir / "SKILL.md").write_text("# Warning Skill")
        (temp_dir / ".opencode").mkdir()
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["status"])
        assert "outside Sklm's store" in result.output
        assert "migrate" in result.output
        import shutil
        shutil.rmtree(test_skill_dir)


# ─── Update Checker ──────────────────────────────────────────────────────────


class TestUpdateChecker:
    """Tests for sklm.core.update.UpdateChecker."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, temp_dir):
        cache_dir = temp_dir / ".sklm-cache"
        monkeypatch.setattr("sklm.core.update.CACHE_DIR", cache_dir)
        monkeypatch.setattr("sklm.core.update.CACHE_FILE", cache_dir / "update-check")
        monkeypatch.setattr("sklm.__version__", "0.1.0")

    def test_parse_version_strips_v_prefix(self):
        from sklm.core.update import UpdateChecker
        assert UpdateChecker._parse_version("v0.2.0") == (0, 2, 0)
        assert UpdateChecker._parse_version("v1.0.0") == (1, 0, 0)

    def test_parse_version_no_prefix(self):
        from sklm.core.update import UpdateChecker
        assert UpdateChecker._parse_version("0.2.0") == (0, 2, 0)

    def test_parse_version_strips_suffix(self):
        from sklm.core.update import UpdateChecker
        assert UpdateChecker._parse_version("v0.2.0-alpha") == (0, 2, 0)
        assert UpdateChecker._parse_version("v0.2.0+build") == (0, 2, 0)

    def test_parse_version_invalid_returns_zero(self):
        from sklm.core.update import UpdateChecker
        assert UpdateChecker._parse_version("invalid") == (0,)

    def test_is_newer_returns_true(self):
        from sklm.core.update import UpdateChecker
        checker = UpdateChecker()
        assert checker._is_newer("v0.2.0") is True
        assert checker._is_newer("v1.0.0") is True

    def test_is_newer_returns_false(self):
        from sklm.core.update import UpdateChecker
        checker = UpdateChecker()
        assert checker._is_newer("v0.1.0") is False
        assert checker._is_newer("v0.0.9") is False

    def test_should_check_no_cache(self, temp_dir):
        from sklm.core.update import UpdateChecker
        checker = UpdateChecker()
        assert checker._should_check() is True

    def test_should_check_cached_recently(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        cache = temp_dir / ".sklm-cache" / "update-check"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("0")
        checker = UpdateChecker()
        assert checker._should_check() is False

    def test_should_check_cache_expired(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        import os
        import time
        cache = temp_dir / ".sklm-cache" / "update-check"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("0")
        old = time.time() - 90000
        os.utime(cache, (old, old))
        checker = UpdateChecker()
        assert checker._should_check() is True

    def test_update_cache_creates_file(self, temp_dir):
        from sklm.core.update import UpdateChecker
        checker = UpdateChecker()
        checker._update_cache()
        assert checker.cache_path.exists()

    def test_check_returns_none_when_cached(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        cache = temp_dir / ".sklm-cache" / "update-check"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("9999999999")
        checker = UpdateChecker()
        assert checker.check() is None

    def test_check_returns_latest_when_newer(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.2.0",
        )
        checker = UpdateChecker()
        result = checker.check()
        assert result == "v0.2.0"

    def test_check_returns_none_when_same_version(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.1.0",
        )
        checker = UpdateChecker()
        assert checker.check() is None

    def test_find_repo_root_returns_none_when_no_git(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        monkeypatch.setattr("sklm.__file__", str(temp_dir / "sklm" / "__init__.py"))
        checker = UpdateChecker()
        assert checker.find_repo_root() is None

    def test_find_repo_root_finds_parent_git(self, temp_dir, monkeypatch):
        from sklm.core.update import UpdateChecker
        git_dir = temp_dir / ".git"
        git_dir.mkdir()
        pkg_dir = temp_dir / "src" / "sklm"
        pkg_dir.mkdir(parents=True)
        monkeypatch.setattr("sklm.__file__", str(pkg_dir / "__init__.py"))
        checker = UpdateChecker()
        assert checker.find_repo_root() == temp_dir.resolve()


class TestUpdateCLI:
    """CLI tests for update commands and passive notice."""

    @pytest.fixture(autouse=True)
    def setup(self, monkeypatch, temp_dir):
        monkeypatch.setattr("sklm.store.SKLM_HOME", temp_dir / ".sklm-home")
        monkeypatch.setattr("sklm.core.registry.REGISTRIES_PATH", temp_dir / ".sklm-home" / "registries.yaml")
        monkeypatch.setattr("sklm.core.registry.REGISTRY_CACHE", temp_dir / ".sklm-home" / "cache")
        monkeypatch.setattr("sklm.cli.main._sklm", None)
        monkeypatch.setattr("sklm.core.update.CACHE_DIR", temp_dir / ".sklm-cache")

    def test_update_check_no_update(self, temp_dir, monkeypatch):
        monkeypatch.setattr("sklm.__version__", "0.1.0")
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.1.0",
        )
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["update", "--check"])
        assert result.exit_code == 0
        assert "up to date" in result.output.lower()

    def test_update_check_new_version(self, temp_dir, monkeypatch):
        monkeypatch.setattr("sklm.__version__", "0.1.0")
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.2.0",
        )
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["update", "--check", "--force"])
        assert result.exit_code == 0
        assert "v0.2.0" in result.output

    def test_update_no_repo(self, temp_dir, monkeypatch):
        monkeypatch.setattr("sklm.__version__", "0.1.0")
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.2.0",
        )
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker.find_repo_root",
            lambda self: None,
        )
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["update", "--force"])
        assert result.exit_code == 1
        assert "Cannot find" in result.output

    def test_update_success(self, temp_dir, monkeypatch):
        from unittest.mock import Mock
        monkeypatch.setattr("sklm.__version__", "0.1.0")
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.2.0",
        )
        repo_dir = temp_dir / "repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker.find_repo_root",
            lambda self: repo_dir,
        )
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker.is_editable",
            lambda self: True,
        )
        mock_run = Mock(return_value=Mock(returncode=0))
        monkeypatch.setattr("sklm.cli.main.subprocess.run", mock_run)
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["update", "--force"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "Updated" in result.output

    def test_update_git_fetch_fails(self, temp_dir, monkeypatch):
        from unittest.mock import Mock
        monkeypatch.setattr("sklm.__version__", "0.1.0")
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker._get_latest_version_via_api",
            lambda self: "v0.2.0",
        )
        repo_dir = temp_dir / "repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()
        monkeypatch.setattr(
            "sklm.core.update.UpdateChecker.find_repo_root",
            lambda self: repo_dir,
        )
        mock_run = Mock(return_value=Mock(returncode=1, stderr=b"error"))
        monkeypatch.setattr("sklm.cli.main.subprocess.run", mock_run)
        from typer.testing import CliRunner
        from sklm.cli.main import app
        runner = CliRunner()
        result = runner.invoke(app, ["update", "--force"])
        assert result.exit_code == 1

    def test_sklm_no_update_check_env(self, temp_dir, monkeypatch):
        monkeypatch.setenv("SKLM_NO_UPDATE_CHECK", "1")
        from sklm.cli.main import _show_update_notice
        _show_update_notice()
