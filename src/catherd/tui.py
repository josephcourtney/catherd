"""Interactive Kitty organizer."""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess  # noqa: S404 -- fixed macOS system appearance query
import sys
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Literal, Protocol

from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.strip import Strip
from textual.widgets import Input, Label, OptionList, Static, Tree
from textual.widgets.option_list import Option

from .activity import PaneActivity, get_pane_activity
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

    def merge_tabs(self, source_tab_id: str, target_tab_id: str) -> None: ...

    def merge_os_windows(self, source_os_window_id: str, target_os_window_id: str) -> None: ...


def _display_name(value: str | None, fallback: str) -> str:
    return value or fallback


_TREE_HINT_MAX = 36
_TREE_NAME_WIDTH = 24

_STYLE_ACTIVE_MARKER = "bold green"
_STYLE_ACTIVE_BRANCH = "cyan"
_STYLE_KIND = "italic cyan"
_STYLE_METADATA = "cyan"
_STYLE_DESCRIPTOR = "italic cyan"
_STYLE_DETAIL_LABEL = "italic cyan"
_STYLE_SECTION_RULE = "cyan"
_STYLE_BREADCRUMB = "italic cyan"


def _active_marker(*, active: bool | None) -> str:
    return "● " if active else "  "


def _tab_band_background(*, dark: bool) -> str:
    return "bright_black" if dark else "bright_white"


def _apply_tab_band(strip: Strip, *, dark: bool) -> Strip:
    style = Style(bgcolor=_tab_band_background(dark=dark))
    return Strip(
        Segment.apply_style(strip, post_style=style),
        strip.cell_length,
    )


def _compact_hint(value: str | None, max_len: int = _TREE_HINT_MAX) -> str | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    if len(normalized) <= max_len:
        return normalized
    return normalized[: max_len - 3].rstrip() + "..."


def _compact_tokens(parts: list[str], max_len: int = _TREE_HINT_MAX) -> str | None:
    if not parts:
        return None
    full = " ".join(parts)
    if len(full) <= max_len:
        return full
    suffix = " ..."
    kept: list[str] = []
    for part in parts:
        candidate = " ".join((*kept, part))
        if len(candidate) + len(suffix) > max_len:
            break
        kept.append(part)
    if kept:
        return " ".join(kept) + suffix
    return _compact_hint(parts[0], max_len=max_len)


