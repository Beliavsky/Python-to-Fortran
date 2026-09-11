"""Fortran-to-Fortran loop-nest reorder tool.

xp2f.py translates a numpy 2D index `arr[i, j]` literally to Fortran
`arr(i+1, j+1)` -- same index order, just rebased to 1-based. Fortran
arrays are column-major (the FIRST index is contiguous in memory); numpy
arrays are row-major (the LAST index is contiguous). So a Python loop
shaped like

    for i in range(rows):
        for j in range(cols):
            arr[i, j] = ...

emits `do i = ...` as the OUTER Fortran loop and `do j = ...` as the INNER
one -- but since `arr(i,j)`'s first index needs to be fast-varying for
cache-friendly access, that nesting strides through memory. This module is
a standalone post-processing pass (deliberately NOT wired into xp2f.py's
own translation pipeline by default -- see xp2f.py's `--optimize-loops`
flag for the opt-in integration) that swaps which of two immediately
nested `do` loops is emitted outer vs. inner, when doing so is both
provably safe and plausibly beneficial.

Tailored to xp2f.py's own emission style: plain, unlabeled
`do var = lo, hi[, step]` / `end do` (no `do while`, no labeled loops,
no loop variable on `end do`). A loop nest that doesn't match this exact
shape -- or whose do-loop headers span more than one physical line via
`&` continuation -- is simply left untouched rather than mishandled.

Safety: this pass only swaps the TEXT of the two `do` header lines with
each other. The loop body and both `end do` lines are never touched, so
a swap can only ever change which loop is nested inside which -- never
what any statement computes. It requires (a) every 2-argument array
subscript in the body that references both loop variables uses them
consistently in `(outer, inner)` order, and (b) no array written inside
the nest is also read anywhere else inside the same nest (the hallmark
of an ordinary numpy Jacobi-style stencil, which always reads from a
separate "old" array -- as opposed to an in-place Gauss-Seidel-style
relaxation, where loop order genuinely changes the numeric result).
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import fortran_scan as fscan

_DO_HEADER_RE = re.compile(
    r"^\s*do\s+(?P<var>[A-Za-z_]\w*)\s*=\s*(?P<bounds>.+?)\s*$",
    re.IGNORECASE,
)
_END_DO_RE = re.compile(r"^\s*end\s*do\s*$", re.IGNORECASE)
_DO_START_RE = re.compile(r"^\s*do\b", re.IGNORECASE)
_ASSIGN_TARGET_RE = re.compile(
    r"^\s*([A-Za-z_]\w*)\s*\(([^=]*)\)\s*=(?!=)"
)
# A 2-argument parenthesized subscript with no nested parens/commas in
# either argument -- covers the common `arr(i + 1, j - 1)` stencil shape.
# An index expression more complex than this (a nested call, a third
# dimension, ...) simply isn't counted as evidence either way.
_SUBSCRIPT2_RE = re.compile(
    r"\b[A-Za-z_]\w*\s*\(\s*([^(),]+?)\s*,\s*([^(),]+?)\s*\)"
)


def _split_code_comment(line: str) -> Tuple[str, str]:
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "!" and not in_single and not in_double:
            return line[:i], line[i:]
    return line, ""


def _is_var_expr(text: str, var: str) -> bool:
    """True if `text` is exactly `var`, or `var` plus/minus one or more
    integer literals (e.g. `i`, `i + 1`, `i-1`, `i - 1 + 1`) -- the
    shapes xp2f.py itself emits for a rebased/offset loop-index
    subscript. A CHAIN of offset terms is common: a Python-side offset
    (`arr[i - 1, j]`) composes with xp2f.py's own 0-based-to-1-based
    rebasing into `arr(i - 1 + 1, j + 1)`, not just a single `+ 1`."""
    return bool(
        re.fullmatch(
            rf"\s*{re.escape(var)}\s*(?:[+\-]\s*\d+\s*)*", text, re.IGNORECASE
        )
    )


def _benefit_check(body_stmts: Sequence[str], ovar: str, ivar: str) -> bool:
    """True if every recognizable 2-arg subscript referencing both loop
    variables uses them in (outer, inner) order, and at least one does."""
    found_any = False
    for stmt in body_stmts:
        for m in _SUBSCRIPT2_RE.finditer(stmt):
            a, b = m.group(1), m.group(2)
            a_is_o = _is_var_expr(a, ovar)
            a_is_i = _is_var_expr(a, ivar)
            b_is_o = _is_var_expr(b, ovar)
            b_is_i = _is_var_expr(b, ivar)
            if a_is_o and b_is_i:
                found_any = True
            elif a_is_i and b_is_o:
                # Opposite order found somewhere -- ambiguous, decline
                # rather than guess which order is actually faster.
                return False
    return found_any


def _safety_check(body_stmts: Sequence[str]) -> bool:
    """True if no array written inside the body is also read anywhere
    else inside the body (at any index) -- i.e. this isn't an in-place
    relaxation where the two loops' relative order affects the result."""
    written_names = set()
    lhs_count = {}
    for stmt in body_stmts:
        m = _ASSIGN_TARGET_RE.match(stmt)
        if not m:
            continue
        name = m.group(1).lower()
        written_names.add(name)
        lhs_count[name] = lhs_count.get(name, 0) + 1
    for name in written_names:
        pat = re.compile(rf"\b{re.escape(name)}\s*\(", re.IGNORECASE)
        total = sum(len(pat.findall(stmt)) for stmt in body_stmts)
        if total > lhs_count.get(name, 0):
            return False
    return True


