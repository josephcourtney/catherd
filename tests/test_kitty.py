import json
from unittest.mock import MagicMock, patch

import pytest

from catherd.kitty import KittyWindow, get_kitty_windows

pytestmark = pytest.mark.small


def test_kittywindow_dataclass():
    w = KittyWindow(id="w", tab="t", title="foo")
    assert w.id == "w"
    assert w.tab == "t"
    assert w.title == "foo"
    assert w.os_window_id is None
    assert w.pid is None
    assert w.foreground_cmd is None


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_get_kitty_windows_json_parsing(mock_run, mock_which):
    # Use a fake kitty ls output
    mock_run.return_value = MagicMock(
        returncode=0,
        stdout=json.dumps([
            {
                "id": 42,
                "is_focused": True,
                "tabs": [
                    {
                        "id": "tabA",
                        "title": "tab",
                        "is_focused": True,
                        "windows": [
                            {
                                "id": 11,
                                "title": "w1",
                                "is_focused": True,
                                "has_bell": False,
                                "is_urgent": True,
                                "cwd": "/safe/cwd",
                                "tty": "/dev/pts/1",
                                "cols": 80,
                                "rows": 24,
                                "x": 10,
                                "y": 5,
                                "foreground_process": {"argv0": "bash", "pid": 100},
                            }
                        ],
                    }
                ],
            }
        ]),
        stderr="",
    )
    windows = get_kitty_windows()
    assert isinstance(windows, list)
    assert isinstance(windows[0], KittyWindow)
    assert windows[0].id == "11"
    assert windows[0].os_window_id == "42"
    assert windows[0].tab == "tabA"
    assert windows[0].tab_title == "tab"
    assert windows[0].is_active_os_window is True
    assert windows[0].is_active_tab is True
    assert windows[0].is_active_window is True
    assert windows[0].foreground_cmd == "bash"
    assert windows[0].pid == 100
    assert windows[0].cwd == "/safe/cwd"
    assert windows[0].tty == "/dev/pts/1"
    assert windows[0].cols == 80
    assert windows[0].rows == 24
    assert windows[0].x == 10
    assert windows[0].y == 5
    assert windows[0].has_bell is False
    assert windows[0].is_urgent is True


def test_kittywindow_repr_and_fields():
    k = KittyWindow(id="abc", tab="tabX", title="my title")
    assert k.id == "abc"
    assert k.tab == "tabX"
    assert k.title == "my title"
    assert repr(k).startswith("KittyWindow(")


def test_get_kitty_windows_kitty_not_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: None)
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
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 1
        stdout = ""
        stderr = "fail"

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    result = get_kitty_windows()
    assert result is None


def test_get_kitty_windows_json_decode_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = "{not-json"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    result = get_kitty_windows()
    assert result is None


def test_get_kitty_windows_no_windows(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = json.dumps([])
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    result = get_kitty_windows()
    assert isinstance(result, list)
    assert result == []


def test_get_kitty_windows_verbose_branch(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = '[{"tabs":[]}]'
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    get_kitty_windows(verbose=True)
    out = capsys.readouterr().out
    assert "Raw output" in out
