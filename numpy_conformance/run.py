"""Run the NumPy conformance programs written by gen.py through xp2f.py.

For each program: run it with Python, translate and compile it with
xp2f.py --compile, run the executable, and compare each `case <id>` block.
A block matches when it has the same number of values and each value has
the same kind (bool, int, float) and agrees to a relative 1e-6 -- so an
array NumPy prints as floats but the Fortran holds as integers is a
difference even when the numbers agree. When a program fails to
translate, compile or run, the failing cases are found from the error
locations (each case's code carries its r_cNNN / f_cNNN names), recorded,
and left out of the next build; errors that can't be placed fall back to
building the remaining cases one at a time.

Statuses, worst first:
  DIFF-value  the values differ (a silent wrong result)
  DIFF-kind   same values, different kind (e.g. int instead of float)
  DIFF-count  a different number of values (shape or length)
  RUN-FAIL    the Fortran executable stopped at the case
  BUILD-FAIL  gfortran rejected the translation
  XLATE-FAIL  xp2f.py raised an error (often an unsupported feature)
  UNTESTED    left out because the case failed in another context
  MATCH

    python numpy_conformance/run.py [name ...] [--no-split] [--edges | --no-edges]

With no names, every program runs, including the edge-input programs
"<spec>__<edge>" (empty, one-element, NaN/inf, 3-D and complex inputs);
--no-edges leaves those out, --edges adds them for the named specs.

Writes numpy_conformance/results/results_<date>.txt and a _terse.txt.
"""

from __future__ import annotations

import datetime as _dt
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import gen  # noqa: E402

XP2F = ROOT / "xp2f.py"
CASES = gen.CASES
SINGLE = CASES / "single"
RESULTS = HERE / "results"
ORDER = ["DIFF-value", "DIFF-kind", "DIFF-count", "RUN-FAIL", "BUILD-FAIL", "XLATE-FAIL", "UNTESTED", "MATCH"]
# xp2f's default debug flags, reporting every error instead of the first.
COMPILER = "gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -fmax-errors=100"
# NaN inputs: an ordered comparison with NaN raises the invalid flag, which
# -ffpe-trap=invalid turns into a crash where numpy just compares.
COMPILER_NAN = "gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=zero -fmax-errors=100"

_TOKEN_RE = re.compile(
    r"True|False|(?<![\w.])[TF](?![\w.])|[-+]?(?:nan|NaN|Infinity|inf|Inf)\b"
    r"|[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eEdD][-+]?\d+)?"
)
_CASE_REF_RE = re.compile(r"\b([rfl])_(c\d{3})([mfl])?\b")
_WHERE = {"m": "top level", "f": "in function", "l": "in loop"}
_GF_LOC_RE = re.compile(r"^(?:[A-Za-z]:)?[^:]*\.f90:(\d+):\d+:")


def tokens(text):
    out = []
    for t in _TOKEN_RE.findall(text):
        if t in ("True", "T"):
            out.append(("bool", 1.0))
        elif t in ("False", "F"):
            out.append(("bool", 0.0))
        elif re.fullmatch(r"[-+]?\d+", t):
            out.append(("int", float(t)))
        else:
            t = t.replace("Infinity", "inf").replace("Inf", "inf").replace("NaN", "nan")
            t = t.replace("d", "e").replace("D", "e")
            out.append(("float", float(t)))
    return out


