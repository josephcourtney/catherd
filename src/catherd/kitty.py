"""Kitty window discovery and data models."""

import json
import shutil
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass
from typing import cast


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
    if isinstance(value, str):
        value = value.strip()
        try:
            return int(value)
        except ValueError:
            return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
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
            _safe_str(proc_map.get("argv0"))
            or _safe_str(proc_map.get("command"))
            or _safe_str(proc_map.get("cmdline"))
        )
        if not cmd:
            cmdline = proc_map.get("cmdline")
            if isinstance(cmdline, list):
                cmd = " ".join(str(part) for part in cmdline if part is not None).strip() or None
        return cmd, pid

    cmd = (
        _safe_str(window.get("foreground_cmd"))
        or _safe_str(window.get("argv0"))
        or _safe_str(window.get("foreground"))
    )
    pid = _safe_int(window.get("pid")) or _safe_int(window.get("foreground_pid"))
    return cmd, pid


@dataclass(frozen=True)
class KittyWindow:
    id: str
    tab: str | None
    title: str
    os_window_id: str | None = None
    tab_title: str | None = None
    is_active_os_window: bool | None = None
    is_active_tab: bool | None = None
    is_active_window: bool | None = None
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


def get_kitty_windows(*, verbose: bool = False) -> list[KittyWindow] | None:
    kitty_path = shutil.which("kitty")
    if not kitty_path:
        print("[error] 'kitty' is not found in PATH.", file=sys.stderr)
        return None

    cmd = [kitty_path, "@", "ls"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        print(f"[error] Failed to run {' '.join(cmd)}: {exc}", file=sys.stderr)
        return None

    if result.returncode != 0:
        print(
            f"[error] 'kitty @ ls' failed (exit code {result.returncode}):\n{result.stderr}",
            file=sys.stderr,
        )
        return None

    if verbose:
        print("[verbose] Raw output from 'kitty @ ls':")
        print(result.stdout)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"[error] Failed to parse output from 'kitty @ ls' as JSON: {exc}", file=sys.stderr)
        return None

    windows: list[KittyWindow] = []
    for os_window in data:
        os_id = _safe_str(os_window.get("id"))
        os_active = _extract_active_flag(os_window)
        for tab in os_window.get("tabs", []) or []:
            tab_id = _safe_str(tab.get("id"))
            tab_title = _safe_str(tab.get("title")) or None
            tab_active = _extract_active_flag(tab)
            for window in tab.get("windows", []) or []:
                win_id = _safe_str(window.get("id")) or ""
                win_title = _safe_str(window.get("title")) or tab_title or ""
                fg_cmd, pid = _normalize_foreground(window)
                windows.append(
                    KittyWindow(
                        id=win_id,
                        tab=tab_id,
                        title=win_title,
                        os_window_id=os_id,
                        tab_title=tab_title,
                        is_active_os_window=os_active,
                        is_active_tab=tab_active,
                        is_active_window=_extract_active_flag(window),
                        pid=pid,
                        cwd=_safe_str(window.get("cwd")),
                        foreground_cmd=fg_cmd,
                        tty=_safe_str(window.get("tty")),
                        cols=_safe_int(window.get("cols")),
                        rows=_safe_int(window.get("rows")),
                        x=_safe_int(window.get("x")),
                        y=_safe_int(window.get("y")),
                        has_bell=_safe_bool(window.get("has_bell")),
                        is_urgent=_safe_bool(window.get("is_urgent")),
                    )
                )
    return windows
