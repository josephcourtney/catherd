import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import catherd.__main__  # noqa: F401
from catherd import cli, core


class DummyFiles:
    @staticmethod
    def joinpath(_fn):
        class Rdr:
            @staticmethod
            def read_text(*args, **kwargs):
                return "dummy snippet"

        return Rdr()


def make_kitty_ls_json():
    # Kitty output as Python structure
    return [
        {
            "tabs": [
                {
                    "id": 10,
                    "title": "Tab 1",
                    "windows": [
                        {"id": 101, "title": "win101"},
                        {"id": 102, "title": "win102"},
                    ],
                },
                {
                    "id": 11,
                    "title": "Tab 2",
                    "windows": [
                        {"id": 103, "title": "win103"},
                    ],
                },
            ]
        }
    ]


@patch("shutil.which")
@patch("subprocess.run")
def test_get_kitty_windows_success(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/kitty"
    fake_json = json.dumps(make_kitty_ls_json())
    mock_run.return_value = MagicMock(returncode=0, stdout=fake_json, stderr="")
    result = core.get_kitty_windows()
    assert isinstance(result, list)
    assert result[0]["id"] == 101
    assert result[1]["id"] == 102
    assert result[2]["tab"] == 11


@patch("shutil.which")
@patch("subprocess.run")
def test_get_kitty_windows_failure(mock_run, mock_which):  # noqa: ARG001
    mock_which.return_value = None
    result = core.get_kitty_windows()
    assert result is None


@patch("shutil.which")
@patch("subprocess.run")
def test_get_kitty_windows_json_decode_error(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/kitty"
    mock_run.return_value = MagicMock(returncode=0, stdout="not-json", stderr="")
    result = core.get_kitty_windows()
    assert result is None


@patch("catherd.core.get_session_file")
def test_get_atuin_session_for_window_file_missing(mock_get_session_file, tmp_path):
    mock_get_session_file.return_value = tmp_path / "nope"
    out = core.get_atuin_session_for_window("123")
    assert out is None


@patch("catherd.core.get_session_file")
def test_get_atuin_session_for_window_success(mock_get_session_file, tmp_path):
    file = tmp_path / "sfile"
    file.write_text("my-session-id extra\n")
    mock_get_session_file.return_value = file
    assert core.get_atuin_session_for_window("123") == "my-session-id"


@patch("shutil.which")
@patch("subprocess.run")
def test_get_last_command_for_atuin_session_success(mock_run, mock_which):
    mock_which.return_value = "/usr/bin/atuin"
    mock_run.return_value = MagicMock(stdout="ls -l\n", returncode=0)
    out = core.get_last_command_for_atuin_session("mysess")
    assert out == "ls -l"


@patch("shutil.which")
def test_get_last_command_for_atuin_session_no_atuin(mock_which):
    mock_which.return_value = None
    assert core.get_last_command_for_atuin_session("abc") == "(atuin not found)"


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_get_kitty_windows_subprocess_error(mock_run, mock_which):
    mock_run.side_effect = subprocess.SubprocessError("fail")
    assert core.get_kitty_windows() is None


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_get_kitty_windows_nonzero_exit(mock_run, mock_which):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="err")
    assert core.get_kitty_windows() is None


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_get_kitty_windows_verbose(mock_run, mock_which, capsys):
    data = json.dumps([{"tabs": []}])
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout=data, stderr="")
    # Should warn about no windows
    result = core.get_kitty_windows(verbose=True)
    captured = capsys.readouterr()
    assert "[verbose] Raw output from" in captured.out
    assert result == []


def test_get_atuin_session_for_window_empty(tmp_path):
    f = tmp_path / "sess"
    f.write_text("\n")
    # monkeypatch get_session_file
    monkey = pytest.MonkeyPatch()
    monkey.setattr(core, "get_session_file", lambda x: f)
    try:
        assert core.get_atuin_session_for_window("x") is None
    finally:
        monkey.undo()


