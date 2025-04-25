import sqlite3

from catherd.atuin import get_atuin_history_db_path, get_last_command_for_atuin_session


def test_atuin_history_db_path(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    path = get_atuin_history_db_path()
    assert path.parts[-2:] == ("atuin", "history.db")
    assert str(path).startswith(str(tmp_path))


def test_get_last_command_no_db(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert get_last_command_for_atuin_session("foo", verbose=True) == "(no history db)"


def test_get_last_command_with_db(tmp_path, monkeypatch):
    dbdir = tmp_path / "atuin"
    dbdir.mkdir()
    dbfile = dbdir / "history.db"
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    con = sqlite3.connect(str(dbfile))
    con.execute("CREATE TABLE history (session TEXT, command TEXT, timestamp INTEGER)")
    con.execute(
        "INSERT INTO history (session, command, timestamp) VALUES (?, ?, ?)", ("sess1", "ls -l", 12345)
    )
    con.commit()
    con.close()
    assert get_last_command_for_atuin_session("sess1") == "ls -l"
    assert get_last_command_for_atuin_session("nope") == "(no command)"


def test_get_last_command_db_error(monkeypatch, tmp_path):
    # Create a "corrupt" history.db that isn't actually a DB
    dbdir = tmp_path / "atuin"
    dbdir.mkdir()
    dbfile = dbdir / "history.db"
    dbfile.write_text("NOTADB", encoding="utf-8")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    # Should hit the except block and return "(sqlite error)"
    result = get_last_command_for_atuin_session("sess", verbose=True)
    assert result == "(sqlite error)"
