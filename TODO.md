# Immediate work

- [ ] Re-run the focused live TUI acceptance checks after the third fix pass.
  - [ ] Confirm pane `J` / `K` changes both Kitty's visual arrangement and the pane order in catherd's tree.
  - [ ] Confirm tab `J` / `K` changes tab order in both Kitty and catherd.
  - [ ] Confirm a mouse click only selects/highlights a tree object; `Enter` or `f` explicitly focuses it in Kitty.
  - [ ] Confirm `M` on an OS-window row merges OS windows.
  - [ ] Confirm `M` on a tab merges all source panes into the selected destination tab.
  - [ ] Confirm `M` on a pane does not open a merge picker and directs the user to `m`.
  - [ ] Confirm pane details show `Position in tab` and layout neighbors without the old pane/group terminology.
  - [ ] Confirm moving the cursor during polling no longer snaps back to the previously highlighted object.
  - [ ] Confirm moving a pane preserves the selected pane and places the tree cursor on it under its new parent.
  - [ ] Re-test OS-window rename. If it still fails, capture the now-expanded Kitty stderr from the status bar.
- [ ] Run `just check`, fix any remaining discrepancies, then merge `feat/kitty-tui`.