@patch("shutil.which", return_value=None)
def test_last_command_no_atuin(mock_which):
    assert core.get_last_command_for_atuin_session("any") == "(atuin not found)"


@patch("shutil.which", return_value="/usr/bin/atuin")
@patch("subprocess.run")
def test_last_command_subprocess_error(mock_run, mock_which):
    mock_run.side_effect = subprocess.SubprocessError("oops")
    assert core.get_last_command_for_atuin_session("x", verbose=True) == "(atuin error)"


@patch("shutil.which", return_value="/usr/bin/atuin")
@patch("subprocess.run")
def test_last_command_empty_stdout(mock_run, mock_which):
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    assert core.get_last_command_for_atuin_session("x") == "(no command)"


def test_core_main_prints_table(monkeypatch, capsys):
    # Patch windows and session lookups
    monkeypatch.setattr(
        core, "get_kitty_windows", lambda verbose=False: [{"id": "1", "tab": "A", "title": "T1"}]
    )
    monkeypatch.setattr(core, "get_atuin_session_for_window", lambda sid, verbose=False: "s1")
    monkeypatch.setattr(core, "get_last_command_for_atuin_session", lambda sid, verbose=False: "cmd")
    core.main(verbose=True)
    out = capsys.readouterr().out
    assert "Kitty WinID" in out
    assert "cmd" in out


def test_print_kitty_session_diagnostics_all_branches(monkeypatch, tmp_path, capsys):
    # Prepare four windows: ok, missing_file, corrupt_file, missing_command
    windows = [
        {"id": "ok", "tab": 1, "title": "OK"},
        {"id": "miss", "tab": 2, "title": "Miss"},
        {"id": "corr", "tab": 3, "title": "Corr"},
        {"id": "ncmd", "tab": 4, "title": "NoCmd"},
    ]
    base = tmp_path
    # Create files for ok, corr, ncmd
    ok_f = base / "atuin_kitty_ok"
    ok_f.write_text("s_ok ok")
    corr_f = base / "atuin_kitty_corr"
    corr_f.write_text("   ")  # corrupt
    ncmd_f = base / "atuin_kitty_ncmd"
    ncmd_f.write_text("s_nc ncmd")
    # Monkeypatch get_session_file
    monkeypatch.setattr(cli, "get_session_file", lambda wid: base / f"atuin_kitty_{wid}")

    # Monkeypatch last command
    def fake_last(sid, *, verbose=False):
        if sid == "s_ok":
            return "last"
        if sid == "s_nc":
            return ""
        return None

    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", fake_last)
    # Run diagnostics
    cli.print_kitty_session_diagnostics(windows)
    out = capsys.readouterr().out
    # Check each section header
    assert "[OK] Windows with valid Atuin session file" in out
    assert "[WARN] Windows missing session file" in out
    assert "[FAIL] Windows with session file but missing Atuin session ID" in out or "corrupt" in out
    assert "[WARN] Windows with session file but no command in Atuin" in out


def test_load_snippet_happy(monkeypatch):
    monkeypatch.setattr("importlib.resources.files", lambda pkg: DummyFiles())
    assert "dummy snippet" in cli.load_snippet_for_shell("zsh")


def test_load_snippet_unknown_shell():
    with pytest.raises(ValueError):
        cli.load_snippet_for_shell("nope")


def test_load_snippet_error(monkeypatch):
    monkeypatch.setattr("importlib.resources.files", lambda pkg: (_ for _ in ()).throw(OSError("boom")))
    out = cli.load_snippet_for_shell("bash")
    assert "[ERROR]" in out


# ------------------ print_shell_snippet ------------------


def test_print_shell_snippet_known(capsys, monkeypatch, tmp_path):
    # stub snippet loader and rc path
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda s: "# snippet")
    fake_rc = tmp_path / "rc"
    fake_rc.write_text("")  # exists
    cli.SHELL_RC_FILES["bash"] = fake_rc
    cli.print_shell_snippet("bash")
    out = capsys.readouterr().out
    assert "Add this to your shell rc file" in out
    assert "# snippet" in out
    assert "Or run 'catherd install'" in out


