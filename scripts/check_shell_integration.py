"""Run real-shell validation for catherd's optional Atuin integration."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from catherd.shell import SUPPORTED_SHELLS, load_snippet_for_shell, validate_snippet_for_shell

_SHELL_RUN_ARGS: dict[str, tuple[str, ...]] = {
    "bash": ("--noprofile", "--norc"),
    "zsh": ("-f",),
    "fish": ("-N",),
    "csh": ("-f",),
}


def _run_script(shell: str, executable: str, script: Path, env: dict[str, str]) -> None:
    command = [executable, *_SHELL_RUN_ARGS[shell], str(script)]
    result = subprocess.run(  # ruff: ignore[subprocess-without-shell-equals-true]
        command,
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )
    if result.returncode == 0:
        return
    detail = result.stderr.strip() or result.stdout.strip() or f"exit status {result.returncode}"
    msg = f"{shell} integration execution failed: {detail}"
    raise RuntimeError(msg)


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("BASH_ENV", None)
    env.pop("KITTY_WINDOW_ID", None)
    env.pop("ATUIN_SESSION", None)
    return env


def _check_xdg_cache(shell: str, executable: str, root: Path) -> None:
    script = root / f"integration.{shell}"
    script.write_text(load_snippet_for_shell(shell), encoding="utf-8")
    cache_home = root / "cache home"
    env = _base_env()
    env.update(
        {
            "HOME": str(root / "home"),
            "XDG_CACHE_HOME": str(cache_home),
            "KITTY_WINDOW_ID": "27",
            "ATUIN_SESSION": "session-abc",
        }
    )

    _run_script(shell, executable, script, env)

    session_file = cache_home / "catherd" / "atuin_kitty_27"
    actual = session_file.read_text(encoding="utf-8").strip()
    if actual != "session-abc 27":
        msg = f"{shell} wrote unexpected XDG session data: {actual!r}"
        raise RuntimeError(msg)


def _check_home_fallback(shell: str, executable: str, root: Path) -> None:
    script = root / f"integration-home.{shell}"
    script.write_text(load_snippet_for_shell(shell), encoding="utf-8")
    home = root / "home with spaces"
    env = _base_env()
    env.pop("XDG_CACHE_HOME", None)
    env.update(
        {
            "HOME": str(home),
            "KITTY_WINDOW_ID": "12",
            "ATUIN_SESSION": "session-home",
        }
    )

    _run_script(shell, executable, script, env)

    session_file = home / ".cache" / "catherd" / "atuin_kitty_12"
    actual = session_file.read_text(encoding="utf-8").strip()
    if actual != "session-home 12":
        msg = f"{shell} wrote unexpected HOME-fallback session data: {actual!r}"
        raise RuntimeError(msg)


def _check_noop_without_association(shell: str, executable: str, root: Path) -> None:
    script = root / f"integration-no-env.{shell}"
    script.write_text(load_snippet_for_shell(shell), encoding="utf-8")
    cache_home = root / "cache"
    env = _base_env()
    env["HOME"] = str(root / "home")
    env["XDG_CACHE_HOME"] = str(cache_home)

    _run_script(shell, executable, script, env)

    if (cache_home / "catherd").exists():
        msg = f"{shell} created catherd cache state without Kitty/Atuin association variables"
        raise RuntimeError(msg)


def main() -> int:
    checked: list[str] = []
    skipped: list[str] = []

    with tempfile.TemporaryDirectory(prefix="catherd-shell-check-") as temporary:
        root = Path(temporary)
        for shell in SUPPORTED_SHELLS:
            executable = shutil.which(shell)
            if executable is None:
                skipped.append(shell)
                continue

            validate_snippet_for_shell(shell)
            shell_root = root / shell
            shell_root.mkdir()
            _check_xdg_cache(shell, executable, shell_root)
            _check_home_fallback(shell, executable, shell_root)
            _check_noop_without_association(shell, executable, shell_root)
            checked.append(shell)

    if checked:
        print(f"validated shell integrations: {', '.join(checked)}")
    if skipped:
        print(f"skipped unavailable shells: {', '.join(skipped)}")

    if not checked:
        msg = "no supported shell executable was available for integration validation"
        raise RuntimeError(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
