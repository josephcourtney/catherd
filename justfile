# ======================================================================
# Global shell + environment
# ======================================================================

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := true
set export := true

# ----------------------------------------------------------------------
# Config (overridable via env/.env)
# ----------------------------------------------------------------------

MODE          := env("MODE", "dev")  # dev | debug | ci
PYTHON_PACKAGE := env("PYTHON_PACKAGE", "borh")
PY_TESTPATH    := env("PY_TESTPATH", "tests")
PY_SRC         := env("PY_SRC", "src")
VERBOSE        := env("VERBOSE", "0")

# ----------------------------------------------------------------------
# Tool wrappers
# ----------------------------------------------------------------------

UV         := "uv"
RUFF       := justfile_directory() + "/.venv/bin/ruff"
PYTEST     := justfile_directory() + "/.venv/bin/pytest"
TY         := justfile_directory() + "/.venv/bin/ty"
SHOWCOV    := justfile_directory() + "/.venv/bin/showcov"
MUTMUT     := justfile_directory() + "/.venv/bin/mutmut"
MKDOCS     := justfile_directory() + "/.venv/bin/mkdocs"
WILY       := justfile_directory() + "/.venv/bin/wily"
WILY_CACHE := justfile_directory() + "/.wily"
WILY_CONFIG := justfile_directory() + "/wily.cfg"
VULTURE    := justfile_directory() + "/.venv/bin/vulture"
RADON      := justfile_directory() + "/.venv/bin/radon"
JSCPD      := "npx --yes jscpd@4.0"
DIFF_COVER := justfile_directory() + "/.venv/bin/diff-cover"
IMPORTLINTER        := justfile_directory() + "/.venv/bin/lint-imports"
IMPORTLINTER_CONFIG := justfile_directory() + "/import-linter.toml"

# ======================================================================
# Meta / Defaults
# ======================================================================

[private]
default: help

# List available recipes; also the default entry point
help:
  @just _log_start help
  @just --list --unsorted --list-prefix "  "
  @just _log_end help


# Print runtime configuration (paths + tool binaries)
env:
  @just _log_start env
  @echo "MODE={{MODE}}"
  @echo "PYTHON_PACKAGE={{PYTHON_PACKAGE}}"
  @echo "PY_TESTPATH={{PY_TESTPATH}}"
  @echo "PY_SRC={{PY_SRC}}"
  @echo "UV={{UV}}"
  @echo "RUFF={{RUFF}}"
  @echo "PYTEST={{PYTEST}}"
  @echo "TY={{TY}}"
  @echo "SHOWCOV={{SHOWCOV}}"
  @echo "MUTMUT={{MUTMUT}}"
  @echo "MKDOCS={{MKDOCS}}"
  @{{UV}} --version || true
  @{{PYTEST}} --version || true
  @{{RUFF}} --version || true
  @echo "WILY={{WILY}}"
  @echo "WILY_CACHE={{WILY_CACHE}}"
  @echo "WILY_CONFIG={{WILY_CONFIG}}"
  @echo "VULTURE={{VULTURE}}"
  @echo "RADON={{RADON}}"
  @echo "JSCPD={{JSCPD}}"
  @echo "DIFF_COVER={{DIFF_COVER}}"
  @just _log_end env

# ----------------------------------------------------------------------
# Logging helpers
# ----------------------------------------------------------------------

_log_start NAME:
  @printf "\n=== START: %s ===\n" "{{NAME}}"

_log_end NAME:
  @printf "=== END: %s ===\n\n" "{{NAME}}"



# ======================================================================
# Bootstrap
# ======================================================================

# Bootstrap: refresh .venv via `uv sync`
setup:
  @just _log_start setup
  {{UV}} sync
  @just _log_end setup


# ======================================================================
# Code quality: lint / format / type-check
# ======================================================================

# Code Quality: Lint with `ruff check` and auto-fix where possible
lint:
  @just _log_start lint
  {{RUFF}} check --fix {{PY_SRC}} {{PY_TESTPATH}} || true
  @just _log_end lint

