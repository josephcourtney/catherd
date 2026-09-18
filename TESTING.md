# Repository Testing Guide

## Purpose

This document is the operational testing guide for catherd. The canonical full validation gate is `just check`.

## Test layers

catherd uses three complementary test layers:

1. **Pure and component tests** exercise parsing, models, CLI behavior, Atuin integration, and Kitty command construction.
2. **Headless TUI acceptance tests** run the Textual application with a stateful fake Kitty backend. These verify rendered hierarchy changes and interaction semantics without requiring a running Kitty instance.
3. **Real-Kitty acceptance** is a deliberately small manual boundary check for behavior that cannot be proven by the headless harness, such as native macOS window titles and Kitty remote-control effects.

Tests use pytest and are classified with the repository's size markers.

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

`just check` runs syntax validation, formatting checks, Ruff linting, type checking, import-boundary validation, the full pytest suite, and coverage reporting.

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

These checks passed for the 0.18.0 release on 2026-09-18.

## Test artifacts

Pytest writes structured artifacts under `.artifacts/` and coverage data to `.coverage.xml`. Generated test artifacts are not project documentation and should not be treated as durable status records.

## Policy

`TODO.md` contains only immediate unfinished work. Completed acceptance work belongs in the changelog and commit history, not in TODO. `CHANGELOG.md` records notable user-visible behavior; detailed test implementation history remains in git.
