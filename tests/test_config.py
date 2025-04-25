from catherd import config


def test_get_xdg_cache_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    path = config.get_xdg_cache_dir()
    assert path.exists()
    assert path.name == "catherd"
    assert path.parent == tmp_path


def test_get_xdg_cache_dir_default(monkeypatch):
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    path = config.get_xdg_cache_dir()
    assert "catherd" in str(path)


def test_get_xdg_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = config.get_xdg_config_dir()
    assert path.exists()
    assert path.name == "catherd"
    assert path.parent == tmp_path


def test_get_session_file(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    fid = "abc123"
    session_path = config.get_session_file(fid)
    assert session_path.name == f"atuin_kitty_{fid}"
    assert "catherd" in str(session_path.parent)
