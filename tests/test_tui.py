from __future__ import annotations

import asyncio
from dataclasses import replace
from threading import Event
from typing import TYPE_CHECKING

import pytest
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.strip import Strip
from textual.widgets import Input, Static, Tree

import catherd.tui as tui_module
from catherd.activity import PaneActivity
from catherd.model import KittyState, OsWindow, Pane, Tab
from catherd.tui import (
    Destination,
    KittyManagerApp,
    KittyTree,
    NodeRef,
    _active_marker,
    _apply_row_background,
    _compact_hint,
    _compact_process_hint,
    _count_label,
    _os_window_label,
    _pane_activity_hint,
    _pane_label,
    _preferred_textual_theme,
    _tab_band_background,
    _tab_label,
    _tree_header,
    _tree_row_background,
    containing_os_window_id,
    merge_os_window_destinations,
    merge_tab_destinations,
    move_destinations,
    selected_details,
    selected_title,
)

if TYPE_CHECKING:
    from collections.abc import Callable


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

    @staticmethod
    def _normalize_tab(tab: Tab) -> Tab:
        pane_count = len(tab.panes)
        panes = tuple(
            replace(
                pane,
                tab_index=index,
                tab_count=pane_count,
                group_index=index,
                group_count=pane_count,
                neighbors_left=(tab.panes[index - 2].id,) if index > 1 else (),
                neighbors_right=(tab.panes[index].id,) if index < pane_count else (),
                neighbors_top=(),
                neighbors_bottom=(),
            )
            for index, pane in enumerate(tab.panes, start=1)
        )
        return replace(tab, panes=panes)

    def _map_tabs(self, transform: Callable[[Tab], Tab]) -> None:
        self.state = KittyState(
            tuple(
                replace(os_window, tabs=tuple(transform(tab) for tab in os_window.tabs))
                for os_window in self.state.os_windows
            )
        )

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

        def rename(tab: Tab) -> Tab:
            panes = tuple(replace(pane, title=title) if pane.id == pane_id else pane for pane in tab.panes)
            return replace(tab, panes=panes)

        self._map_tabs(rename)

    def rename_tab(self, tab_id: str, title: str) -> None:
        self.calls.append(("rename_tab", tab_id, title))
        self._map_tabs(lambda tab: replace(tab, title=title) if tab.id == tab_id else tab)

    def rename_os_window(self, os_window_id: str, title: str) -> None:
        self.calls.append(("rename_os_window", os_window_id, title))
        self.state = KittyState(
            tuple(
                replace(os_window, title=title) if os_window.id == os_window_id else os_window
                for os_window in self.state.os_windows
            )
        )

    def move_pane(self, pane_id: str, target_tab_id: str) -> None:
        self.calls.append(("move_pane", pane_id, target_tab_id))
        location = self.state.find_pane(pane_id)
        if location is None:
            return
        moved = location.pane

        def move(tab: Tab) -> Tab:
            panes = tuple(pane for pane in tab.panes if pane.id != pane_id)
            if tab.id == target_tab_id:
                panes += (moved,)
            return self._normalize_tab(replace(tab, panes=panes))

        self._map_tabs(move)

    def detach_pane_to_new_tab(self, pane_id: str) -> None:
        self.calls.append(("detach_pane_to_new_tab", pane_id))
        location = self.state.find_pane(pane_id)
        if location is None:
            return
        self.move_pane(pane_id, "__detached__")
        new_tab = self._normalize_tab(Tab(id=f"new-tab-{pane_id}", title=location.pane.title, panes=(location.pane,)))
        self.state = KittyState(
            tuple(
                replace(os_window, tabs=(*os_window.tabs, new_tab))
                if os_window.id == location.os_window.id
                else os_window
                for os_window in self.state.os_windows
            )
        )

    def detach_pane_to_new_os_window(self, pane_id: str) -> None:
        self.calls.append(("detach_pane_to_new_os_window", pane_id))
        location = self.state.find_pane(pane_id)
        if location is None:
            return
        self.move_pane(pane_id, "__detached__")
        new_tab = self._normalize_tab(Tab(id=f"new-tab-{pane_id}", title=location.pane.title, panes=(location.pane,)))
        new_os_window = OsWindow(id=f"new-os-{pane_id}", title=None, tabs=(new_tab,))
        self.state = KittyState((*self.state.os_windows, new_os_window))

    def move_tab(self, tab_id: str, target_os_window_id: str) -> None:
        self.calls.append(("move_tab", tab_id, target_os_window_id))
        found = self.state.find_tab(tab_id)
        if found is None:
            return
        moved = found[1]
        os_windows: list[OsWindow] = []
        for os_window in self.state.os_windows:
            tabs = tuple(tab for tab in os_window.tabs if tab.id != tab_id)
            if os_window.id == target_os_window_id:
                tabs += (moved,)
            if tabs:
                os_windows.append(replace(os_window, tabs=tabs))
        self.state = KittyState(tuple(os_windows))

    def detach_tab_to_new_os_window(self, tab_id: str) -> None:
        self.calls.append(("detach_tab_to_new_os_window", tab_id))
        found = self.state.find_tab(tab_id)
        if found is None:
            return
        moved = found[1]
        source_os_id = found[0].id
        os_windows = [
            replace(os_window, tabs=tuple(tab for tab in os_window.tabs if tab.id != tab_id))
            if os_window.id == source_os_id
            else os_window
            for os_window in self.state.os_windows
        ]
        os_windows = [os_window for os_window in os_windows if os_window.tabs]
        os_windows.append(OsWindow(id=f"new-os-tab-{tab_id}", title=None, tabs=(moved,)))
        self.state = KittyState(tuple(os_windows))

    def reorder_pane(self, pane_id: str, direction: str) -> None:
        self.calls.append(("reorder_pane", pane_id, direction))
        location = self.state.find_pane(pane_id)
        if location is None:
            return

        def reorder(tab: Tab) -> Tab:
            if tab.id != location.tab.id:
                return tab
            panes = list(tab.panes)
            index = next(index for index, pane in enumerate(panes) if pane.id == pane_id)
            target = index + (1 if direction == "forward" else -1)
            if 0 <= target < len(panes):
                panes[index], panes[target] = panes[target], panes[index]
            return self._normalize_tab(replace(tab, panes=tuple(panes)))

        self._map_tabs(reorder)

    def reorder_tab(self, tab_id: str, direction: str) -> None:
        self.calls.append(("reorder_tab", tab_id, direction))
        found = self.state.find_tab(tab_id)
        if found is None:
            return
        parent_id = found[0].id
        os_windows: list[OsWindow] = []
        for os_window in self.state.os_windows:
            if os_window.id != parent_id:
                os_windows.append(os_window)
                continue
            tabs = list(os_window.tabs)
            index = next(index for index, tab in enumerate(tabs) if tab.id == tab_id)
            target = index + (1 if direction == "forward" else -1)
            if 0 <= target < len(tabs):
                tabs[index], tabs[target] = tabs[target], tabs[index]
            os_windows.append(replace(os_window, tabs=tuple(tabs)))
        self.state = KittyState(tuple(os_windows))

    def merge_tabs(self, source_tab_id: str, target_tab_id: str) -> None:
        self.calls.append(("merge_tabs", source_tab_id, target_tab_id))
        source = self.state.find_tab(source_tab_id)
        target = self.state.find_tab(target_tab_id)
        if source is None or target is None:
            return
        source_panes = source[1].panes
        os_windows: list[OsWindow] = []
        for os_window in self.state.os_windows:
            tabs: list[Tab] = []
            for tab_ in os_window.tabs:
                if tab_.id == source_tab_id:
                    continue
                if tab_.id == target_tab_id:
                    tab = self._normalize_tab(replace(tab_, panes=tab_.panes + source_panes))
                else:
                    tab = tab_
                tabs.append(tab)
            if tabs:
                os_windows.append(replace(os_window, tabs=tuple(tabs)))
        self.state = KittyState(tuple(os_windows))

    def merge_os_windows(self, source_os_window_id: str, target_os_window_id: str) -> None:
        self.calls.append(("merge_os_windows", source_os_window_id, target_os_window_id))
        source = self.state.find_os_window(source_os_window_id)
        if source is None:
            return
        self.state = KittyState(
            tuple(
                replace(os_window, tabs=os_window.tabs + source.tabs)
                if os_window.id == target_os_window_id
                else os_window
                for os_window in self.state.os_windows
                if os_window.id != source_os_window_id
            )
        )


