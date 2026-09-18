import pytest

from catherd.model import KittyState, OsWindow, Pane, Tab

pytestmark = pytest.mark.small


def test_state_preserves_hierarchy_and_traversal_order():
    pane_a = Pane(id="1", title="one")
    pane_b = Pane(id="2", title="two")
    tab_a = Tab(id="10", title="a", panes=(pane_a, pane_b))
    tab_b = Tab(id="11", title="b", panes=())
    os_window = OsWindow(id="100", title="work", tabs=(tab_a, tab_b))
    state = KittyState(os_windows=(os_window,))

    assert list(state.iter_tabs()) == [(os_window, tab_a), (os_window, tab_b)]
    locations = list(state.iter_panes())
    assert [location.pane.id for location in locations] == ["1", "2"]
    assert all(location.os_window is os_window for location in locations)
    assert all(location.tab is tab_a for location in locations)
    assert state.pane_count == 2
    assert state.find_os_window("100") is os_window
    assert state.find_os_window("missing") is None
    assert state.find_tab("10") == (os_window, tab_a)
    assert state.find_tab("missing") is None
    assert state.find_pane("2") == locations[1]
    assert state.find_pane("missing") is None
