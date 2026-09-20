# Status

This file records the current short-horizon project state for continuity and handoff.

## Current state

catherd 0.18.x is functionally complete for the scope defined in DESIGN.md. The interactive organizer supports inspection, filtering, explicit focus, rename, move, reorder, and merge operations over an existing Kitty hierarchy, with optional Atuin enrichment.

The TUI makeover is complete and integrated with the existing backend model. Selection is distinct from Kitty focus, native tree collapse/expand behavior is preserved, connector topology is continuous, tab groups use non-structural banding, and the inspector separates status, location, process, and history information.

## Verification

The latest UI implementation passed:

- Ruff formatting and lint;
- `ty` type checking;
- import-linter checks;
- the full automated test suite (146 tests).

Headless Textual tests cover interaction and refresh races. Real-Kitty/macOS rehearsal remains the appropriate check for behavior that depends on Kitty remote control or native-window effects.

## Known limitations

These are intentional current-scope boundaries, not incomplete work:

- catherd does not create shells, panes, tabs, or OS windows;
- catherd does not close processes or terminal objects;
- Atuin history is enrichment and may be unavailable independently of Kitty state.

## Next

No immediate feature work is queued. Future work should be bug fixes, compatibility maintenance, or an explicit DESIGN.md scope revision.