# Code Quality: Check for linting violations with `ruff check` without modifying files
lint-no-fix:
  @just _log_start lint-no-fix
  {{RUFF}} check --no-fix {{PY_SRC}} {{PY_TESTPATH}}
  @just _log_end lint-no-fix

# Code Quality: Lint import architecture (Import Linter)
lint-imports:
  @just _log_start lint-imports
  bash -euo pipefail -c 'if [ ! -x {{IMPORTLINTER}} ]; then echo "[lint-imports] ERROR: lint-imports not found ({{IMPORTLINTER}}); install import-linter dev dep and run '\''just setup'\''"; exit 1; fi; set +e; output="$({{IMPORTLINTER}} --verbose --config {{IMPORTLINTER_CONFIG}} 2>&1)"; status=$?; set -e; if [ "$status" -ne 0 ]; then echo "[lint-imports] FAILED"; echo; echo "$output"; exit "$status"; else echo "[lint-imports] no import-linter contract violations detected."; fi'
  @just _log_end lint-imports

# Code Quality: Format with `ruff format` and auto-fix where possible
format:
  @just _log_start format
  {{RUFF}} format {{PY_SRC}} {{PY_TESTPATH}} || true
  @just _log_end format

# Code Quality: Check for formatting violations with `ruff format` without modifying files
format-no-fix:
  @just _log_start format-no-fix
  {{RUFF}} format --check {{PY_SRC}} {{PY_TESTPATH}}
  @just _log_end format-no-fix

# Code Quality: Typecheck with `ty` (if available)
typecheck:
  @just _log_start typecheck
  bash -euo pipefail -c '\
    if [ -x {{TY}} ]; then \
      {{TY}} check {{PY_SRC}} {{PY_TESTPATH}}; \
      exit 0; \
    fi; \
    if [ "{{MODE}}" = "ci" ]; then \
      echo "[typecheck] ERROR: ty not found ({{TY}}) and MODE=ci requires typechecking"; \
      exit 1; \
    fi; \
    echo "[typecheck] skipping: ty not found ({{TY}}) (MODE={{MODE}})"; \
  '
  @just _log_end typecheck

# Code Quality: dead-code scan
dead-code:
  @just _log_start dead-code
  {{VULTURE}} {{PY_SRC}} {{PY_TESTPATH}} || true
  @just _log_end dead-code

# Code Quality: public API consistency check
public-api:
  @just _log_start public-api
  bash -euo pipefail -c 'if [ -x .venv/bin/python ] && [ -f scripts/check_public_api.py ]; then .venv/bin/python scripts/check_public_api.py; else echo "[public-api] ERROR: scripts/check_public_api.py missing or .venv not available"; exit 1; fi'
  @just _log_end public-api

# Code Quality: complexity report
complexity:
  @just _log_start complexity
  {{RADON}} cc -s -a {{PY_SRC}}
  @just _log_end complexity

# Code Quality: raw metrics (optional)
complexity-raw:
  @just _log_start complexity-raw
  {{RADON}} raw {{PY_SRC}}
  @just _log_end complexity-raw

# Code Quality: strict complexity check (fail on high-complexity blocks)
complexity-strict MIN_COMPLEXITY="11":
  @just _log_start complexity-strict
  bash -euo pipefail -c 'echo "[complexity-strict] Failing if any block has cyclomatic complexity >= ${MIN_COMPLEXITY}"; output="$({{RADON}} cc -s -n {{MIN_COMPLEXITY}} {{PY_SRC}} || true)"; if [ -n "$output" ]; then echo "[complexity-strict] Found blocks with complexity >= ${MIN_COMPLEXITY}:"; echo "$output"; exit 1; fi; echo "[complexity-strict] All blocks are below complexity ${MIN_COMPLEXITY}."'
  @just _log_end complexity-strict

