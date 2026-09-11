"""Wrapper giving pyccel an xp2f.py-style --compile/--run/--run-both CLI.

pyccel's own `compile` subcommand always ends in something meant to be
`import`ed back into a running Python process (a `.pyd`/`.so` extension
module) -- there is no `program` unit in what it generates, so there's
no way to get a freestanding native executable straight from pyccel.

But `pyccel compile FILE --convert-only` (which stops right after
translation, skipping pyccel's own Python-extension build machinery)
produces a plain Fortran module with a predictable shape: `module
<stem>` with a `<stem>__init()` subroutine holding the script's own
top-level statements (guarded by an `initialised` flag, mirroring
Python's own "only run a module's top level once" semantics). A tiny,
generic 4-line `program` stub that `use`s that module and calls its
`__init` is enough to link a genuine standalone executable -- verified
directly against pyccel's real output for both a pure-integer/recursive
script and a numpy/float-based one.

Scope: resolves ONE level of local sibling imports (matching what
xp2f.py's own sibling-inlining already handles for the examples in this
project) -- pyccel requires each imported local module to be pyccelized
separately, before the script that imports it, which this wrapper does
automatically; it does not walk transitive (sibling-of-sibling) imports.

Note: pyccel names its own output directory `__pyccel__` + whatever
`PYTEST_XDIST_WORKER` is set to (`pyccel/codegen/pipeline.py`'s own
`pyccel_dirname = '__pyccel__' + os.environ.get('PYTEST_XDIST_WORKER',
'')`) -- a deliberate pyccel feature so ITS OWN test suite is safe under
pytest-xdist. That environment variable is inherited by any subprocess,
so a `pyccel_wrap.py` process spawned from inside an xdist worker (e.g.
by this project's own tests/test_pyccel_wrap.py) sees a directory named
`__pyccel__gw0`, not `__pyccel__` -- this module computes the same name
pyccel itself would, rather than hardcoding the plain form.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

_PYCCEL_DIRNAME = "__pyccel__" + os.environ.get("PYTEST_XDIST_WORKER", "")

_DEFAULT_FLAGS = ["-O0", "-g", "-fcheck=all", "-fbacktrace", "-ffpe-trap=invalid,zero,overflow"]
_FAST_FLAGS = ["-O2"]


def _local_sibling_imports(py_path: Path) -> List[str]:
    """Top-level `import X` / `from X import ...` names in `py_path`
    that resolve to a sibling `X.py` file in the same directory -- one
    level only, matching this wrapper's stated scope."""
    tree = ast.parse(py_path.read_text(encoding="utf-8"))
    names: List[str] = []
    seen = set()
    for node in ast.walk(tree):
        candidates: List[str] = []
        if isinstance(node, ast.Import):
            candidates = [a.name.split(".")[0] for a in node.names]
        elif isinstance(node, ast.ImportFrom) and (node.module is not None) and node.level == 0:
            candidates = [node.module.split(".")[0]]
        for nm in candidates:
            if nm in seen:
                continue
            if (py_path.parent / f"{nm}.py").exists():
                seen.add(nm)
                names.append(nm)
    return names


def _pyccelize(py_path: Path) -> Path:
    """Run `pyccel compile <py_path> --language Fortran --convert-only`
    (cwd set to py_path's own directory, matching how pyccel resolves
    sibling imports) and return the generated `.f90` path. Raises
    RuntimeError with pyccel's own output on failure."""
    cp = subprocess.run(
        ["pyccel", "compile", py_path.name, "--language", "Fortran", "--convert-only"],
        cwd=py_path.parent,
        capture_output=True,
        text=True,
    )
    f90_path = py_path.parent / _PYCCEL_DIRNAME / f"{py_path.stem}.f90"
    if cp.returncode != 0 or not f90_path.exists():
        raise RuntimeError(
            f"pyccel compile failed for {py_path.name}:\n{cp.stdout}\n{cp.stderr}"
        )
    return f90_path


def _find_pyc_math_helper() -> Optional[Path]:
    try:
        import pyccel  # noqa: PLC0415 (imported lazily, only needed here)
    except ImportError:
        return None
    candidate = Path(pyccel.__file__).resolve().parent / "stdlib" / "math" / "pyc_math_f90.F90"
    return candidate if candidate.exists() else None


def _uses_module(f90_path: Path, module_name: str) -> bool:
    text = f90_path.read_text(encoding="utf-8", errors="ignore")
    return bool(re.search(rf"\buse\s+{re.escape(module_name)}\b", text, re.IGNORECASE))


def translate(py_path: Path) -> Tuple[Path, List[Path]]:
    """Pyccelize `py_path` and every local sibling module it imports
    (one level). Returns (entry .f90 path, [sibling .f90 paths in
    dependency order])."""
    sibling_names = _local_sibling_imports(py_path)
    sibling_f90 = [_pyccelize(py_path.parent / f"{nm}.py") for nm in sibling_names]
    entry_f90 = _pyccelize(py_path)
    return entry_f90, sibling_f90


