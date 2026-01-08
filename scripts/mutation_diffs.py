from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

import libcst as cst

# Example mutant name:
#   borh.real.x_cmp_real__mutmut_11
_MUTANT_RE = re.compile(r"^(?P<prefix>.+?)\.(?P<func>[^.]+?)__mutmut_(?P<n>\d+)$")
_RESULT_LINE_RE = re.compile(r"^\s*(\S+)\s*:\s*(\S.*\S|\S)\s*$")


@dataclass(frozen=True)
class MutantRef:
    full_name: str
    module_name: str  # e.g. borh.krawczyk
    func_base: str  # e.g. x_krawczyk_contract
    n: int  # e.g. 14


def parse_mutant_name(name: str) -> MutantRef:
    m = _MUTANT_RE.match(name.strip())
    if not m:
        msg = f"Unrecognized mutant name format: {name!r}"
        raise ValueError(msg)
    return MutantRef(
        full_name=name.strip(),
        module_name=m.group("prefix"),
        func_base=m.group("func"),
        n=int(m.group("n")),
    )


def parse_results_lines(text: str) -> list[tuple[str, str]]:
    """
    Parse lines like:
        borh.real.x_cmp_real__mutmut_11: survived.
    Returns (mutant_name, status) pairs.
    """
    out: list[tuple[str, str]] = []
    for line in text.splitlines():
        m = _RESULT_LINE_RE.match(line)
        if m:
            out.append((m.group(1), m.group(2)))
    return out


class _FuncCollector(cst.CSTVisitor):
    def __init__(self) -> None:
        self.funcs: dict[str, cst.FunctionDef] = {}

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self.funcs[node.name.value] = node


def resolve_source_path(module_name: str, src_root: Path) -> Path:
    """
    Map module name to a source file path.
    borh.krawczyk -> src/borh/krawczyk.py (or src/borh/krawczyk/__init__.py).
    """
    rel = Path(*module_name.split("."))
    py = src_root / (str(rel) + ".py")
    if py.exists():
        return py
    pkg_init = src_root / rel / "__init__.py"
    if pkg_init.exists():
        return pkg_init
    return py  # fallback for clearer error later


def resolve_mutants_path(source_rel_to_project: Path, project_root: Path) -> Path:
    """Mutmut stores mutated files under ./mutants mirroring the project layout."""
    return project_root / "mutants" / source_rel_to_project


def extract_original_and_mutant(
    funcs: dict[str, cst.FunctionDef], func_base: str, n: int
) -> tuple[cst.FunctionDef, cst.FunctionDef]:
    mutant_name = f"{func_base}__mutmut_{n}"
    orig_candidates = (f"{func_base}__mutmut_orig", func_base)

    mutant_fn = funcs.get(mutant_name)
    if mutant_fn is None:
        msg = f"Could not find mutant function {mutant_name!r} in mutants module"
        raise KeyError(msg)

    orig_fn: cst.FunctionDef | None = None
    for cand in orig_candidates:
        orig_fn = funcs.get(cand)
        if orig_fn is not None:
            break
    if orig_fn is None:
        msg = f"Could not find original function for base {func_base!r} (tried {orig_candidates})"
        raise KeyError(msg)

    return orig_fn, mutant_fn


def make_unified_diff(*, source_path: Path, orig_code: str, mutant_code: str) -> str:
    path_str = str(source_path)
    return "\n".join(
        unified_diff(
            orig_code.splitlines(),
            mutant_code.splitlines(),
            fromfile=path_str,
            tofile=path_str,
            lineterm="",
        )
    )


def read_results_text(results_file: str) -> str:
    if results_file:
        return Path(results_file).read_text(encoding="utf-8")

    # If no results-file: stdin piped => read stdin; else run `mutmut results`.
    if sys.stdin.isatty():
        import subprocess

        p = subprocess.run(["mutmut", "results"], text=True, capture_output=True, check=False)
        return (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return sys.stdin.read()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status-regex", default="", help='Filter statuses (e.g. "survived|timeout")')
    ap.add_argument("--results-file", default="", help="Read `mutmut results` output from a file.")
    ap.add_argument("--src-root", default="src", help="Source root (default: src)")
    ap.add_argument("--project-root", default=".", help="Project root containing ./mutants (default: .)")
    args = ap.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    src_root = (project_root / args.src_root).resolve()

    text = read_results_text(args.results_file)
    entries = parse_results_lines(text)
    if not entries:
        print("[mutmut-diffs] No mutants parsed from results.", file=sys.stderr)
        return 0

    status_re = re.compile(args.status_regex) if args.status_regex else None
    filtered: list[tuple[str, str]] = [
        (name, status) for (name, status) in entries if (status_re is None or status_re.search(status))
    ]
    if not filtered:
        print(f"[mutmut-diffs] No mutants matched STATUS regex: {args.status_regex!r}", file=sys.stderr)
        return 0

    # Caches for speed: parse each mutants file once, collect functions once.
    source_path_cache: dict[str, Path] = {}  # module_name -> absolute source path
    mutants_parse_cache: dict[Path, tuple[cst.Module, dict[str, cst.FunctionDef]]] = {}
    missing_mutants_files: set[Path] = set()

    total = len(filtered)
    for i, (mutant_name, status) in enumerate(filtered, start=1):
        print()
        print("================================================================")
        print(f"[{i}/{total}] {mutant_name}: {status}")
        print("================================================================")

        try:
            mut = parse_mutant_name(mutant_name)

            source_abs = source_path_cache.get(mut.module_name)
            if source_abs is None:
                source_abs = resolve_source_path(mut.module_name, src_root)
                source_path_cache[mut.module_name] = source_abs

            try:
                source_rel = source_abs.relative_to(project_root)
            except ValueError:
                # If project_root is not an ancestor, still produce a reasonable label.
                source_rel = source_abs

            mutants_path = resolve_mutants_path(source_rel, project_root)

            if mutants_path in missing_mutants_files:
                msg = f"Mutants file not found: {mutants_path} (did you run `mutmut run` in this repo?)"
                raise FileNotFoundError(msg)

            cached = mutants_parse_cache.get(mutants_path)
            if cached is None:
                if not mutants_path.exists():
                    missing_mutants_files.add(mutants_path)
                    msg = f"Mutants file not found: {mutants_path} (did you run `mutmut run` in this repo?)"
                    raise FileNotFoundError(msg)

                module = cst.parse_module(mutants_path.read_text(encoding="utf-8"))
                collector = _FuncCollector()
                module.visit(collector)
                funcs = collector.funcs
                mutants_parse_cache[mutants_path] = (module, funcs)
            else:
                module, funcs = cached

            orig_fn, mutant_fn = extract_original_and_mutant(funcs, mut.func_base, mut.n)

            # Faster than building cst.Module([fn]).code repeatedly.
            orig_code = module.code_for_node(orig_fn).strip()
            mutant_code = module.code_for_node(mutant_fn).strip()

            diff = make_unified_diff(source_path=source_rel, orig_code=orig_code, mutant_code=mutant_code)
            print("\n".join([f"# {mutant_name}: {status}", diff]))

        except Exception as e:
            print(f"[mutmut-diffs] WARN: failed to diff {mutant_name}: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
