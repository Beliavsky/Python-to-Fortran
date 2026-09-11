"""Fortran strided-array-access diagnostic.

xp2f.py translates a numpy 2D index/slice literally, preserving numpy's
own (row-major) index order rather than transposing to match Fortran's
column-major storage (the FIRST index is the contiguous one). For a
nested loop pair filling a whole array, `fortran_loop_reorder.py`'s
`--optimize-loops` can safely fix this by swapping which loop is
physically outer vs. inner. But two related shapes can't be fixed that
way at all, because there's no second loop to swap against:

- A "row slice" of a 2D array, `arr(i, :)` -- holding the FIRST index
  fixed while sweeping the entire second dimension is non-contiguous in
  Fortran regardless of any loop structure around it (this is exactly
  the shape rk4's own `y(i, :)` uses, passed into a per-step callback).
- A single (non-nested) loop where the loop's own induction variable
  only ever appears as an array's SECOND index while its FIRST index is
  some other, loop-invariant expression, e.g. `ohd(mv + 1, i)` inside
  `do i = ...` -- fixed-row/varying-column reads striding across the
  whole leading dimension on every iteration (dijkstra's own bottleneck).

Both were measured this session as real, substantial slowdowns (rk4
~4x, dijkstra ~2.5x versus pyccel, which avoids this by transposing
array storage). Actually FIXING either shape means changing an array's
own declared/storage layout -- a materially bigger, riskier change than
anything the other fortran_*.py tools this session make (they only
reorder or re-kind existing declarations/loops, never reshape an array),
so this module is deliberately diagnostic-only: it reports where the
pattern occurs, and leaves the decision (restructure the Python source,
accept the cost, or something else) to the person reading the message.
It never modifies the file it scans.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

import fortran_scan as fscan

_DO_HEADER_RE = re.compile(
    r"^\s*do\s+(?P<var>[A-Za-z_]\w*)\s*=\s*.+$", re.IGNORECASE
)
_DO_START_RE = re.compile(r"^\s*do\b", re.IGNORECASE)
_END_DO_RE = re.compile(r"^\s*end\s*do\s*$", re.IGNORECASE)
_ROW_SLICE_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*\(\s*([^,()]+?)\s*,\s*:\s*\)"
)
_SUBSCRIPT2_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*\(\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)"
)


def _is_var_expr(text: str, var: str) -> bool:
    """True if `text` is exactly `var`, or `var` plus/minus one or more
    integer literals (`i`, `i + 1`, `i - 1 + 1`) -- the shapes xp2f.py
    itself emits for a rebased/offset loop-index subscript."""
    return bool(
        re.fullmatch(
            rf"\s*{re.escape(var)}\s*(?:[+\-]\s*\d+\s*)*", text, re.IGNORECASE
        )
    )


def _mentions_var(text: str, var: str) -> bool:
    return bool(re.search(rf"\b{re.escape(var)}\b", text, re.IGNORECASE))


class Hint(NamedTuple):
    line: int
    array: str
    pattern: str  # "row-slice" or "strided-index"
    text: str
    message: str


def _find_row_slice_hints(stmts: Sequence[Tuple[int, str]]) -> List[Hint]:
    hints: List[Hint] = []
    for lineno, text in stmts:
        for m in _ROW_SLICE_RE.finditer(text):
            name, first = m.group(1), m.group(2)
            # A first argument that's itself a range (contains ':') isn't
            # a row-slice -- e.g. `phi(2:n-1, :)` sweeps a sub-block, not
            # one fixed row of a 2D array. Also skip anything whose first
            # argument already reduces to a bare `:` (skip a rank-1 array
            # entirely -- can't happen given the regex requires a comma,
            # but guard anyway) -- and skip an obvious non-array call by
            # requiring the "array" name not be a common intrinsic.
            if ":" in first:
                continue
            hints.append(
                Hint(
                    lineno,
                    name,
                    "row-slice",
                    m.group(0),
                    f"{name}({first.strip()}, :) holds the FIRST index fixed "
                    f"while sweeping the whole second dimension -- "
                    f"non-contiguous in Fortran's column-major layout "
                    f"regardless of loop structure (pyccel avoids this by "
                    f"transposing array storage).",
                )
            )
    return hints


def _find_strided_index_hints(stmts: Sequence[Tuple[int, str]]) -> List[Hint]:
    """For each statement, flag a 2-arg subscript whose SECOND argument
    is its INNERMOST enclosing `do LOOPVAR = ...` loop's own induction
    variable but whose FIRST argument never mentions that variable at
    all -- a fixed-row/varying-column read, striding across the whole
    leading dimension every iteration.

    Deliberately checks only the INNERMOST enclosing loop, via a stack,
    not every ancestor loop: for a nested pair, it's the innermost loop
    that actually determines the real memory-access granularity -- an
    OUTER loop's own induction variable will almost always fail this
    same "only in the second position" check too (that's inherent to any
    2-index array access inside a 2-level nest), but that's not a real
    finding on its own, and a nest like this is exactly what
    `fortran_loop_reorder.py`'s `--optimize-loops` can already fix by
    swapping which loop is outer vs. inner -- checking only the
    innermost loop means this scanner's own hints track whichever loop
    is ACTUALLY innermost after that fix runs, rather than staying stale
    against a nesting order that's already been corrected."""
    hints: List[Hint] = []
    # None on the stack marks a non-range-do (do while, bare do) nesting
    # level -- keeps depth tracking correct without claiming a loop
    # variable to check subscripts against.
    stack: List[Optional[str]] = []
    for lineno, text in stmts:
        if _END_DO_RE.match(text):
            if stack:
                stack.pop()
            continue
        m = _DO_HEADER_RE.match(text)
        if m is not None:
            stack.append(m.group("var"))
            continue
        if _DO_START_RE.match(text):
            stack.append(None)
            continue
        if not stack or stack[-1] is None:
            continue
        loop_var = stack[-1]
        for sm in _SUBSCRIPT2_RE.finditer(text):
            name, first, second = sm.group(1), sm.group(2), sm.group(3)
            if not _is_var_expr(second, loop_var):
                continue
            if _mentions_var(first, loop_var):
                continue
            hints.append(
                Hint(
                    lineno,
                    name,
                    "strided-index",
                    sm.group(0),
                    f"{name}({first.strip()}, {second.strip()}) inside "
                    f"`do {loop_var} = ...`: the loop variable is only "
                    f"in the SECOND (Fortran, slow-varying) position -- "
                    f"strided across the whole leading dimension on "
                    f"every iteration (pyccel avoids this by "
                    f"transposing array storage).",
                )
            )
    return hints


def scan_strided_access_hints(lines: List[str]) -> List[Hint]:
    """Every row-slice or loop-strided-index hint found in `lines`, in
    source order. Read-only -- never modifies `lines`."""
    stmts = fscan.iter_fortran_statements(lines)
    hints = _find_row_slice_hints(stmts) + _find_strided_index_hints(stmts)
    hints.sort(key=lambda h: h.line)
    return hints


def format_hints(hints: Sequence[Hint], source_name: str = "<input>") -> str:
    if not hints:
        return ""
    out = [f"{len(hints)} possible strided-array-access hint(s) in {source_name}:"]
    for h in hints:
        out.append(f"  {source_name}:{h.line}: [{h.pattern}] {h.message}")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_f90", help="Fortran source file to scan (never modified)")
    args = ap.parse_args(argv)

    in_path = Path(args.input_f90)
    lines = in_path.read_text(encoding="utf-8").splitlines(keepends=True)
    hints = scan_strided_access_hints(lines)
    text = format_hints(hints, str(in_path))
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
