# Plan

## Current strategy

catherd 1.0.0 is the stable baseline for the scope defined in DESIGN.md. The project is now in maintenance mode rather than feature-completion mode: preserve the Kitty inspector/organizer contract, keep optional integrations isolated, fix defects conservatively, and expand scope only through an explicit design change.

Kitty remains the authoritative source of hierarchy and current terminal state. Atuin remains optional completed-command history enrichment and must never become a prerequisite for core inspection or organization.

## Maintenance priorities

1. Preserve the public CLI/TUI behavior and invariants documented in DESIGN.md.
2. Treat regressions in Kitty parsing, focus/selection separation, hierarchy mutation, refresh behavior, and shell-integration safety as maintenance defects.
3. Keep optional Atuin failures isolated from core Kitty behavior.
4. Maintain compatibility with the declared Python and Textual ranges unless a deliberate compatibility change is documented.
5. Keep packaging metadata, README behavior descriptions, STATUS.md, and CHANGELOG.md synchronized with each release.
6. Prefer compatible fixes after 1.0.0; require a DESIGN.md update before deliberately expanding the product boundary.

## Ongoing change sequence

For functional changes within the current scope:

1. Update the canonical model/parser only when Kitty exposes new or changed state that catherd must understand.
2. Add or modify the Kitty backend operation and its object/state validation.
3. Expose behavior through CLI or TUI without bypassing the backend boundary.
4. Preserve selection/focus separation, native tree topology, refresh invariants, and stale-result protection.
5. Add headless regression/acceptance coverage for interaction behavior.
6. Run the repository quality gates and, for Kitty/native-window behavior, perform a real-Kitty acceptance rehearsal.
7. Update README, DESIGN, STATUS, TODO, or CHANGELOG only when their policy-defined responsibilities are affected.

## UI maintenance

Presentation changes should remain non-structural whenever possible:

- grouping and highlighting should be rendered as styles, not synthetic tree nodes;
- native Textual collapse and hit-testing topology should be preserved;
- selection styling must not overwrite semantic foreground colors;
- command normalization is for identity/display only; exact commands remain available in metadata;
- responsive behavior should degrade secondary information before structural hierarchy or primary identity.

## Scope expansion

Creating or closing terminal objects, process lifecycle management, persistent workspace/session models, or replacement of Kitty's broader remote-control interface are not part of the 1.0 contract. If one of those becomes a goal, update DESIGN.md first and add an explicit implementation plan before changing behavior.

## Release discipline

Before a release or merge to the default branch:

- no immediate work should remain hidden in TODO.md;
- STATUS.md should reflect the resulting repository state;
- README examples and UI descriptions should match current behavior;
- `just check` and `just release-check` should pass;
- built artifacts should be exercised through the repository's installation/rehearsal tooling;
- known real-Kitty and platform limitations should be recorded rather than inferred from headless tests;
- optional integrations must not be mistaken for core requirements;
- package version, changelog release heading, tag, and published artifacts must agree.

Tagging and publication are separate release actions from the version/documentation bump itself. Do not create a release tag until the commit being tagged is the same tree that passed the final release rehearsal.
