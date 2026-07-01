"""Interactive wizard for Sklm — state detection and contextual menus."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import questionary
from rich.console import Console
from rich.table import Table

from sklm.api import Sklm

_BACK_CHOICE = questionary.Choice(title="← Back", value="Back")
from sklm.models import ResourceKind
from sklm.agents.registry import AgentRegistry
from sklm.core.linking import detect_broken_links, link_resource as _do_link
from sklm.store import SKLM_HOME


console = Console()


# ─── System State ──────────────────────────────────────────────────────────


@dataclass
class SystemState:
    """Detected system state for menu construction."""
    has_store: bool = False
    has_workspace: bool = False
    has_migration: bool = False
    store_count: int = 0
    ws_count: int = 0
    broken_links: int = 0
    agents: list[str] = field(default_factory=list)


def detect_state(f: Sklm) -> SystemState:
    """Detect the current system state by probing filesystem and config."""
    state = SystemState()

    # Store detection
    skills_dir = SKLM_HOME / "store" / "skills"
    if skills_dir.is_dir():
        entries = [d for d in skills_dir.iterdir() if d.is_dir()]
        state.has_store = len(entries) > 0
        state.store_count = len(entries)

    # Workspace detection
    state.has_workspace = f.workspace.exists()
    if state.has_workspace:
        config = f.workspace.load_config()
        state.ws_count = len(
            [r for r in config.resources if r.kind == ResourceKind.skill]
        )
        state.agents = [a for a in config.agents if a != "none"]

        # Broken links
        broken = detect_broken_links(f.workspace)
        state.broken_links = len(broken)

    # Migration source detection
    agents_skills = Path.home() / ".agents" / "skills"
    if agents_skills.is_dir():
        entries = [
            d for d in agents_skills.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]
        state.has_migration = len(entries) > 0

    return state


# ─── Header ────────────────────────────────────────────────────────────────


def show_header(state: SystemState) -> None:
    """Display a context banner with the current system state."""
    console.print()
    console.print("[bold]Sklm — Skills manager for AI agents[/]")
    console.print()

    parts: list[str] = []
    if state.has_store:
        parts.append(f"Global store: [cyan]{state.store_count}[/] skill(s)")
    else:
        parts.append("Global store: [dim]empty[/]")

    if state.has_workspace:
        ws_label = f"Workspace: [green]active[/]"
        if state.agents:
            ws_label += f" ({', '.join(state.agents)})"
        ws_label += f" — [cyan]{state.ws_count}[/] skill(s)"
        parts.append(ws_label)
    else:
        parts.append("Workspace: [dim]none[/]")

    if state.has_migration:
        parts.append("[yellow]Migration source detected[/]")

    if state.broken_links:
        parts.append(f"[red]{state.broken_links} broken link(s)[/]")

    console.print("  " + "  ·  ".join(parts))
    console.print()


# ─── Choices ───────────────────────────────────────────────────────────────


def build_choices(state: SystemState) -> list[str]:
    """Build contextual menu choices based on detected state."""
    choices: list[str] = []

    # Install is always available
    choices.append("Install a skill")

    if state.has_store and state.has_workspace:
        choices.append("Add skill to this workspace")

    if state.has_store or state.has_workspace:
        choices.append("List skills")
        choices.append("Remove a skill")

    if state.has_migration:
        choices.append("Migrate skills")

    if not state.has_workspace and state.has_store:
        choices.append("Initialize this workspace")

    choices.append("Settings")
    choices.append("Exit")

    return choices


# ─── Check & Repair Links ─────────────────────────────────────────────────


def check_and_repair_links(f: Sklm) -> None:
    """Check for broken workspace links and offer to repair them."""
    broken = detect_broken_links(f.workspace)
    if not broken:
        return

    console.print(
        f"\n[yellow]{len(broken)} broken symlink(s) detected.[/]"
    )
    try:
        repair = questionary.confirm(
            "Repair them?", default=True
        ).ask()
    except KeyboardInterrupt:
        console.print("\n[yellow]Repair skipped.[/]")
        return

    if not repair:
        console.print("[dim]Repair skipped.[/]")
        return

    repaired = 0
    failed = 0
    for link in broken:
        try:
            _do_link(f.workspace, f.global_store, link.kind, link.name)
            repaired += 1
        except Exception:
            failed += 1

    if repaired:
        console.print(f"[green]Repaired {repaired} link(s).[/]")
    if failed:
        console.print(f"[red]Failed to repair {failed} link(s).[/]")


# ─── Install Flow ─────────────────────────────────────────────────────────


def install_flow(f: Sklm) -> None:
    """Guide the user through installing a skill."""
    try:
        source = questionary.select(
            "Select installation source:",
            choices=[
                "Git URL",
                "Search registries",
                "Local path",
                _BACK_CHOICE,
            ],
        ).ask()
    except KeyboardInterrupt:
        return

    if source == "Back":
        return

    kind = ResourceKind.skill
    name: Optional[str] = None
    from_url: Optional[str] = None
    subdir: Optional[str] = None
    source_path: Optional[str] = None

    if source == "Git URL":
        try:
            url = questionary.text(
                "Git repository URL:",
                validate=lambda v: len(v.strip()) > 0,
            ).ask()
            if not url:
                return
            name = questionary.text(
                "Skill name:",
                validate=lambda v: len(v.strip()) > 0,
            ).ask()
            if not name:
                return
            subdir = questionary.text(
                "Subdirectory (optional):",
                default="",
            ).ask()
            from_url = url.strip()
            subdir = subdir.strip() or None
        except KeyboardInterrupt:
            return

        try:
            ref = f.install(kind, name, from_url=from_url, subdir=subdir)
            console.print(f"[green]✓[/] Installed [bold]{ref.name}[/] from Git")
        except Exception as e:
            console.print(f"[red]✗[/] Failed to install from Git: {e}")
            return

    elif source == "Search registries":
        try:
            keyword = questionary.text(
                "Enter search keyword:",
                validate=lambda v: len(v.strip()) > 0,
            ).ask()
            if not keyword:
                return

            results = f.registry_search(keyword.strip())
            if not results:
                console.print(f"[yellow]No results for '{keyword}'.[/]")
                return

            ws_skill_names = _get_workspace_skill_names_wizard(f)
            choices = [
                f"{'[✓]' if res.name in ws_skill_names else '[ ]'} {reg_name}:{res.name}"
                for reg_name, res in results
            ]
            selected = questionary.select(
                    "Select a skill to install:",
                    choices=choices + [_BACK_CHOICE],
                ).ask()
            if not selected or selected == "Back":
                return

            # Strip prefix to parse registry:name
            raw = selected
            if raw.startswith("[✓] ") or raw.startswith("[ ] "):
                raw = raw[4:]
            parts = raw.split(":", 1)
            if len(parts) == 2:
                name = parts[1]
                ref = f.install(kind, name)
                console.print(f"[green]✓[/] Installed [bold]{ref.name}[/] from registry")
            else:
                console.print("[red]✗[/] Invalid selection.")
                return

        except KeyboardInterrupt:
            return
        except Exception as e:
            console.print(f"[red]✗[/] Failed to install from registry: {e}")
            return

    elif source == "Local path":
        try:
            path_str = questionary.path(
                "Path to skill directory:",
                validate=lambda p: (
                    Path(p).expanduser().resolve() / "SKILL.md"
                ).exists()
                or "Path does not contain SKILL.md",
            ).ask()
            if not path_str:
                return
            source_path = str(Path(path_str).expanduser().resolve())
            name = Path(source_path).name
        except KeyboardInterrupt:
            return

        try:
            f.global_add(kind, source_path, name)
            console.print(f"[green]✓[/] Installed [bold]{name}[/] from local path")
        except Exception as e:
            console.print(f"[red]✗[/] Failed to install from local path: {e}")
            return

    # Destination choice
    try:
        dest = questionary.select(
            "Destination:",
            choices=["Global store only", "Global store + workspace", _BACK_CHOICE],
        ).ask()
    except KeyboardInterrupt:
        return

    if dest == "Back":
        return

    if dest == "Global store + workspace":
        if not f.workspace.exists():
            console.print("[yellow]No workspace found. Initializing one first...[/]")
            init_workspace_flow(f)

        if f.workspace.exists():
            try:
                ref = f.add(kind, name, from_url=from_url, subdir=subdir)
                console.print(f"[green]✓[/] Added [bold]{ref.name}[/] to workspace")
            except Exception as e:
                console.print(f"[yellow]⚠[/] Installed globally but could not add to workspace: {e}")
        else:
            console.print("[dim]Skill installed globally only.[/]")

    if dest == "Global store only":
        console.print(f"[dim]Skill installed globally.[/]")


# ─── Init Workspace Flow ──────────────────────────────────────────────────


def init_workspace_flow(f: Sklm) -> None:
    """Initialize a workspace with agent selection."""
    try:
        registry = AgentRegistry()
        detected = registry.detect(f.project_root)

        if detected:
            console.print(f"\n[bold]Detected agents:[/] {', '.join(detected)}")
            selected = questionary.checkbox(
                "Select agents to configure:",
                choices=[
                    questionary.Choice(a, checked=True)
                    for a in detected
                ],
            ).ask()
            if selected is None:
                return
            agents = selected if selected else ["none"]
        else:
            all_agents = registry.get_agent_ids()
            console.print("\n[bold]No agents auto-detected.[/]")
            console.print("[dim]Select the AI agent(s) you use:[/]")
            selected = questionary.checkbox(
                "Select agents:",
                choices=all_agents,
            ).ask()
            if selected is None:
                return
            agents = selected if selected else ["none"]

        f.init_workspace(agents)
        active = [a for a in agents if a != "none"]
        label = ", ".join(active) if active else "[yellow]none[/]"
        console.print(f"[green]✓[/] Workspace created with agents: [cyan]{label}[/]")

        # Offer to sync existing skills
        if active:
            try:
                sync_confirm = questionary.confirm(
                    "Sync skills now?", default=True
                ).ask()
                if sync_confirm:
                    try:
                        f.agent_sync()
                        console.print("[green]✓[/] Skills synced to agent config(s).")
                    except RuntimeError as e:
                        console.print(f"[yellow]⚠[/] Sync skipped: {e}")
            except KeyboardInterrupt:
                console.print("[dim]Sync skipped.[/]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Workspace init cancelled.[/]")


# ─── Add to Workspace Flow ────────────────────────────────────────────────


def add_to_workspace_flow(f: Sklm) -> None:
    """Select globally installed skills via checkbox and add them to the workspace."""
    if not f.workspace.exists():
        console.print("[yellow]⚠ No workspace found. Initialize one first.[/]")
        return

    store_skills = f.global_ls(ResourceKind.skill)
    if not store_skills:
        console.print("[yellow]No skills in global store.[/]")
        return

    ws_resources = f.workspace.list_resources(ResourceKind.skill)
    linked_names = {r.name for r in ws_resources}

    try:
        choices = []
        for s in store_skills:
            prefix = "[✓]" if s.name in linked_names else "[ ]"
            choices.append(f"{prefix} {s.name}")

        selected = questionary.checkbox(
            "Select skills to add to workspace (SPACE to toggle, Enter to confirm):",
            choices=choices,
        ).ask()

        # Cancelled (Ctrl+C / Escape)
        if selected is None:
            return

        # Empty selection — nothing checked
        if not selected:
            return

        for item in selected:
            # Strip prefix to get raw name
            raw = item
            if raw.startswith("[✓] ") or raw.startswith("[ ] "):
                raw = raw[4:]

            if raw in linked_names:
                console.print(f"[yellow]⚠[/] [bold]{raw}[/] already in workspace")
                continue

            try:
                ref = f.add(ResourceKind.skill, raw)
                console.print(f"[green]✓[/] Added [bold]{ref.name}[/] to workspace")
            except Exception as e:
                console.print(f"[red]✗[/] Failed to add [bold]{raw}[/]: {e}")
    except KeyboardInterrupt:
        return
    except Exception as e:
        console.print(f"[red]✗[/] Failed to add skill: {e}")


# ─── List Skills Flow ─────────────────────────────────────────────────────


def list_skills_flow(f: Sklm) -> None:
    """Display skills from global store and/or workspace."""
    store_skills = f.global_ls(ResourceKind.skill)
    ws_skills = []
    ws_names: set[str] = set()
    if f.workspace.exists():
        ws_skills = f.workspace.list_resources(ResourceKind.skill)
        ws_names = {s.name for s in ws_skills}

    if store_skills:
        table = Table(title="Global Store Skills")
        table.add_column("Name", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("In workspace", style="magenta")
        for s in store_skills:
            in_ws = "[green]✓[/]" if s.name in ws_names else "[dim]—[/]"
            table.add_row(s.name, s.source, in_ws)
        console.print(table)
    else:
        console.print("[yellow]No skills in global store.[/]")

    if ws_skills:
        table = Table(title="Workspace Skills")
        table.add_column("Name", style="cyan")
        table.add_column("Origin", style="green")
        table.add_column("Linked", style="magenta")
        for s in ws_skills:
            linked = "[green]✓[/]" if s.linked else "[dim]—[/]"
            table.add_row(s.name, s.origin, linked)
        console.print(table)
    else:
        console.print("[yellow]No skills in workspace.[/]")


# ─── Remove Skill Flow ────────────────────────────────────────────────────


def remove_skill_flow(f: Sklm) -> None:
    """Remove a skill from workspace or global store."""
    try:
        scope = questionary.select(
            "Remove from:",
            choices=["Workspace", "Global store", _BACK_CHOICE],
        ).ask()
    except KeyboardInterrupt:
        return

    if scope == "Back":
        return

    kind = ResourceKind.skill

    if scope == "Workspace":
        if not f.workspace.exists():
            console.print("[yellow]No workspace found.[/]")
            return
        ws_skills = f.workspace.list_resources(kind)
        if not ws_skills:
            console.print("[yellow]No skills in workspace.[/]")
            return
        try:
            choices = [s.name for s in ws_skills]
            selected = questionary.select(
                "Select skill to remove:",
                choices=choices + [_BACK_CHOICE],
            ).ask()
            if not selected or selected == "Back":
                return
            confirm = questionary.confirm(
                f"Remove '{selected}' from workspace?", default=False
            ).ask()
            if confirm:
                f.remove(kind, selected)
                console.print(f"[green]✓[/] Removed [bold]{selected}[/] from workspace")
        except KeyboardInterrupt:
            return
        except Exception as e:
            console.print(f"[red]✗[/] {e}")

    elif scope == "Global store":
        store_skills = f.global_ls(kind)
        if not store_skills:
            console.print("[yellow]No skills in global store.[/]")
            return
        try:
            choices = [s.name for s in store_skills]
            selected = questionary.select(
                "Select skill to remove:",
                choices=choices + [_BACK_CHOICE],
            ).ask()
            if not selected or selected == "Back":
                return
            confirm = questionary.confirm(
                f"Remove '{selected}' from global store?",
                default=False,
            ).ask()
            if confirm:
                f.uninstall(kind, selected)
                console.print(f"[green]✓[/] Removed [bold]{selected}[/] from global store")
        except KeyboardInterrupt:
            return
        except Exception as e:
            console.print(f"[red]✗[/] {e}")


# ─── Migrate Flow ─────────────────────────────────────────────────────────


def migrate_flow(f: Sklm) -> None:
    """Migrate skills from ~/.agents/skills/ into the global store."""
    kind = ResourceKind.skill
    try:
        refs_src = f.migrate(kind)
    except FileNotFoundError as e:
        console.print(f"[red]✗[/] {e}")
        return
    except Exception as e:
        console.print(f"[red]✗[/] Migration failed: {e}")
        return

    if not refs_src:
        console.print("[yellow]No skills to migrate.[/]")
        return

    for ref, _ in refs_src:
        console.print(f"[green]✓[/] Migrated [bold]{ref.name}[/]")

    console.print(f"\n[green]Done.[/] {len(refs_src)} skill(s) migrated.")

    # Offer cleanup
    try:
        cleanup = questionary.confirm(
            "Delete source directories?", default=False
        ).ask()
        if cleanup:
            import shutil
            for _, src in refs_src:
                if src.exists():
                    shutil.rmtree(src)
            console.print(f"[green]✓[/] Deleted {len(refs_src)} source director{'y' if len(refs_src) == 1 else 'ies'}")
    except KeyboardInterrupt:
        console.print("[dim]Cleanup skipped.[/]")


# ─── Settings Sub-Menu ────────────────────────────────────────────────────


def settings_menu(f: Sklm) -> None:
    """Display the settings sub-menu."""
    while True:
        try:
            choice = questionary.select(
                "Settings:",
                choices=[
                    "Manage agents",
                    "Toggle telemetry",
                    "Check for updates",
                    "Manage registries",
                    _BACK_CHOICE,
                ],
            ).ask()
        except KeyboardInterrupt:
            return

        if choice == "Back" or choice is None:
            return
        elif choice == "Manage agents":
            agents_menu(f)
        elif choice == "Toggle telemetry":
            _toggle_telemetry(f)
        elif choice == "Check for updates":
            _check_updates()
        elif choice == "Manage registries":
            registries_menu(f)


def _toggle_telemetry(f: Sklm) -> None:
    """Toggle telemetry on or off."""
    from sklm.store import GlobalStore

    store = GlobalStore()
    cfg = store.get_telemetry_config()
    if cfg.enabled:
        cfg.enabled = False
        store.set_telemetry_config(cfg)
        console.print("[yellow]⚠ Telemetry disabled[/]")
    else:
        cfg.enabled = True
        store.set_telemetry_config(cfg)
        console.print("[green]✓ Telemetry enabled[/]")


def _check_updates() -> None:
    """Check for sklm updates."""
    from sklm.core.update import UpdateChecker
    from sklm import __version__

    checker = UpdateChecker()
    console.print("[dim]Checking for updates...[/]")
    latest = checker.check()
    if latest is None:
        console.print(f"[green]✓[/] sklm is up to date (v{__version__})")
    else:
        console.print(
            f"[yellow]⚠[/] sklm [bold]v{latest}[/] available "
            f"(current: v{__version__})"
        )
        console.print("   Run [bold]sklm update[/] to upgrade.")


# ─── Agents Sub-Menu ──────────────────────────────────────────────────────


def agents_menu(f: Sklm) -> None:
    """Display the agents management sub-menu."""
    while True:
        try:
            choice = questionary.select(
                "Manage Agents:",
                choices=[
                    "List agents",
                    "Add agent",
                    "Remove agent",
                    "Detect agents",
                    "Sync skills",
                    _BACK_CHOICE,
                ],
            ).ask()
        except KeyboardInterrupt:
            return

        if choice == "Back" or choice is None:
            return
        elif choice == "List agents":
            _list_agents(f)
        elif choice == "Add agent":
            _add_agent(f)
        elif choice == "Remove agent":
            _remove_agent(f)
        elif choice == "Detect agents":
            _detect_agents(f)
        elif choice == "Sync skills":
            _sync_skills(f)


def _list_agents(f: Sklm) -> None:
    agents = f.list_agents()
    if not agents:
        console.print("[yellow]No agents configured.[/]")
        return
    table = Table(title="Supported Agents")
    table.add_column("Agent", style="cyan")
    table.add_column("ID", style="green")
    table.add_column("Directory", style="white")
    table.add_column("Status", style="yellow")
    for a in agents:
        status = "[green]ACTIVE[/]" if a["active"] else "—"
        table.add_row(
            a["id"].replace("-", " ").title(), a["id"], a["dir"], status,
        )
    console.print(table)


def _add_agent(f: Sklm) -> None:
    if not f.workspace.exists():
        console.print("[yellow]No workspace found. Initialize one first.[/]")
        return
    registry = AgentRegistry()
    all_ids = registry.get_agent_ids()
    try:
        selected = questionary.select(
            "Select agent to add:",
            choices=all_ids + [_BACK_CHOICE],
        ).ask()
        if not selected or selected == "Back":
            return
        f.workspace.add_agent(selected)
        try:
            f.agent_sync()
        except RuntimeError:
            pass
        console.print(f"[green]✓[/] Agent [bold]{selected}[/] added and synced.")
    except KeyboardInterrupt:
        return
    except Exception as e:
        console.print(f"[red]✗[/] {e}")


def _remove_agent(f: Sklm) -> None:
    if not f.workspace.exists():
        console.print("[yellow]No workspace found.[/]")
        return
    config = f.workspace.load_config()
    active = [a for a in config.agents if a != "none"]
    if not active:
        console.print("[yellow]No agents configured.[/]")
        return
    try:
        selected = questionary.select(
            "Select agent to remove:",
            choices=active + [_BACK_CHOICE],
        ).ask()
        if not selected or selected == "Back":
            return
        f.workspace.remove_agent(selected)
        console.print(f"[green]✓[/] Agent [bold]{selected}[/] removed.")
    except KeyboardInterrupt:
        return
    except Exception as e:
        console.print(f"[red]✗[/] {e}")


def _detect_agents(f: Sklm) -> None:
    detected = f.agent_detect()
    if detected:
        console.print(f"[green]✓[/] Detected: [bold]{detected}[/]")
    else:
        console.print("[yellow]No supported agent detected.[/]")


def _sync_skills(f: Sklm) -> None:
    try:
        result = f.agent_sync()
        agents_str = ", ".join(result.get("agents", []))
        console.print(f"[green]✓[/] Synced {agents_str}")
    except RuntimeError as e:
        console.print(f"[yellow]⚠[/] Sync failed: {e}")


# ─── Registries Sub-Menu ──────────────────────────────────────────────────


def registries_menu(f: Sklm) -> None:
    """Display the registries management sub-menu."""
    while True:
        try:
            choice = questionary.select(
                "Manage Registries:",
                choices=[
                    "List registries",
                    "Add registry",
                    "Search registries",
                    _BACK_CHOICE,
                ],
            ).ask()
        except KeyboardInterrupt:
            return

        if choice == "Back" or choice is None:
            return
        elif choice == "List registries":
            _list_registries(f)
        elif choice == "Add registry":
            _add_registry(f)
        elif choice == "Search registries":
            _search_registries(f)


def _list_registries(f: Sklm) -> None:
    sources = f.registry_ls()
    if not sources:
        console.print("[yellow]No registries configured.[/]")
        return
    table = Table(title="Registries")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Source", style="white")
    for name, src in sources.items():
        table.add_row(name, src.type.value, src.url_or_path)
    console.print(table)


def _add_registry(f: Sklm) -> None:
    try:
        url_or_path = questionary.text(
            "Registry path or URL:",
            validate=lambda v: len(v.strip()) > 0,
        ).ask()
        if not url_or_path:
            return
        name = questionary.text(
            "Name (optional, defaults to last path component):",
            default="",
        ).ask()
        name = name.strip() or None
        src = f.registry_add(url_or_path.strip(), name)
        console.print(f"[green]✓[/] Added registry [bold]{src.name}[/] ({src.type.value})")
    except KeyboardInterrupt:
        return
    except Exception as e:
        console.print(f"[red]✗[/] Failed to add registry: {e}")


def _get_workspace_skill_names_wizard(f: Sklm) -> set[str]:
    """Return set of skill names linked in the workspace, or empty set if no workspace exists."""
    if not f.workspace.exists():
        return set()
    return {r.name for r in f.workspace.list_resources(ResourceKind.skill)}


def _search_registries(f: Sklm) -> None:
    try:
        query = questionary.text(
            "Enter search keyword:",
            validate=lambda v: len(v.strip()) > 0,
        ).ask()
        if not query:
            return
        results = f.registry_search(query.strip())
        if not results:
            console.print(f"[yellow]No results for '{query}'.[/]")
            return
        ws_skill_names = _get_workspace_skill_names_wizard(f)
        table = Table(title=f"Search Results: '{query}'")
        table.add_column("Registry", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="magenta")
        table.add_column("Status", style="yellow")
        table.add_column("Path", style="white")
        for reg_name, resource in results:
            status = "[green]✓[/]" if resource.name in ws_skill_names else "[dim]—[/]"
            table.add_row(reg_name, resource.name, resource.kind.value, status, str(resource.path))
        console.print(table)
    except KeyboardInterrupt:
        return
    except Exception as e:
        console.print(f"[red]✗[/] Search failed: {e}")


# ─── Main Wizard Loop ─────────────────────────────────────────────────────


def run_wizard() -> None:
    """Entry point for the interactive wizard."""
    f = Sklm()

    try:
        state = detect_state(f)
    except Exception as e:
        console.print(f"[red]✗[/] Failed to detect system state: {e}")
        return

    # Auto-repair broken links before menu
    if state.has_workspace and state.broken_links > 0:
        check_and_repair_links(f)
        # Re-detect state after repair
        state = detect_state(f)

    while True:
        try:
            show_header(state)
            choices = build_choices(state)
            choice = questionary.select(
                "What would you like to do?",
                choices=choices,
            ).ask()
        except KeyboardInterrupt:
            console.print("\n[dim]Exiting.[/]")
            sys.exit(0)

        if choice is None or choice == "Exit":
            console.print("[dim]Goodbye![/]")
            break

        # Route to the appropriate flow
        if choice == "Install a skill":
            install_flow(f)
        elif choice == "Add skill to this workspace":
            add_to_workspace_flow(f)
        elif choice == "List skills":
            list_skills_flow(f)
        elif choice == "Remove a skill":
            remove_skill_flow(f)
        elif choice == "Migrate skills":
            migrate_flow(f)
        elif choice == "Initialize this workspace":
            init_workspace_flow(f)
        elif choice == "Settings":
            settings_menu(f)

        # Re-detect state after each action
        state = detect_state(f)
