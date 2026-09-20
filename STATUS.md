# Status

This file records the current short-horizon project state for continuity and handoff.

## Current state

catherd is at version 1.0.0 for the scope defined in DESIGN.md. The Kitty inspector/organizer is functionally complete for that scope: inspection, filtering, explicit focus, rename, move, reorder, and merge operate from Kitty state, while Atuin remains optional completed-command history enrichment.

The project is licensed under the GNU Lesser General Public License v3.0 only (`LGPL-3.0-only`), with LICENSE.md and package metadata aligned.

The final local quality, release, and installation rehearsals were reported passing before the version/documentation bump. Subsequent Phase 2 shell-integration fixes corrected fish variable scope, made managed-block enable/disable newline-preserving, and moved real-shell subprocess checks into a dedicated `just check` gate because pytest-test-categories misattributed those subprocesses to randomized small tests.

The Phase 2 shell-integration tree passed a fresh `just check`, including the standalone real-shell integration gate and the full pytest suite.

The previously planned public-CLI hardening phase is now implemented on top of that verified baseline. `show` is hierarchy-oriented and terminal-responsive, human display text is normalized without changing JSON values, `--verbose` exposes lower-value diagnostics, `--version` reports installed package metadata, and unusable Kitty state now produces nonzero exits for `show`, `inspect`, and `doctor`. Main `doctor` output separates core Kitty health from optional Atuin enrichment.

## Known limitations

These are intentional scope boundaries rather than incomplete 1.0 work:

- catherd does not create shells, panes, tabs, or OS windows;
- catherd does not close processes or terminal objects;
- Atuin history is optional and may be unavailable independently of Kitty state;
- shell parser/execution coverage depends on the corresponding shell executable being present;
- tagging and publication are separate from this version bump.

## Next

Run `just check` on the current CLI-hardening tree and fix any resulting lint/type/test failures. Once that gate passes, record the new verified baseline before further maintenance or release work.
