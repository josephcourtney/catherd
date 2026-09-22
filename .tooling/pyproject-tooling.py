# /// script
# requires-python = ">=3.12"
# dependencies = ["packaging==26.3", "tomlkit==0.13.3"]
# ///

"""Reconcile the pyproject.toml entries owned by Skellington.

This script deliberately owns a narrow whitelist. It preserves project metadata,
runtime dependencies, local tool configuration, and extra development
dependencies.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import tomlkit
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import Version
from tomlkit.items import Array, Table

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

REQUIRED_DEV_DEPENDENCIES = (
    "coverage>=7.13.4",
    "import-linter>=2.10",
    "pip-audit>=2.10.1",
    "pytest>=9.0.2",
    "pytest-cov>=7.0.0",
    "pytest-testmon>=2.2.0",
    "pytest-timeout>=2.4.0",
    "pytest-xdist>=3.8.0",
    "radon>=6.0.1",
    "ruff>=0.15.2",
    "rust-just>=1.46.0",
    "showcov>=0.3.5",
    "ty>=0.0.17",
    "vulture>=2.14",
)

RUFF_EXTEND = "./ruff.default.toml"
RUFF_TARGET = "py312"
RUFF_LINE_LENGTH = 120
PYTHON_MIN = "3.12"
SHOWCOV_SOURCE = {
    "git": "https://github.com/josephcourtney/showcov.git",
    "rev": "db8a535b5cb5e36a3557f6559fa15f3cd7f20c0a",
}

_NAME_RE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def requirement_name(requirement: str) -> str:
    """Return a PEP 503-style normalized distribution name."""
    match = _NAME_RE.match(requirement)
    if match is None:
        return requirement.strip().lower()
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def ensure_table(parent, key: str) -> Table:
    existing = parent.get(key)
    if isinstance(existing, Table):
        return existing
    value = tomlkit.table()
    parent[key] = value
    return value


def ensure_array(parent, key: str) -> Array:
    existing = parent.get(key)
    if isinstance(existing, Array):
        return existing
    value = tomlkit.array().multiline(True)
    parent[key] = value
    return value


def declared_python_minor(doc) -> str | None:
    """Return the lowest Python minor admitted by project.requires-python."""
    project = doc.get("project")
    if not isinstance(project, Table):
        return None
    raw = project.get("requires-python")
    if not isinstance(raw, str):
        return None

    try:
        spec = SpecifierSet(raw)
    except InvalidSpecifier:
        return None

    for minor in range(8, 16):
        base = Version(f"3.{minor}")
        late_patch = Version(f"3.{minor}.999")
        if base in spec or late_patch in spec:
            return f"3.{minor}"
    return None


def collect_project_conflicts(doc) -> list[str]:
    """Report project-owned policy that conflicts with template answers."""
    declared = declared_python_minor(doc)
    if declared is not None and declared != PYTHON_MIN:
        return [
            "project.requires-python implies minimum "
            f"{declared}, but Skellington python_min is {PYTHON_MIN}; "
            "rerun Copier with the project minimum"
        ]
    return []


def collect_drift(doc) -> list[str]:
    """Describe only drift in entries Skellington owns."""
    drift: list[str] = collect_project_conflicts(doc)


    groups = doc.get("dependency-groups")
    dev = groups.get("dev") if isinstance(groups, Table) else None
    names = (
        {requirement_name(str(item)) for item in dev}
        if isinstance(dev, Array)
        else set()
    )
    for requirement in REQUIRED_DEV_DEPENDENCIES:
        if requirement_name(requirement) not in names:
            drift.append(f"dependency-groups.dev is missing {requirement!r}")

    tool = doc.get("tool")
    ruff = tool.get("ruff") if isinstance(tool, Table) else None
    if not isinstance(ruff, Table) or ruff.get("extend") != RUFF_EXTEND:
        drift.append(f"tool.ruff.extend must be {RUFF_EXTEND!r}")
    if isinstance(ruff, Table):
        if "target-version" in ruff:
            drift.append(
                "tool.ruff.target-version overrides the managed Ruff baseline "
                f"({RUFF_TARGET})"
            )
        if "line-length" in ruff:
            drift.append(
                "tool.ruff.line-length overrides the managed Ruff baseline "
                f"({RUFF_LINE_LENGTH})"
            )
        lint = ruff.get("lint")
        if isinstance(lint, Table) and "select" in lint:
            drift.append(
                "tool.ruff.lint.select overrides the managed Ruff baseline; "
                "it will be migrated to extend-select"
            )

    uv = tool.get("uv") if isinstance(tool, Table) else None
    sources = uv.get("sources") if isinstance(uv, Table) else None
    if not isinstance(sources, Table) or "showcov" not in sources:
        drift.append("tool.uv.sources.showcov is missing")

    return drift


def reconcile(doc) -> None:
    """Add or repair only the pyproject entries owned by Skellington."""

    groups = ensure_table(doc, "dependency-groups")
    dev = ensure_array(groups, "dev")
    dev_names = {requirement_name(str(item)) for item in dev}
    for requirement in REQUIRED_DEV_DEPENDENCIES:
        name = requirement_name(requirement)
        if name not in dev_names:
            dev.append(requirement)
            dev_names.add(name)

    tool = ensure_table(doc, "tool")
    ruff = ensure_table(tool, "ruff")
    ruff["extend"] = RUFF_EXTEND
    ruff.pop("target-version", None)
    ruff.pop("line-length", None)

    lint = ruff.get("lint")
    if isinstance(lint, Table) and "select" in lint:
        selected = lint.pop("select")
        if isinstance(selected, Array):
            existing = lint.get("extend-select")
            if not isinstance(existing, Array):
                existing = tomlkit.array()
                lint["extend-select"] = existing
            present = {str(item) for item in existing}
            for item in selected:
                value = str(item)
                if value not in present:
                    existing.append(value)
                    present.add(value)

    uv = ensure_table(tool, "uv")
    sources = ensure_table(uv, "sources")
    if "showcov" not in sources:
        source = tomlkit.inline_table()
        for key, value in SHOWCOV_SOURCE.items():
            source[key] = value
        sources["showcov"] = source


def load():
    if not PYPROJECT.exists():
        raise SystemExit(f"tooling: {PYPROJECT} not found")
    return tomlkit.parse(PYPROJECT.read_text())


def check() -> int:
    doc = load()
    conflicts = collect_project_conflicts(doc)
    if conflicts:
        print("tooling: project policy conflicts with Skellington answers:", file=sys.stderr)
        for item in conflicts:
            print(f"  - {item}", file=sys.stderr)
        return 1

    drift = collect_drift(doc)
    if not drift:
        print("tooling: pyproject.toml is in sync")
        return 0

    print("tooling: pyproject.toml differs from Skellington policy:", file=sys.stderr)
    for item in drift:
        print(f"  - {item}", file=sys.stderr)
    print("run `just tooling-sync` to reconcile managed entries", file=sys.stderr)
    return 1


def sync() -> int:
    doc = load()
    conflicts = collect_project_conflicts(doc)
    if conflicts:
        print("tooling: project policy conflicts with Skellington answers:", file=sys.stderr)
        for item in conflicts:
            print(f"  - {item}", file=sys.stderr)
        return 1

    before = tomlkit.dumps(doc)
    reconcile(doc)
    after = tomlkit.dumps(doc)

    if before == after:
        print("tooling: pyproject.toml already in sync")
        return 0

    PYPROJECT.write_text(after)
    print("tooling: reconciled pyproject.toml")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile Skellington-owned pyproject.toml entries."
    )
    parser.add_argument("command", choices=("check", "sync"))
    args = parser.parse_args()
    return check() if args.command == "check" else sync()


if __name__ == "__main__":
    raise SystemExit(main())
