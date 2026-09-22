# Shared generic Just machinery. Managed by Skellington.

set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := true
set export := true

MODE     := env("MODE", "dev")
ROOT_DIR := justfile_directory()
VERBOSE  := env("VERBOSE", "0")

REPO_CACHE_DIR := ROOT_DIR + "/.cache"

[group('meta')]
help:
  @just --list --unsorted --list-prefix "  "

[private]
_log_start NAME:
  @if [ "{{VERBOSE}}" != "0" ]; then printf "\n=== START: %s ===\n" "{{NAME}}"; fi

[private]
_log_end NAME:
  @if [ "{{VERBOSE}}" != "0" ]; then printf "=== END: %s ===\n\n" "{{NAME}}"; fi

[private]
_cache_dirs:
  @mkdir -p "{{REPO_CACHE_DIR}}"

[private]
_run NAME CMD:
  #!/usr/bin/env bash
  set -euo pipefail
  set +e
  out="$(bash -c "$CMD" 2>&1)"
  status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    printf '\033[1;32m✓ %s\033[0m\n' "$NAME"
  else
    printf '\033[1;31m✗ %s\033[0m\n' "$NAME"
    printf '%s\n' "$out"
    exit "$status"
  fi

# Best-effort runner used only by repair workflows.
[private]
_run_soft NAME CMD:
  #!/usr/bin/env bash
  set -uo pipefail
  set +e
  out="$(bash -c "$CMD" 2>&1)"
  status=$?
  set -e
  if [ "$status" -eq 0 ]; then
    printf '\033[1;32m✓ %s\033[0m\n' "$NAME"
  else
    printf '\033[1;31m✗ %s\033[0m\n' "$NAME"
    printf '%s\n' "$out"
  fi
  exit 0

[group('maintenance')]
stash-untracked:
  #!/usr/bin/env bash
  set -euo pipefail
  files=()
  while IFS= read -r -d '' file; do
    files+=("$file")
  done < <(git ls-files --others --exclude-standard -z)

  if [ "${#files[@]}" -eq 0 ]; then
    echo "No untracked non-ignored files to stash."
    exit 0
  fi

  msg="scour:untracked:$(date -u +%Y%m%dT%H%M%SZ)"
  git stash push --include-untracked -m "$msg" -- "${files[@]}" >/dev/null

[group('meta')]
tooling-root:
  @printf '%s\n' "{{ROOT_DIR}}"
