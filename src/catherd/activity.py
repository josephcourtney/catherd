"""Shared Kitty/Atuin activity enrichment."""

from dataclasses import dataclass

from .atuin import get_last_command_for_atuin_session
from .config import get_session_file


@dataclass(frozen=True, slots=True)
class PaneActivity:
    """Atuin activity associated with a Kitty pane."""

    session_id: str | None
    last_command: str | None


def get_atuin_session_for_window(window_id: str, *, verbose: bool = False) -> str | None:
    """Return the Atuin session recorded for a Kitty pane."""
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


def get_pane_activity(window_id: str) -> PaneActivity:
    """Return the current Atuin activity associated with a Kitty pane."""
    session_id = get_atuin_session_for_window(window_id)
    last_command = get_last_command_for_atuin_session(session_id) if session_id is not None else None
    return PaneActivity(session_id=session_id, last_command=last_command)
