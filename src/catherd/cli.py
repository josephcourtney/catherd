import json
import os
import shutil
import tempfile
from itertools import groupby, starmap
from pathlib import Path
from typing import Final

import click

from .activity import get_atuin_session_for_window
from .atuin import get_atuin_history_db_path, get_last_command_for_atuin_session
from .config import get_session_file
from .kitty import KittyClientError, get_kitty_state
from .model import KittyState, Pane, PaneLocation
from .shell import (
    SUPPORTED_SHELLS,
    append_managed_snippet,
    get_shell_rc_path,
    load_snippet_for_shell,
    managed_snippet_block,
    managed_snippet_state,
    replace_managed_snippet,
    validate_snippet_for_shell,
)
from .tui import run_tui


def is_sync_active_in_this_shell() -> bool:
    kitty_id = os.environ.get("KITTY_WINDOW_ID")
    atuin_sess = os.environ.get("ATUIN_SESSION")
    if not kitty_id or not atuin_sess:
        return False
    session_path = get_session_file(str(kitty_id))
    try:
        if not session_path.exists():
            return False
        content = session_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
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
@click.version_option(package_name="catherd", prog_name="catherd")
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


_SHOW_FALLBACK_WIDTH: Final[int] = 120
_SHOW_MIN_WIDTH: Final[int] = 40
_SHOW_INLINE_CWD_WIDTH: Final[int] = 92
_SHOW_CWD_TARGET_WIDTH: Final[int] = 38


def _normalize_human_text(value: str | None) -> str:
    """Collapse display-only whitespace without changing machine-readable values."""
    return " ".join(value.split()) if value else ""


def _display_cwd(cwd: str | None) -> str:
    """Return a compact human-readable working directory."""
    normalized = _normalize_human_text(cwd)
    if not normalized:
        return ""
    home = str(Path.home())
    if normalized == home:
        return "~"
    prefix = home + os.sep
    if normalized.startswith(prefix):
        return "~" + os.sep + normalized[len(prefix) :]
    return normalized


def _show_width() -> int:
    """Return the usable terminal width for human show output."""
    return max(_SHOW_MIN_WIDTH, shutil.get_terminal_size(fallback=(_SHOW_FALLBACK_WIDTH, 24)).columns)


def _fit_human(value: str | None, width: int) -> str:
    """Normalize and truncate text to a display width."""
    return _truncate(_normalize_human_text(value), max(1, width))


def _tab_title_hint(tab_rows: list[tuple[PaneLocation, str]]) -> str:
    title = _normalize_human_text(tab_rows[0][0].tab.title)
    return f" — {title}" if title else ""


def _pane_size(pane: Pane) -> str | None:
    if pane.cols is None and pane.rows is None:
        return None
    return f"{pane.cols or '?'}×{pane.rows or '?'}"


def _pane_verbose_summary(pane: Pane) -> str:
    parts = [f"id {pane.id}"]
    if pane.pid is not None:
        parts.append(f"pid {pane.pid}")
    if size := _pane_size(pane):
        parts.append(size)
    if pane.at_prompt is True:
        parts.append("at prompt")
    elif pane.at_prompt is False:
        parts.append("running")
    if pane.tty:
        parts.append(f"tty {pane.tty}")
    foreground = _normalize_human_text(pane.foreground_cmd)
    if foreground:
        parts.append(f"fg {foreground}")
    return " · ".join(parts)


def _prepare_show_rows(state: KittyState) -> list[tuple[PaneLocation, str]]:
    rows: list[tuple[PaneLocation, str]] = []
    for location in state.iter_panes():
        session_id = get_atuin_session_for_window(location.pane.id, verbose=False)
        last_cmd = get_last_command_for_atuin_session(session_id, verbose=False) if session_id else None
        rows.append((location, _resolve_display_command(location.pane, last_cmd)))
    return rows


