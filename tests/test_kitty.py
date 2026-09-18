import json
from unittest.mock import MagicMock, patch

import pytest

from catherd.kitty import KittyClient, KittyObjectNotFoundError, get_kitty_state, parse_kitty_state
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
                            "title_overridden": True,
                            "is_focused": True,
                            "pid": 100,
                            "cwd": "/shell/cwd",
                            "cmdline": ["/bin/zsh", "-l"],
                            "last_reported_cmdline": "uv run pytest",
                            "at_prompt": False,
                            "lines": 24,
                            "columns": 80,
                            "needs_attention": True,
                            "has_activity_since_last_focus": True,
                            "foreground_processes": [
                                {
                                    "pid": 201,
                                    "cwd": "/safe/cwd",
                                    "cmdline": ["python", "-m", "pytest"],
                                }
                            ],
                            "env": {},
                        },
                        {
                            "id": 12,
                            "title": "Rename tab",
                            "pid": 202,
                            "cwd": "/safe/cwd",
                            "cmdline": ["kitten", "__run__"],
                            "env": {"KITTEN_RUNNING_AS_UI": "1"},
                        },
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
    assert len(tab.panes) == 1
    assert pane.foreground_cmd == "python -m pytest"
    assert pane.pid == 201
    assert pane.cwd == "/safe/cwd"
    assert pane.root_cmdline == "/bin/zsh -l"
    assert pane.current_command == "uv run pytest"
    assert pane.at_prompt is False
    assert pane.title_overridden is True
    assert pane.needs_attention is True
    assert pane.has_activity_since_last_focus is True
    assert pane.cols == 80
    assert pane.rows == 24
    assert pane.is_urgent is True


def test_parse_kitty_state_tolerates_non_mapping_entries():
    state = parse_kitty_state([None, "x", {"tabs": [None, {"windows": [None]}]}])
    assert len(state.os_windows) == 1
    assert len(state.os_windows[0].tabs) == 1
    assert state.pane_count == 0


def test_parse_kitty_state_tolerates_unsupported_integer_metadata():
    state = parse_kitty_state([
        {
            "tabs": [
                {
                    "windows": [
                        {
                            "id": 1,
                            "title": "pane",
                            "pid": {},
                            "columns": [],
                            "lines": 24.5,
                        }
                    ]
                }
            ]
        }
    ])
    pane = state.os_windows[0].tabs[0].panes[0]
    assert pane.pid is None
    assert pane.cols is None
    assert pane.rows == 24


@patch("shutil.which", return_value="/usr/bin/kitty")
@patch("subprocess.run")
def test_get_kitty_state_json_parsing(mock_run, mock_which):
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
        msg = "fail"
        raise FileNotFoundError(msg)

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


def _operation_state() -> KittyState:
    return KittyState(
        os_windows=(
            OsWindow(
                id="100",
                title="source",
                tabs=(
                    Tab(id="10", title="one", panes=(Pane(id="1", title="one"),)),
                    Tab(id="11", title="two", panes=(Pane(id="2", title="two"),)),
                ),
            ),
            OsWindow(
                id="200",
                title="target",
                tabs=(Tab(id="20", title="three", panes=(Pane(id="3", title="three"),)),),
            ),
        )
    )


def _record_remote_calls(monkeypatch):
    calls: list[tuple[str, ...]] = []

    def fake_run(command, **_kwargs):
        calls.append(tuple(command))
        return MagicMock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    return calls


def test_client_focus_and_rename_operations(monkeypatch):
    calls = _record_remote_calls(monkeypatch)
    state = _operation_state()
    monkeypatch.setattr(KittyClient, "snapshot", lambda _self: state)
    client = KittyClient(executable="/usr/bin/kitty")

    client.focus_pane("1")
    client.focus_tab("10")
    client.focus_os_window("200")
    client.rename_pane("1", "editor")
    client.rename_tab("10", "work")
    client.rename_os_window("200", "project")

    assert calls == [
        ("/usr/bin/kitty", "@", "focus-window", "--match", "id:1"),
        ("/usr/bin/kitty", "@", "focus-tab", "--match", "id:10"),
        ("/usr/bin/kitty", "@", "focus-window", "--match", "id:3"),
        ("/usr/bin/kitty", "@", "set-window-title", "--match", "id:1", "editor"),
        ("/usr/bin/kitty", "@", "set-tab-title", "--match", "id:10", "work"),
        ("/usr/bin/kitty", "@", "set-os-window-title", "--match", "id:3", "project"),
    ]