# Code Quality: duplication detection
dup:
  @just _log_start dup
  {{JSCPD}} --pattern "{{PY_SRC}}/*/*.py" --pattern "{{PY_SRC}}/*/*/*.py" --pattern "{{PY_SRC}}/*/*/*/*.py" --pattern "{{PY_TESTPATH}}/*/*.py" --pattern "{{PY_TESTPATH}}/*/*/*.py" --pattern "{{PY_TESTPATH}}/*/*/*/*.py" --reporters console
  @just _log_end dup


# ======================================================================
# Security / supply chain
# ======================================================================

# Security: Secret scan with trufflehog (report-only; does not fail if tool missing)
sec-secrets:
  @just _log_start sec-secrets
  bash -euo pipefail -c 'if command -v trufflehog >/dev/null 2>&1; then tmp_file=$(mktemp); printf ".venv\nbuild\ndist\n" > "$tmp_file"; trufflehog filesystem . --exclude-paths "$tmp_file"; rm -f "$tmp_file"; else echo "[sec-secrets] skipping: trufflehog not found on PATH"; fi'
  @just _log_end sec-secrets

# Security: Dependency scan with pip-audit
sec-deps:
  @just _log_start sec-deps
  bash -euo pipefail -c 'if [ -x .venv/bin/pip-audit ]; then PIP_NO_CACHE_DIR=1 .venv/bin/pip-audit; else echo "[sec-deps] ERROR: .venv/bin/pip-audit not found; run '\''just setup'\'' to install dev deps"; exit 1; fi'
  @just _log_end sec-deps

# Security: Check external tools (presence + minimum versions)
sec-tools:
  @just _log_start sec-tools
  bash -euo pipefail -c 'if [ -x .venv/bin/python ] && [ -f scripts/check_tools.py ]; then .venv/bin/python scripts/check_tools.py; else echo "[sec-tools] ERROR: scripts/check_tools.py missing"; exit 1; fi'
  @just _log_end sec-tools


# ======================================================================
# Testing
# ======================================================================

# Testing: Run full test suite
test:
  @just _log_start test
  {{PYTEST}} {{PY_TESTPATH}} || true
  @just _log_end test

# Testing: Run full test suite and fail if any test fails
test-strict:
  @just _log_start test-strict
  {{PYTEST}} {{PY_TESTPATH}}
  @just _log_end test-strict

# Testing: Marker-driven test runner with graceful "no tests" handling
test-marker MARKER:
  @just _log_start test-marker
  bash -euo pipefail -c 'set +e; {{PYTEST}} {{PY_TESTPATH}} -m "{{MARKER}}"; status=$?; set -e; if [ "$status" -eq 5 ]; then echo "[{{MARKER}}] skipping: no tests marked with {{MARKER}} collected"; elif [ "$status" -ne 0 ]; then exit "$status"; fi'
  @just _log_end test-marker

# Testing: Run tests marked with "unit" and not marked with "slow"
test-fast:
  @just _log_start test-fast
  @just test-marker "unit and not slow"
  @just _log_end test-fast

# Testing: Run tests marked with "smoke"
test-smoke:
  @just _log_start test-smoke
  @just test-marker "smoke"
  @just _log_end test-smoke

# Testing: Run tests marked with "regression"
test-regression:
  @just _log_start test-regression
  @just test-marker "regression"
  @just _log_end test-regression

# Testing: Run tests marked with "performance"
test-performance:
  @just _log_start test-performance
  @just test-marker "performance"
  @just _log_end test-performance

# Testing: Run tests marked with "property_based"
test-property:
  @just _log_start test-property
  @just test-marker "property_based"
  @just _log_end test-property


# ======================================================================
# Test Quality
# ======================================================================

# Testing: Run full test suite and report slowest tests
test-timed:
  @just _log_start test-timed
  {{PYTEST}} {{PY_TESTPATH}} --durations=25
  @just _log_end test-timed

