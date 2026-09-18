# Immediate work

- [ ] Run `just test-tui` and `just check`.
- [ ] Perform only the remaining real-Kitty/macOS boundary checks:
  - [ ] Confirm pane and tab `J` / `K` remote-control actions produce the same visual ordering that Kitty reports through `ls`.
  - [ ] Confirm explicit `Enter` / `f` focus switches the intended real Kitty pane/tab/OS window while ordinary mouse selection in catherd does not trigger an extra remote focus action.
  - [ ] Confirm tab merge moves every source pane into the chosen target tab and Kitty removes the emptied source tab.
  - [ ] Confirm OS-window merge moves every source tab and Kitty removes the emptied source OS window.
  - [ ] Re-test native OS-window rename. If it fails, capture the expanded Kitty stderr from the status bar.
- [ ] Fix any boundary discrepancies, run `just check`, then merge `feat/kitty-tui`.