class BlockingSnapshotBackend(FakeBackend):
    def __init__(self, state: KittyState) -> None:
        super().__init__(state)
        self.block_next_snapshot = False
        self.snapshot_started = Event()
        self.snapshot_release = Event()

    def snapshot(self) -> KittyState:
        self.calls.append(("snapshot",))
        if self.block_next_snapshot:
            self.block_next_snapshot = False
            self.snapshot_started.set()
            self.snapshot_release.wait(timeout=2)
        return self.state


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


def _child_refs(tree: Tree[NodeRef], ref: NodeRef) -> list[NodeRef]:
    return [data for child in _find_node(tree, ref).children if (data := child.data) is not None]


def _root_refs(tree: Tree[NodeRef]) -> list[NodeRef]:
    return [data for child in tree.root.children if (data := child.data) is not None]


def _line_for_ref(tree: Tree[NodeRef], ref: NodeRef) -> int:
    for line in range(tree.last_line + 1):
        node = tree.get_node_at_line(line)
        if node is not None and node.data == ref:
            return line
    msg = f"missing rendered line: {ref}"
    raise AssertionError(msg)


def _style_for(text: Text, needle: str) -> Style:
    offset = text.plain.index(needle)
    for span in text.spans:
        if span.start <= offset < span.end:
            return Style.parse(span.style) if isinstance(span.style, str) else span.style
    return Style()


