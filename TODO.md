# Immediate work

- [ ] Run the TUI against a disposable live Kitty layout with at least two OS windows, multiple tabs, and one split tab.
  - Verify focus for panes, tabs, and OS windows.
  - Verify pane/tab/OS-window rename behavior and title persistence.
  - Verify pane moves to an existing tab, a new tab, and a new OS window.
  - Verify tab moves and detachment to a new OS window.
  - Verify pane/tab reorder direction matches the displayed tree order.
  - Verify OS-window merge moves every source tab and removes the empty source window.
  - Verify external Kitty changes are reflected by polling without losing the logical selection.
  - Verify structural operations return focus to the catherd pane while explicit `Enter` focus does not.
  - Verify the details panel tracks the highlighted object and pane Atuin activity updates without blocking navigation.
- [ ] Fix any discrepancies found during the live rehearsal, run `just check`, then merge `feat/kitty-tui`.
