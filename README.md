# catherd

A command-line and terminal interface for inspecting and organizing a running Kitty instance, with Atuin history enrichment.

## Interactive organizer

Run:

```sh
catherd tui
```

The TUI displays Kitty's hierarchy as OS windows → tabs → panes. Pane order follows Kitty's visual layout order. A details panel shows metadata for the highlighted object. For panes it distinguishes Kitty's currently running command from the most recently completed Atuin command. Mouse clicks only change the selection inside catherd; focusing the corresponding Kitty object is an explicit action.

| Key | Action |
| --- | --- |
| `j` / `k` | move through the tree |
| `h` / `l` | collapse / expand |
| `Enter` / `f` | focus selected OS window, tab, or pane in Kitty |
| `r` | rename selected object |
| `m` | move a pane or tab |
| `J` / `K` | reorder a pane or tab among siblings |
| `M` | merge an OS window into another OS window, or a tab into another tab |
| `Ctrl-R` | refresh |
| `q` | quit |

The TUI intentionally does not close processes or create new shells in this version.

## Existing commands

`catherd show` lists open Kitty panes and their most recent Atuin command when available. `catherd inspect` emits the richer combined dataset as JSON, and `catherd doctor` diagnoses Kitty/Atuin integration.
