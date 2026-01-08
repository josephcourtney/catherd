## TODO: Enrich Kitty shell/window metadata harvesting

* [ ] **Define an expanded Kitty model**

  * Update `src/catherd/kitty.py`:

    * Extend `KittyWindow` (or introduce `KittyWindowInfo`) to carry optional fields:

      * `os_window_id: str | None`
      * `tab_title: str | None`
      * `is_active_os_window: bool | None`
      * `is_active_tab: bool | None`
      * `is_active_window: bool | None`
      * `pid: int | None`
      * `cwd: str | None`
      * `foreground_cmd: str | None` (or `argv0`)
      * `tty: str | None`
      * `cols: int | None`, `rows: int | None`
      * `x: int | None`, `y: int | None` (or other geometry if available)
      * `has_bell: bool | None`, `is_urgent: bool | None` (if available)
    * Keep all new fields optional to tolerate Kitty version/key variability.

* [ ] **Implement a robust JSON extractor that tolerates key drift**

  * Update `get_kitty_windows()` in `src/catherd/kitty.py`:

    * Capture `os_window_id` from the top-level loop if present.
    * Capture `tab_title` and any active/focus indicators at the tab/window levels.
    * Extract per-window fields defensively (`dict.get`, nested `get`, type guards).
    * Normalize types deterministically:

      * Always stringify IDs (`os_window_id`, `tab`, `id`).
      * `pid` as `int | None` only if parseable.
      * `cwd`/`tty` as strings only if non-empty.
    * Avoid introducing non-deterministic ordering; preserve traversal order.

* [ ] **Add a stable “foreground fallback” when Atuin history is missing**

  * Update `src/catherd/cli.py`:

    * Define a display policy:

      * Prefer Atuin last command when available and not a sentinel.
      * Else fall back to Kitty `foreground_cmd` (and optionally `pid`).
      * Else fall back to an explicit sentinel (e.g., `"(no command)"`).
    * Ensure the sentinel set remains centralized and tested.

* [ ] **Enrich `show` human output (tab grouping + active markers)**

  * Update `src/catherd/cli.py` `show`:

    * Group rows by `os_window_id` and `tab` (if present).
    * Add active markers (e.g., `*` or `ACTIVE`) for active OS window/tab/window.
    * Add optional columns (keep width reasonable):

      * `CWD` (possibly truncated)
      * `PID`
      * `FG` (foreground cmd)
      * `TTY` (optional)
      * `SIZE` (`cols`×`rows`)
    * Keep legacy columns/ordering reasonable; avoid breaking tests by making formatting too strict.

* [ ] **Enrich `show --json` output with the new fields**

  * Update `src/catherd/cli.py` `show` JSON payload:

    * Include new keys with `null` when unknown:

      * `os_window_id`, `tab_title`, `active` flags, `pid`, `cwd`, `foreground_cmd`, `tty`, `cols`, `rows`, `x`, `y`, `has_bell`, `is_urgent`
    * Keep existing keys unchanged (`window_id`, `tab`, `title`, `last_command`).

* [ ] **Add a dedicated command for full-detail introspection**

  * Add `catherd inspect` (or `catherd ls --json --verbose` equivalent) in `src/catherd/cli.py`:

    * Emits the richest possible per-window dataset.
    * Defaults to JSON to avoid fragile table formatting.
    * Optional `--pretty` for indented JSON.

* [ ] **Sync health / staleness correlation (Kitty ↔ session file)**

  * Update `src/catherd/cli.py` diagnostics helpers:

    * Extend `_collect_kitty_session_diagnostics()` to optionally report:

      * “duplicate ATUIN_SESSION across multiple windows”
      * “session file refers to a different window id than expected”
    * If you include file mtimes, gate behind `--verbose` (and test with time freezing).

* [ ] **Update `doctor` to surface the enriched Kitty metadata**

  * Update `src/catherd/cli.py` `doctor` and `print_kitty_session_diagnostics()`:

    * When reporting each window, include key metadata if available (pid/cwd/fg/tty).
    * Add actionable hints tied to missing fields:

      * e.g., “cwd unavailable; enable Kitty shell integration if desired” (keep wording factual).