def blocks(text):
    out, cur = {}, None
    for line in text.splitlines():
        m = re.fullmatch(r"\s*case (c\d+[mfl])\s*", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return {k: "\n".join(v) for k, v in out.items()}


def compare(py_text, ft_text):
    a, b = tokens(py_text), tokens(ft_text)
    if len(a) != len(b):
        return "DIFF-count", f"{len(a)} values vs {len(b)}"
    for (_, va), (_, vb) in zip(a, b):
        same = (va != va and vb != vb) or va == vb or (
            va == va and vb == vb and abs(va - vb) <= 1e-6 * max(1.0, abs(va), abs(vb)))
        if not same:
            return "DIFF-value", ""
    if "j" in py_text:
        # A complex value prints as (7-2j): its parts aren't int/float evidence.
        return "MATCH", ""
    for (ka, _), (kb, _) in zip(a, b):
        if ka != kb:
            return "DIFF-kind", f"{ka} vs {kb}"
    return "MATCH", ""


def first_error(text):
    for line in text.splitlines():
        if "FAIL" in line and ("Transpile" in line or "Build" in line):
            return line.strip()[:300]
    for line in text.splitlines():
        if line.strip().startswith("Error:") or ": Error:" in line:
            return line.strip()[:300]
    return ""


def python_blocks(py_path):
    run = subprocess.run([sys.executable, str(py_path)], capture_output=True, text=True, timeout=300)
    return blocks(run.stdout)


def translate_and_build(py_path):
    """("OK" | "XLATE-FAIL" | "BUILD-FAIL", log)."""
    compiler = COMPILER_NAN if "__nan" in py_path.stem else COMPILER
    try:
        xp = subprocess.run([sys.executable, str(XP2F), str(py_path), "--compile", "--compiler", compiler],
                            cwd=ROOT, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return "XLATE-FAIL", "timeout"
    log = xp.stdout + xp.stderr
    if "Transpile: FAIL" in log or ("Build:" not in log and xp.returncode != 0):
        return "XLATE-FAIL", log
    if "Build: FAIL" in log:
        return "BUILD-FAIL", log
    return "OK", log


def run_exe(py_path):
    exe = py_path.with_name(py_path.stem + "_p.exe")
    try:
        ft = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        text, err, rc = ft.stdout, ft.stderr, ft.returncode
    except subprocess.TimeoutExpired:
        text, err, rc = "", "timeout", -1
    detail = ""
    if rc != 0:
        lines = [ln.strip() for ln in (err or text).splitlines() if ln.strip()]
        detail = next((ln for ln in lines if "error" in ln.lower()), lines[0] if lines else f"exit {rc}")
    return blocks(text), detail[:300]


def _owner(lines, idx, main_start):
    """(case id, context) of the code holding lines[idx]: the nearest
    r_cNNN<ctx> / f_cNNN / l_cNNN reference at or above it (not in a PUBLIC
    or USE list)."""
    for k in range(idx, -1, -1):
        s = lines[k].strip().lower()
        if s.startswith(("public", "use ", "private")):
            continue
        m = _CASE_REF_RE.search(lines[k])
        if m:
            if m.group(3):
                return m.group(2), m.group(3)
            return m.group(2), ("m" if idx >= main_start else ("l" if m.group(1) == "l" else "f"))
    return None


def attribute(status, log, py_path):
    """{case id: {context: message}} for the errors in log."""
    out = {}
    if status == "XLATE-FAIL":
        m = re.search(r"Transpile: FAIL \((.*) at line (\d+): .*\)\s*$", log, re.M)
        if not m:
            return out
        lines = py_path.read_text(encoding="utf-8").splitlines()
        idx = min(int(m.group(2)) - 1, len(lines) - 1)
        main_start = next((k for k, ln in enumerate(lines) if ln.startswith("# fixtures")), len(lines))
        own = _owner(lines, idx, main_start)
        if own:
            out.setdefault(own[0], {})[own[1]] = m.group(1)[:300]
        return out
    f90 = py_path.with_name(py_path.stem + "_p.f90")
    if not f90.exists():
        return out
    lines = f90.read_text(encoding="utf-8").splitlines()
    main_start = next((k for k, ln in enumerate(lines) if re.match(r"^\s*program\s", ln, re.I)), len(lines))
    log_lines = log.splitlines()
    for k, ln in enumerate(log_lines):
        m = _GF_LOC_RE.match(ln.strip())
        if not m:
            continue
        err = next((x.strip() for x in log_lines[k + 1:k + 8] if x.strip().startswith("Error:")), None)
        if err is None:
            continue
        own = _owner(lines, int(m.group(1)) - 1, main_start)
        if own:
            out.setdefault(own[0], {}).setdefault(own[1], err[:300])
    return out


def run_program(name, split=True):
    exprs = gen.build(name)
    ids = [f"c{k + 1:03d}" for k in range(len(exprs))]
    path = CASES / f"xnp_{name}.py"
    results = {}
    active = list(range(len(exprs)))

    def record(k, ctx, st, det, pyt="", ftt=""):
        results[(k, ctx)] = (ids[k], ctx, exprs[k], st, det, pyt, ftt)

    for _attempt in range(len(exprs) + 10):
        if not active:
            break
        path.write_text(gen.program(name, [exprs[k] for k in active], [ids[k] for k in active]), encoding="utf-8")
        pyb = python_blocks(path)
        status, log = translate_and_build(path)
        if status == "OK":
            ftb, detail = run_exe(path)
            crashed = None
            for k in active:
                for ctx in gen.contexts(exprs[k]):
                    key = ids[k] + ctx
                    if crashed is None and key in ftb:
                        record(k, ctx, *compare(pyb.get(key, ""), ftb[key]), pyb.get(key, ""), ftb[key])
                    elif crashed is None:
                        crashed = (k, ctx)
            if crashed is None:
                break
            # Record the crash and rebuild without the cases up to it.
            k, ctx = crashed
            record(k, ctx, "RUN-FAIL", detail)
            ctxs = gen.contexts(exprs[k])
            for later in ctxs[ctxs.index(ctx) + 1:]:
                record(k, later, "UNTESTED", "")
            active = active[active.index(k) + 1:]
            continue
        culprits = {ids.index(cid): ctxs for cid, ctxs in attribute(status, log, path).items()}
        culprits = {k: v for k, v in culprits.items() if k in active}
        if not culprits:
            msg = first_error(log) or log.strip()[-300:]
            if split and len(active) > 1:
                for r in run_single(name, exprs, active):
                    results[(ids.index(r[0]), r[1])] = r
            else:
                for k in active:
                    for ctx in gen.contexts(exprs[k]):
                        record(k, ctx, status, msg)
            break
        for k, ctxs in culprits.items():
            for ctx in gen.contexts(exprs[k]):
                record(k, ctx, *((status, ctxs[ctx]) if ctx in ctxs else ("UNTESTED", "")))
            active.remove(k)
    return [results[key] for key in sorted(results)]


def run_single(name, exprs, indices):
    SINGLE.mkdir(parents=True, exist_ok=True)
    out = []
    for k in indices:
        cid, e = f"c{k + 1:03d}", exprs[k]
        path = SINGLE / f"xnp_{name}_{cid}.py"
        path.write_text(gen.program(name, [e], [cid]), encoding="utf-8")
        pyb = python_blocks(path)
        status, log = translate_and_build(path)
        if status == "OK":
            ftb, detail = run_exe(path)
            for ctx in gen.contexts(e):
                key = cid + ctx
                st, det = compare(pyb.get(key, ""), ftb[key]) if key in ftb else ("RUN-FAIL", detail)
                out.append((cid, ctx, e, st, det, pyb.get(key, ""), ftb.get(key, "")))
        else:
            out += [(cid, ctx, e, status, first_error(log), "", "") for ctx in gen.contexts(e)]
        print(f"    {cid} {out[-1][3]}  {e}", flush=True)
    return out


def main(argv):
    split = "--no-split" not in argv
    names = [a for a in argv if not a.startswith("--")]
    if not names:
        names = gen.program_names(edges="--no-edges" not in argv)
    elif "--edges" in argv:
        names = [f"{n}__{e}" for e in gen.EDGE_SETS for n in names] + names
    names = [n for n in names if gen.build(n)]
    RESULTS.mkdir(exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M")
    full = RESULTS / f"results_{stamp}.txt"
    terse = RESULTS / f"results_{stamp}_terse.txt"
    totals = {s: 0 for s in ORDER}
    with full.open("w", encoding="utf-8") as fh, terse.open("w", encoding="utf-8") as th:
        for name in names:
            print(f"{name} ...", flush=True)
            res = run_program(name, split)
            counts = {s: 0 for s in ORDER}
            for r in res:
                counts[r[3]] += 1
                totals[r[3]] += 1
            summary = ", ".join(f"{s} {n}" for s, n in counts.items() if n)
            print(f"  {summary}", flush=True)
            th.write(f"{name}: {summary}\n")
            fh.write(f"== {name}: {summary}\n")
            for cid, ctx, e, st, det, pyt, ftt in sorted(res, key=lambda r: (ORDER.index(r[3]), r[0], r[1])):
                if st in ("MATCH", "UNTESTED"):
                    continue
                where = _WHERE[ctx]
                line = f"{st:10s} {cid}{ctx} {e}  [{where}]" + (f"  {det}" if det else "")
                th.write("  " + line + "\n")
                fh.write(line + "\n")
                if st.startswith("DIFF"):
                    fh.write(f"    python : {' '.join(pyt.split())[:200]}\n")
                    fh.write(f"    fortran: {' '.join(ftt.split())[:200]}\n")
            fh.flush()
            th.flush()
        tot = ", ".join(f"{s} {n}" for s, n in totals.items() if n)
        fh.write(f"\nTOTAL: {tot}\n")
        th.write(f"\nTOTAL: {tot}\n")
    print(f"TOTAL: {tot}\nwrote {full}\nwrote {terse}")


if __name__ == "__main__":
    main(sys.argv[1:])
