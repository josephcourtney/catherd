import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import catherd.__main__  # ruff: ignore[unused-import]
from catherd import cli
from catherd.cli import _collect_kitty_session_diagnostics, print_kitty_session_diagnostics
from catherd.model import KittyState, OsWindow, Pane, Tab
from catherd.shell import ATUIN_INTEGRATION_MARKER, managed_snippet_block


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


@pytest.mark.small
def test_main_entrypoint_exits_zero():
    result = CliRunner().invoke(cli.main, ["--help"])
    assert result.exit_code == 0


@pytest.mark.small
def test_tui_command(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "run_tui", lambda: calls.append("run"))

    result = CliRunner().invoke(cli.main, ["tui"])

    assert result.exit_code == 0
    assert calls == ["run"]


@patch("catherd.cli.get_kitty_state")
@patch("catherd.cli.get_atuin_session_for_window")
@patch("catherd.cli.get_last_command_for_atuin_session")
@pytest.mark.small
def test_show_prints_commands(mock_last, mock_sess, mock_state):
    mock_state.return_value = _two_tab_state()
    mock_sess.side_effect = ["sessA", "sessB"]
    mock_last.side_effect = ["cmdA", "cmdB"]
    result = CliRunner().invoke(cli.main, ["show"])
    assert "Kitty WinID" in result.output
    assert "cmdA" in result.output
    assert "cmdB" in result.output


@pytest.mark.small
def test_show_empty_warns():
    with patch("catherd.cli.get_kitty_state", return_value=KittyState(os_windows=())):
        result = CliRunner().invoke(cli.main, ["show"])
    assert "No Kitty windows/tabs found" in result.stderr


@pytest.mark.small
def test_show_none_warns():
    with patch("catherd.cli.get_kitty_state", return_value=None):
        result = CliRunner().invoke(cli.main, ["show"])
    assert "Could not get Kitty windows" in result.stderr


@pytest.mark.medium
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


