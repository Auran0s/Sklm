"""Interactive TUI for managing project skills.

Unified SkillManagerApp — no mode branching; adaptive action button
reacts to the user's toggle choices ("Add selected"/"Remove selected"/"Apply changes").
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widgets import Button, Checkbox, Input, Label, LoadingIndicator, Static

from sklm.api import Sklm
from sklm.models import ResourceRef


# ─── Custom Widgets ───────────────────────────────────────────────────────────


class TitleBar(Static):
    """macOS-style title bar with traffic lights and centered title."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="title-bar"):
            yield Static(
                "[#ff5f57]●[/] [#febc2e]●[/] [#28c840]●[/]",
                id="traffic-lights",
            )
            yield Static(
                "Sklm - Skills manager for AI agents",
                id="title-text",
            )


class ShortcutBar(Static):
    """Full-width black shortcut bar with keyboard binding labels."""

    def compose(self) -> ComposeResult:
        yield Static(
            "  ^a Select All   ^d Deselect All   ↑↓ Navigate   Space Toggle   q Quit                         ^p Palette",
            id="shortcuts",
        )


class SkillRow(Static):
    """A single skill row: checkbox + name, with focus styling."""

    def __init__(
        self,
        ref: ResourceRef,
        linked: bool,
    ) -> None:
        super().__init__()
        self.ref = ref
        self.linked = linked
        self.selected = False

    def compose(self) -> ComposeResult:
        cb = Checkbox(
            Text.from_markup(f"[#d4d4d4]{self.ref.name}[/]"),
            value=self.linked,
            classes="skill-checkbox",
        )
        cb.data = self.ref
        yield cb

    def on_mount(self) -> None:
        """Sync initial selected state from linked status."""
        self.selected = self.linked

    @property
    def checkbox(self) -> Checkbox:
        return self.query_one(Checkbox)

    def on_click(self) -> None:
        """Toggle checkbox when clicking the row (accessibility)."""
        self.checkbox.toggle()
        self.selected = self.checkbox.value


# ─── Command Palette Provider ────────────────────────────────────────────────


class SklmCommands(Provider):
    """Command palette actions for Sklm."""

    def __init__(self, app: App) -> None:
        super().__init__(app)
        self.sklm_app: SkillManagerApp = app  # type: ignore[assignment]

    async def search(self, query: str) -> Hits:
        """Return matching commands."""
        matcher = self.matcher(query)

        yield Hit(
            100,
            matcher.highlight("Sync Agents"),
            "Sync skills to agent config directories",
            self.sync_agents,
        )

        yield Hit(
            90,
            matcher.highlight("Refresh Skill List"),
            "Reload skills from store and registries",
            self.refresh_skills,
        )

        yield Hit(
            80,
            matcher.highlight("Install from Git..."),
            "Install a skill from a GitHub repo",
            self.install_from_git,
        )

    async def sync_agents(self) -> None:
        """Sync skills to agent config directories."""
        try:
            self.sklm_app.sklm.agent_sync()
            self.app.notify("Agents synced successfully", severity="information")
        except Exception as e:
            self.app.notify(f"Sync failed: {e}", severity="error")

    async def refresh_skills(self) -> None:
        """Reload skill data from store and registries."""
        self.sklm_app._reload_skills()

    async def install_from_git(self) -> None:
        """Stub: install from git is deferred."""
        self.app.notify("Coming soon — Install from Git", severity="information")


# ─── Main App ────────────────────────────────────────────────────────────────


