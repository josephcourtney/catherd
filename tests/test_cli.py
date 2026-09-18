import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import catherd.__main__  # noqa: F401
from catherd import cli
from catherd.cli import _collect_kitty_session_diagnostics, print_kitty_session_diagnostics
from catherd.model import KittyState, OsWindow, Pane, Tab

pytestmark = pytest.mark.small


def _state(
    *panes: Pane,
    tab_id: str = "t",
    tab_title: str | None = None,
    os_id: str = "os",
    os_active: bool | None = None,
    tab_active: bool | None = None,
) -> KittyState:
    return KittyState(
        os_windows=(
            OsWindow(
                id=os_id,
                is_active=os_active,
                tabs=(Tab(id=tab_id, title=tab_title, panes=tuple(panes), is_active=tab_active),),
            ),
        )
    )


def _two_tab_state() -> KittyState:
    return KittyState(
        os_windows=(
            OsWindow(
                id="os",
                tabs=(
                    Tab(id="t1", title=None, panes=(Pane(id="a", title="foo"),)),
                    Tab(id="t2", title=None, panes=(Pane(id="b", title="bar"),)),
                ),
            ),
        )
    )


def setup_sync_env(tmp_path, monkeypatch):
    """Simulate a shell with KITTY_WINDOW_ID + ATUIN_SESSION available."""
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("ATUIN_SESSION", "s")
    session_file = tmp_path / "atuin_kitty_1"
    session_file.write_text("s 1")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))


def test_main_entrypoint_exits_zero():
    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0


@patch("catherd.cli.get_kitty_state")
@patch("catherd.cli.get_atuin_session_for_window")
@patch("catherd.cli.get_last_command_for_atuin_session")
def test_show_prints_commands(mock_last, mock_sess, mock_state):
    mock_state.return_value = _two_tab_state()
    mock_sess.side_effect = ["sessA", "sessB"]
    mock_last.side_effect = ["cmdA", "cmdB"]
    result = CliRunner().invoke(cli.main, ["show"])
    assert "Kitty WinID" in result.output
    assert "cmdA" in result.output
    assert "cmdB" in result.output


def test_show_empty_warns():
    with patch("catherd.cli.get_kitty_state", return_value=KittyState(os_windows=())):
        result = CliRunner().invoke(cli.main, ["show"])
    assert "No Kitty windows/tabs found" in result.stderr


def test_show_none_warns():
    with patch("catherd.cli.get_kitty_state", return_value=None):
        result = CliRunner().invoke(cli.main, ["show"])
    assert "Could not get Kitty windows" in result.stderr


