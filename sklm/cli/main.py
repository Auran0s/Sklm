"""Sklm CLI — main entrypoint with real backend."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import traceback as tb_mod
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print_json

from sklm import __version__
from sklm.api import Sklm
from sklm.models import RegistryType, ResourceKind
from sklm.agents.registry import AgentRegistry

app = typer.Typer(
    name="sklm",
    help="Skills manager for AI agents",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console()

_sklm: Optional[Sklm] = None
_tracker_start: float = 0.0
_tracker_command: str = ""
_tracker: Optional["UmamiTracker"] = None  # type: ignore[name-defined]


def get_tracker() -> Optional["UmamiTracker"]:
    global _tracker
    if _tracker is None:
        from sklm.store import GlobalStore
        from sklm.telemetry import UmamiTracker

        store = GlobalStore()
        cfg = store.get_telemetry_config()
        _tracker = UmamiTracker(
            umami_url=cfg.umami_url,
            website_id=cfg.website_id,
            enabled=cfg.enabled,
        )
    return _tracker


def get_sklm() -> Sklm:
    global _sklm
    if _sklm is None:
        _sklm = Sklm()
    return _sklm


def version_callback(value: bool):
    if value:
        console.print(f"sklm v{__version__}")
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

    is_interactive = sys.stdout.isatty() and os.environ.get("SKLM_NO_INTERACTIVE", "").lower() not in ("1", "true", "yes", "on")

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
    global _tracker_start, _tracker_command
    _tracker_start = time.monotonic()
    _tracker_command = ctx.invoked_subcommand or ""


def _prompt_agent_selection(f: Sklm) -> list[str]:
    """Show interactive prompt for agent selection."""
    registry = AgentRegistry()
    agent_ids = registry.get_agent_ids()

    console.print("\n[bold]No agent detected in this directory.[/]")
    console.print("[dim]Which agent(s) are you using?[/]\n")

    for i, aid in enumerate(agent_ids, 1):
        config = registry.get_agent_config(aid)
        label = f"{aid.replace('-', ' ').title():20s}"
        dir_name = config.get("dir_name", "?") if config else "?"
        console.print(f"  [{i}] {label}  [dim]({dir_name})[/]")

    console.print(f"  [c] cancel  [dim](skip agent setup)[/]")

    while True:
        choice = typer.prompt("\nEnter numbers separated by commas (e.g. 1,3,5)", default="")
        choice = choice.strip().lower()

        if choice == "c":
            console.print()
            return ["none"]

        selected: list[str] = []
        parts = choice.replace(",", " ").split()
        valid = True
        for p in parts:
            if p.isdigit():
                idx = int(p) - 1
                if 0 <= idx < len(agent_ids):
                    selected.append(agent_ids[idx])
                else:
                    console.print(f"[red]✗[/] Invalid number: {p}")
                    valid = False
                    break
            else:
                console.print(f"[red]✗[/] Invalid input: '{p}'. Use numbers or 'c' to cancel.")
                valid = False
                break

        if valid:
            console.print()
            return selected


# ─── Workspace ───────────────────────────────────────────────────────────────


@app.command()
def init(
    agent: Optional[list[str]] = typer.Option(
        None, "--agent", "-a", help="Agent(s) to configure (repeatable, auto-detect if omitted)"
    ),
):
    """Initialize a Sklm workspace in the current directory."""
    f = get_sklm()
    if f.workspace.exists():
        if agent:
            for a in agent:
                f.workspace.add_agent(a)
            console.print("[yellow]⚠[/] Workspace already exists at [bold].sklm/[/]")
            console.print(f"   Agents updated: [cyan]{', '.join(agent)}[/]")
            return
        console.print("[yellow]⚠[/] Workspace already exists at [bold].sklm/[/]")
        raise typer.Exit(1)
    if agent:
        agents = agent
    else:
        detected = f.agent_registry.detect(f.project_root)
        if detected:
            agents = detected
        else:
            agents = _prompt_agent_selection(f)
    detected = f.init_workspace(agents)
    label = ", ".join(detected) if detected != ["none"] else "[yellow]none[/]"
    console.print("[green]✓[/] Workspace created at [bold].sklm/[/]")
    console.print(f"   Agents: [cyan]{label}[/]")
    if detected == ["none"]:
        console.print("   [dim]Run 'sklm init --agent <name>' to configure an agent later.[/]")


@app.command()
def status(
    repair: bool = typer.Option(False, "--repair", help="Attempt to repair broken links"),
):
    """Show workspace status."""
    f = get_sklm()
    if not f.workspace.exists():
        console.print("[red]✗[/] No Sklm workspace found. Run [bold]sklm init[/] first.")
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
    linked = f.list_workspace_skills()
    if linked:
        table.add_row("Active project skills", ", ".join(r.name for r in linked))
    console.print(table)
    if state["broken_links"] > 0:
        console.print("\n[yellow]💡 Tip:[/] Run [bold]sklm status --repair[/] to fix broken links")
    external_count = state.get("external_skills_count", 0)
    if external_count > 0:
        console.print(
            f"\n[yellow]⚠ {external_count} skills found outside Sklm's store[/]"
            "\n   These may be globally visible to your AI agent in every project."
            "\n   Use [bold]sklm migrate[/] to import them into the Sklm store."
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
    f = get_sklm()
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
    f = get_sklm()
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
    """Import resources from ~/.agents/ or a local registry into the Sklm global store."""
    f = get_sklm()
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
        console.print("Tip: Run [bold]sklm add {kind.value} {name}[/] to activate it in this project.")
    else:
        console.print("Tip: Run [bold]sklm ls[/] to see available resources, then [bold]sklm add[/] to activate.")


# ─── Resource Management ─────────────────────────────────────────────────────


@app.command()
def add(
    resource_type: Optional[str] = typer.Argument(
        None, help="Resource type: skill (omit to use interactive picker)"
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
    """Add and activate a resource in the project. Launch interactive picker when no args given."""
    if resource_type is None:
        from sklm.tui import run_tui

        result = run_tui("add")
        if result is None:
            raise typer.Exit(0)
        console.print(f"[green]✓[/] Added {len(result)} skill(s)")
        return
    f = get_sklm()
    kind = parse_resource_type(resource_type)
    try:
        ref = f.add(kind, name or "", from_url=from_url, subdir=subdir)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Added {kind.value} [bold]{ref.name}[/] (origin: {ref.origin})")


@app.command()
def rm(
    resource_type: Optional[str] = typer.Argument(
        None, help="Resource type: skill (omit to use interactive picker)"
    ),
    name: Optional[str] = typer.Argument(
        None, help="Resource name to remove"
    ),
):
    """Remove a resource from the workspace. Launch interactive picker when no args given."""
    if resource_type is None:
        from sklm.tui import run_tui

        result = run_tui("remove")
        if result is None:
            raise typer.Exit(0)
        console.print(f"[green]✓[/] Removed {len(result)} skill(s)")
        return
    f = get_sklm()
    kind = parse_resource_type(resource_type)
    try:
        ref = f.remove(kind, name or "")
    except (KeyError, RuntimeError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Removed {kind.value} [bold]{ref.name}[/]")


@app.command()
def skills():
    """Open interactive skill manager."""
    from sklm.tui import run_tui

    result = run_tui("manage")
    if result is None:
        return
    console.print(f"[green]✓[/] Updated {len(result)} skill(s)")


@app.command()
def ls(
    resource_type: Optional[str] = typer.Argument(
        None, help="Filter by type: skills"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List resources in the workspace."""
    f = get_sklm()
    kind = parse_resource_type(resource_type) if resource_type else None
    try:
        resources = f.list(kind)
    except FileNotFoundError as e:
        console.print("[red]✗[/] No Sklm workspace found.")
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
    f = get_sklm()
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
        from sklm.agents._sync import get_variant_names
        variants = get_variant_names(ref.path)
        if variants:
            table.add_row("Variants", ", ".join(variants))
    console.print(table)