def write_stub(stem: str, out_path: Path) -> None:
    out_path.write_text(
        f"program wrapper_main\n"
        f"  use {stem}, only: {stem}__init\n"
        f"  implicit none\n"
        f"  call {stem}__init()\n"
        f"end program wrapper_main\n",
        encoding="utf-8",
    )


def compile_exe(
    entry_f90: Path,
    sibling_f90: Sequence[Path],
    exe_path: Path,
    *,
    fast: bool = False,
) -> subprocess.CompletedProcess:
    stub_path = entry_f90.parent / "wrapper_main.f90"
    write_stub(entry_f90.stem, stub_path)

    link_inputs = list(sibling_f90) + [entry_f90]
    pyc_math = _find_pyc_math_helper()
    if pyc_math is not None and any(_uses_module(f, "pyc_math_f90") for f in link_inputs):
        link_inputs.insert(0, pyc_math)
    link_inputs.append(stub_path)

    flags = _FAST_FLAGS if fast else _DEFAULT_FLAGS
    cmd = ["gfortran", *flags, *[str(f) for f in link_inputs], "-o", str(exe_path)]
    print("Build:", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True)


def run_capture(cmd: Sequence[str]) -> Tuple[int, str, str]:
    cp = subprocess.run(cmd, capture_output=True, text=True)
    return cp.returncode, cp.stdout, cp.stderr


_NUM_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][-+]?\d+)?")


def _numeric_tokens(text: str) -> List[float]:
    out = []
    for tok in _NUM_RE.findall(text):
        try:
            out.append(float(tok.replace("d", "e").replace("D", "E")))
        except ValueError:
            pass
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_py", help="Python script to translate (via pyccel) and optionally build/run")
    ap.add_argument("--compile", action="store_true", help="also link a standalone executable")
    ap.add_argument("--run", action="store_true", help="also run the compiled executable (implies --compile)")
    ap.add_argument("--run-both", action="store_true", help="run both the original Python and the compiled executable, and diff stdout (implies --run)")
    ap.add_argument("--numeric-diff", action="store_true", help="with --run-both, compare only the numeric tokens in stdout, with a relative tolerance")
    ap.add_argument(
        "--tol", type=float, default=1e-4,
        help="relative tolerance for --numeric-diff (default: 1e-4 -- "
        "looser than xp2f.py's own 1e-12 default because pyccel's "
        "generated print statements use a fixed-decimal-places format "
        "(e.g. F0.15) with no scientific notation, which shows only a "
        "handful of significant digits for a very small-magnitude "
        "value; this is a print-formatting characteristic of pyccel's "
        "own codegen, not a computation difference)",
    )
    ap.add_argument("--fast", action="store_true", help="compile with -O2 instead of xp2f.py's own default debug flags (-O0 -g -fcheck=all ...)")
    args = ap.parse_args(argv)

    do_run_both = args.run_both
    do_run = args.run or do_run_both
    do_compile = args.compile or do_run

    py_path = Path(args.input_py).resolve()

    py_stdout = None
    if do_run_both:
        print("Run (python):", sys.executable, py_path.name)
        rc, out, err = run_capture([sys.executable, str(py_path)])
        if rc != 0:
            print("Run (python): FAIL")
            print(err)
            return 1
        print("Run (python): PASS")
        py_stdout = out

    try:
        entry_f90, sibling_f90 = translate(py_path)
    except RuntimeError as e:
        print(f"Translate: FAIL\n{e}")
        return 1
    print("Translate: PASS ->", entry_f90)

    if not do_compile:
        return 0

    exe_path = py_path.parent / _PYCCEL_DIRNAME / f"{py_path.stem}_pyccel_wrap.exe"
    cp = compile_exe(entry_f90, sibling_f90, exe_path, fast=args.fast)
    if cp.returncode != 0:
        print(f"Build: FAIL (exit {cp.returncode})")
        if cp.stdout.strip():
            print(cp.stdout.rstrip())
        if cp.stderr.strip():
            print(cp.stderr.rstrip())
        return cp.returncode
    print("Build: PASS")

    if not do_run:
        return 0

    rc, f_out, f_err = run_capture([str(exe_path)])
    if rc != 0:
        print(f"Run: FAIL (exit {rc})")
        print(f_err)
        return rc
    print("Run: PASS")
    print(f_out.rstrip())

    if do_run_both:
        if args.numeric_diff:
            py_nums = _numeric_tokens(py_stdout)
            f_nums = _numeric_tokens(f_out)
            if len(py_nums) != len(f_nums):
                print(f"Run numeric diff: DIFF (different token count: python={len(py_nums)} fortran={len(f_nums)})")
                return 1
            for i, (a, b) in enumerate(zip(py_nums, f_nums)):
                denom = max(abs(a), abs(b), 1e-300)
                if abs(a - b) / denom > args.tol:
                    print(f"Run numeric diff: DIFF at token {i}: python={a} fortran={b}")
                    return 1
            print("Run numeric diff: MATCH")
        else:
            if py_stdout.strip() == f_out.strip():
                print("Run diff: MATCH")
            else:
                print("Run diff: DIFF")
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