@pytest.mark.small
def test_move_destinations_for_pane() -> None:
    destinations = move_destinations(_state(), NodeRef("pane", "1"))

    assert Destination("tab", "11", "OS 100 — work / shell [11]") in destinations
    assert Destination("tab", "20", "OS 200 — notes / notes [20]") in destinations
    assert Destination("tab", "10", "OS 100 — work / editor [10]") not in destinations
    assert destinations[-2:] == (
        Destination("new_tab", None, "New tab"),
        Destination("new_os_window", None, "New OS window"),
    )


@pytest.mark.small
def test_move_destinations_for_tab() -> None:
    destinations = move_destinations(_state(), NodeRef("tab", "10"))

    assert destinations == (
        Destination("os_window", "200", "OS 200 — notes"),
        Destination("new_os_window", None, "New OS window"),
    )


@pytest.mark.small
def test_merge_os_window_destinations_exclude_source() -> None:
    assert merge_os_window_destinations(_state(), "100") == (Destination("os_window", "200", "OS 200 — notes"),)


@pytest.mark.small
def test_merge_tab_destinations_exclude_source() -> None:
    destinations = merge_tab_destinations(_state(), "10")

    assert Destination("tab", "10", "irrelevant") not in destinations
    assert Destination("tab", "11", "OS 100 — work / shell [11]") in destinations
    assert Destination("tab", "20", "OS 200 — notes / notes [20]") in destinations


@pytest.mark.small
def test_containing_os_window_id_resolves_all_node_kinds() -> None:
    state = _state()

    assert containing_os_window_id(state, NodeRef("os_window", "100")) == "100"
    assert containing_os_window_id(state, NodeRef("tab", "10")) == "100"
    assert containing_os_window_id(state, NodeRef("pane", "1")) == "100"


@pytest.mark.small
def test_count_label_uses_singular_and_plural_grammar() -> None:
    assert _count_label(1, "OS window") == "1 OS window"
    assert _count_label(2, "OS window") == "2 OS windows"
    assert _count_label(1, "pane") == "1 pane"
    assert _count_label(2, "pane") == "2 panes"


@pytest.mark.small
def test_selected_title_uses_hierarchy() -> None:
    state = _state()

    assert selected_title(state, NodeRef("pane", "1")) == "nvim"
    assert selected_title(state, NodeRef("tab", "10")) == "editor"
    assert selected_title(state, NodeRef("os_window", "100")) == "work"
    assert selected_title(state, NodeRef("pane", "missing")) == ""


@pytest.mark.small
def test_selected_details_for_os_window() -> None:
    details = selected_details(_state(), NodeRef("os_window", "100"))

    assert "OS WINDOW #100" in details.plain
    assert "work" in details.plain
    assert "SUMMARY" in details.plain
    assert "State      active" in details.plain
    assert "Tabs       2" in details.plain
    assert "Panes      3" in details.plain


@pytest.mark.small
def test_selected_details_for_tab() -> None:
    details = selected_details(_state(), NodeRef("tab", "10"))

    assert "TAB #10" in details.plain
    assert "editor" in details.plain
    assert "OS #100" in details.plain
    assert "SUMMARY" in details.plain
    assert "State      active" in details.plain
    assert "Layout     splits" in details.plain
    assert "Panes      2" in details.plain


@pytest.mark.small
def test_selected_details_for_pane_with_activity() -> None:
    details = selected_details(
        _state(),
        NodeRef("pane", "1"),
        activity=_activity("1"),
    )

    assert "PANE #1" in details.plain
    assert "nvim" in details.plain
    assert "OS #100 > editor #10" in details.plain

    assert "STATE" in details.plain
    assert "● ACTIVE" in details.plain
    assert "Command running" in details.plain

    assert "LOCATION" in details.plain
    assert "Path       /code/project" in details.plain
    assert "Pane       1 of 2" in details.plain
    assert "Size       120 × 40" in details.plain  # ruff: ignore[ambiguous-unicode-character-string]
    assert "Neighbors  R:2" in details.plain

    assert "PROCESS" in details.plain
    assert "Command    uv run pytest" in details.plain
    assert "Foreground nvim" in details.plain
    assert "Shell      /bin/zsh -l" in details.plain

    assert "RECENT" in details.plain
    assert "Last       pytest -q" in details.plain
    assert "Atuin      session-1" in details.plain


@pytest.mark.small
def test_selected_details_for_pane_loading() -> None:
    details = selected_details(
        _state(),
        NodeRef("pane", "1"),
        activity_loading=True,
    )

    assert "RECENT" in details.plain
    assert "Last       loading…" in details.plain


@pytest.mark.small
def test_selected_details_explains_empty_recent_command() -> None:
    details = selected_details(
        _state(),
        NodeRef("pane", "1"),
        activity=PaneActivity(session_id="session-1", last_command=None),
    )

    assert "Last       No completed command" in details.plain
    assert "Atuin      session-1" in details.plain


@pytest.mark.medium
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
        assert "RECENT" in details.content.plain
        assert "session-live" in details.content.plain
        assert "uv run pytest" in details.content.plain

    assert "1" in calls


