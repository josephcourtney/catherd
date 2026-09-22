# Shared Python distribution operations. Managed by Skellington.

PACKAGE_IMPORT := env("PACKAGE_IMPORT", "catherd")
CLI_SMOKE      := env("CLI_SMOKE", "catherd --help")

[group('production')]
build:
  {{UV}} build

[group('production')]
build-release:
  rm -rf dist
  {{UV}} build --no-sources

[group('production')]
publish:
  {{UV}} publish

[group('production')]
release-smoke:
  #!/usr/bin/env bash
  set -euo pipefail
  wheels=(dist/*.whl)
  if [ "${#wheels[@]}" -ne 1 ] || [ ! -f "${wheels[0]}" ]; then
    echo "release-smoke: expected exactly one wheel in dist/" >&2
    exit 1
  fi

  smoke_dir="{{REPO_CACHE_DIR}}/release-smoke"
  rm -rf "$smoke_dir"
  {{UV}} venv "$smoke_dir"
  {{UV}} pip install --python "$smoke_dir/bin/python" "${wheels[0]}"
  "$smoke_dir/bin/python" -c "import {{PACKAGE_IMPORT}}"

  if [ -n "{{CLI_SMOKE}}" ]; then
    PATH="$smoke_dir/bin:$PATH" bash -c "{{CLI_SMOKE}}"
  fi
