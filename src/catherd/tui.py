"""Interactive Kitty organizer."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Literal, Protocol

from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, OptionList, Static, Tree
from textual.widgets.option_list import Option
from .kitty import KittyClient, KittyClientError
from .model import KittyState

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import ClassVar

    from textual.app import ComposeResult
    from textual.binding import BindingType
    from textual.widgets.tree import TreeNode

    from .model import OsWindow, Pane, Tab

NodeKind = Literal["os_window", "tab", "pane"]
DestinationKind = Literal["os_window", "tab", "new_tab", "new_os_window"]
ReorderDirection = Literal["forward", "backward"]


@dataclass(frozen=True, slots=True)
class NodeRef:
    """Stable reference to an object in a Kitty snapshot."""

    kind: NodeKind
    id: str


@dataclass(frozen=True, slots=True)
class Destination:
    """A valid destination for a move or merge operation."""

    kind: DestinationKind
    id: str | None
    label: str


class KittyBackend(Protocol):
    """Operations required by the TUI."""

    def snapshot(self) -> KittyState: ...

    def focus_pane(self, pane_id: str) -> None: ...

    def focus_tab(self, tab_id: str) -> None: ...

    def focus_os_window(self, os_window_id: str) -> None: ...

    def rename_pane(self, pane_id: str, title: str) -> None: ...

    def rename_tab(self, tab_id: str, title: str) -> None: ...

    def rename_os_window(self, os_window_id: str, title: str) -> None: ...

    def move_pane(self, pane_id: str, target_tab_id: str) -> None: ...

    def detach_pane_to_new_tab(self, pane_id: str) -> None: ...

    def detach_pane_to_new_os_window(self, pane_id: str) -> None: ...

    def move_tab(self, tab_id: str, target_os_window_id: str) -> None: ...

    def detach_tab_to_new_os_window(self, tab_id: str) -> None: ...

    def reorder_pane(self, pane_id: str, direction: ReorderDirection) -> None: ...

    def reorder_tab(self, tab_id: str, direction: ReorderDirection) -> None: ...

    def merge_os_windows(self, source_os_window_id: str, target_os_window_id: str) -> None: ...


def _display_name(value: str | None, fallback: str) -> str:
    return value or fallback


def _os_window_label(os_window: OsWindow) -> Text:
    label = Text()
    label.append("● " if os_window.is_active else "  ", style="bold" if os_window.is_active else "")
    label.append("OS ", style="dim")
    label.append(_display_name(os_window.id, "?"))
    if os_window.title:
        label.append("  ")
        label.append(os_window.title, style="bold" if os_window.is_active else "")
    return label


def _tab_label(tab: Tab) -> Text:
    label = Text()
    label.append("● " if tab.is_active else "  ", style="bold" if tab.is_active else "")
    label.append(_display_name(tab.title, "(untitled)"), style="bold" if tab.is_active else "")
    if tab.id:
        label.append(f"  [{tab.id}]", style="dim")
    if tab.layout:
        label.append(f"  {tab.layout}", style="dim")
    return label


def _pane_label(pane: Pane) -> Text:
    label = Text()
    label.append("● " if pane.is_active else "  ", style="bold" if pane.is_active else "")
    label.append(_display_name(pane.title, "(untitled)"), style="bold" if pane.is_active else "")
    label.append(f"  [{pane.id}]", style="dim")
    if pane.cwd:
        label.append(f"  {pane.cwd}", style="dim")
    if pane.foreground_cmd:
        label.append(f"  {pane.foreground_cmd}", style="dim")
    return label


def _os_window_name(os_window: OsWindow) -> str:
    return f"OS {os_window.id or '?'} — {_display_name(os_window.title, '(untitled)')}"


def _tab_name(os_window: OsWindow, tab: Tab) -> str:
    return f"{_os_window_name(os_window)} / {_display_name(tab.title, '(untitled)')} [{tab.id or '?'}]"


def move_destinations(state: KittyState, source: NodeRef) -> tuple[Destination, ...]:
    """Return destinations valid for the selected pane or tab."""
    if source.kind == "pane":
        return _pane_destinations(state, source.id)
    if source.kind == "tab":
        return _tab_destinations(state, source.id)
    return ()


def _pane_destinations(state: KittyState, pane_id: str) -> tuple[Destination, ...]:
    source = state.find_pane(pane_id)
    source_tab_id = source.tab.id if source is not None else None
    destinations = [
        Destination("tab", tab.id, _tab_name(os_window, tab))
        for os_window, tab in state.iter_tabs()
        if tab.id is not None and tab.id != source_tab_id
    ]
    destinations.extend((
        Destination("new_tab", None, "New tab"),
        Destination("new_os_window", None, "New OS window"),
    ))
    return tuple(destinations)


def _tab_destinations(state: KittyState, tab_id: str) -> tuple[Destination, ...]:
    source = state.find_tab(tab_id)
    source_os_id = source[0].id if source is not None else None
    destinations = [
        Destination("os_window", os_window.id, _os_window_name(os_window))
        for os_window in state.os_windows
        if os_window.id is not None and os_window.id != source_os_id
    ]
    destinations.append(Destination("new_os_window", None, "New OS window"))
    return tuple(destinations)


def merge_destinations(state: KittyState, source_os_window_id: str) -> tuple[Destination, ...]:
    """Return OS windows into which the selected OS window may be merged."""
    return tuple(
        Destination("os_window", os_window.id, _os_window_name(os_window))
        for os_window in state.os_windows
        if os_window.id is not None and os_window.id != source_os_window_id
    )


def selected_title(state: KittyState, ref: NodeRef) -> str:
    """Return the current title of a referenced object."""
    if ref.kind == "pane":
        location = state.find_pane(ref.id)
        return location.pane.title if location is not None else ""
    if ref.kind == "tab":
        found = state.find_tab(ref.id)
        if found is None:
            return ""
        return found[1].title or ""
    os_window = state.find_os_window(ref.id)
    if os_window is None:
        return ""
    return os_window.title or ""


def _walk_nodes(node: TreeNode[NodeRef]) -> Iterator[TreeNode[NodeRef]]:
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


class KittyTree(Tree[NodeRef]):
    """Tree with Vim-like navigation."""

    BINDINGS: ClassVar[list[BindingType]] = [
        *Tree.BINDINGS,
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "collapse_or_parent", "Collapse", show=False),
        Binding("l", "expand_or_child", "Expand", show=False),
    ]

    def action_collapse_or_parent(self) -> None:
        node = self.cursor_node
        if node is None:
            return
        if node.allow_expand and node.is_expanded:
            node.collapse()
            return
        if node.parent is not None:
            self.move_cursor(node.parent)

    def action_expand_or_child(self) -> None:
        node = self.cursor_node
        if node is None or not node.children:
            return
        if node.is_collapsed:
            node.expand()
            return
        self.move_cursor(node.children[0])


class VimOptionList(OptionList):
    """Option list with j/k navigation."""

    BINDINGS: ClassVar[list[BindingType]] = [
        *OptionList.BINDINGS,
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]


class RenameScreen(ModalScreen[str | None]):
    """Small modal used to rename the selected object."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel", show=False)]

    CSS = """
    RenameScreen {
        align: center middle;
    }

    RenameScreen > #rename-dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }

    RenameScreen Input {
        margin-top: 1;
    }
    """

    def __init__(self, prompt: str, value: str) -> None:
        super().__init__()
        self._prompt = prompt
        self._value = value

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label(self._prompt),
            Input(value=self._value, id="rename-input"),
            id="rename-dialog",
        )

    def on_mount(self) -> None:
        self.query_one("#rename-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DestinationScreen(ModalScreen[Destination | None]):
    """Modal destination picker."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel", show=False)]

    CSS = """
    DestinationScreen {
        align: center middle;
    }

    DestinationScreen > #destination-dialog {
        width: 84;
        height: auto;
        max-height: 80%;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }

    DestinationScreen OptionList {
        margin-top: 1;
        height: auto;
        max-height: 20;
    }
    """

    def __init__(self, prompt: str, destinations: tuple[Destination, ...]) -> None:
        super().__init__()
        self._prompt = prompt
        self._destinations = {str(index): destination for index, destination in enumerate(destinations)}

    def compose(self) -> ComposeResult:
        options = [
            Option(destination.label, id=option_id)
            for option_id, destination in self._destinations.items()
        ]
        yield Vertical(
            Label(self._prompt),
            VimOptionList(*options, id="destination-list"),
            id="destination-dialog",
        )

    def on_mount(self) -> None:
        option_list = self.query_one("#destination-list", VimOptionList)
        if option_list.option_count:
            option_list.highlighted = 0
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_id is not None:
            self.dismiss(self._destinations[event.option_id])

    def action_cancel(self) -> None:
        self.dismiss(None)


class KittyManagerApp(App[None]):
    """Interactive organizer for a single running Kitty instance."""

    TITLE = "catherd"
    SUB_TITLE = "Kitty organizer"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("r", "rename_selected", "Rename"),
        Binding("m", "move_selected", "Move"),
        Binding("shift+m", "merge_selected", "Merge"),
        Binding("shift+j", "reorder_forward", "Move down"),
        Binding("shift+k", "reorder_backward", "Move up"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    CSS = """
    #kitty-tree {
        height: 1fr;
    }

    #status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    Footer {
        height: 1;
    }
    """

    def __init__(
        self,
        client: KittyBackend | None = None,
        *,
        poll_interval: float | None = 2.0,
    ) -> None:
        super().__init__()
        self.client: KittyBackend = client if client is not None else KittyClient.discover()
        self.poll_interval = poll_interval
        self.state = KittyState(os_windows=())
        self._manager_pane_id = os.environ.get("KITTY_WINDOW_ID")
        self._mutation_active = False

    def compose(self) -> ComposeResult:
        tree: KittyTree = KittyTree("Kitty", id="kitty-tree")
        tree.root.expand()
        yield tree
        yield Static("Loading Kitty state…", id="status")
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_state()
        if self.poll_interval is not None:
            self.set_interval(self.poll_interval, self._poll)

    def _poll(self) -> None:
        if not self._mutation_active:
            self.action_refresh()

    def _tree(self) -> KittyTree:
        return self.query_one("#kitty-tree", KittyTree)

    def _status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _selected_ref(self) -> NodeRef | None:
        node = self._tree().cursor_node
        return node.data if node is not None else None

    def _expanded_refs(self) -> set[NodeRef]:
        expanded: set[NodeRef] = set()
        for node in _walk_nodes(self._tree().root):
            if node.data is not None and node.is_expanded:
                expanded.add(node.data)
        return expanded

    def _initial_ref(self, state: KittyState) -> NodeRef | None:
        for location in state.iter_panes():
            if (
                location.os_window.is_active
                and location.tab.is_active
                and location.pane.is_active
                and location.pane.id
            ):
                return NodeRef("pane", location.pane.id)
        first_pane = next(state.iter_panes(), None)
        if first_pane is not None:
            return NodeRef("pane", first_pane.pane.id)
        first_tab = next(state.iter_tabs(), None)
        if first_tab is not None and first_tab[1].id is not None:
            return NodeRef("tab", first_tab[1].id)
        if state.os_windows and state.os_windows[0].id is not None:
            return NodeRef("os_window", state.os_windows[0].id)
        return None

    def _render_state(
        self,
        state: KittyState,
        *,
        preferred: NodeRef | None,
        expanded: set[NodeRef] | None,
    ) -> None:
        tree = self._tree()
        tree.reset("Kitty")
        tree.root.expand()
        nodes: dict[NodeRef, TreeNode[NodeRef]] = {}
        for os_window in state.os_windows:
            self._add_os_window(tree.root, os_window, nodes, expanded)
        self.state = state
        target = preferred or self._initial_ref(state)
        if target is not None and target in nodes:
            self._reveal_and_select(tree, nodes[target])
        elif tree.root.children:
            tree.move_cursor(tree.root.children[0])

    def _add_os_window(
        self,
        root: TreeNode[NodeRef],
        os_window: OsWindow,
        nodes: dict[NodeRef, TreeNode[NodeRef]],
        expanded: set[NodeRef] | None,
    ) -> None:
        if os_window.id is None:
            return
        ref = NodeRef("os_window", os_window.id)
        node = root.add(_os_window_label(os_window), ref, expand=expanded is None or ref in expanded)
        nodes[ref] = node
        for tab in os_window.tabs:
            self._add_tab(node, tab, nodes, expanded)

    def _add_tab(
        self,
        parent: TreeNode[NodeRef],
        tab: Tab,
        nodes: dict[NodeRef, TreeNode[NodeRef]],
        expanded: set[NodeRef] | None,
    ) -> None:
        if tab.id is None:
            return
        ref = NodeRef("tab", tab.id)
        node = parent.add(_tab_label(tab), ref, expand=expanded is None or ref in expanded)
        nodes[ref] = node
        for pane in tab.panes:
            pane_ref = NodeRef("pane", pane.id)
            nodes[pane_ref] = node.add_leaf(_pane_label(pane), pane_ref)

    @staticmethod
    def _reveal_and_select(tree: KittyTree, node: TreeNode[NodeRef]) -> None:
        parent = node.parent
        while parent is not None:
            parent.expand()
            parent = parent.parent
        tree.move_cursor(node)

    async def refresh_state(self, preferred: NodeRef | None = None) -> None:
        """Reload Kitty state and redraw while preserving navigation state."""
        tree = self._tree()
        selected = preferred or self._selected_ref()
        expanded = self._expanded_refs() if tree.root.children else None
        try:
            state = await asyncio.to_thread(self.client.snapshot)
        except KittyClientError as exc:
            self._status(f"Kitty error: {exc}")
            return
        self._render_state(state, preferred=selected, expanded=expanded)
        self._status(
            f"{len(state.os_windows)} OS windows · "
            f"{sum(1 for _ in state.iter_tabs())} tabs · "
            f"{state.pane_count} panes"
        )

    def action_refresh(self) -> None:
        if self._mutation_active:
            self._status("A Kitty operation is still running")
            return
        self.run_worker(self.refresh_state(), group="kitty-refresh", exclusive=True)

    def on_tree_node_selected(self, event: Tree.NodeSelected[NodeRef]) -> None:
        ref = event.node.data
        if ref is not None:
            self._start_mutation(
                "Focused",
                self._focus_operation(ref),
                preferred=ref,
                restore_manager_focus=False,
            )

    def action_rename_selected(self) -> None:
        ref = self._selected_ref()
        if ref is None:
            return
        prompt = f"Rename {ref.kind.replace('_', ' ')}:"
        self.push_screen(
            RenameScreen(prompt, selected_title(self.state, ref)),
            partial(self._complete_rename, ref),
        )

    def _complete_rename(self, ref: NodeRef, title: str | None) -> None:
        if title is None:
            return
        self._start_mutation("Renamed", self._rename_operation(ref, title), preferred=ref)

    def action_move_selected(self) -> None:
        ref = self._selected_ref()
        if ref is None:
            return
        destinations = move_destinations(self.state, ref)
        if not destinations:
            self._status("Select a pane or tab to move")
            return
        self.push_screen(
            DestinationScreen("Move to:", destinations),
            partial(self._complete_move, ref),
        )

    def _complete_move(self, ref: NodeRef, destination: Destination | None) -> None:
        if destination is None:
            return
        operation = self._move_operation(ref, destination)
        if operation is None:
            self._status("That move is not supported")
            return
        self._start_mutation("Moved", operation, preferred=ref)

    def action_merge_selected(self) -> None:
        ref = self._selected_ref()
        if ref is None or ref.kind != "os_window":
            self._status("Select an OS window to merge")
            return
        destinations = merge_destinations(self.state, ref.id)
        if not destinations:
            self._status("No other OS window is available")
            return
        self.push_screen(
            DestinationScreen("Merge into:", destinations),
            partial(self._complete_merge, ref),
        )

    def _complete_merge(self, source: NodeRef, destination: Destination | None) -> None:
        if destination is None or destination.id is None:
            return
        target = NodeRef("os_window", destination.id)
        operation = partial(self.client.merge_os_windows, source.id, destination.id)
        self._start_mutation("Merged", operation, preferred=target)

    def action_reorder_forward(self) -> None:
        self._reorder_selected("forward")

    def action_reorder_backward(self) -> None:
        self._reorder_selected("backward")

    def _reorder_selected(self, direction: ReorderDirection) -> None:
        ref = self._selected_ref()
        if ref is None:
            return
        operation = self._reorder_operation(ref, direction)
        if operation is None:
            self._status("OS windows cannot be reordered by Kitty")
            return
        self._start_mutation("Reordered", operation, preferred=ref)

    def _focus_operation(self, ref: NodeRef) -> Callable[[], None]:
        if ref.kind == "pane":
            return partial(self.client.focus_pane, ref.id)
        if ref.kind == "tab":
            return partial(self.client.focus_tab, ref.id)
        return partial(self.client.focus_os_window, ref.id)

    def _rename_operation(self, ref: NodeRef, title: str) -> Callable[[], None]:
        if ref.kind == "pane":
            return partial(self.client.rename_pane, ref.id, title)
        if ref.kind == "tab":
            return partial(self.client.rename_tab, ref.id, title)
        return partial(self.client.rename_os_window, ref.id, title)

    def _move_operation(self, ref: NodeRef, destination: Destination) -> Callable[[], None] | None:
        if ref.kind == "pane":
            return self._pane_move_operation(ref.id, destination)
        if ref.kind == "tab":
            return self._tab_move_operation(ref.id, destination)
        return None

    def _pane_move_operation(self, pane_id: str, destination: Destination) -> Callable[[], None] | None:
        if destination.kind == "tab" and destination.id is not None:
            return partial(self.client.move_pane, pane_id, destination.id)
        if destination.kind == "new_tab":
            return partial(self.client.detach_pane_to_new_tab, pane_id)
        if destination.kind == "new_os_window":
            return partial(self.client.detach_pane_to_new_os_window, pane_id)
        return None

    def _tab_move_operation(self, tab_id: str, destination: Destination) -> Callable[[], None] | None:
        if destination.kind == "os_window" and destination.id is not None:
            return partial(self.client.move_tab, tab_id, destination.id)
        if destination.kind == "new_os_window":
            return partial(self.client.detach_tab_to_new_os_window, tab_id)
        return None

    def _reorder_operation(
        self,
        ref: NodeRef,
        direction: ReorderDirection,
    ) -> Callable[[], None] | None:
        if ref.kind == "pane":
            return partial(self.client.reorder_pane, ref.id, direction)
        if ref.kind == "tab":
            return partial(self.client.reorder_tab, ref.id, direction)
        return None

    def _start_mutation(
        self,
        success_message: str,
        operation: Callable[[], None],
        *,
        preferred: NodeRef,
        restore_manager_focus: bool = True,
    ) -> None:
        if self._mutation_active:
            self._status("Another Kitty operation is still running")
            return
        self._mutation_active = True
        self.run_worker(
            self._run_mutation(
                success_message,
                operation,
                preferred,
                restore_manager_focus=restore_manager_focus,
            ),
            group="kitty-mutation",
            exclusive=True,
        )

    async def _run_mutation(
        self,
        success_message: str,
        operation: Callable[[], None],
        preferred: NodeRef,
        *,
        restore_manager_focus: bool,
    ) -> None:
        try:
            await asyncio.to_thread(operation)
            if restore_manager_focus and self._manager_pane_id is not None:
                await asyncio.to_thread(self.client.focus_pane, self._manager_pane_id)
            await self.refresh_state(preferred)
        except KittyClientError as exc:
            self._status(f"Kitty error: {exc}")
        else:
            self._status(success_message)
        finally:
            self._mutation_active = False


def run_tui() -> None:
    """Run the interactive Kitty organizer."""
    KittyManagerApp().run()
