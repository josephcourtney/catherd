# AGENTS.md

## Purpose

This file defines how AI coding agents (LLMs, autonomous development tools,
etc.) must operate when contributing to the Mund workspace.

## Role

Your responsibilities include:

- Editing Python source files under `packages/*/src/`
- Creating or editing package tests under `packages/*/tests/`
- Creating or editing cross-package tests under root `tests/`
- Maintaining package-local architecture documents when explicitly required
- Maintaining repository-level planning and status documents when explicitly required
- Preserving output determinism, testability, and extensibility
- Respecting package boundaries, authority boundaries, CLI conventions, and
  internal architecture

## Directory Constraints

Mund is a `uv` workspace containing independently bounded Python packages.

Repository layout:

- Package source: `packages/<package>/src/<package>/`
- Package tests: `packages/<package>/tests/`
- Cross-package tests: `tests/`
- Repository scripts: `scripts/`
- Package design: `packages/<package>/DESIGN.md`
- Package README: `packages/<package>/README.md`
- Repository vision: `VISION.md`
- Repository implementation plan: `PLAN.md`
- Repository current state: `STATUS.md`
- Repository immediate work: `TODO.md`
- Repository change history: `CHANGELOG.md`
- Documentation policy: `POLICY.md`

Current executive packages are:

- `reck`
- `refa`
- `shyft`
- `scroot`

Do not assume that code belonging to one package may be placed in another
package merely because all packages share one repository.

Do not create shared packages, common utility modules, shared domain models,
or other cross-package abstractions speculatively. Introduce shared code only
when an actual cross-package requirement or demonstrated duplication justifies
it.

## Tooling Requirements

Use the root `justfile` as the canonical interface to repository tooling.

Before considering implementation work complete, run the relevant validation
recipes. For repository-wide changes, `just check` is the canonical validation
gate.

If a command fails because of a missing executable or broken environment,
report the failure clearly. Do not work around the configured toolchain by
silently substituting unrelated tools.

### Package Management

- Command: `uv`
- Rules:
  - use `uv` for package management, dependency changes, locking, and syncing
  - use the root workspace rather than creating package-local virtual
    environments
  - add dependencies to the narrowest package that actually requires them
  - add repository-only development tooling to the root development dependency
    group

### Linting

- Command: `just lint --no-fix`
- Repair command: `just lint`
- Rules are defined by the root `pyproject.toml`, `ruff.default.toml`, and
  package-local Ruff configuration.

### Formatting

- Check: `just format --check`
- Repair: `just format`

### Static Typing

- Command: `just typecheck`
- Syntax must remain compatible with the Python range declared by the affected
  package.
- Constraints are defined by repository and package configuration.

### Testing

- Command: `just test`
- Fast development run: `just test --fast`
- Development-selection run: `just test --dev`
- Coverage: Add tests for new features and regression paths
- Constraints:
  - Use deterministic data
  - Avoid system-dependent values (e.g., timestamps, user paths)
  - Put package-specific tests under that package's `tests/` directory
  - Put tests spanning package boundaries under root `tests/`
  - Use existing test-category markers consistently

### Import Architecture

- Command: `just lint-imports`
- Package-local `import-linter.toml` files define internal package boundaries.
- A root `import-linter.toml`, when present, defines only workspace-wide
  cross-package constraints.
- Do not move package-local architecture rules into the root configuration
  merely for centralization.

### Canonical Validation

- Command: `just check`
- `just check` is the repository-wide validation gate and includes syntax,
  formatting, linting, typing, import architecture, tests, and coverage
  reporting.

## Behavior Constraints

- Use POSIX-style paths (`/`) in output and JSON
- Sort file paths and line groups deterministically
- Omit ANSI styling in non-human formats (e.g., JSON)
- Maintain internal consistency across toolchain and file states
- Keep domain and behavioral policy out of CLI and other presentation code
- Preserve package authority boundaries described by `VISION.md` and each
  package's `DESIGN.md`
- Preserve provenance distinctions where the design treats user reports,
  observations, inferences, corrections, triggers, and decisions as different
  facts
- Prefer deleting obsolete compatibility machinery over layering new behavior
  on top of it; this is a single-user system and backwards compatibility is
  not a default requirement
- Do not add speculative abstractions for hypothetical future components
- Prefer a concrete vertical slice before generalizing architecture
- Prefer existing, popular, well-supported libraries when appropriate
  - For logic or functionality that is not core to the project, or is not highly customized, add an appropriate dependency rather than writing a custom version.

## Logging and Progress Tracking

### To-Do List Maintenance

- Follow `POLICY.md`.
- `TODO.md` contains only immediate unfinished work.
- Remove completed items rather than retaining them as history.
- Do not use `TODO.md` as a changelog or progress archive.
- Add or rewrite TODO items when implementation work changes the immediate
  execution frontier.

### Changelog Maintenance

Follow `POLICY.md` and Keep a Changelog conventions.

- Example heading: `## [1.2.3] - 2025-08-02`
- Allowed sections: `Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`

Ensure:

- changelog entries describe notable implemented changes rather than
  task-level details
- changelog contents match actual behavior
- package-version changes are made only when appropriate for the affected
  package
- repository-wide and package-specific history are not conflated merely
  because the packages share one workspace

Example:

```markdown
## [1.4.0] - 2025-08-02

### Added
- add `--format json` CLI option for machine-readable output

### Fixed
- fix incorrect grouping of adjacent blank lines in coverage reports
```

## Commit Standards

Each commit must pass:

- `just check`

Use conventional commit messages:

- `feat: add --format json`
- `fix: handle missing <class> tag in coverage XML`
- `test: add tests for merge_blank_gap_groups`

Before submitting a pull request:

- update documentation required by `POLICY.md`
- update the affected package version only when the change warrants a release
- update changelog entries for notable completed changes

## Prohibited Behavior

- Do not introduce dependencies between executive packages merely for
  implementation convenience
- Do not bypass semantic exchange boundaries by importing another executive
  package's internal domain/application implementation
- Do not create a generic shared `common`, `core`, or `utils` package without a
  demonstrated cross-package requirement
- Do not preserve obsolete APIs, schemas, migrations, adapters, or abstraction
  layers solely for backwards compatibility unless explicitly requested
- Do not introduce non-determinism (e.g., random output, time-dependent data)
- Do not put domain policy in CLI code
- Do not treat objective activity as proof of subjective attention
- Do not silently collapse user reports, observations, inferences, corrections,
  or explicit decisions into one representation

## Assumptions and Capabilities

You must assume:

- Each task starts with only the current file state
- `VISION.md` is normative for workspace-level authority boundaries
- each package's `DESIGN.md` is normative for that package's architecture
- `PLAN.md` describes future implementation sequencing
- `STATUS.md` describes current implementation state
- `TODO.md` describes immediate unfinished work
- `CHANGELOG.md` records notable completed changes
- `POLICY.md` governs documentation responsibilities
- relevant design, status, TODO, and changelog material must be read before
  making changes that depend on project history or current intent

If lacking access to shell or file I/O:

- Emit a Markdown-formatted patch containing proposed edits
- Describe expected outputs of toolchain commands
- Do not claim that validation was run

## Compliance

All actions must follow this protocol unless:

- Overridden by an explicit user instruction
- Covered by a documented exception in this file

