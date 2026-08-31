"""Skim CLI — main entrypoint with real backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print_json

from skim import __version__
from skim.api import Skim
from skim.cli.prompts import (
    prompt_agent_selection,
    prompt_install_from_git,
    prompt_main_menu,
    prompt_skill_selection,
)
from skim.models import RegistryType, ResourceKind
from skim.agents.registry import AgentRegistry

app = typer.Typer(
    name="skim",
    help="Skills manager for AI agents — run without arguments for interactive mode",
    no_args_is_help=False,
    rich_markup_mode="rich",
)
console = Console()

_skim: Optional[Skim] = None


def get_skim() -> Skim:
    global _skim
    if _skim is None:
        _skim = Skim()
    return _skim


def version_callback(value: bool):
    if value:
        console.print(f"skim v{__version__}")
        raise typer.Exit()


def parse_resource_type(val: str) -> ResourceKind:
    if val in ("skill", "skills"):
        return ResourceKind.skill
    raise typer.BadParameter(f"Invalid type '{val}'. Use 'skill'.")


def _prompt_cleanup(
    refs_src: list[tuple["ResourceRef", Path]],
    force_cleanup: bool,
    no_cleanup: bool,
) -> None:
    if not refs_src:
        return

    if no_cleanup:
        console.print("[dim]Source files preserved (--no-cleanup).[/]")
        return

    is_interactive = sys.stdout.isatty() and os.environ.get("SKIM_NO_INTERACTIVE", "").lower() not in ("1", "true", "yes", "on")

    if force_cleanup:
        for _, src in refs_src:
            if src.exists():
                shutil.rmtree(src)
        msg = f"[green]✓[/] Deleted {len(refs_src)} source director{'y' if len(refs_src) == 1 else 'ies'}"
        console.print(msg)
        return

    if not is_interactive:
        console.print("[dim]Non-interactive mode: source files preserved. Use --force-cleanup to delete.[/]")
        return

    if len(refs_src) == 1:
        msg = f"Delete source directory {refs_src[0][1]}?"
    else:
        parent = refs_src[0][1].parent
        msg = f"Delete {len(refs_src)} migrated source directories from {parent}?"

    if typer.confirm(msg, default=False):
        for _, src in refs_src:
            if src.exists():
                shutil.rmtree(src)
        msg = f"[green]✓[/] Deleted {len(refs_src)} source director{'y' if len(refs_src) == 1 else 'ies'}"
        console.print(msg)
    else:
        console.print("[dim]Source files preserved.[/]")


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version", callback=version_callback
    ),
):
    pass


def _get_agent_selection_for_init(f: Skim) -> list[str]:
    """Get agent selection for ``init``, using prompt or fallback."""
    registry = AgentRegistry()
    return prompt_agent_selection(registry)


# ─── Workspace ───────────────────────────────────────────────────────────────


@app.command()
def init(
    agent: Optional[list[str]] = typer.Option(
        None, "--agent", "-a", help="Agent(s) to configure (repeatable, auto-detect if omitted)"
    ),
):
    """Initialize a Skim workspace in the current directory. Use --agent to add agents (re-run to update an existing workspace)."""
    f = get_skim()
    if f.workspace.exists():
        if agent:
            for a in agent:
                f.workspace.add_agent(a)
            # Sync agent config directories immediately so the user doesn't
            # need a separate `skim agent sync` step.
            try:
                f.agent_sync()
            except RuntimeError as e:
                console.print(f"[yellow]⚠[/] Agent sync failed: {e}")
            console.print("[yellow]⚠[/] Workspace already exists at [bold].skim/[/]")
            console.print(f"   Agents updated: [cyan]{', '.join(agent)}[/]")
            return
        console.print("[yellow]⚠[/] Workspace already exists at [bold].skim/[/]")
        raise typer.Exit(1)
    if agent:
        agents = agent
    else:
        detected = f.agent_registry.detect(f.project_root)
        if detected:
            agents = detected
        else:
            agents = _get_agent_selection_for_init(f)
    detected = f.init_workspace(agents)
    label = ", ".join(detected) if detected != ["none"] else "[yellow]none[/]"
    console.print("[green]✓[/] Workspace created at [bold].skim/[/]")
    console.print(f"   Agents: [cyan]{label}[/]")
    if detected == ["none"]:
        console.print("   [dim]Run 'skim init --agent <name>' to configure an agent later.[/]")


@app.command()
def status(
    repair: bool = typer.Option(False, "--repair", help="Attempt to repair broken links"),
):
    """Show workspace status."""
    f = get_skim()
    if not f.workspace.exists():
        console.print("[red]✗[/] No Skim workspace found. Run [bold]skim init[/] first.")
        raise typer.Exit(1)
    if repair:
        result = f.repair_broken_links()
        if result["repaired"]:
            for link in result["repaired"]:
                console.print(f"[green]✓ Repaired[/] {link.kind.value}:{link.name}")
        if result["still_broken"]:
            for link in result["still_broken"]:
                console.print(f"[red]✗ Still broken[/] {link.kind.value}:{link.name}")
        return
    state = f.get_status()
    table = Table(title="Workspace Status")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    agents_label = ", ".join(state["agents"]) if state["agents"] != ["none"] else "[yellow]none[/]"
    table.add_row("Agents", agents_label)
    table.add_row("Skills", str(state["skills"]))
    table.add_row("Total links", str(state["total_links"]))
    table.add_row("Broken links", str(state["broken_links"]))
    console.print(table)
    if state["broken_links"] > 0:
        console.print("\n[yellow]💡 Tip:[/] Run [bold]skim status --repair[/] to fix broken links")
    external_count = state.get("external_skills_count", 0)
    if external_count > 0:
        console.print(
            f"\n[yellow]⚠ {external_count} skills found outside Skim's store[/]"
            "\n   These may be globally visible to your AI agent in every project."
            "\n   Use [bold]skim migrate[/] to import them into the Skim store."
        )


# ─── Install / Uninstall ────────────────────────────────────────────────────


@app.command()
def install(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name"),
    from_url: Optional[str] = typer.Option(
        None, "--from", help="Git repository URL to install from"
    ),
    subdir: Optional[str] = typer.Option(
        None, "--subdir", help="Subdirectory within the repo (default: skills/<name>)"
    ),
):
    """Install a resource into the global store without activating it."""
    f = get_skim()
    kind = parse_resource_type(resource_type)
    try:
        ref = f.install(kind, name, from_url=from_url, subdir=subdir)
    except (FileNotFoundError, FileExistsError, ValueError, OSError, subprocess.TimeoutExpired) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Installed {kind.value} [bold]{ref.name}[/] in global store")
    if ref.origin:
        console.print(f"   Source: {ref.origin}")


@app.command()
def uninstall(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name to uninstall"),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
):
    """Remove a resource from the global store permanently."""
    f = get_skim()
    kind = parse_resource_type(resource_type)
    linked_projects = []
    try:
        f.workspace.get_resource(kind, name)
        linked_projects.append("current project")
    except KeyError:
        pass
    if linked_projects and not force:
        console.print(
            f"[yellow]⚠[/] {kind.value} [bold]{name}[/] is linked in the current project."
        )
        confirm = typer.confirm("Unlink and uninstall?")
        if not confirm:
            console.print("[yellow]Cancelled.[/]")
            raise typer.Exit(0)
    try:
        f.uninstall(kind, name)
    except KeyError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Uninstalled {kind.value} [bold]{name}[/] from global store")


@app.command()
def migrate(
    resource_type: str = typer.Argument("skill", help="Resource type: skill"),
    name: Optional[str] = typer.Argument(
        None, help="Resource name (omit to migrate all)"
    ),
    from_registry: Optional[str] = typer.Option(
        None, "--from-registry", help="Migrate from a local registry by name"
    ),
    force_cleanup: bool = typer.Option(
        False, "--force-cleanup", help="Delete source files without prompting"
    ),
    no_cleanup: bool = typer.Option(
        False, "--no-cleanup", help="Preserve source files without prompting"
    ),
):
    """Import resources from ~/.agents/ or a local registry into the Skim global store."""
    f = get_skim()
    kind = parse_resource_type(resource_type)

    source_path: Optional[Path] = None
    if from_registry:
        sources = f.registry_manager.list_sources()
        if from_registry not in sources:
            console.print(f"[red]✗[/] Registry '{from_registry}' not found")
            raise typer.Exit(1)
        src = sources[from_registry]
        if src.type != RegistryType.local:
            console.print(
                f"[red]✗[/] Cannot migrate from git registry '{from_registry}'. "
                "Only local registries are supported."
            )
            raise typer.Exit(1)
        source_path = Path(src.url_or_path).expanduser().resolve()

    try:
        refs_src = f.migrate(kind, name, source_path)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    if not refs_src:
        console.print("[yellow]No resources to migrate.[/]")
        return
    for ref, _ in refs_src:
        console.print(f"[green]✓[/] Migrated {kind.value} [bold]{ref.name}[/]")
    console.print(f"\n[green]Done.[/] {len(refs_src)} resource(s) migrated.")

    _prompt_cleanup(refs_src, force_cleanup, no_cleanup)

    if name:
        console.print("Tip: Run [bold]skim add {kind.value} {name}[/] to activate it in this project.")
    else:
        console.print("Tip: Run [bold]skim ls[/] to see available resources, then [bold]skim add[/] to activate.")


# ─── Resource Management ─────────────────────────────────────────────────────


@app.command()
def add(
    resource_type: Optional[str] = typer.Argument(
        None, help="Resource type: skill"
    ),
    name: Optional[str] = typer.Argument(
        None, help="Resource name (optionally prefixed: registry:name)"
    ),
    from_url: Optional[str] = typer.Option(
        None, "--from", help="Git repository URL to install from"
    ),
    subdir: Optional[str] = typer.Option(
        None, "--subdir", help="Subdirectory within the repo (default: skills/<name>)"
    ),
):
    """Add and activate a resource in the project (resolves, stores, links, syncs agent).

    When called without arguments, opens an interactive checkbox prompt to select
    skills from the global store.
    """
    f = get_skim()

    # Interactive prompt when name is omitted
    if not name:
        selected = prompt_skill_selection(f, mode="add")
        if not selected:
            return
        linked_names = {l.name for l in f.workspace.list_links()}
        added = 0
        for skill_name in selected:
            if skill_name in linked_names:
                continue  # already installed, skip
            try:
                f.add(ResourceKind.skill, skill_name)
                console.print(f"[green]✓[/] Added [bold]{skill_name}[/]")
                added += 1
            except (FileNotFoundError, FileExistsError, ValueError) as e:
                console.print(f"[red]✗[/] {e}")
        if added == 0:
            console.print("[yellow]No new skills to add (all selected are already installed).[/]")
            return
        try:
            f.agent_sync()
        except RuntimeError:
            pass
        return

    kind = parse_resource_type(resource_type or "skill")
    try:
        ref = f.add(kind, name, from_url=from_url, subdir=subdir)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Added {kind.value} [bold]{ref.name}[/] (origin: {ref.origin})")


@app.command()
def rm(
    resource_type: Optional[str] = typer.Argument(
        None, help="Resource type: skill"
    ),
    name: Optional[str] = typer.Argument(
        None, help="Resource name to remove"
    ),
):
    """Remove a resource from the workspace (unlinks and syncs agent).

    When called without arguments, opens an interactive checkbox prompt to select
    linked skills to remove.
    """
    f = get_skim()

    # Interactive prompt when name is omitted
    if not name:
        selected = prompt_skill_selection(f, mode="remove")
        if not selected:
            return
        for skill_name in selected:
            try:
                ref = f.remove(ResourceKind.skill, skill_name)
                console.print(f"[green]✓[/] Removed {ref.kind.value} [bold]{ref.name}[/]")
            except (KeyError, RuntimeError) as e:
                console.print(f"[red]✗[/] {e}")
        try:
            f.agent_sync()
        except RuntimeError:
            pass
        return

    kind = parse_resource_type(resource_type or "skill")
    try:
        ref = f.remove(kind, name)
    except (KeyError, RuntimeError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Removed {kind.value} [bold]{ref.name}[/]")


@app.command()
def ls(
    resource_type: Optional[str] = typer.Argument(
        None, help="Filter by type: skills"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List resources in the workspace."""
    f = get_skim()
    kind = parse_resource_type(resource_type) if resource_type else None
    try:
        resources = f.list(kind)
    except FileNotFoundError as e:
        console.print("[red]✗[/] No Skim workspace found.")
        raise typer.Exit(1) from e
    if json_output:
        data = [r.model_dump(mode="json") for r in resources]
        print_json(data=data)
        return
    if not resources:
        console.print("[yellow]No resources in workspace.[/]")
        return
    table = Table(title="Workspace Resources")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Origin", style="green")
    for r in resources:
        table.add_row(r.name, r.kind.value, r.origin)
    console.print(table)


