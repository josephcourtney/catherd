from unittest.mock import patch

from click.testing import CliRunner

import catherd.__main__  # noqa: F401
from catherd import cli
from catherd.cli import (
    _collect_kitty_session_diagnostics,
    print_kitty_session_diagnostics,
)
from catherd.kitty import KittyWindow


def test_main_entrypoint_exits_zero():
    runner = CliRunner()
    result = runner.invoke(cli.main, ["--help"])
    assert result.exit_code == 0


@patch("catherd.cli.get_kitty_windows")
@patch("catherd.cli.get_atuin_session_for_window")
@patch("catherd.cli.get_last_command_for_atuin_session")
def test_show_prints_commands(mock_last, mock_sess, mock_win):
    mock_win.return_value = [
        KittyWindow(id="a", tab="t1", title="foo"),
        KittyWindow(id="b", tab="t2", title="bar"),
    ]
    mock_sess.side_effect = ["sessA", "sessB"]
    mock_last.side_effect = ["cmdA", "cmdB"]
    result = CliRunner().invoke(cli.main, ["show"])
    assert "Kitty WinID" in result.output
    assert "cmdA" in result.output
    assert "cmdB" in result.output


@patch("catherd.cli.get_kitty_windows", return_value=[])
def test_show_empty_warns(mock_win):
    _ = mock_win
    result = CliRunner().invoke(cli.main, ["show"])
    assert "No Kitty windows/tabs found" in result.output


@patch("catherd.cli.get_kitty_windows", return_value=None)
def test_show_none_warns(mock_win):
    _ = mock_win
    result = CliRunner().invoke(cli.main, ["show"])
    assert "Could not get Kitty windows" in result.output


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
    assert "[FAIL]" in result.output


@patch("catherd.cli.get_kitty_windows", return_value=None)
@patch("catherd.cli.is_sync_active_in_this_shell", return_value=False)
def test_doctor_no_windows(mock_sync, mock_win):
    _ = mock_sync
    _ = mock_win
    out = CliRunner().invoke(cli.main, ["doctor"]).output
    assert "No Kitty windows found" in out


@patch("catherd.cli.get_kitty_windows")
def test_doctor_basic(mock_win):
    mock_win.return_value = [KittyWindow(id="X", tab="T", title="Y")]
    with (
        patch("catherd.cli.get_session_file") as gsf,
        patch("catherd.cli.get_last_command_for_atuin_session") as glc,
    ):
        gsf.return_value.exists.return_value = False
        glc.return_value = None
        out = CliRunner().invoke(cli.main, ["doctor"]).output
        assert "sync snippet" in out or "Add this to your shell rc file" in out


def test_is_sync_env_missing(monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    assert not cli.is_sync_active_in_this_shell()


def test_is_sync_success(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "a")
    monkeypatch.setenv("ATUIN_SESSION", "sess")
    p = tmp_path / "f"
    p.write_text("sess a")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: p)
    assert cli.is_sync_active_in_this_shell()


def test_main_invocation(monkeypatch, runner):
    _ = monkeypatch
    result = runner.invoke(["-m", "catherd"])
    assert result.exit_code == 0


def test_show_env_verbose(monkeypatch):
    class FakeWin:
        def __init__(self):
            self.id = "w"
            self.tab = "t"
            self.title = "tit"

    monkeypatch.setattr(cli, "get_kitty_windows", lambda *_args, **_kwargs: [FakeWin()])
    monkeypatch.setattr(cli, "get_atuin_session_for_window", lambda *_args, **_kwargs: None)
    runner = CliRunner()
    result = runner.invoke(cli.main, ["show", "-v"])
    assert "no session info" in result.output


def test_print_shell_snippet_and_env(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: "rc")
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda *_args, **_kwargs: "snippet")
    cli.print_shell_snippet("zsh")
    cli.print_shell_snippet("unknown")
    cli.print_env_diagnostics()
    out = capsys.readouterr().out
    assert "Add this to your shell" in out or "Unknown shell" in out


def test__collect_kitty_session_diagnostics(monkeypatch, tmp_path):
    win = KittyWindow(id="id", tab="tab", title="title")
    session_file = tmp_path / "atuin_kitty_id"
    session_file.write_text("sessid")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "cmd")
    ok, missing, corrupt, missing_cmd = _collect_kitty_session_diagnostics([win], verbose=True)
    assert ok or missing or corrupt or missing_cmd


