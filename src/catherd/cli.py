import json
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
    # default to `show` if no subcommand given
    if not hasattr(main, "_called") and not click.get_current_context().invoked_subcommand:
        click.get_current_context().invoked_subcommand = "show"
        click.get_current_context().forward(show)
    main._called = True


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
def show(*, verbose: bool = False, as_json: bool = False) -> None:
    """Show each open Kitty window/tab and its last Atuin command."""
    # pre-flight: require KITTY_WINDOW_ID + ATUIN_SESSION
    if not (os.environ.get("KITTY_WINDOW_ID") and os.environ.get("ATUIN_SESSION")):
        msg = "Atuin/Kitty sync snippet is not active in this shell; run 'catherd doctor' to diagnose."
        raise click.ClickException(msg)
    windows = get_kitty_windows(verbose=verbose)
    if windows is None:
        click.echo("[error] Could not get Kitty windows. See error messages above.", err=True)
        return
    if not windows:
        click.echo("[warning] No Kitty windows/tabs found. Is Kitty running?", err=True)
        return

    click.secho(f"{'Kitty WinID':>10} | {'TabID':>5} | {'Title':<25} | Last Command", fg="cyan", bold=True)
    click.secho("-" * 80, fg="cyan")

    if as_json:
        out = []

    for win in windows:
        session_id = get_atuin_session_for_window(win.id, verbose=verbose)
        last_cmd = (
            get_last_command_for_atuin_session(session_id, verbose=verbose)
            if session_id
            else "(no session info)"
        )
        click.echo(f"{win.id:>10} | {win.tab or '':>5} | {win.title[:25]:<25} | {last_cmd}")
        if as_json:
            out.append({
                "window_id": win.id,
                "tab": win.tab,
                "title": win.title,
                "last_command": last_cmd,
            })
    if as_json:
        click.echo(json.dumps(out, indent=2))


@main.command("install")
@click.option("--shell", "force_shell", help="Force install for this shell (zsh, bash, fish, csh)")
@click.option("--dry-run", is_flag=True)
def install_shell_snippet(force_shell: str | None = None, dry_run: bool = False) -> None:
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
            if not dry_run:
                shutil.copyfile(rc_path, rc_path.with_suffix(rc_path.suffix + ".catherd.bak"))
            click.secho(
                f"[INFO] Backed up {rc_path} → {rc_path.with_suffix(rc_path.suffix + '.catherd.bak')}",
                fg="yellow",
                err=dry_run,
            )
        with rc_path.open("a", encoding="utf-8") as f:
            if dry_run:
                click.echo(f"[DRY-RUN] Would append snippet to {rc_path}", err=True)
            else:
                f.write("\n\n" + snippet_block + "\n")
        click.secho(f"[OK] Snippet added to {rc_path}", fg="green")
        click.secho(
            "You must restart Kitty tabs/windows or re-source your shell for the change to take effect.",
            fg="yellow",
        )
    except ValueError as err:
        raise click.ClickException(str(err)) from err


@main.command("uninstall")
@click.option("--shell", "force_shell", help="Force uninstall for this shell (zsh, bash, fish, csh)")
@click.option("--dry-run", is_flag=True)
def uninstall(force_shell: str | None = None, dry_run: bool = False) -> None:
    """Remove the Atuin/Kitty session sync snippet from your shell startup file."""
    shell = get_shell_info(force_shell)
    rc_path = get_shell_rc_path(shell)
    marker = "# catherd atuin/kitty sync snippet"
    end_marker = "# end catherd atuin/kitty sync"

    if not rc_path.exists():
        msg = f"No rc file found at {rc_path}"
        raise click.ClickException(msg)

    lines = rc_path.read_text().splitlines()
    inside = False
    new = []
    removed = False
    for ln in lines:
        if ln.strip() == marker:
            inside = True
            removed = True
            continue
        if inside and ln.strip() == end_marker:
            inside = False
            continue
        if not inside:
            new.append(ln)

    if not removed:
        click.secho(f"[WARN] No snippet found in {rc_path}", fg="yellow")
        return

    if dry_run:
        click.echo(f"[DRY-RUN] Would remove snippet from {rc_path}", err=True)
        return

    backup = rc_path.with_suffix(rc_path.suffix + ".catherd.uninstall.bak")
    shutil.copyfile(rc_path, backup)
    rc_path.write_text("\n".join(new))
    click.secho(f"[OK] Snippet removed from {rc_path}; backup at {backup}", fg="green")


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
        raise SystemExit(1)

    print_kitty_session_diagnostics(windows, verbose=verbose)

    if not is_sync_active_in_this_shell():
        click.secho(
            "TIP: Run 'catherd install' to set up the session sync automatically for your shell.",
            fg="blue",
        )
    click.secho("=== Doctor check complete ===", fg="blue")


if __name__ == "__main__":
    main()