def reorder_column_major_loop_nests(lines: List[str]) -> List[str]:
    """Swap the outer/inner nesting of immediately-nested `do` loops that
    fill a 2D array in (outer_var, inner_var) subscript order, when doing
    so is provably safe (see module docstring). Returns a new list of
    lines; the input is not mutated."""
    stmts = fscan.iter_fortran_statements(lines)
    n = len(stmts)

    def stmt_span(k: int) -> Tuple[int, int]:
        """1-based inclusive physical line range covered by statement k
        (up to, but not including, the next statement's own start line)."""
        start = stmts[k][0]
        end = stmts[k + 1][0] - 1 if k + 1 < n else len(lines)
        return start, end

    def is_single_line(k: int) -> bool:
        start, end = stmt_span(k)
        return start == end

    out = list(lines)
    k = 0
    while k < n:
        line_o, text_o = stmts[k]
        m_o = _DO_HEADER_RE.match(text_o)
        if m_o is None or not is_single_line(k):
            k += 1
            continue
        if k + 1 >= n:
            k += 1
            continue
        line_i, text_i = stmts[k + 1]
        m_i = _DO_HEADER_RE.match(text_i)
        if m_i is None or not is_single_line(k + 1):
            k += 1
            continue
        ovar, ivar = m_o.group("var"), m_i.group("var")
        if ovar.lower() == ivar.lower():
            k += 1
            continue

        # Find the inner loop's own `end do` (depth starts at 1 -- we're
        # already inside it), then require the outer loop's `end do` to
        # follow IMMEDIATELY (no other statements between them), i.e.
        # the outer loop's body is exactly this one inner loop.
        depth = 1
        j = k + 2
        inner_end_idx: Optional[int] = None
        while j < n:
            t = stmts[j][1]
            if _DO_START_RE.match(t):
                depth += 1
            elif _END_DO_RE.match(t):
                depth -= 1
                if depth == 0:
                    inner_end_idx = j
                    break
            j += 1
        if inner_end_idx is None:
            k += 1
            continue
        if inner_end_idx + 1 >= n or not _END_DO_RE.match(
            stmts[inner_end_idx + 1][1]
        ):
            k += 1
            continue
        outer_end_idx = inner_end_idx + 1

        body_stmts = [stmts[i][1] for i in range(k + 2, inner_end_idx)]

        if _benefit_check(body_stmts, ovar, ivar) and _safety_check(body_stmts):
            _swap_header_lines(out, line_o, line_i)

        k = outer_end_idx + 1

    return out


def _swap_header_lines(out: List[str], line_o: int, line_i: int) -> None:
    """Exchange the `do var = bounds` text of the two given 1-based
    physical line numbers, each keeping its own original indentation,
    trailing comment (if any), and end-of-line style."""
    idx_o, idx_i = line_o - 1, line_i - 1
    raw_o, raw_i = out[idx_o], out[idx_i]

    def parts(raw: str) -> Tuple[str, str, str, str]:
        eol = ""
        body = raw
        for e in ("\r\n", "\n"):
            if body.endswith(e):
                eol = e
                body = body[: -len(e)]
                break
        code, comment = _split_code_comment(body)
        indent = code[: len(code) - len(code.lstrip())]
        m = _DO_HEADER_RE.match(code)
        assert m is not None
        return indent, m.group("var"), m.group("bounds"), comment + eol

    indent_o, _var_o, bounds_o, tail_o = parts(raw_o)
    indent_i, _var_i, bounds_i, tail_i = parts(raw_i)

    out[idx_o] = f"{indent_o}do {_var_i} = {bounds_i}{tail_o}"
    out[idx_i] = f"{indent_i}do {_var_o} = {bounds_o}{tail_i}"


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_f90", help="Fortran source file to reorder loop nests in")
    ap.add_argument(
        "-o",
        "--out",
        help="write result to this path instead of overwriting the input "
        "(use '-' to print to stdout)",
    )
    ap.add_argument(
        "--diff",
        action="store_true",
        help="print a unified diff of the changes instead of writing output",
    )
    args = ap.parse_args(argv)

    in_path = Path(args.input_f90)
    text = in_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    new_lines = reorder_column_major_loop_nests(lines)

    if args.diff:
        diff = difflib.unified_diff(
            lines, new_lines, fromfile=str(in_path), tofile=str(in_path) + " (reordered)"
        )
        sys.stdout.writelines(diff)
        return 0

    new_text = "".join(new_lines)
    if args.out == "-":
        sys.stdout.write(new_text)
    elif args.out:
        Path(args.out).write_text(new_text, encoding="utf-8")
    else:
        in_path.write_text(new_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