@pytest.mark.medium
def test_inspect_outputs_full_metadata(tmp_path, monkeypatch):
    session_file = tmp_path / "atuin_kitty_win"
    session_file.write_text("sessA win")
    state = _state(
        Pane(
            id="win",
            title="title",
            pid=1234,
            cwd=str(tmp_path),
            foreground_cmd="python -m pytest",
            root_cmdline="/bin/zsh -l",
            current_command="uv run pytest",
            at_prompt=False,
            title_overridden=True,
            needs_attention=True,
            has_activity_since_last_focus=True,
            cols=132,
            rows=43,
        ),
        tab_id="tab",
        os_id="os-1",
    )

    monkeypatch.setattr(cli, "get_kitty_state", lambda **_kwargs: state)
    monkeypatch.setattr(cli, "get_atuin_session_for_window", lambda *_args, **_kwargs: "sessA")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "echo hi")

    result = CliRunner().invoke(cli.main, ["inspect"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["window_id"] == "win"
    assert payload[0]["os_window_id"] == "os-1"
    assert payload[0]["pid"] == 1234
    assert payload[0]["cwd"] == str(tmp_path)
    assert payload[0]["foreground_cmd"] == "python -m pytest"
    assert payload[0]["root_cmdline"] == "/bin/zsh -l"
    assert payload[0]["current_command"] == "uv run pytest"
    assert payload[0]["at_prompt"] is False
    assert payload[0]["title_overridden"] is True
    assert payload[0]["needs_attention"] is True
    assert payload[0]["has_activity_since_last_focus"] is True
    assert payload[0]["cols"] == 132
    assert payload[0]["rows"] == 43
    assert payload[0]["atuin_session_id"] == "sessA"
    assert payload[0]["session_content"] == "sessA win"


@pytest.mark.small
def test_show_env_verbose(monkeypatch):
    state = _state(Pane(id="w", title="tit"))
    monkeypatch.setattr(cli, "get_kitty_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(cli, "get_atuin_session_for_window", lambda *_args, **_kwargs: None)
    result = CliRunner().invoke(cli.main, ["show", "-v"])
    assert "(no command)" in result.output


@pytest.mark.small
def test_show_prefers_running_command(monkeypatch):
    state = _state(
        Pane(
            id="w",
            title="tit",
            current_command="uv run pytest",
            foreground_cmd="python -m pytest",
        )
    )
    monkeypatch.setattr(cli, "get_kitty_state", lambda *_args, **_kwargs: state)
    monkeypatch.setattr(cli, "get_atuin_session_for_window", lambda *_args, **_kwargs: "s")
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "git status")

    result = CliRunner().invoke(cli.main, ["show", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload[0]["last_command"] == "uv run pytest"
    assert payload[0]["current_command"] == "uv run pytest"


@pytest.mark.medium
def test_show_core_behavior_without_atuin(tmp_path, monkeypatch):
    """Kitty state remains sufficient when no Atuin association or DB exists."""
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    state = _state(
        Pane(
            id="w",
            title="server",
            current_command="python -m http.server",
            foreground_cmd="python -m http.server",
            cwd="/code/project",
        ),
        os_active=True,
        tab_active=True,
    )
    monkeypatch.setattr(cli, "get_kitty_state", lambda *_args, **_kwargs: state)

    def fail_history_lookup(*_args, **_kwargs):
        msg = "Atuin history must not be queried without a pane/session association"
        raise AssertionError(msg)

    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", fail_history_lookup)

    result = CliRunner().invoke(cli.main, ["show"])

    assert result.exit_code == 0
    assert "python -m http.server" in result.output
    assert "/code/project" in result.output


@pytest.mark.medium
def test_preflight_only_on_show(tmp_path, monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)

    with patch("catherd.cli.get_kitty_state", return_value=KittyState(os_windows=())):
        show_result = CliRunner().invoke(cli.main, ["show"])
    assert show_result.exit_code == 0
    assert "Run 'catherd doctor'" in show_result.stderr or "diagnose" in show_result.stderr

    rc = tmp_path / ".bashrc"
    rc.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)
    dry_run = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash", "--dry-run"])
    assert dry_run.exit_code == 0
    assert "DRY-RUN" in dry_run.stderr


@pytest.mark.medium
def test_atuin_enable_writes_managed_block_and_backup(monkeypatch, tmp_path):
    rc = tmp_path / "rc"
    rc.write_text("existing\n", encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash"])

    assert result.exit_code == 0
    assert "Atuin integration enabled" in result.output
    contents = rc.read_text(encoding="utf-8")
    assert contents.startswith("existing\n")
    assert ATUIN_INTEGRATION_MARKER in contents
    assert (tmp_path / "rc.catherd.bak").read_text(encoding="utf-8") == "existing\n"


@pytest.mark.small
def test_atuin_enable_rejects_unsupported_shell():
    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "noshell"])
    assert result.exit_code == 1
    assert "Unknown shell" in result.stderr


@pytest.mark.medium
def test_atuin_enable_is_idempotent(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    rc.write_text(managed_snippet_block("bash"), encoding="utf-8")
    before = rc.read_text(encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash"])

    assert result.exit_code == 0
    assert "already enabled" in result.output
    assert rc.read_text(encoding="utf-8") == before
    assert not (tmp_path / "rc.catherd.bak").exists()


@pytest.mark.medium
def test_atuin_enable_migrates_legacy_block(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    original = "before\n# catherd atuin/kitty sync snippet\nlegacy body\n# end catherd atuin/kitty sync\nafter\n"
    rc.write_text(original, encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash"])

    assert result.exit_code == 0
    assert "Migrated legacy" in result.output
    migrated = rc.read_text(encoding="utf-8")
    assert migrated.startswith("before\n")
    assert migrated.endswith("after\n")
    assert ATUIN_INTEGRATION_MARKER in migrated
    assert "# catherd atuin/kitty sync snippet" not in migrated
    assert (tmp_path / "rc.catherd.bak").read_text(encoding="utf-8") == original


@pytest.mark.medium
def test_atuin_enable_dry_run_performs_no_writes(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    rc.write_text("orig", encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY-RUN" in result.stderr
    assert rc.read_text(encoding="utf-8") == "orig"
    assert not (tmp_path / "rc.catherd.bak").exists()


@pytest.mark.medium
def test_atuin_enable_handles_new_rc_path_with_spaces(tmp_path, monkeypatch):
    rc = tmp_path / "config dir" / "shell rc"
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash"])

    assert result.exit_code == 0
    assert ATUIN_INTEGRATION_MARKER in rc.read_text(encoding="utf-8")
    assert not (tmp_path / "config dir" / "shell rc.catherd.bak").exists()


@pytest.mark.medium
def test_atuin_enable_preserves_rc_symlink(tmp_path, monkeypatch):
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    target = dotfiles / "zshrc"
    target.write_text("setopt promptsubst\n", encoding="utf-8")
    rc = tmp_path / ".zshrc"
    rc.symlink_to(target)
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "zsh"])

    assert result.exit_code == 0
    assert rc.is_symlink()
    assert ATUIN_INTEGRATION_MARKER in target.read_text(encoding="utf-8")
    assert (tmp_path / ".zshrc.catherd.bak").read_text(encoding="utf-8") == "setopt promptsubst\n"

    disable_result = CliRunner().invoke(cli.main, ["atuin", "disable", "--shell", "zsh"])

    assert disable_result.exit_code == 0
    assert rc.is_symlink()
    assert target.read_text(encoding="utf-8") == "setopt promptsubst\n"
    assert ATUIN_INTEGRATION_MARKER in (tmp_path / ".zshrc.catherd.disable.bak").read_text(encoding="utf-8")


@pytest.mark.medium
def test_atuin_enable_rejects_dangling_rc_symlink(tmp_path, monkeypatch):
    rc = tmp_path / ".zshrc"
    rc.symlink_to(tmp_path / "missing-target")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "zsh"])

    assert result.exit_code == 1
    assert "dangling, cyclic, or unreadable" in result.stderr
    assert rc.is_symlink()


@pytest.mark.medium
def test_atuin_enable_write_failure_leaves_original_and_backup(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    rc.write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    def fail_write(_path, _contents):
        msg = "simulated write failure"
        raise OSError(msg)

    monkeypatch.setattr(cli, "_atomic_write_text", fail_write)
    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash"])

    assert result.exit_code == 1
    assert "simulated write failure" in result.stderr
    assert rc.read_text(encoding="utf-8") == "original\n"
    assert (tmp_path / "rc.catherd.bak").read_text(encoding="utf-8") == "original\n"


@pytest.mark.medium
def test_atuin_enable_validation_failure_preserves_rc(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    rc.write_text("orig", encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)

    def reject(_shell):
        msg = "invalid generated snippet"
        raise ValueError(msg)

    monkeypatch.setattr(cli, "validate_snippet_for_shell", reject)
    result = CliRunner().invoke(cli.main, ["atuin", "enable", "--shell", "bash"])

    assert result.exit_code == 1
    assert "invalid generated snippet" in result.stderr
    assert rc.read_text(encoding="utf-8") == "orig"
    assert not (tmp_path / "rc.catherd.bak").exists()


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.medium
def test_atuin_disable_removes_current_or_legacy_block(tmp_path, monkeypatch, legacy):
    rc = tmp_path / "rc"
    if legacy:
        block = "# catherd atuin/kitty sync snippet\nlegacy body\n# end catherd atuin/kitty sync\n"
    else:
        block = managed_snippet_block("bash")
    original = f"line1\n{block}line2\n"
    rc.write_text(original, encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)

    result = CliRunner().invoke(cli.main, ["atuin", "disable", "--shell", "bash"])

    assert result.exit_code == 0
    assert "Removed" in result.output
    assert rc.read_text(encoding="utf-8") == "line1\nline2\n"
    assert (tmp_path / "rc.catherd.disable.bak").read_text(encoding="utf-8") == original


@pytest.mark.medium
def test_atuin_disable_dry_run_performs_no_writes(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    original = f"before\n{managed_snippet_block('bash')}after\n"
    rc.write_text(original, encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)

    result = CliRunner().invoke(cli.main, ["atuin", "disable", "--shell", "bash", "--dry-run"])

    assert result.exit_code == 0
    assert "DRY-RUN" in result.stderr
    assert rc.read_text(encoding="utf-8") == original
    assert not (tmp_path / "rc.catherd.disable.bak").exists()


@pytest.mark.medium
def test_atuin_disable_rejects_unterminated_managed_block_without_writing(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    original = "keep\n# catherd atuin/kitty sync snippet\nunterminated\n"
    rc.write_text(original, encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)

    result = CliRunner().invoke(cli.main, ["atuin", "disable", "--shell", "bash"])

    assert result.exit_code == 1
    assert "Unterminated" in result.stderr
    assert rc.read_text(encoding="utf-8") == original
    assert not (tmp_path / "rc.catherd.disable.bak").exists()


@pytest.mark.medium
def test_atuin_disable_missing_rc_is_optional(tmp_path, monkeypatch):
    rc = tmp_path / "missing"
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)

    result = CliRunner().invoke(cli.main, ["atuin", "disable", "--shell", "bash"])

    assert result.exit_code == 0
    assert "not enabled" in result.output


@pytest.mark.medium
def test_legacy_install_uninstall_aliases_remain_invokable(tmp_path, monkeypatch):
    rc = tmp_path / "rc"
    rc.write_text("", encoding="utf-8")
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: rc)
    monkeypatch.setattr(cli, "validate_snippet_for_shell", lambda *_args, **_kwargs: None)

    install_result = CliRunner().invoke(cli.main, ["install", "--shell", "bash"])
    assert install_result.exit_code == 0
    assert "[DEPRECATED]" in install_result.stderr
    assert ATUIN_INTEGRATION_MARKER in rc.read_text(encoding="utf-8")

    uninstall_result = CliRunner().invoke(cli.main, ["uninstall", "--shell", "bash"])
    assert uninstall_result.exit_code == 0
    assert "[DEPRECATED]" in uninstall_result.stderr
    assert ATUIN_INTEGRATION_MARKER not in rc.read_text(encoding="utf-8")


@pytest.mark.small
def test_legacy_install_uninstall_are_hidden_from_help():
    result = CliRunner().invoke(cli.main, ["--help"])

    assert result.exit_code == 0
    assert "\n  atuin " in result.output
    assert "\n  install " not in result.output
    assert "\n  uninstall " not in result.output


@patch("catherd.cli.get_kitty_state", return_value=KittyState(os_windows=()))
@pytest.mark.medium
def test_doctor_no_windows(mock_state):
    _ = mock_state
    result = CliRunner().invoke(cli.main, ["doctor"])
    assert result.exit_code == 1
    assert "No Kitty windows found" in result.output


@patch("catherd.cli.get_kitty_state")
@pytest.mark.medium
def test_doctor_basic(mock_state):
    mock_state.return_value = _state(Pane(id="X", title="Y"), tab_id="T")
    with (
        patch("catherd.cli.get_session_file") as gsf,
        patch("catherd.cli.get_last_command_for_atuin_session") as glc,
    ):
        gsf.return_value.exists.return_value = False
        glc.return_value = None
        result = CliRunner().invoke(cli.main, ["doctor"])
    assert "Optional Atuin history" in result.output
    assert "catherd atuin doctor" in result.output


@pytest.mark.medium
def test_atuin_doctor_treats_missing_atuin_as_optional(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    monkeypatch.setattr(cli, "get_atuin_history_db_path", lambda: tmp_path / "missing-history.db")
    monkeypatch.setattr(cli, "get_kitty_state", lambda **_kwargs: KittyState(os_windows=()))
    monkeypatch.setattr(cli, "get_shell_info", lambda *_args, **_kwargs: "bash")
    monkeypatch.setattr(cli, "is_sync_active_in_this_shell", lambda: False)
    monkeypatch.setattr(cli, "print_shell_snippet", lambda _shell: None)

    result = CliRunner().invoke(cli.main, ["atuin", "doctor"])

    assert result.exit_code == 0
    assert "Atuin executable not found" in result.output
    assert "core catherd behavior" in result.output
    assert "No Kitty panes are available" in result.output


@pytest.mark.small
def test_atuin_commands_are_visible_under_explicit_namespace():
    result = CliRunner().invoke(cli.main, ["atuin", "--help"])

    assert result.exit_code == 0
    assert "enable" in result.output
    assert "disable" in result.output
    assert "doctor" in result.output


@pytest.mark.small
def test_is_sync_env_missing(monkeypatch):
    monkeypatch.delenv("KITTY_WINDOW_ID", raising=False)
    monkeypatch.delenv("ATUIN_SESSION", raising=False)
    assert not cli.is_sync_active_in_this_shell()


@pytest.mark.small
def test_is_sync_unreadable_session_file_is_inactive(monkeypatch):
    monkeypatch.setenv("KITTY_WINDOW_ID", "a")
    monkeypatch.setenv("ATUIN_SESSION", "sess")

    class UnreadableSessionFile:
        @staticmethod
        def exists():
            return True

        @staticmethod
        def read_text(*_args, **_kwargs):
            msg = "permission denied"
            raise OSError(msg)

    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: UnreadableSessionFile())

    assert not cli.is_sync_active_in_this_shell()


@pytest.mark.medium
def test_is_sync_success(monkeypatch, tmp_path):
    monkeypatch.setenv("KITTY_WINDOW_ID", "a")
    monkeypatch.setenv("ATUIN_SESSION", "sess")
    session_file = tmp_path / "f"
    session_file.write_text("sess a")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    assert cli.is_sync_active_in_this_shell()


@pytest.mark.medium
def test__collect_kitty_session_diagnostics(monkeypatch, tmp_path):
    state = _state(Pane(id="id", title="title"), tab_id="tab")
    session_file = tmp_path / "atuin_kitty_id"
    session_file.write_text("sessid")
    monkeypatch.setattr(cli, "get_session_file", lambda *_args, **_kwargs: session_file)
    monkeypatch.setattr(cli, "get_last_command_for_atuin_session", lambda *_args, **_kwargs: "cmd")
    ok, missing, corrupt, missing_cmd, notes = _collect_kitty_session_diagnostics(state, verbose=True)
    assert ok or missing or corrupt or missing_cmd
    assert notes == []


@pytest.mark.medium
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
    assert [location.pane.id for location in missing] == ["a"]
    assert [location.pane.id for location, _ in corrupt] == ["b"]
    assert len(missing_cmd) == 1
    assert missing_cmd[0][0].pane.id == "c"
    assert len(ok) == 1
    assert ok[0][0].pane.id == "d"
    assert notes == []


@pytest.mark.small
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
    assert "without optional Atuin pane/session association" in out
    assert "unusable Atuin association state" in out
    assert "no command in Atuin" in out
    assert "Optional Atuin history enrichment active in" in out


@pytest.mark.small
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
    assert "Optional Atuin history enrichment is not active in any open windows" in out


@pytest.mark.small
def test_main_invocation(runner, monkeypatch):
    monkeypatch.setattr(cli, "is_sync_active_in_this_shell", lambda: True)
    monkeypatch.setattr(cli, "get_kitty_state", lambda **_kwargs: KittyState(os_windows=()))

    result = runner.invoke(cli.main, [])

    assert result.exit_code == 0


@pytest.mark.small
def test_print_shell_snippet_and_env(monkeypatch, capsys):
    monkeypatch.setattr(cli, "get_shell_rc_path", lambda *_args, **_kwargs: "rc")
    monkeypatch.setattr(cli, "load_snippet_for_shell", lambda *_args, **_kwargs: "snippet")
    cli.print_shell_snippet("zsh")
    cli.print_shell_snippet("unknown")
    cli.print_env_diagnostics()
    out = capsys.readouterr().out
    assert "Optional Atuin association snippet" in out or "Unknown shell" in out
