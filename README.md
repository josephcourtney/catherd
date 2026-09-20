# catherd

A command-line and terminal interface for inspecting and organizing a running Kitty instance, with optional Atuin history enrichment.

## Interactive organizer

Run:

```sh
catherd tui
```

The TUI presents Kitty as a collapsible OS-window → tab → pane hierarchy. Native tree guides remain continuous, alternating tab subtrees provide non-structural grouping, and command-like titles are normalized for scanning. The selected row belongs to catherd and is shown with a neutral background plus a left-edge cursor marker; it does not change Kitty focus. The actually focused pane is marked `● focused`, while pane activity is reported independently as `▶ running` or `○ at prompt`.

The inspector shows richer information for the selected object, including location, process metadata, layout position and neighbors, and Atuin-backed command history when available. Mouse clicks change only the catherd selection; focusing the corresponding Kitty object is always explicit.

| Key | Action |
| --- | --- |
| `j` / `k` | move through the tree |
| `h` / `l`, `←` / `→` | collapse / expand |
| `Enter` / `f` | focus selected OS window, tab, or pane in Kitty |
| `/` | filter by title, ID, path, or command; submit empty or press `Esc` to clear |
| `a` | clear filtering and jump to the focused Kitty pane |
| `r` | rename selected object |
| `m` | move a pane or tab |
| `J` / `K` | reorder a pane or tab among siblings |
| `M` | merge an OS window into another OS window, or a tab into another tab |
| `Ctrl-R` | refresh |
| `?` | help |
| `q` | quit |

The TUI follows macOS light/dark appearance at launch, falling back to terminal color hints on other platforms. Set `CATHERD_THEME=ansi-light` or `CATHERD_THEME=ansi-dark` to override detection. The older `textual-light` and `textual-dark` names remain accepted aliases.

### Scope

catherd organizes objects that already exist in Kitty. The current 0.18.x scope intentionally does **not** create shells/windows/tabs or close processes. It is an inspector and organizer rather than a replacement for Kitty's complete remote-control interface.

## CLI

Running `catherd` without a subcommand is equivalent to `catherd show`.

| Command | Purpose |
| --- | --- |
| `catherd tui` | interactive hierarchy browser and organizer |
| `catherd show` | list open panes with current/recent command information |
| `catherd inspect` | emit the richer Kitty + Atuin dataset as JSON |
| `catherd doctor` | diagnose Kitty/Atuin integration |
| `catherd install` | install the shell snippet that associates Kitty pane IDs with Atuin sessions |
| `catherd uninstall` | remove that shell snippet |

Atuin enrichment is optional for basic Kitty inspection. To enable per-pane history association:

```sh
catherd install
catherd doctor
```

Restart/re-source the affected shells after installation.

## Design and project state

- [DESIGN.md](DESIGN.md) defines the durable scope, architecture, and invariants.
- [PLAN.md](PLAN.md) describes the implementation and maintenance strategy.
- [STATUS.md](STATUS.md) records the current project state.
- [TODO.md](TODO.md) contains immediate work only.
- [POLICY.md](POLICY.md) defines the documentation and history policy.

## Development

The interaction layer is exercised headlessly with Textual's testing harness and a stateful fake Kitty backend. Tests cover keyboard and mouse selection, explicit focus, collapse/expand, filtering, rename, move/detach, pane/tab reordering, tab and OS-window merging, details updates, selection/expansion preservation, polling races, and stale asynchronous activity results.

Run the TUI tests with:

```sh
just test-tui
```

Run the repository quality gates with:

```sh
just check
```

The headless suite is complemented by real-Kitty/macOS acceptance rehearsal for remote-control and native-window behavior.