def _print_show_pane(location: PaneLocation, display_cmd: str, *, width: int, verbose: bool) -> None:
    pane = location.pane
    marker = "●" if pane.is_active else " "
    prefix = f"    {marker} "
    command = _normalize_human_text(display_cmd) or _DISPLAY_COMMAND_FALLBACK
    cwd = _display_cwd(pane.cwd)

    if width >= _SHOW_INLINE_CWD_WIDTH and cwd:
        available = max(1, width - len(prefix))
        cwd_width = min(_SHOW_CWD_TARGET_WIDTH, max(18, available // 3))
        command_width = max(1, available - cwd_width - 2)
        click.echo(f"{prefix}{_fit_human(command, command_width):<{command_width}}  {_fit_human(cwd, cwd_width)}")
    else:
        click.echo(prefix + _fit_human(command, width - len(prefix)))
        if cwd:
            cwd_prefix = "      "
            click.echo(cwd_prefix + _fit_human(cwd, width - len(cwd_prefix)))

    if verbose:
        detail_prefix = "      "
        click.echo(detail_prefix + _fit_human(_pane_verbose_summary(pane), width - len(detail_prefix)))


def _render_show_hierarchy(
    rows: list[tuple[PaneLocation, str]],
    *,
    verbose: bool,
    width: int | None = None,
) -> None:
    resolved_width = width or _show_width()
    first_os = True
    for os_id, os_group in groupby(rows, key=lambda entry: entry[0].os_window.id or ""):
        os_rows = list(os_group)
        if not os_rows:
            continue
        if not first_os:
            click.echo()
        first_os = False

        os_window = os_rows[0][0].os_window
        os_label = os_id or "(unknown)"
        os_title = _normalize_human_text(os_window.title)
        title_suffix = f" — {os_title}" if os_title else ""
        focus_suffix = " • focused" if os_window.is_active else ""
        click.secho(_fit_human(f"OS Window {os_label}{title_suffix}{focus_suffix}", resolved_width), bold=True)

        for tab_id, tab_group in groupby(os_rows, key=lambda entry: entry[0].tab.id or ""):
            tab_rows = list(tab_group)
            if not tab_rows:
                continue
            tab_label = tab_id or "(unknown)"
            focus_suffix = " • focused" if any(row[0].tab.is_active for row in tab_rows) else ""
            tab_line = f"  Tab {tab_label}{_tab_title_hint(tab_rows)}{focus_suffix}"
            click.echo(_fit_human(tab_line, resolved_width))
            for location, display_cmd in tab_rows:
                _print_show_pane(location, display_cmd, width=resolved_width, verbose=verbose)


def _require_kitty_state() -> KittyState:
    state = get_kitty_state(verbose=False)
    if state is None:
        raise click.ClickException("Could not read Kitty state.")
    if state.pane_count == 0:
        raise click.ClickException("No Kitty panes found. Is Kitty running with remote control enabled?")
    return state


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show pane IDs and process/layout details")
@click.option("--json", "as_json", is_flag=True, help="Output stable machine-readable JSON")
def show(*, verbose: bool, as_json: bool) -> None:
    """Show the current Kitty hierarchy and best available command."""
    state = _require_kitty_state()
    rows = _prepare_show_rows(state)

    if as_json:
        click.echo(json.dumps(list(starmap(_serialize_pane, rows)), indent=2))
        return

    _render_show_hierarchy(rows, verbose=verbose)


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
@click.option("--pretty", is_flag=True, help="Pretty-print the JSON output")
def inspect(*, verbose: bool, pretty: bool) -> None:
    """Show the richest per-window Kitty + Atuin dataset as JSON."""
    if verbose:
        click.echo("[INFO] inspect already emits full fields; verbose diagnostics stay on stderr.", err=True)
    state = _require_kitty_state()
    locations = list(state.iter_panes())

    payloads: list[dict[str, str | int | bool | None]] = []
    for location in locations:
        pane = location.pane
        session_id = get_atuin_session_for_window(pane.id, verbose=False)
        session_path = get_session_file(pane.id)
        session_content: str | None = None
        try:
            if session_path.exists():
                session_content = session_path.read_text(encoding="utf-8").strip()
        except OSError:
            session_content = None
        atuin_cmd = get_last_command_for_atuin_session(session_id, verbose=False) if session_id else None
        display_cmd = _resolve_display_command(pane, atuin_cmd)
        payload = _serialize_pane(location, display_cmd)
        payload.update({
            "atuin_session_id": session_id,
            "session_file": str(session_path),
            "session_content": session_content,
        })
        payloads.append(payload)

    click.echo(json.dumps(payloads, indent=2 if pretty else None))


def _atomic_write_text(path: Path, contents: str) -> None:
    """Replace a text file atomically, preserving its mode when it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent, text=True)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(contents)
        if path.exists():
            shutil.copymode(path, temporary_path)
        Path(temporary_path).replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _backup_rc_file(rc_path: Path, suffix: str) -> Path:
    backup = rc_path.with_suffix(rc_path.suffix + suffix)
    shutil.copy2(rc_path, backup)
    return backup


def _rc_write_target(rc_path: Path) -> Path:
    """Return the file to replace without destroying an rc-file symlink."""
    if not rc_path.is_symlink():
        return rc_path
    try:
        return rc_path.resolve(strict=True)
    except (OSError, RuntimeError) as err:
        msg = f"Refusing to replace dangling, cyclic, or unreadable rc-file symlink {rc_path}: {err}"
        raise ValueError(msg) from err


def _enable_atuin_integration(*, force_shell: str | None, dry_run: bool) -> None:
    shell = get_shell_info(force_shell)
    rc_path = get_shell_rc_path(shell)
    write_target = _rc_write_target(rc_path)

    contents = rc_path.read_text(encoding="utf-8") if rc_path.exists() else ""
    state = managed_snippet_state(contents)
    if state == "current":
        click.secho(f"[OK] Atuin integration already enabled in {rc_path}", fg="green")
        return

    # Generated code must parse before catherd creates backups or modifies startup files.
    validate_snippet_for_shell(shell)
    block = managed_snippet_block(shell)

    if state == "legacy":
        new_contents, replaced = replace_managed_snippet(contents, block)
        if not replaced:
            msg = "Legacy catherd integration marker disappeared while preparing migration"
            raise click.ClickException(msg)
        action = "migrate the legacy catherd Atuin integration"
    else:
        new_contents = append_managed_snippet(contents, block)
        action = "enable the catherd Atuin integration"

    if dry_run:
        click.echo(f"[DRY-RUN] Would {action} in {rc_path}", err=True)
        click.secho("[OK] Dry-run complete; no changes made.", fg="green")
        return

    backup: Path | None = None
    if rc_path.exists():
        backup = _backup_rc_file(rc_path, ".catherd.bak")
    _atomic_write_text(write_target, new_contents)

    if state == "legacy":
        click.secho(f"[OK] Migrated legacy Atuin integration in {rc_path}", fg="green")
    else:
        click.secho(f"[OK] Atuin integration enabled in {rc_path}", fg="green")
    if backup is not None:
        click.echo(f"Backup: {backup}")
    click.secho(
        "Restart or re-source the affected shell for the change to take effect.",
        fg="yellow",
    )


def _disable_atuin_integration(*, force_shell: str | None, dry_run: bool) -> None:
    shell = get_shell_info(force_shell)
    rc_path = get_shell_rc_path(shell)
    write_target = _rc_write_target(rc_path)
    if not rc_path.exists():
        click.secho(f"[INFO] No rc file found at {rc_path}; Atuin integration is not enabled there.", fg="yellow")
        return

    contents = rc_path.read_text(encoding="utf-8")
    state = managed_snippet_state(contents)
    if state == "absent":
        click.secho(f"[INFO] No catherd Atuin integration found in {rc_path}", fg="yellow")
        return

    new_contents, removed = replace_managed_snippet(contents, None)
    if not removed:
        msg = "catherd integration marker disappeared while preparing removal"
        raise click.ClickException(msg)

    if dry_run:
        click.echo(f"[DRY-RUN] Would disable the catherd Atuin integration in {rc_path}", err=True)
        return

    backup = _backup_rc_file(rc_path, ".catherd.disable.bak")
    _atomic_write_text(write_target, new_contents)
    migrated = " legacy" if state == "legacy" else ""
    click.secho(f"[OK] Removed{migrated} Atuin integration from {rc_path}", fg="green")
    click.echo(f"Backup: {backup}")


@main.group("atuin")
def atuin_group() -> None:
    """Manage optional Atuin completed-command history enrichment."""


@atuin_group.command("enable")
@click.option("--shell", "force_shell", help=f"Shell to configure ({', '.join(SUPPORTED_SHELLS)})")
@click.option("--dry-run", is_flag=True, help="Show the planned rc-file change without writing it")
def atuin_enable(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Enable catherd's optional Kitty-pane to Atuin-session association."""
    try:
        _enable_atuin_integration(force_shell=force_shell, dry_run=dry_run)
    except (OSError, ValueError) as err:
        raise click.ClickException(str(err)) from err


@atuin_group.command("disable")
@click.option("--shell", "force_shell", help=f"Shell to configure ({', '.join(SUPPORTED_SHELLS)})")
@click.option("--dry-run", is_flag=True, help="Show the planned rc-file change without writing it")
def atuin_disable(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Disable catherd's optional Atuin association and preserve an rc backup."""
    try:
        _disable_atuin_integration(force_shell=force_shell, dry_run=dry_run)
    except (OSError, ValueError) as err:
        raise click.ClickException(str(err)) from err


@main.command("install", hidden=True)
@click.option("--shell", "force_shell")
@click.option("--dry-run", is_flag=True)
def install_shell_snippet(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Use the deprecated compatibility alias for catherd atuin enable."""
    click.echo("[DEPRECATED] Use 'catherd atuin enable' instead.", err=True)
    try:
        _enable_atuin_integration(force_shell=force_shell, dry_run=dry_run)
    except (OSError, ValueError) as err:
        raise click.ClickException(str(err)) from err


@main.command("uninstall", hidden=True)
@click.option("--shell", "force_shell")
@click.option("--dry-run", is_flag=True)
def uninstall(*, force_shell: str | None = None, dry_run: bool) -> None:
    """Use the deprecated compatibility alias for catherd atuin disable."""
    click.echo("[DEPRECATED] Use 'catherd atuin disable' instead.", err=True)
    try:
        _disable_atuin_integration(force_shell=force_shell, dry_run=dry_run)
    except (OSError, ValueError) as err:
        raise click.ClickException(str(err)) from err


def print_shell_snippet(shell: str) -> None:
    try:
        rc_path = get_shell_rc_path(shell)
        snippet = load_snippet_for_shell(shell)
        click.echo(f"Optional Atuin association snippet for {shell} ({rc_path}):\n")
        click.echo(snippet)
        click.echo("\nOr run 'catherd atuin enable' to install it safely.")
    except ValueError as err:
        click.echo(f"[INFO] {err}")


def print_env_diagnostics() -> None:
    kitty_id = os.environ.get("KITTY_WINDOW_ID")
    atuin_sess = os.environ.get("ATUIN_SESSION")
    if not kitty_id:
        click.secho("[WARN] $KITTY_WINDOW_ID is not set in this shell. Are you inside Kitty?", fg="yellow")
    if not atuin_sess:
        click.secho(
            "[INFO] $ATUIN_SESSION is not set; optional Atuin history enrichment is inactive in this shell.",
            fg="yellow",
        )


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
        try:
            if not session_path.exists():
                missing_file.append(location)
                continue
            content = session_path.read_text(encoding="utf-8").strip()
        except OSError as err:
            corrupt_file.append((location, f"unreadable: {err}"))
            continue

        if not content or not content.split():
            corrupt_file.append((location, content))
            continue

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
    click.secho("[OK] Panes with valid Atuin session association:", fg="green")
    for location, content, last_cmd in ok:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        click.echo(f"      Content: '{content}'")
        click.echo(f"      Atuin last command: {last_cmd}")
        _print_kitty_window_metadata(pane)


def _print_missing_files(missing_file: list[PaneLocation]) -> None:
    if not missing_file:
        return
    click.secho("[INFO] Panes without optional Atuin session association:", fg="yellow")
    for location in missing_file:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        _print_kitty_window_metadata(pane)
    click.echo("    -> Kitty-only inspection and organization remain available.")
    click.echo("    -> To add completed-command history: run 'catherd atuin enable', then restart the shell.")


def _print_corrupt_windows(corrupt_file: list[tuple[PaneLocation, str]]) -> None:
    if not corrupt_file:
        return
    click.secho("[WARN] Panes with unusable Atuin association state:", fg="yellow")
    for location, content in corrupt_file:
        pane = location.pane
        click.echo(f"  - WinID: {pane.id}, TabID: {location.tab.id}, Title: {pane.title[:30]}")
        click.echo(f"      Content: '{content}' (empty or corrupt)")
        _print_kitty_window_metadata(pane)
    click.echo("    -> To fix: restart your shell/tab.")


def _print_missing_command_windows(missing_command: list[tuple[PaneLocation, str, str]]) -> None:
    if not missing_command:
        return
    click.secho("[WARN] Panes associated with Atuin but without completed-command history:", fg="yellow")
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
    click.secho(f"[OK] Found {total} Kitty pane(s).\n", fg="green")

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
            f"[INFO] Optional Atuin history enrichment active in {synced}/{total} windows.",
            fg=color,
        )


def _print_core_doctor_summary(state: KittyState) -> None:
    panes = [location.pane for location in state.iter_panes()]
    total = len(panes)
    click.secho(f"  [OK] Kitty remote control: {total} pane(s) discovered", fg="green")
    shell = get_shell_info()
    if shell:
        click.echo(f"  [INFO] Current shell: {shell}")

    cwd_count = sum(pane.cwd is not None for pane in panes)
    command_count = sum(bool(pane.current_command or pane.foreground_cmd) for pane in panes)
    tty_count = sum(pane.tty is not None for pane in panes)
    click.echo(
        "  [INFO] Kitty metadata: "
        f"CWD {cwd_count}/{total}, command {command_count}/{total}, TTY {tty_count}/{total}"
    )
    if tty_count < total:
        click.echo(
            "  [INFO] Kitty shell integration can provide richer terminal metadata; "
            "it is separate from catherd's optional Atuin association."
        )


def _print_atuin_doctor_summary(state: KittyState, *, verbose: bool) -> None:
    ok, missing_file, corrupt_file, missing_command, notes = _collect_kitty_session_diagnostics(
        state,
        verbose=verbose,
    )
    total = state.pane_count
    associated = len(ok) + len(missing_command)
    history = len(ok)

    if associated == total and not corrupt_file:
        click.secho(f"    [OK] Pane association: {associated}/{total}", fg="green")
    elif associated == 0:
        click.secho(
            "    [INFO] Pane association is not active; core catherd behavior is unaffected.",
            fg="yellow",
        )
    else:
        click.secho(f"    [INFO] Pane association: {associated}/{total}", fg="yellow")

    if associated:
        click.echo(f"    [INFO] Completed-command history available for {history}/{total} pane(s).")
    if corrupt_file:
        click.secho(f"    [WARN] Unusable association state for {len(corrupt_file)} pane(s).", fg="yellow")
    if notes:
        click.secho(f"    [WARN] {len(notes)} association consistency observation(s).", fg="yellow")

    if verbose:
        click.echo()
        click.echo("    Detailed Atuin state")
        _print_ok_windows(ok)
        _print_missing_files(missing_file)
        _print_corrupt_windows(corrupt_file)
        _print_missing_command_windows(missing_command)
        _print_sync_notes(notes)


def _print_atuin_installation_status() -> None:
    executable = shutil.which("atuin")
    history_db = get_atuin_history_db_path()
    if executable is None:
        click.secho(
            "[INFO] Atuin executable not found on PATH; this does not affect core catherd behavior.",
            fg="yellow",
        )
    else:
        click.secho(f"[OK] Atuin executable: {executable}", fg="green")

    if history_db.exists():
        click.secho(f"[OK] Atuin history database: {history_db}", fg="green")
    else:
        click.secho(f"[INFO] Atuin history database not found at {history_db}", fg="yellow")


@atuin_group.command("doctor")
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
def atuin_doctor(*, verbose: bool = False) -> None:
    """Diagnose only the optional Atuin enrichment integration."""
    click.echo("=== catherd atuin doctor ===")
    _print_atuin_installation_status()
    print_env_diagnostics()
    shell = get_shell_info()
    click.echo(f"[INFO] Detected shell: {shell}")

    state = get_kitty_state(verbose=verbose)
    if state is None or state.pane_count == 0:
        click.secho(
            "[INFO] No Kitty panes are available to inspect for Atuin association; core catherd is unaffected.",
            fg="yellow",
        )
    else:
        print_kitty_session_diagnostics(state, verbose=verbose)

    if not is_sync_active_in_this_shell():
        print_shell_snippet(shell)
    click.secho("=== Atuin integration check complete ===", fg="blue")


@main.command()
def tui() -> None:
    """Interactively organize Kitty OS windows, tabs, and panes."""
    try:
        run_tui()
    except KittyClientError as err:
        raise click.ClickException(str(err)) from err


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show detailed optional-integration diagnostics")
def doctor(*, verbose: bool = False) -> None:
    """Diagnose the core Kitty boundary and optional integrations."""
    click.echo("=== catherd doctor ===")
    click.echo()
    click.echo("Core")
    state = _require_kitty_state()
    _print_core_doctor_summary(state)

    click.echo()
    click.echo("Optional integrations")
    click.echo("  Atuin")
    _print_atuin_doctor_summary(state, verbose=verbose)

    if not is_sync_active_in_this_shell():
        click.echo("    [INFO] Enable completed-command enrichment with 'catherd atuin enable' if desired.")

    click.echo()
    click.secho("=== Doctor check complete ===", fg="blue")


if __name__ == "__main__":
    main()
