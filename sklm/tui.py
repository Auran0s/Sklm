"""Interactive TUI for managing project skills.

ponytail: one-screen app, no router; add/remove modes swap the action button.
"""

from __future__ import annotations

import sys
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Markdown

from sklm.api import Sklm
from sklm.models import ResourceRef


class SkillTui(App):
    """Multi-select skill manager."""

    CSS = """
    Screen { align: center middle; }
    #container { width: 90%; height: 90%; border: solid $primary; padding: 1 2; }
    #title { text-align: center; }
    .skill-row { height: auto; padding: 0 1; }
    .skill-row:hover { background: $surface; }
    #body { height: 1fr; }
    #list-panel { width: 40%; overflow-y: auto; border-right: solid $primary; }
    #preview-panel { width: 60%; padding: 0 1; overflow-y: auto; }
    #preview-placeholder { color: $text-muted; text-align: center; margin-top: 2; }
    .-hidden { display: none; }
    #filter { margin-bottom: 1; }
    #loading { color: $text-muted; text-align: center; }
    #stats { color: $text-muted; }
    .section-header { color: $text-muted; text-style: bold; padding: 0 1; }
    #footer { margin-top: 1; }
    """

    BINDINGS = [
        ("ctrl+a", "select_all", "Select All"),
        ("ctrl+d", "deselect_all", "Deselect All"),
        ("enter", "confirm", "Confirm"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, mode: str = "manage", sklm: Optional[Sklm] = None) -> None:
        super().__init__()
        self.mode = mode  # "add" | "remove" | "manage"
        self.sklm = sklm or Sklm()
        self.result: list[ResourceRef] = []
        self._all_rows: list[tuple[ResourceRef, bool]] = []
        self._rendered = False
        self._visible_count = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="container"):
            yield Label(self._title(), id="title")
            yield Input(placeholder="Type to filter skills...", id="filter")
            with Horizontal(id="body"):
                with Vertical(id="list-panel"):
                    yield Label("Loading skills...", id="loading")
                with Vertical(id="preview-panel"):
                    yield Label("Select a skill to preview", id="preview-placeholder")
                    yield Markdown(id="preview")
            with Horizontal(id="footer"):
                yield Label("0 selected", id="stats")
                if self.mode in ("add", "manage"):
                    yield Button("Add selected", id="add", variant="success")
                if self.mode in ("remove", "manage"):
                    yield Button("Remove selected", id="remove", variant="error")
                yield Button("Cancel", id="cancel")
        yield Footer()

    def _title(self) -> str:
        if self.mode == "add":
            return "[green]Add Skills to Project[/]"
        if self.mode == "remove":
            return "[red]Remove Skills from Project[/]"
        return "[blue]Manage Project Skills[/]"

    def on_mount(self) -> None:
        self.run_worker(self._load_skills, exclusive=True, thread=True)

    def _load_skills(self) -> None:
        """Load skills from Sklm API in a background thread."""
        try:
            if self.mode in ("add", "manage"):
                for ref in self.sklm.list_available_skills():
                    self._all_rows.append((ref, False))
            if self.mode in ("remove", "manage"):
                for ref in self.sklm.list_workspace_skills():
                    self._all_rows.append((ref, True))
        except Exception as e:
            self.call_from_thread(self._render_error, str(e))
            return
        self.call_from_thread(self._render_rows)

    def _render_error(self, error_msg: str) -> None:
        """Display a loading error on the UI thread."""
        if not self._rendered:
            self.query_one("#loading", Label).update(
                f"[red]Error loading skills:[/] {error_msg}"
            )
            self._rendered = True

    def _render_rows(self, filter_text: str = "") -> None:
        """Render skill rows, filtering by filter_text."""
        list_box = self.query_one("#list-panel", Vertical)
        if not self._rendered:
            self.query_one("#loading", Label).remove()
            self._rendered = True

        # Remove empty label, section headers, and existing skill rows
        list_box.query("#empty").remove()
        for row in list_box.query(".section-header"):
            row.remove()
        for row in list_box.query(".skill-row"):
            row.remove()

        rows_to_show = [
            (ref, checked)
            for ref, checked in self._all_rows
            if not filter_text or filter_text.lower() in ref.name.lower()
        ]

        # Sort by origin, then by name within each origin
        rows_to_show.sort(key=lambda x: (x[0].origin, x[0].name))

        self._visible_count = len(rows_to_show)

        if not rows_to_show:
            list_box.mount(Label("[dim]No skills available.[/]", id="empty"))
            return

        # Group by origin with section headers
        current_origin = None
        for ref, checked in rows_to_show:
            if ref.origin != current_origin:
                current_origin = ref.origin
                list_box.mount(
                    Label(f"── {current_origin} ──", classes="section-header")
                )
            list_box.mount(self._row(ref, checked))

        self._update_stats()

    @staticmethod
    def _origin_badge(origin: str) -> str:
        """Return a Rich-markup badge for the given origin."""
        if origin == "global":
            return f"[green]{origin}[/]"
        if origin == "local":
            return f"[yellow]{origin}[/]"
        if origin.startswith("registry:"):
            return f"[cyan]{origin}[/]"
        return f"[dim]{origin}[/]"

    def _row(self, ref: ResourceRef, checked: bool) -> Vertical:
        cb = Checkbox(f"{ref.name}  {self._origin_badge(ref.origin)}", value=checked)
        cb.data = ref  # ponytail: stash ref on widget for action handler
        return Vertical(cb, classes="skill-row")

    def _update_stats(self) -> None:
        """Update the selected count label."""
        count = sum(
            1
            for row in self.query(".skill-row")
            for cb in row.query(Checkbox)
            if cb.value
        )
        self.query_one("#stats", Label).update(
            f"{count} / {self._visible_count} selected"
        )

    def _update_preview(self, ref: ResourceRef | None) -> None:
        """Update the preview panel with the given skill's SKILL.md content."""
        placeholder = self.query_one("#preview-placeholder", Label)
        preview = self.query_one("#preview", Markdown)
        if ref is None or ref.path is None:
            placeholder.remove_class("-hidden")
            preview.update("")
            return

        skill_md = ref.path / "SKILL.md"
        if not skill_md.exists():
            placeholder.remove_class("-hidden")
            preview.update("")
            return

        try:
            content = skill_md.read_text(encoding="utf-8")
            placeholder.add_class("-hidden")
            preview.update(content)
        except Exception:
            placeholder.remove_class("-hidden")
            preview.update("")
            self.notify("Failed to read SKILL.md", severity="error")

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox toggle to update stats and preview."""
        self._update_stats()
        ref: ResourceRef | None = event.checkbox.data
        self._update_preview(ref)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter skill list as user types."""
        self._render_rows(event.value)

    def action_select_all(self) -> None:
        """Select all visible skills."""
        for row in self.query(".skill-row"):
            for cb in row.query(Checkbox):
                cb.value = True
        self._update_stats()

    def action_deselect_all(self) -> None:
        """Deselect all visible skills."""
        for row in self.query(".skill-row"):
            for cb in row.query(Checkbox):
                cb.value = False
        self._update_stats()

    def action_confirm(self) -> None:
        """Press the primary action button."""
        if self.mode in ("add", "manage"):
            self.query_one("#add", Button).press()
        elif self.mode == "remove":
            self.query_one("#remove", Button).press()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "cancel":
            self.exit(None)
            return

        refs = [
            cb.data
            for row in self.query(".skill-row")
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
