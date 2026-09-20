from pathlib import Path

import pytest

from catherd.shell import (
    ATUIN_INTEGRATION_MARKER,
    LEGACY_ATUIN_INTEGRATION_END_MARKER,
    LEGACY_ATUIN_INTEGRATION_MARKER,
    SUPPORTED_SHELLS,
    append_managed_snippet,
    get_shell_rc_path,
    load_snippet_for_shell,
    managed_snippet_block,
    managed_snippet_state,
    replace_managed_snippet,
)


@pytest.mark.small
def test_get_shell_rc_path_zsh(monkeypatch):
    monkeypatch.setenv("ZDOTDIR", "/tmp/zdot")  # ruff: ignore[hardcoded-temp-file]
    rc = get_shell_rc_path("zsh")
    assert rc == Path("/tmp/zdot/.zshrc")  # ruff: ignore[hardcoded-temp-file]


@pytest.mark.small
def test_get_shell_rc_path_bash():
    rc = get_shell_rc_path("bash")
    assert rc.name == ".bashrc"


@pytest.mark.small
def test_get_shell_rc_path_fish(monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xconfig")  # ruff: ignore[hardcoded-temp-file]
    rc = get_shell_rc_path("fish")
    assert str(rc).endswith("fish/config.fish")


@pytest.mark.small
def test_load_snippets_are_shell_native():
    for shell in SUPPORTED_SHELLS:
        snippet = load_snippet_for_shell(shell)
        assert "ATUIN_SESSION" in snippet
        assert "KITTY_WINDOW_ID" in snippet
        assert "atuin_kitty_" in snippet

    assert "${XDG_CACHE_HOME:-" not in load_snippet_for_shell("fish")
    assert "${XDG_CACHE_HOME:-" not in load_snippet_for_shell("csh")


@pytest.mark.small
def test_load_snippet_unknown_shell():
    with pytest.raises(ValueError, match="Unknown shell"):
        load_snippet_for_shell("notarealshell")


@pytest.mark.small
def test_get_shell_rc_path():
    assert get_shell_rc_path("zsh").name == ".zshrc"
    assert get_shell_rc_path("bash").name == ".bashrc"
    assert get_shell_rc_path("fish").name == "config.fish"
    assert get_shell_rc_path("csh").name == ".cshrc"
    with pytest.raises(ValueError, match="Unknown shell"):
        get_shell_rc_path("noshell")


@pytest.mark.small
def test_get_shell_rc_path_zsh_no_zdotdir(monkeypatch):
    monkeypatch.delenv("ZDOTDIR", raising=False)
    rc = get_shell_rc_path("zsh")
    assert rc.name == ".zshrc"


@pytest.mark.small
def test_get_shell_rc_path_fish_no_xdg(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    rc = get_shell_rc_path("fish")
    assert rc.name == "config.fish"


@pytest.mark.small
def test_managed_snippet_state_recognizes_current_and_legacy():
    current = managed_snippet_block("zsh")
    legacy = f"{LEGACY_ATUIN_INTEGRATION_MARKER}\nlegacy body\n{LEGACY_ATUIN_INTEGRATION_END_MARKER}\n"

    assert managed_snippet_state("setopt foo\n") == "absent"
    assert managed_snippet_state(current) == "current"
    assert managed_snippet_state(legacy) == "legacy"


@pytest.mark.small
def test_replace_legacy_block_preserves_surrounding_rc_text():
    original = (
        "before exactly\n"
        f"{LEGACY_ATUIN_INTEGRATION_MARKER}\n"
        "legacy body\n"
        f"{LEGACY_ATUIN_INTEGRATION_END_MARKER}\n"
        "after exactly\n"
    )
    replacement = managed_snippet_block("zsh")

    migrated, replaced = replace_managed_snippet(original, replacement)

    assert replaced
    assert migrated.startswith("before exactly\n")
    assert migrated.endswith("after exactly\n")
    assert LEGACY_ATUIN_INTEGRATION_MARKER not in migrated
    assert ATUIN_INTEGRATION_MARKER in migrated


@pytest.mark.small
def test_remove_managed_block_preserves_surrounding_rc_text():
    original = f"before\n{managed_snippet_block('bash')}after\n"

    removed, found = replace_managed_snippet(original, None)

    assert found
    assert removed == "before\nafter\n"


@pytest.mark.small
def test_malformed_managed_block_is_rejected_without_guessing():
    malformed = f"keep me\n{LEGACY_ATUIN_INTEGRATION_MARKER}\nunterminated\n"

    with pytest.raises(ValueError, match="Unterminated"):
        managed_snippet_state(malformed)

    with pytest.raises(ValueError, match="Unterminated"):
        replace_managed_snippet(malformed, None)


@pytest.mark.small
def test_multiple_managed_blocks_are_rejected():
    duplicated = managed_snippet_block("bash") + managed_snippet_block("bash")

    with pytest.raises(ValueError, match="Multiple"):
        managed_snippet_state(duplicated)


@pytest.mark.small
def test_append_managed_snippet_uses_minimal_separator():
    block = managed_snippet_block("bash")

    assert append_managed_snippet("", block) == block
    assert append_managed_snippet("existing\n", block) == "existing\n" + block
    assert append_managed_snippet("existing", block) == "existing\n" + block


@pytest.mark.small
def test_append_then_remove_round_trips_newline_terminated_contents():
    original = "existing\n"
    installed = append_managed_snippet(original, managed_snippet_block("bash"))

    removed, found = replace_managed_snippet(installed, None)

    assert found
    assert removed == original
