from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable


@dataclass
class ToolSpec:
    name: str
    cmd: list[str]
    min_version: str | None  # semantic-ish string, or None for presence-only
    version_regex: str  # regex with one capturing group for version string


TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="trufflehog",
        cmd=["trufflehog", "--version"],
        min_version="3.78.0",
        # e.g. "trufflehog 3.78.0"
        version_regex=r"trufflehog\s+(\d+\.\d+\.\d+)",
    ),
    ToolSpec(
        name="pip-audit",
        cmd=["pip-audit", "--version"],
        min_version="2.7.0",
        version_regex=r"pip-audit\s+(\d+\.\d+\.\d+)",
    ),
    # add more tools here as needed
]


def parse_version(s: str) -> tuple[int, ...]:
    parts = re.split(r"[^\d]+", s.strip())
    ints = [int(p) for p in parts if p.isdigit()]
    return tuple(ints)


def check_tool(spec: ToolSpec) -> tuple[bool, str]:
    # Presence
    if shutil.which(spec.cmd[0]) is None:
        return False, f"{spec.name}: not found on PATH"

    try:
        proc = subprocess.run(
            spec.cmd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except OSError as exc:
        return False, f"{spec.name}: failed to invoke: {exc!r}"

    output = proc.stdout.strip()
    m = re.search(spec.version_regex, output)
    if not m:
        return False, f"{spec.name}: could not parse version from output: {output!r}"

    found_version = m.group(1)
    if spec.min_version is None:
        return True, f"{spec.name}: found version {found_version}"

    found_tuple = parse_version(found_version)
    min_tuple = parse_version(spec.min_version)

    if found_tuple < min_tuple:
        return False, (
            f"{spec.name}: version {found_version} < required {spec.min_version} (output: {output!r})"
        )

    return True, f"{spec.name}: OK (version {found_version} >= {spec.min_version})"


def main() -> int:
    failures = 0
    for spec in TOOLS:
        ok, msg = check_tool(spec)
        print(msg)
        if not ok:
            failures += 1

    if failures:
        print(f"[check-tools] FAILED: {failures} tool(s) missing or outdated")
        return 1

    print("[check-tools] All required tools present and meet minimum versions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
