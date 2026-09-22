# Shared Python environment and quality operations. Managed by Skellington.

PYTHON_PACKAGE := env("PYTHON_PACKAGE", "catherd")

UV_CACHE_DIR            := REPO_CACHE_DIR + "/uv"
RUFF_CACHE_DIR          := REPO_CACHE_DIR + "/ruff"
IMPORT_LINTER_CACHE_DIR := REPO_CACHE_DIR + "/import-linter"

PY_SRC      := env("PY_SRC", "src")
PY_TESTPATH := env("PY_TESTPATH", "tests")
PY_SCRIPTS  := env("PY_SCRIPTS", "scripts")

UV                   := "uv --cache-dir " + UV_CACHE_DIR
PYTHON               := UV + " run python"
RUFF                 := UV + " run ruff"
RUFF_LINT            := RUFF + " check --cache-dir " + RUFF_CACHE_DIR
RUFF_FORMAT          := RUFF + " format --cache-dir " + RUFF_CACHE_DIR
TY                   := UV + " run ty"
VULTURE              := UV + " run vulture"
RADON                 := UV + " run radon"
IMPORT_LINTER        := UV + " run lint-imports --cache-dir " + IMPORT_LINTER_CACHE_DIR
IMPORT_LINTER_CONFIG := ROOT_DIR + "/import-linter.toml"
JSCPD                 := "npx --yes jscpd@4.0"
PYPROJECT_TOOLING     := UV + " run " + ROOT_DIR + "/.tooling/pyproject-tooling.py"

[private]
_python_cache_dirs:
  @mkdir -p "{{UV_CACHE_DIR}}" "{{RUFF_CACHE_DIR}}" "{{IMPORT_LINTER_CACHE_DIR}}"

[group('environment')]
tooling-check:
  {{PYPROJECT_TOOLING}} check

[group('environment')]
tooling-sync:
  just sync

[group('environment')]
sync:
  {{PYPROJECT_TOOLING}} sync
  just _sync_environment

[private]
_sync_environment:
  #!/usr/bin/env bash
  set -euo pipefail
  just _python_cache_dirs
  stamp=".venv/.sync-state"
  sync_arg=""

  if grep -Eq '^[[:space:]]*\[tool\.uv\.workspace\][[:space:]]*(#.*)?$' pyproject.toml; then
    sync_arg="--all-packages"
  fi

  fingerprint() {
    {
      printf '%s\n' "uv-sync-arg=$sync_arg"
      for file in pyproject.toml uv.lock uv.toml .python-version; do
        [[ ! -f "$file" ]] || cat "$file"
      done
      git ls-files '*pyproject.toml' | LC_ALL=C sort | while IFS= read -r file; do
        [[ "$file" == "pyproject.toml" ]] || cat "$file"
      done
    } | shasum -a 256 | cut -d' ' -f1
  }

  current="$(fingerprint)"
  if [[ -d .venv && -f "$stamp" && "$(cat "$stamp")" == "$current" ]]; then
    echo "already up to date."
    exit 0
  fi

  if [ -n "$sync_arg" ]; then
    {{UV}} sync "$sync_arg"
  else
    {{UV}} sync
  fi
  mkdir -p .venv
  fingerprint > "$stamp"

[group('environment')]
upgrade:
  {{UV}} lock --upgrade
  {{UV}} sync

[group('environment')]
upgrade-package package:
  {{UV}} lock --upgrade-package {{package}}
  rm -f .venv/.sync-state
  just sync

[group('code quality')]
syntax:
  #!/usr/bin/env bash
  set -euo pipefail
  for path in "{{PY_SRC}}" "{{PY_TESTPATH}}" "{{PY_SCRIPTS}}"; do
    [[ -e "$path" ]] || continue
    {{PYTHON}} -m compileall -q "$path"
  done

[group('code quality')]
[arg("no-fix", long, value="true")]
lint no-fix="false":
  #!/usr/bin/env bash
  set -euo pipefail
  just _python_cache_dirs
  args=({{RUFF_LINT}})
  [[ "{{no-fix}}" != "true" ]] || args+=(--no-fix)
  for path in "{{PY_SRC}}" "{{PY_TESTPATH}}" "{{PY_SCRIPTS}}"; do
    [[ -e "$path" ]] && args+=("$path")
  done
  "${args[@]}"

