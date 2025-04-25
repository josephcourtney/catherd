import os
import sqlite3
from pathlib import Path


def get_atuin_history_db_path() -> Path:
    # Atuin uses $XDG_DATA_HOME/atuin/history.db or ~/.local/share/atuin/history.db
    xdg_data = os.environ.get("XDG_DATA_HOME")
    path = Path(xdg_data) if xdg_data else Path("~/.local/share").expanduser()
    return path / "atuin" / "history.db"


def get_last_command_for_atuin_session(
    session_id: str,
    *,
    verbose: bool = False,
) -> str:
    db_path = get_atuin_history_db_path()
    if not db_path.exists():
        if verbose:
            print(f"[verbose] Atuin history DB not found at {db_path}")
        return "(no history db)"
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT command
                FROM history
                WHERE session = ?
                ORDER BY timestamp DESC
                LIMIT 1;
                """,
                (session_id,),
            )
            row = cursor.fetchone()
            if row:
                return row[0]
            return "(no command)"
    except sqlite3.DatabaseError as e:
        if verbose:
            print(f"[verbose] SQLite error: {e}")
        return "(sqlite error)"