@app.command()
def info(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name"),
):
    """Show detailed information about a resource."""
    f = get_skim()
    kind = parse_resource_type(resource_type)
    ref = f.info(kind, name)
    if not ref:
        console.print(f"[red]✗[/] {kind.value} [bold]{name}[/] not found.")
        raise typer.Exit(1)
    table = Table(title=f"Resource: {ref.name}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")
    table.add_row("Name", ref.name)
    table.add_row("Type", ref.kind.value)
    table.add_row("Origin", ref.origin)
    table.add_row("Linked", "[green]✓[/]" if ref.linked else "")
    table.add_row("Path", str(ref.path) if ref.path else "N/A")
    if ref.path and ref.path.is_dir():
        from skim.agents._sync import get_variant_names
        variants = get_variant_names(ref.path)
        if variants:
            table.add_row("Variants", ", ".join(variants))
    console.print(table)


@app.command()
def skills():
    """Interactive multi-level menu for managing skills.

    Opens a ``questionary.select`` menu with options to add skills, remove
    skills, install from git, sync agents, and manage agent configuration.
    The command runs the selected action then exits.
    """
    f = get_skim()
    action = prompt_main_menu(f)
    if action is None:
        return

    if action == "add":
        selected = prompt_skill_selection(f, mode="add")
        if not selected:
            return
        linked_names = {l.name for l in f.workspace.list_links()}
        added = 0
        for skill_name in selected:
            if skill_name in linked_names:
                continue
            try:
                f.add(ResourceKind.skill, skill_name)
                console.print(f"[green]✓[/] Added [bold]{skill_name}[/]")
                added += 1
            except (FileNotFoundError, FileExistsError, ValueError) as e:
                console.print(f"[red]✗[/] {e}")
        if added == 0:
            console.print("[yellow]No new skills to add.[/]")
        try:
            f.agent_sync()
        except RuntimeError:
            pass

    elif action == "remove":
        selected = prompt_skill_selection(f, mode="remove")
        if not selected:
            return
        for skill_name in selected:
            try:
                ref = f.remove(ResourceKind.skill, skill_name)
                console.print(f"[green]✓[/] Removed {ref.kind.value} [bold]{ref.name}[/]")
            except (KeyError, RuntimeError) as e:
                console.print(f"[red]✗[/] {e}")
        try:
            f.agent_sync()
        except RuntimeError:
            pass

    elif action == "install":
        url, subdir = prompt_install_from_git()
        if not url:
            return
        try:
            ref = f.install(ResourceKind.skill, "from-git", from_url=url, subdir=subdir)
            console.print(f"[green]✓[/] Installed from git: [bold]{ref.name}[/]")
            f.workspace.add_resource(ref)
            from skim.core.linking import link_resource as _link_resource
            _link_resource(f.workspace, f.global_store, ResourceKind.skill, ref.name)
            f.agent_sync()
        except (FileNotFoundError, FileExistsError, ValueError, OSError, subprocess.TimeoutExpired) as e:
            console.print(f"[red]✗[/] {e}")

    elif action == "sync":
        try:
            result = f.agent_sync()
            agents_str = ", ".join(result["agents"])
            console.print(f"[green]✓[/] Synced {len(result['agents'])} agent(s): {agents_str}")
        except RuntimeError as e:
            console.print(f"[red]✗[/] {e}")

    elif action == "agents":
        from skim.agents.registry import AgentRegistry
        registry = AgentRegistry()
        agent_choice = prompt_agent_selection(registry)
        if agent_choice and agent_choice != ["none"]:
            for agent_name in agent_choice:
                try:
                    f.workspace.add_agent(agent_name)
                    console.print(f"[green]✓[/] Agent [bold]{agent_name}[/] added.")
                except ValueError as e:
                    console.print(f"[red]✗[/] {e}")
            try:
                f.agent_sync()
            except RuntimeError:
                pass


