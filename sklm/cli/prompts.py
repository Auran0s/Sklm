"""Interactive prompt functions for the Sklm CLI.

Replaces the former TUI (``sklm/tui.py``) with inline keyboard-driven prompts
using ``questionary`` (↑↓ navigate, Space toggle, Enter confirm).
"""

from __future__ import annotations

import sys
from typing import Optional

import questionary
import typer
from rich.console import Console
from rich.table import Table

from sklm.agents.registry import AgentRegistry
from sklm.models import ResourceKind

console = Console()


def _ensure_tty() -> None:
    """Raise a RuntimeError if stdout is not a TTY.

    All interactive prompt functions should call this first so they fail
    early with a clear message when used in non-interactive contexts (piped
    output, CI, etc.).
    """
    if not sys.stdout.isatty():
        msg = (
            "Interactive prompts require a terminal (TTY). "
            "Use command-line arguments instead, e.g. "
            "'sklm add skill <name>' or 'sklm rm skill <name>'."
        )
        raise RuntimeError(msg)


def _make_skill_choices(
    sklm: object,
    mode: str = "add",
) -> list[questionary.Choice]:
    """Build a list of ``questionary.Choice`` items for skill selection.

    Parameters
    ----------
    sklm
        A ``Sklm`` facade instance.
    mode
        ``"add"`` to show all global skills (linked ones pre-checked),
        ``"remove"`` to show only currently linked skills.

    Returns
    -------
    list[questionary.Choice]
        Choice objects each with a Rich-formatted title and the skill
        name as the value.
    """
    from sklm.api import Sklm

    sklm_obj = sklm  # type: Sklm
    global_skills = sklm_obj.global_store.list_resources(ResourceKind.skill)
    linked_names = {l.name for l in sklm_obj.workspace.list_links()}

    if mode == "remove":
        # Only linked skills can be removed
        candidates = [r for r in global_skills if r.name in linked_names]
    else:
        # Show ALL global skills — linked ones appear pre-checked
        candidates = list(global_skills)

    choices: list[questionary.Choice] = []
    for r in candidates:
        title = f"{r.name:{24}}"
        checked = r.name in linked_names
        choices.append(questionary.Choice(title=title, value=r.name, checked=checked))
    return choices


def _print_skill_header(choices: list[questionary.Choice], title: str) -> None:
    """Print a Rich-formatted header table above the prompt."""
    if not choices:
        return
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("icon", style="cyan", width=3)
    table.add_column("name", style="bold cyan", width=26)
    table.add_column("description", style="white", no_wrap=True)
    for c in choices:
        table.add_row("☐", c.title.strip(), "")
    console.print(f"\n[bold]{title}[/]")
    console.print(table)
    console.print("[dim]↑↓ Navigate   Space Toggle   Enter Confirm   Esc Cancel[/]\n")


def prompt_skill_selection(
    sklm: object,
    mode: str = "add",
    title: str = "Select skills",
) -> list[str]:
    """Show an interactive checkbox for selecting skills.

    Parameters
    ----------
    sklm
        A ``Sklm`` facade instance.
    mode
        ``"add"`` to select from unlinked global skills, ``"remove"`` to
        select from currently linked skills.
    title
        Heading text displayed above the prompt.

    Returns
    -------
    list[str]
        The names of the skill(s) the user selected.
    """
    _ensure_tty()
    choices = _make_skill_choices(sklm, mode)
    if not choices:
        if mode == "remove":
            console.print("[yellow]No linked skills to remove.[/]")
        else:
            console.print(
                "[yellow]No unlinked skills available in the global store.[/]"
                "\n   Use [bold]sklm install skill <name>[/] to add skills first."
            )
        return []

    selected = questionary.checkbox(
        title,
        choices=choices,
    ).ask()

    if selected is None:
        return []
    return selected


def prompt_install_from_git() -> tuple[str, str | None]:
    """Prompt for a Git URL and optional subdirectory.

    Returns
    -------
    tuple[str, str | None]
        ``(git_url, subdirectory)`` where *subdirectory* may be ``None``.
    """
    _ensure_tty()
    url = questionary.text("Git repository URL:").ask()
    if not url:
        return ("", None)

    subdir = questionary.text(
        "Subdirectory (optional, press Enter to skip):",
        default="",
    ).ask()

    if not subdir:
        return (url, None)
    return (url, subdir)


def prompt_agent_selection(registry: AgentRegistry) -> list[str]:
    """Prompt the user to select one or more agents.

    Uses ``questionary.select`` when available, falling back to the
    original numbered-list prompt for backward compatibility.

    Parameters
    ----------
    registry
        An ``AgentRegistry`` instance.

    Returns
    -------
    list[str]
        The selected agent ID(s), or ``["none"]`` if the user cancels.
    """
    agent_ids = registry.get_agent_ids()
    if not agent_ids:
        console.print("[yellow]No agents found in registry.[/]")
        return ["none"]

    console.print("\n[bold]No agent detected in this directory.[/]")
    console.print("[dim]Which agent(s) are you using?[/]\n")

    if sys.stdout.isatty():
        choices = [
            questionary.Choice(
                title=f"{aid.replace('-', ' ').title():20s}  "
                f"[dim]({registry.get_agent_config(aid).get('dir_name', '?') if registry.get_agent_config(aid) else '?'})[/]",
                value=aid,
            )
            for aid in agent_ids
        ]
        choices.append(
            questionary.Choice(
                title="Skip agent setup",
                value="none",
            )
        )

        result = questionary.select(
            "Select an agent (or multiple by running again):",
            choices=choices,
        ).ask()

        if result is None or result == "none":
            return ["none"]
        return [result]

    # Non-TTY fallback: original numbered-list prompt with typer.prompt
    # (compatible with CliRunner's input= parameter in tests)
    for i, aid in enumerate(agent_ids, 1):
        config = registry.get_agent_config(aid)
        label = f"{aid.replace('-', ' ').title():20s}"
        dir_name = config.get("dir_name", "?") if config else "?"
        console.print(f"  [{i}] {label}  [dim]({dir_name})[/]")
    console.print(f"  [c] cancel  [dim](skip agent setup)[/]")

    while True:
        raw = typer.prompt("\nEnter numbers separated by commas (e.g. 1,3,5)", default="")
        choice = raw.strip().lower()

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
                console.print(
                    f"[red]✗[/] Invalid input: '{p}'. Use numbers or 'c' to cancel."
                )
                valid = False
                break
        if valid:
            console.print()
            return selected


def prompt_main_menu(sklm: object) -> str | None:
    """Display the top-level multi-choice menu for ``sklm skills``.

    Parameters
    ----------
    sklm
        A ``Sklm`` facade instance.

    Returns
    -------
    str | None
        The selected menu action: ``"add"``, ``"remove"``, ``"install"``,
        ``"sync"``, ``"agents"``, or ``None`` for quit.
    """
    _ensure_tty()
    choices = [
        questionary.Choice(title="Add skills to this project", value="add"),
        questionary.Choice(
            title="Remove skills from this project", value="remove"
        ),
        questionary.Choice(
            title="Install a skill from a git repository", value="install"
        ),
        questionary.Choice(title="Sync agents", value="sync"),
        questionary.Choice(
            title="Manage agents (add/remove)", value="agents"
        ),
        questionary.Choice(title="Quit", value="quit"),
    ]

    result = questionary.select(
        "What do you want to do?",
        choices=choices,
    ).ask()

    if result is None or result == "quit":
        return None
    return result