def test_client_move_and_detach_operations(monkeypatch):
    calls = _record_remote_calls(monkeypatch)
    state = _operation_state()
    monkeypatch.setattr(KittyClient, "snapshot", lambda _self: state)
    client = KittyClient(executable="/usr/bin/kitty")

    client.move_pane("1", "20")
    client.detach_pane_to_new_tab("1")
    client.detach_pane_to_new_os_window("1")
    client.move_tab("10", "200")
    client.detach_tab_to_new_os_window("10")

    assert calls == [
        (
            "/usr/bin/kitty",
            "@",
            "detach-window",
            "--match",
            "id:1",
            "--target-tab",
            "id:20",
        ),
        (
            "/usr/bin/kitty",
            "@",
            "detach-window",
            "--match",
            "id:1",
            "--target-tab",
            "new",
        ),
        ("/usr/bin/kitty", "@", "detach-window", "--match", "id:1"),
        (
            "/usr/bin/kitty",
            "@",
            "detach-tab",
            "--match",
            "id:10",
            "--target-tab",
            "id:20",
        ),
        ("/usr/bin/kitty", "@", "detach-tab", "--match", "id:10"),
    ]


def test_client_reorder_operations_focus_before_move(monkeypatch):
    calls = _record_remote_calls(monkeypatch)
    monkeypatch.setattr(KittyClient, "snapshot", lambda _self: _operation_state())
    client = KittyClient(executable="/usr/bin/kitty")

    client.reorder_pane("1", "forward")
    client.reorder_pane("1", "backward")
    client.reorder_tab("10", "forward")
    client.reorder_tab("10", "backward")

    assert calls == [
        ("/usr/bin/kitty", "@", "focus-window", "--match", "id:1"),
        ("/usr/bin/kitty", "@", "action", "--match", "id:1", "move_window_forward"),
        ("/usr/bin/kitty", "@", "focus-window", "--match", "id:1"),
        ("/usr/bin/kitty", "@", "action", "--match", "id:1", "move_window_backward"),
        ("/usr/bin/kitty", "@", "focus-tab", "--match", "id:10"),
        ("/usr/bin/kitty", "@", "action", "--match", "id:1", "move_tab_forward"),
        ("/usr/bin/kitty", "@", "focus-tab", "--match", "id:10"),
        ("/usr/bin/kitty", "@", "action", "--match", "id:1", "move_tab_backward"),
    ]


def test_client_merge_os_windows_moves_all_source_tabs(monkeypatch):
    calls = _record_remote_calls(monkeypatch)
    state = _operation_state()
    monkeypatch.setattr(KittyClient, "snapshot", lambda _self: state)
    client = KittyClient(executable="/usr/bin/kitty")

    client.merge_os_windows("100", "200")

    assert calls == [
        (
            "/usr/bin/kitty",
            "@",
            "detach-tab",
            "--match",
            "id:10",
            "--target-tab",
            "id:20",
        ),
        (
            "/usr/bin/kitty",
            "@",
            "detach-tab",
            "--match",
            "id:11",
            "--target-tab",
            "id:20",
        ),
    ]


def test_client_merge_same_os_window_is_noop(monkeypatch):
    calls = _record_remote_calls(monkeypatch)
    client = KittyClient(executable="/usr/bin/kitty")

    client.merge_os_windows("100", "100")

    assert calls == []


def test_client_operation_reports_missing_os_window(monkeypatch):
    monkeypatch.setattr(KittyClient, "snapshot", lambda _self: _operation_state())
    client = KittyClient(executable="/usr/bin/kitty")

    with pytest.raises(KittyObjectNotFoundError, match="OS window"):
        client.move_tab("10", "missing")
