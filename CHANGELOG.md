## [Unreleased]

### Added
- add explicit `catherd atuin enable`, `catherd atuin disable`, and `catherd atuin doctor` commands for optional completed-command history enrichment.

### Changed
- keep the former top-level `install` and `uninstall` commands as hidden deprecation aliases while migrating legacy shell-integration markers automatically.
- harden Atuin shell integration with shell-native bash/zsh/fish/csh snippets, syntax validation before writes, atomic rc-file replacement, backups, symlink preservation, idempotent lifecycle operations, and safe rejection of malformed managed blocks.
- define Kitty as the complete core runtime boundary and Atuin as optional completed-command history enrichment; update CLI/documentation wording and add regressions proving core CLI/TUI behavior without Atuin state.
- distinguish catherd cursor selection from Kitty focus with a full-row selection marker and explicit focused/running/at-prompt status grammar; make inspector labels, paths, identifiers, footer actions, and filtered counts easier to scan.
- simplify TUI tree rows to identity plus a concise activity/layout hint and distinguish Kitty-active objects from catherd selection.
- reorganize the details pane into a fixed-width grouped inspector with breadcrumbs and exceptional-state emphasis.
- replace the colorful binding footer with a restrained command strip and add tree filtering plus jump-to-active navigation.
- replace the triangle-like active indicator with a circular marker, follow macOS light/dark appearance with Textual's terminal-native ANSI themes, and use theme-aware borders.
- strengthen visual grouping with section rules and hierarchy weight while suppressing repetitive shell-wrapper hints.
- preserve Textual's native guide/collapse topology while separating tab groups with stronger non-structural zebra bands; normalize command-like identities, reduce repeated focus labels, and rebalance hierarchy/status column widths.

## [0.18.0] - 2026-09-18

### Added
- add a Textual TUI for navigating, focusing, renaming, moving, reordering, and merging Kitty OS windows, tabs, and panes.
- add automatic state refresh that preserves tree selection and expansion state.
- add a selected-object details panel with Kitty metadata and asynchronous Atuin session/command enrichment for panes.
- add a stateful headless Textual acceptance harness covering TUI structural operations, mouse/keyboard focus semantics, and asynchronous refresh races.

### Fixed
- update Kitty state parsing for the current `ls` schema, including foreground processes, terminal size, command state, and attention state.
- filter Kitty's transient UI overlays, such as the built-in tab-renaming prompt, from catherd's pane hierarchy.
- keep renamed objects visibly renamed in the TUI, explicitly target tab/pane reorder actions, and allow merge from any node in the source OS window.
- distinguish the currently running Kitty shell-integration command from the most recently completed Atuin command.
- handle uppercase terminal key events for `J`, `K`, and `M`, preserve logical selection across structural refreshes, and show pane position/neighbors from Kitty's layout metadata.
- make pane tree order follow Kitty's visual layout order, separate mouse selection from explicit Kitty focus, and support tab-to-tab merges while rejecting merge on individual panes.
- close Atuin SQLite connections explicitly instead of relying on the connection context manager's transaction-only cleanup.
- make explicit `Enter`/`f` focus take precedence over Textual Tree selection while mouse interaction remains selection-only.

## [0.16.0] - 2026-09-18

### Added
- add supported Kitty operations for focusing, renaming, moving, detaching, reordering, and merging OS windows, tabs, and panes.
- add hierarchy lookup helpers used by interactive frontends.

### Fixed
- remove the unused `pytest-freezegun` plugin dependency that emitted `distutils` deprecation warnings under current pytest.

## [0.15.1] - 2026-09-18

### Changed
- refactor Kitty discovery around a canonical OS-window/tab/pane hierarchy and isolated remote-control client boundary without changing CLI behavior.

### Fixed
- fix refactor lint failures by narrowing exception boundaries and make Kitty integer metadata normalization type-safe.

## [0.15.0] - 2026-01-07

### Removed
- remove the legacy `catherd.core` compatibility module and its associated tests.
- remove packaged shell snippet files and file-based snippet loading, keeping embedded snippets as the single source of truth.

## [0.14.2] - 2026-01-07

### Fixed
- fix `core.py` by removing duplicate/broken definitions and delegating consistently to the authoritative modules.
- fix embedded shell snippet text to use literal shell operators (`&&`, `>`) rather than HTML-escaped entities.

## [0.14.1] - 2026-01-07

### Fixed
- fix shell snippet loading to work reliably when installed by embedding snippet content and avoiding fragile filesystem-relative lookups.
- fix `doctor` diagnostics classification to match actual Atuin sentinel values and report missing history/command/db errors correctly.
- fix `install --dry-run` to avoid creating or opening rc files and to perform no filesystem writes.
- fix `show` to degrade gracefully when sync env vars are missing instead of hard-failing.
- fix `uninstall` to use UTF-8 encoding consistently.
- fix legacy `core.py` duplication by delegating to the authoritative `kitty`/`atuin` modules.

## [0.14.0] - 2026-01-07

### Added
- add a default `show` invocation, JSON output switch, and Atuin/Kitty sync preflight gating to the CLI along with doctor diagnostics and shell snippet helpers.
- add install/uninstall dry-run handling plus backups and extend the CLI test suite to exercise JSON output, install flows, and diagnostics so the merged functionality stays covered.
