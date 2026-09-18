from pathlib import Path
from unittest.mock import patch

import pytest

from catherd import config

pytestmark = pytest.mark.small


def test_get_xdg_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with patch.object(Path, "mkdir") as mkdir:
        path = config.get_xdg_cache_dir()
    assert path == tmp_path / "catherd"
    mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_get_xdg_cache_dir_default(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    with patch.object(Path, "mkdir") as mkdir:
        path = config.get_xdg_cache_dir()
    assert path == tmp_path / ".cache" / "catherd"
    mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_get_xdg_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with patch.object(Path, "mkdir") as mkdir:
        path = config.get_xdg_config_dir()
    assert path == tmp_path / "catherd"
    mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_get_session_file(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    with patch.object(Path, "mkdir"):
        session_path = config.get_session_file("abc123")
    assert session_path == tmp_path / "catherd" / "atuin_kitty_abc123"
