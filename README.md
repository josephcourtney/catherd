# catherd

A command-line and terminal interface for inspecting and organizing a running Kitty instance. Kitty provides all core hierarchy, activity, and organization behavior; Atuin can optionally enrich panes with their most recently completed command.

## Release status

catherd 1.0.0 is the stable public-release boundary for the current Kitty inspector/organizer scope. Package metadata and repository licensing use the GNU Lesser General Public License v3.0 only (`LGPL-3.0-only`).


## Interactive organizer

Run:

```sh
catherd tui
```

The TUI presents Kitty as a collapsible OS-window → tab → pane hierarchy. Native tree guides remain continuous, alternating tab subtrees provide non-structural grouping, and command-like titles are normalized for scanning. The selected row belongs to catherd and is shown with a neutral background plus a left-edge cursor marker; it does not change Kitty focus. The actually focused pane is marked `● focused`, while pane activity is reported independently as `▶ running` or `○ at prompt`.

The right-hand inspector is a compact summary of the selected object. Long paths, commands, history values, and identifiers may be abbreviated there for scanning; press `i` to open a near-full-screen, scrollable inspector containing the complete display-normalized values in block form. Mouse clicks change only the catherd selection; focusing the corresponding Kitty object is always explicit.

| Key | Action |
| --- | --- |
| `j` / `k` | move through the tree |
| `h` / `l`, `←` / `→` | collapse / expand |
| `Enter` / `f` | focus selected OS window, tab, or pane in Kitty |
| `i` | open full details for the selected object; `i`, `Esc`, or `q` closes it |
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

Running `catherd` without a subcommand is equivalent to `catherd show`. Use `catherd --version` to report the installed package version.

| Command | Purpose |
| --- | --- |
| `catherd tui` | interactive hierarchy browser and organizer |
| `catherd show` | show a responsive OS-window → tab → pane hierarchy with current/recent commands |
| `catherd show --verbose` | add pane IDs and process/layout diagnostics to the human view |
| `catherd show --json` | emit the stable machine-readable pane representation |
| `catherd inspect` | emit the richest available Kitty dataset as JSON, including optional Atuin fields |
| `catherd doctor` | diagnose the core Kitty boundary separately from optional integrations |
| `catherd atuin doctor` | diagnose only the optional Atuin integration |
| `catherd atuin enable` | safely enable Kitty-pane-to-Atuin-session association |
| `catherd atuin disable` | remove that association while preserving an rc-file backup |

The default human `show` view adapts to terminal width. It normalizes multiline commands for display, places the working directory beside the command when both fit, and otherwise wraps complete command and path values across indented lines rather than truncating them. Low-value process metadata remains behind `--verbose`. JSON and `inspect` retain exact underlying values rather than display-normalized text.

Core Kitty failures are command failures: `show`, `inspect`, and `doctor` return a nonzero exit status when a usable Kitty hierarchy cannot be obtained. Missing Atuin state remains optional and does not make those core commands unhealthy.

No Atuin setup is required to use catherd. To additionally enable per-pane completed-command history from Atuin:

```sh
catherd atuin doctor
catherd atuin enable
```

The integration supports bash, zsh, fish, and csh with shell-native snippets. Before writing a startup file, catherd asks the corresponding shell to syntax-check the generated snippet. Existing startup files are backed up, symlinked rc files keep their symlink identity, writes are atomic, repeated enable/disable operations are safe, and the old pre-0.19 Atuin/Kitty marker is migrated automatically. The former top-level `install` and `uninstall` commands remain hidden compatibility aliases for existing users.

Restart or re-source the affected shell after enabling the integration.

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

Validate release packaging and installed-artifact behavior with:

```sh
just release-check
```


The headless suite is complemented by real-Kitty/macOS acceptance rehearsal for remote-control and native-window behavior.

## License

catherd is licensed under the GNU Lesser General Public License v3.0 only (`LGPL-3.0-only`). See [LICENSE.md](LICENSE.md).