class SkillManagerApp(App):
    """Unified skill manager TUI."""

    # ── CSS Theme ────────────────────────────────────────────────────────────

    CSS = """
    Screen {
        background: #0d0d0d;
    }

    /* ── Layout ── */

    #title-bar {
        height: 1;
        align: center middle;
        background: #0d0d0d;
    }
    #traffic-lights {
        width: auto;
        margin-left: 1;
    }
    #title-text {
        width: 1fr;
        text-align: center;
        color: #d4d4d4;
    }

    #body {
        height: 1fr;
    }

    #left-panel {
        width: 1fr;
        min-width: 40;
        border-right: solid #1e3a2a;
        padding: 0 1;
    }

    #preview-panel {
        width: 35;
        min-width: 25;
        background: #090909;
        padding: 0 1;
    }

    #footer-bar {
        height: auto;
        margin-top: 0;
    }

    /* ── Search ── */

    #search-input {
        margin-bottom: 1;
        background: #0d0d0d;
        border: solid #1e3a2a;
        color: #d4d4d4;
    }
    #search-input:focus {
        border: solid #3fb950;
    }

    /* ── Skill List ── */

    #skill-list {
        overflow-y: scroll;
        height: 1fr;
    }

    .skill-row {
        height: auto;
        padding: 0 1;
        border: none;
        background: transparent;
    }
    .skill-row:focus-within {
        border: solid #3fb950;
        background: rgba(63, 185, 80, 0.08);
    }

    .skill-checkbox {
        color: #d4d4d4;
    }
    .skill-checkbox > .toggle--button {
        color: #3fb950;
    }

    /* ── Preview ── */

    .preview-header {
        color: #3fb950;
        text-style: bold;
        margin-bottom: 1;
    }
    #preview-name {
        color: #d4d4d4;
        text-style: bold;
        margin-bottom: 1;
    }
    #preview-description {
        color: #808080;
    }
    #preview-placeholder {
        color: #808080;
        text-align: center;
        margin-top: 2;
    }

    /* ── Action Buttons ── */

    #action-bar {
        height: auto;
        padding: 0 1;
        margin-top: 1;
    }
    #stats-label {
        color: #808080;
        width: auto;
    }
    #action-btn {
        width: auto;
        margin-left: 1;
    }
    #cancel-btn {
        width: auto;
        margin-left: 1;
    }

    /* ── Shortcut Bar ── */

    #shortcuts {
        background: #000000;
        padding: 0 1;
        color: #808080;
    }

    /* ── Loading / Empty / Error ── */

    #loading {
        color: #3fb950;
        text-align: center;
        margin-top: 2;
    }
    #empty {
        color: #808080;
        text-align: center;
        margin-top: 2;
    }
    #error {
        color: #ff5f57;
        text-align: center;
        margin-top: 2;
    }

    /* ── Responsive (narrow terminal) ── */

    .narrow #preview-panel {
        width: 1fr;
        height: auto;
        max-height: 40%;
    }
    .narrow #left-panel {
        width: 1fr;
        border-right: none;
    }
    .narrow #body {
        layout: vertical;
    }
    """

    # ── Bindings ─────────────────────────────────────────────────────────────

    BINDINGS = [
        Binding("ctrl+a", "select_all", "Select All"),
        Binding("ctrl+d", "deselect_all", "Deselect All"),
        Binding("space", "toggle_focused", "Toggle"),
        Binding("enter", "confirm", "Confirm"),
        Binding("q", "quit", "Quit"),
        Binding("escape", "quit", "Quit"),
        Binding("/", "focus_search", "Search"),
    ]

    # ── Reactive State ───────────────────────────────────────────────────────

    selected_count = reactive(0)
    has_additions = reactive(False)
    has_removals = reactive(False)

    def __init__(self, mode: str = "manage", sklm: Optional[Sklm] = None) -> None:
        super().__init__()
        self.mode = mode  # "add" | "remove" | "manage" — used as initial hint
        self.sklm = sklm or Sklm()
        self.result: list[ResourceRef] = []
        self._all_rows: list[tuple[ResourceRef, bool]] = []  # (ref, linked)
        self._loaded = False

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield TitleBar()
        with Horizontal(id="body"):
            with Vertical(id="left-panel"):
                yield Input(
                    placeholder="⌕ Search skills...",
                    id="search-input",
                )
                yield LoadingIndicator(id="loading")
                yield Label("", id="error")
                yield Vertical(id="skill-list")
            with Vertical(id="preview-panel"):
                yield Label("Preview", classes="preview-header")
                yield Label("Select a skill to preview", id="preview-placeholder")
                yield Label("", id="preview-name")
                yield Label("", id="preview-description")
        with Horizontal(id="footer-bar"):
            with Horizontal(id="action-bar"):
                yield Label("0 selected", id="stats-label")
                yield Button("Apply", id="action-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")
        yield ShortcutBar()

    # ── Mount & Resize ───────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self.run_worker(self._load_skills, exclusive=True, thread=True)
        try:
            self.register_provider(SklmCommands)
        except Exception:
            pass
        self._apply_responsive()

    def on_resize(self) -> None:
        """Handle terminal resize for responsive layout."""
        self._apply_responsive()

    def _apply_responsive(self) -> None:
        """Toggle narrow class based on terminal width."""
        try:
            if self.size.width < 80:
                self.screen.add_class("narrow")
            else:
                self.screen.remove_class("narrow")
        except Exception:
            pass

    # ── Data Loading ─────────────────────────────────────────────────────────

    def _load_skills(self) -> None:
        """Load skills from Sklm API in a background thread."""
        try:
            # Load all available skills
            available = list(self.sklm.list_available_skills())
            for ref in available:
                if ref not in [r for r, _ in self._all_rows]:
                    self._all_rows.append((ref, False))

            # Load workspace skills (mark as linked)
            workspace = list(self.sklm.list_workspace_skills())
            workspace_names = {r.name for r in workspace}
            for ref in workspace:
                self._all_rows.append((ref, True))

            # Merge: if a skill is both available and workspace, mark as linked
            seen: dict[str, bool] = {}
            merged: list[tuple[ResourceRef, bool]] = []
            for ref, linked in self._all_rows:
                if ref.name not in seen:
                    seen[ref.name] = linked or ref.name in workspace_names
                    merged.append((ref, seen[ref.name]))
                elif linked:
                    seen[ref.name] = True
                    # Update existing entry in merged
                    for i, (r, _) in enumerate(merged):
                        if r.name == ref.name:
                            merged[i] = (r, True)
                            break

            self._all_rows = merged
        except Exception as e:
            self.call_from_thread(self._show_error, str(e))
            return
        self.call_from_thread(self._render_skills)

    def _show_error(self, error_msg: str) -> None:
        """Display an error message."""
        if not self._loaded:
            try:
                self.query_one("#loading", LoadingIndicator).remove()
            except NoMatches:
                pass
            try:
                error_label = self.query_one("#error", Label)
                error_label.update(f"[red]Error loading skills:[/] {error_msg}")
                error_label.display = True
            except NoMatches:
                pass
            self._loaded = True

    def _render_skills(self, filter_text: str = "") -> None:
        """Render skill rows, optionally filtered."""
        skill_list = self.query_one("#skill-list", Vertical)

        if not self._loaded:
            try:
                self.query_one("#loading", LoadingIndicator).remove()
            except NoMatches:
                pass
            try:
                self.query_one("#error", Label).update("")
            except NoMatches:
                pass
            self._loaded = True

        # Clear existing rows
        skill_list.remove_children()

        # Filter
        rows_to_show = [
            (ref, linked)
            for ref, linked in self._all_rows
            if not filter_text or filter_text.lower() in ref.name.lower()
        ]

        if not rows_to_show:
            if filter_text:
                skill_list.mount(
                    Label("[dim]No skills match[/]", id="empty")
                )
            else:
                skill_list.mount(
                    Label("[dim]No skills available.[/]", id="empty")
                )
            self._update_stats()
            return

        for ref, linked in rows_to_show:
            row = SkillRow(ref, linked)
            row.classes = "skill-row"
            skill_list.mount(row)

        self._update_stats()

    # ── Search / Filter ──────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the skill list as the user types."""
        if event.input.id == "search-input":
            self._render_skills(event.value)

    # ── Preview ──────────────────────────────────────────────────────────────

    def _update_preview(self, ref: Optional[ResourceRef]) -> None:
        """Update the preview panel with the given skill's info."""
        placeholder = self.query_one("#preview-placeholder", Label)
        name_label = self.query_one("#preview-name", Label)
        desc_label = self.query_one("#preview-description", Label)

        if ref is None or ref.path is None:
            placeholder.display = True
            name_label.update("")
            desc_label.update("")
            return

        skill_md = ref.path / "SKILL.md"
        if not skill_md.exists():
            placeholder.display = True
            name_label.update("")
            desc_label.update("")
            return

        placeholder.display = False
        name_label.update(f"[#d4d4d4]{ref.name}[/]")

        # Extract first non-empty paragraph from SKILL.md
        try:
            content = skill_md.read_text(encoding="utf-8")
            description = self._extract_first_paragraph(content)
            desc_label.update(f"[#808080]{description}[/]")
        except Exception:
            desc_label.update("")

    @staticmethod
    def _extract_first_paragraph(markdown_text: str) -> str:
        """Extract the first non-empty, non-heading paragraph from markdown."""
        for line in markdown_text.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped[:200]  # Cap at 200 chars
        return ""

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox toggle to update stats and preview."""
        ref: Optional[ResourceRef] = getattr(event.checkbox, "data", None)
        self._update_preview(ref)
        self._recompute_state()

    def on_skill_row_click(self, event: SkillRow.Changed) -> None:
        """Handle SkillRow click events."""
        self._recompute_state()

    # ── Reactive State ───────────────────────────────────────────────────────

    def _recompute_state(self) -> None:
        """Recalculate has_additions, has_removals, and selected_count."""
        additions = 0
        removals = 0
        selected = 0

        for row in self.query(".skill-row"):
            if not isinstance(row, SkillRow):
                continue
            cb = row.checkbox
            current = cb.value
            if current:
                selected += 1
            if current and not row.linked:
                additions += 1
            elif not current and row.linked:
                removals += 1

        self.selected_count = selected
        self.has_additions = additions > 0
        self.has_removals = removals > 0

    def watch_selected_count(self, count: int) -> None:
        """Update the stats label and action button."""
        try:
            stats_label = self.query_one("#stats-label", Label)
            stats_label.update(f"{count} selected")
        except NoMatches:
            pass
        self._update_action_button()

    def watch_has_additions(self, _additions: bool) -> None:
        self._update_action_button()

    def watch_has_removals(self, _removals: bool) -> None:
        self._update_action_button()

    def _update_action_button(self) -> None:
        """Update the action button label and variant based on state."""
        try:
            btn = self.query_one("#action-btn", Button)
        except NoMatches:
            return

        count = self.selected_count

        if count == 0:
            btn.disabled = True
            btn.label = "Apply"
            return

        btn.disabled = False

        if self.has_additions and self.has_removals:
            btn.label = f"Apply changes ({count})"
            btn.variant = "primary"
        elif self.has_additions:
            btn.label = f"Add selected ({count})"
            btn.variant = "success"
        elif self.has_removals:
            btn.label = f"Remove selected ({count})"
            btn.variant = "error"

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_select_all(self) -> None:
        """Check all visible rows."""
        for row in self.query(".skill-row"):
            if isinstance(row, SkillRow):
                row.checkbox.value = True
        self._recompute_state()

    def action_deselect_all(self) -> None:
        """Uncheck all visible rows."""
        for row in self.query(".skill-row"):
            if isinstance(row, SkillRow):
                row.checkbox.value = False
        self._recompute_state()

    def action_toggle_focused(self) -> None:
        """Toggle the currently focused checkbox."""
        focused = self.focused
        if focused and hasattr(focused, "toggle"):
            focused.toggle()
            self._recompute_state()

    def action_confirm(self) -> None:
        """Press the action button."""
        try:
            self.query_one("#action-btn", Button).press()
        except NoMatches:
            pass

    def action_focus_search(self) -> None:
        """Focus the search input."""
        try:
            self.query_one("#search-input", Input).focus()
        except NoMatches:
            pass

    # ── Button Handlers ───────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "cancel-btn":
            self.exit(None)
            return

        if button_id == "action-btn":
            self._apply_changes()

    def _apply_changes(self) -> None:
        """Calculate diffs and apply add/remove operations."""
        additions: list[str] = []
        removals: list[str] = []

        for row in self.query(".skill-row"):
            if not isinstance(row, SkillRow):
                continue
            cb = row.checkbox
            current = cb.value
            if current and not row.linked:
                additions.append(row.ref.name)
            elif not current and row.linked:
                removals.append(row.ref.name)

        try:
            if additions:
                self.sklm.add_skills(additions)
            if removals:
                self.sklm.remove_skills(removals)
            # Agent sync once
            self.sklm.agent_sync()
        except Exception as e:
            self.notify(f"Failed: {e}", severity="error")
            return

        # Build result list
        result_refs: list[ResourceRef] = []
        for row in self.query(".skill-row"):
            if isinstance(row, SkillRow) and row.checkbox.value:
                result_refs.append(row.ref)

        self.notify(
            f"Applied: {len(additions)} added, {len(removals)} removed",
            severity="information",
        )
        self.exit(result_refs)

    # ── Reload ───────────────────────────────────────────────────────────────

    def _reload_skills(self) -> None:
        """Reload skill data from store and registries."""
        self._all_rows = []
        self._loaded = False
        try:
            self.query_one("#loading", LoadingIndicator).display = True
        except NoMatches:
            pass
        self.run_worker(self._load_skills, exclusive=True, thread=True)


# ─── Entrypoint ───────────────────────────────────────────────────────────────


def run_tui(mode: str = "manage") -> Optional[list[ResourceRef]]:
    if not sys.stdout.isatty():
        print(
            "Interactive mode requires a TTY. Use sklm add/rm with arguments instead.",
            file=sys.stderr,
        )
        return None
    sklm = Sklm()
    if not sklm.workspace.exists():
        print("No Sklm workspace found. Run 'sklm init' first.", file=sys.stderr)
        return None
    # Auto-import existing skills from all configured agents
    for agent in sklm.workspace.load_config().agents:
        if agent != "none":
            sklm.import_agent_project_skills(agent)
    app = SkillManagerApp(mode=mode, sklm=sklm)
    return app.run()
