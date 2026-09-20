import json
import os
import shutil
from itertools import groupby, starmap
from pathlib import Path
from typing import Final

import click

from .activity import get_atuin_session_for_window
from .atuin import get_last_command_for_atuin_session
from .config import get_session_file
from .kitty import KittyClientError, get_kitty_state
from .model import KittyState, Pane, PaneLocation
from .shell import get_shell_rc_path, load_snippet_for_shell
from .tui import run_tui


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


def get_shell_info(force_shell: str | None = None) -> str:
    shell = force_shell
    if not shell:
        shell_path = os.environ.get("SHELL", "")
        shell = Path(shell_path).name
    return shell


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Inspect and organize Kitty, with optional Atuin history enrichment."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(show)


main = cli


_MISSING_COMMAND_SENTINELS: Final[set[str]] = {"(no history db)", "(no command)", "(sqlite error)"}
_DISPLAY_COMMAND_FALLBACK: Final[str] = "(no command)"
_TRUNCATE_MIN: Final[int] = 3


def _is_missing_or_error_command(last_cmd: str | None) -> bool:
    if not last_cmd:
        return True
    return last_cmd in _MISSING_COMMAND_SENTINELS


def _resolve_display_command(pane: Pane, atuin_cmd: str | None) -> str:
    if pane.current_command:
        return pane.current_command
    if atuin_cmd and not _is_missing_or_error_command(atuin_cmd):
        return atuin_cmd
    if pane.foreground_cmd:
        return pane.foreground_cmd
    return _DISPLAY_COMMAND_FALLBACK


def _truncate(value: str | None, max_len: int) -> str:
    if not value:
        return ""
    if len(value) <= max_len:
        return value
    if max_len <= _TRUNCATE_MIN:
        return value[:max_len]
    return value[: max_len - 3] + "..."


def _active_summary(location: PaneLocation) -> str:
    parts: list[str] = []
    if location.os_window.is_active:
        parts.append("os")
    if location.tab.is_active:
        parts.append("tab")
    if location.pane.is_active:
        parts.append("win")
    return ",".join(parts)


def _serialize_pane(location: PaneLocation, last_command: str) -> dict[str, str | int | bool | None]:
    pane = location.pane
    return {
        "window_id": pane.id,
        "tab": location.tab.id,
        "title": pane.title,
        "last_command": last_command,
        "os_window_id": location.os_window.id,
        "tab_title": location.tab.title,
        "is_active_os_window": location.os_window.is_active,
        "is_active_tab": location.tab.is_active,
        "is_active_window": pane.is_active,
        "pid": pane.pid,
        "cwd": pane.cwd,
        "foreground_cmd": pane.foreground_cmd,
        "root_cmdline": pane.root_cmdline,
        "current_command": pane.current_command,
        "at_prompt": pane.at_prompt,
        "title_overridden": pane.title_overridden,
        "needs_attention": pane.needs_attention,
        "has_activity_since_last_focus": pane.has_activity_since_last_focus,
        "is_self": pane.is_self,
        "tab_index": pane.tab_index,
        "tab_count": pane.tab_count,
        "group_index": pane.group_index,
        "group_count": pane.group_count,
        "neighbors_left": ",".join(pane.neighbors_left) or None,
        "neighbors_top": ",".join(pane.neighbors_top) or None,
        "neighbors_right": ",".join(pane.neighbors_right) or None,
        "neighbors_bottom": ",".join(pane.neighbors_bottom) or None,
        "tty": pane.tty,
        "cols": pane.cols,
        "rows": pane.rows,
        "x": pane.x,
        "y": pane.y,
        "has_bell": pane.has_bell,
        "is_urgent": pane.is_urgent,
    }


_TITLE_WIDTH: Final[int] = 25
_CMD_WIDTH: Final[int] = 25
_CWD_WIDTH: Final[int] = 20
_FG_WIDTH: Final[int] = 20
_SIZE_WIDTH: Final[int] = 7
_ACTIVE_WIDTH: Final[int] = 10
_TAB_TITLE_HINT_WIDTH: Final[int] = 30


def _tab_title_hint(tab_rows: list[tuple[PaneLocation, str]]) -> str:
    title = tab_rows[0][0].tab.title
    return f" - {_truncate(title, _TAB_TITLE_HINT_WIDTH)}" if title else ""