def test_print_shell_snippet_unknown(capsys):
    cli.print_shell_snippet("nada")
    out = capsys.readouterr().out
    assert "[INFO] Unknown shell" in out


# ------------------ is_sync_active_in_this_shell ------------------


@pytest.mark.parametrize(
    ("kit", "atuin"),
    [
        (None, None),
        ("123", None),
        (None, "sess"),
    ],
)
def test_sync_env_missing(monkeypatch, kit, atuin):
    if kit is not None:
        monkeypatch.setenv("KITTY_WINDOW_ID", kit)
    else:
        monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    if atuin is not None:
        monkeypatch.setenv("ATUIN_SESSION", atuin)
    else:
        monkeypatch.delenv("ATUIN_SESSION", raising=False)
    assert not cli.is_sync_active_in_this_shell()


def test_sync_file_not_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("ATUIN_SESSION", "s")
    monkeypatch.setattr(cli, "get_session_file", lambda x: tmp_path / "nope")
    assert not cli.is_sync_active_in_this_shell()


def test_sync_corrupt_and_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("ATUIN_SESSION", "s")
    p = tmp_path / "f"
    p.write_text("   \n")
    monkeypatch.setattr(cli, "get_session_file", lambda x: p)
    assert not cli.is_sync_active_in_this_shell()
    p.write_text("other 1")
    assert not cli.is_sync_active_in_this_shell()


def test_sync_success(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "1")
    monkeypatch.setenv("ATUIN_SESSION", "s")
    p = tmp_path / "f"
    p.write_text("s 1")
    monkeypatch.setattr(cli, "get_session_file", lambda x: p)
    assert cli.is_sync_active_in_this_shell()


# ------------------ install_shell_snippet ------------------


def test_install_unsupported(monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "get_shell_info", lambda _: "badsh")
    result = runner.invoke(cli.main, ["install"])
    assert "[FAIL]" in result.output


def test_install_already(monkeypatch, tmp_path):
    runner = CliRunner()
    monkeypatch.setattr(cli, "get_shell_info", lambda _: "bash")
    fake = tmp_path / "rc"
    fake.write_text("# catherd atuin/kitty sync snippet")
    cli.SHELL_RC_FILES["bash"] = fake
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda s: "# s")
    result = runner.invoke(cli.main, ["install"])
    assert "already installed" in result.output


def test_install_new(tmp_path, monkeypatch):
    runner = CliRunner()
    monkeypatch.setattr(cli, "get_shell_info", lambda _: "bash")
    fake = tmp_path / "rc"
    fake.write_text("")
    cli.SHELL_RC_FILES["bash"] = fake
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda s: "# s")
    result = runner.invoke(cli.main, ["install"])
    assert "Snippet added" in result.output


# ------------------ print_env_diagnostics ------------------


