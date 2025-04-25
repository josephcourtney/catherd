import os
import shutil
from pathlib import Path

import click

from .atuin import get_last_command_for_atuin_session
from .config import get_session_file
from .kitty import KittyWindow, get_kitty_windows
from .shell import SHELL_SNIPPET_FILENAMES, get_shell_rc_path, load_snippet_for_shell


def is_sync_active_in_this_shell() -> bool:
    kitty_id = os.environ.get("KITTY_WINDOW_ID")
    atuin_sess = os.environ.get("ATUIN_SESSION")
    if not kitty_id or not atuin_sess:
        return False
    session_path = get_session_file(str(kitty_id))
    if not session_path.exists():
        return False
    content = session_path.read_text(encoding="utf-8").strip()
    if not content or not content.split():
        return False
    session_id, *_ = content.split()
    return session_id == atuin_sess and str(kitty_id) in content


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


def get_shell_info(force_shell: str | None = None) -> str:
    shell = force_shell
    if not shell:
        shell_path = os.environ.get("SHELL", "")
        shell = Path(shell_path).name
    return shell


@click.group()
def main():
    """catherd: herd your Kitty windows and Atuin history."""


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
def show(*, verbose: bool = False) -> None:
    """Show each open Kitty window/tab and its last Atuin command."""
    windows = get_kitty_windows(verbose=verbose)
    if windows is None:
        click.echo("[error] Could not get Kitty windows. See error messages above.", err=True)
        return
    if not windows:
        click.echo("[warning] No Kitty windows/tabs found. Is Kitty running?", err=True)
        return

    click.echo(f"{'Kitty WinID':>10} | {'TabID':>5} | {'Title':<25} | Last Command")
    click.echo("-" * 80)
    for win in windows:
        session_id = get_atuin_session_for_window(win.id, verbose=verbose)
        last_cmd = (
            get_last_command_for_atuin_session(session_id, verbose=verbose)
            if session_id
            else "(no session info)"
        )
        click.echo(f"{win.id:>10} | {win.tab or '':>5} | {win.title[:25]:<25} | {last_cmd}")


@main.command("install")
@click.option("--shell", "force_shell", help="Force install for this shell (zsh, bash, fish, csh)")
def install_shell_snippet(force_shell: str | None = None) -> None:
    """Install the Atuin/Kitty session sync snippet to your shell startup file (idempotent)."""
    try:
        shell = get_shell_info(force_shell)
        rc_path = get_shell_rc_path(shell)
        snippet_marker = "# catherd atuin/kitty sync snippet"
        snippet_block = (
            snippet_marker
            + "\n"
            + load_snippet_for_shell(shell).rstrip()
            + "\n# end catherd atuin/kitty sync\n"
        )

        if rc_path.exists():
            contents = rc_path.read_text(encoding="utf-8")
            if snippet_marker in contents:
                click.secho(f"[OK] Snippet already installed in {rc_path}", fg="green")
                return
            shutil.copyfile(rc_path, rc_path.with_suffix(rc_path.suffix + ".catherd.bak"))
        with rc_path.open("a", encoding="utf-8") as f:
            f.write("\n\n" + snippet_block + "\n")
        click.secho(f"[OK] Snippet added to {rc_path}", fg="green")
        click.secho(
            "You must restart Kitty tabs/windows or re-source your shell for the change to take effect.",
            fg="yellow",
        )
    except ValueError as err:
        click.secho(f"[FAIL] {err}", fg="red")
        return


def print_shell_snippet(shell: str) -> None:
    if shell in SHELL_SNIPPET_FILENAMES:
        rc_path = get_shell_rc_path(shell) or "<your-shell-rc>"
        snippet = load_snippet_for_shell(shell)
        click.echo(f"Add this to your shell rc file ({rc_path}):\n")
        click.echo(snippet)
        click.echo("\nOr run 'catherd install' to do it automatically.")
    else:
        click.echo(
            "[INFO] Unknown shell. See the README or scripts/catherd_rc_snippet.* for setup instructions.\n"
        )


