"""Coverage probe: one small program per public numpy function, run
through xp2f.py and compared with numpy.

    python numpy_conformance/coverage_probe.py gen
    python numpy_conformance/coverage_probe.py run [START STOP] [--jobs N] [--redo STATUS ...]
    python numpy_conformance/coverage_probe.py report

gen picks, for each public function of numpy, numpy.linalg, numpy.fft and
the six numpy.polynomial modules, the first argument list from a fixed
set of candidates (small real, integer, boolean vectors and matrices,
scalars) that numpy accepts without a warning and that returns small
numeric arrays. A function that returns a tuple is unpacked and each part
printed. Writes coverage/cases.json.

run translates, compiles and runs the programs of cases [START, STOP)
(default: all), in parallel, appending to coverage/results.txt; cases
already there are skipped, so a long run can be done in chunks (and
--redo STATUS... runs again the cases with those statuses). Statuses:

  MATCH       the same numbers as numpy (relative 1e-7, absolute 1e-8)
  DIFF        different numbers or a different count (check: may be a
              silent wrong result, or a known difference in printing)
  RUN-FAIL    the Fortran program stopped
  BUILD-FAIL  gfortran rejected the translation
  XLATE-FAIL  xp2f.py raised an error (usually an unsupported feature)
  NOARGS      no candidate argument list suits the function

report writes coverage/report.md: counts by status and the cases that
are not MATCH with their first error line.

The work files (the programs and executables) are in coverage/work.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import warnings
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "coverage"
WORK = OUT / "work"
XP2F = HERE.parent / "xp2f.py"
CASES = OUT / "cases.json"
RESULTS = OUT / "results.txt"

FIX = {
    "x": "np.array([0.5, 1.5, -2.0, 3.25])",
    "xi": "np.array([3, 1, 4, 1])",
    "m": "np.array([[2.0, 1.0], [1.0, 3.0]])",
    "mr": "np.array([[2.0, 1.0, 0.5], [1.0, 3.0, -1.0]])",
    "b": "np.array([True, False, True, True])",
}
HEADER = "import numpy as np\n" + "".join(f"{k} = {v}\n" for k, v in FIX.items())
CANDS = [["x"], ["m"], ["x", "x"], ["m", "m"], ["xi"], ["x", "0.7"], ["x", "2"], ["mr"], ["0.7"], ["3"],
         ["0.7", "0.4"], ["3", "4"], ["b"], ["b", "b"], ["xi", "xi"], ["x", "xi"], ["m", "x[:2]"], ["xi", "2"],
         ["x", "x", "x"], ["0.5", "0.25", "4"], ["3", "4", "2"], ["mr", "1"], ["m", "0"], ["x", "[1, 2]"]]
# I/O, configuration, dtype introspection and other functions without a
# numeric result to compare.
SKIP = {"info", "show_config", "show_runtime", "get_include", "set_printoptions", "get_printoptions",
        "printoptions", "seterr", "geterr", "seterrcall", "geterrcall", "errstate", "setbufsize", "getbufsize",
        "load", "save", "savez", "savez_compressed", "loadtxt", "savetxt", "genfromtxt", "fromfile", "fromregex",
        "frombuffer", "fromstring", "memmap", "test", "deprecate", "who", "source", "lookfor", "byte_bounds",
        "safe_eval", "add_newdoc", "add_docstring", "nested_iters", "broadcast", "nditer", "busday_count",
        "busday_offset", "is_busday", "datetime_as_string", "datetime_data", "set_string_function",
        "from_dlpack", "fromiter", "einsum_path", "require", "asfortranarray", "ascontiguousarray",
        "shares_memory", "may_share_memory", "iterable", "isfortran", "copyto", "putmask", "place", "put",
        "put_along_axis", "fill_diagonal", "ndindex", "ndenumerate", "unravel_index", "ravel_multi_index",
        "base_repr", "binary_repr", "format_float_positional", "format_float_scientific", "array2string",
        "array_repr", "array_str", "typename", "mintypecode", "common_type", "result_type", "promote_types",
        "can_cast", "min_scalar_type", "issubdtype", "isdtype", "frompyfunc", "vectorize",
        "piecewise", "apply_along_axis", "apply_over_axes", "get_array_wrap"}
# Differences that are deliberate (see python_to_fortran_syntax_guide.md);
# report lists them apart from the others.
KNOWN = {
    "np.linalg.eig": "always complex in the translation",
    "np.linalg.eigvals": "always complex in the translation",
    "np.argpartition": "numpy's introselect order is not reproduced",
    "np.partition": "numpy's introselect order is not reproduced",
}
for _f in ("poly", "cheb", "leg", "herm", "herme", "lag"):
    _mod = {"poly": "polynomial", "cheb": "chebyshev", "leg": "legendre", "herm": "hermite", "herme": "hermite_e",
            "lag": "laguerre"}[_f]
    KNOWN[f"np.polynomial.{_mod}.{_f}roots"] = "always complex in the translation"
KNOWN["np.roots"] = "always complex in the translation"
NUM = (r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?|\bTrue\b|\bFalse\b|\bT\b|\bF\b|\bnan\b|\bNaN\b"
       r"|\binf\b|\bInfinity\b")


def _numeric_parts(v):
    import numpy as np
    vals = tuple(v) if isinstance(v, tuple) else (v,)
    for vv in vals:
        a = np.asarray(vv)
        if a.dtype.kind not in "biufc" or a.size > 64 or a.ndim > 2:
            return None
    return len(vals) if isinstance(v, tuple) else 0


def gen() -> None:
    import numpy as np
    mods = [("np", np), ("np.linalg", np.linalg), ("np.fft", np.fft)] + [
        (f"np.polynomial.{n}", getattr(np.polynomial, n))
        for n in ("polynomial", "chebyshev", "legendre", "hermite", "hermite_e", "laguerre")]
    def fresh_env():
        # New fixtures for every candidate: some functions change their
        # arguments in place.
        env = {"np": np}
        for k, v in FIX.items():
            env[k] = eval(v, env)
        return env
    out, seen = [], set()
    for pre, mod in mods:
        names = getattr(mod, "__all__", None) or [n for n in dir(mod) if not n.startswith("_")]
        for n in sorted(set(names)):
            if n.startswith("_") or n in SKIP or (pre == "np" and n in seen):
                continue
            obj = getattr(mod, n, None)
            if obj is None or inspect.isclass(obj) or inspect.ismodule(obj) or not callable(obj):
                continue
            seen.add(n)
            chosen, parts = None, 0
            for c in CANDS:
                expr = f"{pre}.{n}({', '.join(c)})"
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("error")
                        v = eval(expr, fresh_env())
                except Exception:
                    continue
                k = _numeric_parts(v)
                if k is not None:
                    chosen, parts = expr, k
                    break
            out.append({"name": f"{pre}.{n}", "expr": chosen, "parts": parts})
    OUT.mkdir(exist_ok=True)
    CASES.write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(len(out), "functions;", sum(1 for o in out if o["expr"]), "with arguments")


def _program(case) -> str:
    k = case.get("parts", 0)
    if k:
        names = [f"r{i}" for i in range(k)]
        return HEADER + f"{', '.join(names)} = {case['expr']}\n" + "".join(f"print({n})\n" for n in names)
    return HEADER + f"r = {case['expr']}\nprint(r)\n"


def _numbers(s: str) -> list[float]:
    conv = {"True": "1", "False": "0", "T": "1", "F": "0", "NaN": "nan", "Infinity": "inf"}
    return [float(conv.get(t, t)) for t in re.findall(NUM, s)]


def _run_one(case) -> tuple[str, str]:
    if case["expr"] is None:
        return "NOARGS", ""
    tag = re.sub(r"\W", "_", case["name"].replace("np.", ""))
    try:
        return _run_one_in(case, tag)
    finally:
        # Keep the program and its translation; the executable and objects
        # are large.
        for f in WORK.glob(f"cv_{tag}_p*"):
            if f.suffix not in {".f90", ".py"}:
                f.unlink(missing_ok=True)


def _run_one_in(case, tag) -> tuple[str, str]:
    src = WORK / f"cv_{tag}.py"
    src.write_text(_program(case), encoding="utf-8")
    py = subprocess.run([sys.executable, "-W", "ignore", src.name], cwd=WORK, capture_output=True, text=True)
    p = subprocess.run([sys.executable, str(XP2F), src.name, "--compile"], cwd=WORK, capture_output=True,
                       text=True, timeout=300)
    out = p.stdout + p.stderr
    if "Transpile: FAIL" in out or (p.returncode != 0 and "Build:" not in out):
        m = re.search(r"Transpile: FAIL \((.*?)(?: at line \d+.*)?\)\s*$", out, re.M)
        tail = out.strip().splitlines()
        return "XLATE-FAIL", (m.group(1) if m else (tail[-1] if tail else "?"))[:160]
    if "Build: FAIL" in out:
        m = re.search(r"Error: (.*)", out)
        return "BUILD-FAIL", (m.group(1) if m else "")[:160]
    exe = WORK / f"cv_{tag}_p.exe"
    try:
        r = subprocess.run([str(exe)], cwd=WORK, capture_output=True, text=True, timeout=60)
    except Exception as e:  # noqa: BLE001 - recorded as the case's status
        return "RUN-FAIL", str(e)[:120]
    if r.returncode != 0:
        return "RUN-FAIL", (r.stderr.strip().splitlines() or [""])[0][:160]
    a, b = _numbers(py.stdout), _numbers(r.stdout)
    show = f"py={' '.join(py.stdout.split())[:80]} | ft={' '.join(r.stdout.split())[:80]}"
    if len(a) != len(b):
        return "DIFF", f"count {len(a)} vs {len(b)}: {show}"
    for u, v in zip(a, b):
        if u != u and v != v:
            continue
        if not (u == v or abs(u - v) <= 1e-7 * max(1.0, abs(u)) or abs(u - v) <= 1e-8):
            return "DIFF", show
    return "MATCH", ""


def _read_results() -> dict[str, tuple[str, str]]:
    res = {}
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            st, name, *rest = line.split("\t")
            res[name] = (st, rest[0] if rest else "")
    return res


def run(start: int, stop: int | None, jobs: int, redo: list[str]) -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))[start:stop]
    WORK.mkdir(parents=True, exist_ok=True)
    done = _read_results()
    if redo:
        keep = {n: v for n, v in done.items() if v[0] not in redo}
        RESULTS.write_text("".join(f"{st}\t{n}\t{d}\n" for n, (st, d) in keep.items()), encoding="utf-8")
        done = keep
    todo = [c for c in cases if c["name"] not in done]
    lock = threading.Lock()
    counts = Counter()

    def one(c):
        try:
            st, detail = _run_one(c)
        except Exception as e:  # noqa: BLE001
            st, detail = "PROBE-ERROR", repr(e)[:120]
        with lock:
            with RESULTS.open("a", encoding="utf-8") as fh:
                fh.write(f"{st}\t{c['name']}\t{detail}\n")
            counts[st] += 1
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one, todo))
    print(f"{len(todo)} run:", dict(counts))


def report() -> None:
    res = _read_results()
    counts = Counter(st for st, _ in res.values())
    order = ["DIFF", "RUN-FAIL", "BUILD-FAIL", "XLATE-FAIL", "PROBE-ERROR", "NOARGS", "MATCH"]
    lines = ["# numpy coverage probe", "", f"{len(res)} functions.", "", "| status | count |", "|---|---|"]
    lines += [f"| {st} | {counts[st]} |" for st in order if counts[st]]
    for st in order[:-2]:
        names = sorted(n for n, v in res.items() if v[0] == st and n not in KNOWN)
        if names:
            lines += ["", f"## {st}", ""] + [f"- `{n}`: {res[n][1]}" for n in names]
    known = sorted(n for n, v in res.items() if v[0] not in {"MATCH", "NOARGS"} and n in KNOWN)
    if known:
        lines += ["", "## Known differences", ""] + [f"- `{n}` ({res[n][0]}): {KNOWN[n]}" for n in known]
    lines += ["", "## NOARGS", "", ", ".join(f"`{n}`" for n in sorted(n for n, v in res.items() if v[0] == "NOARGS"))]
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(dict(counts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen")
    pr = sub.add_parser("run")
    pr.add_argument("start", nargs="?", type=int, default=0)
    pr.add_argument("stop", nargs="?", type=int, default=None)
    pr.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    pr.add_argument("--redo", nargs="*", default=[])
    sub.add_parser("report")
    args = ap.parse_args()
    if args.cmd == "gen":
        gen()
    elif args.cmd == "run":
        run(args.start, args.stop, args.jobs, args.redo)
    else:
        report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
