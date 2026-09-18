from __future__ import annotations

from dataclasses import replace

import pytest
from rich.text import Text
from textual.widgets import Input, Static, Tree

from catherd.activity import PaneActivity
from catherd.model import KittyState, OsWindow, Pane, Tab
from catherd.tui import (
    Destination,
    KittyManagerApp,
    NodeRef,
    containing_os_window_id,
    merge_os_window_destinations,
    merge_tab_destinations,
    move_destinations,
    selected_details,
    selected_title,
)

pytestmark = pytest.mark.small


def _state() -> KittyState:
    return KittyState(
        os_windows=(
            OsWindow(
                id="100",
                title="work",
                is_active=True,
                tabs=(
                    Tab(
                        id="10",
                        title="editor",
                        is_active=True,
                        layout="splits",
                        panes=(
                            Pane(
                                id="1",
                                title="nvim",
                                is_active=True,
                                cwd="/code/project",
                                foreground_cmd="nvim",
                                root_cmdline="/bin/zsh -l",
                                current_command="uv run pytest",
                                at_prompt=False,
                                title_overridden=False,
                                needs_attention=True,
                                has_activity_since_last_focus=True,
                                tab_index=1,
                                tab_count=2,
                                group_index=1,
                                group_count=2,
                                neighbors_right=("2",),
                                cols=120,
                                rows=40,
                            ),
                            Pane(
                                id="2",
                                title="tests",
                                cwd="/code/project",
                                foreground_cmd="pytest",
                                tab_index=2,
                                tab_count=2,
                                group_index=2,
                                group_count=2,
                                neighbors_left=("1",),
                            ),
                        ),
                    ),
                    Tab(id="11", title="shell", panes=(Pane(id="3", title="zsh"),)),
                ),
            ),
            OsWindow(
                id="200",
                title="notes",
                tabs=(Tab(id="20", title="notes", panes=(Pane(id="4", title="nvim"),)),),
            ),
        )
    )


def _activity(_pane_id: str) -> PaneActivity:
    return PaneActivity(session_id="session-1", last_command="pytest -q")


class FakeBackend:
    def __init__(self, state: KittyState) -> None:
        self.state = state
        self.calls: list[tuple[object, ...]] = []

    def snapshot(self) -> KittyState:
        self.calls.append(("snapshot",))
        return self.state

    def focus_pane(self, pane_id: str) -> None:
        self.calls.append(("focus_pane", pane_id))

    def focus_tab(self, tab_id: str) -> None:
        self.calls.append(("focus_tab", tab_id))

    def focus_os_window(self, os_window_id: str) -> None:
        self.calls.append(("focus_os_window", os_window_id))

    def rename_pane(self, pane_id: str, title: str) -> None:
        self.calls.append(("rename_pane", pane_id, title))

    def rename_tab(self, tab_id: str, title: str) -> None:
        self.calls.append(("rename_tab", tab_id, title))

    def rename_os_window(self, os_window_id: str, title: str) -> None:
        self.calls.append(("rename_os_window", os_window_id, title))

    def move_pane(self, pane_id: str, target_tab_id: str) -> None:
        self.calls.append(("move_pane", pane_id, target_tab_id))
        location = self.state.find_pane(pane_id)
        if location is None:
            return
        moved = location.pane
        os_windows: list[OsWindow] = []
        for os_window in self.state.os_windows:
            tabs: list[Tab] = []
            for tab in os_window.tabs:
                panes = tuple(pane for pane in tab.panes if pane.id != pane_id)
                if tab.id == target_tab_id:
                    panes += (moved,)
                tabs.append(replace(tab, panes=panes))
            os_windows.append(replace(os_window, tabs=tuple(tabs)))
        self.state = KittyState(tuple(os_windows))

    def detach_pane_to_new_tab(self, pane_id: str) -> None:
        self.calls.append(("detach_pane_to_new_tab", pane_id))

    def detach_pane_to_new_os_window(self, pane_id: str) -> None:
        self.calls.append(("detach_pane_to_new_os_window", pane_id))

    def move_tab(self, tab_id: str, target_os_window_id: str) -> None:
        self.calls.append(("move_tab", tab_id, target_os_window_id))

    def detach_tab_to_new_os_window(self, tab_id: str) -> None:
        self.calls.append(("detach_tab_to_new_os_window", tab_id))

    def reorder_pane(self, pane_id: str, direction: str) -> None:
        self.calls.append(("reorder_pane", pane_id, direction))

    def reorder_tab(self, tab_id: str, direction: str) -> None:
        self.calls.append(("reorder_tab", tab_id, direction))

    def merge_tabs(self, source_tab_id: str, target_tab_id: str) -> None:
        self.calls.append(("merge_tabs", source_tab_id, target_tab_id))

    def merge_os_windows(self, source_os_window_id: str, target_os_window_id: str) -> None:
        self.calls.append(("merge_os_windows", source_os_window_id, target_os_window_id))


