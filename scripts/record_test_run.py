from __future__ import annotations

import argparse
import contextlib
import json
import operator
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# ----------------------------
# Small utilities
# ----------------------------


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def copy_file(src: Path, dst: Path) -> None:
    safe_mkdir(dst.parent)
    shutil.copy2(src, dst)


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def first_existing_file(repo_root: Path, rel_candidates: list[str]) -> Path | None:
    for rel in rel_candidates:
        p = repo_root / rel
        if p.is_file():
            return p
    return None


def first_existing_dir(repo_root: Path, rel_candidates: list[str]) -> Path | None:
    for rel in rel_candidates:
        p = repo_root / rel
        if p.is_dir():
            return p
    return None


def read_text_if_exists(p: Path) -> str | None:
    if p.is_file():
        return p.read_text(encoding="utf-8", errors="replace")
    return None


# ----------------------------
# Git + environment metadata
# ----------------------------


def _run_git(repo_root: Path, args: list[str]) -> str:
    p = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(p.stdout.strip())
    return p.stdout.strip()


def git_info(repo_root: Path) -> dict[str, Any]:
    info: dict[str, Any] = {}
    try:
        info["sha"] = _run_git(repo_root, ["rev-parse", "HEAD"])
        info["branch"] = _run_git(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        info["is_dirty"] = bool(_run_git(repo_root, ["status", "--porcelain"]))
        info["describe"] = _run_git(repo_root, ["describe", "--always", "--dirty", "--tags"])
    except Exception as e:
        info["git_error"] = str(e)
    return info


def env_fingerprint() -> dict[str, Any]:
    return {
        "python": {
            "version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    }


# ----------------------------
# Parsing (best-effort)
# ----------------------------


def parse_junit_xml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}

    tree = ET.parse(path)
    root = tree.getroot()

    suites: list[ET.Element]
    if root.tag == "testsuite":
        suites = [root]
    elif root.tag == "testsuites":
        suites = [x for x in root.findall("testsuite")]
    else:
        suites = [root]

    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "time_s": 0.0}
    testcases: list[dict[str, Any]] = []

    for s in suites:
        totals["tests"] += int(s.attrib.get("tests", "0"))
        totals["failures"] += int(s.attrib.get("failures", "0"))
        totals["errors"] += int(s.attrib.get("errors", "0"))
        totals["skipped"] += int(s.attrib.get("skipped", "0"))
        with contextlib.suppress(ValueError):
            totals["time_s"] += float(s.attrib.get("time", "0") or 0.0)

        for tc in s.findall("testcase"):
            classname = tc.attrib.get("classname", "")
            name = tc.attrib.get("name", "")
            nodeid = f"{classname}::{name}" if classname else name
            try:
                dur = float(tc.attrib.get("time", "0") or 0.0)
            except ValueError:
                dur = None

            outcome = "passed"
            if tc.find("failure") is not None:
                outcome = "failed"
            elif tc.find("error") is not None:
                outcome = "error"
            elif tc.find("skipped") is not None:
                outcome = "skipped"

            testcases.append({"nodeid": nodeid, "outcome": outcome, "duration_s": dur})

    slowest = sorted(
        [t for t in testcases if isinstance(t.get("duration_s"), (int, float))],
        key=operator.itemgetter("duration_s"),  # type: ignore[index]
        reverse=True,
    )[:25]

    return {"present": True, "totals": totals, "slowest": slowest}


def parse_pytest_json_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"present": True, "parse_error": str(e)}

    summary = data.get("summary", {}) or {}
    tests = data.get("tests", []) or []

    norm_tests: list[dict[str, Any]] = []
    for t in tests:
        nodeid = t.get("nodeid")
        if not nodeid:
            continue
        norm_tests.append({
            "nodeid": nodeid,
            "outcome": t.get("outcome"),
            "duration_s": t.get("duration"),
        })

    return {
        "present": True,
        "summary": {
            "passed": summary.get("passed", 0),
            "failed": summary.get("failed", 0),
            "skipped": summary.get("skipped", 0),
            "xfailed": summary.get("xfailed", 0),
            "xpassed": summary.get("xpassed", 0),
            "errors": summary.get("errors", 0),
            "total": summary.get("total", len(norm_tests)),
            "duration_s": summary.get("duration", None),
        },
        "tests": norm_tests,
    }