# Test Quality: Summarize coverage results from last test execution
cov:
  @just _log_start cov
  bash -euo pipefail -c 'if [ -x {{SHOWCOV}} ]; then {{SHOWCOV}} --sections summary --format human || true; else echo "[cov] skipping: showcov ({{SHOWCOV}}) not found"; fi'
  @just _log_end cov

# Test Quality: List lines not covered by last test execution
cov-lines:
  @just _log_start cov-lines
  bash -euo pipefail -c 'if [ -x {{SHOWCOV}} ]; then {{SHOWCOV}} --code --context 2,2 || true; else echo "[cov-lines] skipping: showcov ({{SHOWCOV}}) not found"; fi'
  @just _log_end cov-lines

# Test Quality: Run mutation testing on the test suite
mutation *ARGS:
  @just _log_start mutation
  bash -euo pipefail -c 'if [ -x {{MUTMUT}} ]; then {{MUTMUT}} run {{ARGS}}; else echo "[mutmut] skipping: mutmut not found ({{MUTMUT}})"; fi'
  @just _log_end mutation

# Test Quality: Report mutation testing results
mutation-report:
  @just _log_start mutation-report
  bash -euo pipefail -c 'if [ -x {{MUTMUT}} ]; then {{MUTMUT}} results; else echo "[mutation-report] skipping: mutmut not found ({{MUTMUT}})"; fi'
  @just _log_end mutation-report

# Test Quality: Mutation score summary (for humans/CI)
mutation-score:
  @just _log_start mutation-score
  {{MUTMUT}} results | .venv/bin/python scripts/mutation_score.py
  @just _log_end mutation-score

# Test Quality: Show the diff for every mutant listed by `mutmut results`
mutation-diffs *ARGS:
  @just _log_start mutation-diffs
  bash -euo pipefail -c 'echo "=== Mutant Diffs ==="; .venv/bin/python scripts/mutation_diffs.py {{ARGS}} || true'
  @just _log_end mutation-diffs

# Test Quality: Test test flakiness by repeated runs of the test suite
flake N='5':
  @just _log_start flake
  bash -euo pipefail -c 'set +e; rm -f .flake-log.txt; for i in $(seq 1 {{N}}); do echo "=== run $i ===" | tee -a .flake-log.txt; {{PYTEST}} {{PY_TESTPATH}} --maxfail=50 --randomly-seed=last | tee -a .flake-log.txt; done; set -e'
  @just _log_end flake

# Test Quality: Report test flakiness results
flake-report:
  @just _log_start flake-report
  bash -euo pipefail -c 'if [ -f .flake-log.txt ]; then if [ -x .venv/bin/python ] && [ -f scripts/flake_report.py ]; then .venv/bin/python scripts/flake_report.py; else echo "[flake-report] scripts/flake_report.py missing; basic summary:"; echo "Tests that failed in at least one run:"; grep -oE "FAILED .*::[a-zA-Z0-9_]+" .flake-log.txt | sed "s/FAILED *//g" | sort | uniq -c | sort -nr; fi; else echo "[flake-report] no .flake-log.txt; run '\''just flake'\'' first"; fi'
  @just _log_end flake-report

# Test Quality: coverage of changed lines vs main
diff-cov BRANCH="origin/main":
  @just _log_start diff-cov
  bash -euo pipefail -c 'if [ ! -f .coverage.xml ]; then echo "[diff-cov] .coverage.xml not found; run '\''just test-strict'\'' first"; exit 1; fi; {{DIFF_COVER}} .coverage.xml --compare-branch={{BRANCH}}'
  @just _log_end diff-cov

# Test Quality: strict coverage of changed lines vs main with threshold
diff-cov-strict BRANCH="origin/main" THRESHOLD="90":
  @just _log_start diff-cov-strict
  bash -euo pipefail -c 'if [ ! -f .coverage.xml ]; then echo "[diff-cov-strict] .coverage.xml not found; run '\''just test-strict'\'' first"; exit 1; fi; echo "[diff-cov-strict] Enforcing changed-line coverage >= ${THRESHOLD}% against ${BRANCH}"; {{DIFF_COVER}} .coverage.xml --compare-branch={{BRANCH}} --fail-under={{THRESHOLD}}'
  @just _log_end diff-cov-strict