def _find_node(tree: Tree[NodeRef], ref: NodeRef):
    for os_node in tree.root.children:
        if os_node.data == ref:
            return os_node
        for tab_node in os_node.children:
            if tab_node.data == ref:
                return tab_node
            for pane_node in tab_node.children:
                if pane_node.data == ref:
                    return pane_node
    msg = f"missing node: {ref}"
    raise AssertionError(msg)


def test_move_destinations_for_pane() -> None:
    destinations = move_destinations(_state(), NodeRef("pane", "1"))

    assert Destination("tab", "11", "OS 100 — work / shell [11]") in destinations
    assert Destination("tab", "20", "OS 200 — notes / notes [20]") in destinations
    assert Destination("tab", "10", "OS 100 — work / editor [10]") not in destinations
    assert destinations[-2:] == (
        Destination("new_tab", None, "New tab"),
        Destination("new_os_window", None, "New OS window"),
    )


def test_move_destinations_for_tab() -> None:
    destinations = move_destinations(_state(), NodeRef("tab", "10"))

    assert destinations == (
        Destination("os_window", "200", "OS 200 — notes"),
        Destination("new_os_window", None, "New OS window"),
    )


def test_merge_os_window_destinations_exclude_source() -> None:
    assert merge_os_window_destinations(_state(), "100") == (
        Destination("os_window", "200", "OS 200 — notes"),
    )


def test_merge_tab_destinations_exclude_source() -> None:
    destinations = merge_tab_destinations(_state(), "10")

    assert Destination("tab", "10", "irrelevant") not in destinations
    assert Destination("tab", "11", "OS 100 — work / shell [11]") in destinations
    assert Destination("tab", "20", "OS 200 — notes / notes [20]") in destinations


def test_containing_os_window_id_resolves_all_node_kinds() -> None:
    state = _state()

    assert containing_os_window_id(state, NodeRef("os_window", "100")) == "100"
    assert containing_os_window_id(state, NodeRef("tab", "10")) == "100"
    assert containing_os_window_id(state, NodeRef("pane", "1")) == "100"


def test_selected_title_uses_hierarchy() -> None:
    state = _state()

    assert selected_title(state, NodeRef("pane", "1")) == "nvim"
    assert selected_title(state, NodeRef("tab", "10")) == "editor"
    assert selected_title(state, NodeRef("os_window", "100")) == "work"
    assert selected_title(state, NodeRef("pane", "missing")) == ""


def test_selected_details_for_os_window() -> None:
    details = selected_details(_state(), NodeRef("os_window", "100"))

    assert "OS window" in details.plain
    assert "Tabs: 2" in details.plain
    assert "Panes: 3" in details.plain


def test_selected_details_for_tab() -> None:
    details = selected_details(_state(), NodeRef("tab", "10"))

    assert "Tab" in details.plain
    assert "Layout: splits" in details.plain
    assert "Panes: 2" in details.plain


def test_selected_details_for_pane_with_activity() -> None:
    details = selected_details(
        _state(),
        NodeRef("pane", "1"),
        activity=_activity("1"),
    )

    assert "Pane" in details.plain
    assert "CWD: /code/project" in details.plain
    assert "Current command: uv run pytest" in details.plain
    assert "Foreground process: nvim" in details.plain
    assert "Root process: /bin/zsh -l" in details.plain
    assert "Position in tab: 1 of 2" in details.plain
    assert "Neighbors: R:2" in details.plain
    assert "Size: 120×40" in details.plain  # ruff: ignore[ambiguous-unicode-character-string]
    assert "Needs attention: yes" in details.plain
    assert "Atuin session: session-1" in details.plain
    assert "Last completed command: pytest -q" in details.plain


def test_selected_details_for_pane_loading() -> None:
    details = selected_details(
        _state(),
        NodeRef("pane", "1"),
        activity_loading=True,
    )

    assert "Atuin session: loading…" in details.plain
    assert "Last completed command: loading…" in details.plain


