"""Sklm CLI — main entrypoint with real backend."""

from __future__ import annotations

import os
import re
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
from sklm.cli.prompts import (
    prompt_agent_selection,
    prompt_discovered_selection,
    prompt_install_from_git,
    prompt_main_menu,
    prompt_skill_selection,
)
from sklm.models import RegistryType, ResourceKind
from sklm.core.sources import SourceParseError, looks_like_source
from sklm.core.fetch import SourceFetchError
from sklm.agents.registry import AgentRegistry

app = typer.Typer(
    name="sklm",
    help="Skills manager for AI agents — run without arguments for interactive mode",
    no_args_is_help=False,
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


_LEGACY_TYPE_TOKENS = ("skill", "skills")


def _legacy_type_error(command: str, corrected: str) -> None:
    """Report that the resource-type argument was removed from *command*."""
    console.print(
        f"[red]✗[/] The resource-type argument was removed from "
        f"[bold]sklm {command}[/]."
    )
    console.print(f"   Use [bold]{corrected}[/] instead.")
    raise typer.Exit(1)


def _single_positional(
    values: Optional[list[str]], command: str, corrected: str
) -> Optional[str]:
    """Return the single positional argument, rejecting the legacy type token."""
    if not values:
        return None
    if values[0] in _LEGACY_TYPE_TOKENS:
        _legacy_type_error(command, corrected)
    if len(values) > 1:
        console.print(
            f"[red]✗[/] Expected at most one argument for [bold]sklm {command}[/]."
        )
        raise typer.Exit(1)
    return values[0]


def _positional_names(
    values: Optional[list[str]], command: str, corrected: str
) -> list[str]:
    """Return resource names, rejecting the legacy type token."""
    if not values:
        return []
    if values[0] in _LEGACY_TYPE_TOKENS:
        _legacy_type_error(command, corrected)
    return list(values)


def _print_discovered(resolved) -> None:
    """Print the skills found in a resolved source."""
    if not resolved.skills:
        console.print("[yellow]No skills found in this source.[/]")
        return
    table = Table(title=f"Skills in {resolved.parsed.display}")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    for skill in resolved.skills:
        table.add_row(skill.name, skill.description or "")
    console.print(table)


def _interactive_add(f: Sklm) -> None:
    """Interactive picker over skills in the global store."""
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
        except (FileNotFoundError, FileExistsError, ValueError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
    if added == 0:
        console.print(
            "[yellow]No new skills to add (all selected are already installed).[/]"
        )
        return
    try:
        f.agent_sync()
    except RuntimeError:
        pass


def _interactive_rm(f: Sklm) -> None:
    """Interactive picker over skills linked in the workspace."""
    selected = prompt_skill_selection(f, mode="remove")
    if not selected:
        return
    for skill_name in selected:
        try:
            ref = f.remove(ResourceKind.skill, skill_name)
            console.print(f"[green]✓[/] Removed skill [bold]{ref.name}[/]")
        except (KeyError, RuntimeError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
    try:
        f.agent_sync()
    except RuntimeError:
        pass


def _run_source_command(
    f: Sklm,
    source: str,
    skill_filters: list[str],
    all_: bool,
    list_: bool,
    ref: Optional[str],
    subdir: Optional[str],
    activate: bool,
) -> None:
    """Resolve *source*, select skills, and store (and optionally activate) them."""
    if not all_ and not skill_filters and not list_:
        if not sys.stdout.isatty():
            console.print(
                "[red]✗[/] No skill selected. Use [bold]--skill <name>[/], "
                "[bold]--all[/], or [bold]--list[/]."
            )
            raise typer.Exit(1)

    console.print(f"[dim]Resolving {source}...[/]")
    try:
        resolved = f.resolve_source(source, subdir=subdir)
    except (SourceParseError, SourceFetchError, ValueError, OSError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e

    if list_:
        _print_discovered(resolved)
        return

    if not resolved.skills:
        console.print(f"[red]✗[/] No skills found in '{source}'.")
        raise typer.Exit(1)

    if not skill_filters and not all_:
        chosen = prompt_discovered_selection(resolved.skills)
        if not chosen:
            return
        skill_filters = chosen

    try:
        if activate:
            refs = f.add_source(
                source, skills=skill_filters, all_=all_, subdir=subdir, ref=ref
            )
        else:
            refs = f.install_source(
                source, skills=skill_filters, all_=all_, subdir=subdir, ref=ref
            )
    except (SourceParseError, SourceFetchError, ValueError, FileNotFoundError, OSError) as e:
        console.print(f"[red]✗[/] {e}")
        raise typer.Exit(1) from e

    verb = "Added" if activate else "Installed"
    for resource_ref in refs:
        console.print(
            f"[green]✓[/] {verb} skill [bold]{resource_ref.name}[/] "
            f"(from {resource_ref.origin})"
        )


def _resolve_source_args(
    command: str,
    corrected: str,
    values: Optional[list[str]],
    from_url: Optional[str],
    skill: Optional[list[str]],
) -> tuple[Optional[str], Optional[str], list[str]]:
    """Split positionals and ``--from`` into (source, bare name, skill filters).

    A source is returned in the first slot. When the positional is a stored
    skill name instead, it is returned in the second slot so the caller can
    take the store lookup path.
    """
    positional = _single_positional(values, command, corrected)
    filters = list(skill or [])

    if from_url:
        if positional and not looks_like_source(positional):
            filters.append(positional)
        return from_url, None, filters

    if positional is None:
        return None, None, filters

    if looks_like_source(positional):
        return positional, None, filters

    return None, positional, filters


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


def _get_agent_selection_for_init(f: Sklm) -> list[str]:
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
    """Initialize a Sklm workspace in the current directory. Use --agent to add agents (re-run to update an existing workspace)."""
    f = get_sklm()
    if f.workspace.exists():
        if agent:
            for a in agent:
                f.workspace.add_agent(a)
            # Sync agent config directories immediately so the user doesn't
            # need a separate `sklm agent sync` step.
            try:
                f.agent_sync()
            except RuntimeError as e:
                console.print(f"[yellow]⚠[/] Agent sync failed: {e}")
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
            agents = _get_agent_selection_for_init(f)
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
    source: Optional[list[str]] = typer.Argument(
        None,
        help="Source to install from (owner/repo, URL, or local path), or a skill name",
    ),
    skill: Optional[list[str]] = typer.Option(
        None, "--skill", "-s", help="Skill to install from the source (repeatable)"
    ),
    all_: bool = typer.Option(
        False, "--all", help="Install every skill found in the source"
    ),
    list_: bool = typer.Option(
        False, "--list", "-l", help="List the skills found in the source without installing"
    ),
    ref: Optional[str] = typer.Option(
        None, "--ref", help="Git ref (branch, tag, or commit) to use"
    ),
    from_url: Optional[str] = typer.Option(
        None, "--from", help="Source URL (alias for the positional argument)"
    ),
    subdir: Optional[str] = typer.Option(
        None, "--subdir", help="Restrict discovery to this subdirectory of the source"
    ),
):
    """Install a skill into the global store without activating it."""
    f = get_sklm()
    source_value, bare_name, filters = _resolve_source_args(
        "install", "sklm install my-skill", source, from_url, skill
    )

    if source_value is None and bare_name is None:
        console.print(
            "[red]✗[/] Provide a source or a skill name. Run "
            "[bold]sklm install --help[/] for usage."
        )
        raise typer.Exit(1)

    if source_value is None:
        try:
            resource_ref = f.install(ResourceKind.skill, bare_name)
        except (FileNotFoundError, FileExistsError, ValueError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
            raise typer.Exit(1) from e
        console.print(
            f"[green]✓[/] Installed skill [bold]{resource_ref.name}[/] in global store"
        )
        if resource_ref.origin:
            console.print(f"   Source: {resource_ref.origin}")
        return

    _run_source_command(
        f, source_value, filters, all_, list_, ref, subdir, activate=False
    )


@app.command()
def uninstall(
    names: Optional[list[str]] = typer.Argument(
        None, help="Skill name(s) to uninstall"
    ),
    force: bool = typer.Option(False, "--force", help="Skip confirmation"),
):
    """Remove a skill from the global store permanently."""
    f = get_sklm()
    targets = _positional_names(names, "uninstall", "sklm uninstall my-skill")
    if not targets:
        console.print("[red]✗[/] Provide a skill name to uninstall.")
        raise typer.Exit(1)

    kind = ResourceKind.skill
    for name in targets:
        linked = f.workspace.get_resource(kind, name)
        if linked and not force:
            console.print(
                f"[yellow]⚠[/] skill [bold]{name}[/] is linked in the current project."
            )
            if not typer.confirm("Unlink and uninstall?"):
                console.print("[yellow]Cancelled.[/]")
                continue
        try:
            f.uninstall(kind, name)
        except (KeyError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
            raise typer.Exit(1) from e
        console.print(
            f"[green]✓[/] Uninstalled skill [bold]{name}[/] from global store"
        )


@app.command()
def migrate(
    names: Optional[list[str]] = typer.Argument(
        None, help="Skill name to migrate (omit to migrate all)"
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
    """Import skills from ~/.agents/ or a local registry into the Sklm global store."""
    f = get_sklm()
    kind = ResourceKind.skill

    targets = _positional_names(names, "migrate", "sklm migrate my-skill")
    if len(targets) > 1:
        console.print("[red]✗[/] Provide at most one skill name.")
        raise typer.Exit(1)
    name = targets[0] if targets else None

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
    source: Optional[list[str]] = typer.Argument(
        None,
        help="Source to install from (owner/repo, URL, or local path), or a stored skill name",
    ),
    skill: Optional[list[str]] = typer.Option(
        None, "--skill", "-s", help="Skill to install from the source (repeatable)"
    ),
    all_: bool = typer.Option(
        False, "--all", help="Install every skill found in the source"
    ),
    list_: bool = typer.Option(
        False, "--list", "-l", help="List the skills found in the source without installing"
    ),
    ref: Optional[str] = typer.Option(
        None, "--ref", help="Git ref (branch, tag, or commit) to use"
    ),
    from_url: Optional[str] = typer.Option(
        None, "--from", help="Source URL (alias for the positional argument)"
    ),
    subdir: Optional[str] = typer.Option(
        None, "--subdir", help="Restrict discovery to this subdirectory of the source"
    ),
):
    """Add and activate a skill in the project.

    With a source, discovers the skills it contains and installs the selected
    ones. With a plain name, resolves the skill from the global store. With no
    argument, opens an interactive picker over the global store.
    """
    f = get_sklm()
    source_value, bare_name, filters = _resolve_source_args(
        "add", "sklm add my-skill", source, from_url, skill
    )

    if source_value is None and bare_name is None:
        if list_ or all_ or filters:
            console.print("[red]✗[/] Provide a source to install from.")
            raise typer.Exit(1)
        _interactive_add(f)
        return

    if source_value is None:
        try:
            ref = f.add(ResourceKind.skill, bare_name)
        except (FileNotFoundError, FileExistsError, ValueError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
            raise typer.Exit(1) from e
        console.print(
            f"[green]✓[/] Added skill [bold]{ref.name}[/] (origin: {ref.origin})"
        )
        return

    _run_source_command(
        f, source_value, filters, all_, list_, ref, subdir, activate=True
    )


@app.command()
def rm(
    names: Optional[list[str]] = typer.Argument(
        None, help="Skill name(s) to remove"
    ),
):
    """Remove a skill from the workspace (unlinks and syncs agent).

    When called without arguments, opens an interactive checkbox prompt to select
    linked skills to remove.
    """
    f = get_sklm()
    targets = _positional_names(names, "rm", "sklm rm my-skill")

    if not targets:
        _interactive_rm(f)
        return

    kind = ResourceKind.skill
    for name in targets:
        try:
            ref = f.remove(kind, name)
        except (KeyError, RuntimeError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
            raise typer.Exit(1) from e
        console.print(f"[green]✓[/] Removed skill [bold]{ref.name}[/]")


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


@app.command()
def skills():
    """Interactive multi-level menu for managing skills.

    Opens a ``questionary.select`` menu with options to add skills, remove
    skills, install from git, sync agents, and manage agent configuration.
    The command runs the selected action then exits.
    """
    f = get_sklm()
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
            resolved = f.resolve_source(url, subdir=subdir)
        except (SourceParseError, SourceFetchError, ValueError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
            return
        if not resolved.skills:
            console.print("[yellow]No skills found in this source.[/]")
            return
        chosen = prompt_discovered_selection(resolved.skills)
        if not chosen:
            return
        try:
            refs = f.add_source(url, skills=chosen, subdir=subdir)
        except (SourceParseError, SourceFetchError, ValueError, FileNotFoundError, OSError) as e:
            console.print(f"[red]✗[/] {e}")
            return
        for resource_ref in refs:
            console.print(f"[green]✓[/] Added [bold]{resource_ref.name}[/]")

    elif action == "sync":
        try:
            result = f.agent_sync()
            agents_str = ", ".join(result["agents"])
            console.print(f"[green]✓[/] Synced {len(result['agents'])} agent(s): {agents_str}")
        except RuntimeError as e:
            console.print(f"[red]✗[/] {e}")

    elif action == "agents":
        from sklm.agents.registry import AgentRegistry
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
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Search for resources across registries."""
    f = get_sklm()
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

    console.print("Updating sklm...")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "sklm-cli"],
            capture_output=True,
            timeout=60,
        )
        if result.returncode != 0:
            console.print(f"[red]✗[/] Update failed:\n{result.stderr.decode().strip()}")
            raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]✗[/] Update timed out.")
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

    # TTY detection: launch wizard when interactive with no arguments
    if len(sys.argv) <= 1:
        if sys.stdin.isatty():
            from sklm.cli.wizard import run_wizard as _run_wizard
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
                raw = "".join(tb_mod.format_list(tail))
                # Sanitize: replace all absolute file paths with just the filename
                sanitized = re.sub(r'File "([^"]+)", line (\d+)',
                                   lambda m: f'File "{Path(m.group(1)).name}", line {m.group(2)}',
                                   raw)
                _track_traceback = sanitized.rstrip()
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
