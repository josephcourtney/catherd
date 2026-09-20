import os
import shutil
import subprocess  # ruff: ignore[suspicious-subprocess-import] -- validates fixed, allow-listed shell snippets
from pathlib import Path
from typing import Final, Literal

SUPPORTED_SHELLS: Final[tuple[str, ...]] = ("bash", "zsh", "fish", "csh")

ATUIN_INTEGRATION_MARKER: Final[str] = "# catherd atuin integration"
ATUIN_INTEGRATION_END_MARKER: Final[str] = "# end catherd atuin integration"
LEGACY_ATUIN_INTEGRATION_MARKER: Final[str] = "# catherd atuin/kitty sync snippet"
LEGACY_ATUIN_INTEGRATION_END_MARKER: Final[str] = "# end catherd atuin/kitty sync"

ManagedSnippetState = Literal["absent", "current", "legacy"]

_EMBEDDED_SNIPPETS: Final[dict[str, str]] = {
    "bash": (
        'if [[ -n "${KITTY_WINDOW_ID:-}" && -n "${ATUIN_SESSION:-}" ]]; then\n'
        '  _catherd_dir="${XDG_CACHE_HOME:-$HOME/.cache}/catherd"\n'
        '  mkdir -p "$_catherd_dir"\n'
        "  printf '%s %s\\n' \"$ATUIN_SESSION\" \"$KITTY_WINDOW_ID\" > "
        '"$_catherd_dir/atuin_kitty_${KITTY_WINDOW_ID}"\n'
        "  unset _catherd_dir\n"
        "fi\n"
    ),
    "zsh": (
        'if [[ -n "${KITTY_WINDOW_ID:-}" && -n "${ATUIN_SESSION:-}" ]]; then\n'
        '  _catherd_dir="${XDG_CACHE_HOME:-$HOME/.cache}/catherd"\n'
        '  mkdir -p "$_catherd_dir"\n'
        '  print -r -- "$ATUIN_SESSION $KITTY_WINDOW_ID" > "$_catherd_dir/atuin_kitty_${KITTY_WINDOW_ID}"\n'
        "  unset _catherd_dir\n"
        "fi\n"
    ),
    "fish": (
        "if set -q KITTY_WINDOW_ID; and set -q ATUIN_SESSION\n"
        "    if set -q XDG_CACHE_HOME\n"
        '        set -l _catherd_dir "$XDG_CACHE_HOME/catherd"\n'
        "    else\n"
        '        set -l _catherd_dir "$HOME/.cache/catherd"\n'
        "    end\n"
        '    mkdir -p "$_catherd_dir"\n'
        "    printf '%s %s\\n' \"$ATUIN_SESSION\" \"$KITTY_WINDOW_ID\" > "
        '"$_catherd_dir/atuin_kitty_$KITTY_WINDOW_ID"\n'
        "end\n"
    ),
    "csh": (
        "if ($?KITTY_WINDOW_ID && $?ATUIN_SESSION) then\n"
        "    if ($?XDG_CACHE_HOME) then\n"
        '        set _catherd_dir = "$XDG_CACHE_HOME/catherd"\n'
        "    else\n"
        '        set _catherd_dir = "$HOME/.cache/catherd"\n'
        "    endif\n"
        '    mkdir -p "$_catherd_dir"\n'
        '    echo "$ATUIN_SESSION $KITTY_WINDOW_ID" > "$_catherd_dir/atuin_kitty_$KITTY_WINDOW_ID"\n'
        "    unset _catherd_dir\n"
        "endif\n"
    ),
}