async def test_details_panel_loads_activity_for_highlighted_pane() -> None:
    calls: list[str] = []

    def activity_provider(pane_id: str) -> PaneActivity:
        calls.append(pane_id)
        return PaneActivity(session_id="session-live", last_command="uv run pytest")

    backend = FakeBackend(_state())
    app = KittyManagerApp(
        backend,
        poll_interval=None,
        activity_provider=activity_provider,
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        await app.workers.wait_for_complete()
        details = app.query_one("#details", Static)
        assert isinstance(details.content, Text)
        assert "Atuin session: session-live" in details.content.plain
        assert "Last completed command: uv run pytest" in details.content.plain

    assert "1" in calls


async def test_tui_renders_hierarchy_and_selects_active_pane() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        assert len(tree.root.children) == 2
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("pane", "1")
        assert _find_node(tree, NodeRef("tab", "10")).is_expanded


async def test_refresh_preserves_selection_and_reveals_it() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tab_ref = NodeRef("tab", "11")
        tree.move_cursor(_find_node(tree, tab_ref))
        await pilot.pause()
        other_os_ref = NodeRef("os_window", "200")
        _find_node(tree, other_os_ref).collapse()

        os_windows = list(backend.state.os_windows)
        os_windows[1] = replace(os_windows[1], title="renamed")
        backend.state = KittyState(tuple(os_windows))
        await app.refresh_state()
        await pilot.pause()

        assert tree.cursor_node is not None
        assert tree.cursor_node.data == tab_ref
        assert _find_node(tree, other_os_ref).is_collapsed


async def test_tree_selection_does_not_focus_kitty_until_explicit_action() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        target = _find_node(tree, NodeRef("pane", "2"))
        tree.select_node(target)
        await pilot.pause()

        assert ("focus_pane", "2") not in backend.calls

        await pilot.press("f")
        await app.workers.wait_for_complete()

    assert ("focus_pane", "2") in backend.calls


async def test_enter_focuses_selected_pane() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("focus_pane", "2") in backend.calls


async def test_reorder_routes_to_backend_and_preserves_selection() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        pane_ref = NodeRef("pane", "2")
        tree.move_cursor(_find_node(tree, pane_ref))
        await pilot.press("J")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == pane_ref

    assert ("reorder_pane", "2", "forward") in backend.calls


async def test_tab_reorder_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("tab", "10")))
        await pilot.press("J")
        await app.workers.wait_for_complete()

    assert ("reorder_tab", "10", "forward") in backend.calls


async def test_uppercase_k_routes_backward_reorder() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("K")
        await app.workers.wait_for_complete()

    assert ("reorder_pane", "2", "backward") in backend.calls


async def test_reorder_restores_manager_focus(monkeypatch) -> None:
    monkeypatch.setenv("KITTY_WINDOW_ID", "99")
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("J")
        await app.workers.wait_for_complete()

    reorder_index = backend.calls.index(("reorder_pane", "2", "forward"))
    restore_index = backend.calls.index(("focus_pane", "99"))
    assert restore_index > reorder_index


async def test_rename_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("r")
        await pilot.pause()
        rename_input = app.screen.query_one("#rename-input", Input)
        rename_input.value = "test runner"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        renamed = _find_node(tree, NodeRef("pane", "2"))
        assert isinstance(renamed.label, Text)
        assert "test runner" in renamed.label.plain

    assert ("rename_pane", "2", "test runner") in backend.calls


async def test_os_window_rename_updates_tree_label() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        os_ref = NodeRef("os_window", "100")
        tree.move_cursor(_find_node(tree, os_ref))
        await pilot.press("r")
        await pilot.pause()
        rename_input = app.screen.query_one("#rename-input", Input)
        rename_input.value = "research"
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        renamed = _find_node(tree, os_ref)
        assert isinstance(renamed.label, Text)
        assert "research" in renamed.label.plain

    assert ("rename_os_window", "100", "research") in backend.calls


async def test_move_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "1")))
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        pane_ref = NodeRef("pane", "1")
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == pane_ref
        moved_node = _find_node(tree, pane_ref)
        assert moved_node.parent is not None
        assert moved_node.parent.data == NodeRef("tab", "11")

    assert ("move_pane", "1", "11") in backend.calls


async def test_merge_on_pane_is_rejected() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "1")))
        await pilot.press("M")
        await pilot.pause()

    assert not any(call[0] in {"merge_tabs", "merge_os_windows"} for call in backend.calls)


async def test_merge_tab_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("tab", "10")))
        await pilot.press("M")
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("merge_tabs", "10", "11") in backend.calls


async def test_merge_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("os_window", "100")))
        await pilot.press("M")
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("merge_os_windows", "100", "200") in backend.calls
