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

    def find_os_window(self, os_window_id: str) -> OsWindow | None:
        """Return an OS window by Kitty ID."""
        return next((item for item in self.os_windows if item.id == os_window_id), None)

    def find_tab(self, tab_id: str) -> tuple[OsWindow, Tab] | None:
        """Return a tab and its parent OS window by Kitty ID."""
        return next(((os_window, tab) for os_window, tab in self.iter_tabs() if tab.id == tab_id), None)

    def find_pane(self, pane_id: str) -> PaneLocation | None:
        """Return a pane and its parents by Kitty ID."""
        return next((location for location in self.iter_panes() if location.pane.id == pane_id), None)

    @property
    def pane_count(self) -> int:
        """The total number of panes in the snapshot."""
        return sum(len(tab.panes) for _, tab in self.iter_tabs())
