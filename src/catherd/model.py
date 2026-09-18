"""Canonical in-memory model of a running Kitty instance."""

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Pane:
    """A Kitty window (called a pane in catherd's user-facing terminology)."""

    id: str
    title: str
    is_active: bool | None = None
    pid: int | None = None
    cwd: str | None = None
    foreground_cmd: str | None = None
    tty: str | None = None
    cols: int | None = None
    rows: int | None = None
    x: int | None = None
    y: int | None = None
    has_bell: bool | None = None
    is_urgent: bool | None = None


@dataclass(frozen=True, slots=True)
class Tab:
    """A Kitty tab containing one or more panes."""

    id: str | None
    title: str | None
    panes: tuple[Pane, ...]
    is_active: bool | None = None
    layout: str | None = None


@dataclass(frozen=True, slots=True)
class OsWindow:
    """A top-level operating-system window owned by Kitty."""

    id: str | None
    tabs: tuple[Tab, ...]
    title: str | None = None
    is_active: bool | None = None


@dataclass(frozen=True, slots=True)
class PaneLocation:
    """A pane together with its parent tab and OS window."""

    os_window: OsWindow
    tab: Tab
    pane: Pane


@dataclass(frozen=True, slots=True)
class KittyState:
    """A point-in-time snapshot of Kitty's OS-window/tab/pane hierarchy."""

    os_windows: tuple[OsWindow, ...]

    def iter_tabs(self) -> Iterator[tuple[OsWindow, Tab]]:
        """Yield tabs in Kitty traversal order together with their OS windows."""
        for os_window in self.os_windows:
            for tab in os_window.tabs:
                yield os_window, tab

    def iter_panes(self) -> Iterator[PaneLocation]:
        """Yield panes in Kitty traversal order together with their parents."""
        for os_window, tab in self.iter_tabs():
            for pane in tab.panes:
                yield PaneLocation(os_window=os_window, tab=tab, pane=pane)

    @property
    def pane_count(self) -> int:
        """The total number of panes in the snapshot."""
        return sum(len(tab.panes) for _, tab in self.iter_tabs())
