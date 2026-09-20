# Status

This file records the current short-horizon project state for continuity and handoff.

## Current state

catherd is at version 1.0.0 for the scope defined in DESIGN.md. The Kitty inspector/organizer is functionally complete for that scope: inspection, filtering, explicit focus, rename, move, reorder, and merge operate from Kitty state, while Atuin remains optional completed-command history enrichment.

The project is licensed under the GNU Lesser General Public License v3.0 only (`LGPL-3.0-only`), with LICENSE.md and package metadata aligned.

The final local quality, release, and installation rehearsals were reported passing before this version/documentation bump. No code or runtime behavior changes are part of the bump itself.

## Known limitations

These are intentional scope boundaries rather than incomplete 1.0 work:

- catherd does not create shells, panes, tabs, or OS windows;
- catherd does not close processes or terminal objects;
- Atuin history is optional and may be unavailable independently of Kitty state;
- shell parser/execution coverage depends on the corresponding shell executable being present;
- tagging and publication are separate from this version bump.

## Next

Ensure the eventual `v1.0.0` tag points at the exact release tree that passed the final rehearsal, then publish from that tagged state. After release, restrict 1.0.x work to compatible defect and maintenance fixes unless DESIGN.md explicitly changes the product boundary.
