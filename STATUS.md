# Status

This file records the current short-horizon project state for continuity and handoff.

## Current state

catherd is in 0.19.0 public-release hardening. The core Kitty organizer remains functionally complete for the scope defined in DESIGN.md: inspection, filtering, explicit focus, rename, move, reorder, and merge all operate from Kitty state.

Public-release Phase 1 is complete. Kitty is now explicitly the required core boundary, while Atuin is defined as optional completed-command history enrichment. Kitty shell integration and catherd's optional Kitty-pane-to-Atuin-session association are documented as separate mechanisms.

The TUI makeover remains complete: selection is distinct from Kitty focus, native tree collapse/expand behavior is preserved, connector topology is continuous, tab groups use non-structural banding, and the inspector separates status, location, process, and optional history information.

## Verification

`just check` passes on the current Phase 1 state.

The existing suite covers interaction, structural mutations, and refresh races. Phase 1 adds explicit regression coverage that:

- `catherd show` uses Kitty current-command/process state with no Atuin session files or history database;
- the TUI starts, renders Kitty command state, and performs core focus operations with no Atuin state present.

Real-Kitty/macOS rehearsal remains the appropriate check for behavior that depends on Kitty remote control or native-window effects.

## Known limitations

These are intentional current-scope boundaries, not incomplete core work:

- catherd does not create shells, panes, tabs, or OS windows;
- catherd does not close processes or terminal objects;
- Atuin history is optional enrichment and may be unavailable independently of Kitty state.

## Next

Proceed to PLAN.md Phase 2: isolate and harden the optional Atuin integration, including explicit integration-scoped CLI terminology and validated shell snippets.
