import os
from pathlib import Path

SHELL_SNIPPET_FILENAMES = {
    "zsh": "catherd_rc_snippet.zsh",
    "bash": "catherd_rc_snippet.bash",
    "fish": "catherd_rc_snippet.fish",
    "csh": "catherd_rc_snippet.csh",
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
    if shell not in SHELL_SNIPPET_FILENAMES:
        msg = f"Unknown shell: {shell!r}"
        raise ValueError(msg)
    snippet_file = Path(__file__).parent / SHELL_SNIPPET_FILENAMES[shell]
    if not snippet_file.exists():
        return "# (no snippet for this shell)"
    return snippet_file.read_text(encoding="utf-8")
