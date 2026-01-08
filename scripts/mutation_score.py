"""Summarize Mutmut mutation scores."""

from __future__ import annotations

from collections import Counter
import sys


def main() -> int:
    counter: Counter[str] = Counter()

    for line in sys.stdin.read().splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        status = line.split(":", 1)[-1].strip()
        counter[status] += 1

    killed = counter.get("killed", 0)
    survived = counter.get("survived", 0)
    total = killed + survived
    score = 100.0 * killed / total if total else 0.0

    print(f"Mutation score: {score:.1f}% (killed={killed}, survived={survived}, total={total})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