def parse_coverage_xml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except Exception as e:
        return {"present": True, "parse_error": str(e)}

    def get_float_attr(k: str) -> float | None:
        v = root.attrib.get(k)
        if v is None:
            return None
        try:
            return float(v)
        except ValueError:
            return None

    line_rate = get_float_attr("line-rate")
    branch_rate = get_float_attr("branch-rate")

    out: dict[str, Any] = {"present": True}
    if line_rate is not None:
        out["line_coverage_pct"] = 100.0 * line_rate
    if branch_rate is not None:
        out["branch_coverage_pct"] = 100.0 * branch_rate
    return out


def parse_mutation_score_text(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"present": False}
    import re

    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r"Mutation score:\s*([0-9.]+)%", text)
    if not m:
        return {"present": True, "parse_error": "could not find 'Mutation score: X%'"}
    return {"present": True, "mutation_score_pct": float(m.group(1))}


def parse_perf_results(dirpath: Path) -> dict[str, Any]:
    if not dirpath.is_dir():
        return {"present": False}

    results: list[dict[str, Any]] = []
    for p in sorted(dirpath.glob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        results.append({"name": obj.get("name", p.stem), "latency_ms": obj.get("latency_ms")})
    return {"present": True, "results": results}


def parse_flake_log(path: Path) -> dict[str, Any]:
    """
    Very lightweight: count FAILED occurrences; your scripts/flake_report.py does more,
    but here we just store basics + preserve raw log as artifact.
    """
    if not path.is_file():
        return {"present": False}

    text = path.read_text(encoding="utf-8", errors="replace")
    failed_lines = [ln for ln in text.splitlines() if "FAILED" in ln]
    return {"present": True, "failed_line_count": len(failed_lines)}


# ----------------------------
# Canonical artifact bundle
# ----------------------------


@dataclass(frozen=True)
class BundlePaths:
    bundle_root: Path
    junit_xml: Path
    pytest_json: Path
    coverage_xml: Path
    mutation_score_txt: Path
    flake_log: Path
    perf_dir: Path


def make_bundle_paths(repo_root: Path, run_id: str) -> BundlePaths:
    root = repo_root / ".artifacts" / run_id
    return BundlePaths(
        bundle_root=root,
        junit_xml=root / "pytest-junit.xml",
        pytest_json=root / "pytest-report.json",
        coverage_xml=root / "coverage.xml",
        mutation_score_txt=root / "mutation-score.txt",
        flake_log=root / "flake-log.txt",
        perf_dir=root / "perf_results",
    )


# ----------------------------
# Recording
# ----------------------------


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    safe_mkdir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", default=".", help="Repository root")
    ap.add_argument("--tag", default="local", help="Tag for this run (ci-pr, ci-nightly, local, etc.)")
    ap.add_argument("--out", default=".records/test_runs.jsonl", help="Append-only JSONL output")
    ap.add_argument("--run-id", default="", help="Override run id (default: utc timestamp + short sha)")
    ap.add_argument("--copy-perf", action="store_true", help="Copy .perf_results into the bundle if present")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()

    git = git_info(repo_root)
    short_sha = (git.get("sha") or "nogit")[:12]
    run_id = args.run_id or f"{utc_now_iso().replace(':', '').replace('-', '')}_{short_sha}"

    bundle = make_bundle_paths(repo_root, run_id)
    safe_mkdir(bundle.bundle_root)

    # ---------
    # Discover artifact producers' outputs (best-effort)
    #
    # You control these producers via your existing just recipes; this script only finds/copies.
    # ---------

    junit_src = first_existing_file(
        repo_root,
        [
            ".artifacts/pytest-junit.xml",
            "pytest-junit.xml",
            "junit.xml",
            ".pytest-junit.xml",
        ],
    )

    pytest_json_src = first_existing_file(
        repo_root,
        [
            ".artifacts/pytest-report.json",
            "pytest-report.json",
            ".pytest-report.json",
            ".report.json",
        ],
    )

    # Your coverage.xml is configured as ".coverage.xml"
    coverage_src = first_existing_file(
        repo_root,
        [
            ".coverage.xml",
            "coverage.xml",
            ".artifacts/coverage.xml",
        ],
    )

    # Mutation: allow several common locations (you can standardize later)
    mutation_src = first_existing_file(
        repo_root,
        [
            ".mutation-score.txt",
            ".artifacts/mutation-score.txt",
            "mutation-score.txt",
        ],
    )

    flake_log_src = first_existing_file(
        repo_root,
        [
            ".flake-log.txt",
            ".artifacts/flake-log.txt",
        ],
    )

    perf_src_dir = first_existing_dir(
        repo_root,
        [
            ".perf_results",
            ".artifacts/perf_results",
        ],
    )

    # ---------
    # Copy into canonical bundle
    # ---------
    if junit_src:
        copy_file(junit_src, bundle.junit_xml)
    if pytest_json_src:
        copy_file(pytest_json_src, bundle.pytest_json)
    if coverage_src:
        copy_file(coverage_src, bundle.coverage_xml)
    if mutation_src:
        copy_file(mutation_src, bundle.mutation_score_txt)
    if flake_log_src:
        copy_file(flake_log_src, bundle.flake_log)
    if args.copy_perf and perf_src_dir:
        copy_tree(perf_src_dir, bundle.perf_dir)

    # ---------
    # Parse canonical bundle (best-effort)
    # ---------
    record: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "timestamp_utc": utc_now_iso(),
        "tag": args.tag,
        "git": git,
        "env": env_fingerprint(),
        "bundle": {
            "root": str(bundle.bundle_root.relative_to(repo_root)),
            "pytest_junit": str(bundle.junit_xml.relative_to(repo_root))
            if bundle.junit_xml.exists()
            else None,
            "pytest_json": str(bundle.pytest_json.relative_to(repo_root))
            if bundle.pytest_json.exists()
            else None,
            "coverage_xml": str(bundle.coverage_xml.relative_to(repo_root))
            if bundle.coverage_xml.exists()
            else None,
            "mutation_score_txt": str(bundle.mutation_score_txt.relative_to(repo_root))
            if bundle.mutation_score_txt.exists()
            else None,
            "flake_log": str(bundle.flake_log.relative_to(repo_root)) if bundle.flake_log.exists() else None,
            "perf_dir": str(bundle.perf_dir.relative_to(repo_root)) if bundle.perf_dir.exists() else None,
        },
        "junit": parse_junit_xml(bundle.junit_xml),
        "pytest_json_report": parse_pytest_json_report(bundle.pytest_json),
        "coverage": parse_coverage_xml(bundle.coverage_xml),
        "mutation": parse_mutation_score_text(bundle.mutation_score_txt),
        "flake": parse_flake_log(bundle.flake_log),
        "perf": parse_perf_results(
            bundle.perf_dir if bundle.perf_dir.exists() else (perf_src_dir or Path("/dev/null"))
        ),
    }

    out_path = (repo_root / args.out).resolve()
    append_jsonl(out_path, record)

    latest_path = out_path.with_name("latest.json")
    latest_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(f"[record-run] run_id:  {run_id}")
    print(f"[record-run] bundle:  {bundle.bundle_root}")
    print(f"[record-run] appended: {out_path}")
    print(f"[record-run] wrote:    {latest_path}")

    # collector never fails the build; it records what exists
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
