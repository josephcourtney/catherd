"""Kitty window discovery and data models."""

import json
import shutil
import subprocess  # noqa: S404
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class KittyWindow:
    id: str
    tab: str | None
    title: str


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
        for tab in os_window.get("tabs", []):
            tab_id = tab.get("id")
            tab_title = tab.get("title", "")
            for window in tab.get("windows", []):
                win_id = window.get("id")
                win_title = window.get("title", tab_title)
                windows.append(
                    KittyWindow(
                        id=str(win_id) if win_id is not None else "",
                        tab=str(tab_id) if tab_id is not None else None,
                        title=win_title,
                    )
                )
    return windows
