"""Coverage probe: one small program per public numpy function, run
through xp2f.py and compared with numpy.

    python numpy_conformance/coverage_probe.py gen
    python numpy_conformance/coverage_probe.py run [START STOP] [--jobs N] [--redo STATUS ...]
    python numpy_conformance/coverage_probe.py report
    python numpy_conformance/coverage_probe.py genvar
    python numpy_conformance/coverage_probe.py run --variants [START STOP] ...
    python numpy_conformance/coverage_probe.py report --variants

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
  KIND        the same numbers, but integers where numpy has floats (or
              booleans), or the reverse
  DIFF        different numbers or a different count (check: may be a
              silent wrong result, or a known difference in printing)
  RUN-FAIL    the Fortran program stopped
  BUILD-FAIL  gfortran rejected the translation
  XLATE-FAIL  xp2f.py raised an error (usually an unsupported feature)
  NOARGS      no candidate argument list suits the function

report writes coverage/report.md: counts by status and the cases that
are not MATCH with their first error line.

genvar makes variants of the cases that match: the same call with the
fixtures rebound to integer arrays, arrays with NaN and inf, ties, one
element and empty arrays (VARIANTS), and calls with a matrix argument
given axis=0, axis=1, axis=-1, keepdims=True or ddof=1 (KW_VARIANTS);
a variant is kept when numpy accepts it without a warning. They are run
and reported with --variants (coverage/variant_results.txt,
coverage/variant_report.md).

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
VCASES = OUT / "variants.json"
# Without -ffpe-trap: compare the values a build without the debug traps
# computes (numpy returns NaN and inf where the trap would stop).
BUILD = ["--compile", "--compiler", "gfortran -O0 -g -fcheck=all -fbacktrace"]
VRESULTS = OUT / "variant_results.txt"

FIX = {
    "x": "np.array([0.5, 1.5, -2.0, 3.25])",
    "xi": "np.array([3, 1, 4, 1])",
    "m": "np.array([[2.0, 1.0], [1.0, 3.0]])",
    "mr": "np.array([[2.0, 1.0, 0.5], [1.0, 3.0, -1.0]])",
    "b": "np.array([True, False, True, True])",
}
HEADER = "import numpy as np\n" + "".join(f"{k} = {v}\n" for k, v in FIX.items())
# Variant fixture sets (genvar): the same call with the names rebound, to
# look for silent wrong results on other inputs.
VARIANTS = {
    "int": {"x": "np.array([3, 1, -4, 2])", "m": "np.array([[2, 1], [1, 3]])",
            "mr": "np.array([[2, 1, 0], [1, 3, -1]])"},
    "nan": {"x": "np.array([0.5, np.nan, -2.0, np.inf])", "m": "np.array([[2.0, np.nan], [1.0, 3.0]])",
            "mr": "np.array([[2.0, 1.0, -np.inf], [np.nan, 3.0, -1.0]])"},
    "ties": {"x": "np.array([2.0, -2.0, 2.0, 0.0])", "xi": "np.array([2, 2, -1, 0])",
             "m": "np.array([[1.0, 1.0], [0.0, 1.0]])", "mr": "np.array([[0.0, 1.0, 1.0], [1.0, 0.0, 1.0]])",
             "b": "np.array([False, False, True, False])"},
    "one": {"x": "np.array([2.5])", "xi": "np.array([3])", "m": "np.array([[2.0]])",
            "mr": "np.array([[1.0, -2.0, 0.5]])", "b": "np.array([True])"},
    "empty": {"x": "np.array([])", "xi": "np.array([], dtype=int)", "m": "np.zeros((0, 2))",
              "mr": "np.zeros((2, 0))", "b": "np.array([], dtype=bool)"},
}
# Keyword variants: added to a call with a matrix argument.
KW_VARIANTS = {"axis0": "axis=0", "axis1": "axis=1", "axism1": "axis=-1", "keepdims": "axis=0, keepdims=True",
               "ddof": "ddof=1"}
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
# Variants: NaN propagation details, platform-dependent values, and the
# probe's own limits.
KNOWN.update({
    "np.empty_like": "uninitialized values",
    "np.empty_like[int]": "uninitialized values",
    "np.linalg.solve[nan]": "NaN propagation through the LAPACK factorization differs",
    "np.roots[ties]": "the roots in another order (eigenvalue order)",
    "np.setxor1d[nan]": "NaN treated as one value",
    "np.frexp[nan]": "the exponent of inf and NaN is platform-dependent (0 here, numpy on Windows -1)",
    "np.interp[nan]": "xp with NaN and inf (not increasing, as numpy requires)",
    "np.digitize[nan]": "bins with NaN are rejected as not monotonic",
    "np.nonzero[empty]": "the probe reads numpy's dtype=int64 as a number",
    "np.where[empty]": "the probe reads numpy's dtype=int64 as a number",
    "np.polymul[empty]": "empty coefficient arrays",
    "np.resize[empty]": "resizing an empty array",
    "np.vander[empty]": "an empty array",
})
for _n in ("pinv", "qr", "svd", "svdvals"):
    KNOWN[f"np.linalg.{_n}[empty]"] = "empty matrices are not supported (LAPACK reports an illegal argument)"
for _n in ("fft", "ifft", "rfft", "fftn", "ifftn", "rfftn", "ihfft", "fft2", "ifft2", "rfft2"):
    KNOWN[f"np.fft.{_n}[nan]"] = "NaN propagation through the FFT differs (numpy keeps some parts finite)"
for _w in ("bartlett", "blackman", "hamming", "hanning"):
    KNOWN[f"np.{_w}"] = "the probe's float M is rejected (M must be an integer)"
    for _v in VARIANTS:
        KNOWN[f"np.{_w}[{_v}]"] = "the probe's float M is rejected (M must be an integer)"
NUM = (r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?|\bTrue\b|\bFalse\b|\bT\b|\bF\b|\bnan\b|\bNaN\b"
       r"|\binf\b|\bInf\b|\bInfinity\b")


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


def _header(fixtures: dict | None = None) -> str:
    fx = dict(FIX, **(fixtures or {}))
    return "import numpy as np\n" + "".join(f"{k} = {v}\n" for k, v in fx.items())


def gen_variants() -> None:
    """Variants of the base cases that match: each fixture set of
    VARIANTS, and each keyword of KW_VARIANTS for calls with a matrix
    argument, kept when numpy accepts them without a warning."""
    import numpy as np
    base = json.loads(CASES.read_text(encoding="utf-8"))
    res = _read_results(RESULTS)
    out = []
    for c in base:
        if c["expr"] is None or res.get(c["name"], ("",))[0] != "MATCH":
            continue
        tries = [(v, c["expr"], fx) for v, fx in VARIANTS.items()]
        if re.search(r"\b(m|mr)\b", c["expr"]) and c["expr"].endswith(")"):
            tries += [(v, c["expr"][:-1] + ", " + kw + ")", {}) for v, kw in KW_VARIANTS.items()]
        for v, expr, fx in tries:
            env = {"np": np}
            for k, src in dict(FIX, **fx).items():
                env[k] = eval(src, env)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error")
                    val = eval(expr, env)
            except Exception:
                continue
            k = _numeric_parts(val)
            if k is None:
                continue
            out.append({"name": f"{c['name']}[{v}]", "expr": expr, "parts": k, "fixtures": fx})
    VCASES.write_text(json.dumps(out, indent=0), encoding="utf-8")
    print(len(out), "variants of", len({o["name"].split("[")[0] for o in out}), "functions")


def _program(case) -> str:
    head = _header(case.get("fixtures"))
    k = case.get("parts", 0)
    if k:
        names = [f"r{i}" for i in range(k)]
        return head + f"{', '.join(names)} = {case['expr']}\n" + "".join(f"print({n})\n" for n in names)
    return head + f"r = {case['expr']}\nprint(r)\n"


def _kinds(s: str) -> list[str]:
    """bool/float/int of each number printed (numpy prints floats with a
    point or exponent, Fortran too; nan and inf are floats)."""
    out = []
    for tok in re.findall(NUM, s):
        if tok in {"True", "False", "T", "F"}:
            out.append("bool")
        elif re.search(r"[.eE]", tok) or tok.lower() in {"nan", "inf", "infinity"}:
            out.append("float")
        else:
            out.append("int")
    return out


def _numbers(s: str) -> list[float]:
    conv = {"True": "1", "False": "0", "T": "1", "F": "0", "NaN": "nan", "Infinity": "inf", "Inf": "inf"}
    return [float(conv.get(t, t)) for t in re.findall(NUM, s)]


def _xp2f(src: Path):
    """xp2f.py --compile of src, run again once if it printed nothing (a
    transient failure, seen under heavy parallel load)."""
    for _ in range(2):
        p = subprocess.run([sys.executable, str(XP2F), src.name] + BUILD, cwd=WORK, capture_output=True,
                           text=True, timeout=600)
        if (p.stdout + p.stderr).strip():
            break
    return p


def _run_one(case) -> tuple[str, str]:
    if case["expr"] is None:
        return "NOARGS", ""
    tag = re.sub(r"\W", "_", case["name"].replace("np.", "")).strip("_")
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
    p = _xp2f(src)
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
    if _kinds(py.stdout) != _kinds(r.stdout):
        return "KIND", show
    return "MATCH", ""


MARK = "@@case"


def _group_program(cases) -> tuple[str, list[tuple[int, int]]]:
    """One program for several cases (the variants of one function): case
    k's fixtures are named x_k, m_k, ..., and its output follows a line
    "@@case k". Returns the source and each case's (first, last) line."""
    lines, spans = ["import numpy as np"], []
    for k, c in enumerate(cases):
        first = len(lines) + 1
        fx = dict(FIX, **(c.get("fixtures") or {}))
        expr = c["expr"]
        used = [n for n in fx if re.search(rf"\b{n}\b", expr)]
        for n in used:
            lines.append(f"{n}_{k} = {fx[n]}")
        expr = re.sub(r"\b(" + "|".join(used) + r")\b", lambda mm: f"{mm.group(1)}_{k}", expr) if used else expr
        lines.append(f'print("{MARK} {k}")')
        parts = c.get("parts", 0)
        if parts:
            names = [f"r{k}_{i}" for i in range(parts)]
            lines.append(f"{', '.join(names)} = {expr}")
            lines += [f"print({n})" for n in names]
        else:
            lines += [f"r{k} = {expr}", f"print(r{k})"]
        spans.append((first, len(lines)))
    return "\n".join(lines) + "\n", spans