@pytest.mark.small
@pytest.mark.parametrize(
    ("dark", "expected"),
    [(True, "#272727"), (False, "#f4f4f4")],
)
def test_tab_band_background_tracks_theme(dark, expected) -> None:
    assert _tab_band_background(dark=dark) == expected


@pytest.mark.small
def test_tree_row_background_preserves_grouping_through_hover_and_selection() -> None:
    assert _tree_row_background(
        dark=False,
        banded=True,
        selected=False,
        hovered=False,
    ) == "#f4f4f4"
    assert _tree_row_background(
        dark=False,
        banded=True,
        selected=False,
        hovered=True,
    ) == "#e9eff2"
    assert _tree_row_background(
        dark=False,
        banded=False,
        selected=False,
        hovered=True,
    ) == "#edf3f6"
    assert _tree_row_background(
        dark=False,
        banded=True,
        selected=True,
        hovered=True,
    ) == "#365f7e"
    assert _tree_row_background(
        dark=False,
        banded=False,
        selected=True,
        hovered=True,
    ) == "#3e6786"


@pytest.mark.small
def test_row_background_spans_whole_strip() -> None:
    strip = Strip(
        [
            Segment("row", Style(bgcolor="red")),
            Segment("      ", Style(bgcolor="red")),
        ]
    )

    styled = _apply_row_background(strip, "#f4f4f4")

    for segment in styled:
        assert segment.style is not None
        assert segment.style.bgcolor is not None
        assert segment.style.bgcolor.name == "#f4f4f4"


@pytest.mark.small
def test_active_marker_does_not_reuse_tree_disclosure_triangle() -> None:
    assert _active_marker(active=True) == "● "
    assert _active_marker(active=False) == "  "


@pytest.mark.small
def test_outline_header_explains_tree_columns() -> None:
    header = _tree_header()

    assert "HIERARCHY" in header.plain
    assert "ID" in header.plain
    assert "LAYOUT / STATE" in header.plain
    assert "CURRENT / SUMMARY" in header.plain
    for heading in ("HIERARCHY", "ID", "LAYOUT / STATE", "CURRENT / SUMMARY"):
        assert _style_for(header, heading).bold


@pytest.mark.small
def test_tree_labels_use_semantic_outline_columns() -> None:
    state = _state()
    os_window = state.os_windows[0]
    tab = os_window.tabs[0]
    pane = tab.panes[0]

    os_label = _os_window_label(os_window, active_branch=True)
    tab_label = _tab_label(tab, active_branch=True)
    pane_label = _pane_label(pane, tab.title, active=True)

    assert os_label.plain.index("work") < os_label.plain.index("#100")
    assert os_label.plain.index("#100") < os_label.plain.index("active")
    assert os_label.plain.index("active") < os_label.plain.index("2 tabs · 3 panes")

    assert tab_label.plain.index("editor") < tab_label.plain.index("#10")
    assert tab_label.plain.index("#10") < tab_label.plain.index("splits")

    assert pane_label.plain.index("nvim") < pane_label.plain.index("#1")
    assert pane_label.plain.index("#1") < pane_label.plain.index("active")
    assert pane_label.plain.index("active") < pane_label.plain.index("uv run pytest")

    assert _style_for(tab_label, "editor").bold
    assert _style_for(tab_label, "editor").color.name == "cyan"
    assert _style_for(pane_label, "#1").color.name == "cyan"
    assert _style_for(pane_label, "uv run pytest").italic


@pytest.mark.small
def test_outline_columns_align_across_tree_depths() -> None:
    state = _state()
    os_window = state.os_windows[0]
    tab = os_window.tabs[0]
    pane = tab.panes[0]

    os_label = _os_window_label(os_window, active_branch=True)
    tab_label = _tab_label(tab, active_branch=True)
    pane_label = _pane_label(pane, tab.title, active=True)

    # Textual uses four cells per hierarchy level. Expandable OS/tab rows
    # also receive a two-cell disclosure prefix; pane leaves do not.
    os_id_cell = 4 + 2 + os_label.plain.index("#100")
    tab_id_cell = 8 + 2 + tab_label.plain.index("#10")
    pane_id_cell = 12 + pane_label.plain.index("#1")
    assert os_id_cell == tab_id_cell == pane_id_cell

    os_state_cell = 4 + 2 + os_label.plain.index("active")
    tab_state_cell = 8 + 2 + tab_label.plain.index("splits")
    pane_state_cell = 12 + pane_label.plain.index("active")
    assert os_state_cell == tab_state_cell == pane_state_cell


@pytest.mark.small
def test_inspector_uses_labels_to_explain_values() -> None:
    details = selected_details(_state(), NodeRef("pane", "1"), activity=_activity("1"))

    kind_style = _style_for(details, "PANE")
    assert kind_style.italic
    assert kind_style.color.name == "cyan"
    assert _style_for(details, "#1").color.name == "cyan"

    breadcrumb_style = _style_for(details, "OS #100 > editor #10")
    assert breadcrumb_style.italic
    assert breadcrumb_style.color.name == "cyan"

    assert _style_for(details, "STATE").color.name == "cyan"
    assert _style_for(details, "Path").italic
    assert _style_for(details, "Path").color.name == "cyan"
    assert _style_for(details, "/code/project").bold
    assert _style_for(details, "─").color.name == "cyan"



