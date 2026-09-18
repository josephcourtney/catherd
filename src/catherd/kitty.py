"""Kitty remote-control client and state parsing."""

import json
import shlex
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from dataclasses import dataclass
from typing import Literal, cast

from .model import KittyState, OsWindow, Pane, Tab


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _safe_int(value: object) -> int | None:
    result = None
    if value is None:
        result = None
    elif isinstance(value, int):
        result = value
    elif isinstance(value, float):
        try:
            result = int(value)
        except (OverflowError, ValueError):
            result = None
    elif isinstance(value, str):
        value = value.strip()
        try:
            result = int(value)
        except ValueError:
            result = None
    return result


def _safe_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"true", "1", "yes", "y"}:
            return True
        if value in {"false", "0", "no", "n"}:
            return False
    return None


def _extract_active_flag(source: dict[str, object]) -> bool | None:
    for key in ("is_active", "is_focused", "has_focus", "active"):
        if key in source:
            val = _safe_bool(source.get(key))
            if val is not None:
                return val
    return None


def _cmdline_text(value: object) -> str | None:
    if isinstance(value, list):
        parts = [text for item in value if (text := _safe_str(item)) is not None]
        return shlex.join(parts) if parts else None
    return _safe_str(value)


def _normalize_foreground(window: dict[str, object]) -> tuple[str | None, int | None, str | None]:
    processes = _as_object_list(window.get("foreground_processes"))
    if processes:
        proc = max(processes, key=lambda item: _safe_int(item.get("pid")) or -1)
        pid = _safe_int(proc.get("pid"))
        cmd = _cmdline_text(proc.get("cmdline")) or _safe_str(proc.get("argv0"))
        cwd = _safe_str(proc.get("cwd"))
        return cmd, pid, cwd

    proc = _as_object(window.get("foreground_process"))
    if proc is not None:
        pid = _safe_int(proc.get("pid"))
        cmd = (
            _cmdline_text(proc.get("cmdline"))
            or _safe_str(proc.get("argv0"))
            or _safe_str(proc.get("command"))
        )
        return cmd, pid, _safe_str(proc.get("cwd"))

    cmd = (
        _cmdline_text(window.get("cmdline"))
        or _safe_str(window.get("foreground_cmd"))
        or _safe_str(window.get("argv0"))
        or _safe_str(window.get("foreground"))
    )
    pid = _safe_int(window.get("pid")) or _safe_int(window.get("foreground_pid"))
    return cmd, pid, _safe_str(window.get("cwd"))


def _as_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _as_object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [obj for item in value if (obj := _as_object(item)) is not None]


def _is_kitty_ui_window(window: dict[str, object]) -> bool:
    env = _as_object(window.get("env"))
    if env is None:
        return False
    value = _safe_str(env.get("KITTEN_RUNNING_AS_UI"))
    return value not in {None, "", "0", "false", "False"}


def parse_kitty_state(data: object) -> KittyState:
    """Parse kitty @ ls JSON data into the canonical hierarchy."""
    os_windows: list[OsWindow] = []
    for os_data in _as_object_list(data):
        tabs: list[Tab] = []
        for tab_data in _as_object_list(os_data.get("tabs")):
            tab_title = _safe_str(tab_data.get("title"))
            panes: list[Pane] = []
            for pane_data in _as_object_list(tab_data.get("windows")):
                if _is_kitty_ui_window(pane_data):
                    continue
                foreground_cmd, pid, foreground_cwd = _normalize_foreground(pane_data)
                at_prompt = _safe_bool(pane_data.get("at_prompt"))
                last_reported_cmdline = _safe_str(pane_data.get("last_reported_cmdline"))
                needs_attention = _safe_bool(pane_data.get("needs_attention"))
                legacy_urgent = _safe_bool(pane_data.get("is_urgent"))
                panes.append(
                    Pane(
                        id=_safe_str(pane_data.get("id")) or "",
                        title=_safe_str(pane_data.get("title")) or tab_title or "",
                        is_active=_extract_active_flag(pane_data),
                        pid=pid,
                        cwd=foreground_cwd or _safe_str(pane_data.get("cwd")),
                        foreground_cmd=foreground_cmd,
                        root_cmdline=_cmdline_text(pane_data.get("cmdline")),
                        current_command=last_reported_cmdline if at_prompt is False else None,
                        at_prompt=at_prompt,
                        title_overridden=_safe_bool(pane_data.get("title_overridden")),
                        needs_attention=needs_attention,
                        has_activity_since_last_focus=_safe_bool(
                            pane_data.get("has_activity_since_last_focus")
                        ),
                        is_self=_safe_bool(pane_data.get("is_self")),
                        tty=_safe_str(pane_data.get("tty")),
                        cols=_safe_int(pane_data.get("columns")) or _safe_int(pane_data.get("cols")),
                        rows=_safe_int(pane_data.get("lines")) or _safe_int(pane_data.get("rows")),
                        x=_safe_int(pane_data.get("x")),
                        y=_safe_int(pane_data.get("y")),
                        has_bell=_safe_bool(pane_data.get("has_bell")),
                        is_urgent=legacy_urgent if legacy_urgent is not None else needs_attention,
                    )
                )
            tabs.append(
                Tab(
                    id=_safe_str(tab_data.get("id")),
                    title=tab_title,
                    panes=tuple(panes),
                    is_active=_extract_active_flag(tab_data),
                    layout=_safe_str(tab_data.get("layout")),
                )
            )
        os_windows.append(
            OsWindow(
                id=_safe_str(os_data.get("id")),
                title=_safe_str(os_data.get("title")),
                tabs=tuple(tabs),
                is_active=_extract_active_flag(os_data),
            )
        )
    return KittyState(os_windows=tuple(os_windows))