# ─── Global Store ────────────────────────────────────────────────────────────


global_app = typer.Typer(help="Manage the global Sklm store")
app.add_typer(global_app, name="global")


@global_app.command("add")
def global_add(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    path: str = typer.Argument(..., help="Path to the resource"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Custom name for the resource"),
):
    """Add a resource to the global store."""
    f = get_sklm()
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
    f = get_sklm()
    kind = parse_resource_type(resource_type) if resource_type else None
    resources = f.global_ls(kind)
    if not resources:
        console.print("[yellow]No resources in global store.[/]")
        return
    table = Table(title="Global Store")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Source", style="green")
    table.add_column("Path", style="white")
    for r in resources:
        table.add_row(r.name, r.kind.value, r.source, str(r.path))
    console.print(table)


@global_app.command("rm")
def global_rm(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name to remove from store"),
):
    """Remove a resource from the global store."""
    f = get_sklm()
    kind = parse_resource_type(resource_type)
    try:
        f.global_rm(kind, name)
    except KeyError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Removed {kind.value} [bold]{name}[/] from global store")


# ─── Registry ────────────────────────────────────────────────────────────────


registry_app = typer.Typer(help="Manage Sklm registries")
app.add_typer(registry_app, name="registry")


@registry_app.command("add")
def registry_add(
    source: str = typer.Argument(..., help="Path or URL of the registry"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="Custom name for the registry"),
):
    """Add a registry source."""
    f = get_sklm()
    try:
        src = f.registry_add(source, name)
    except FileExistsError as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Added registry [bold]{src.name}[/] ({src.type.value})")


@registry_app.command("ls")
def registry_ls():
    """List registered registry sources."""
    f = get_sklm()
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
):
    """Search for resources across registries."""
    f = get_sklm()
    kind = parse_resource_type(resource_type) if resource_type else None
    results = f.registry_search(query, registry, kind)
    if not results:
        console.print(f"[yellow]No results for '{query}'.[/]")
        return
    table = Table(title=f"Search Results: '{query}'")
    table.add_column("Registry", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Type", style="magenta")
    table.add_column("Path", style="white")
    for reg_name, resource in results:
        table.add_row(reg_name, resource.name, resource.kind.value, str(resource.path))
    console.print(table)


# ─── Agent ───────────────────────────────────────────────────────────────────


agent_app = typer.Typer(help="Manage AI agent configuration")
app.add_typer(agent_app, name="agent")


@agent_app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without applying"),
):
    """Synchronize workspace resources with the active agent config."""
    f = get_sklm()
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
    f = get_sklm()
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
    f = get_sklm()
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
    f = get_sklm()
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
    f = get_sklm()
    detected = f.agent_detect()
    if detected:
        console.print(f"[green]✓[/] Detected: [bold]{detected}[/]")
    else:
        console.print("[yellow]No supported agent detected.[/]")