def test_doctor_all(monkeypatch):
    monkeypatch.setattr(cli, "get_kitty_windows", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(cli, "is_sync_active_in_this_shell", lambda: False)
    runner = CliRunner()
    result = runner.invoke(cli.main, ["doctor"])
    assert "No Kitty windows found" in result.output


def test_print_kitty_session_diagnostics_all_branches(monkeypatch, capsys):
    # OK
    w_ok = KittyWindow(id="a", tab="t", title="title")
    # Missing file
    w_missing = KittyWindow(id="b", tab="t", title="title2")
    # Corrupt
    w_corrupt = KittyWindow(id="c", tab="t", title="title3")
    # Missing command
    w_cmd = KittyWindow(id="d", tab="t", title="title4")

    ok = [(w_ok, "sessid", "cmd")]
    missing_file = [w_missing]
    corrupt_file = [(w_corrupt, "")]
    missing_command = [(w_cmd, "sessid", "(atuin error)")]
    # patch diagnostics to yield all four scenarios
    monkeypatch.setattr(
        cli,
        "_collect_kitty_session_diagnostics",
        lambda *_args, **_kwargs: (ok, missing_file, corrupt_file, missing_command),
    )
    print_kitty_session_diagnostics([w_ok, w_missing, w_corrupt, w_cmd], verbose=True)
    out = capsys.readouterr().out
    assert "[OK] Windows with valid Atuin session file:" in out
    assert "missing session file" in out
    assert "missing Atuin session ID" in out
    assert "no command in Atuin" in out
    assert "Atuin/Kitty sync active in" in out


def test_print_kitty_session_diagnostics_none_synced(monkeypatch, capsys):
    w = KittyWindow(id="a", tab="t", title="title")
    monkeypatch.setattr(
        cli,
        "_collect_kitty_session_diagnostics",
        lambda *_args, **_kwargs: ([], [w], [], []),
    )
    print_kitty_session_diagnostics([w], verbose=True)
    out = capsys.readouterr().out
    assert "sync is not active in any open windows" in out


def test_print_env_diagnostics_warns(monkeypatch, capsys):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    cli.print_env_diagnostics()
    out = capsys.readouterr().out
    assert "not set in this shell" in out


def test_get_atuin_session_for_window_no_file(tmp_path, capsys, monkeypatch):
    # Arrange: make get_session_file() point to a non-existent path
    p = tmp_path / "nope"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "get_session_file", lambda _: p)

    # Act
    result = cli.get_atuin_session_for_window("whatever", verbose=True)
    out = capsys.readouterr().out

    # Assert
    assert result is None
    assert "[verbose] No session file:" in out


def test_get_atuin_session_for_window_empty_file(tmp_path, capsys, monkeypatch):
    p = tmp_path / "found"
    p.write_text("")  # empty
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "get_session_file", lambda _: p)

    result = cli.get_atuin_session_for_window("whatever", verbose=True)
    out = capsys.readouterr().out

    assert result is None
    assert "Read session info" in out  # it read the file but returned None


def test_get_atuin_session_for_window_valid(tmp_path, monkeypatch):
    p = tmp_path / "found"
    p.write_text("mysess extra data")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "get_session_file", lambda _: p)

    result = cli.get_atuin_session_for_window("whatever", verbose=False)
    assert result == "mysess"


def test_install_shell_snippet_already_installed(tmp_path, monkeypatch):
    # Set up a fake rc file that already contains the marker
    rc = tmp_path / "rc"
    rc.write_text("# catherd atuin/kitty sync snippet\n…")
    monkeypatch.setattr(cli, "get_shell_info", lambda *_: "bash")
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda _: "# snippet")
    monkeypatch.setenv("HOME", str(tmp_path))  # so get_shell_rc_path("bash") → tmp_path/.bashrc
    # Create ~/.bashrc
    fake_bashrc = tmp_path / ".bashrc"
    fake_bashrc.write_text(rc.read_text())

    runner = CliRunner()
    result = runner.invoke(cli.main, ["install", "--shell", "bash"])
    assert "[OK] Snippet already installed" in result.output


def test__collect_kitty_session_diagnostics_branches(tmp_path, monkeypatch):
    # Prepare four windows to hit every branch
    w_no_file = KittyWindow(id="a", tab=None, title="")
    w_corrupt = KittyWindow(id="b", tab=None, title="")
    w_nocommand = KittyWindow(id="c", tab=None, title="")
    w_ok = KittyWindow(id="d", tab=None, title="")

    # Make get_session_file behave differently per ID
    def fake_session_file(window_id):
        p = tmp_path / f"atuin_kitty_{window_id}"
        if window_id == "b":
            p.write_text("")  # corrupt
        elif window_id == "c":
            p.write_text("sess_c")
        elif window_id == "d":
            p.write_text("sess_d")
        return p

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "get_session_file", fake_session_file)

    # get_last_command_for_atuin_session returns error for "c", normal for "d"
    def fake_last(session_id, *, verbose=False):
        # only the "c" session errors
        if session_id == "sess_c" and verbose:
            return "(atuin error)"
        return "cmd"

    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", fake_last)

    ok, missing, corrupt, missing_cmd = _collect_kitty_session_diagnostics(
        [w_no_file, w_corrupt, w_nocommand, w_ok], verbose=True
    )
    assert [w_no_file] == missing
    assert [(w_corrupt, "")] == corrupt
    assert len(missing_cmd) == 1
    assert missing_cmd[0][0] == w_nocommand
    assert len(ok) == 1
    assert ok[0][0] == w_ok