class KittyClientError(RuntimeError):
    """Base class for failures at the Kitty remote-control boundary."""


class KittyNotFoundError(KittyClientError):
    """Raised when the Kitty executable cannot be located."""


class KittyInvocationError(KittyClientError):
    """Raised when the Kitty process cannot be started."""

    def __init__(self, command: tuple[str, ...], cause: BaseException) -> None:
        self.command = command
        self.cause = cause
        super().__init__(str(cause))


class KittyCommandError(KittyClientError):
    """Raised when a Kitty remote-control command fails."""

    def __init__(self, command: tuple[str, ...], returncode: int, stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"command failed with exit code {returncode}: {' '.join(command)}")


class KittyOutputError(KittyClientError):
    """Raised when Kitty returns invalid JSON."""


class KittyObjectNotFoundError(KittyClientError):
    """Raised when an operation references a Kitty object absent from the snapshot."""

    def __init__(self, kind: str, object_id: str) -> None:
        super().__init__(f"{kind} {object_id!r} was not found")


class KittyStateError(KittyClientError):
    """Raised when a snapshot cannot support the requested operation."""


def _require_os_window(state: KittyState, os_window_id: str) -> OsWindow:
    os_window = state.find_os_window(os_window_id)
    if os_window is None:
        msg = "OS window"
        raise KittyObjectNotFoundError(msg, os_window_id)
    return os_window


def _representative_tab_id(os_window: OsWindow) -> str:
    for tab in os_window.tabs:
        if tab.id is not None:
            return tab.id
    msg = f"OS window {os_window.id!r} has no addressable tab"
    raise KittyStateError(msg)


def _representative_pane_id(os_window: OsWindow) -> str:
    for tab in os_window.tabs:
        for pane in tab.panes:
            if pane.id:
                return pane.id
    msg = f"OS window {os_window.id!r} has no addressable pane"
    raise KittyStateError(msg)


def _representative_pane_id_for_tab(state: KittyState, tab_id: str) -> str:
    found = state.find_tab(tab_id)
    if found is None:
        msg = "tab"
        raise KittyObjectNotFoundError(msg, tab_id)
    for pane in found[1].panes:
        if pane.id:
            return pane.id
    msg = f"Tab {tab_id!r} has no addressable pane"
    raise KittyStateError(msg)


