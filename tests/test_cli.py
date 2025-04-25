import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

import catherd.__main__  # noqa: F401
import catherd.__version__ as version_module
from catherd import cli


def test_main_invocation(monkeypatch, runner):
    # Simulate running `python -m catherd`
    result = runner.invoke(["-m", "catherd"])
    assert result.exit_code == 0


def test_version_string():
    assert isinstance(version_module.__version__, str)


def test_main_entrypoint_exits_zero():
    # click will sys.exit(0) if no args
    with pytest.raises(SystemExit) as e:
        runpy.run_module("catherd.__main__", run_name="__main__")
    assert e.value.code == 0


def test_get_shell_info_env(monkeypatch):
    monkeypatch.setenv("SHELL", "/bin/zsh")
    assert cli.get_shell_info(None) == "zsh"


def test_get_shell_info_force():
    assert cli.get_shell_info("fish") == "fish"


def test_load_snippet_for_shell_known(monkeypatch):
    # Patch importlib.resources.files to simulate snippet loading
    class FakeFiles:
        @staticmethod
        def joinpath(_fn):
            class Reader:
                @staticmethod
                def read_text(*_args, **_kwargs):  # allow any signature
                    return "SHELL SNIPPET"

            return Reader()

    monkeypatch.setattr("importlib.resources.files", lambda _pkg: FakeFiles())
    assert "SHELL SNIPPET" in cli.load_snippet_for_shell("zsh")


def test_load_snippet_for_shell_unknown():
    with pytest.raises(ValueError, match="Unknown shell"):
        cli.load_snippet_for_shell("notashell")


@patch("catherd.cli.get_kitty_windows")
@patch("catherd.cli.get_atuin_session_for_window")
@patch("catherd.cli.get_last_command_for_atuin_session")
def test_cli_show_happy(mock_last_cmd, mock_session, mock_windows):
    mock_windows.return_value = [
        {"id": "id1", "tab": "tabA", "title": "Term 1"},
        {"id": "id2", "tab": "tabB", "title": "Term 2"},
    ]
    mock_session.side_effect = ["s1", "s2"]
    mock_last_cmd.side_effect = ["ls -l", "echo hi"]
    runner = CliRunner()
    result = runner.invoke(cli.main, ["show"])
    assert "Kitty WinID" in result.output
    assert "ls -l" in result.output
    assert "echo hi" in result.output
    assert result.exit_code == 0


@patch("catherd.cli.get_kitty_windows")
def test_cli_show_no_windows(mock_windows):
    mock_windows.return_value = []
    runner = CliRunner()
    result = runner.invoke(cli.main, ["show"])
    assert "No Kitty windows/tabs found" in result.output
    assert result.exit_code == 0


@patch("catherd.cli.get_kitty_windows")
def test_cli_show_none_windows(mock_windows):
    mock_windows.return_value = None
    runner = CliRunner()
    result = runner.invoke(cli.main, ["show"])
    assert "Could not get Kitty windows" in result.output


@patch("catherd.cli.is_sync_active_in_this_shell", return_value=False)
@patch("catherd.cli.get_kitty_windows")
def test_cli_doctor_basic(mock_get_kitty_windows, mock_is_sync_active):  # noqa: ARG001
    mock_get_kitty_windows.return_value = [{"id": "id1", "tab": "tabA", "title": "TestWin"}]
    runner = CliRunner()
    with (
        patch("catherd.cli.get_session_file") as gsf,
        patch("catherd.cli.get_last_command_for_atuin_session") as glc,
    ):
        gsf.return_value.exists.return_value = False
        glc.return_value = None
        result = runner.invoke(cli.main, ["doctor"])
        assert "No session files found" in result.output
        assert "TIP" in result.output


def test_cli_install(monkeypatch, tmp_path):
    runner = CliRunner()
    # Patch get_shell_info and load_snippet_for_shell to avoid file IO
    monkeypatch.setattr("catherd.cli.get_shell_info", lambda _: "bash")
    monkeypatch.setattr("catherd.cli.load_snippet_for_shell", lambda _: "# mock snippet")
    fake_rc = tmp_path / "fake_rc"
    # Patch SHELL_RC_FILES to use our temp file
    with patch.dict("catherd.cli.SHELL_RC_FILES", {"bash": fake_rc}):
        # Create the fake_rc file so open() and exists() work without patching Path methods
        fake_rc.write_text("")  # ensure file exists
        with (
            patch("shutil.copyfile"),
            patch.object(
                Path,
                "open",
                MagicMock(
                    return_value=MagicMock(
                        __enter__=lambda _s: MagicMock(),
                        __exit__=lambda _s, _exc_type, _exc_val, _exc_tb: False,
                    )
                ),
            ),
        ):
            result = runner.invoke(cli.main, ["install", "--shell", "bash"])
            assert "Snippet added" in result.output


# --------------------------- __main__ and __version__ ---------------------------


def test_version_import():
    # The version module should define __version__
    assert hasattr(version_module, "__version__")
    assert isinstance(version_module.__version__, str)


# def test_main_module_runs_without_error():
#     # Running the __main__ entrypoint should not raise
#     runpy.run_module("catherd.__main__", run_name="__main__")
#

# --------------------------- cli.load_snippet_for_shell ---------------------------


def test_load_snippet_for_shell_resource_error(monkeypatch):
    # Simulate resource loading failure
    monkeypatch.setattr(
        "importlib.resources.files", lambda pkg: (_ for _ in ()).throw(FileNotFoundError("boom"))
    )
    text = cli.load_snippet_for_shell("zsh")
    assert "[ERROR]" in text


# --------------------------- cli.is_sync_active_in_this_shell ---------------------------


def test_is_sync_env_missing(monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    assert not cli.is_sync_active_in_this_shell()


def test_is_sync_file_not_exists(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "123")
    monkeypatch.setenv("ATUIN_SESSION", "sess")
    # get_session_file returns a non-existent path
    monkeypatch.setattr(cli, "get_session_file", lambda x: tmp_path / "nope")
    assert not cli.is_sync_active_in_this_shell()


def test_is_sync_corrupt_and_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "123")
    monkeypatch.setenv("ATUIN_SESSION", "sess")
    path = tmp_path / "f"
    # Case 1: empty file => corrupt
    path.write_text("   \n")
    monkeypatch.setattr(cli, "get_session_file", lambda x: path)
    assert not cli.is_sync_active_in_this_shell()
    # Case 2: content mismatches sess
    path.write_text("other 123")
    assert not cli.is_sync_active_in_this_shell()


def test_is_sync_success(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "123")
    monkeypatch.setenv("ATUIN_SESSION", "sess")
    path = tmp_path / "f"
    path.write_text("sess 123")
    monkeypatch.setattr(cli, "get_session_file", lambda x: path)
    assert cli.is_sync_active_in_this_shell()


# --------------------------- cli.install ---------------------------


def test_install_unsupported_shell(monkeypatch):
    runner = CliRunner()
    # Force an unsupported shell
    monkeypatch.setattr(cli, "get_shell_info", lambda _: "fishy")
    result = runner.invoke(cli.main, ["install"])
    assert "[FAIL]" in result.output


class DummyFiles:
    @staticmethod
    def joinpath(_fn):
        class Rdr:
            @staticmethod
            def read_text(*args, **kwargs):
                return "dummy snippet"

        return Rdr()


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
