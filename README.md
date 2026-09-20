# catherd

A command-line and terminal interface for inspecting and organizing a running Kitty instance. Kitty provides all core hierarchy, activity, and organization behavior; Atuin can optionally enrich panes with their most recently completed command.

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

catherd organizes objects that already exist in Kitty. The current scope intentionally does **not** create shells/windows/tabs or close processes. It is an inspector and organizer rather than a replacement for Kitty's complete remote-control interface.

### Core and optional enrichment

Kitty is the only external system required for core catherd behavior. The hierarchy, focus state, current command/process metadata, filtering, inspection, and all organization operations come from Kitty and remain available when Atuin is not installed or configured.

Atuin is optional history enrichment. When a Kitty pane has been associated with an Atuin session, catherd can show the most recently completed command after the shell has returned to a prompt. Without that association, catherd continues to use Kitty's current-command and process information; only history-specific information is absent.

Kitty's own shell integration is separate from catherd's optional Kitty-pane-to-Atuin-session association.

## CLI

Running `catherd` without a subcommand is equivalent to `catherd show`.

| Command | Purpose |
| --- | --- |
| `catherd tui` | interactive hierarchy browser and organizer |
| `catherd show` | list open panes with current/recent command information |
| `catherd inspect` | emit the richest available Kitty dataset as JSON, including optional Atuin fields |
| `catherd doctor` | diagnose Kitty and optional enrichment state |
| `catherd install` | currently install the optional Kitty-pane-to-Atuin-session association snippet |
| `catherd uninstall` | currently remove that optional Atuin association snippet |

No Atuin setup is required to use catherd. To additionally enable per-pane completed-command history from Atuin:

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
