import json
import os
import shutil
from itertools import groupby, starmap
from pathlib import Path
from typing import Final

import click

from .atuin import get_last_command_for_atuin_session
from .config import get_session_file
from .kitty import KittyWindow, get_kitty_windows
from .shell import get_shell_rc_path, load_snippet_for_shell


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


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """catherd: herd your Kitty windows and Atuin history."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(show)


_MISSING_COMMAND_SENTINELS: Final[set[str]] = {"(no history db)", "(no command)", "(sqlite error)"}
_DISPLAY_COMMAND_FALLBACK: Final[str] = "(no command)"
_TRUNCATE_MIN: Final[int] = 3


def _is_missing_or_error_command(last_cmd: str | None) -> bool:
    if not last_cmd:
        return True
    return last_cmd in _MISSING_COMMAND_SENTINELS


def _resolve_display_command(window: KittyWindow, atuin_cmd: str | None) -> str:
    if atuin_cmd and not _is_missing_or_error_command(atuin_cmd):
        return atuin_cmd
    if window.foreground_cmd:
        return window.foreground_cmd
    return _DISPLAY_COMMAND_FALLBACK


def _truncate(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    if len(value) <= max_len:
        return value
    if max_len <= _TRUNCATE_MIN:
        return value[:max_len]
    return value[: max_len - 3] + "..."


def _active_summary(window: KittyWindow) -> str:
    parts: list[str] = []
    if window.is_active_os_window:
        parts.append("os")
    if window.is_active_tab:
        parts.append("tab")
    if window.is_active_window:
        parts.append("win")
    return ",".join(parts)


def _serialize_window(window: KittyWindow, last_command: str) -> dict[str, str | int | bool | None]:
    return {
        "window_id": window.id,
        "tab": window.tab,
        "title": window.title,
        "last_command": last_command,
        "os_window_id": window.os_window_id,
        "tab_title": window.tab_title,
        "is_active_os_window": window.is_active_os_window,
        "is_active_tab": window.is_active_tab,
        "is_active_window": window.is_active_window,
        "pid": window.pid,
        "cwd": window.cwd,
        "foreground_cmd": window.foreground_cmd,
        "tty": window.tty,
        "cols": window.cols,
        "rows": window.rows,
        "x": window.x,
        "y": window.y,
        "has_bell": window.has_bell,
        "is_urgent": window.is_urgent,
    }


_TITLE_WIDTH: Final[int] = 25
_CMD_WIDTH: Final[int] = 25
_CWD_WIDTH: Final[int] = 20
_FG_WIDTH: Final[int] = 20
_TTY_WIDTH: Final[int] = 15
_SIZE_WIDTH: Final[int] = 7
_ACTIVE_WIDTH: Final[int] = 10
_TAB_TITLE_HINT_WIDTH: Final[int] = 30


def _tab_title_hint(tab_rows: list[tuple[KittyWindow, str]]) -> str:
    title = tab_rows[0][0].tab_title
    return f" - {_truncate(title, _TAB_TITLE_HINT_WIDTH)}" if title else ""


def _print_show_row(win: KittyWindow, display_cmd: str) -> None:
    truncated_title = _truncate(win.title, _TITLE_WIDTH)
    truncated_cmd = _truncate(display_cmd, _CMD_WIDTH)
    truncated_cwd = _truncate(win.cwd, _CWD_WIDTH)
    truncated_fg = _truncate(win.foreground_cmd, _FG_WIDTH)
    truncated_tty = _truncate(win.tty, _TTY_WIDTH)
    size = ""
    if win.cols is not None or win.rows is not None:
        size = f"{win.cols or ''}x{win.rows or ''}"
        if size == "x":
            size = ""
    click.echo(
        f"{win.id:>10} | {win.tab or '':>5} | {truncated_title:<{_TITLE_WIDTH}} | "
        f"{truncated_cmd:<{_CMD_WIDTH}} | {truncated_cwd:<{_CWD_WIDTH}} | "
        f"{win.pid or '':>5} | {truncated_fg:<{_FG_WIDTH}} | "
        f"{truncated_tty:<{_TTY_WIDTH}} | {size:<{_SIZE_WIDTH}} | "
        f"{_active_summary(win):<{_ACTIVE_WIDTH}}"
    )


def _prepare_show_rows(windows: list[KittyWindow], *, verbose: bool) -> list[tuple[KittyWindow, str]]:
    rows: list[tuple[KittyWindow, str]] = []
    for win in windows:
        session_id = get_atuin_session_for_window(win.id, verbose=verbose)
        last_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose) if session_id else None
        rows.append((win, _resolve_display_command(win, last_cmd)))
    return rows


def _render_show_table(rows: list[tuple[KittyWindow, str]]) -> None:
    header = (
        f"{'Kitty WinID':>10} | {'Tab':>5} | {'Title':<{_TITLE_WIDTH}} | "
        f"{'Command':<{_CMD_WIDTH}} | {'CWD':<{_CWD_WIDTH}} | {'PID':>5} | "
        f"{'FG':<{_FG_WIDTH}} | {'TTY':<{_TTY_WIDTH}} | {'SIZE':<{_SIZE_WIDTH}} | "
        f"{'Active':<{_ACTIVE_WIDTH}}"
    )
    click.secho(header, fg="cyan", bold=True)
    click.secho("-" * len(header), fg="cyan")

    first_os = True
    for os_id, os_group in groupby(rows, key=lambda entry: entry[0].os_window_id or ""):
        os_rows = list(os_group)
        if not os_rows:
            continue
        if not first_os:
            click.echo()
        first_os = False
        os_label = os_id or "(unknown os window)"
        os_active_suffix = " (active)" if any(row[0].is_active_os_window for row in os_rows) else ""
        click.secho(f"OS Window {os_label}{os_active_suffix}", fg="cyan")
        for tab_id, tab_group in groupby(os_rows, key=lambda entry: entry[0].tab or ""):
            tab_rows = list(tab_group)
            if not tab_rows:
                continue
            tab_label = tab_id or "(no tab id)"
            tab_active_suffix = " (active)" if any(row[0].is_active_tab for row in tab_rows) else ""
            tab_hint = _tab_title_hint(tab_rows)
            click.echo(f"  Tab {tab_label}{tab_active_suffix}{tab_hint}")
            for win, display_cmd in tab_rows:
                _print_show_row(win, display_cmd)


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
def show(*, verbose: bool, as_json: bool) -> None:
    """Show each open Kitty window/tab and its last Atuin command."""
    if not (os.environ.get("KITTY_WINDOW_ID") and os.environ.get("ATUIN_SESSION")) and not as_json:
        click.secho(
            "[WARN] Atuin/Kitty sync env vars are not set in this shell; results may be incomplete. "
            "Run 'catherd doctor' to diagnose.",
            fg="yellow",
            err=True,
        )

    windows = get_kitty_windows(verbose=verbose)
    if windows is None:
        click.echo("[error] Could not get Kitty windows. See error messages above.", err=True)
        return
    if not windows:
        click.echo("[warning] No Kitty windows/tabs found. Is Kitty running?", err=True)
        return

    rows = _prepare_show_rows(windows, verbose=verbose)

    if as_json:
        click.echo(json.dumps(list(starmap(_serialize_window, rows)), indent=2))
        return

    _render_show_table(rows)


@cli.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
@click.option("--pretty", is_flag=True, help="Pretty-print the JSON output")
def inspect(*, verbose: bool, pretty: bool) -> None:
    """Show the richest per-window Kitty + Atuin dataset as JSON."""
    windows = get_kitty_windows(verbose=verbose)
    if windows is None:
        click.echo("[error] Could not get Kitty windows. See error messages above.", err=True)
        return
    if not windows:
        click.echo("[warning] No Kitty windows/tabs found. Is Kitty running?", err=True)
        return

    payloads: list[dict[str, str | int | bool | None]] = []
    for win in windows:
        session_id = get_atuin_session_for_window(win.id, verbose=verbose)
        session_path = get_session_file(win.id)
        session_content: str | None = None
        if session_path.exists():
            session_content = session_path.read_text(encoding="utf-8").strip()
        atuin_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose) if session_id else None
        display_cmd = _resolve_display_command(win, atuin_cmd)
        payload = _serialize_window(win, display_cmd)
        payload.update({
            "atuin_session_id": session_id,
            "session_file": str(session_path),
            "session_content": session_content,
        })
        payloads.append(payload)

    click.echo(json.dumps(payloads, indent=2 if pretty else None))


@cli.command("install")
@click.option("--shell", "force_shell", help="Force install for this shell (zsh, bash, fish, csh)")
@click.option("--dry-run", is_flag=True)
def install_shell_snippet(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Install the Atuin/Kitty session sync snippet to your shell startup file (idempotent)."""
    try:
        shell = get_shell_info(force_shell)
        rc_path = get_shell_rc_path(shell)
        snippet = load_snippet_for_shell(shell).rstrip()
    except ValueError as err:
        raise click.ClickException(str(err)) from err

    snippet_marker = "# catherd atuin/kitty sync snippet"
    snippet_block = snippet_marker + "\n" + snippet + "\n# end catherd atuin/kitty sync\n"
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
    elif dry_run:
        click.echo(f"[DRY-RUN] Would create {rc_path} and append snippet", err=True)
        click.secho("[OK] Dry-run complete; no changes made.", fg="green")
        return

    if dry_run:
        click.echo(f"[DRY-RUN] Would append snippet to {rc_path}", err=True)
        click.secho("[OK] Dry-run complete; no changes made.", fg="green")
        return

    with rc_path.open("a", encoding="utf-8") as f:
        f.write("\n\n" + snippet_block + "\n")

    click.secho(f"[OK] Snippet added to {rc_path}", fg="green")
    click.secho(
        "You must restart Kitty tabs/windows or re-source your shell for the change to take effect.",
        fg="yellow",
    )