def _compact_process_hint(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parts = shlex.split(value)
    except ValueError:
        return _compact_hint(value)
    compact = [os.path.basename(part) if part.startswith("/") else part for part in parts]
    return _compact_tokens(compact)


def _pane_activity_hint(pane: Pane) -> str | None:
    if pane.current_command:
        return _compact_hint(pane.current_command)
    foreground = pane.foreground_cmd
    if foreground and "pty-proxy" in foreground and "--shell" in foreground:
        return None
    return _compact_process_hint(foreground)


def _preferred_textual_theme() -> str | None:
    override = os.environ.get("CATHERD_THEME")
    aliases = {
        "textual-light": "ansi-light",
        "textual-dark": "ansi-dark",
        "ansi-light": "ansi-light",
        "ansi-dark": "ansi-dark",
    }
    if override in aliases:
        return aliases[override]
    if sys.platform == "darwin":
        try:
            result = subprocess.run(  # noqa: S603 -- fixed macOS system command and arguments
                ["/usr/bin/defaults", "read", "-g", "AppleInterfaceStyle"],
                check=False,
                capture_output=True,
                text=True,
                timeout=0.5,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        else:
            return "ansi-dark" if result.stdout.strip().casefold() == "dark" else "ansi-light"
    colorfgbg = os.environ.get("COLORFGBG")
    if colorfgbg:
        background = colorfgbg.rsplit(";", 1)[-1]
        if background == "0":
            return "ansi-dark"
        if background in {"7", "15"}:
            return "ansi-light"
    return None


def _fit_tree_column(value: str, width: int = _TREE_NAME_WIDTH) -> str:
    if len(value) > width:
        value = value[: width - 1].rstrip() + "…"
    return f"{value:<{width}}"


def _same_identity(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return left.strip().casefold() == right.strip().casefold()


def _pane_row_title(pane: Pane, tab_title: str | None, display_title: str | None = None) -> str:
    title = display_title if display_title is not None else pane.title
    if title and not _same_identity(title, tab_title):
        return title

    for candidate in (pane.root_cmdline, pane.foreground_cmd):
        compact = _compact_process_hint(candidate)
        if compact and not _same_identity(compact, tab_title):
            return compact

    if pane.current_command and not _same_identity(pane.current_command, tab_title):
        return _compact_hint(pane.current_command) or pane.current_command
    return _display_name(title, "(untitled)")


def _os_window_label(os_window: OsWindow, display_title: str | None = None) -> Text:
    label = Text()
    label.append("OS ", style=_STYLE_KIND)
    label.append(_display_name(os_window.id, "?"), style="bold")
    title = display_title if display_title is not None else os_window.title
    if title:
        label.append("  ")
        label.append(title, style="bold")
    pane_count = sum(len(tab.panes) for tab in os_window.tabs)
    label.append(
        f"  {len(os_window.tabs)} tabs · {pane_count} panes",
        style=_STYLE_METADATA,
    )
    return label


def _tab_label(tab: Tab, display_title: str | None = None) -> Text:
    label = Text()
    title = _display_name(display_title if display_title is not None else tab.title, "(untitled)")
    label.append(_fit_tree_column(title), style="bold")
    if tab.id:
        label.append(f"  #{tab.id:<4}", style=_STYLE_METADATA)
    if tab.layout:
        label.append(f" {tab.layout}", style=_STYLE_DESCRIPTOR)
    return label


def _pane_label(
    pane: Pane,
    tab_title: str | None = None,
    display_title: str | None = None,
) -> Text:
    label = Text()
    label.append(
        _active_marker(active=pane.is_active),
        style=_STYLE_ACTIVE_MARKER if pane.is_active else "",
    )
    title = _pane_row_title(pane, tab_title, display_title)
    label.append(_fit_tree_column(title), style="bold" if pane.is_active else "")
    label.append(f"  #{pane.id:<4}", style=_STYLE_METADATA)
    hint = _pane_activity_hint(pane)
    if hint and not _same_identity(hint, title):
        label.append(f" {hint}", style=_STYLE_DESCRIPTOR)
    return label


def _matches_query(query: str, *values: object | None) -> bool:
    needle = query.casefold()
    return any(value is not None and needle in str(value).casefold() for value in values)


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
    destinations.extend((Destination("new_tab", None, "New tab"), Destination("new_os_window", None, "New OS window")))
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


def merge_os_window_destinations(state: KittyState, source_os_window_id: str) -> tuple[Destination, ...]:
    """Return OS windows into which the selected OS window may be merged."""
    return tuple(
        Destination("os_window", os_window.id, _os_window_name(os_window))
        for os_window in state.os_windows
        if os_window.id is not None and os_window.id != source_os_window_id
    )


def merge_tab_destinations(state: KittyState, source_tab_id: str) -> tuple[Destination, ...]:
    """Return tabs into which the selected tab may be merged."""
    return tuple(
        Destination("tab", tab.id, _tab_name(os_window, tab))
        for os_window, tab in state.iter_tabs()
        if tab.id is not None and tab.id != source_tab_id
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


def _detail_value(value: object | None) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _append_section(details: Text, title: str) -> None:
    details.append("\n")
    label = title.upper()
    details.append(label, style="bold")
    details.append(" ")
    details.append("─" * max(2, 32 - len(label)), style=_STYLE_SECTION_RULE)
    details.append("\n")


def _append_detail(details: Text, label: str, value: object | None) -> None:
    if value is None or value == "":
        return
    details.append(f"{label:<16}", style=_STYLE_DETAIL_LABEL)
    details.append(_detail_value(value))
    details.append("\n")


def _append_identity(
    details: Text,
    kind: str,
    title: str,
    object_id: str | None,
    breadcrumb: str | None = None,
) -> None:
    details.append(kind.upper(), style=_STYLE_KIND)
    details.append("\n")
    details.append(_display_name(title, "(untitled)"), style="bold")
    if object_id:
        details.append(f"  [{object_id}]", style=_STYLE_METADATA)
    details.append("\n")
    if breadcrumb:
        details.append(breadcrumb, style=_STYLE_BREADCRUMB)
        details.append("\n")


def _pane_position(pane: Pane) -> str | None:
    if pane.tab_index is None or pane.tab_count is None:
        return None
    return f"{pane.tab_index} of {pane.tab_count}"


def _pane_neighbors(pane: Pane) -> str | None:
    items = (
        ("L", pane.neighbors_left),
        ("T", pane.neighbors_top),
        ("R", pane.neighbors_right),
        ("B", pane.neighbors_bottom),
    )
    parts = [f"{label}:{','.join(ids)}" for label, ids in items if ids]
    return "  ".join(parts) or None


def _prompt_state(pane: Pane) -> str | None:
    if pane.at_prompt is True:
        return "at prompt"
    if pane.at_prompt is False:
        return "command running"
    return None


def _os_window_details(
    state: KittyState,
    ref: NodeRef,
    *,
    display_title: str | None,
) -> Text:
    os_window = state.find_os_window(ref.id)
    if os_window is None:
        return Text("OS window no longer exists", style="dim")
    details = Text()
    title = display_title if display_title is not None else os_window.title
    _append_identity(details, "OS window", _display_name(title, f"OS {os_window.id or '?'}"), os_window.id)
    _append_section(details, "Contents")
    _append_detail(details, "Tabs", len(os_window.tabs))
    _append_detail(details, "Panes", sum(len(tab.panes) for tab in os_window.tabs))
    if os_window.is_active:
        _append_section(details, "State")
        _append_detail(details, "Kitty active", "yes")
    return details


def _tab_details(
    state: KittyState,
    ref: NodeRef,
    *,
    display_title: str | None,
) -> Text:
    found = state.find_tab(ref.id)
    if found is None:
        return Text("Tab no longer exists", style="dim")
    os_window, tab = found
    details = Text()
    title = display_title if display_title is not None else tab.title
    breadcrumb = f"OS {os_window.id or '?'}"
    _append_identity(details, "Tab", _display_name(title, "(untitled)"), tab.id, breadcrumb)
    _append_section(details, "Contents")
    _append_detail(details, "Layout", tab.layout)
    _append_detail(details, "Panes", len(tab.panes))
    if tab.is_active:
        _append_section(details, "State")
        _append_detail(details, "Kitty active", "yes")
    return details


def _append_pane_location(details: Text, pane: Pane) -> None:
    _append_section(details, "Location")
    _append_detail(details, "CWD", pane.cwd)
    _append_detail(details, "Position", _pane_position(pane))
    size = (
        f"{pane.cols}×{pane.rows}"  # ruff: ignore[ambiguous-unicode-character-string]
        if pane.cols is not None and pane.rows is not None
        else None
    )
    _append_detail(details, "Size", size)
    _append_detail(details, "Neighbors", _pane_neighbors(pane))


def _append_pane_process(details: Text, pane: Pane) -> None:
    _append_section(details, "Process")
    _append_detail(details, "Current", pane.current_command)
    _append_detail(details, "Foreground", pane.foreground_cmd)
    _append_detail(details, "PID", pane.pid)
    _append_detail(details, "Root", pane.root_cmdline)


def _pane_state_items(pane: Pane) -> tuple[tuple[str, object], ...]:
    items: list[tuple[str, object]] = []
    prompt = _prompt_state(pane)
    if prompt is not None:
        items.append(("Prompt", prompt))
    if pane.is_active:
        items.append(("Kitty active", "yes"))
    if pane.title_overridden:
        items.append(("Title locked", "yes"))
    if pane.needs_attention:
        items.append(("Attention", "yes"))
    if pane.has_activity_since_last_focus:
        items.append(("Activity", "since focus"))
    return tuple(items)


def _append_pane_state(details: Text, pane: Pane) -> None:
    items = _pane_state_items(pane)
    if not items:
        return
    _append_section(details, "State")
    for label, value in items:
        _append_detail(details, label, value)


def _append_atuin(
    details: Text,
    *,
    activity: PaneActivity | None,
    activity_loading: bool,
) -> None:
    if activity_loading:
        _append_section(details, "Atuin")
        _append_detail(details, "Session", "loading...")
        _append_detail(details, "Last completed", "loading...")
        return
    if activity is None or (activity.session_id is None and activity.last_command is None):
        return
    _append_section(details, "Atuin")
    _append_detail(details, "Session", activity.session_id)
    _append_detail(details, "Last completed", activity.last_command)


def _pane_details(
    state: KittyState,
    ref: NodeRef,
    *,
    activity: PaneActivity | None,
    activity_loading: bool,
    display_title: str | None,
) -> Text:
    location = state.find_pane(ref.id)
    if location is None:
        return Text("Pane no longer exists", style="dim")
    pane = location.pane
    details = Text()
    title = display_title if display_title is not None else pane.title
    tab_title = _display_name(location.tab.title, "(untitled)")
    breadcrumb = f"OS {location.os_window.id or '?'} > {tab_title} [{location.tab.id or '?'}]"
    _append_identity(details, "Pane", _display_name(title, "(untitled)"), pane.id, breadcrumb)
    _append_pane_location(details, pane)
    _append_pane_process(details, pane)
    _append_pane_state(details, pane)
    _append_atuin(details, activity=activity, activity_loading=activity_loading)
    return details


def selected_details(
    state: KittyState,
    ref: NodeRef,
    *,
    activity: PaneActivity | None = None,
    activity_loading: bool = False,
    display_title: str | None = None,
) -> Text:
    """Render a compact, grouped inspector for an object in the current Kitty snapshot."""
    if ref.kind == "os_window":
        return _os_window_details(state, ref, display_title=display_title)
    if ref.kind == "tab":
        return _tab_details(state, ref, display_title=display_title)
    return _pane_details(
        state,
        ref,
        activity=activity,
        activity_loading=activity_loading,
        display_title=display_title,
    )

def containing_os_window_id(state: KittyState, ref: NodeRef) -> str | None:
    """Return the OS window containing a referenced tree object."""
    if ref.kind == "os_window":
        return ref.id if state.find_os_window(ref.id) is not None else None
    if ref.kind == "tab":
        found = state.find_tab(ref.id)
        return found[0].id if found is not None else None
    location = state.find_pane(ref.id)
    return location.os_window.id if location is not None else None


def _walk_nodes(node: TreeNode[NodeRef]) -> Iterator[TreeNode[NodeRef]]:
    yield node
    for child in node.children:
        yield from _walk_nodes(child)


class KittyTree(Tree[NodeRef]):
    """Tree with Vim-like navigation and lightweight group banding."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter,f,F", "focus_kitty", "Focus"),
        *Tree.BINDINGS,
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "collapse_or_parent", "Collapse", show=False),
        Binding("l", "expand_or_child", "Expand", show=False),
    ]

    def clear_bands(self) -> None:
        self._banded_refs: set[NodeRef] = set()

    def set_banded(self, ref: NodeRef, *, banded: bool) -> None:
        banded_refs = getattr(self, "_banded_refs", set())
        if banded:
            banded_refs.add(ref)
        else:
            banded_refs.discard(ref)
        self._banded_refs = banded_refs

    def _selectable_line(self, start: int, step: int) -> int | None:
        line = start
        while 0 <= line <= self.last_line:
            node = self.get_node_at_line(line)
            if node is not None and node.data is not None:
                return line
            line += step
        return None

    def action_cursor_up(self) -> None:
        start = self.last_line if self.cursor_line == -1 else self.cursor_line - 1
        line = self._selectable_line(start, -1)
        if line is not None:
            self.move_cursor_to_line(line)

    def action_cursor_down(self) -> None:
        start = 0 if self.cursor_line == -1 else self.cursor_line + 1
        line = self._selectable_line(start, 1)
        if line is not None:
            self.move_cursor_to_line(line)

    def action_select_cursor(self) -> None:
        node = self.cursor_node
        if node is None or node.data is None:
            return
        super().action_select_cursor()

    def _render_spacer_line(self, node: TreeNode[NodeRef]) -> Strip:
        guide_style = self.get_component_rich_style("tree--guides", partial=True)
        guides_hidden = self.get_component_styles("tree--guides").color.a == 0

        if self.show_guides and not guides_hidden:
            lines = self.LINES["default"]
            if guide_style.bold:
                lines = self.LINES["bold"]
            elif guide_style.underline2:
                lines = self.LINES["double"]
            guide_depth = max(0, self.guide_depth - 2)

            def guide_text(characters: str) -> str:
                return f"{characters[0]}{characters[1] * guide_depth} "

            space = guide_text(lines[0])
            vertical = guide_text(lines[1])
        else:
            space = vertical = " " * self.guide_depth

        ancestors: list[TreeNode[NodeRef]] = []
        ancestor = node.parent
        while ancestor is not None and ancestor is not self.root:
            ancestors.append(ancestor)
            ancestor = ancestor.parent
        ancestors.reverse()

        guides = Text()
        for ancestor in ancestors:
            guides.append(space if ancestor.is_last else vertical, style=guide_style)
        guides.append(vertical, style=guide_style)

        strip = Strip(list(guides.render(self.app.console)))
        strip = strip.extend_cell_length(self.size.width, self.rich_style)
        scroll_x = self.scroll_offset.x
        return strip.crop(scroll_x, scroll_x + self.size.width)

    def render_line(self, y: int) -> Strip:
        absolute_line = y + self.scroll_offset.y
        node = self.get_node_at_line(absolute_line)
        if node is not None and node is not self.root and node.data is None:
            return self._render_spacer_line(node)

        strip = super().render_line(y)
        if (
            node is None
            or node.data not in getattr(self, "_banded_refs", set())
            or absolute_line == self.cursor_line
            or absolute_line == self.hover_line
        ):
            return strip

        return _apply_tab_band(strip, dark=self.app.current_theme.dark)

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
        child = next((candidate for candidate in node.children if candidate.data is not None), None)
        if child is not None:
            self.move_cursor(child)

    async def action_focus_kitty(self) -> None:
        await self.app.run_action("focus_selected")


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


class FilterScreen(ModalScreen[str | None]):
    """Modal tree filter."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "Cancel", show=False)]

    CSS = """
    FilterScreen {
        align: center middle;
    }

    FilterScreen > #filter-dialog {
        width: 64;
        height: auto;
        padding: 1 2;
        border: round $primary;
        background: $surface;
    }

    FilterScreen Input {
        margin-top: 1;
    }
    """

    def __init__(self, value: str) -> None:
        super().__init__()
        self._value = value

    def compose(self) -> ComposeResult:
        yield Vertical(
            Label("Filter tree:"),
            Input(value=self._value, placeholder="title, id, path, or command", id="filter-input"),
            id="filter-dialog",
        )

    def on_mount(self) -> None:
        input_widget = self.query_one("#filter-input", Input)
        input_widget.focus()
        input_widget.action_end()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

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
        options = [Option(destination.label, id=option_id) for option_id, destination in self._destinations.items()]
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
    TREE_LABEL: ClassVar[str] = "Kitty"

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("q", "quit", "Quit"),
        Binding("escape", "clear_filter", "Clear filter", show=False),
        Binding("/", "filter_tree", "Filter"),
        Binding("a", "jump_active", "Active"),
        Binding("r", "rename_selected", "Rename"),
        Binding("m", "move_selected", "Move"),
        Binding("M,shift+m", "merge_selected", "Merge"),
        Binding("J,shift+j", "reorder_forward", "Move down"),
        Binding("K,shift+k", "reorder_backward", "Move up"),
        Binding("ctrl+r", "refresh", "Refresh"),
    ]

    CSS = """
    #main {
        height: 1fr;
    }

    #kitty-tree {
        width: 1fr;
        min-width: 30;
    }

    #details {
        width: 48;
        min-width: 38;
        max-width: 54;
        padding: 1 2;
        border-left: solid $border-blurred;
        overflow-y: auto;
    }

    #status {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }

    #actions {
        height: 1;
        padding: 0 1;
        color: $text-muted;
    }
    """

    def __init__(
        self,
        client: KittyBackend | None = None,
        *,
        poll_interval: float | None = 2.0,
        activity_provider: Callable[[str], PaneActivity] | None = None,
        theme_name: str | None = None,
    ) -> None:
        super().__init__()
        if theme_name is not None:
            self.theme = theme_name
        self.client: KittyBackend = client if client is not None else KittyClient.discover()
        self.poll_interval = poll_interval
        self._activity_provider = activity_provider if activity_provider is not None else get_pane_activity
        self.state = KittyState(os_windows=())
        self._display_names: dict[NodeRef, str] = {}
        self._logical_selection: NodeRef | None = None
        self._filter_query = ""
        self._manager_pane_id = os.environ.get("KITTY_WINDOW_ID")
        self._mutation_active = False

    def compose(self) -> ComposeResult:
        tree: KittyTree = KittyTree(self.TREE_LABEL, id="kitty-tree")
        tree.auto_expand = False
        tree.root.expand()
        yield Horizontal(
            tree,
            Static("Select an OS window, tab, or pane", id="details"),
            id="main",
        )
        yield Static("Loading Kitty state…", id="status")
        yield Static(
            "Enter Focus  r Rename  m Move  M Merge  J/K Reorder  / Filter  a Active  ^R Refresh  q Quit",
            id="actions",
        )

    async def on_mount(self) -> None:
        await self.refresh_state()
        self._tree().focus()
        if self.poll_interval is not None:
            self.set_interval(self.poll_interval, self._poll)

    def _poll(self) -> None:
        if not self._mutation_active:
            self.action_refresh()

    def _tree(self) -> KittyTree:
        return self.query_one("#kitty-tree", KittyTree)

    def _status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def _details(self) -> Static:
        return self.query_one("#details", Static)

    def _show_details(self, ref: NodeRef | None) -> None:
        if ref is None:
            self._details().update("Select an OS window, tab, or pane")
            return
        if ref.kind != "pane":
            self._details().update(selected_details(self.state, ref, display_title=self._display_names.get(ref)))
            return
        self._details().update(
            selected_details(
                self.state,
                ref,
                activity_loading=True,
                display_title=self._display_names.get(ref),
            )
        )
        self.run_worker(
            self._load_pane_activity(ref),
            group="pane-details",
            exclusive=True,
        )

    async def _load_pane_activity(self, ref: NodeRef) -> None:
        try:
            activity = await asyncio.to_thread(self._activity_provider, ref.id)
        except OSError as exc:
            if self._selected_ref() == ref:
                self._details().update(selected_details(self.state, ref, display_title=self._display_names.get(ref)))
                self._status(f"Activity lookup failed: {exc}")
            return
        if self._selected_ref() == ref:
            self._details().update(
                selected_details(
                    self.state,
                    ref,
                    activity=activity,
                    display_title=self._display_names.get(ref),
                )
            )

    def _selected_ref(self) -> NodeRef | None:
        node = self._tree().cursor_node
        if node is not None and node.data is not None:
            return node.data
        return self._logical_selection

    def _selected_title(self, ref: NodeRef) -> str:
        return self._display_names.get(ref, selected_title(self.state, ref))

    def _record_display_name(self, ref: NodeRef, title: str) -> None:
        if title:
            self._display_names[ref] = title
        else:
            self._display_names.pop(ref, None)
        self._update_node_label(ref)
        self._show_details(ref)

    def _update_node_label(self, ref: NodeRef) -> None:
        node = next((item for item in _walk_nodes(self._tree().root) if item.data == ref), None)
        if node is None:
            return
        display_title = self._display_names.get(ref)
        if ref.kind == "os_window":
            os_window = self.state.find_os_window(ref.id)
            if os_window is not None:
                node.set_label(_os_window_label(os_window, display_title))
            return
        if ref.kind == "tab":
            found = self.state.find_tab(ref.id)
            if found is not None:
                node.set_label(_tab_label(found[1], display_title))
            return
        location = self.state.find_pane(ref.id)
        if location is not None:
            node.set_label(_pane_label(location.pane, display_title))

    def _expanded_refs(self) -> set[NodeRef]:
        expanded: set[NodeRef] = set()
        for node in _walk_nodes(self._tree().root):
            if node.data is not None and node.is_expanded:
                expanded.add(node.data)
        return expanded

    def _pane_matches_filter(self, pane: Pane) -> bool:
        ref = NodeRef("pane", pane.id)
        return _matches_query(
            self._filter_query,
            self._display_names.get(ref),
            pane.title,
            pane.id,
            pane.cwd,
            pane.current_command,
            pane.foreground_cmd,
            pane.root_cmdline,
        )

    def _tab_own_matches_filter(self, tab: Tab) -> bool:
        ref = NodeRef("tab", tab.id or "")
        return _matches_query(
            self._filter_query,
            self._display_names.get(ref),
            tab.title,
            tab.id,
            tab.layout,
        )

    def _tab_matches_filter(self, tab: Tab) -> bool:
        return self._tab_own_matches_filter(tab) or any(self._pane_matches_filter(pane) for pane in tab.panes)

    def _os_window_own_matches_filter(self, os_window: OsWindow) -> bool:
        ref = NodeRef("os_window", os_window.id or "")
        return _matches_query(
            self._filter_query,
            self._display_names.get(ref),
            os_window.id,
            os_window.title,
        )

    def _os_window_matches_filter(self, os_window: OsWindow) -> bool:
        return self._os_window_own_matches_filter(os_window) or any(
            self._tab_matches_filter(tab) for tab in os_window.tabs
        )

    @staticmethod
    def _first_visible_ref(nodes: dict[NodeRef, TreeNode[NodeRef]]) -> NodeRef | None:
        for kind in ("pane", "tab", "os_window"):
            for ref in nodes:
                if ref.kind == kind:
                    return ref
        return None

    @staticmethod
    def _initial_ref(state: KittyState) -> NodeRef | None:
        for location in state.iter_panes():
            if location.os_window.is_active and location.tab.is_active and location.pane.is_active and location.pane.id:
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
        tree.clear_bands()
        tree.root.expand()
        nodes: dict[NodeRef, TreeNode[NodeRef]] = {}
        visible_windows = [
            os_window
            for os_window in state.os_windows
            if not self._filter_query or self._os_window_matches_filter(os_window)
        ]
        for index, os_window in enumerate(visible_windows):
            if index:
                tree.root.add_leaf(" ", None)
            self._add_os_window(tree.root, os_window, nodes, expanded)
        self.state = state
        target = preferred or self._logical_selection or self._initial_ref(state)
        if target is not None and target in nodes:
            self._logical_selection = target
            self._schedule_cursor_restore(tree, nodes[target])
            return
        fallback = self._initial_ref(state)
        if fallback is None or fallback not in nodes:
            fallback = self._first_visible_ref(nodes)
        self._logical_selection = fallback
        if fallback is not None and fallback in nodes:
            self._schedule_cursor_restore(tree, nodes[fallback])
        elif tree.root.children:
            self._schedule_cursor_restore(tree, tree.root.children[0])
        else:
            self._details().update("No matching Kitty objects")

    def _add_os_window(
        self,
        root: TreeNode[NodeRef],
        os_window: OsWindow,
        nodes: dict[NodeRef, TreeNode[NodeRef]],
        expanded: set[NodeRef] | None,
    ) -> None:
        if os_window.id is None:
            return
        if self._filter_query and not self._os_window_matches_filter(os_window):
            return
        ref = NodeRef("os_window", os_window.id)
        reveal_all = bool(self._filter_query and self._os_window_own_matches_filter(os_window))
        node = root.add(
            _os_window_label(os_window, self._display_names.get(ref)),
            ref,
            expand=bool(self._filter_query) or expanded is None or ref in expanded,
        )
        nodes[ref] = node
        visible_tabs = [
            tab
            for tab in os_window.tabs
            if reveal_all or not self._filter_query or self._tab_matches_filter(tab)
        ]
        for index, tab in enumerate(visible_tabs):
            if index:
                node.add_leaf(" ", None)
            self._add_tab(
                node,
                tab,
                nodes,
                expanded,
                reveal_all=reveal_all,
                banded=bool(index % 2),
            )

    def _add_tab(
        self,
        parent: TreeNode[NodeRef],
        tab: Tab,
        nodes: dict[NodeRef, TreeNode[NodeRef]],
        expanded: set[NodeRef] | None,
        *,
        reveal_all: bool = False,
        banded: bool = False,
    ) -> None:
        if tab.id is None:
            return
        if self._filter_query and not reveal_all and not self._tab_matches_filter(tab):
            return
        ref = NodeRef("tab", tab.id)
        reveal_panes = reveal_all or bool(self._filter_query and self._tab_own_matches_filter(tab))
        node = parent.add(
            _tab_label(tab, self._display_names.get(ref)),
            ref,
            expand=bool(self._filter_query) or expanded is None or ref in expanded,
        )
        nodes[ref] = node
        tree = self._tree()
        tree.set_banded(ref, banded=banded)
        for pane in tab.panes:
            if self._filter_query and not reveal_panes and not self._pane_matches_filter(pane):
                continue
            pane_ref = NodeRef("pane", pane.id)
            nodes[pane_ref] = node.add_leaf(
                _pane_label(pane, self._display_names.get(pane_ref)),
                pane_ref,
            )
            tree.set_banded(pane_ref, banded=banded)

    def _schedule_cursor_restore(self, tree: KittyTree, node: TreeNode[NodeRef]) -> None:
        parent = node.parent
        while parent is not None:
            if parent.is_collapsed:
                parent.expand()
            parent = parent.parent
        ref = node.data
        tree.call_after_refresh(self._restore_cursor_if_current, tree, node, ref)

    def _restore_cursor_if_current(
        self,
        tree: KittyTree,
        node: TreeNode[NodeRef],
        ref: NodeRef | None,
    ) -> None:
        if ref is not None and self._logical_selection == ref:
            tree.move_cursor(node, animate=False)

    async def refresh_state(self, preferred: NodeRef | None = None) -> None:
        """Reload Kitty state and redraw while preserving navigation state."""
        tree = self._tree()
        try:
            state = await asyncio.to_thread(self.client.snapshot)
        except KittyClientError as exc:
            self._status(f"Kitty error: {exc}")
            return
        if self._mutation_active and preferred is None:
            return
        selected = preferred or self._logical_selection or self._selected_ref()
        expanded = self._expanded_refs() if tree.root.children else None
        self._render_state(state, preferred=selected, expanded=expanded)
        summary = (
            f"{len(state.os_windows)} OS windows · {sum(1 for _ in state.iter_tabs())} tabs · {state.pane_count} panes"
        )
        if self._filter_query:
            summary += f" · filter: {self._filter_query}"
        self._status(summary)

    def action_refresh(self) -> None:
        if self._mutation_active:
            self._status("A Kitty operation is still running")
            return
        self.run_worker(self.refresh_state(), group="kitty-refresh", exclusive=True)

    def action_filter_tree(self) -> None:
        self.push_screen(FilterScreen(self._filter_query), self._complete_filter)

    def action_clear_filter(self) -> None:
        if not self._filter_query:
            return
        self._filter_query = ""
        self._render_state(
            self.state,
            preferred=self._selected_ref(),
            expanded=self._expanded_refs(),
        )
        self._status("Filter cleared")

    def _complete_filter(self, query: str | None) -> None:
        if query is None:
            return
        self._filter_query = query
        self._render_state(
            self.state,
            preferred=self._selected_ref(),
            expanded=self._expanded_refs(),
        )
        if query:
            self._status(f"Filter: {query}")
        else:
            self._status("Filter cleared")

    def action_jump_active(self) -> None:
        active = self._initial_ref(self.state)
        if active is None:
            self._status("No active Kitty object")
            return
        self._filter_query = ""
        self._render_state(
            self.state,
            preferred=active,
            expanded=self._expanded_refs(),
        )
        self._status("Selected active Kitty pane")

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[NodeRef]) -> None:
        if event.node.data is not None:
            self._logical_selection = event.node.data
        self._show_details(event.node.data)

    def on_tree_node_selected(self, event: Tree.NodeSelected[NodeRef]) -> None:
        """Treat mouse/Tree selection as selection inside catherd only."""
        if event.node.data is not None:
            self._logical_selection = event.node.data

    def action_focus_selected(self) -> None:
        ref = self._selected_ref()
        if ref is None:
            return
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
            RenameScreen(prompt, self._selected_title(ref)),
            partial(self._complete_rename, ref),
        )

    def _complete_rename(self, ref: NodeRef, title: str | None) -> None:
        if title is None:
            return
        self._start_mutation(
            "Renamed",
            self._rename_operation(ref, title),
            preferred=ref,
            restore_manager_focus=False,
            on_success=partial(self._record_display_name, ref, title),
        )

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
        if ref is None:
            return
        if ref.kind == "pane":
            self._status("Panes are moved, not merged; use m")
            return
        if ref.kind == "tab":
            destinations = merge_tab_destinations(self.state, ref.id)
            prompt = "Merge tab into:"
        else:
            destinations = merge_os_window_destinations(self.state, ref.id)
            prompt = "Merge OS window into:"
        if not destinations:
            self._status("No compatible merge destination is available")
            return
        self.push_screen(
            DestinationScreen(prompt, destinations),
            partial(self._complete_merge, ref),
        )

    def _complete_merge(self, source: NodeRef, destination: Destination | None) -> None:
        if destination is None or destination.id is None:
            return
        if source.kind == "tab" and destination.kind == "tab":
            target = NodeRef("tab", destination.id)
            operation = partial(self.client.merge_tabs, source.id, destination.id)
        elif source.kind == "os_window" and destination.kind == "os_window":
            target = NodeRef("os_window", destination.id)
            operation = partial(self.client.merge_os_windows, source.id, destination.id)
        else:
            self._status("That merge is not supported")
            return
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
        on_success: Callable[[], None] | None = None,
    ) -> None:
        if self._mutation_active:
            self._status("Another Kitty operation is still running")
            return
        self._logical_selection = preferred
        self._mutation_active = True
        self.run_worker(
            self._run_mutation(
                success_message,
                operation,
                preferred,
                restore_manager_focus=restore_manager_focus,
                on_success=on_success,
            ),
            group="kitty-mutation",
            exclusive=True,
        )

    async def _perform_mutation(
        self,
        operation: Callable[[], None],
        preferred: NodeRef,
        *,
        restore_manager_focus: bool,
        on_success: Callable[[], None] | None,
    ) -> None:
        await asyncio.to_thread(operation)
        if on_success is not None:
            on_success()
        if restore_manager_focus and self._manager_pane_id is not None:
            await asyncio.to_thread(self.client.focus_pane, self._manager_pane_id)
        await self.refresh_state(preferred)

    async def _run_mutation(
        self,
        success_message: str,
        operation: Callable[[], None],
        preferred: NodeRef,
        *,
        restore_manager_focus: bool,
        on_success: Callable[[], None] | None,
    ) -> None:
        try:
            await self._perform_mutation(
                operation,
                preferred,
                restore_manager_focus=restore_manager_focus,
                on_success=on_success,
            )
        except KittyClientError as exc:
            self._status(f"Kitty error: {exc}")
        else:
            self._status(success_message)
        finally:
            self._mutation_active = False


def run_tui() -> None:
    """Run the interactive Kitty organizer."""
    KittyManagerApp(theme_name=_preferred_textual_theme()).run()
