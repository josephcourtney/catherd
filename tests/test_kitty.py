import json
from unittest.mock import MagicMock, patch

import pytest

from catherd.kitty import KittyClient, get_kitty_state, parse_kitty_state
from catherd.model import KittyState, OsWindow, Pane, Tab

pytestmark = pytest.mark.small


def _payload():
    return [
        {
            "id": 42,
            "title": "work",
            "is_focused": True,
            "tabs": [
                {
                    "id": "tabA",
                    "title": "tab",
                    "layout": "splits",
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
    ]


def test_parse_kitty_state_preserves_hierarchy_and_metadata():
    state = parse_kitty_state(_payload())
    assert isinstance(state, KittyState)
    os_window = state.os_windows[0]
    assert isinstance(os_window, OsWindow)
    assert os_window.id == "42"
    assert os_window.title == "work"
    assert os_window.is_active is True

    tab = os_window.tabs[0]
    assert isinstance(tab, Tab)
    assert tab.id == "tabA"
    assert tab.title == "tab"
    assert tab.layout == "splits"
    assert tab.is_active is True

    pane = tab.panes[0]
    assert isinstance(pane, Pane)
    assert pane.id == "11"
    assert pane.title == "w1"
    assert pane.is_active is True
    assert pane.foreground_cmd == "bash"
    assert pane.pid == 100
    assert pane.cwd == "/safe/cwd"
    assert pane.tty == "/dev/pts/1"
    assert pane.cols == 80
    assert pane.rows == 24
    assert pane.x == 10
    assert pane.y == 5
    assert pane.has_bell is False
    assert pane.is_urgent is True


def test_parse_kitty_state_tolerates_non_mapping_entries():
    state = parse_kitty_state([None, "x", {"tabs": [None, {"windows": [None]}]}])
    assert len(state.os_windows) == 1
    assert len(state.os_windows[0].tabs) == 1
    assert state.pane_count == 0


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_get_kitty_state_json_parsing(mock_run, mock_which):  # noqa: ARG001
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(_payload()), stderr="")
    state = get_kitty_state()
    assert state is not None
    assert state.os_windows[0].tabs[0].panes[0].id == "11"


def test_client_snapshot_uses_parser(monkeypatch):
    client = KittyClient(executable="/usr/bin/kitty")
    monkeypatch.setattr(client.__class__, "read_state_json", lambda _self: json.dumps(_payload()))
    state = client.snapshot()
    assert state.pane_count == 1


def test_get_kitty_state_kitty_not_found(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: None)
    assert get_kitty_state() is None


def test_get_kitty_state_subprocess_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    def raise_exc(*_a, **_k):
        raise FileNotFoundError("fail")

    monkeypatch.setattr("subprocess.run", raise_exc)
    assert get_kitty_state() is None


def test_get_kitty_state_nonzero_return(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 1
        stdout = ""
        stderr = "fail"

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    assert get_kitty_state() is None


def test_get_kitty_state_json_decode_error(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = "{not-json"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    assert get_kitty_state() is None


def test_get_kitty_state_no_windows(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = "[]"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    state = get_kitty_state()
    assert state == KittyState(os_windows=())


def test_get_kitty_state_verbose_branch(monkeypatch, capsys):
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/kitty")

    class R:
        returncode = 0
        stdout = '[{"tabs":[]}]'
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *_a, **_k: R())
    get_kitty_state(verbose=True)
    out = capsys.readouterr().out
    assert "Raw output" in out
