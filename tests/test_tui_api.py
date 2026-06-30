"""Self-check for TUI API helpers."""

from __future__ import annotations

from sklm.api import Sklm


def test_tui_helpers():
    s = Sklm()
    available = s.list_available_skills()
    assert isinstance(available, list)
    # global store skills are offered
    assert all(r.kind.value == "skill" for r in available)

    workspace = s.list_workspace_skills()
    assert isinstance(workspace, list)
    # no duplicates between available list
    names = [r.name for r in available]
    assert len(names) == len(set(names))

    # import from a non-existent agent dir is a no-op
    imported = s.import_agent_project_skills("claude")
    assert imported == []

    print("tui helpers ok")


if __name__ == "__main__":
    test_tui_helpers()