def print_env_diagnostics():
    kitty_id = os.environ.get("KITTY_WINDOW_ID")
    atuin_sess = os.environ.get("ATUIN_SESSION")
    if not kitty_id:
        click.secho("[WARN] $KITTY_WINDOW_ID is not set in this shell. Are you inside Kitty?", fg="yellow")
    if not atuin_sess:
        click.secho("[WARN] $ATUIN_SESSION is not set. Is Atuin initialized in your shell?", fg="yellow")


def _collect_kitty_session_diagnostics(
    windows: list[KittyWindow], *, verbose: bool = False
) -> tuple[list, list, list, list]:
    ok = []
    missing_file = []
    corrupt_file = []
    missing_command = []
    for win in windows:
        session_path = get_session_file(str(win.id))
        if not session_path.exists():
            missing_file.append(win)
        else:
            content = session_path.read_text(encoding="utf-8").strip()
            if not content or not content.split():
                corrupt_file.append((win, content))
            else:
                session_id = content.split()[0]
                last_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose)
                if not last_cmd or last_cmd.startswith("(atuin error)"):
                    missing_command.append((win, content, last_cmd))
                else:
                    ok.append((win, content, last_cmd))
    return ok, missing_file, corrupt_file, missing_command


def print_kitty_session_diagnostics(windows: list[KittyWindow], *, verbose: bool = False) -> None:
    ok, missing_file, corrupt_file, missing_command = _collect_kitty_session_diagnostics(
        windows, verbose=verbose
    )
    click.secho(f"[OK] Found {len(windows)} Kitty window(s).\n", fg="green")

    if ok:
        click.secho("[OK] Windows with valid Atuin session file:", fg="green")
        for win, content, last_cmd in ok:
            click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
            click.echo(f"      Content: '{content}'")
            click.echo(f"      Atuin last command: {last_cmd}")
    if missing_file:
        click.secho("[WARN] Windows missing session file (sync inactive):", fg="yellow")
        for win in missing_file:
            click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
        click.echo("    -> The Atuin/Kitty sync snippet is NOT active in these windows/tabs.")
        click.echo(
            "    -> To activate: Ensure your shell sources the sync snippet and "
            "RESTART this Kitty tab/window."
        )
    if corrupt_file:
        click.secho("[FAIL] Windows with session file but missing Atuin session ID:", fg="red")
        for win, content in corrupt_file:
            click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
            click.echo(f"      Content: '{content}' (empty or corrupt)")
        click.echo("    -> To fix: restart your shell/tab.")
    if missing_command:
        click.secho("[WARN] Windows with session file but no command in Atuin:", fg="yellow")
        for win, content, last_cmd in missing_command:
            click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
            click.echo(f"      Content: '{content}'")
            click.echo(f"      Atuin last command: {last_cmd}")
        click.echo("    -> To fix: ensure Atuin is tracking this session's history.")

    total = len(windows)
    synced = len(ok)
    if synced == 0:
        click.secho(
            "[INFO] Atuin/Kitty sync is not active in any open windows.\n"
            "To enable full functionality, add the sync snippet to your shell startup file, "
            "then restart Kitty tabs/windows.",
            fg="yellow",
        )
    else:
        color = "green" if synced == total else "yellow"
        click.secho(
            f"[INFO] Atuin/Kitty sync active in {synced}/{total} windows.",
            fg=color,
        )


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
def doctor(*, verbose: bool = False) -> None:
    """Diagnose catherd/Kitty/Atuin integration issues."""
    click.echo("=== catherd doctor ===")

    print_env_diagnostics()
    shell = get_shell_info()
    click.echo(f"[INFO] Detected shell: {shell}")

    if not is_sync_active_in_this_shell():
        print_shell_snippet(shell)

    windows = get_kitty_windows(verbose=verbose)
    if windows is None or not windows:
        click.secho(
            "[FAIL] No Kitty windows found. Is Kitty running and are there open windows/tabs?", fg="red"
        )
        return

    print_kitty_session_diagnostics(windows, verbose=verbose)

    if not is_sync_active_in_this_shell():
        click.secho(
            "TIP: Run 'catherd install' to set up the session sync automatically for your shell.",
            fg="blue",
        )
    click.secho("=== Doctor check complete ===", fg="blue")


if __name__ == "__main__":
    main()
