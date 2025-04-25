import json
import sqlite3

from catherd import core
from catherd.core import (
    get_atuin_session_for_window,
    get_kitty_windows,
    get_last_command_for_atuin_session,
)


def test_get_last_command_for_atuin_session_no_db(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    # No history.db in XDG_DATA_HOME
    assert get_last_command_for_atuin_session("sess1") == "(no history db)"
    assert get_last_command_for_atuin_session("sess2") == "(no history db)"


def test_get_last_command_for_atuin_session_success(tmp_path, monkeypatch):
    dbdir = tmp_path / "atuin"
    dbdir.mkdir()
    dbfile = dbdir / "history.db"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    con = sqlite3.connect(str(dbfile))
    con.execute("CREATE TABLE history (session TEXT, command TEXT, timestamp INTEGER)")
    con.execute(
        "INSERT INTO history (session, command, timestamp) VALUES (?, ?, ?)",
        ("mysess", "ls -l", 12345),
    )
    con.commit()
    con.close()
    assert get_last_command_for_atuin_session("mysess") == "ls -l"
    assert get_last_command_for_atuin_session("nope") == "(no command)"


def test_get_kitty_windows_kitty_not_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_args, **_kwargs: None)
    result = get_kitty_windows()
    assert result is None


def test_get_kitty_windows_subprocess_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    def raise_exc(*_a, **_k):
        msg = "fail"
        raise FileNotFoundError(msg)

    monkeypatch.setattr("subprocess.run", raise_exc)
    result = get_kitty_windows()
    assert result is None


def test_get_kitty_windows_nonzero_return(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_args, **_kwargs: "/usr/bin/kitty")

    class R:
        returncode = 1
        stdout = ""
        stderr = "fail"

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    result = get_kitty_windows()
    assert result is None


def test_get_kitty_windows_json_decode_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_args, **_kwargs: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = "{not-json"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    result = get_kitty_windows()
    assert result is None


def test_get_kitty_windows_no_windows(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda *_args, **_kwargs: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = json.dumps([])
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    wins = get_kitty_windows()
    assert isinstance(wins, list)
    assert wins == []


def test_get_atuin_session_for_window_file_not_found(monkeypatch, tmp_path):
    path = tmp_path / "notfound"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(core, "get_session_file", lambda *_args, **_kwargs: path)
    assert get_atuin_session_for_window("id", verbose=True) is None


def test_get_atuin_session_for_window_empty_file(monkeypatch, tmp_path):
    path = tmp_path / "found"
    path.write_text("")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(core, "get_session_file", lambda *_args, **_kwargs: path)
    assert get_atuin_session_for_window("id", verbose=True) is None


def test_get_atuin_session_for_window_valid(monkeypatch, tmp_path):
    path = tmp_path / "found"
    path.write_text("abc123")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(core, "get_session_file", lambda *_args, **_kwargs: path)
    assert get_atuin_session_for_window("id", verbose=True) == "abc123"


def test_get_kitty_windows_verbose_print(monkeypatch, capsys):
    # Should hit verbose print and .stdout
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = json.dumps([{"tabs": [{"id": 1, "title": "tab", "windows": [{"id": 11, "title": "w1"}]}]}])
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    get_kitty_windows(verbose=True)
    out = capsys.readouterr().out
    assert "Raw output" in out


def test_get_kitty_windows_multi_tab_parse(monkeypatch):
    # Actually parse inner windows/tabs logic
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")
    # Multiple tabs, windows
    data = [
        {
            "tabs": [
                {"id": "t1", "title": "tab1", "windows": [{"id": "w1", "title": "wtitle1"}]},
                {"id": "t2", "title": "tab2", "windows": [{"id": "w2"}]},
            ]
        }
    ]

    class R:
        returncode = 0
        stdout = json.dumps(data)
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    wins = get_kitty_windows()
    assert len(wins) == 2
    assert wins[0]["id"] == "w1"
    assert wins[1]["id"] == "w2"


def test_get_last_command_for_atuin_session_verbose_no_db(tmp_path, monkeypatch, capsys):
    # Should print "[verbose] Atuin history DB not found"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    get_last_command_for_atuin_session("abc", verbose=True)
    out = capsys.readouterr().out
    assert "Atuin history DB not found" in out


def test_get_last_command_for_atuin_session_sqlite_error(tmp_path, monkeypatch, capsys):
    # Corrupt DB triggers the verbose SQLite error
    dbdir = tmp_path / "atuin"
    dbdir.mkdir()
    dbfile = dbdir / "history.db"
    dbfile.write_text("notadb", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    get_last_command_for_atuin_session("x", verbose=True)
    out = capsys.readouterr().out
    assert "SQLite error" in out


def test_core_main_all_branches(capsys):
    core.get_kitty_windows = lambda *_args, **_kwargs: [{"id": "w", "tab": "t", "title": "long"}]
    core.get_atuin_session_for_window = lambda *_args, **_kwargs: "sessid"
    core.get_last_command_for_atuin_session = lambda *_args, **_kwargs: "cmd"

    core.main(verbose=False)
    out = capsys.readouterr().out
    assert "Kitty WinID" in out
    assert "cmd" in out


def test_core_main_no_windows(capsys):
    core.get_kitty_windows = lambda *_args, **_kwargs: []
    core.main(verbose=False)
    out = capsys.readouterr().out
    assert "Kitty WinID" in out