# ─── Global Store ────────────────────────────────────────────────────────────


global_app = typer.Typer(help="Manage the global Skim store")
app.add_typer(global_app, name="global")


@global_app.command("add")
def global_add(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    path: str = typer.Argument(..., help="Path to the resource"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Custom name for the resource"),
):
    """Add a resource to the global store."""
    f = get_skim()
    kind = parse_resource_type(resource_type)
    try:
        resource = f.global_add(kind, path, name)
    except (FileNotFoundError, FileExistsError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Added {kind.value} [bold]{resource.name}[/] to global store")


@global_app.command("ls")
def global_ls(
    resource_type: Optional[str] = typer.Argument(
        None, help="Filter by type: skills"
    ),
):
    """List resources in the global store."""
    f = get_skim()
    kind = parse_resource_type(resource_type) if resource_type else None
    resources = f.global_ls(kind)
    if not resources:
        console.print("[yellow]No resources in global store.[/]")
        return
    ws_skill_names = f._workspace_skill_names()
    table = Table(title="Global Store")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Source", style="green")
    table.add_column("In workspace", style="yellow")
    table.add_column("Path", style="white")
    for r in resources:
        in_ws = "[green]✓[/]" if r.name in ws_skill_names else "[dim]—[/]"
        table.add_row(r.name, r.kind.value, r.source, in_ws, str(r.path))
    console.print(table)


@global_app.command("rm")
def global_rm(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name to remove from store"),
):
    """Remove a resource from the global store."""
    f = get_skim()
    kind = parse_resource_type(resource_type)
    try:
        f.global_rm(kind, name)
    except KeyError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Removed {kind.value} [bold]{name}[/] from global store")


# ─── Registry ────────────────────────────────────────────────────────────────


registry_app = typer.Typer(help="Manage Skim registries")
app.add_typer(registry_app, name="registry")


@registry_app.command("add")
def registry_add(
    source: str = typer.Argument(..., help="Path or URL of the registry"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Custom name for the registry"),
):
    """Add a registry source."""
    f = get_skim()
    try:
        src = f.registry_add(source, name)
    except FileExistsError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Added registry [bold]{src.name}[/] ({src.type.value})")


@registry_app.command("ls")
def registry_ls():
    """List registered registry sources."""
    f = get_skim()
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


@registry_app.command("search")
def registry_search(
    query: str = typer.Argument(..., help="Search keyword"),
    registry: Optional[str] = typer.Option(None, "--registry", "-r", help="Filter by registry"),
    resource_type: Optional[str] = typer.Option(None, "--type", "-t", help="Filter by type"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search for resources across registries."""
    f = get_skim()
    kind = parse_resource_type(resource_type) if resource_type else None
    results = f.registry_search(query, registry, kind)
    if not results:
        console.print(f"[yellow]No results for '{query}'.[/]")
        return

    ws_skill_names = f._workspace_skill_names()

    if json_output:
        data = []
        for reg_name, resource in results:
            item = resource.model_dump(mode="json")
            item["registry"] = reg_name
            item["in_workspace"] = resource.name in ws_skill_names
            data.append(item)
        print_json(data=data)
        return

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


# ─── Agent ───────────────────────────────────────────────────────────────────


agent_app = typer.Typer(help="Manage AI agent configuration")
app.add_typer(agent_app, name="agent")


@agent_app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
):
    """Synchronize workspace resources with the active agent config."""
    f = get_skim()
    try:
        result = f.agent_sync(dry_run)
    except RuntimeError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    if dry_run:
        console.print("[blue]DRY-RUN[/]")
        console.print(f"   Agents: {', '.join(result['agents'])}")
        console.print(f"   Skills to add: {', '.join(result['skills_to_add']) or 'none'}")
    else:
        agents_str = ", ".join(result["agents"])
        console.print(f"[green]✓[/] Synced {len(result['agents'])} agent(s): {agents_str}")


@agent_app.command("list")
def list_agents(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all supported AI agents and their detection status."""
    f = get_skim()
    agents = f.list_agents()
    if json_output:
        print_json(data=agents)
        return
    table = Table(title="Supported Agents")
    table.add_column("Agent", style="cyan")
    table.add_column("ID", style="green")
    table.add_column("Directory", style="white")
    table.add_column("Detect", style="magenta")
    table.add_column("Status", style="yellow")
    for a in agents:
        status = "[green]ACTIVE[/]" if a["active"] else "—"
        table.add_row(
            a["id"].replace("-", " ").title(),
            a["id"],
            a["dir"],
            a["detect"],
            status,
        )
    console.print(table)


@agent_app.command("add")
def agent_add(
    name: str = typer.Argument(..., help="Agent name to add (e.g. opencode, claude)"),
):
    """Add an agent to the workspace config and sync skills."""
    f = get_skim()
    registry = AgentRegistry()
    if not registry.get_adapter(name):
        known = ", ".join(registry.get_agent_ids())
        console.print(f"[red]✗[/] Unknown agent '{name}'. Known agents: {known}")
        raise typer.Exit(1)
    try:
        f.workspace.add_agent(name)
    except ValueError as e:
        if "Unknown agent" in str(e):
            console.print(f"[red]✗[/] {e}")
            raise typer.Exit(1) from e
        raise
    try:
        f.agent_sync()
    except RuntimeError:
        pass
    console.print(f"[green]✓[/] Agent [bold]{name}[/] added and synced.")


@agent_app.command("remove")
def agent_remove(
    name: str = typer.Argument(..., help="Agent name to remove (e.g. claude)"),
):
    """Remove an agent from the workspace config and clean its skills."""
    f = get_skim()
    try:
        f.workspace.remove_agent(name)
    except KeyError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    adapter = f._find_adapter_by_name(name)
    if adapter:
        adapter.sync(f.project_root, [])
    console.print(f"[green]✓[/] Agent [bold]{name}[/] removed. Skills cleaned.")


@agent_app.command()
def detect():
    """Detect the active AI agent in the current project."""
    f = get_skim()
    detected = f.agent_detect()
    if detected:
        console.print(f"[green]✓[/] Detected: [bold]{detected}[/]")
    else:
        console.print("[yellow]No supported agent detected.[/]")


# ─── Update ─────────────────────────────────────────────────────────────────


@app.command()
def update(
    check_only: bool = typer.Option(False, "--check", help="Check without upgrading"),
    force: bool = typer.Option(False, "--force", help="Force re-check, ignore cache"),
):
    """Check for or install the latest version of skim."""
    from skim.core.update import UpdateChecker

    checker = UpdateChecker()

    if force:
        latest = checker.get_latest()
        if latest is None:
            console.print("[red]✗ Could not check for updates[/]")
            raise typer.Exit(1)
    else:
        latest = checker.check()
        if latest is None:
            console.print(f"[green]✓[/] skim is up to date (v{__version__})")
            return

    if not checker._is_newer(latest):
        console.print(f"[green]✓[/] skim is up to date (v{__version__})")
        return

    if check_only:
        console.print(
            f"[yellow]⚠[/] skim [bold]v{latest}[/] available "
            f"(current: v{__version__})"
        )
        return

    console.print("Updating skim...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "skim"],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            console.print(f"[red]✗[/] Update failed:\n{result.stderr.decode().strip()}")
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]✗[/] Update timed out.")
        raise typer.Exit(1)
    console.print(f"[green]✓[/] Updated to skim [bold]v{latest}[/]")


# ─── Update Check ──────────────────────────────────────────────────────────


def _show_update_notice() -> None:
    if os.environ.get("SKIM_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes", "on"):
        return
    if any(arg in sys.argv for arg in ("--version", "-V")):
        return
    try:
        from skim.core.update import UpdateChecker

        checker = UpdateChecker()
        latest = checker.check()
        if latest:
            console.print()
            console.print(
                f"[yellow]⚠[/] skim [bold]v{latest}[/] is available! "
                f"(you're on v{__version__})"
            )
            console.print("   Run [bold]skim update[/] to upgrade.")
    except Exception:
        pass


# ─── Entrypoint ──────────────────────────────────────────────────────────────


def run():
    # TTY detection: launch wizard when interactive with no arguments
    if len(sys.argv) <= 1:
        if sys.stdin.isatty():
            from skim.cli.wizard import run_wizard as _run_wizard
            _run_wizard()
            return
        # Non-interactive no-args: show help (preserves original behavior)
        app(["--help"])
        return

    error = None
    try:
        app()
    except SystemExit as e:
        error = e
    except BaseException as e:
        error = e

    _show_update_notice()

    if error is not None:
        raise error