# Test Quality: Performance regression check against baselines
perf-regression:
  @just _log_start perf-regression
  bash -euo pipefail -c 'if [ ! -d .perf_results ]; then echo "[perf-regression] skipping: no .perf_results directory; run '\''just test-performance'\'' first"; exit 0; fi; if [ -x .venv/bin/python ] && [ -f scripts/check_perf_regression.py ]; then .venv/bin/python scripts/check_perf_regression.py; else echo "[perf-regression] ERROR: scripts/check_perf_regression.py missing"; exit 1; fi'
  @just _log_end perf-regression


# ======================================================================
# Metrics
# ======================================================================

# Metrics: build or update wily index incrementally
wily-index:
  @just _log_start wily-index
  bash -euo pipefail -c 'stash_name=""; if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then if [ -n "$(git status --porcelain)" ]; then stash_name="wily:temp:$(date -u +%Y%m%dT%H%M%SZ)"; git stash push -u -m "$stash_name" >/dev/null; trap "git stash pop -q" EXIT; fi; fi; {{WILY}} --config {{WILY_CONFIG}} --cache {{WILY_CACHE}} build {{PY_SRC}} {{PY_TESTPATH}}'
  @just _log_end wily-index

# Metrics: report current metrics from index
wily-metrics FILE="":
  @just _log_start wily-metrics
  @just wily-index
  bash -euo pipefail -c 'file="{{FILE}}"; if [ -z "$file" ]; then file="{{PY_SRC}}/{{PYTHON_PACKAGE}}/__init__.py"; fi; {{WILY}} --config {{WILY_CONFIG}} --cache {{WILY_CACHE}} report "$file"'
  @just _log_end wily-metrics

# Metrics: report stats for all files
wily-stats:
  @just _log_start wily-stats
  @just wily-index
  bash -euo pipefail -c 'mapfile -t files < <(rg --files -g "*.py" {{PY_SRC}} {{PY_TESTPATH}}); if [ "${#files[@]}" -eq 0 ]; then echo "[wily-stats] no Python files found in {{PY_SRC}} or {{PY_TESTPATH}}"; exit 0; fi; {{WILY}} --config {{WILY_CONFIG}} --cache {{WILY_CACHE}} diff --all --no-detail "${files[@]}"'
  @just _log_end wily-stats

# Metrics: report-only (no gating)
metrics-report:
  @just _log_start metrics-report
  bash -euo pipefail -c 'echo "=== Metrics Report (non-gating) ==="; echo "--- Coverage summary ---"; if [ -x {{SHOWCOV}} ]; then {{SHOWCOV}} --sections summary --format human || true; else echo "[metrics-report] showcov not found ({{SHOWCOV}}); skipping coverage summary"; fi; echo; echo "--- Mutation score ---"; if [ -x {{MUTMUT}} ]; then {{MUTMUT}} results | .venv/bin/python scripts/mutation_score.py || true; else echo "[metrics-report] mutmut not found ({{MUTMUT}}); skipping mutation score"; fi; echo; echo "--- Complexity report ---"; if [ -x {{RADON}} ]; then {{RADON}} cc -s -a {{PY_SRC}} || true; else echo "[metrics-report] radon not found ({{RADON}}); skipping complexity report"; fi; echo; echo "--- Duplication report ---"; {{JSCPD}} --pattern "{{PY_SRC}}/**/*.py" --pattern "{{PY_TESTPATH}}/**/*.py" --reporters console || true; echo; echo "--- Flakiness report ---"; if [ -f .flake-log.txt ]; then if [ -x .venv/bin/python ] && [ -f scripts/flake_report.py ]; then .venv/bin/python scripts/flake_report.py || true; else echo "[metrics-report] flake_report script missing; using basic grep summary"; grep -oE "FAILED .*::[a-zA-Z0-9_]+" .flake-log.txt | sed "s/FAILED *//g" | sort | uniq -c | sort -nr || true; fi; else echo "[metrics-report] no .flake-log.txt; run '\''just flake'\'' first for flake metrics"; fi; echo; echo "=== Metrics Report complete (non-gating) ==="'
  @just _log_end metrics-report

