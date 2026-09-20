# Repository Testing Guide

## Purpose

This document is the operational testing guide for catherd. The canonical full validation gate is `just check`.

## Test layers

catherd uses three complementary test layers:

1. **Pure and component tests** exercise parsing, models, CLI behavior, Atuin integration, shell managed-block migration/safety, and Kitty command construction.
2. **Headless TUI acceptance tests** run the Textual application with a stateful fake Kitty backend. These verify rendered hierarchy changes and interaction semantics without requiring a running Kitty instance.
3. **Real-Kitty acceptance** is a deliberately small manual boundary check for behavior that cannot be proven by the headless harness, such as native macOS window titles and Kitty remote-control effects.

Tests use pytest and are classified with the repository's size markers. Size is based on resource behavior, not merely runtime:

- `small`: hermetic; no real filesystem, database, subprocess, network, or sleep calls.
- `medium`: may use local filesystem/SQLite/subprocesses or framework event loops that sleep/yield internally.
- Textual `App.run_test()` cases are therefore `medium`; pure TUI helper/rendering functions remain `small`.
- Tests using `tmp_path` for real file behavior are `medium`; use pyfakefs or mocks only when the test is genuinely intended to remain a hermetic unit test.
- Real advertised-shell validation is intentionally outside pytest because it launches external shell processes. `just test-shell-integration` syntax-checks and executes the generated bash, zsh, fish, and csh snippets when those executables are available.

## Standard commands

Run the TUI acceptance suite during TUI development:

```sh
just test-tui
```

This suite covers keyboard and mouse selection, explicit Kitty focus, rename, move/detach, pane/tab reordering, tab and OS-window merging, details updates, selection preservation, polling races, and stale asynchronous Atuin activity results.

Run the complete repository validation gate before merging:

```sh
just check
```

Before a release, also validate the distributable artifacts and installed entry points:

```sh
just release-check
```

The final 1.0.0 rehearsal also included the repository's installation validation path in the user's release-ready working tree. The tagged release tree should contain the same validation path used for that rehearsal.


`just check` runs syntax validation, formatting checks, Ruff linting, type checking, import-boundary validation, the standalone real-shell integration gate, the full pytest suite, and coverage reporting. Pytest covers optional-Atuin lifecycle, legacy-marker migration, and rc-file preservation/failure recovery; the separate shell gate covers parser and execution behavior against installed shell executables.

For rapid iteration, the general test runner remains available:

```sh
just test --fast
just test --failing
just test --debug
```

## TUI boundary acceptance

After the headless suite passes, real Kitty testing should be limited to the external boundary:

- pane and tab `J` / `K` visually match the hierarchy reported back by Kitty;
- mouse selection inside catherd does not trigger remote focus, while `Enter` / `f` does;
- tab merge moves every source pane and removes the emptied source tab;
- OS-window merge moves every source tab and removes the emptied source OS window;
- OS-window rename changes the native Kitty/macOS window title.

These real-Kitty boundary checks were last explicitly recorded for the 0.18.0 release on 2026-09-18; they remain the manual boundary checklist for 1.0.x maintenance.

## Test artifacts

Pytest writes structured artifacts under `.artifacts/` and coverage data to `.coverage.xml`. Generated test artifacts are not project documentation and should not be treated as durable status records.

## Policy

`TODO.md` contains only immediate unfinished work. Completed acceptance work belongs in the changelog and commit history, not in TODO. `CHANGELOG.md` records notable user-visible behavior; detailed test implementation history remains in git.
