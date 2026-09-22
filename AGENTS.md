# AGENTS.md

## Purpose

This file defines generic contribution and tooling rules for catherd.
Project-specific architecture, domain invariants, and authority boundaries belong
in DESIGN.md and other project documentation rather than in this shared file.

## Canonical tooling interface

Use the root `justfile` as the normal interface to repository tooling.

For repository-wide implementation work, `just check` is the canonical
validation gate unless the project explicitly documents another gate.

Do not silently bypass a configured tool because it is inconvenient or missing.
Report the failure or repair the configured environment.

## Python tooling

- Use `uv` for environment synchronization, locking, dependency operations,
  and Python command execution.
- Use `just tooling-sync` to reconcile the Skellington-owned entries in
  `pyproject.toml` and synchronize the environment.
- Use `just tooling-check` to detect shared pyproject drift without modifying it.
- Use `just format --check` for non-mutating format validation.
- Use `just lint --no-fix` for non-mutating Ruff validation.
- Use `just typecheck` for static typing.
- Use `just test` for the normal test suite.
- Use `just test --fast` for a shorter development selection.
- Use `just cov` to inspect coverage from a coverage-bearing test run.
- Use `just lint-imports` when the repository has an
  `import-linter.toml`; those contracts remain project-specific.

The shared Ruff baseline targets Python 3.12 and a line length of
120. Project-specific exceptions belong in local configuration
unless an exception is genuinely general.

## Design discipline

- Prefer a concrete vertical slice before introducing an abstraction.
- Do not introduce shared/common utility layers for hypothetical future reuse.
- Prefer deleting obsolete compatibility machinery when backwards
  compatibility is not an explicit requirement.
- Prefer established, well-supported libraries for non-core functionality.
- Preserve deterministic output and tests where practical.
- Keep domain policy out of presentation/CLI layers.
- Keep architecture rules in project-owned design/configuration rather than
  shared tooling.

## Documentation and history

Follow `POLICY.md`.

- DESIGN.md records durable intent and architecture.
- PLAN.md records execution strategy.
- STATUS.md records current state and handoff context.
- TODO.md contains immediate unfinished work.
- CHANGELOG.md records curated notable changes.
- Git commits form fine-grained implementation history.

Read relevant project-owned documents before changes that depend on current
intent or project history.

## Commits

Prefer logically scoped, self-contained commits with concise subjects such as:

- `feat: add structured output`
- `fix: handle missing configuration`
- `test: cover release artifact behavior`

A project may impose stronger requirements locally.
