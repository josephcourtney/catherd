from __future__ import annotations

from dataclasses import replace

import pytest
from textual.widgets import Input, Tree

from catherd.model import KittyState, OsWindow, Pane, Tab
from catherd.tui import (
    Destination,
    KittyManagerApp,
    NodeRef,
    merge_destinations,
    move_destinations,
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
                            ),
                            Pane(id="2", title="tests", cwd="/code/project", foreground_cmd="pytest"),
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
    raise AssertionError(f"missing node: {ref}")


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


def test_merge_destinations_exclude_source() -> None:
    assert merge_destinations(_state(), "100") == (
        Destination("os_window", "200", "OS 200 — notes"),
    )


def test_selected_title_uses_hierarchy() -> None:
    state = _state()

    assert selected_title(state, NodeRef("pane", "1")) == "nvim"
    assert selected_title(state, NodeRef("tab", "10")) == "editor"
    assert selected_title(state, NodeRef("os_window", "100")) == "work"
    assert selected_title(state, NodeRef("pane", "missing")) == ""


async def test_tui_renders_hierarchy_and_selects_active_pane() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test():
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        assert len(tree.root.children) == 2
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("pane", "1")
        assert _find_node(tree, NodeRef("tab", "10")).is_expanded


async def test_refresh_preserves_selection_and_reveals_it() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test():
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tab_ref = NodeRef("tab", "11")
        tree.move_cursor(_find_node(tree, tab_ref))
        _find_node(tree, NodeRef("os_window", "100")).collapse()

        os_windows = list(backend.state.os_windows)
        os_windows[1] = replace(os_windows[1], title="renamed")
        backend.state = KittyState(tuple(os_windows))
        await app.refresh_state()

        assert tree.cursor_node is not None
        assert tree.cursor_node.data == tab_ref
        assert _find_node(tree, NodeRef("os_window", "100")).is_expanded


async def test_enter_focuses_selected_pane() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test() as pilot:
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("focus_pane", "2") in backend.calls


async def test_reorder_routes_to_backend_and_preserves_selection() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test() as pilot:
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        pane_ref = NodeRef("pane", "2")
        tree.move_cursor(_find_node(tree, pane_ref))
        await pilot.press("shift+j")
        await app.workers.wait_for_complete()
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == pane_ref

    assert ("reorder_pane", "2", "forward") in backend.calls



async def test_reorder_restores_manager_focus(monkeypatch) -> None:
    monkeypatch.setenv("KITTY_WINDOW_ID", "99")
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test() as pilot:
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("shift+j")
        await app.workers.wait_for_complete()

    reorder_index = backend.calls.index(("reorder_pane", "2", "forward"))
    restore_index = backend.calls.index(("focus_pane", "99"))
    assert restore_index > reorder_index


async def test_rename_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test() as pilot:
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("r")
        rename_input = app.query_one("#rename-input", Input)
        rename_input.value = "test runner"
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("rename_pane", "2", "test runner") in backend.calls


async def test_move_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test() as pilot:
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "1")))
        await pilot.press("m")
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("move_pane", "1", "11") in backend.calls


async def test_merge_dialog_routes_to_backend() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None)

    async with app.run_test() as pilot:
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("os_window", "100")))
        await pilot.press("shift+m")
        await pilot.press("enter")
        await app.workers.wait_for_complete()

    assert ("merge_os_windows", "100", "200") in backend.calls