# ─── Telemetry ────────────────────────────────────────────────────────────────


telemetry_app = typer.Typer(help="Manage telemetry settings")
app.add_typer(telemetry_app, name="telemetry")


@telemetry_app.command("on")
def telemetry_on():
    """Enable telemetry."""
    from sklm.store import GlobalStore

    store = GlobalStore()
    cfg = store.get_telemetry_config()
    cfg.enabled = True
    store.set_telemetry_config(cfg)
    console.print("[green]✓[/] Telemetry enabled")


@telemetry_app.command("off")
def telemetry_off():
    """Disable telemetry."""
    from sklm.store import GlobalStore

    store = GlobalStore()
    cfg = store.get_telemetry_config()
    cfg.enabled = False
    store.set_telemetry_config(cfg)
    console.print("[yellow]⚠[/] Telemetry disabled")


@telemetry_app.command("status")
def telemetry_status():
    """Show telemetry status."""
    from sklm.store import GlobalStore

    store = GlobalStore()
    cfg = store.get_telemetry_config()
    tracker = get_tracker()

    if not tracker:
        console.print("[yellow]⚠ Telemetry not initialized[/]")
        raise typer.Exit(1)

    if not cfg.umami_url or not cfg.website_id:
        console.print("[yellow]⚠ Telemetry inactive[/]")
        console.print("   Configure SKLM_UMAMI_URL and SKLM_WEBSITE_ID")
        console.print("   or run: [bold]sklm telemetry on[/]")
        raise typer.Exit(1)

    if tracker.active:
        console.print(f"[green]Active[/] → {cfg.umami_url}")
    else:
        console.print("[yellow]⚠ Telemetry disabled[/]")
        console.print("   Run [bold]sklm telemetry on[/] to enable")


@telemetry_app.command("ping")
def telemetry_ping():
    """Send a test event to verify telemetry connectivity."""
    tracker = get_tracker()

    if not tracker:
        console.print("[red]✗ Telemetry not initialized[/]")
        raise typer.Exit(1)

    if not tracker.active:
        console.print("[yellow]⚠ Telemetry disabled or not configured[/]")
        console.print("   Run [bold]sklm telemetry on[/] to enable")
        raise typer.Exit(1)

    console.print("[dim]Sending test event...[/]")
    ok, status, dur = tracker.ping()
    if ok:
        console.print(f"[green]✓ Ping succeeded[/] ({status}, {dur:.0f}ms)")
    else:
        console.print(f"[red]✗ Ping failed[/] ({status})")
        raise typer.Exit(1)


