# Plan

## Current strategy

The next milestone is public-release hardening for catherd 0.19.0. The core Kitty organizer is functionally complete for the scope defined in DESIGN.md; this plan does not expand that scope. The release work is intended to make the existing product safe to install, understandable to new users, reproducibly testable, and distributable through PyPI and GitHub.

Kitty remains the authoritative source of hierarchy and current terminal state. Atuin is optional enrichment only: catherd must remain fully useful for inspection and organization when Atuin is absent.

GitHub Actions work is deliberately deferred until all release work that can be completed and verified without GitHub Actions is finished. Local quality gates and manual/clean-environment rehearsals remain authoritative during the earlier phases.

## Phase 1: Clarify the product boundary

Establish the public contract before changing release mechanics.

- Define catherd as a Kitty inspector and organizer.
- Treat Kitty as the only external dependency required for core functionality.
- Define Atuin as an optional integration used to enrich panes with recently completed command history.
- Ensure the TUI, hierarchy inspection, focus, rename, move, reorder, merge, filtering, and basic `show` behavior remain functional without Atuin.
- Keep the current scope exclusions: no creation or closing of terminal objects, no process-lifecycle management, no persistent workspace/session model, and no attempt to replace Kitty's full remote-control interface.
- Update DESIGN.md where necessary to make the core/optional-integration distinction durable.

The acceptance condition for this phase is that removing Atuin and its catherd session files does not impair core organizer behavior.

## Phase 2: Isolate and harden optional Atuin integration

Move Atuin setup out of the apparent core-installation path and make its filesystem effects safe.

- Replace ambiguous top-level `install` / `uninstall` terminology with an explicitly Atuin-scoped interface, such as `catherd atuin enable|disable|doctor` or an equivalent integration namespace.
- Provide a reasonable migration path for existing installations and old snippet markers.
- Treat a missing Atuin executable, session environment, history database, or pane/session mapping as an optional-integration state rather than a core catherd failure.
- Keep Atuin out of mandatory Python package dependencies.
- Correct the generated shell snippets and decide which shells are genuinely supported for the initial public release.
- Validate every advertised shell's generated snippet with the shell's parser where practical and exercise its behavior in isolated HOME/XDG environments.
- Verify idempotent enable/disable behavior, preservation of existing rc contents, dry-run behavior, backups, special-character/path handling, and failure recovery.
- Validate a generated snippet before modifying a user's startup file.

The acceptance condition is that a fresh installation never modifies shell configuration merely to use catherd, and every advertised Atuin integration path is syntax- and behavior-tested.

## Phase 3: Harden the public CLI

Make the non-TUI interface suitable both for humans and scripts.

### Responsive `show`

Replace the fixed-width database-style table with a hierarchy-oriented, terminal-responsive human view.

- Derive layout from available terminal width.
- Normalize embedded newlines and repeated whitespace in command summaries.
- Keep commands to one display line in the default view.
- Prefer titles, current/recent command, focus/activity state, and working directory over IDs and process metadata.
- Adapt or omit secondary metadata at narrow widths rather than relying on fixed truncation widths.
- Preserve complete values in `--json` and the richer `inspect` representation.
- Keep a verbose human mode for IDs, process details, geometry, and other diagnostic metadata.
- Define sensible behavior for piped output where terminal width is unavailable.
- Verify representative narrow, ordinary, and wide terminal widths.

### Diagnostic structure

Reorganize `doctor` around the actual dependency boundary:

- core Kitty availability and remote control;
- Kitty-provided enrichment such as current command, CWD, and shell-integration metadata;
- optional Atuin enrichment as a separate section.

Diagnostics must distinguish Kitty shell integration from catherd's optional Atuin shell integration and must not imply that missing Atuin makes catherd itself unhealthy.

### CLI contract

Audit command exit semantics so successful commands return zero and required-dependency, invocation, parsing, and mutation failures return nonzero. Absence of optional Atuin enrichment should normally remain successful. Add a normal `catherd --version` interface and corresponding tests.

The acceptance condition is that the CLI is readable interactively and dependable from scripts.

## Phase 4: Resolve licensing, packaging, and support metadata

Prepare the project metadata for publication.

- Resolve the current license contradiction between LICENSE.md and `pyproject.toml`, choose the intended license, and make all SPDX/package/repository metadata agree.
- Add a meaningful package description, classifiers, keywords, supported Python versions, supported operating-system information, and useful project URLs.
- Decide and document the initially supported operating systems based on actual testing rather than assumed portability.
- Remove metadata/dependency-list inconsistencies such as duplicate development requirements.
- Improve the GitHub repository description and topics so the project is discoverable by purpose as well as by name.

The acceptance condition is that wheel/sdist metadata accurately communicates what catherd is, its license, its compatibility, and where users should report problems.

## Phase 5: Public documentation and onboarding

Make the repository usable by someone who has not participated in development.

- Add a concise README introduction that states what catherd does and does not do.
- Add explicit prerequisites, including Kitty and any required Kitty remote-control configuration.
- Add supported installation methods for the intended PyPI release, with `uv tool` as the preferred path and other supported methods documented as appropriate.
- Make the first-run path clear: install, run `catherd doctor`, then run `catherd tui` or `catherd show`.
- Document Atuin separately as optional enrichment and document only the shells/platforms actually supported.
- Add one or two current screenshots of the finished TUI, sufficient to communicate the hierarchy, focus/selection distinction, and inspector without turning the README into a gallery.
- Ensure README examples, DESIGN.md, STATUS.md, TESTING.md, and CLI help all describe the same public contract.

The acceptance condition is that a new user can install and reach a working TUI from the README alone.

## Phase 6: Reproducible local build and artifact validation