@pytest.mark.small
def test_preferred_theme_honors_override(monkeypatch) -> None:
    monkeypatch.setenv("CATHERD_THEME", "ansi-light")

    assert _preferred_textual_theme() == "ansi-light"


@pytest.mark.small
@pytest.mark.parametrize(
    ("appearance", "expected"),
    [("Dark\n", "ansi-dark"), ("", "ansi-light")],
)
def test_preferred_theme_uses_macos_appearance(monkeypatch, appearance, expected) -> None:
    monkeypatch.delenv("CATHERD_THEME", raising=False)
    monkeypatch.setattr(tui_module.sys, "platform", "darwin")
    monkeypatch.setattr(
        tui_module.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"stdout": appearance})(),
    )

    assert _preferred_textual_theme() == expected


@pytest.mark.medium
async def test_explicit_theme_name_is_applied() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(
        backend,
        poll_interval=None,
        activity_provider=_activity,
        theme_name="ansi-light",
    )

    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.theme == "ansi-light"


@pytest.mark.small
def test_compact_hint_normalizes_and_truncates() -> None:
    assert _compact_hint("  uv   run   pytest  ") == "uv run pytest"
    hint = _compact_hint("x" * 80)
    assert hint is not None
    assert len(hint) == 36
    assert hint.endswith("...")


@pytest.mark.small
def test_shell_wrapper_is_omitted_from_pane_activity_hint() -> None:
    location = _state().find_pane("2")
    assert location is not None
    pane = replace(
        location.pane,
        current_command=None,
        foreground_cmd="/Users/me/.local/bin/atuin-patched pty-proxy --shell /bin/zsh",
    )

    assert _pane_activity_hint(pane) is None


@pytest.mark.small
def test_compact_process_hint_strips_absolute_paths() -> None:
    hint = _compact_process_hint(
        "/Users/me/.local/bin/atuin-patched-18.22.0 pty-proxy --shell /opt/homebrew/bin/zsh"
    )

    assert hint == "atuin-patched-18.22.0 pty-proxy ..."
    assert "/Users/me" not in hint


@pytest.mark.medium
async def test_tree_rows_are_compact_and_mark_kitty_active() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        pane = _find_node(tree, NodeRef("pane", "1"))
        assert isinstance(pane.label, Text)
        assert "● " in pane.label.plain
        assert "nvim" in pane.label.plain
        assert "#1" in pane.label.plain
        assert "uv run pytest" in pane.label.plain
        assert "/code/project" not in pane.label.plain

        inactive = _find_node(tree, NodeRef("pane", "2"))
        assert isinstance(inactive.label, Text)
        assert "● " not in inactive.label.plain


@pytest.mark.small
def test_locally_active_pane_is_not_marked_as_globally_active() -> None:
    pane = Pane(id="12", title="shell", is_active=True)

    label = _pane_label(pane, "other", active=False)

    assert "● " not in label.plain


@pytest.mark.small
def test_redundant_pane_title_falls_back_to_process_identity() -> None:
    pane = Pane(
        id="12",
        title="~/code/AirBattery",
        root_cmdline="/opt/homebrew/bin/zsh",
        at_prompt=True,
        tab_index=1,
        tab_count=2,
    )

    label = _pane_label(pane, "~/code/AirBattery")

    assert "~/code/AirBattery" not in label.plain
    assert "zsh" in label.plain
    assert "#12" in label.plain
    assert "1/2" in label.plain
    assert "prompt" in label.plain


@pytest.mark.small
def test_long_command_title_is_preserved_in_current_column() -> None:
    command = "uv run python -m http.server --bind 127.0.0.1"
    pane = Pane(
        id="6",
        title=command,
        current_command=command,
        at_prompt=False,
    )

    label = _pane_label(pane, "~/code/lecgan")

    assert "uv run python" in label.plain
    assert "running" in label.plain
    assert _compact_hint(command) in label.plain


@pytest.mark.small
def test_repeated_pane_title_prefers_current_command_over_shell() -> None:
    pane = Pane(
        id="17",
        title="catherd tui",
        current_command="catherd tui",
        root_cmdline="/opt/homebrew/bin/zsh",
    )

    label = _pane_label(pane, "catherd tui")

    assert "catherd tui" in label.plain
    assert "zsh" not in label.plain


