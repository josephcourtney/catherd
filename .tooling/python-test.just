# Shared pytest execution model. Managed by Skellington.

PYTEST_CACHE_DIR := REPO_CACHE_DIR + "/pytest"
PYTEST            := UV + " run pytest -o cache_dir=" + PYTEST_CACHE_DIR
SHOWCOV           := UV + " run showcov"

PYTEST_TIMEOUT       := env("PYTEST_TIMEOUT", "300")
PYTEST_DEV_WORKERS   := env("PYTEST_DEV_WORKERS", "auto")
PYTEST_DEV_DIST      := env("PYTEST_DEV_DIST", "loadscope")
PYTEST_DEV_THRESHOLD := env("PYTEST_DEV_THRESHOLD", "80")

PYTEST_BASE_OPTS      := "--timeout=" + PYTEST_TIMEOUT + " --cov=" + PYTHON_PACKAGE
PYTEST_QUIET_OPTS     := "-q --tb=short -r fE --show-capture=no -o log_cli=false"
PYTEST_DEBUG_OPTS     := "-vv --tb=long -l --show-capture=all -o log_cli=true"
PYTEST_LOG_OPTS       := "-q --tb=short -r fE --show-capture=no -o log_cli=true --log-cli-level=INFO"
PYTEST_FAST_OPTS      := "-m 'not slow' --durations=25 --durations-min=0.1 --timeout=30"
PYTEST_FAILING_OPTS   := "--lf"
PYTEST_DEV_BASE_OPTS  := "--testmon --no-cov"
PYTEST_DEV_XDIST_OPTS := "-n '" + PYTEST_DEV_WORKERS + "' --dist '" + PYTEST_DEV_DIST + "'"

[group('testing')]
[arg("strict", long, value="true")]
[arg("fast", long, value="true")]
[arg("failing", long, value="true")]
[arg("dev", long, value="true")]
[arg("quiet", long, value="quiet")]
[arg("logs", long, value="logs")]
[arg("debug", long, value="debug")]
test strict="true" fast="false" dev="false" quiet="" logs="" debug="" failing="false":
  #!/usr/bin/env bash
  set -euo pipefail
  just _cache_dirs
  mkdir -p "{{PYTEST_CACHE_DIR}}"

  mode_count=0
  [ -n "{{quiet}}" ] && mode_count=$((mode_count + 1))
  [ -n "{{logs}}" ]  && mode_count=$((mode_count + 1))
  [ -n "{{debug}}" ] && mode_count=$((mode_count + 1))
  if [ "$mode_count" -gt 1 ]; then
    echo "test: choose at most one of --quiet, --logs, or --debug" >&2
    exit 2
  fi

  args=({{PYTEST}})
  eval "args+=({{PYTEST_BASE_OPTS}})"
  [ -z "{{quiet}}" ] || eval "args+=({{PYTEST_QUIET_OPTS}})"
  [ -z "{{logs}}" ]  || eval "args+=({{PYTEST_LOG_OPTS}})"
  [ -z "{{debug}}" ] || eval "args+=({{PYTEST_DEBUG_OPTS}})"
  [ "{{fast}}" != "true" ] || eval "args+=({{PYTEST_FAST_OPTS}})"
  [ "{{failing}}" != "true" ] || eval "args+=({{PYTEST_FAILING_OPTS}})"

  if [ "{{dev}}" = "true" ]; then
    eval "args+=({{PYTEST_DEV_BASE_OPTS}})"

    collect_args=(
      {{PYTEST}}
      "--collect-only"
      "-q"
      "--no-cov"
    )
    [ "{{fast}}" != "true" ] || eval "collect_args+=({{PYTEST_FAST_OPTS}})"
    [ "{{failing}}" != "true" ] || eval "collect_args+=({{PYTEST_FAILING_OPTS}})"
    collect_args+=("{{ROOT_DIR}}/{{PY_TESTPATH}}")

    set +e
    collect_out="$("${collect_args[@]}" 2>&1)"
    collect_status=$?
    set -e
    if [ "$collect_status" -ne 0 ] && [ "$collect_status" -ne 5 ]; then
      printf '%s\n' "$collect_out" >&2
      exit "$collect_status"
    fi
    test_count="$(printf '%s\n' "$collect_out" | grep -c '::' || true)"
    if [ "${test_count:-0}" -ge "{{PYTEST_DEV_THRESHOLD}}" ]; then
      eval "args+=({{PYTEST_DEV_XDIST_OPTS}})"
    fi
  fi

  args+=("{{ROOT_DIR}}/{{PY_TESTPATH}}")
  set +e
  "${args[@]}"
  status=$?
  set -e

  if [ "{{strict}}" = "true" ]; then
    exit "$status"
  fi
  [ "$status" -eq 0 ] || echo "test: pytest exited $status (--strict=false)" >&2

[group('test quality')]
[arg("lines", long, value="true")]
cov lines="false":
  #!/usr/bin/env bash
  set -euo pipefail
  if [ "{{lines}}" = "true" ]; then
    {{SHOWCOV}} report --lines --code --context 2
  else
    {{SHOWCOV}} report --summary --no-lines --no-branches
  fi
