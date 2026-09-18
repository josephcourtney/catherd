import os
from pathlib import Path
from typing import Final

_EMBEDDED_SNIPPETS: Final[dict[str, str]] = {
    "bash": (
        'if [[ -n "$KITTY_WINDOW_ID" && -n "$ATUIN_SESSION" ]]; then\n'
        '  mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}/catherd"\n'
        '  echo "$ATUIN_SESSION $KITTY_WINDOW_ID" > '
        '"${XDG_CACHE_HOME:-$HOME/.cache}/catherd/atuin_kitty_${KITTY_WINDOW_ID}"\n'
        "fi\n"
    ),
    "zsh": (
        'if [[ -n "$KITTY_WINDOW_ID" && -n "$ATUIN_SESSION" ]]; then\n'
        '  local _catherd_dir="${XDG_CACHE_HOME:-$HOME/.cache}/catherd\n'
        '  mkdir -p -- "$_catherd_dir\n'
        '  print -r -- "$ATUIN_SESSION $KITTY_WINDOW_ID" > "$_catherd_dir/atuin_kitty_${KITTY_WINDOW_ID}\n'
        "fi\n"
    ),
    "fish": (
        "if set -q KITTY_WINDOW_ID; and set -q ATUIN_SESSION\n"
        '    mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}/catherd"\n'
        '    echo "$ATUIN_SESSION $KITTY_WINDOW_ID" > '
        '"${XDG_CACHE_HOME:-$HOME/.cache}/catherd/atuin_kitty_${KITTY_WINDOW_ID}"\n'
        "end\n"
    ),
    "csh": (
        "if ($?KITTY_WINDOW_ID && $?ATUIN_SESSION) then\n"
        '    mkdir -p "${XDG_CACHE_HOME:-$HOME/.cache}/catherd"\n'
        '    echo "$ATUIN_SESSION $KITTY_WINDOW_ID" > '
        '"${XDG_CACHE_HOME:-$HOME/.cache}/catherd/atuin_kitty_${KITTY_WINDOW_ID}"\n'
        "endif\n"
    ),
}


def get_shell_rc_path(shell: str) -> Path:
    """
    Return the absolute path to the shell's RC (startup) file.

    Raises ValueError if the shell is unknown.

    - zsh: Respects $ZDOTDIR if set.
    - fish: Respects $XDG_CONFIG_HOME if set.
    """
    home = Path.home()
    if shell == "zsh":
        zdotdir = os.environ.get("ZDOTDIR")
        if zdotdir:
            return Path(zdotdir) / ".zshrc"
        return home / ".zshrc"
    if shell == "bash":
        return home / ".bashrc"
    if shell == "fish":
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(home / ".config"))
        return Path(xdg_config) / "fish" / "config.fish"
    if shell == "csh":
        return home / ".cshrc"
    msg = f"Unknown shell: {shell!r}"
    raise ValueError(msg)


def load_snippet_for_shell(shell: str) -> str:
    """
    Load and return the shell snippet for the given shell.

    Raises ValueError if the shell is unknown.
    """
    if shell not in _EMBEDDED_SNIPPETS:
        msg = f"Unknown shell: {shell!r}"
        raise ValueError(msg)
    return _EMBEDDED_SNIPPETS[shell]
