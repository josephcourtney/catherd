# Plan

## Current strategy

catherd's current implementation strategy is maintenance-oriented: preserve the 0.18.x scope defined in DESIGN.md, keep the Kitty snapshot model authoritative, and make changes through the existing backend/CLI/TUI boundaries rather than expanding the product ad hoc.

## Change sequence

For functional changes within the current scope:

1. Update the canonical model/parser only when Kitty exposes new or changed state that catherd must understand.
2. Add or modify the Kitty backend operation and its object/state validation.
3. Expose the behavior through CLI or TUI without bypassing the backend boundary.
4. Preserve selection/focus separation, native tree topology, refresh invariants, and stale-result protection.
5. Add headless regression/acceptance coverage for interaction behavior.
6. Run the repository quality gates and, for Kitty/native-window behavior, perform a real-Kitty acceptance rehearsal.
7. Update README, DESIGN, STATUS, or CHANGELOG only when their respective policy-defined responsibilities are affected.

## UI maintenance

Presentation changes should remain non-structural whenever possible. In particular:

- grouping and highlighting should be rendered as styles, not synthetic tree nodes;
- native Textual collapse/hit-testing topology should be preserved;
- selection styling must not overwrite semantic foreground colors;
- command normalization is for identity/display only; exact commands remain available in metadata.

## Scope expansion

Creating or closing terminal objects, process lifecycle management, persistent workspace/session models, or replacement of Kitty's broader remote-control interface are not queued implementation stages. If one of those becomes a goal, update DESIGN.md first, then add an implementation phase here.

## Release discipline

Before release or merge to the default branch:

- no immediate work should remain hidden in TODO.md;
- STATUS.md should reflect the resulting repository state;
- README examples and UI descriptions should match current behavior;
- formatting, lint, type checking, import checks, and tests should pass;
- known real-Kitty limitations should be recorded rather than inferred from headless tests.
