# Design

## Purpose

catherd is a local command-line and terminal interface for inspecting and organizing an already-running Kitty instance. Kitty is the authoritative runtime dependency for core behavior: its hierarchy, process metadata, focus state, and remote-control operations define what catherd can inspect and organize. Optional integrations may enrich that state but must not be required for core functionality.

Atuin is one such optional integration. When available and associated with a pane, its session history can supply the most recently completed command; when absent, catherd continues to operate from Kitty state alone.

The primary interactive model is:

```text
OS window
└─ tab
   └─ pane
```

Kitty calls the leaf object a window; catherd uses **pane** in user-facing terminology to avoid confusing it with an operating-system window.

## Goals

- Present one canonical snapshot of Kitty's OS-window/tab/pane hierarchy.
- Make object identity, Kitty focus, process activity, and catherd selection distinct concepts.
- Support deliberate organization of existing Kitty objects: focus, rename, move, reorder, and merge.
- Keep all inspection and organization behavior functional from Kitty state alone.
- Enrich panes with Atuin session/history information when available, without making Atuin a runtime requirement or changing the meaning of core Kitty state.
- Remain useful during live polling: preserve the user's selection and expansion state and reject stale asynchronous detail results.
- Keep the interface compact enough for terminal use while exposing richer metadata in an inspector.
- Keep Kitty interaction behind a narrow backend boundary that can be replaced by a stateful fake in tests.

## Non-goals

The current 0.18.x design does not attempt to:

- create shells, panes, tabs, or OS windows;
- close processes or terminal objects;
- replace Kitty's complete remote-control interface;
- persist a second authoritative model of Kitty state;
- make Atuin, catherd's Atuin session files, or any history provider mandatory for hierarchy inspection, organization, or current Kitty activity display.

These are scope changes, not missing features. Adding them requires an explicit design revision.

## Canonical state model

`catherd.model` owns the immutable in-memory representation:

- `KittyState` contains `OsWindow` objects;
- each `OsWindow` contains `Tab` objects;
- each `Tab` contains `Pane` objects;
- `PaneLocation` couples a pane to its parent tab and OS window.

A snapshot is authoritative only for the instant at which Kitty produced it. Mutations are directed to Kitty and followed by a new snapshot rather than editing the model in place.

The parser normalizes Kitty's current `ls` schema, filters transient Kitty UI overlays, and records available focus, process, prompt, size, layout-order, group, and neighbor metadata.

## Dependency model

Core catherd depends on Kitty, not Atuin. A valid Kitty snapshot is sufficient for hierarchy inspection, filtering, focus, rename, move, reorder, merge, and the TUI's process/current-command presentation. Optional enrichment must be additive: its absence may remove history-only fields, but it must not invalidate a Kitty snapshot, disable a core operation, or change the success/failure semantics of a Kitty mutation.

Kitty's own shell integration and catherd's Atuin association snippet are separate mechanisms. Kitty shell integration can enrich Kitty's own reported process/prompt metadata. The catherd snippet exists only to associate a Kitty pane ID with an Atuin session ID.

## External boundaries

### Kitty

`catherd.kitty` is the remote-control boundary. It is responsible for:

- discovering/invoking Kitty;
- parsing `kitty @ ls` output into `KittyState`;
- validating object references;
- performing supported focus and organization operations;
- translating invocation/output/state failures into catherd-specific exceptions.

UI code must not construct raw Kitty remote-control commands directly.

### Atuin

`catherd.atuin` reads Atuin's local history database. `catherd.activity` associates a Kitty pane ID with an Atuin session ID via catherd's session files, then retrieves the most recent command for that session.

Atuin lookup is enrichment only. Missing Atuin, missing catherd session files, missing history, or lookup failure must not invalidate the Kitty hierarchy or block any core inspection or organization operation. When no Atuin history is available, catherd continues to use Kitty-provided current-command and process metadata; a history-only "last completed command" may simply be absent.

### Optional Atuin shell integration

`catherd.shell` provides the optional shell startup snippet used to associate `KITTY_WINDOW_ID` with `ATUIN_SESSION`. This snippet is not required to run catherd and is not Kitty shell integration. The current CLI install/uninstall operations manage only this optional Atuin association; Phase 2 of the public-release plan will move those operations under explicitly Atuin-scoped terminology.

## Interfaces

### CLI

`catherd.cli` provides:

- `show`: human-readable current hierarchy/activity summary;
- `inspect`: richer JSON data;
- `doctor`: integration diagnostics;
- `install` / `uninstall`: shell integration management;
- `tui`: the interactive organizer.

The default invocation remains `show`.

### TUI

`catherd.tui` is a live view over repeated Kitty snapshots.

The tree uses native Textual hierarchy nodes; synthetic spacer nodes must not be inserted because they alter connector topology, hit testing, and collapse semantics.

The tree presentation follows these semantic rules:

- **catherd selection** is an interaction state represented by a neutral row background and left cursor marker;
- **Kitty focus** is runtime state and is explicitly marked only on the focused pane;
- **activity** is independent of focus and is shown as running or at-prompt status;
- IDs, guides, and secondary metadata are visually subordinate to object identity;
- tab-subtree banding is presentational only and must not change the logical tree.

The inspector contains richer information for the currently selected object. Command-like titles may be normalized for identity/display, while exact process commands remain available in process metadata.

Mouse selection never focuses Kitty implicitly. Focus requires an explicit action.

## Supported mutations

Within current scope, the backend/TUI supports:

- focus an OS window, tab, or pane;
- rename an OS window, tab, or pane where Kitty supports the operation;
- move a pane between tabs or to a new tab/OS window;
- move a tab between OS windows or to a new OS window;
- reorder panes or tabs among siblings;
- merge tabs;
- merge OS windows.

An operation must target stable Kitty IDs from a snapshot. If the referenced object disappears before execution, the operation fails rather than guessing a replacement.

## Refresh and concurrency invariants

Automatic refresh is observational except when reflecting a completed explicit mutation.

The TUI must preserve:

- logical selection when the selected object still exists;
- explicit user collapse/expansion state where possible;
- selected ancestors when collapsing would otherwise hide the selected descendant;
- the distinction between catherd selection and Kitty focus.

Asynchronous Atuin/activity lookup is selection-sensitive. A result for an object that is no longer selected must not overwrite the current inspector.

During an explicit mutation, polling must not race the mutation and restore stale state.

## Error handling

External failures are surfaced at the boundary that can explain them:

- Kitty invocation, output, object-resolution, and state errors use dedicated exceptions;
- CLI commands convert user-facing failures into Click errors/messages;
- TUI operations report failures in the status area and refresh from Kitty rather than maintaining speculative state;
- Atuin enrichment degrades to absent/error history rather than invalidating Kitty data or changing core-operation availability.

## Testing strategy

The canonical logic is covered by unit/component tests. The Textual interface is exercised headlessly against a stateful fake Kitty backend so interaction semantics can be tested without controlling the developer's real terminal.

Acceptance coverage includes selection versus focus, mouse/keyboard navigation, collapse/expand, filtering, rename/move/reorder/merge operations, refresh preservation, mutation races, stale asynchronous activity results, and core CLI/TUI operation with no Atuin session files or history database present.

Real-Kitty/macOS rehearsal complements the headless suite for behavior that depends on Kitty remote control or native-window effects.