def test_print_env_diagnostics(capsys, monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    cli.print_env_diagnostics()
    out = capsys.readouterr().out
    assert "$KITTY_WINDOW_ID" in out
    assert "$ATUIN_SESSION" in out


# ------------------ show command ------------------


@patch("catherd.cli.get_kitty_windows")
def test_show_none(mock_win):
    mock_win.return_value = None
    out = CliRunner().invoke(cli.main, ["show"]).output
    assert "Could not get Kitty windows" in out


@patch("catherd.cli.get_kitty_windows")
def test_show_empty(mock_win):
    mock_win.return_value = []
    out = CliRunner().invoke(cli.main, ["show"]).output
    assert "No Kitty windows/tabs found" in out


@patch("catherd.cli.get_kitty_windows")
@patch("catherd.cli.get_atuin_session_for_window")
@patch("catherd.cli.get_last_command_for_atuin_session")
def test_show_happy(mock_last, mock_sess, mock_win):
    mock_win.return_value = [{"id": "1", "tab": "A", "title": "T"}]
    mock_sess.return_value = "sess"
    mock_last.return_value = "cmd"
    out = CliRunner().invoke(cli.main, ["show", "--verbose"]).output
    assert "Kitty WinID" in out
    assert "cmd" in out


# ------------------ doctor command ------------------


@patch("catherd.cli.is_sync_active_in_this_shell", return_value=False)
@patch("catherd.cli.get_kitty_windows", return_value=None)
def test_doctor_no_windows(mock_win, mock_sync):
    out = CliRunner().invoke(cli.main, ["doctor"]).output
    assert "No Kitty windows found" in out


# ------------------ core.get_kitty_windows ------------------


@patch("shutil.which", return_value=None)
def test_kitty_not_in_path(mock_which):
    assert core.get_kitty_windows() is None


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_kitty_run_error(mock_run, mock_which):
    mock_run.side_effect = subprocess.SubprocessError()
    assert core.get_kitty_windows() is None


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_kitty_nonzero_exit(mock_run, mock_which):
    mock_run.return_value = subprocess.CompletedProcess([], 1, "", "err")
    assert core.get_kitty_windows() is None


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_kitty_verbose_empty(mock_run, mock_which, capsys):
    mock_run.return_value = subprocess.CompletedProcess([], 0, json.dumps([{"tabs": []}]), "")
    result = core.get_kitty_windows(verbose=True)
    cap = capsys.readouterr()
    assert "[verbose] Raw output" in cap.out
    assert result == []


# ------------------ core.get_atuin_session_for_window ------------------


def test_get_session_missing(tmp_path, capsys):
    tmp_path / "x"
    # no file
    assert core.get_atuin_session_for_window("x", verbose=True) is None
    # no verbose print because path nonexistent, but then exists->False returns None


def test_get_session_verbose_read(tmp_path, capsys):
    f = tmp_path / "x"
    f.write_text("sid rest")
    # monkeypatch get_session_file
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(core, "get_session_file", lambda w: f)
    try:
        out = core.get_atuin_session_for_window("x", verbose=True)
        cap = capsys.readouterr().out
        assert "Read session info" in cap
        assert out == "sid"
    finally:
        monkeypatch.undo()


# ------------------ core.get_last_command_for_atuin_session ------------------


@patch("shutil.which", return_value=None)
def test_last_cmd_no_atuin(mock_which, capsys):
    out = core.get_last_command_for_atuin_session("x", verbose=True)
    assert out == "(atuin not found)"
    assert "[verbose] 'atuin' is not found" in capsys.readouterr().out


@patch("shutil.which", return_value="/usr/bin/atuin")
@patch("subprocess.run")
def test_last_cmd_error(mock_run, mock_which, capsys):
    mock_run.side_effect = subprocess.SubprocessError("boom")
    out = core.get_last_command_for_atuin_session("x", verbose=True)
    assert out == "(atuin error)"
    assert "Error running atuin" in capsys.readouterr().out


@patch("shutil.which", return_value="/usr/bin/atuin")
@patch("subprocess.run")
def test_last_cmd_empty(mock_run, mock_which):
    mock_run.return_value = subprocess.CompletedProcess([], 0, "", "\n")
    assert core.get_last_command_for_atuin_session("x") == "(no command)"


# ------------------ core.main ------------------


def test_core_main_none(monkeypatch, capsys):
    monkeypatch.setattr(core, "get_kitty_windows", lambda verbose=False: None)
    core.main(verbose=True)
    out = capsys.readouterr().out
    assert "Kitty WinID" in out  # header printed, then return w/o crash


def test_core_main_happy(monkeypatch, capsys):
    monkeypatch.setattr(
        core, "get_kitty_windows", lambda verbose=False: [{"id": "1", "tab": "T", "title": "tt"}]
    )
    monkeypatch.setattr(core, "get_atuin_session_for_window", lambda w, verbose=False: "s")
    monkeypatch.setattr(core, "get_last_command_for_atuin_session", lambda sid, verbose=False: "c")
    core.main(verbose=False)
    out = capsys.readouterr().out
    assert "Kitty WinID" in out
    assert "c" in out
