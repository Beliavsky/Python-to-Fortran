"""Suppress stdout output reachable from a Fortran FUNCTION.

xp2f.py translates a Python function that both returns a value and
prints (directly, or by calling something else that prints) into a
Fortran FUNCTION that does the same. That's a latent crash risk: a
Fortran FUNCTION is usable inside an expression, and Fortran forbids a
nested I/O statement from executing while an OUTER I/O statement is
still transferring data ("recursive I/O not allowed"). So the moment
ANY caller -- in this program today, or a future edit, or another
program that reuses the generated module as a library -- writes
`print *, f(...)` for such an `f`, the build crashes at runtime, even
though the identical Python `print(f(...))` was always perfectly
valid (Python's print calls are simply sequential, not nested).

Since a function's future callers can't be controlled or predicted,
the only way to make a function-with-output truly safe to embed is to
remove the output from it. This module implements that as an OPT-IN
transformation (see xp2f.py's `--suppress-function-print`): every
stdout PRINT statement, and every WRITE statement targeting an
external unit (`*` or a literal unit number -- never an internal
CHARACTER-buffer WRITE, which has no observable output and is
harmless), that is reachable -- directly, or transitively through any
number of calls -- from any FUNCTION anywhere in the file, gets
commented out. "Reachable from a function" is computed GLOBALLY: if a
routine is EVER called from a function context, ALL of its stdout
output is suppressed, even at call sites that are only ever reached
from the top-level PROGRAM and never from a function -- the simpler,
safer trade-off over maintaining two print/no-print variants of the
same routine for different callers.

This is a text-level post-processing pass over the ALREADY-GENERATED
Fortran, following the same convention as its siblings
(fortran_loop_reorder.py, fortran_int_kind.py, fortran_purity.py):
never touches xp2f.py's own AST-level codegen, reuses fortran_purity's
already-tested procedure/call/I/O-statement parsing rather than
duplicating it, and is entirely opt-in -- default xp2f.py behavior is
completely unchanged.

Every suppression is reported back to the caller as a human-readable
warning (see `format_warnings`), since suppressing output is exactly
the point where the Fortran translation's console output starts to
diverge from the original Python program's.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional, Sequence, Set, Tuple

import fortran_purity as fpurity


class Suppression(NamedTuple):
    start_line: int
    end_line: int
    proc_name: str
    proc_kind: str


def _statement_end_line(lines: Sequence[str], start_line: int) -> int:
    """Given the 1-based start line of a (possibly free-form-continued)
    statement, return its 1-based end line, by re-applying the exact
    same continuation-line detection fortran_purity.join_continued_lines
    uses internally (which only ever returns a statement's START line,
    not its extent) -- needed here so a multi-line PRINT/WRITE gets
    every one of its physical lines commented out, not just its first."""
    n = len(lines)
    i = start_line
    while i <= n:
        code = fpurity.strip_comment(lines[i - 1]).rstrip("\r\n")
        if code.rstrip().endswith("&"):
            i += 1
            continue
        return i
    return min(start_line, n)


def _stdout_io_kind(stmt: str) -> Optional[str]:
    """'print' or 'write' if `stmt` is a PRINT statement, or a WRITE
    statement targeting an EXTERNAL unit (stdout, or any other numeric
    external unit -- xp2f.py itself only ever emits `*`, but a literal
    unit number is just as observable/external); None for everything
    else, including an internal-file WRITE (into a CHARACTER buffer),
    which produces no output and is perfectly safe to leave alone."""
    action = stmt.strip()
    if fpurity.PRINT_RE.match(action):
        return "print"
    low = action.lower()
    direct_write = fpurity.WRITE_RE.match(action)
    inline_io = fpurity.INLINE_IO_RE.search(low)
    if not (direct_write or inline_io):
        return None
    if direct_write:
        io_statement = action
    else:
        assert inline_io is not None
        if inline_io.group(1).lower() != "write":
            return None
        io_statement = low[inline_io.start(1):]
    control = fpurity.extract_io_control_list(io_statement, "write")
    if control is None:
        return None
    unit_expr = fpurity.io_unit_expr_from_control(control)
    if unit_expr is None:
        return None
    ue = unit_expr.strip()
    if ue == "*" or re.match(r"^[+-]?\d+$", ue):
        return "write"
    return None


def _called_local_names(stmt: str, known_names: Set[str]) -> Set[str]:
    """Every KNOWN local procedure name invoked in `stmt` -- covers both
    `call NAME(...)` and a bare `NAME(...)` function-call expression
    via fortran_purity's own general "identifier immediately followed
    by (" detector. Deliberately conservative: a stray false positive
    (some unrelated local variable that happens to share a name with a
    top-level procedure) only widens the suppressed set, never narrows
    it -- the safe direction for a check whose entire purpose is
    avoiding a hard runtime crash."""
    found = {m.group(1).lower() for m in fpurity.INVOCATION_RE.finditer(stmt)}
    found |= {m.group(1).lower() for m in fpurity.CALL_RE.finditer(stmt)}
    return found & known_names


def suppress_function_reachable_stdout_prints(
    lines: List[str],
) -> Tuple[List[str], List[str]]:
    """See module docstring. Returns (new_lines, warnings); never
    raises, never partially applies a statement (every suppression
    comments out the statement's full physical line range at once)."""
    procs = fpurity.parse_procedures(lines)
    if not procs:
        return list(lines), []

    known_names = {p.name.lower() for p in procs}
    calls: Dict[str, Set[str]] = {p.name: set() for p in procs}
    stdout_stmts: Dict[str, List[int]] = {p.name: [] for p in procs}

    for proc in procs:
        for lineno, stmt in proc.body:
            calls[proc.name] |= _called_local_names(stmt, known_names)
            if _stdout_io_kind(stmt) is not None:
                stdout_stmts[proc.name].append(lineno)

    reachable: Set[str] = set()
    stack = [p.name for p in procs if p.kind == "function"]
    while stack:
        nm = stack.pop()
        if nm in reachable:
            continue
        reachable.add(nm)
        stack.extend(calls.get(nm, set()) - reachable)

    to_suppress: List[Suppression] = []
    for proc in procs:
        if proc.name not in reachable:
            continue
        for lineno in stdout_stmts[proc.name]:
            end_line = _statement_end_line(lines, lineno)
            to_suppress.append(Suppression(lineno, end_line, proc.name, proc.kind))

    if not to_suppress:
        return list(lines), []

    new_lines = list(lines)
    warnings: List[str] = []
    for sup in sorted(to_suppress, key=lambda s: s.start_line):
        for i in range(sup.start_line, sup.end_line + 1):
            new_lines[i - 1] = "!" + new_lines[i - 1]
        loc = (
            f"line {sup.start_line}"
            if sup.end_line == sup.start_line
            else f"lines {sup.start_line}-{sup.end_line}"
        )
        warnings.append(
            f"{loc}: suppressed stdout output in {sup.proc_kind} `{sup.proc_name}` "
            "(reachable from a function) -- Fortran output now diverges from Python here"
        )
    return new_lines, warnings


def format_warnings(warnings: Sequence[str], source_name: str = "<input>") -> str:
    if not warnings:
        return ""
    out = [
        f"{len(warnings)} stdout print/write statement(s) suppressed in "
        f"{source_name} (--suppress-function-print):"
    ]
    for w in warnings:
        out.append(f"  {source_name}:{w}")
    return "\n".join(out)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_f90", help="Fortran source file to rewrite")
    ap.add_argument("-o", "--out", help="write result here instead of overwriting input_f90")
    ap.add_argument("--diff", action="store_true", help="print a unified diff instead of writing output")
    args = ap.parse_args(argv)

    in_path = Path(args.input_f90)
    lines = in_path.read_text(encoding="utf-8").splitlines(keepends=True)
    new_lines, warnings = suppress_function_reachable_stdout_prints(lines)
    text = format_warnings(warnings, str(in_path))
    if text:
        print(text, file=sys.stderr)

    if args.diff:
        sys.stdout.writelines(
            difflib.unified_diff(lines, new_lines, fromfile=str(in_path), tofile=str(in_path))
        )
        return 0

    out_path = Path(args.out) if args.out else in_path
    out_path.write_text("".join(new_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
