from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

RUN_HEADER_RE = re.compile(r"^=== run (\d+) ===")
FAILED_TEST_RE = re.compile(r"FAILED +([^\s]+::[A-Za-z0-9_]+)")


def main() -> int:
    log_path = Path(".flake-log.txt")
    if not log_path.is_file():
        print("[flake-report] no .flake-log.txt; run 'just flake' first")
        return 1

    text = log_path.read_text(encoding="utf-8")

    # Count per-test failures and approximate run count
    failures: Counter[str] = Counter()
    runs_seen: set[int] = set()

    for line in text.splitlines():
        m_run = RUN_HEADER_RE.match(line)
        if m_run:
            runs_seen.add(int(m_run.group(1)))
            continue

        m_fail = FAILED_TEST_RE.search(line)
        if m_fail:
            test_name = m_fail.group(1)
            failures[test_name] += 1

    if not runs_seen:
        print("[flake-report] no run headers found; is .flake-log.txt in expected format?")
        return 1

    total_runs = max(runs_seen)
    if total_runs == 0:
        print("[flake-report] no runs detected")
        return 1

    if not failures:
        print(f"[flake-report] no test failures across {total_runs} runs")
        return 0

    # Assume every test that failed at least once was executed in each run.
    # For more precision, you'd need to parse "collected N items" per run.
    print(f"[flake-report] Detected {len(failures)} tests with at least one failure across {total_runs} runs")
    print()
    print("Per-test flake rates (failures / runs):")
    for test_name, fail_count in failures.most_common():
        flake_rate = fail_count / total_runs * 100.0
        print(f"  {fail_count:3d}/{total_runs:3d} ({flake_rate:5.1f}%)  {test_name}")

    # Global flake rate = total failures / (total_runs * num_tests_with_any_failure)
    total_failures = sum(failures.values())
    approx_total_executions = total_runs * len(failures)
    overall_rate = total_failures / approx_total_executions * 100.0
    print()
    print(
        f"[flake-report] Approx overall flake rate among failing tests: "
        f"{total_failures}/{approx_total_executions} = {overall_rate:.2f}%"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
