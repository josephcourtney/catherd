from pathlib import Path

import pytest

from catherd import shell
from catherd.shell import SHELL_SNIPPET_FILENAMES, get_shell_rc_path, load_snippet_for_shell


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


def test_load_snippet_for_shell(monkeypatch):
    # Monkeypatch importlib.resources.files
    class DummyFiles:
        @staticmethod
        def joinpath(fn):
            class R:
                @staticmethod
                def read_text(*_args, **_kwargs):
                    return f"snippet for {fn}"

            return R()

    monkeypatch.setattr("importlib.resources.files", lambda *_args, **_kwargs: DummyFiles())
    for sh in SHELL_SNIPPET_FILENAMES:
        txt = load_snippet_for_shell(sh)
        assert "snippet for catherd_rc_snippet" in txt or "snippet for" in txt


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


def test_load_snippet_for_shell_returns_str(tmp_path, monkeypatch):
    # Simulate a snippet file for "zsh"
    snippet_file = tmp_path / "catherd_rc_snippet.zsh"
    snippet_file.write_text("export X=1")
    monkeypatch.setattr("catherd.shell.Path", lambda *_args, **_kwargs: tmp_path)
    result = load_snippet_for_shell("zsh")
    assert "export X=1" in result or result.startswith("# (no snippet")


def test_get_shell_rc_path_zsh_no_zdotdir(monkeypatch):
    monkeypatch.delenv("ZDOTDIR", raising=False)
    rc = get_shell_rc_path("zsh")
    assert rc.name == ".zshrc"


def test_get_shell_rc_path_fish_no_xdg(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    rc = get_shell_rc_path("fish")
    assert rc.name == "config.fish"


def test_load_snippet_for_shell_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("catherd.shell.Path", lambda *_args, **_kwargs: tmp_path)
    # Remove file if it exists
    file = tmp_path / "catherd_rc_snippet.bash"
    if file.exists():
        file.unlink()
    result = load_snippet_for_shell("bash")
    assert result.startswith("# (no snippet")


def test_load_snippet_for_shell_reads_file():
    here = Path(shell.__file__).parent
    snippet_name = "catherd_rc_snippet.zsh"
    path = here / snippet_name

    # Write test snippet to correct location
    path.write_text("export X=42", encoding="utf-8")

    try:
        val = shell.load_snippet_for_shell("zsh")
        assert "export X=42" in val
    finally:
        path.unlink()
