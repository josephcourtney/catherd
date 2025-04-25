import json
import shutil
import subprocess  # noqa: S404
import sys
from typing import Any

from .config import get_session_file


def get_kitty_windows(*, verbose: bool = False) -> list[dict[str, Any]] | None:
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
            f"[error] 'kitty @ ls' failed (exit code {result.returncode}):\n{result.stderr}", file=sys.stderr
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

    windows = []
    for os_window in data:
        for tab in os_window.get("tabs", []):
            tab_id = tab.get("id", None)
            tab_title = tab.get("title", "")
            for window in tab.get("windows", []):
                win_id = window.get("id", None)
                win_title = window.get("title", tab_title)
                windows.append({
                    "id": win_id,
                    "tab": tab_id,
                    "title": win_title,
                })
    if not windows:
        print("[warning] No windows found in Kitty session. Try opening a window or tab.", file=sys.stderr)
    return windows


def get_atuin_session_for_window(window_id: str, *, verbose: bool = False) -> str | None:
    path = get_session_file(window_id)
    if not path.exists():
        if verbose:
            print(f"[verbose] No session file: {path}")
        return None
    line = path.read_text(encoding="utf-8").strip()
    if verbose:
        print(f"[verbose] Read session info from {path}: '{line}'")
    if not line:
        return None
    return line.split()[0]


def get_last_command_for_atuin_session(session_id: str, *, verbose: bool = False) -> str:
    atuin_path = shutil.which("atuin")
    if not atuin_path:
        if verbose:
            print("[verbose] 'atuin' is not found in PATH.")
        return "(atuin not found)"
    try:
        result = subprocess.run(  # noqa: S603
            [atuin_path, "search", "--session", session_id, "--limit", "1", "--format", "{command}"],
            capture_output=True,
            text=True,
            check=False,
        )
        if verbose:
            print(f"[verbose] Atuin search result for session {session_id}: '{result.stdout.strip()}'")
        return result.stdout.strip() or "(no command)"
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        if verbose:
            print(f"[verbose] Error running atuin for session {session_id}: {exc}")
        return "(atuin error)"


def main(*, verbose: bool = False) -> None:
    windows = get_kitty_windows(verbose=verbose)
    print(f"{'Kitty WinID':>10} | {'TabID':>5} | {'Title':<25} | Last Command")
    print("-" * 80)
    if not windows:
        return
    for win in windows:
        session_id = get_atuin_session_for_window(win["id"], verbose=verbose)
        last_cmd = (
            get_last_command_for_atuin_session(session_id, verbose=verbose)
            if session_id
            else "(no session info)"
        )
        print(f"{win['id']:>10} | {win['tab']:>5} | {win['title'][:25]:<25} | {last_cmd}")


if __name__ == "__main__":
    main(verbose="--verbose" in sys.argv)