# Metrics: enforce thresholds
metrics-gate:
  @just _log_start metrics-gate
  bash -euo pipefail -c 'echo "=== Metrics Gate (gating) ==="; if [ -x .venv/bin/python ] && [ -f scripts/check_test_markers.py ]; then .venv/bin/python scripts/check_test_markers.py; else echo "[metrics-gate] ERROR: scripts/check_test_markers.py not found"; exit 1; fi; if [ ! -f .coverage.xml ]; then echo "[metrics-gate] .coverage.xml not found; run '\''just test-strict'\'' first"; exit 1; fi; {{DIFF_COVER}} .coverage.xml --compare-branch=origin/main --fail-under=90; {{RADON}} cc -s -n 11 {{PY_SRC}}; if [ -x {{MUTMUT}} ]; then {{MUTMUT}} results | .venv/bin/python scripts/mutation_score.py | tee .mutation-score.txt; if [ -x .venv/bin/python ] && [ -f scripts/check_mutation_threshold.py ]; then export MUTATION_MIN="${MUTATION_MIN:-70}"; .venv/bin/python scripts/check_mutation_threshold.py < .mutation-score.txt; else echo "[metrics-gate] ERROR: scripts/check_mutation_threshold.py not found"; exit 1; fi; else echo "[metrics-gate] ERROR: mutmut not found ({{MUTMUT}})"; exit 1; fi; echo "=== Metrics Gate PASSED ==="'
  @just _log_end metrics-gate


# ======================================================================
# Documentation
# ======================================================================

# Documentation: Build documentation using `mkdocs`
build-docs:
  @just _log_start build-docs
  bash -euo pipefail -c 'if [ -x {{MKDOCS}} ]; then {{MKDOCS}} build; else echo "[build-docs] skipping: mkdocs not found ({{MKDOCS}} or on PATH)"; fi'
  @just _log_end build-docs

# Documentation: Serve the documentation site locally
docs:
  @just _log_start docs
  @just build-docs
  bash -euo pipefail -c 'if [ -x {{MKDOCS}} ]; then python3 -m webbrowser http://127.0.0.1:8000; {{MKDOCS}} serve --livereload; else echo "[docs] skipping: mkdocs not found ({{MKDOCS}} or on PATH)"; fi'
  @just _log_end docs


# ======================================================================
# Build, packaging, publishing
# ======================================================================

# Production: Build Python artifacts with `uv build`
build:
  @just _log_start build
  {{UV}} build
  @just _log_end build

# Production: Publish to PyPI using `uv publish`
publish:
  @just _log_start publish
  {{UV}} publish
  @just _log_end publish


# ======================================================================
# Running
# ======================================================================

# Run: CLI mode via `python -m {{PYTHON_PACKAGE}}`
cli:
  @just _log_start cli
  @just setup
  .venv/bin/python -m {{PYTHON_PACKAGE}}
  @just _log_end cli


# ======================================================================
# Cleaning / maintenance
# ======================================================================

# Cleaning: Remove caches/build artifacts and prune uv cache
clean:
  @just _log_start clean
  find . -name '__pycache__' -type d -prune -exec rm -rf '{}' +
  rm -rf .ruff_cache .pytest_cache .mypy_cache .pytype
  rm -rf .coverage .coverage.* coverage.xml htmlcov
  rm -rf dist build
  rm -rf logs
  rm -rf .hypothesis .ropeproject .wily mutants
  {{UV}} cache prune
  @just _log_end clean

