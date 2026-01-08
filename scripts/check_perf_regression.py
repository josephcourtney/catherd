from __future__ import annotations

import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    results_dir = root / ".perf_results"
    baseline_dir = root / "tests" / "perf_baseline"

    if not results_dir.is_dir():
        print("[perf] no .perf_results directory; did you run performance tests?")
        return 1

    failures = 0

    for baseline_path in baseline_dir.glob("*.json"):
        baseline = load_json(baseline_path)
        name = baseline["name"]
        baseline_ms = float(baseline["latency_ms"])
        max_reg_pct = float(baseline.get("max_regression_pct", 10.0))

        result_path = results_dir / f"{name}.json"
        if not result_path.is_file():
            print(f"[perf] missing runtime result for '{name}'")
            failures += 1
            continue

        result = load_json(result_path)
        current_ms = float(result["latency_ms"])

        if baseline_ms <= 0:
            print(f"[perf] baseline for '{name}' is non-positive; skipping regression check")
            continue

        regression_pct = (current_ms - baseline_ms) / baseline_ms * 100.0
        print(
            f"[perf] {name}: baseline={baseline_ms:.2f} ms, "
            f"current={current_ms:.2f} ms, delta={regression_pct:+.1f}%"
        )

        if regression_pct > max_reg_pct:
            print(
                f"[perf] ERROR: '{name}' regression {regression_pct:.1f}% exceeds allowed {max_reg_pct:.1f}%"
            )
            failures += 1

    if failures:
        print(f"[perf] Performance regression check FAILED ({failures} issues)")
        return 1

    print("[perf] Performance regression check PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