def _blocks(out: str) -> dict[int, str]:
    """The output after each "@@case k" line."""
    res, cur = {}, None
    for line in out.splitlines():
        m = re.match(rf"\s*{MARK} (\d+)\s*$", line)
        if m:
            cur = int(m.group(1))
            res[cur] = ""
        elif cur is not None:
            res[cur] += line + "\n"
    return res


def _compare(py: str, ft: str) -> tuple[str, str]:
    a, b = _numbers(py), _numbers(ft)
    show = f"py={' '.join(py.split())[:80]} | ft={' '.join(ft.split())[:80]}"
    if len(a) != len(b):
        return "DIFF", f"count {len(a)} vs {len(b)}: {show}"
    for u, v in zip(a, b):
        if u != u and v != v:
            continue
        if not (u == v or abs(u - v) <= 1e-7 * max(1.0, abs(u)) or abs(u - v) <= 1e-8):
            return "DIFF", show
    if _kinds(py) != _kinds(ft):
        return "KIND", show
    return "MATCH", ""


def _run_group(cases) -> dict[str, tuple[str, str]]:
    """Statuses of cases run as one program; a case that fails to
    translate (the error names its line) or stops the program is recorded
    and the program built again without it; a build error falls back to
    one program per case."""
    if len(cases) == 1:
        return {cases[0]["name"]: _run_one(cases[0])}
    tag = re.sub(r"\W", "_", cases[0]["name"].split("[")[0].replace("np.", "")).strip("_") + "_var"
    res = {}
    todo = list(cases)
    try:
        while todo:
            src_txt, spans = _group_program(todo)
            src = WORK / f"cv_{tag}.py"
            src.write_text(src_txt, encoding="utf-8")
            py = subprocess.run([sys.executable, "-W", "ignore", src.name], cwd=WORK, capture_output=True,
                                text=True)
            p = _xp2f(src)
            out = p.stdout + p.stderr
            if "Transpile: FAIL" in out or (p.returncode != 0 and "Build:" not in out):
                m = re.search(r"Transpile: FAIL \((.*?)(?: at line (\d+).*)?\)\s*$", out, re.M)
                line = int(m.group(2)) if m and m.group(2) else None
                bad = next((i for i, (a, b) in enumerate(spans) if line is not None and a <= line <= b), None)
                if bad is None:
                    break
                res[todo[bad]["name"]] = ("XLATE-FAIL", m.group(1)[:160])
                del todo[bad]
                continue
            if "Build: FAIL" in out:
                break
            exe = WORK / f"cv_{tag}_p.exe"
            r = subprocess.run([str(exe)], cwd=WORK, capture_output=True, text=True, timeout=120)
            pyb, ftb = _blocks(py.stdout), _blocks(r.stdout)
            stopped = None
            if r.returncode != 0:
                stopped = max(ftb) if ftb else 0
            for k, c in enumerate(todo):
                if stopped is not None and k >= stopped:
                    break
                res[c["name"]] = _compare(pyb.get(k, ""), ftb.get(k, ""))
            if stopped is None:
                todo = []
            else:
                res[todo[stopped]["name"]] = ("RUN-FAIL", (r.stderr.strip().splitlines() or [""])[0][:160])
                todo = todo[stopped + 1:]
        for c in todo:
            res[c["name"]] = _run_one(c)
    finally:
        for f in WORK.glob(f"cv_{tag}_p*"):
            if f.suffix not in {".f90", ".py"}:
                f.unlink(missing_ok=True)
    return res