_MARKER_PAIRS: Final[dict[str, str]] = {
    ATUIN_INTEGRATION_MARKER: ATUIN_INTEGRATION_END_MARKER,
    LEGACY_ATUIN_INTEGRATION_MARKER: LEGACY_ATUIN_INTEGRATION_END_MARKER,
}
_END_MARKERS: Final[set[str]] = set(_MARKER_PAIRS.values())
_VALIDATION_ARGS: Final[dict[str, tuple[str, ...]]] = {
    "bash": ("--noprofile", "--norc", "-n"),
    "zsh": ("-f", "-n"),
    "fish": ("-N", "-n"),
    "csh": ("-f", "-n", "-s"),
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
    msg = f"Unknown shell: {shell!r}. Supported shells: {', '.join(SUPPORTED_SHELLS)}"
    raise ValueError(msg)


def load_snippet_for_shell(shell: str) -> str:
    """Return the optional Atuin-association snippet for a supported shell."""
    try:
        return _EMBEDDED_SNIPPETS[shell]
    except KeyError as exc:
        msg = f"Unknown shell: {shell!r}. Supported shells: {', '.join(SUPPORTED_SHELLS)}"
        raise ValueError(msg) from exc


def managed_snippet_block(shell: str) -> str:
    """Return the complete current catherd-managed Atuin integration block."""
    snippet = load_snippet_for_shell(shell).rstrip()
    return f"{ATUIN_INTEGRATION_MARKER}\n{snippet}\n{ATUIN_INTEGRATION_END_MARKER}\n"


def validate_snippet_for_shell(shell: str) -> None:
    """Parse-check a generated snippet with the corresponding shell executable."""
    snippet = load_snippet_for_shell(shell)
    executable = shutil.which(shell)
    if executable is None:
        msg = f"Cannot validate {shell!r} integration: {shell} executable was not found on PATH"
        raise ValueError(msg)

    environment = os.environ.copy()
    environment.pop("BASH_ENV", None)
    try:
        result = subprocess.run(  # noqa: S603
            [executable, *_VALIDATION_ARGS[shell]],
            input=snippet,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
            env=environment,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        msg = f"Could not validate generated {shell} integration: {err}"
        raise ValueError(msg) from err

    if result.returncode == 0:
        return
    detail = result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"
    msg = f"Generated {shell} integration failed syntax validation: {detail}"
    raise ValueError(msg)


def _managed_blocks(contents: str) -> list[tuple[int, int, str]]:
    """Return managed block line ranges, rejecting malformed or nested markers."""
    lines = contents.splitlines(keepends=True)
    blocks: list[tuple[int, int, str]] = []
    index = 0
    while index < len(lines):
        marker = lines[index].strip()
        if marker in _END_MARKERS:
            msg = f"Found catherd integration end marker without a matching start marker: {marker}"
            raise ValueError(msg)
        expected_end = _MARKER_PAIRS.get(marker)
        if expected_end is None:
            index += 1
            continue

        start = index
        index += 1
        while index < len(lines) and lines[index].strip() != expected_end:
            nested_marker = lines[index].strip()
            if nested_marker in _MARKER_PAIRS or nested_marker in _END_MARKERS:
                msg = f"Malformed catherd integration block near marker: {nested_marker}"
                raise ValueError(msg)
            index += 1
        if index >= len(lines):
            msg = f"Unterminated catherd integration block beginning with: {marker}"
            raise ValueError(msg)
        blocks.append((start, index + 1, marker))
        index += 1

    if len(blocks) > 1:
        msg = "Multiple catherd Atuin integration blocks found; remove duplicates before continuing"
        raise ValueError(msg)
    return blocks


def managed_snippet_state(contents: str) -> ManagedSnippetState:
    """Return whether rc contents contain the current, legacy, or no managed block."""
    blocks = _managed_blocks(contents)
    if not blocks:
        return "absent"
    return "current" if blocks[0][2] == ATUIN_INTEGRATION_MARKER else "legacy"


def replace_managed_snippet(contents: str, replacement: str | None) -> tuple[str, bool]:
    """Replace or remove the one managed block while preserving all other text."""
    blocks = _managed_blocks(contents)
    if not blocks:
        return contents, False

    lines = contents.splitlines(keepends=True)
    start, end, _marker = blocks[0]
    replacement_lines = [] if replacement is None else [replacement]
    return "".join([*lines[:start], *replacement_lines, *lines[end:]]), True


def append_managed_snippet(contents: str, block: str) -> str:
    """Append a managed block with stable separation from existing rc contents."""
    if not contents:
        return block
    separator = "\n" if contents.endswith("\n") else "\n\n"
    return contents + separator + block