@pytest.mark.small
def test_active_branch_labels_strengthen_ancestry_without_green_markers() -> None:
    state = _state()
    os_label = _os_window_label(state.os_windows[0], active_branch=True)
    tab_label = _tab_label(state.os_windows[0].tabs[0], active_branch=True)

    assert "● " not in os_label.plain
    assert "● " not in tab_label.plain
    assert _style_for(os_label, "work").bold
    assert _style_for(os_label, "work").color.name == "cyan"
    assert _style_for(os_label, "#100").color.name == "cyan"
    assert _style_for(tab_label, "editor").bold
    assert _style_for(tab_label, "editor").color.name == "cyan"


@pytest.mark.medium
async def test_only_active_pane_has_green_marker_and_branch_is_tracked() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: KittyTree = app.query_one("#kitty-tree", KittyTree)

        os_label = _find_node(tree, NodeRef("os_window", "100")).label
        tab_label = _find_node(tree, NodeRef("tab", "10")).label
        pane_label = _find_node(tree, NodeRef("pane", "1")).label
        assert isinstance(os_label, Text)
        assert isinstance(tab_label, Text)
        assert isinstance(pane_label, Text)
        assert "● " not in os_label.plain
        assert "● " not in tab_label.plain
        assert "● " in pane_label.plain
        assert tree._active_branch_refs == {
            NodeRef("os_window", "100"),
            NodeRef("tab", "10"),
            NodeRef("pane", "1"),
        }


@pytest.mark.medium
async def test_help_moves_infrequent_actions_out_of_persistent_footer() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("?")
        await pilot.pause()

        help_dialog = app.screen.query_one("#help-dialog", Static)
        assert "M         merge tab / OS window" in str(help_dialog.content)
        assert "J/K       reorder pane / tab" in str(help_dialog.content)


@pytest.mark.medium
async def test_action_strip_is_quiet_static_help() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        actions = app.query_one("#actions", Static)
        assert isinstance(actions.content, Text)
        assert "/ filter" in actions.content.plain
        assert "a active" in actions.content.plain
        assert "? help" in actions.content.plain
        assert "r rename" not in actions.content.plain
        assert "m move" not in actions.content.plain
        assert "J/K" not in actions.content.plain
        assert "Merge" not in actions.content.plain
        assert _style_for(actions.content, "Enter").bold
        assert not _style_for(actions.content, "focus").bold

        footer = app.query_one("#footer")
        status = app.query_one("#status", Static)
        assert footer is status.parent


@pytest.mark.medium
async def test_filter_tree_keeps_matching_ancestors_and_prunes_siblings() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        filter_input = app.screen.query_one("#filter-input", Input)
        filter_input.value = "tests"
        await pilot.press("enter")
        await pilot.pause()

        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        assert _child_refs(tree, NodeRef("os_window", "100")) == [NodeRef("tab", "10")]
        assert _child_refs(tree, NodeRef("tab", "10")) == [NodeRef("pane", "2")]
        assert all(node.data != NodeRef("os_window", "200") for node in tree.root.children)


@pytest.mark.medium
async def test_escape_clears_tree_filter() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        filter_input = app.screen.query_one("#filter-input", Input)
        filter_input.value = "pytest"
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("escape")
        await pilot.pause()

        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        assert app._filter_query == ""
        assert _root_refs(tree) == [NodeRef("os_window", "100"), NodeRef("os_window", "200")]


@pytest.mark.medium
async def test_jump_active_clears_filter_and_selects_active_pane() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("/")
        filter_input = app.screen.query_one("#filter-input", Input)
        filter_input.value = "notes"
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()

        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("pane", "1")
        assert app._filter_query == ""
        assert _find_node(tree, NodeRef("os_window", "200"))


@pytest.mark.medium
async def test_tree_inserts_blank_spacing_between_tabs_and_windows() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)

        assert [child.data for child in tree.root.children] == [
            NodeRef("os_window", "100"),
            None,
            NodeRef("os_window", "200"),
        ]
        os_node = _find_node(tree, NodeRef("os_window", "100"))
        assert [child.data for child in os_node.children] == [
            NodeRef("tab", "10"),
            None,
            NodeRef("tab", "11"),
        ]

        window_spacer = tree.root.children[1]
        window_spacer_line = next(
            line
            for line in range(tree.last_line + 1)
            if tree.get_node_at_line(line) is window_spacer
        )
        window_gap = tree.render_line(window_spacer_line).text
        assert "│" in window_gap
        assert "├" not in window_gap
        assert "└" not in window_gap

        tab_spacer = os_node.children[1]
        tab_spacer_line = next(
            line
            for line in range(tree.last_line + 1)
            if tree.get_node_at_line(line) is tab_spacer
        )
        tab_gap = tree.render_line(tab_spacer_line).text
        assert "│" in tab_gap
        assert "├" not in tab_gap
        assert "└" not in tab_gap


@pytest.mark.medium
async def test_tree_navigation_skips_blank_spacers() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))

        await pilot.press("j")
        await pilot.pause()

        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("tab", "11")


@pytest.mark.medium
async def test_alternate_tab_subtree_is_banded() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: KittyTree = app.query_one("#kitty-tree", KittyTree)

        assert NodeRef("tab", "10") not in tree._banded_refs
        assert NodeRef("pane", "1") not in tree._banded_refs
        assert NodeRef("tab", "11") in tree._banded_refs
        assert NodeRef("pane", "3") in tree._banded_refs