def _read_results(path: Path) -> dict[str, tuple[str, str]]:
    res = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            st, name, *rest = line.split("\t")
            res[name] = (st, rest[0] if rest else "")
    return res


def run(start: int, stop: int | None, jobs: int, redo: list[str], variants: bool = False) -> None:
    cases_path, results = (VCASES, VRESULTS) if variants else (CASES, RESULTS)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))[start:stop]
    WORK.mkdir(parents=True, exist_ok=True)
    done = _read_results(results)
    if redo:
        keep = {n: v for n, v in done.items() if v[0] not in redo}
        results.write_text("".join(f"{st}\t{n}\t{d}\n" for n, (st, d) in keep.items()), encoding="utf-8")
        done = keep
    todo = [c for c in cases if c["name"] not in done]
    if todo:
        # Build the runtime objects once: parallel builds of a changed
        # python.f90 would write the same object files at once.
        warm = WORK / "cv_warmup.py"
        warm.write_text("import numpy as np\nprint(np.sum(np.array([1.0, 2.0])))\n", encoding="utf-8")
        subprocess.run([sys.executable, str(XP2F), warm.name] + BUILD, cwd=WORK, capture_output=True, text=True)
    lock = threading.Lock()
    counts = Counter()
    # Variants of one function run as one program (translation dominates
    # the time).
    groups = {}
    for c in todo:
        groups.setdefault(c["name"].split("[")[0] if variants else c["name"], []).append(c)

    def one(group):
        try:
            got = _run_group(group) if variants else {group[0]["name"]: _run_one(group[0])}
        except Exception as e:  # noqa: BLE001
            got = {c["name"]: ("PROBE-ERROR", repr(e)[:120]) for c in group}
        with lock:
            with results.open("a", encoding="utf-8") as fh:
                for name, (st, detail) in got.items():
                    fh.write(f"{st}\t{name}\t{detail}\n")
                    counts[st] += 1
    with ThreadPoolExecutor(jobs) as ex:
        list(ex.map(one, list(groups.values())))
    print(f"{len(todo)} run:", dict(counts))