@cli.command("uninstall")
@click.option("--shell", "force_shell", help="Force uninstall for this shell (zsh, bash, fish, csh)")
@click.option("--dry-run", is_flag=True)
def uninstall(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Remove the Atuin/Kitty session sync snippet from your shell startup file."""
    shell = get_shell_info(force_shell)
    rc_path = get_shell_rc_path(shell)
    marker = "# catherd atuin/kitty sync snippet"
    end_marker = "# end catherd atuin/kitty sync"

    if not rc_path.exists():
        msg = f"No rc file found at {rc_path}"
        raise click.ClickException(msg)

    lines = rc_path.read_text(encoding="utf-8").splitlines()
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
    rc_path.write_text("\n".join(new), encoding="utf-8")
    click.secho(f"[OK] Snippet removed from {rc_path}; backup at {backup}", fg="green")


def print_shell_snippet(shell: str) -> None:
    try:
        rc_path = get_shell_rc_path(shell)
        snippet = load_snippet_for_shell(shell)
        click.echo(f"Add this to your shell rc file ({rc_path}):\n")
        click.echo(snippet)
        click.echo("\nOr run 'catherd install' to do it automatically.")
    except ValueError:
        click.echo("[INFO] Unknown shell. See the README or scripts/catherd_rc_snippet.* for setup instructions.\n")


def print_env_diagnostics():
    kitty_id = os.environ.get("KITTY_WINDOW_ID")
    atuin_sess = os.environ.get("ATUIN_SESSION")
    if not kitty_id:
        click.secho("[WARN] $KITTY_WINDOW_ID is not set in this shell. Are you inside Kitty?", fg="yellow")
    if not atuin_sess:
        click.secho("[WARN] $ATUIN_SESSION is not set. Is Atuin initialized in your shell?", fg="yellow")


MIN_SESSION_TOKENS: Final[int] = 2


def _collect_kitty_session_diagnostics(
    windows: list[KittyWindow], *, verbose: bool = False
) -> tuple[list, list, list, list, list[str]]:
    ok = []
    missing_file = []
    corrupt_file = []
    missing_command = []
    session_map: dict[str, list[str]] = {}
    notes: list[str] = []
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
                session_map.setdefault(session_id, []).append(win.id)
                tokens = content.split()
                if len(tokens) >= MIN_SESSION_TOKENS:
                    declared_window = tokens[1]
                    if declared_window != win.id:
                        notes.append(
                            f"session file {session_path} references window {declared_window} but we expected {win.id}"
                        )
                last_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose)
                if _is_missing_or_error_command(last_cmd):
                    missing_command.append((win, content, last_cmd))
                else:
                    ok.append((win, content, last_cmd))
    for session_id, wins in session_map.items():
        if len(wins) > 1:
            notes.append(f"duplicate ATUIN_SESSION {session_id} across windows {', '.join(sorted(wins))}")
    return ok, missing_file, corrupt_file, missing_command, notes


def _gather_window_metadata(win: KittyWindow) -> list[str]:
    metadata: list[str] = []
    if win.pid is not None:
        metadata.append(f"PID: {win.pid}")
    if win.cwd:
        metadata.append(f"CWD: {win.cwd}")
    if win.foreground_cmd:
        metadata.append(f"FG: {win.foreground_cmd}")
    if win.tty:
        metadata.append(f"TTY: {win.tty}")
    return metadata


def _gather_window_hints(win: KittyWindow) -> list[str]:
    hints: list[str] = []
    if win.cwd is None:
        hints.append("cwd unavailable; enable Kitty shell integration if desired.")
    if not win.foreground_cmd:
        hints.append("foreground command unavailable; ensure Kitty shell integration is enabled.")
    if win.tty is None:
        hints.append("tty unavailable; enable Kitty shell integration for richer metadata.")
    if win.pid is None:
        hints.append("pid unavailable; ensure Kitty shell integration is enabled for richer metadata.")
    return hints


def _print_kitty_window_metadata(win: KittyWindow) -> None:
    metadata = _gather_window_metadata(win)
    if metadata:
        click.echo(f"      Kitty metadata: {', '.join(metadata)}")
    else:
        click.echo("      Kitty metadata unavailable; enable Kitty shell integration for richer info.")

    for hint in _gather_window_hints(win):
        click.echo(f"      Hint: {hint}")


def _print_ok_windows(ok: list[tuple[KittyWindow, str, str]]) -> None:
    if not ok:
        return
    click.secho("[OK] Windows with valid Atuin session file:", fg="green")
    for win, content, last_cmd in ok:
        click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
        click.echo(f"      Content: '{content}'")
        click.echo(f"      Atuin last command: {last_cmd}")
        _print_kitty_window_metadata(win)


def _print_missing_files(missing_file: list[KittyWindow]) -> None:
    if not missing_file:
        return
    click.secho("[WARN] Windows missing session file (sync inactive):", fg="yellow")
    for win in missing_file:
        click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
        _print_kitty_window_metadata(win)
    click.echo("    -> The Atuin/Kitty sync snippet is NOT active in these windows/tabs.")
    click.echo("    -> To activate: Ensure your shell sources the sync snippet and RESTART this Kitty tab/window.")


def _print_corrupt_windows(corrupt_file: list[tuple[KittyWindow, str]]) -> None:
    if not corrupt_file:
        return
    click.secho("[FAIL] Windows with session file but missing Atuin session ID:", fg="red")
    for win, content in corrupt_file:
        click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
        click.echo(f"      Content: '{content}' (empty or corrupt)")
        _print_kitty_window_metadata(win)
    click.echo("    -> To fix: restart your shell/tab.")


def _print_missing_command_windows(missing_command: list[tuple[KittyWindow, str, str]]) -> None:
    if not missing_command:
        return
    click.secho("[WARN] Windows with session file but no command in Atuin:", fg="yellow")
    for win, content, last_cmd in missing_command:
        click.echo(f"  - WinID: {win.id}, TabID: {win.tab}, Title: {win.title[:30]}")
        click.echo(f"      Content: '{content}'")
        click.echo(f"      Atuin last command: {last_cmd}")
        _print_kitty_window_metadata(win)
    click.echo("    -> To fix: ensure Atuin is tracking this session's history.")


def _print_sync_notes(notes: list[str]) -> None:
    if not notes:
        return
    click.secho("[INFO] Additional sync observations:", fg="yellow")
    for note in notes:
        click.echo(f"  - {note}")


def print_kitty_session_diagnostics(windows: list[KittyWindow], *, verbose: bool = False) -> None:
    ok, missing_file, corrupt_file, missing_command, notes = _collect_kitty_session_diagnostics(
        windows, verbose=verbose
    )
    click.secho(f"[OK] Found {len(windows)} Kitty window(s).\n", fg="green")

    _print_ok_windows(ok)
    _print_missing_files(missing_file)
    _print_corrupt_windows(corrupt_file)
    _print_missing_command_windows(missing_command)
    _print_sync_notes(notes)

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


@cli.command()
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
        click.secho("[FAIL] No Kitty windows found. Is Kitty running and are there open windows/tabs?", fg="red")
        raise SystemExit(1)

    print_kitty_session_diagnostics(windows, verbose=verbose)

    if not is_sync_active_in_this_shell():
        click.secho(
            "TIP: Run 'catherd install' to set up the session sync automatically for your shell.",
            fg="blue",
        )
    click.secho("=== Doctor check complete ===", fg="blue")


if __name__ == "__main__":
    cli()