@pytest.mark.medium
async def test_banded_row_keeps_group_identity_when_selected_or_hovered() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: KittyTree = app.query_one("#kitty-tree", KittyTree)
        banded_ref = NodeRef("pane", "3")
        banded_node = _find_node(tree, banded_ref)
        banded_line = _line_for_ref(tree, banded_ref)

        tree.move_cursor(banded_node)
        await pilot.pause()
        selected_strip = tree.render_line(banded_line)
        assert selected_strip.cell_length == tree.size.width
        selected_segment = list(selected_strip)[-1]
        assert selected_segment.style is not None
        assert selected_segment.style.bgcolor is not None
        selected_banded = selected_segment.style.bgcolor.name

        tree.move_cursor(_find_node(tree, NodeRef("pane", "1")))
        tree.hover_line = banded_line
        hovered_strip = tree.render_line(banded_line)
        assert hovered_strip.cell_length == tree.size.width
        hovered_segment = list(hovered_strip)[-1]
        assert hovered_segment.style is not None
        assert hovered_segment.style.bgcolor is not None
        hovered_banded = hovered_segment.style.bgcolor.name

        dark = app.current_theme.dark
        assert selected_banded == _tree_row_background(
            dark=dark,
            banded=True,
            selected=True,
            hovered=False,
        )
        assert hovered_banded == _tree_row_background(
            dark=dark,
            banded=True,
            selected=False,
            hovered=True,
        )


@pytest.mark.medium
async def test_tui_renders_hierarchy_and_selects_active_pane() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        assert not tree.show_root
        header = app.query_one("#tree-header", Static)
        assert isinstance(header.content, Text)
        assert "HIERARCHY" in header.content.plain
        assert "ID" in header.content.plain
        assert "LAYOUT / STATE" in header.content.plain
        assert "CURRENT / SUMMARY" in header.content.plain
        assert _root_refs(tree) == [NodeRef("os_window", "100"), NodeRef("os_window", "200")]
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("pane", "1")
        assert _find_node(tree, NodeRef("tab", "10")).is_expanded


@pytest.mark.medium
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


@pytest.mark.medium
async def test_tree_click_selects_without_focusing_kitty_until_explicit_action() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        target_ref = NodeRef("pane", "2")
        target_line = _line_for_ref(tree, target_ref)

        assert await pilot.click(tree, offset=(20, target_line))
        await pilot.pause()

        assert tree.cursor_node is not None
        assert tree.cursor_node.data == target_ref
        assert ("focus_pane", "2") not in backend.calls

        await pilot.press("f")
        await app.workers.wait_for_complete()

    assert ("focus_pane", "2") in backend.calls


@pytest.mark.medium
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


@pytest.mark.parametrize(
    ("ref", "expected_call"),
    [
        (NodeRef("tab", "10"), ("focus_tab", "10")),
        (NodeRef("os_window", "200"), ("focus_os_window", "200")),
    ],
)
@pytest.mark.medium
async def test_explicit_focus_routes_selected_container(
    ref: NodeRef,
    expected_call: tuple[object, ...],
) -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, ref))
        await pilot.press("f")
        await app.workers.wait_for_complete()

    assert expected_call in backend.calls


@pytest.mark.medium
async def test_reorder_pane_updates_tree_order_and_preserves_selection() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        pane_ref = NodeRef("pane", "1")
        tree.move_cursor(_find_node(tree, pane_ref))
        await pilot.press("J")
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert _child_refs(tree, NodeRef("tab", "10")) == [
            NodeRef("pane", "2"),
            NodeRef("pane", "1"),
        ]
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == pane_ref

    assert ("reorder_pane", "1", "forward") in backend.calls


@pytest.mark.medium
async def test_reorder_tab_updates_tree_order() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tab_ref = NodeRef("tab", "10")
        tree.move_cursor(_find_node(tree, tab_ref))
        await pilot.press("J")
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert _child_refs(tree, NodeRef("os_window", "100")) == [
            NodeRef("tab", "11"),
            NodeRef("tab", "10"),
        ]
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == tab_ref

    assert ("reorder_tab", "10", "forward") in backend.calls


@pytest.mark.medium
async def test_uppercase_k_reorders_backward() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.press("K")
        await app.workers.wait_for_complete()
        await pilot.pause()

        assert _child_refs(tree, NodeRef("tab", "10")) == [
            NodeRef("pane", "2"),
            NodeRef("pane", "1"),
        ]

    assert ("reorder_pane", "2", "backward") in backend.calls


@pytest.mark.medium
async def test_reorder_restores_manager_focus(monkeypatch) -> None:
    monkeypatch.setenv("KITTY_WINDOW_ID", "99")
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "1")))
        await pilot.press("J")
        await app.workers.wait_for_complete()

    reorder_index = backend.calls.index(("reorder_pane", "1", "forward"))
    restore_index = backend.calls.index(("focus_pane", "99"))
    assert restore_index > reorder_index