[group('code quality')]
[arg("check", long, value="true")]
format check="false":
  #!/usr/bin/env bash
  set -euo pipefail
  just _python_cache_dirs
  args=({{RUFF_FORMAT}})
  [[ "{{check}}" != "true" ]] || args+=(--check)
  for path in "{{PY_SRC}}" "{{PY_TESTPATH}}" "{{PY_SCRIPTS}}"; do
    [[ -e "$path" ]] && args+=("$path")
  done
  "${args[@]}"

[group('code quality')]
lint-imports:
  #!/usr/bin/env bash
  set -euo pipefail
  if [ ! -f "{{IMPORT_LINTER_CONFIG}}" ]; then
    echo "lint-imports: no import-linter.toml; skipping"
    exit 0
  fi
  {{IMPORT_LINTER}} --verbose --config "{{IMPORT_LINTER_CONFIG}}"

[group('code quality')]
typecheck:
  #!/usr/bin/env bash
  set -euo pipefail
  paths=()
  for path in "{{PY_SRC}}" "{{PY_TESTPATH}}" "{{PY_SCRIPTS}}"; do
    [[ -e "$path" ]] && paths+=("$path")
  done
  if {{TY}} --version >/dev/null 2>&1; then
    {{TY}} check "${paths[@]}"
  elif [ "{{MODE}}" = "ci" ]; then
    echo "typecheck: ty is not available; run just sync" >&2
    exit 1
  else
    echo "typecheck: ty is not available; skipping outside CI"
  fi

[group('code quality')]
dead-code:
  {{VULTURE}} --min-confidence 61 {{PY_SRC}} {{PY_TESTPATH}} {{PY_SCRIPTS}}

[group('code quality')]
[arg("raw", long, value="true")]
[arg("strict", long, value="true")]
complexity raw="false" strict="false" min_complexity="11":
  #!/usr/bin/env bash
  set -euo pipefail
  if [ "{{raw}}" = "true" ] && [ "{{strict}}" = "true" ]; then
    echo "choose at most one of --raw or --strict" >&2
    exit 2
  fi
  if [ "{{raw}}" = "true" ]; then
    {{RADON}} raw "{{PY_SRC}}"
  elif [ "{{strict}}" = "true" ]; then
    output="$({{RADON}} cc -s -n "{{min_complexity}}" "{{PY_SRC}}" || true)"
    if [ -n "$output" ]; then
      echo "$output"
      exit 1
    fi
  else
    {{RADON}} cc -s -a "{{PY_SRC}}"
  fi

[group('code quality')]
dup:
  #!/usr/bin/env bash
  set -euo pipefail
  paths=()
  for path in "{{PY_SRC}}" "{{PY_TESTPATH}}" "{{PY_SCRIPTS}}"; do
    [[ -e "$path" ]] && paths+=("$path")
  done
  if [ "${#paths[@]}" -eq 0 ]; then
    echo "dup: no Python source directories found; skipping"
    exit 0
  fi
  {{JSCPD}} --pattern "**/*.py" --reporters console "${paths[@]}"

[group('security')]
secrets:
  #!/usr/bin/env bash
  set -euo pipefail
  if command -v trufflehog >/dev/null 2>&1; then
    tmp_file="$(mktemp)"
    trap 'rm -f "$tmp_file"' EXIT
    printf ".venv\n.cache\nbuild\ndist\n" > "$tmp_file"
    trufflehog filesystem . --exclude-paths "$tmp_file"
  else
    echo "secrets: trufflehog not found; skipping"
  fi

[group('security')]
sec-deps:
  #!/usr/bin/env bash
  set -euo pipefail
  if [ ! -x "{{ROOT_DIR}}/.venv/bin/pip-audit" ]; then
    echo "sec-deps: pip-audit not found; run just sync" >&2
    exit 1
  fi
  PIP_NO_CACHE_DIR=1 "{{ROOT_DIR}}/.venv/bin/pip-audit"

[group('cleaning')]
clean:
  #!/usr/bin/env bash
  set -euo pipefail
  find . -path './.venv' -prune -o -name '__pycache__' -type d -prune -exec rm -rf '{}' +
  rm -rf .cache .ruff_cache .pytest_cache .mypy_cache .pytype \
    .import_linter_cache .coverage .coverage.* coverage.xml .coverage.xml \
    htmlcov .hypothesis mutants dist build

[group('cleaning')]
scour:
  just clean
  just stash-untracked
  git clean -fXd -e .venv/