def _print_show_row(location: PaneLocation, display_cmd: str) -> None:
    pane = location.pane
    truncated_title = _truncate(pane.title, _TITLE_WIDTH)
    truncated_cmd = _truncate(display_cmd, _CMD_WIDTH)
    truncated_cwd = _truncate(pane.cwd, _CWD_WIDTH)
    truncated_fg = _truncate(pane.foreground_cmd, _FG_WIDTH)
    size = ""
    if pane.cols is not None or pane.rows is not None:
        size = f"{pane.cols or ''}x{pane.rows or ''}"
        if size == "x":
            size = ""
    click.echo(
        f"{pane.id:>10} | {location.tab.id or '':>5} | {truncated_title:<{_TITLE_WIDTH}} | "
        f"{truncated_cmd:<{_CMD_WIDTH}} | {truncated_cwd:<{_CWD_WIDTH}} | "
        f"{pane.pid or '':>5} | {truncated_fg:<{_FG_WIDTH}} | "
        f"{size:<{_SIZE_WIDTH}} | "
        f"{_active_summary(location):<{_ACTIVE_WIDTH}}"
    )


def _prepare_show_rows(state: KittyState, *, verbose: bool) -> list[tuple[PaneLocation, str]]:
    rows: list[tuple[PaneLocation, str]] = []
    for location in state.iter_panes():
        session_id = get_atuin_session_for_window(location.pane.id, verbose=verbose)
        last_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose) if session_id else None
        rows.append((location, _resolve_display_command(location.pane, last_cmd)))
    return rows


def _render_show_table(rows: list[tuple[PaneLocation, str]]) -> None:
    header = (
        f"{'Kitty WinID':>10} | {'Tab':>5} | {'Title':<{_TITLE_WIDTH}} | "
        f"{'Command':<{_CMD_WIDTH}} | {'CWD':<{_CWD_WIDTH}} | {'PID':>5} | "
        f"{'FG':<{_FG_WIDTH}} | {'SIZE':<{_SIZE_WIDTH}} | "
        f"{'Active':<{_ACTIVE_WIDTH}}"
    )
    click.secho(header, fg="cyan", bold=True)
    click.secho("-" * len(header), fg="cyan")

    first_os = True
    for os_id, os_group in groupby(rows, key=lambda entry: entry[0].os_window.id or ""):
        os_rows = list(os_group)
        if not os_rows:
            continue
        if not first_os:
            click.echo()
        first_os = False
        os_label = os_id or "(unknown os window)"
        os_active_suffix = " (active)" if any(row[0].os_window.is_active for row in os_rows) else ""
        click.secho(f"OS Window {os_label}{os_active_suffix}", fg="cyan")
        for tab_id, tab_group in groupby(os_rows, key=lambda entry: entry[0].tab.id or ""):
            tab_rows = list(tab_group)
            if not tab_rows:
                continue
            tab_label = tab_id or "(no tab id)"
            tab_active_suffix = " (active)" if any(row[0].tab.is_active for row in tab_rows) else ""
            tab_hint = _tab_title_hint(tab_rows)
            click.echo(f"  Tab {tab_label}{tab_active_suffix}{tab_hint}")
            for location, display_cmd in tab_rows:
                _print_show_row(location, display_cmd)


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
def show(*, verbose: bool, as_json: bool) -> None:
    """Show each open Kitty window/tab and its last Atuin command."""
    if not (os.environ.get("KITTY_WINDOW_ID") and os.environ.get("ATUIN_SESSION")) and not as_json:
        click.secho(
            "[INFO] Optional Atuin history association is not active in this shell; "
            "Kitty-only results remain available. Run 'catherd doctor' for details.",
            fg="yellow",
            err=True,
        )

    state = get_kitty_state(verbose=verbose)
    if state is None:
        click.echo("[error] Could not get Kitty windows. See error messages above.", err=True)
        return
    rows = _prepare_show_rows(state, verbose=verbose)
    if not rows:
        click.echo("[warning] No Kitty windows/tabs found. Is Kitty running?", err=True)
        return

    if as_json:
        click.echo(json.dumps(list(starmap(_serialize_pane, rows)), indent=2))
        return

    _render_show_table(rows)


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
@click.option("--pretty", is_flag=True, help="Pretty-print the JSON output")
def inspect(*, verbose: bool, pretty: bool) -> None:
    """Show the richest per-window Kitty + Atuin dataset as JSON."""
    state = get_kitty_state(verbose=verbose)
    if state is None:
        click.echo("[error] Could not get Kitty windows. See error messages above.", err=True)
        return
    locations = list(state.iter_panes())
    if not locations:
        click.echo("[warning] No Kitty windows/tabs found. Is Kitty running?", err=True)
        return

    payloads: list[dict[str, str | int | bool | None]] = []
    for location in locations:
        pane = location.pane
        session_id = get_atuin_session_for_window(pane.id, verbose=verbose)
        session_path = get_session_file(pane.id)
        session_content: str | None = None
        if session_path.exists():
            session_content = session_path.read_text(encoding="utf-8").strip()
        atuin_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose) if session_id else None
        display_cmd = _resolve_display_command(pane, atuin_cmd)
        payload = _serialize_pane(location, display_cmd)
        payload.update({
            "atuin_session_id": session_id,
            "session_file": str(session_path),
            "session_content": session_content,
        })
        payloads.append(payload)

    click.echo(json.dumps(payloads, indent=2 if pretty else None))


