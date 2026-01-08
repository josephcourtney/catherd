from pathlib import Path

import pytest

from catherd.shell import get_shell_rc_path, load_snippet_for_shell


def test_get_shell_rc_path_zsh(monkeypatch):
    monkeypatch.setenv("ZDOTDIR", "/tmp/zdot")  # noqa: S108
    rc = get_shell_rc_path("zsh")
    assert rc == Path("/tmp/zdot/.zshrc")  # noqa: S108


def test_get_shell_rc_path_bash():
    rc = get_shell_rc_path("bash")
    assert rc.name == ".bashrc"


def test_get_shell_rc_path_fish(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xconfig")  # noqa: S108
    rc = get_shell_rc_path("fish")
    assert str(rc).endswith("fish/config.fish")


def test_load_snippet_for_shell():
    for sh in ("bash", "zsh", "fish", "csh"):
        txt = load_snippet_for_shell(sh)
        assert "ATUIN_SESSION" in txt or txt.startswith("# (no snippet")

    rc = get_shell_rc_path("fish")
    assert rc.name == "config.fish"


def test_load_snippet_unknown_shell():
    with pytest.raises(ValueError, match="Unknown shell"):
        load_snippet_for_shell("notarealshell")


def test_get_shell_rc_path():
    assert get_shell_rc_path("zsh").name == ".zshrc"
    assert get_shell_rc_path("bash").name == ".bashrc"
    assert get_shell_rc_path("fish").name == "config.fish"
    assert get_shell_rc_path("csh").name == ".cshrc"
    with pytest.raises(ValueError, match="Unknown shell"):
        get_shell_rc_path("noshell")


def test_get_shell_rc_path_zsh_no_zdotdir(monkeypatch):
    monkeypatch.delenv("ZDOTDIR", raising=False)
    rc = get_shell_rc_path("zsh")
    assert rc.name == ".zshrc"


def test_get_shell_rc_path_fish_no_xdg(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    rc = get_shell_rc_path("fish")
    assert rc.name == "config.fish"