@pytest.mark.medium
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


@pytest.mark.medium
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


@pytest.mark.medium
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


@pytest.mark.medium
async def test_move_pane_to_new_tab_updates_hierarchy() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        pane_ref = NodeRef("pane", "1")
        tree.move_cursor(_find_node(tree, pane_ref))
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("j", "j", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        location = backend.state.find_pane("1")
        assert location is not None
        assert location.tab.id == "new-tab-1"
        moved_node = _find_node(tree, pane_ref)
        assert moved_node.parent is not None
        assert moved_node.parent.data == NodeRef("tab", "new-tab-1")
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == pane_ref


@pytest.mark.medium
async def test_move_pane_to_new_os_window_updates_hierarchy() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        pane_ref = NodeRef("pane", "1")
        tree.move_cursor(_find_node(tree, pane_ref))
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("j", "j", "j", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        location = backend.state.find_pane("1")
        assert location is not None
        assert location.os_window.id == "new-os-1"
        assert _find_node(tree, pane_ref).parent is not None
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == pane_ref


@pytest.mark.medium
async def test_move_tab_to_existing_os_window_updates_hierarchy() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tab_ref = NodeRef("tab", "10")
        tree.move_cursor(_find_node(tree, tab_ref))
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        found = backend.state.find_tab("10")
        assert found is not None
        assert found[0].id == "200"
        moved_node = _find_node(tree, tab_ref)
        assert moved_node.parent is not None
        assert moved_node.parent.data == NodeRef("os_window", "200")
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == tab_ref


@pytest.mark.medium
async def test_detach_tab_to_new_os_window_updates_hierarchy() -> None:
    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tab_ref = NodeRef("tab", "10")
        tree.move_cursor(_find_node(tree, tab_ref))
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("j", "enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        found = backend.state.find_tab("10")
        assert found is not None
        assert found[0].id == "new-os-tab-10"
        assert _find_node(tree, NodeRef("os_window", "new-os-tab-10"))
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == tab_ref


@pytest.mark.medium
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


@pytest.mark.medium
async def test_merge_tab_updates_hierarchy() -> None:
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
        await pilot.pause()

        assert backend.state.find_tab("10") is None
        assert _child_refs(tree, NodeRef("tab", "11")) == [
            NodeRef("pane", "3"),
            NodeRef("pane", "1"),
            NodeRef("pane", "2"),
        ]
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("tab", "11")

    assert ("merge_tabs", "10", "11") in backend.calls


@pytest.mark.medium
async def test_merge_os_windows_updates_hierarchy() -> None:
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
        await pilot.pause()

        assert backend.state.find_os_window("100") is None
        assert _child_refs(tree, NodeRef("os_window", "200")) == [
            NodeRef("tab", "20"),
            NodeRef("tab", "10"),
            NodeRef("tab", "11"),
        ]
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == NodeRef("os_window", "200")

    assert ("merge_os_windows", "100", "200") in backend.calls


@pytest.mark.medium
async def test_in_flight_refresh_does_not_restore_stale_selection() -> None:
    backend = BlockingSnapshotBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=_activity)

    async with app.run_test() as pilot:
        await pilot.pause()
        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        backend.block_next_snapshot = True
        refresh = asyncio.create_task(app.refresh_state())

        started = await asyncio.to_thread(backend.snapshot_started.wait, 1.0)
        assert started

        target_ref = NodeRef("pane", "2")
        tree.move_cursor(_find_node(tree, target_ref))
        await pilot.pause()

        backend.snapshot_release.set()
        await refresh
        await pilot.pause()

        assert tree.cursor_node is not None
        assert tree.cursor_node.data == target_ref


@pytest.mark.medium
async def test_stale_activity_result_does_not_overwrite_new_selection() -> None:
    pane_one_started = Event()
    pane_one_release = Event()

    def activity_provider(pane_id: str) -> PaneActivity:
        if pane_id == "1":
            pane_one_started.set()
            pane_one_release.wait(timeout=2)
            return PaneActivity(session_id="session-1", last_command="stale-one")
        return PaneActivity(session_id="session-2", last_command="current-two")

    backend = FakeBackend(_state())
    app = KittyManagerApp(backend, poll_interval=None, activity_provider=activity_provider)

    async with app.run_test() as pilot:
        await pilot.pause()
        started = await asyncio.to_thread(pane_one_started.wait, 1.0)
        assert started

        tree: Tree[NodeRef] = app.query_one("#kitty-tree", Tree)
        tree.move_cursor(_find_node(tree, NodeRef("pane", "2")))
        await pilot.pause()

        pane_one_release.set()
        await app.workers.wait_for_complete()
        await pilot.pause()

        details = app.query_one("#details", Static)
        assert isinstance(details.content, Text)
        assert "RECENT" in details.content.plain
        assert "Atuin      session-2" in details.content.plain
        assert "Last       current-two" in details.content.plain
        assert "stale-one" not in details.content.plain
