import importlib.resources
import os
import shutil
from pathlib import Path

import click

from .config import get_session_file
from .core import (
    get_atuin_session_for_window,
    get_kitty_windows,
    get_last_command_for_atuin_session,
)

__exit_called = False

SHELL_SNIPPET_FILENAMES = {
    "zsh": "catherd_rc_snippet.zsh",
    "bash": "catherd_rc_snippet.bash",
    "fish": "catherd_rc_snippet.fish",
    "csh": "catherd_rc_snippet.csh",
    "tcsh": "catherd_rc_snippet.csh",
}

SHELL_RC_FILES = {
    "zsh": Path("~/.zshrc").expanduser(),
    "bash": Path("~/.bashrc").expanduser(),
    "fish": Path("~/.config/fish/config.fish").expanduser(),
    "csh": Path("~/.cshrc").expanduser(),
    "tcsh": Path("~/.tcshrc").expanduser(),
}


def load_snippet_for_shell(shell: str) -> str:
    """Load the shell snippet text for the given shell name."""
    filename = SHELL_SNIPPET_FILENAMES.get(shell)
    if not filename:
        msg = f"Unknown shell for snippet: {shell}"
        raise ValueError(msg)
    try:
        return importlib.resources.files("catherd.snippets").joinpath(filename).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError, AttributeError) as e:
        return f"# [ERROR] Could not load snippet for {shell}: {e}"


def print_shell_snippet(shell):
    """Print setup instructions and the shell snippet for the detected shell."""
    if shell in SHELL_SNIPPET_FILENAMES:
        rc_path = SHELL_RC_FILES.get(shell, "<your-shell-rc>")
        snippet = load_snippet_for_shell(shell)
        click.echo(f"Add this to your shell rc file ({rc_path}):\n")
        click.echo(snippet)
        click.echo("\nOr run 'catherd install' to do it automatically.")
    else:
        click.echo(
            "[INFO] Unknown shell. See the README or scripts/catherd_rc_snippet.* for setup instructions.\n"
        )


@click.group()
def main():
    """catherd: herd your Kitty windows and Atuin history."""


def is_sync_active_in_this_shell() -> bool:
    """Check if the catherd sync is active in this shell instance."""
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
    # It is active if both IDs match
    return session_id == atuin_sess and str(kitty_id) in content


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
def show(verbose):
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
        session_id = get_atuin_session_for_window(win["id"], verbose=verbose)
        last_cmd = (
            get_last_command_for_atuin_session(session_id, verbose=verbose)
            if session_id
            else "(no session info)"
        )
        click.echo(f"{win['id']:>10} | {win['tab']:>5} | {win['title'][:25]:<25} | {last_cmd}")


def get_shell_info(force_shell=None):
    """Determine the user's shell name, possibly overriding with an explicit argument."""
    shell = force_shell
    if not shell:
        shell_path = os.environ.get("SHELL", "")
        shell = Path(shell_path).name
    return shell


@main.command("install")
@click.option("--shell", "force_shell", help="Force install for this shell (zsh, bash, fish, csh)")
def install_shell_snippet(force_shell):
    """Install the Atuin/Kitty session sync snippet to your shell startup file (idempotent)."""
    shell = get_shell_info(force_shell)
    rc_path = SHELL_RC_FILES.get(shell)
    if rc_path is None or shell not in SHELL_SNIPPET_FILENAMES:
        click.secho("[FAIL] Could not detect shell or unsupported shell. Use --shell option.", fg="red")
        return

    snippet_marker = "# catherd atuin/kitty sync snippet"
    snippet_block = (
        snippet_marker + "\n" + load_snippet_for_shell(shell).rstrip() + "\n# end catherd atuin/kitty sync\n"
    )

    if rc_path.exists():
        contents = rc_path.read_text(encoding="utf-8")
        if snippet_marker in contents:
            click.secho(f"[OK] Snippet already installed in {rc_path}", fg="green")
            return
        shutil.copyfile(rc_path, rc_path.with_suffix(rc_path.suffix + ".catherd.bak"))
    else:
        contents = ""
    with rc_path.open("a", encoding="utf-8") as f:
        f.write("\n\n" + snippet_block + "\n")
    click.secho(f"[OK] Snippet added to {rc_path}", fg="green")
    click.secho(
        "You must restart Kitty tabs/windows or re-source your shell for the change to take effect.",
        fg="yellow",
    )