# ─── Update ─────────────────────────────────────────────────────────────────


@app.command()
def update(
    check_only: bool = typer.Option(False, "--check", help="Check without upgrading"),
    force: bool = typer.Option(False, "--force", help="Force re-check, ignore cache"),
):
    """Check for or install the latest version of sklm."""
    from sklm.core.update import UpdateChecker

    checker = UpdateChecker()

    if force:
        latest = checker.get_latest()
        if latest is None:
            console.print("[red]✗ Could not check for updates[/]")
            raise typer.Exit(1)
    else:
        latest = checker.check()
        if latest is None:
            console.print(f"[green]✓[/] sklm is up to date (v{__version__})")
            return

    if not checker._is_newer(latest):
        console.print(f"[green]✓[/] sklm is up to date (v{__version__})")
        return

    if check_only:
        console.print(
            f"[yellow]⚠[/] sklm [bold]v{latest}[/] available "
            f"(current: v{__version__})"
        )
        return

    repo_root = checker.find_repo_root()
    if repo_root is None:
        console.print("[red]✗[/] Cannot find the sklm git repository.")
        console.print(f"   Reinstall from [link]{checker.github_repo_url}[/]")
        raise typer.Exit(1)

    tag = f"v{latest.lstrip('v')}"
    console.print(f"Fetching tags from origin...")
    try:
        result = subprocess.run(
            ["git", "fetch", "--tags"],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            console.print(f"[red]✗[/] git fetch failed:\n{result.stderr.decode().strip()}")
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]✗[/] git fetch timed out.")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print("[red]✗[/] git not found.")
        raise typer.Exit(1)

    console.print(f"Checking out {tag}...")
    try:
        result = subprocess.run(
            ["git", "checkout", tag],
            cwd=repo_root,
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            console.print(f"[red]✗[/] git checkout failed:\n{result.stderr.decode().strip()}")
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]✗[/] git checkout timed out.")
        raise typer.Exit(1)

    console.print("Reinstalling...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-e", str(repo_root)],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            console.print(f"[red]✗[/] pip install failed:\n{result.stderr.decode().strip()}")
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]✗[/] pip install timed out.")
        raise typer.Exit(1)
    console.print(f"[green]✓[/] Updated to sklm [bold]v{latest}[/]")


# ─── Update Check ──────────────────────────────────────────────────────────


def _show_update_notice() -> None:
    if os.environ.get("SKLM_NO_UPDATE_CHECK", "").lower() in ("1", "true", "yes", "on"):
        return
    if any(arg in sys.argv for arg in ("--version", "-V")):
        return
    try:
        from sklm.core.update import UpdateChecker

        checker = UpdateChecker()
        latest = checker.check()
        if latest:
            console.print()
            console.print(
                f"[yellow]⚠[/] sklm [bold]v{latest}[/] is available! "
                f"(you're on v{__version__})"
            )
            console.print("   Run [bold]sklm update[/] to upgrade.")
    except Exception:
        pass


# ─── Entrypoint ──────────────────────────────────────────────────────────────


def run():
    global _tracker_command
    error = None
    try:
        app()
    except SystemExit as e:
        error = e
    except BaseException as e:
        error = e

    _track_success = True
    _track_error = None
    _track_error_message = None
    _track_traceback = None

    if isinstance(error, SystemExit):
        cause = getattr(error, "__cause__", None)
        if cause:
            _track_success = False
            _track_error = type(cause).__name__
            _track_error_message = (str(cause).replace(str(Path.home()), "~")) or None
            tb_frames = tb_mod.extract_tb(cause.__traceback__)
            if tb_frames:
                tail = tb_frames[-3:]
                _track_traceback = "".join(tb_mod.format_list(tail)).replace(str(Path.home()), "~").rstrip()
        else:
            _track_success = error.code in (None, 0)
            _track_error = None if _track_success else "error"
    elif error is not None:
        _track_success = False
        _track_error = type(error).__name__
        _track_error_message = (str(error).replace(str(Path.home()), "~")) or None

    if _tracker_start > 0:
        duration = (time.monotonic() - _tracker_start) * 1000
        tracker = get_tracker()
        if tracker:
            tracker.track_command(
                _tracker_command,
                _track_success,
                duration,
                _track_error,
                _track_error_message,
                _track_traceback,
            )

    _show_update_notice()

    if error is not None:
        raise error
