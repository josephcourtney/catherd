# Project-owned composition layer.
#
# Skellington owns the imported shared tooling. Catherd owns this file and
# composes those shared operations with project-specific validation.

import '.tooling/core.just'
import '.tooling/python-quality.just'
import '.tooling/python-test.just'
import '.tooling/python-package.just'

PACKAGE := file_stem(ROOT_DIR)

[private]
default: help


# Print resolved runtime configuration.
[group('meta')]
env:
  @just _log_start env
  @echo "MODE={{MODE}}"
  @echo "PACKAGE={{PACKAGE}}"
  @echo "PYTHON_PACKAGE={{PYTHON_PACKAGE}}"
  @echo "PY_SRC={{PY_SRC}}"
  @echo "PY_TESTPATH={{PY_TESTPATH}}"
  @echo "PY_SCRIPTS={{PY_SCRIPTS}}"
  @echo "UV={{UV}}"
  @echo "RUFF={{RUFF}}"
  @echo "PYTEST={{PYTEST}}"
  @echo "TY={{TY}}"
  @echo "SHOWCOV={{SHOWCOV}}"
  @echo "VULTURE={{VULTURE}}"
  @echo "RADON={{RADON}}"
  @echo "IMPORT_LINTER={{IMPORT_LINTER}}"
  @echo "JSCPD={{JSCPD}}"
  @{{UV}} --version || true
  @{{PYTEST}} --version || true
  @{{RUFF}} --version || true
  @just _log_end env


# Run real advertised-shell parser and behavior checks outside pytest.
#
# pytest-test-categories enforces subprocess isolation inside pytest; this
# boundary check intentionally launches the shell executables themselves.
[group('testing')]
test-shell-integration:
  {{PYTHON}} {{ROOT_DIR}}/scripts/check_shell_integration.py


# Run the headless Textual acceptance suite for the Kitty organizer.
[group('testing')]
test-tui:
  {{PYTEST}} --timeout={{PYTEST_TIMEOUT}} --no-cov {{ROOT_DIR}}/tests/test_tui.py


# Best-effort local repair loop.
#
# Shared/static repair steps continue after individual failures. Environment
# reconciliation and tests remain strict.
[group('convenience')]
fix:
  @just _run tooling-sync "just tooling-sync"
  @just _run_soft syntax "just syntax"
  @just _run_soft format "just format"
  @just _run_soft lint "just lint"
  @just _run_soft typecheck "just typecheck"
  @just _run_soft lint-imports "just lint-imports"
  @just _run shell-integration "just test-shell-integration"
  @just _run "test --fast" "just test --fast"
  @just _run_soft cov "just cov"


# Canonical repository validation gate.
[group('convenience')]
check:
  @just _run tooling-check "just tooling-check"
  @just _run syntax "just syntax"
  @just _run format "just format --check"
  @just _run lint "just lint --no-fix"
  @just _run typecheck "MODE=ci just typecheck"
  @just _run lint-imports "just lint-imports"
  @just _run shell-integration "just test-shell-integration"
  @just _run test "just test"
  @just _run cov "just cov"


# Preserve Catherd's existing release gate for this migration. The imported
# release-smoke recipe will be tested separately before deciding whether it
# belongs here permanently.
[group('production')]
release-check:
  @just _run check "just check"
  @just _run build-release "just build-release"
