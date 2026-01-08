from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

SCOPE_MARKERS = {"unit", "component", "integration", "system", "contract"}


class TestIssue(NamedTuple):
    path: Path
    lineno: int
    kind: str  # "missing_scope" | "wrong_scope"
    message: str


def iter_test_files(root: Path) -> Iterable[Path]:
    tests_root = root / "tests"
    if not tests_root.is_dir():
        return
    yield from tests_root.rglob("test_*.py")


def get_decorator_marker_names(decorator: ast.expr) -> set[str]:
    """
    Extract marker names from a decorator expression.

    Handles patterns like:
    - @pytest.mark.unit
    - @mark.unit
    - @pytest.mark.unit(...)
    - @mark.unit(...)
    """
    names: set[str] = set()

    def extract_from_attr(node: ast.AST) -> None:
        if isinstance(node, ast.Attribute):
            # recurse left first
            extract_from_attr(node.value)
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)

    if isinstance(decorator, ast.Attribute):
        extract_from_attr(decorator)
    elif isinstance(decorator, ast.Call):
        extract_from_attr(decorator.func)

    return names


def infer_expected_scope(path: Path) -> str | None:
    """
    Infer expected scope marker from directory layout.

    Example:
    - tests/unit/... -> "unit"
    - tests/component/... -> "component"
    """
    parts = path.parts
    try:
        tests_idx = parts.index("tests")
    except ValueError:
        return None

    if len(parts) <= tests_idx + 1:
        return None

    subdir = parts[tests_idx + 1]
    if subdir in SCOPE_MARKERS:
        return subdir
    return None


def check_file(path: Path) -> list[TestIssue]:
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(path))

    issues: list[TestIssue] = []
    expected_scope = infer_expected_scope(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            markers: set[str] = set()
            for decorator in node.decorator_list:
                markers |= get_decorator_marker_names(decorator)

            present_scopes = markers & SCOPE_MARKERS
            if not present_scopes:
                issues.append(
                    TestIssue(
                        path,
                        node.lineno,
                        "missing_scope",
                        f"Test '{node.name}' has no scope marker (expected one of: {sorted(SCOPE_MARKERS)})",
                    )
                )
                continue

            if expected_scope is not None and expected_scope not in present_scopes:
                issues.append(
                    TestIssue(
                        path,
                        node.lineno,
                        "wrong_scope",
                        f"Test '{node.name}' in directory '{expected_scope}' "
                        f"should include '@pytest.mark.{expected_scope}' "
                        f"(found: {sorted(present_scopes)})",
                    )
                )

    return issues


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    all_issues: list[TestIssue] = []

    for path in iter_test_files(root):
        all_issues.extend(check_file(path))

    if not all_issues:
        print("Test marker check: OK (all tests have valid scope markers)")
        return 0

    print("Test marker check: found issues:")
    for issue in all_issues:
        rel = issue.path.relative_to(root)
        print(f"  {rel}:{issue.lineno}: {issue.kind}: {issue.message}")

    # Non-zero exit so CI can gate on this
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
