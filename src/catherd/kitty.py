"""Kitty remote-control client and state parsing."""

import json
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import]
import sys
from dataclasses import dataclass
from typing import cast

from .model import KittyState, OsWindow, Pane, Tab


def _safe_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (OverflowError, ValueError):
            return None
    if isinstance(value, str):
        value = value.strip()
        try:
            return int(value)
        except ValueError:
            return None
    return None


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


def _normalize_foreground(window: dict[str, object]) -> tuple[str | None, int | None]:
    proc = window.get("foreground_process")
    if isinstance(proc, dict):
        proc_map = cast("dict[str, object]", proc)
        pid = _safe_int(proc_map.get("pid"))
        cmd = (
            _safe_str(proc_map.get("argv0")) or _safe_str(proc_map.get("command")) or _safe_str(proc_map.get("cmdline"))
        )
        if not cmd:
            cmdline = proc_map.get("cmdline")
            if isinstance(cmdline, list):
                cmd = " ".join(str(part) for part in cmdline if part is not None).strip() or None
        return cmd, pid

    cmd = (
        _safe_str(window.get("foreground_cmd")) or _safe_str(window.get("argv0")) or _safe_str(window.get("foreground"))
    )
    pid = _safe_int(window.get("pid")) or _safe_int(window.get("foreground_pid"))
    return cmd, pid


def _as_object(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast("dict[str, object]", value)
    return None


def _as_object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [obj for item in value if (obj := _as_object(item)) is not None]


def parse_kitty_state(data: object) -> KittyState:
    """Parse kitty @ ls JSON data into the canonical hierarchy."""
    os_windows: list[OsWindow] = []
    for os_data in _as_object_list(data):
        tabs: list[Tab] = []
        for tab_data in _as_object_list(os_data.get("tabs")):
            tab_title = _safe_str(tab_data.get("title"))
            panes: list[Pane] = []
            for pane_data in _as_object_list(tab_data.get("windows")):
                foreground_cmd, pid = _normalize_foreground(pane_data)
                panes.append(
                    Pane(
                        id=_safe_str(pane_data.get("id")) or "",
                        title=_safe_str(pane_data.get("title")) or tab_title or "",
                        is_active=_extract_active_flag(pane_data),
                        pid=pid,
                        cwd=_safe_str(pane_data.get("cwd")),
                        foreground_cmd=foreground_cmd,
                        tty=_safe_str(pane_data.get("tty")),
                        cols=_safe_int(pane_data.get("cols")),
                        rows=_safe_int(pane_data.get("rows")),
                        x=_safe_int(pane_data.get("x")),
                        y=_safe_int(pane_data.get("y")),
                        has_bell=_safe_bool(pane_data.get("has_bell")),
                        is_urgent=_safe_bool(pane_data.get("is_urgent")),
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

    def read_state_json(self) -> str:
        """Return raw JSON from kitty @ ls."""
        command = (self.executable, "@", "ls")
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)  # ruff: ignore[subprocess-without-shell-equals-true]
        except (FileNotFoundError, subprocess.SubprocessError) as exc:
            raise KittyInvocationError(command, exc) from exc
        if result.returncode != 0:
            raise KittyCommandError(command, result.returncode, result.stderr)
        return result.stdout

    def snapshot(self) -> KittyState:
        """Read and parse the current Kitty hierarchy."""
        return _parse_kitty_state_json(self.read_state_json())


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