Prove the distributable package independently of the source checkout before automating it.

- Make the development/release environment reproducible; commit the uv lockfile unless a concrete reason not to do so emerges.
- Build both sdist and wheel with the intended build backend.
- Inspect package contents and metadata for accidental omissions or reliance on development-only repository files.
- Install the wheel into a clean environment and exercise the installed entry points, including help, version, module invocation, diagnostics, and expected failure behavior without Kitty or Atuin.
- Verify that the installed artifact behaves equivalently to the source checkout.
- Run local dependency/security and secret checks that do not require GitHub infrastructure.
- Ensure runtime dependency ranges remain package-appropriate even though development/release tooling is locked.

The acceptance condition is that the exact built artifacts intended for publication pass smoke and behavior checks in an isolated environment.

## Phase 7: Clean-machine and safety acceptance

Perform a release rehearsal from the perspective of a user rather than a developer.

- Install only the built/public candidate artifact, without relying on the repository checkout.
- Start with Kitty available but no catherd shell configuration and no Atuin integration.
- Exercise `doctor`, `show`, and the TUI's inspect/focus/rename/move/reorder/merge workflow.
- Enable optional Atuin enrichment, start fresh shells/panes as required, and verify pane-to-history association.
- Disable the integration and verify that startup-file contents remain sound.
- Review every persistent filesystem write and Kitty mutation for partial failure, stale state, interruption, special-character handling, and recovery behavior.
- Confirm that no undocumented local-development assumptions are required.

The acceptance condition is a successful clean-user rehearsal with and without optional Atuin enrichment.

## Phase 8: Prepare the 0.19.0 release state

Once the product and artifacts are locally release-ready:

- choose 0.19.0 as the deliberate first public-release boundary unless a later decision changes the target;
- set package/version metadata consistently;
- curate the accumulated `Unreleased` changelog into the release entry and restore an empty `Unreleased` section;
- update STATUS.md to describe the release-ready state;
- ensure TODO.md contains no hidden release blockers;
- ensure all local formatting, lint, type, import, test, build, artifact-install, and acceptance gates pass.

No GitHub Actions implementation should begin before Phases 1-8 are complete except for investigation that is strictly necessary to determine later workflow requirements.

## Phase 9: Add GitHub Actions and repository automation

Only after all non-GitHub-Actions-dependent hardening is complete, automate the gates that have already been proven locally.

### Continuous integration

Add GitHub Actions for pushes and pull requests covering the Python versions declared as supported, currently 3.12 through 3.14. The automated gates should include:

- syntax validation;
- format checking;
- Ruff;
- ty;
- import-linter;
- the complete pytest suite;
- shell-integration validation for advertised shells;
- package build;
- clean installation and smoke tests of built artifacts.

Add OS jobs only for platforms the project intends to claim as supported.

### Supply-chain and maintenance automation

Add appropriate automated dependency/security checks, secret-scanning integration, and dependency-update automation where useful. Do not make optional developer reporting tools accidental requirements for otherwise valid CI.

### Release automation

Use a tag-driven release process that:

1. verifies the tag and package version agree;
2. reruns required release gates;
3. builds the sdist and wheel once;
4. tests those exact artifacts;
5. publishes those same artifacts to PyPI;
6. creates the corresponding GitHub Release.

Prefer PyPI Trusted Publishing from GitHub Actions over a reusable long-lived publishing token, and use release-environment protections as appropriate.

The acceptance condition is that a tagged commit reproducibly produces one verified artifact set that is used for both PyPI and the GitHub Release.

## Phase 10: Public release

After the automated release path itself has been rehearsed successfully:

- tag `v0.19.0`;
- publish the verified package artifacts;
- publish the GitHub Release and curated release notes;
- immediately verify installation from PyPI in a fresh environment;
- record only genuine post-release defects or compatibility work as follow-up issues rather than expanding the release scope.

Subsequent patch releases should address compatible fixes and maintenance. Any deliberate expansion of the product boundary should update DESIGN.md before entering PLAN.md.

## Ongoing change sequence

For functional changes within the current scope:

1. Update the canonical model/parser only when Kitty exposes new or changed state that catherd must understand.
2. Add or modify the Kitty backend operation and its object/state validation.
3. Expose behavior through CLI or TUI without bypassing the backend boundary.
4. Preserve selection/focus separation, native tree topology, refresh invariants, and stale-result protection.
5. Add headless regression/acceptance coverage for interaction behavior.
6. Run the repository quality gates and, for Kitty/native-window behavior, perform a real-Kitty acceptance rehearsal.
7. Update README, DESIGN, STATUS, or CHANGELOG only when their policy-defined responsibilities are affected.

## UI maintenance

Presentation changes should remain non-structural whenever possible. In particular:

- grouping and highlighting should be rendered as styles, not synthetic tree nodes;
- native Textual collapse/hit-testing topology should be preserved;
- selection styling must not overwrite semantic foreground colors;
- command normalization is for identity/display only; exact commands remain available in metadata.

## Scope expansion

Creating or closing terminal objects, process lifecycle management, persistent workspace/session models, or replacement of Kitty's broader remote-control interface are not queued release requirements. If one of those becomes a goal, update DESIGN.md first, then add an implementation phase here.

## Release discipline

Before release or merge to the default branch:

- no immediate work should remain hidden in TODO.md;
- STATUS.md should reflect the resulting repository state;
- README examples and UI descriptions should match current behavior;
- formatting, lint, type checking, import checks, tests, build checks, and artifact smoke tests should pass;
- known real-Kitty and platform limitations should be recorded rather than inferred from headless tests;
- optional integrations must not be mistaken for core requirements.
