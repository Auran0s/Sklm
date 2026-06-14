"""Sklm CLI — main entrypoint with real backend."""

from __future__ import annotations

import time
import traceback as tb_mod
from pathlib import Path
from typing import Optional

import click
import typer
from rich.console import Console
from rich.table import Table
from rich import print_json

from sklm import __version__
from sklm.api import Sklm
from sklm.models import ResourceKind

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


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V", help="Show version", callback=version_callback
    ),
):
    global _tracker_start, _tracker_command
    _tracker_start = time.monotonic()
    ctx = click.get_current_context()
    _tracker_command = ctx.invoked_subcommand or ""


# ─── Workspace ───────────────────────────────────────────────────────────────


@app.command()
def init(
    agent: Optional[str] = typer.Option(
        None, "--agent", "-a", help="Agent to configure (auto-detect if omitted)"
    ),
):
    """Initialize a Sklm workspace in the current directory."""
    f = get_sklm()
    if f.workspace.exists():
        if agent:
            f.set_agent(agent)
            console.print("[yellow]⚠[/] Workspace already exists at [bold].sklm/[/]")
            console.print(f"   Agent updated to: [cyan]{agent}[/]")
            return
        console.print("[yellow]⚠[/] Workspace already exists at [bold].sklm/[/]")
        raise typer.Exit(1)
    detected = f.init_workspace(agent)
    console.print("[green]✓[/] Workspace created at [bold].sklm/[/]")
    console.print(f"   Agent: [cyan]{detected}[/]")


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
    table.add_row("Agent", state["agent"])
    table.add_row("Skills", str(state["skills"]))
    table.add_row("Total links", str(state["total_links"]))
    table.add_row("Broken links", str(state["broken_links"]))
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
    except (FileNotFoundError, FileExistsError, ValueError) as e:
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
):
    """Import resources from ~/.agents/ into the Sklm global store."""
    f = get_sklm()
    kind = parse_resource_type(resource_type)
    try:
        refs = f.migrate(kind, name)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    if not refs:
        console.print("[yellow]No resources to migrate.[/]")
        return
    for ref in refs:
        console.print(f"[green]✓[/] Migrated {kind.value} [bold]{ref.name}[/]")
    console.print(f"\n[green]Done.[/] {len(refs)} resource(s) migrated.")
    if name:
        console.print("Tip: Run [bold]sklm add {kind.value} {name}[/] to activate it in this project.")
    else:
        console.print("Tip: Run [bold]sklm ls[/] to see available resources, then [bold]sklm add[/] to activate.")


# ─── Resource Management ─────────────────────────────────────────────────────


@app.command()
def add(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name (optionally prefixed: registry:name)"),
    from_url: Optional[str] = typer.Option(
        None, "--from", help="Git repository URL to install from"
    ),
    subdir: Optional[str] = typer.Option(
        None, "--subdir", help="Subdirectory within the repo (default: skills/<name>)"
    ),
):
    """Add and activate a resource in the project (resolves, stores, links, syncs agent)."""
    f = get_sklm()
    kind = parse_resource_type(resource_type)
    try:
        ref = f.add(kind, name, from_url=from_url, subdir=subdir)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e
    console.print(f"[green]✓[/] Added {kind.value} [bold]{ref.name}[/] (origin: {ref.origin})")


@app.command()
def rm(
    resource_type: str = typer.Argument(..., help="Resource type: skill"),
    name: str = typer.Argument(..., help="Resource name to remove"),
):
    """Remove a resource from the workspace (unlinks and syncs agent)."""
    f = get_sklm()
    kind = parse_resource_type(resource_type)
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
        console.print(f"   Agent: {result['agent']}")
        console.print(f"   Skills to add: {', '.join(result['skills_to_add']) or 'none'}")
    else:
        console.print(f"[green]✓[/] Synced with {result['agent']}")


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

    if error is not None:
        raise error
