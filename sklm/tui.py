"""Interactive TUI for managing project skills.

ponytail: one-screen app, no router; add/remove modes swap the action button.
"""

from __future__ import annotations

import sys
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Header, Label

from sklm.api import Sklm
from sklm.models import ResourceKind, ResourceRef


class SkillTui(App):
    """Multi-select skill manager."""

    CSS = """
    Screen { align: center middle; }
    #container { width: 80; height: auto; border: solid green; padding: 1 2; }
    #title { text-align: center; }
    #list { height: auto; max-height: 20; overflow-y: scroll; }
    .row { height: auto; padding: 0 1; }
    #footer { margin-top: 1; }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self, mode: str = "manage", sklm: Optional[Sklm] = None) -> None:
        super().__init__()
        self.mode = mode  # "add" | "remove" | "manage"
        self.sklm = sklm or Sklm()
        self.result: list[ResourceRef] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="container"):
            yield Label(self._title(), id="title")
            with Vertical(id="list"):
                yield Label("Loading skills...", id="loading")
            with Horizontal(id="footer"):
                if self.mode in ("add", "manage"):
                    yield Button("Add selected", id="add", variant="success")
                if self.mode in ("remove", "manage"):
                    yield Button("Remove selected", id="remove", variant="error")
                yield Button("Cancel", id="cancel")

    def _title(self) -> str:
        if self.mode == "add":
            return "Add skills to project"
        if self.mode == "remove":
            return "Remove skills from project"
        return "Manage project skills"

    def on_mount(self) -> None:
        list_box = self.query_one("#list", Vertical)
        loading = self.query_one("#loading", Label)
        rows: list[Vertical] = []
        try:
            if self.mode in ("add", "manage"):
                for ref in self.sklm.list_available_skills():
                    rows.append(self._row(ref, False))
            if self.mode in ("remove", "manage"):
                for ref in self.sklm.list_workspace_skills():
                    rows.append(self._row(ref, True))
        except Exception as e:
            loading.update(f"[red]Error loading skills:[/] {e}")
            return
        loading.remove()
        if not rows:
            list_box.mount(Label("[dim]No skills available.[/]"))
            return
        for row in rows:
            list_box.mount(row)

    def _row(self, ref: ResourceRef, checked: bool) -> Vertical:
        cb = Checkbox(f"{ref.name}  [dim]({ref.origin})[/]", value=checked)
        cb.data = ref  # ponytail: stash ref on widget for action handler
        return Vertical(cb, classes="row")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "cancel":
            self.exit(None)
            return

        refs = [
            cb.data
            for row in self.query(".row")
            for cb in row.query(Checkbox)
            if cb.value
        ]
        if not refs:
            self.notify("No skills selected", severity="warning")
            return

        try:
            if button_id == "add":
                self.result = self.sklm.add_skills([r.name for r in refs])
            else:
                self.result = self.sklm.remove_skills([r.name for r in refs])
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")
            return
        self.exit(self.result)


def run_tui(mode: str = "manage") -> Optional[list[ResourceRef]]:
    if not sys.stdout.isatty():
        print("Interactive mode requires a TTY. Use sklm add/rm with arguments instead.", file=sys.stderr)
        return None
    sklm = Sklm()
    if not sklm.workspace.exists():
        print("No Sklm workspace found. Run 'sklm init' first.", file=sys.stderr)
        return None
    # ponytail: auto-import existing skills from all configured agents
    for agent in sklm.workspace.load_config().agents:
        if agent != "none":
            sklm.import_agent_project_skills(agent)
    app = SkillTui(mode=mode, sklm=sklm)
    return app.run()
