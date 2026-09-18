## [0.17.0] - 2026-09-18

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