def _install_shell_snippet(*, force_shell: str | None, dry_run: bool) -> None:
    shell = get_shell_info(force_shell)
    rc_path = get_shell_rc_path(shell)
    snippet_marker = "# catherd atuin/kitty sync snippet"
    snippet_block = (
        snippet_marker + "\n" + load_snippet_for_shell(shell).rstrip() + "\n# end catherd atuin/kitty sync\n"
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


@main.command("install")
@click.option("--shell", "force_shell", help="Force install for this shell (zsh, bash, fish, csh)")
@click.option("--dry-run", is_flag=True)
def install_shell_snippet(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Install the Atuin/Kitty session sync snippet to your shell startup file (idempotent)."""
    try:
        _install_shell_snippet(force_shell=force_shell, dry_run=dry_run)
    except ValueError as err:
        raise click.ClickException(str(err)) from err


@main.command("uninstall")
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
    state: KittyState, *, verbose: bool = False
) -> tuple[list, list, list, list, list[str]]:
    ok = []
    missing_file = []
    corrupt_file = []
    missing_command = []
    session_map: dict[str, list[str]] = {}
    notes: list[str] = []
    for location in state.iter_panes():
        pane = location.pane
        session_path = get_session_file(pane.id)
        if not session_path.exists():
            missing_file.append(location)
        else:
            content = session_path.read_text(encoding="utf-8").strip()
            if not content or not content.split():
                corrupt_file.append((location, content))
            else:
                session_id = content.split()[0]
                session_map.setdefault(session_id, []).append(pane.id)
                tokens = content.split()
                if len(tokens) >= MIN_SESSION_TOKENS:
                    declared_window = tokens[1]
                    if declared_window != pane.id:
                        notes.append(
                            f"session file {session_path} references window {declared_window} but we expected {pane.id}"
                        )
                last_cmd = get_last_command_for_atuin_session(session_id, verbose=verbose)
                if _is_missing_or_error_command(last_cmd):
                    missing_command.append((location, content, last_cmd))
                else:
                    ok.append((location, content, last_cmd))
    for session_id, pane_ids in session_map.items():
        if len(pane_ids) > 1:
            notes.append(f"duplicate ATUIN_SESSION {session_id} across windows {', '.join(sorted(pane_ids))}")
    return ok, missing_file, corrupt_file, missing_command, notes


def _gather_window_metadata(pane: Pane) -> list[str]:
    metadata: list[str] = []
    if pane.pid is not None:
        metadata.append(f"PID: {pane.pid}")
    if pane.cwd:
        metadata.append(f"CWD: {pane.cwd}")
    if pane.foreground_cmd:
        metadata.append(f"FG: {pane.foreground_cmd}")
    if pane.tty:
        metadata.append(f"TTY: {pane.tty}")
    return metadata


def _gather_window_hints(pane: Pane) -> list[str]:
    hints: list[str] = []
    if pane.cwd is None:
        hints.append("cwd unavailable; enable Kitty shell integration if desired.")
    if not pane.foreground_cmd:
        hints.append("foreground command unavailable; ensure Kitty shell integration is enabled.")
    if pane.tty is None:
        hints.append("tty unavailable; enable Kitty shell integration for richer metadata.")
    if pane.pid is None:
        hints.append("pid unavailable; ensure Kitty shell integration is enabled for richer metadata.")
    return hints


def _print_kitty_window_metadata(pane: Pane) -> None:
    metadata = _gather_window_metadata(pane)
    if metadata:
        click.echo(f"      Kitty metadata: {', '.join(metadata)}")
    else:
        click.echo("      Kitty metadata unavailable; enable Kitty shell integration for richer info.")

    for hint in _gather_window_hints(pane):
        click.echo(f"      Hint: {hint}")


def _print_ok_windows(ok: list[tuple[PaneLocation, str, str]]) -> None:
    if not ok:
        return
    click.secho("[OK] Windows with valid Atuin session file:", fg="green")
    for location, content, last_cmd in ok:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        click.echo(f"      Content: '{content}'")
        click.echo(f"      Atuin last command: {last_cmd}")
        _print_kitty_window_metadata(pane)


def _print_missing_files(missing_file: list[PaneLocation]) -> None:
    if not missing_file:
        return
    click.secho("[WARN] Windows missing session file (sync inactive):", fg="yellow")
    for location in missing_file:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        _print_kitty_window_metadata(pane)
    click.echo("    -> The Atuin/Kitty sync snippet is NOT active in these windows/tabs.")
    click.echo("    -> To activate: Ensure your shell sources the sync snippet and RESTART this Kitty tab/window.")


def _print_corrupt_windows(corrupt_file: list[tuple[PaneLocation, str]]) -> None:
    if not corrupt_file:
        return
    click.secho("[FAIL] Windows with session file but missing Atuin session ID:", fg="red")
    for location, content in corrupt_file:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        click.echo(f"      Content: '{content}' (empty or corrupt)")
        _print_kitty_window_metadata(pane)
    click.echo("    -> To fix: restart your shell/tab.")


def _print_missing_command_windows(missing_command: list[tuple[PaneLocation, str, str]]) -> None:
    if not missing_command:
        return
    click.secho("[WARN] Windows with session file but no command in Atuin:", fg="yellow")
    for location, content, last_cmd in missing_command:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        click.echo(f"      Content: '{content}'")
        click.echo(f"      Atuin last command: {last_cmd}")
        _print_kitty_window_metadata(pane)
    click.echo("    -> To fix: ensure Atuin is tracking this session's history.")


def _print_sync_notes(notes: list[str]) -> None:
    if not notes:
        return
    click.secho("[INFO] Additional sync observations:", fg="yellow")
    for note in notes:
        click.echo(f"  - {note}")


def print_kitty_session_diagnostics(state: KittyState, *, verbose: bool = False) -> None:
    ok, missing_file, corrupt_file, missing_command, notes = _collect_kitty_session_diagnostics(state, verbose=verbose)
    total = state.pane_count
    click.secho(f"[OK] Found {total} Kitty window(s).\n", fg="green")

    _print_ok_windows(ok)
    _print_missing_files(missing_file)
    _print_corrupt_windows(corrupt_file)
    _print_missing_command_windows(missing_command)
    _print_sync_notes(notes)

    synced = len(ok)
    if synced == 0:
        click.secho(
            "[INFO] Optional Atuin history enrichment is not active in any open windows.\n"
            "To add per-pane completed-command history, enable the Atuin association snippet, "
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
def tui() -> None:
    """Interactively organize Kitty OS windows, tabs, and panes."""
    try:
        run_tui()
    except KittyClientError as err:
        raise click.ClickException(str(err)) from err


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

    state = get_kitty_state(verbose=verbose)
    if state is None or state.pane_count == 0:
        click.secho("[FAIL] No Kitty windows found. Is Kitty running and are there open windows/tabs?", fg="red")
        raise SystemExit(1)

    print_kitty_session_diagnostics(state, verbose=verbose)

    if not is_sync_active_in_this_shell():
        click.secho(
            "TIP: Run 'catherd install' to set up the session sync automatically for your shell.",
            fg="blue",
        )
    click.secho("=== Doctor check complete ===", fg="blue")


if __name__ == "__main__":
    main()
