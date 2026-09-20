# Status

This file records the current short-horizon project state for continuity and handoff.

## Current state

catherd is in 0.19.0 public-release hardening. The core Kitty organizer remains functionally complete for the scope defined in DESIGN.md: inspection, filtering, explicit focus, rename, move, reorder, and merge all operate from Kitty state.

Public-release Phases 1 and 2 are implemented. Kitty is the required core boundary; Atuin is optional completed-command history enrichment managed through the explicit `catherd atuin enable|disable|doctor` namespace. The former top-level `install` / `uninstall` commands remain hidden compatibility aliases.

The optional shell integration now uses shell-native bash, zsh, fish, and csh snippets. Generated snippets are syntax-validated before writes; existing rc files are backed up; replacement is atomic; legacy markers are migrated; malformed or duplicate managed blocks are rejected rather than guessed through.

## Verification

Phase 1 passed `just check`. Phase 2 adds regression coverage for:

- enable/disable idempotence, dry-run, backups, legacy-marker migration, malformed-block rejection, and write-failure recovery;
- startup-file paths containing spaces and creation of a previously absent rc file;
- real parser and execution checks for bash, zsh, fish, and csh when those executables are installed;
- missing/unreadable Atuin state degrading to optional enrichment absence rather than a core failure;
- hidden compatibility aliases and the explicit Atuin CLI namespace.

A local `just check` run is still required to close Phase 2 verification because this environment cannot execute the repository checkout.

## Known limitations

These are intentional current-scope boundaries, not incomplete core work:

- catherd does not create shells, panes, tabs, or OS windows;
- catherd does not close processes or terminal objects;
- Atuin history is optional enrichment and may be unavailable independently of Kitty state;
- locally unavailable shell executables cause their real-shell tests to skip until the later CI matrix supplies them.

## Next

Run the Phase 2 local quality gate. Once it passes, proceed to PLAN.md Phase 3: harden the public CLI, including responsive `show`, diagnostic structure, and exit semantics.