@dataclass(frozen=True, slots=True)
class KittyClient:
    """Thin synchronous adapter around Kitty's supported remote-control CLI."""

    executable: str

    @classmethod
    def discover(cls) -> "KittyClient":
        """Locate Kitty on PATH and construct a client."""
        executable = shutil.which("kitty")
        if not executable:
            raise KittyNotFoundError
        return cls(executable=executable)

    def _run_remote(self, *args: str) -> str:
        command = (self.executable, "@", *args)
        try:
            result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
                command,
                capture_output=True,
                text=True,
                check=False,
            )
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise KittyInvocationError(command, exc) from exc
        if result.returncode != 0:
            raise KittyCommandError(command, result.returncode, result.stderr)
        return result.stdout

    def read_state_json(self) -> str:
        """Return raw JSON from kitty @ ls."""
        return self._run_remote("ls")

    def snapshot(self) -> KittyState:
        """Read and parse the current Kitty hierarchy."""
        return _parse_kitty_state_json(self.read_state_json())

    def focus_pane(self, pane_id: str) -> None:
        """Focus a pane, switching tab and OS window if needed."""
        self._run_remote("focus-window", "--match", f"id:{pane_id}")

    def focus_tab(self, tab_id: str) -> None:
        """Focus a tab and its active pane."""
        self._run_remote("focus-tab", "--match", f"id:{tab_id}")

    def focus_os_window(self, os_window_id: str) -> None:
        """Focus an OS window via one of its panes."""
        pane_id = _representative_pane_id(_require_os_window(self.snapshot(), os_window_id))
        self.focus_pane(pane_id)

    def rename_pane(self, pane_id: str, title: str) -> None:
        """Set a pane title."""
        self._run_remote("set-window-title", "--match", f"id:{pane_id}", title)

    def rename_tab(self, tab_id: str, title: str) -> None:
        """Set a tab title."""
        self._run_remote("set-tab-title", "--match", f"id:{tab_id}", title)

    def rename_os_window(self, os_window_id: str, title: str) -> None:
        """Set an OS-window title via one of its panes."""
        pane_id = _representative_pane_id(_require_os_window(self.snapshot(), os_window_id))
        self._run_remote("set-os-window-title", "--match", f"id:{pane_id}", title)

    def move_pane(self, pane_id: str, target_tab_id: str) -> None:
        """Move a pane into an existing tab."""
        self._run_remote(
            "detach-window",
            "--match",
            f"id:{pane_id}",
            "--target-tab",
            f"id:{target_tab_id}",
        )

    def detach_pane_to_new_tab(self, pane_id: str) -> None:
        """Move a pane into a new tab in the current OS window."""
        self._run_remote("detach-window", "--match", f"id:{pane_id}", "--target-tab", "new")

    def detach_pane_to_new_os_window(self, pane_id: str) -> None:
        """Move a pane into a new OS window."""
        self._run_remote("detach-window", "--match", f"id:{pane_id}")

    def move_tab(self, tab_id: str, target_os_window_id: str) -> None:
        """Move a tab into an existing OS window."""
        target = _require_os_window(self.snapshot(), target_os_window_id)
        target_tab_id = _representative_tab_id(target)
        self._run_remote(
            "detach-tab",
            "--match",
            f"id:{tab_id}",
            "--target-tab",
            f"id:{target_tab_id}",
        )

    def detach_tab_to_new_os_window(self, tab_id: str) -> None:
        """Move a tab into a new OS window."""
        self._run_remote("detach-tab", "--match", f"id:{tab_id}")

    def reorder_pane(self, pane_id: str, direction: Literal["forward", "backward"]) -> None:
        """Move a pane one sibling position, focusing and matching it explicitly."""
        self.focus_pane(pane_id)
        action = "move_window_forward" if direction == "forward" else "move_window_backward"
        self._run_remote("action", "--match", f"id:{pane_id}", action)

    def reorder_tab(self, tab_id: str, direction: Literal["forward", "backward"]) -> None:
        """Move a tab one sibling position using one of its panes as action context."""
        pane_id = _representative_pane_id_for_tab(self.snapshot(), tab_id)
        self.focus_tab(tab_id)
        action = "move_tab_forward" if direction == "forward" else "move_tab_backward"
        self._run_remote("action", "--match", f"id:{pane_id}", action)

    def merge_os_windows(self, source_os_window_id: str, target_os_window_id: str) -> None:
        """Move every tab from one OS window into another."""
        if source_os_window_id == target_os_window_id:
            return
        state = self.snapshot()
        source = _require_os_window(state, source_os_window_id)
        target = _require_os_window(state, target_os_window_id)
        target_tab_id = _representative_tab_id(target)
        for tab in source.tabs:
            if tab.id is not None:
                self._run_remote(
                    "detach-tab",
                    "--match",
                    f"id:{tab.id}",
                    "--target-tab",
                    f"id:{target_tab_id}",
                )


def _parse_kitty_state_json(raw: str) -> KittyState:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise KittyOutputError(str(exc)) from exc
    return parse_kitty_state(data)


def _load_kitty_state(*, verbose: bool, client: KittyClient | None) -> KittyState:
    resolved_client = client or KittyClient.discover()
    raw = resolved_client.read_state_json()
    if verbose:
        print("[verbose] Raw output from 'kitty @ ls':")
        print(raw)
    return _parse_kitty_state_json(raw)


def get_kitty_state(*, verbose: bool = False, client: KittyClient | None = None) -> KittyState | None:
    """Return the current Kitty state, preserving the CLI's existing error behavior."""
    try:
        return _load_kitty_state(verbose=verbose, client=client)
    except KittyNotFoundError:
        print("[error] 'kitty' is not found in PATH.", file=sys.stderr)
    except KittyInvocationError as exc:
        print(f"[error] Failed to run {' '.join(exc.command)}: {exc.cause}", file=sys.stderr)
    except KittyCommandError as exc:
        print(
            f"[error] 'kitty @ ls' failed (exit code {exc.returncode}):\n{exc.stderr}",
            file=sys.stderr,
        )
    except KittyOutputError as exc:
        print(f"[error] Failed to parse output from 'kitty @ ls' as JSON: {exc}", file=sys.stderr)
    except KittyClientError as exc:
        print(f"[error] {exc}", file=sys.stderr)
    return None