# Cleaning: Stash untracked (non-ignored) files (used by `scour`)
stash-untracked:
  @just _log_start stash-untracked
  bash -euo pipefail -c 'if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then msg="scour:untracked:$(date -u +%Y%m%dT%H%M%SZ)"; if git ls-files --others --exclude-standard --directory --no-empty-directory | grep -q .; then git ls-files --others --exclude-standard -z | xargs -0 git stash push -m "$msg" -- >/dev/null; echo "Stashed untracked (non-ignored) files as: $msg"; else echo "No untracked (non-ignored) paths to stash."; fi; else echo "[stash-untracked] not a git repository; skipping"; fi'
  @just _log_end stash-untracked

# Cleaning: Remove git-ignored files/dirs while keeping .venv
scour:
  @just _log_start scour
  @just clean
  @just stash-untracked
  bash -euo pipefail -c 'if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git clean -fXd -e .venv; else echo "[scour] not a git repository; skipping git clean"; fi'
  @just _log_end scour

# Testing + record: run tests and append a normalized record into .records/test_runs.jsonl
record TAG="local":
  @just _log_start record
  .venv/bin/python scripts/record_test_run.py --tag "{{TAG}}"
  @just _log_end record


# ======================================================================
# Composite flows
# ======================================================================

# Convenience: setup, lint, format, typecheck, build-docs, test, cov
fix:
  @just _log_start fix
  @just setup
  @just lint
  @just format
  @just typecheck
  @just lint-imports
  @just build-docs
  @just test
  @just cov
  @just record
  @just _log_end fix

# ----------------------------------------------------------------------
# MODE-driven orchestration
#
# MODE=dev   : fast, gating on core hygiene; avoids expensive gates by default.
# MODE=debug : minimal gating + increased diagnostics; skips expensive gates.
# MODE=ci    : full enforcement (equivalent to prior `check`).
# ----------------------------------------------------------------------

# Dev: fast-ish gating (no expensive metrics/security gates by default)
check-dev:
  @just _log_start check-dev
  @just setup
  @just format-no-fix
  @just lint-no-fix
  @just typecheck
  @just lint-imports
  @just public-api
  @just test-strict
  @just cov
  @just record TAG="dev"
  @just _log_end check-dev

# Debug: prioritize iteration speed + diagnostics; do not block on heavy gates.
#
# Use `just test-marker <expr>` / `just test-fast` / `just test-smoke` for tighter loops.
check-debug:
  @just _log_start check-debug
  @just setup
  # Keep formatting/lint checks (cheap) but avoid expensive / noisy gates.
  @just format-no-fix
  @just lint-no-fix
  @just typecheck
  # Avoid import-linter / public-api / metrics gates unless explicitly requested during debugging.
  # Run tests in "timed" mode to surface slow tests quickly.
  @just test-timed
  @just cov
  @just record TAG="debug"
  @just _log_end check-debug

# CI: full enforcement (previous `check` behavior)
check-ci:
  @just _log_start check-ci
  @just setup
  @just format-no-fix
  @just lint-no-fix
  @just typecheck
  @just lint-imports
  @just public-api
  @just test-strict
  @just metrics-gate
  @just cov
  @just sec-deps
  @just record TAG="ci"
  @just _log_end check-ci

# Canonical entrypoint: dispatch based on MODE
check:
  @just _log_start check
  bash -euo pipefail -c '\
    case "{{MODE}}" in \
      dev)   just check-dev ;; \
      debug) just check-debug ;; \
      ci)    just check-ci ;; \
      *)     echo "[check] ERROR: invalid MODE={{MODE}} (expected: dev|debug|ci)"; exit 2 ;; \
    esac \
  '
  @just _log_end check

# Optional: a convenience alias for full local enforcement without changing MODE
check-full:
  @just _log_start check-full
  MODE=ci just check-ci
  @just _log_end check-full

