# Immediate work

- [ ] Re-run the live TUI acceptance rehearsal after the first acceptance-fix pass.
  - [ ] Confirm `r` immediately updates the displayed pane/tab/OS-window name.
  - [ ] Confirm `J` / `K` actually reorder both panes and tabs and that direction matches the displayed tree.
  - [ ] Confirm `M` opens the merge picker from an OS-window, tab, or pane selection and moves every source tab.
  - [ ] Confirm Kitty's transient `Rename tab` overlay never appears as a catherd pane.
  - [ ] Confirm a command that is still running appears as `Current command`, while Atuin history is labeled `Last completed command`.
  - [ ] Confirm pane size, foreground process/PID, prompt state, title-lock state, and attention/activity state populate from Kitty.
  - [ ] Confirm unsupported Kitty `ls` fields (TTY, pixel position, standalone bell/urgent fields) are no longer presented as perpetually unknown details.
  - [ ] Verify pane moves to an existing tab, a new tab, and a new OS window.
  - [ ] Verify tab moves and detachment to a new OS window.
  - [ ] Verify external Kitty changes are reflected by polling without losing logical selection or unrelated collapsed state.
  - [ ] Verify structural operations return focus to the catherd pane while explicit `Enter` focus does not.
- [ ] Run `just check` after the live rehearsal, fix any remaining discrepancies, then merge `feat/kitty-tui`.
