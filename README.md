# catherd

A command-line and terminal interface for inspecting and organizing a running Kitty instance, with Atuin history enrichment.

## Interactive organizer

Run:

```sh
catherd tui
```

The TUI displays Kitty's hierarchy as OS windows → tabs → panes. The tree is intentionally compact: it shows identity plus one meaningful activity/layout hint, while the fixed-width inspector separates richer metadata with labeled section rules. A persistent `●` marks the object currently active in Kitty; the highlighted row is the selection inside catherd. Generic shell-wrapper process hints are suppressed. Mouse clicks only change the catherd selection, while focusing the corresponding Kitty object is explicit.

| Key | Action |
| --- | --- |
| `j` / `k` | move through the tree |
| `h` / `l` | collapse / expand |
| `Enter` / `f` | focus selected OS window, tab, or pane in Kitty |
| `/` | filter the tree by title, ID, path, or command; submit empty or press `Esc` to clear |
| `a` | clear filtering and jump to the active Kitty pane |
| `r` | rename selected object |
| `m` | move a pane or tab |
| `J` / `K` | reorder a pane or tab among siblings |
| `M` | merge an OS window into another OS window, or a tab into another tab |
| `Ctrl-R` | refresh |
| `q` | quit |

The TUI follows macOS light/dark appearance when launched, falling back to terminal color hints on other platforms. Set `CATHERD_THEME=ansi-light` or `CATHERD_THEME=ansi-dark` to override detection. The older `textual-light` / `textual-dark` names are accepted as aliases but map to the terminal-native ANSI themes. The 0.18.0 TUI intentionally does not close processes or create new shells.

### TUI testing

The interaction layer is exercised headlessly with Textual's testing harness and a stateful fake Kitty backend:

```sh
just test-tui
```

These tests cover keyboard and mouse selection, explicit focus, rename, move/detach, pane/tab reordering, tab and OS-window merging, details updates, selection preservation, polling races, and stale asynchronous activity results. The headless suite is complemented by a small real-Kitty/macOS acceptance rehearsal for remote-control and native-window behavior.

## Existing commands

`catherd show` lists open Kitty panes and their most recent Atuin command when available. `catherd inspect` emits the richer combined dataset as JSON, and `catherd doctor` diagnoses Kitty/Atuin integration.
