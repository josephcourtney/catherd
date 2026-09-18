# Immediate work

- [ ] Re-run the focused live TUI acceptance checks after the second fix pass.
  - [ ] Confirm `J` / `K` reorder panes and tabs and that direction matches the tree.
  - [ ] Confirm OS-window rename updates the catherd tree label and the Kitty OS-window title.
  - [ ] Confirm `M` opens the merge picker and merges the selected node's containing OS window.
  - [ ] Confirm pane details show logical position within the tab: pane ordinal, layout-group ordinal, and neighbors.
  - [ ] Confirm moving a pane preserves the selected pane and places the tree cursor on it under its new parent.
- [ ] Run `just check`, fix any remaining discrepancies, then merge `feat/kitty-tui`.
