from __future__ import annotations

import os
import re
import sys


def main() -> int:
    text = sys.stdin.read()
    m = re.search(r"Mutation score:\s*([0-9.]+)", text)
    if not m:
        print("[mutation-threshold] could not find mutation score in input")
        return 1

    score = float(m.group(1))
    threshold = float(os.environ.get("MUTATION_MIN", "70"))
    print(f"[mutation-threshold] score={score:.1f}%, required>={threshold:.1f}%")
    if score < threshold:
        print("[mutation-threshold] FAILED: mutation score below threshold")
        return 1

    print("[mutation-threshold] PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