def test_json_output(tmp_path, monkeypatch):
    setup_sync_env(tmp_path, monkeypatch)
    state = _state(Pane(id="1", title="T"))
    monkeypatch.setattr(cli, "get_kitty_state", lambda **_kwargs: state)
    monkeypatch.setattr(cli, "get_atuin_session_for_window", lambda *_args, **_kwargs: "s")
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "ls")

    result = CliRunner().invoke(cli.main, ["show", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    item = data[0]
    assert item["window_id"] == "1"
    assert item["tab"] == "t"
    assert item["title"] == "T"
    assert item["last_command"] == "ls"


def test_inspect_outputs_full_metadata(tmp_path, monkeypatch):
    session_file = tmp_path / "atuin_kitty_win"
    session_file.write_text("sessA win")
    state = _state(
        Pane(
            id="win",
            title="title",
            pid=1234,
            cwd=str(tmp_path),
            foreground_cmd="bash",
            tty="/dev/pts/42",
        ),
        tab_id="tab",
        os_id="os-1",
    )

    monkeypatch.setattr(cli, "get_kitty_state", lambda **_kwargs: state)
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "echo hi")

    result = CliRunner().invoke(cli.main, ["inspect"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["window_id"] == "win"
    assert payload[0]["os_window_id"] == "os-1"
    assert payload[0]["pid"] == 1234
    assert payload[0]["cwd"] == str(tmp_path)
    assert payload[0]["foreground_cmd"] == "bash"
    assert payload[0]["tty"] == "/dev/pts/42"
    assert payload[0]["atuin_session_id"] == "sessA"
    assert payload[0]["session_content"] == "sessA win"


def test_show_env_verbose(monkeypatch):
    state = _state(Pane(id="w", title="tit"))
    monkeypatch.setattr(cli, "get_kitty_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(cli, "get_atuin_session_for_window", lambda *_args, **_kwargs: None)
    result = CliRunner().invoke(cli.main, ["show", "-v"])
    assert "(no command)" in result.output


def test_preflight_only_on_show(tmp_path, monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)

    with patch("catherd.cli.get_kitty_state", return_value=KittyState(os_windows=())):
        show_result = CliRunner().invoke(cli.main, ["show"])
    assert show_result.exit_code == 0
    assert "Run 'catherd doctor'" in show_result.stderr or "diagnose" in show_result.stderr

    monkeypatch.setenv("HOME", str(tmp_path))
    rc = tmp_path / ".bashrc"
    rc.write_text("")
    dry_run = CliRunner().invoke(cli.main, ["install", "--shell", "bash", "--dry-run"])
    assert dry_run.exit_code == 0
    assert "DRY-RUN" in dry_run.stderr


def test_install_shell_snippet(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "get_shell_info", lambda *_args, **_kwargs: "bash")
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda *_args, **_kwargs: "# mock snippet")
    fake_rc = tmp_path / "rc"
    fake_rc.write_text("")
    with patch("catherd.cli.get_shell_rc_path", return_value=fake_rc), patch("shutil.copyfile"):
        result = CliRunner().invoke(cli.main, ["install", "--shell", "bash"])
        assert "Snippet added" in result.output or "already installed" in result.output


def test_install_shell_snippet_unsupported(monkeypatch):
    monkeypatch.setattr(cli, "get_shell_info", lambda *_args, **_kwargs: "badsh")
    result = CliRunner().invoke(cli.main, ["install"])
    assert result.exit_code == 1
    assert "Unknown shell" in result.stderr


def test_install_shell_snippet_already_installed(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    rc.write_text("# catherd atuin/kitty sync snippet\n…")
    monkeypatch.setattr(cli, "get_shell_info", lambda *_: "bash")
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda *_: "# snippet")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_: rc)
    result = CliRunner().invoke(cli.main, ["install", "--shell", "bash"])
    assert "Snippet already installed" in result.output


def test_install_dry_run(tmp_path, monkeypatch):
    rc = tmp_path / ".bashrc"
    rc.write_text("orig")
    monkeypatch.setenv("HOME", str(tmp_path))
    result = CliRunner().invoke(cli.main, ["install", "--shell", "bash", "--dry-run"])
    assert result.exit_code == 0
    assert "DRY-RUN" in result.stderr or "Would append" in result.stderr
    assert rc.read_text() == "orig"


def test_uninstall_dry_run_and_remove(tmp_path, monkeypatch):
    content = "line1\n# catherd atuin/kitty sync snippet\nfoo\n# end catherd atuin/kitty sync\nline2"
    rc = tmp_path / ".bashrc"
    rc.write_text(content)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")

    dry = CliRunner().invoke(cli.main, ["uninstall", "--dry-run"])
    assert dry.exit_code == 0
    assert "DRY-RUN" in dry.stderr

    res = CliRunner().invoke(cli.main, ["uninstall"])
    assert res.exit_code == 0
    assert "Snippet removed" in res.output
    assert "catherd atuin/kitty" not in rc.read_text()
    assert (tmp_path / ".bashrc.catherd.uninstall.bak").exists()


def test_exit_code_on_unknown_shell_install():
    result = CliRunner().invoke(cli.main, ["install", "--shell", "noshell"])
    assert result.exit_code == 1
    assert "Unknown shell" in result.stderr


def test_errors_and_diagnostics_to_stderr(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    result = CliRunner().invoke(cli.main, ["uninstall"])
    assert result.exit_code == 1
    assert "No rc file found" in result.stderr


@patch("catherd.cli.get_kitty_state", return_value=KittyState(os_windows=()))
def test_doctor_no_windows(mock_state):
    _ = mock_state
    result = CliRunner().invoke(cli.main, ["doctor"])
    assert result.exit_code == 1
    assert "No Kitty windows found" in result.output


@patch("catherd.cli.get_kitty_state")
def test_doctor_basic(mock_state):
    mock_state.return_value = _state(Pane(id="X", title="Y"), tab_id="T")
    with (
        patch("catherd.cli.get_session_file") as gsf,
        patch("catherd.cli.get_last_command_for_atuin_session") as glc,
    ):
        gsf.return_value.exists.return_value = False
        glc.return_value = None
        result = CliRunner().invoke(cli.main, ["doctor"])
    assert "sync snippet" in result.output or "Add this to your shell rc file" in result.output


def test_is_sync_env_missing(monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    assert not cli.is_sync_active_in_this_shell()


def test_is_sync_success(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "a")
    monkeypatch.setenv("ATUIN_SESSION", "sess")
    session_file = tmp_path / "f"
    session_file.write_text("sess a")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    assert cli.is_sync_active_in_this_shell()


def test__collect_kitty_session_diagnostics(monkeypatch, tmp_path):
    state = _state(Pane(id="id", title="title"), tab_id="tab")
    session_file = tmp_path / "atuin_kitty_id"
    session_file.write_text("sessid")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "cmd")
    ok, missing, corrupt, missing_cmd, notes = _collect_kitty_session_diagnostics(state, verbose=True)
    assert ok or missing or corrupt or missing_cmd
    assert notes == []


def test__collect_kitty_session_diagnostics_branches(tmp_path, monkeypatch):
    state = _state(
        Pane(id="a", title=""),
        Pane(id="b", title=""),
        Pane(id="c", title=""),
        Pane(id="d", title=""),
        tab_id="",
    )

    def fake_session_file(window_id):
        p = tmp_path / f"atuin_kitty_{window_id}"
        if window_id == "b":
            p.write_text("")
        elif window_id == "c":
            p.write_text("sess_c")
        elif window_id == "d":
            p.write_text("sess_d")
        return p

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "get_session_file", fake_session_file)

    def fake_last(session_id, *, verbose=False):
        if session_id == "sess_c" and verbose:
            return "(sqlite error)"
        return "cmd"

    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", fake_last)

    ok, missing, corrupt, missing_cmd, notes = _collect_kitty_session_diagnostics(state, verbose=True)
    assert ["a"] == [location.pane.id for location in missing]
    assert ["b"] == [location.pane.id for location, _ in corrupt]
    assert len(missing_cmd) == 1
    assert missing_cmd[0][0].pane.id == "c"
    assert len(ok) == 1
    assert ok[0][0].pane.id == "d"
    assert notes == []


def test_print_kitty_session_diagnostics_all_branches(monkeypatch, capsys):
    state = _state(
        Pane(id="a", title="title"),
        Pane(id="b", title="title2"),
        Pane(id="c", title="title3"),
        Pane(id="d", title="title4"),
    )
    locations = list(state.iter_panes())
    ok = [(locations[0], "sessid", "cmd")]
    missing_file = [locations[1]]
    corrupt_file = [(locations[2], "")]
    missing_command = [(locations[3], "sessid", "(sqlite error)")]

    monkeypatch.setattr(
        cli,
        "_collect_kitty_session_diagnostics",
        lambda *_args, **_kwargs: (ok, missing_file, corrupt_file, missing_command, []),
    )
    print_kitty_session_diagnostics(state, verbose=True)
    out = capsys.readouterr().out
    assert "[OK] Windows with valid Atuin session file:" in out
    assert "missing session file" in out
    assert "missing Atuin session ID" in out
    assert "no command in Atuin" in out
    assert "Atuin/Kitty sync active in" in out


def test_print_kitty_session_diagnostics_none_synced(monkeypatch, capsys):
    state = _state(Pane(id="a", title="title"))
    location = next(state.iter_panes())
    monkeypatch.setattr(
        cli,
        "_collect_kitty_session_diagnostics",
        lambda *_args, **_kwargs: ([], [location], [], [], []),
    )
    print_kitty_session_diagnostics(state, verbose=True)
    out = capsys.readouterr().out
    assert "sync is not active in any open windows" in out


def test_main_invocation(runner):
    result = runner.invoke(["-m", "catherd"])
    assert result.exit_code == 0


def test_print_shell_snippet_and_env(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: "rc")
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda *_args, **_kwargs: "snippet")
    cli.print_shell_snippet("zsh")
    cli.print_shell_snippet("unknown")
    cli.print_env_diagnostics()
    out = capsys.readouterr().out
    assert "Add this to your shell" in out or "Unknown shell" in out