def report(variants: bool = False) -> None:
    res = _read_results(VRESULTS if variants else RESULTS)
    counts = Counter(st for st, _ in res.values())
    order = ["DIFF", "KIND", "RUN-FAIL", "BUILD-FAIL", "XLATE-FAIL", "PROBE-ERROR", "NOARGS", "MATCH"]
    title = "numpy coverage probe: input variants" if variants else "numpy coverage probe"
    lines = [f"# {title}", "", f"{len(res)} {'variants' if variants else 'functions'}.", "",
             "| status | count |", "|---|---|"]
    lines += [f"| {st} | {counts[st]} |" for st in order if counts[st]]
    for st in order[:-2]:
        names = sorted(n for n, v in res.items() if v[0] == st and n not in KNOWN and n.split("[")[0] not in KNOWN)
        if names:
            lines += ["", f"## {st}", ""] + [f"- `{n}`: {res[n][1]}" for n in names]
    known = sorted(n for n, v in res.items() if v[0] not in {"MATCH", "NOARGS"}
                   and (n in KNOWN or n.split("[")[0] in KNOWN))
    if known:
        lines += ["", "## Known differences", ""] + [f"- `{n}` ({res[n][0]}): {KNOWN.get(n) or KNOWN[n.split('[')[0]]}"
                                                       for n in known]
    if not variants:
        lines += ["", "## NOARGS", "", ", ".join(f"`{n}`" for n in sorted(n for n, v in res.items()
                                                                          if v[0] == "NOARGS"))]
    (OUT / ("variant_report.md" if variants else "report.md")).write_text("\n".join(lines) + "\n",
                                                                         encoding="utf-8")
    print(dict(counts))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen")
    sub.add_parser("genvar")
    pr = sub.add_parser("run")
    pr.add_argument("start", nargs="?", type=int, default=0)
    pr.add_argument("stop", nargs="?", type=int, default=None)
    pr.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    pr.add_argument("--redo", nargs="*", default=[])
    pr.add_argument("--variants", action="store_true", help="run the variants (genvar) instead")
    rp = sub.add_parser("report")
    rp.add_argument("--variants", action="store_true")
    args = ap.parse_args()
    if args.cmd == "gen":
        gen()
    elif args.cmd == "genvar":
        gen_variants()
    elif args.cmd == "run":
        run(args.start, args.stop, args.jobs, args.redo, args.variants)
    else:
        report(args.variants)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