class DiagnosticReporter:
    """Centralizes printing logic for session diagnostics."""

    def __init__(self, printer=click.echo):
        self.printer = printer

    def report_ok(self, ok):
        self.printer("────────────────────────────────────────────────────────")
        click.secho("[OK] Windows with valid Atuin session file:", fg="green")
        if ok:
            for win, content, last_cmd in ok:
                self.printer(f"  - WinID: {win['id']}, TabID: {win['tab']}, Title: {win['title'][:30]}")
                self.printer(f"      Content: '{content}'")
                self.printer(f"      Atuin last command: {last_cmd}")
        else:
            self.printer("  (none)")

    def report_missing_file(self, missing_file):
        if missing_file:
            self.printer("────────────────────────────────────────────────────────")
            click.secho("[WARN] Windows missing session file (sync inactive):", fg="yellow")
            for win in missing_file:
                self.printer(f"  - WinID: {win['id']}, TabID: {win['tab']}, Title: {win['title'][:30]}")
            self.printer("    -> The Atuin/Kitty sync snippet is NOT active in these windows/tabs.")
            self.printer(
                "    -> To activate: Ensure your shell sources the sync snippet and "
                "RESTART this Kitty tab/window."
            )

    def report_corrupt_file(self, corrupt_file):
        if corrupt_file:
            self.printer("────────────────────────────────────────────────────────")
            click.secho("[FAIL] Windows with session file but missing Atuin session ID:", fg="red")
            for win, content in corrupt_file:
                self.printer(f"  - WinID: {win['id']}, TabID: {win['tab']}, Title: {win['title'][:30]}")
                self.printer(f"      Content: '{content}' (empty or corrupt)")
            self.printer("    -> To fix: restart your shell/tab.")

    def report_missing_command(self, missing_command):
        if missing_command:
            self.printer("────────────────────────────────────────────────────────")
            click.secho("[WARN] Windows with session file but no command in Atuin:", fg="yellow")
            for win, content, last_cmd in missing_command:
                self.printer(f"  - WinID: {win['id']}, TabID: {win['tab']}, Title: {win['title'][:30]}")
                self.printer(f"      Content: '{content}'")
                self.printer(f"      Atuin last command: {last_cmd}")
            self.printer("    -> To fix: ensure Atuin is tracking this session's history.")


def print_kitty_session_diagnostics(windows, *, verbose=False):
    """Diagnose and categorize Kitty/Atuin sync state across windows."""
    ok = []
    missing_file = []
    corrupt_file = []
    missing_command = []

    for win in windows:
        session_path = get_session_file(str(win["id"]))
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

    click.secho(f"[OK] Found {len(windows)} Kitty window(s).\n", fg="green")

    reporter = DiagnosticReporter()
    reporter.report_ok(ok)
    reporter.report_missing_file(missing_file)
    reporter.report_corrupt_file(corrupt_file)
    reporter.report_missing_command(missing_command)

    if not ok:
        click.echo("────────────────────────────────────────────────────────")
        click.secho(
            "[INFO] No session files found for any window.\n"
            "To enable full functionality, add the Atuin/Kitty sync snippet to your shell startup file, "
            "then restart Kitty tabs/windows.",
            fg="yellow",
        )
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


def print_env_diagnostics():
    """Print diagnostic info about Kitty/Atuin environment variables."""
    kitty_id = os.environ.get("KITTY_WINDOW_ID")
    atuin_sess = os.environ.get("ATUIN_SESSION")
    if not kitty_id:
        click.secho("[WARN] $KITTY_WINDOW_ID is not set in this shell. Are you inside Kitty?", fg="yellow")
    if not atuin_sess:
        click.secho("[WARN] $ATUIN_SESSION is not set. Is Atuin initialized in your shell?", fg="yellow")


@main.command()
@click.option("-v", "--verbose", is_flag=True, help="Show verbose/debug output")
def doctor(verbose):
    """Diagnose catherd/Kitty/Atuin integration issues."""
    click.echo("=== catherd doctor ===")

    print_env_diagnostics()

    shell = get_shell_info()
    click.echo(f"[INFO] Detected shell: {shell}")

    # Only print shell snippet suggestion if sync is NOT active in this shell!
    if not is_sync_active_in_this_shell():
        print_shell_snippet(shell)

    windows = get_kitty_windows(verbose=verbose)
    if windows is None or not windows:
        click.secho(
            "[FAIL] No Kitty windows found. Is Kitty running and are there open windows/tabs?", fg="red"
        )
        return

    print_kitty_session_diagnostics(windows, verbose=verbose)

    # Only print TIP if sync not active in this shell!
    if not is_sync_active_in_this_shell():
        click.secho(
            "TIP: Run 'catherd install' to set up the session sync automatically for your shell.",
            fg="blue",
        )
    click.secho("=== Doctor check complete ===", fg="blue")


if __name__ == "__main__":
    main()
