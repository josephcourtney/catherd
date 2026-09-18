import pytest

from catherd import activity


@pytest.mark.medium
def test_get_atuin_session_for_window_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(activity, "get_session_file", lambda _window_id: tmp_path / "missing")

    assert activity.get_atuin_session_for_window("1") is None


@pytest.mark.medium
def test_get_atuin_session_for_window_reads_session(tmp_path, monkeypatch):
    session_file = tmp_path / "session"
    session_file.write_text("session-1 42", encoding="utf-8")
    monkeypatch.setattr(activity, "get_session_file", lambda _window_id: session_file)

    assert activity.get_atuin_session_for_window("42") == "session-1"


@pytest.mark.small
def test_get_pane_activity(monkeypatch):
    monkeypatch.setattr(activity, "get_atuin_session_for_window", lambda _window_id: "session-1")
    monkeypatch.setattr(activity, "get_last_command_for_atuin_session", lambda _session_id: "pytest")

    assert activity.get_pane_activity("42") == activity.PaneActivity(
        session_id="session-1",
        last_command="pytest",
    )


@pytest.mark.small
def test_get_pane_activity_without_session(monkeypatch):
    monkeypatch.setattr(activity, "get_atuin_session_for_window", lambda _window_id: None)

    assert activity.get_pane_activity("42") == activity.PaneActivity(
        session_id=None,
        last_command=None,
    )
