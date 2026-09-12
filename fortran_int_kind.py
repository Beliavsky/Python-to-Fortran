"""Fortran-to-Fortran integer-kind tool.

xp2f.py declares every integer as bare `integer` (the compiler's default
kind, normally 4 bytes/int32). This is a real parity gap against Python's
own unbounded `int` and against pyccel (which always uses an explicit
8-byte kind) -- concretely, `sum()` over a large array of default-kind
Fortran integers can silently overflow/wrap where the equivalent Python
code would not.

This module is a standalone post-processing pass (deliberately NOT wired
into xp2f.py's own translation pipeline by default -- see xp2f.py's
`--int-kind {int32,int64}` flag for the opt-in integration) that rewrites
bare `integer` declarations in an already-generated `.f90` file to
`integer(kind=ikind)`, inserting `integer, parameter :: ikind = int32` (or
`int64`) plus the matching `use, intrinsic :: iso_fortran_env, only: ...`
import once per module/program unit.

Safety: a small, fixed set of external boundary procedures (LAPACK
routines and this project's own scipy.optimize-style bridge wrappers --
`lapack_d.f90`, `fsolve_bridge.f90`, `curvefit_bridge.f90`,
`lbfgsb_bridge.f90`, `bfgs_bridge.f90`, `powell_bridge.f90`) are static,
unmodified external Fortran that declare every size/leading-dimension/info
argument as plain default-kind INTEGER. A generated local variable that's
passed as an actual argument to one of these calls is left as plain
`integer` -- never upgraded -- since widening it would be a genuine
dummy-argument kind mismatch against that external procedure's own
explicit interface (a real compile-time failure, not a style choice).

Every bare integer LITERAL constant also gets an `_ikind` suffix (skipping
string/comment content and anything inside a boundary call's own argument
list) -- this mirrors xp2f.py's own existing, proven approach for REAL
literals (every real constant it emits already gets a `_dp` suffix, e.g.
`0.5` -> `0.5_dp`): Fortran requires an actual argument passed to a
procedure under an explicit interface to match its dummy's kind EXACTLY
(unlike assignment or arithmetic, which freely widen) -- so a literal like
`foo(3, 4)` fails to compile once `foo`'s own parameters become
`integer(kind=ikind)`, the same way an unsuffixed real literal would fail
against a `real(kind=dp)` parameter.

Tailored to xp2f.py's own emission style, but unlike fortran_loop_reorder.py
(which declines a `do`-loop nest whose header spans more than one physical
line -- swapping two header lines in place has nowhere to put a longer
one), a statement that spans more than one physical line via `&`
continuation is still handled here: it's flattened to its already-joined
logical text, rewritten as a single line, and re-wrapped afterward with
this codebase's own existing `fortran_post.wrap_long_lines` if that made
it too long -- rather than skipped.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

import fortran_post as fpost
import fortran_scan as fscan

# External boundary procedures: static, unmodified Fortran -- the vendored
# runtime helper library (python.f90, ~300 procedures: linspace, sorting/
# searching, RNG, stats helpers, ...) and this project's own scipy.optimize-
# style bridge wrappers (*_bridge.f90) -- whose own dummy arguments are
# plain default-kind INTEGER wherever they're typed integer at all. A
# generated local variable passed as an actual argument to one of these
# calls must be excluded from the kind upgrade, or the call becomes a
# dummy-argument kind mismatch against that external procedure's own
# explicit interface. There are far too many such procedures (and new ones
# get added to python.f90 over time) to hand-maintain a fixed name list --
# instead this scans the actual vendored source files directly, once, the
# first time it's needed, and caches the result.
_BOUNDARY_SOURCE_FILES = ("python.f90", "lapack_d.f90")
_BOUNDARY_SOURCE_GLOB = "*_bridge.f90"

_boundary_calls_cache: Optional[frozenset] = None


def _scan_external_boundary_calls() -> frozenset:
    """Every subroutine/function name defined in the vendored runtime
    helper library or a *_bridge.f90 file that has at least one bare
    (not already `integer(kind=...)`) INTEGER dummy argument."""
    global _boundary_calls_cache
    if _boundary_calls_cache is not None:
        return _boundary_calls_cache

    names: Set[str] = set()
    base_dir = Path(__file__).resolve().parent
    candidates = [base_dir / f for f in _BOUNDARY_SOURCE_FILES]
    candidates.extend(sorted(base_dir.glob(_BOUNDARY_SOURCE_GLOB)))
    for path in candidates:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        src_lines = text.splitlines()
        for unit in fscan.split_fortran_units_simple(text):
            if unit["kind"] not in ("subroutine", "function"):
                continue
            arg_names = {a.lower() for a in unit["args"]}
            if not arg_names:
                continue
            for body_line in unit["body_lines"]:
                m = _DECL_RE.match(body_line)
                if m is None or "::" not in m.group("rest"):
                    continue
                _attrs, decl_names_part = m.group("rest").split("::", 1)
                for chunk in fscan._split_top_level_commas(decl_names_part):
                    nm_m = re.match(r"^\s*([A-Za-z_]\w*)", chunk)
                    if nm_m and nm_m.group(1).lower() in arg_names:
                        names.add(unit["name"].lower())
                        break
        # A call site never spells out argsort_int/argsort_real (the
        # concrete procedures just found above) -- it calls the GENERIC
        # interface name (`call argsort(...)`, resolved to whichever
        # concrete procedure matches at compile time), which is a
        # different name entirely and was invisible to the scan above
        # (an `interface NAME ... end interface` block is neither a
        # `subroutine` nor a `function` unit). If any of an interface's
        # own module procedures already has a bare-integer dummy (i.e.
        # is already in `names`), the interface's own name is just as
        # much an external boundary call as they are.
        for m_if in re.finditer(
            r"^\s*interface\s+([A-Za-z_]\w*)\s*$(.*?)^\s*end\s+interface\b",
            text,
            flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        ):
            iface_name = m_if.group(1).lower()
            body = m_if.group(2)
            concrete = set()
            for m_mp in re.finditer(r"^\s*module\s+procedure\s+(.+)$", body, flags=re.IGNORECASE | re.MULTILINE):
                for nm in m_mp.group(1).split(","):
                    nm = nm.strip().lower()
                    if nm:
                        concrete.add(nm)
            if concrete & names:
                names.add(iface_name)
        del src_lines

    _boundary_calls_cache = frozenset(names)
    return _boundary_calls_cache

_DECL_RE = re.compile(r"^(?P<indent>\s*)integer\b(?!\s*\()(?P<rest>.*)$", re.IGNORECASE)
_UNIT_OPEN_RE = re.compile(r"^\s*(module|program)\s+([A-Za-z_]\w*)\s*$", re.IGNORECASE)
_UNIT_CLOSE_RE = re.compile(r"^\s*end\s+(module|program)\b", re.IGNORECASE)
_IMPLICIT_NONE_RE = re.compile(r"^\s*implicit\s+none\s*$", re.IGNORECASE)
_USE_ISO_FORTRAN_ENV_RE = re.compile(
    r"^(?P<indent>\s*)use(?:\s*,\s*intrinsic\s*)?\s*::?\s*iso_fortran_env\s*,\s*only\s*:\s*(?P<names>.+?)\s*$",
    re.IGNORECASE,
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


_LEADING_KIND_SELECTOR_RE = re.compile(
    r"^\s*(?:real|integer|complex|logical|character)\s*\(\s*(\d+)\s*\)",
    re.IGNORECASE,
)


def _suffix_bare_int_literals_in_code(code: str) -> str:
    """Append `_ikind` to every bare integer literal TOKEN in `code`
    (which must already have any trailing comment stripped) -- skipping
    content inside quoted strings, real-number literals (has a `.` or an
    exponent letter adjacent), anything already kind-suffixed, digits that
    are actually part of a longer identifier (e.g. the `64` in `real64`),
    and -- if `code` is a declaration STATEMENT that opens with an
    old-style bare numeric kind selector (`real(8) :: x`, as opposed to
    this codebase's own `real(kind=dp)` style, which is unaffected here
    since `dp` isn't a digit) -- that selector's own number, which names a
    KIND, not a data value, and must stay a plain default-kind literal.
    An intrinsic call using the identical `real(1, ...)` syntax as an
    ordinary expression (not at the very start of the statement) is a
    normal data value and IS suffixed as usual."""
    protected_span: Optional[Tuple[int, int]] = None
    m_lead = _LEADING_KIND_SELECTOR_RE.match(code)
    if m_lead is not None:
        protected_span = m_lead.span(1)

    out: List[str] = []
    i = 0
    n = len(code)
    in_single = False
    in_double = False
    while i < n:
        ch = code[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            i += 1
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            i += 1
            continue
        if in_single or in_double:
            out.append(ch)
            i += 1
            continue
        if ch.isdigit():
            j = i
            while j < n and code[j].isdigit():
                j += 1
            prev_ch = code[i - 1] if i > 0 else ""
            next_ch = code[j] if j < n else ""
            is_ident_or_real_prefix = prev_ch.isalnum() or prev_ch in "_."
            is_real_or_suffixed_or_ident = next_ch in "._" or next_ch.isalpha()
            is_leading_kind_selector = protected_span == (i, j)
            token = code[i:j]
            if is_ident_or_real_prefix or is_real_or_suffixed_or_ident or is_leading_kind_selector:
                out.append(token)
            else:
                out.append(token + "_ikind")
            i = j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_INT_CAST_RE = re.compile(r"\bint\s*\(", re.IGNORECASE)


def _widen_bare_int_casts_in_code(code: str) -> str:
    """Rewrite every single-argument `int(expr)` call (no existing
    `kind=`) to `int(expr, kind=ikind)`. xp2f.py's own codegen sometimes
    emits an explicit, unkinded `int(...)` narrowing cast around an
    expression that's ABOUT to be passed to (or assigned into) something
    this pass has since widened to `integer(kind=ikind)` -- e.g.
    `call Spline__basis_funcs(self, xi, int(span), basis)`, where `span`
    was real-valued and `Spline__basis_funcs`'s own now-widened `span`
    dummy expects int64. `int(expr)` with no kind= always returns
    default-kind INTEGER, so left alone it silently narrows the widened
    value right back down at exactly the boundary where it mattered.
    Blanket-safe the same way literal-suffixing is (an `int(x, kind=
    ikind)` cast is a strict superset of what `int(x)` could produce, and
    is just as valid an assignment/expression operand everywhere `int(x)`
    was) -- the one place this must NOT be applied is inside a call to a
    TRUE external boundary procedure, which the caller already excludes
    by never running this function over that statement's own lines. An
    already-kinded (`int(x, kind=...)`) or 2-argument old-style
    (`int(x, 4)`) call is left untouched either way."""
    out_parts: List[str] = []
    pos = 0
    for m in _INT_CAST_RE.finditer(code):
        if m.start() < pos:
            continue
        # Guard against matching the tail of a longer identifier (e.g.
        # `myint(`) -- require a non-identifier character (or start of
        # line) immediately before "int".
        if m.start() > 0 and (code[m.start() - 1].isalnum() or code[m.start() - 1] == "_"):
            continue
        depth = 1
        i = m.end()
        n = len(code)
        while i < n and depth > 0:
            if code[i] == "(":
                depth += 1
            elif code[i] == ")":
                depth -= 1
            i += 1
        if depth != 0:
            continue
        inner = code[m.end() : i - 1]
        if not fscan._split_top_level_commas(inner):
            continue
        args = fscan._split_top_level_commas(inner)
        if len(args) != 1:
            continue
        out_parts.append(code[pos : m.end()])
        out_parts.append(f"{args[0].strip()}, kind=ikind")
        out_parts.append(")")
        pos = i
    out_parts.append(code[pos:])
    return "".join(out_parts)


def _line_eol(raw: str) -> Tuple[str, str]:
    for e in ("\r\n", "\n"):
        if raw.endswith(e):
            return raw[: -len(e)], e
    return raw, ""


def _find_calls_to(text: str, names: frozenset) -> List[Tuple[str, str]]:
    """Every `NAME(...)` occurrence in `text` where `NAME` (case-
    insensitive) is in `names`, anywhere in the statement -- not just a
    whole `call NAME(...)` statement, since a boundary FUNCTION (like
    python.f90's own `linspace`) is invoked as an ordinary expression
    (`x = linspace(...)`), not a `call` statement. Uses balanced-paren
    matching (not a lazy/greedy regex) so a nested call in an argument
    doesn't truncate the match early. Returns (name, arg_list_text)
    pairs."""
    out: List[Tuple[str, str]] = []
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", text):
        nm = m.group(1).lower()
        if nm not in names:
            continue
        depth = 1
        i = m.end()
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        if depth == 0:
            out.append((nm, text[m.end() : i - 1]))
    return out


_SIMPLE_OFFSET_ARG_RE = re.compile(
    r"^([A-Za-z_]\w*)\s*(?:[+\-]\s*\d+\s*)*$"
)


def _collect_excluded_names(stmts: Sequence[Tuple[int, str]], boundary: frozenset) -> Set[str]:
    """Every bare-Name (or simple `name +/- literal` offset, e.g. `n + 1`
    -- extremely common as a "point count" passed to something like
    `linspace`) actual argument passed to a known external-boundary call,
    anywhere in the file. A more complex expression is left alone -- this
    is deliberately the same conservative, name-level (not expression-
    rewriting) exclusion used everywhere else in this tool."""
    excluded: Set[str] = set()
    for _lineno, text in stmts:
        for _nm, arglist in _find_calls_to(text, boundary):
            for arg in fscan._split_top_level_commas(arglist):
                arg = arg.strip()
                # Keyword actual (`kw=expr`): only the expr side can be a
                # bare name reference, not the keyword itself.
                if "=" in arg and "=>" not in arg:
                    arg = arg.split("=", 1)[1].strip()
                m = _SIMPLE_OFFSET_ARG_RE.match(arg)
                if m:
                    excluded.add(m.group(1).lower())
    return excluded


def _expand_boundary_with_local_functions(lines: List[str], boundary: frozenset) -> frozenset:
    """A locally-defined function/subroutine (in THIS file, not the
    vendored runtime library) whose own body transitively calls something
    in `boundary` is itself added to the boundary set. Otherwise it would
    end up with a MIX of upgraded and un-upgradeable parameters (e.g.
    `laplace_2d`'s `nx`/`ny` must stay default-kind because they flow
    into `linspace` internally, but `laplace_2d` itself is then called
    elsewhere with literal arguments for nx/ny that would otherwise get
    wrongly `_ikind`-suffixed against those still-default-kind dummies).
    Excluding the WHOLE function this way is more conservative than
    strictly necessary (parameters of `laplace_2d` that never reach a
    boundary call, like `rtol`, also stay default-kind) but is simple and
    provably safe -- never a kind mismatch -- matching this tool's
    decline-rather-than-guess approach elsewhere."""
    # `lines` may or may not already carry their own trailing newline
    # (xp2f.py's own f90_lines pipeline does not; a file read via
    # `splitlines(keepends=True)` does) -- join on a guaranteed newline
    # per line rather than "".join, which would silently collapse
    # newline-free input into one unparseable blob.
    text = "\n".join(_line_eol(ln)[0] for ln in lines)
    units = {
        u["name"].lower(): u
        for u in fscan.split_fortran_units_simple(text)
        if u["kind"] in ("subroutine", "function")
    }
    current = set(boundary)
    changed = True
    while changed:
        changed = False
        for name, unit in units.items():
            if name in current:
                continue
            body_text = " ; ".join(unit["body_lines"])
            if _find_calls_to(body_text, frozenset(current)):
                current.add(name)
                changed = True
    return frozenset(current)


def _rewrite_decl_line(raw: str, excluded: Set[str]) -> List[str]:
    """Rewrite one physical `integer ...` declaration line, splitting it
    into an untouched line (for any excluded names) and an upgraded line
    (for the rest) if both are present. An upgraded line always
    references the `ikind` parameter -- never a literal `int32`/`int64` --
    so every declaration stays in sync with whichever kind the enclosing
    unit's own `integer, parameter :: ikind = ...` declares. Returns the
    replacement line(s), or [raw] unchanged if there's nothing to do."""
    body, eol = _line_eol(raw)
    code, comment = _split_code_comment(body)
    m = _DECL_RE.match(code)
    if m is None or "::" not in m.group("rest"):
        return [raw]
    indent = m.group("indent")
    attrs_part, names_part = m.group("rest").split("::", 1)
    attrs_part = attrs_part.rstrip()

    included_chunks: List[str] = []
    excluded_chunks: List[str] = []
    for chunk in fscan._split_top_level_commas(names_part):
        stripped = chunk.strip()
        if not stripped:
            continue
        nm_m = re.match(r"^([A-Za-z_]\w*)", stripped)
        nm = nm_m.group(1).lower() if nm_m else None
        if nm is not None and nm in excluded:
            excluded_chunks.append(stripped)
        else:
            included_chunks.append(stripped)

    if not included_chunks:
        return [raw]
    if not excluded_chunks:
        return [f"{indent}integer(kind=ikind){attrs_part} :: {names_part.strip()}{comment}{eol}"]

    out = [
        f"{indent}integer{attrs_part} :: {', '.join(excluded_chunks)}{eol}",
        f"{indent}integer(kind=ikind){attrs_part} :: {', '.join(included_chunks)}{comment}{eol}",
    ]
    return out


def _ensure_unit_has_ikind(unit_lines: List[str], kind_name: str) -> List[str]:
    """Given the physical lines of one module/program unit (open line
    through, but not including, its matching end line), return a modified
    copy with an `integer, parameter :: ikind = kind_name` declaration and
    a matching iso_fortran_env import inserted, if not already present."""
    out = list(unit_lines)

    already_has_ikind = any(
        re.search(r"\bikind\s*=", ln, re.IGNORECASE) for ln in out
    )

    # Indentation to use for any brand-new line this function inserts,
    # derived from `implicit none`'s own line (virtually always present
    # and properly indented in xp2f.py's own output) so a newly-inserted
    # `use` line doesn't end up at column 0 while the rest of the unit is
    # indented -- the unit-open line itself (`module foo`/`program foo`)
    # is not a reliable indentation source, since it's normally at
    # column 0.
    unit_indent = "   "
    for ln in out:
        if _IMPLICIT_NONE_RE.match(_split_code_comment(ln)[0]):
            m_ind = re.match(r"^(\s*)", ln)
            if m_ind:
                unit_indent = m_ind.group(1)
            break

    # Extend an existing `use, intrinsic :: iso_fortran_env, only: ...`
    # line in this unit if one exists; otherwise insert a new one.
    use_idx = None
    for i, ln in enumerate(out):
        if _USE_ISO_FORTRAN_ENV_RE.match(_split_code_comment(ln)[0]):
            use_idx = i
            break
    if use_idx is not None:
        body, eol = _line_eol(out[use_idx])
        code, comment = _split_code_comment(body)
        m = _USE_ISO_FORTRAN_ENV_RE.match(code)
        names = [n.strip() for n in m.group("names").split(",")]
        if kind_name not in [n.lower() for n in names]:
            names.append(kind_name)
            out[use_idx] = f"{m.group('indent')}use, intrinsic :: iso_fortran_env, only: {', '.join(names)}{comment}{eol}"
    else:
        # No existing iso_fortran_env import in this unit -- insert one
        # right after the unit-open line.
        insert_at = 1 if out else 0
        out.insert(insert_at, f"{unit_indent}use, intrinsic :: iso_fortran_env, only: {kind_name}\n")

    if not already_has_ikind:
        # Insert right after `implicit none` if present, else right after
        # the (possibly just-inserted) use line, else after the unit-open
        # line.
        target_idx = None
        for i, ln in enumerate(out):
            if _IMPLICIT_NONE_RE.match(_split_code_comment(ln)[0]):
                target_idx = i
                break
        if target_idx is None:
            target_idx = use_idx if use_idx is not None else 0
        out.insert(target_idx + 1, f"{unit_indent}integer, parameter :: ikind = {kind_name}\n")

    return out


def add_integer_kind(lines: List[str], kind_name: str) -> List[str]:
    """Rewrite bare `integer` declarations to `integer(kind={kind_name})`
    throughout `lines`, excluding anything passed as an actual argument to
    a known external-boundary call (see module docstring). Returns a new
    list of lines; the input is not mutated."""
    assert kind_name in ("int32", "int64"), kind_name

    stmts = fscan.iter_fortran_statements(lines)
    boundary = _expand_boundary_with_local_functions(lines, _scan_external_boundary_calls())
    excluded = _collect_excluded_names(stmts, boundary)
    # A kind-selector constant (dp/sp -- this codebase's own real32/real64
    # selectors -- and ikind, this pass's own) is used purely as a
    # compile-time KIND number, never as a runtime value; widening its own
    # declared integer kind would be pointless and confusing, so it's
    # always left as plain `integer`, regardless of the external-boundary
    # scan above.
    excluded = excluded | {"dp", "sp", "ikind"}

    def stmt_last_line(k: int) -> int:
        """1-based index of the LAST physical line of statement k,
        following its own `&` continuations from its own start line --
        NOT derived from the next statement's own start line, which a
        blank or comment-only line in between (extremely common right
        after a declaration block in xp2f.py's own output) would wrongly
        widen, making a genuinely single-physical-line statement look
        multi-line."""
        idx = stmts[k][0] - 1
        while idx < len(lines):
            code = _split_code_comment(lines[idx])[0].rstrip()
            if not code.endswith("&"):
                break
            idx += 1
        return idx + 1

    def stmt_span(k: int) -> Tuple[int, int]:
        # A "generous" span (through the line before the NEXT statement,
        # rather than stmt_last_line's precise end) for boundary-line
        # marking below -- including a trailing blank/comment line is
        # harmless there, since those lines have no literals to protect.
        start = stmts[k][0]
        end = stmts[k + 1][0] - 1 if k + 1 < len(stmts) else len(lines)
        return start, end

    # Every physical line belonging to a boundary-call statement is left
    # out of integer-literal suffixing -- a literal actual argument to one
    # of these external, default-kind-INTEGER procedures (or a local
    # function that transitively reaches one -- `boundary` from above
    # already covers both) must stay unsuffixed, the same reason its
    # variable counterparts are excluded above.
    boundary_lines: Set[int] = set()
    for k, (_lineno, text) in enumerate(stmts):
        if _find_calls_to(text, boundary):
            start, end = stmt_span(k)
            boundary_lines.update(range(start, end + 1))

    # One unified pass over STATEMENTS (not raw physical lines): a
    # statement spanning more than one physical line via `&` continuation
    # is flattened to its already-joined logical text (from `stmts`) and
    # rewritten as a single (possibly long) line, rather than skipped --
    # `fpost.wrap_long_lines` below re-wraps anything that ends up over
    # gfortran's free-form line-length limit, the same wrapper xp2f.py's
    # own pipeline already uses for exactly this purpose.
    out: List[str] = []
    consumed_through = 0
    for k, (lineno, text) in enumerate(stmts):
        start_idx = lineno - 1
        if start_idx < consumed_through:
            continue
        out.extend(lines[consumed_through:start_idx])
        end_idx = stmt_last_line(k) - 1

        if lineno in boundary_lines:
            out.extend(lines[start_idx : end_idx + 1])
            consumed_through = end_idx + 1
            continue

        first_code = _split_code_comment(_line_eol(lines[start_idx])[0])[0]
        indent_m = re.match(r"^(\s*)", first_code)
        indent = indent_m.group(1) if indent_m else ""
        last_body, eol = _line_eol(lines[end_idx])
        _, comment = _split_code_comment(last_body)

        code_line = _widen_bare_int_casts_in_code(f"{indent}{text}")
        code_line = _suffix_bare_int_literals_in_code(code_line)
        full_line = f"{code_line}{comment}{eol}"

        if _DECL_RE.match(code_line):
            out.extend(_rewrite_decl_line(full_line, excluded))
        else:
            out.append(full_line)
        consumed_through = end_idx + 1
    out.extend(lines[consumed_through:])
    # fpost.wrap_long_lines only puts the ORIGINAL line's own trailing
    # newline (if any) on the LAST of the segments it splits a long line
    # into -- correct for xp2f.py's own f90_lines convention (no line
    # carries its own newline; the caller joins the whole list with "\n"
    # at the very end), but this tool's standalone CLI convention (like
    # `lines`, read via splitlines(keepends=True)) is that EVERY element
    # carries its own newline. Normalize to whichever convention `lines`
    # itself actually used, so a newly-inserted internal segment doesn't
    # end up silently concatenated onto the next line with no separator.
    out = fpost.wrap_long_lines(out, max_len=80)
    if lines and lines[0].endswith(("\n", "\r\n")):
        out = [ln if ln.endswith(("\n", "\r\n")) else ln + "\n" for ln in out]

    # Second pass: insert the ikind parameter (+ iso_fortran_env import)
    # once per module/program unit.
    final: List[str] = []
    i = 0
    while i < len(out):
        m = _UNIT_OPEN_RE.match(_split_code_comment(out[i])[0])
        if m is None:
            final.append(out[i])
            i += 1
            continue
        j = i + 1
        depth = 1
        while j < len(out):
            code_j = _split_code_comment(out[j])[0]
            if _UNIT_OPEN_RE.match(code_j):
                depth += 1
            elif _UNIT_CLOSE_RE.match(code_j):
                depth -= 1
                if depth == 0:
                    break
            j += 1
        unit_body = out[i:j]  # open line through the line before `end ...`
        unit_body = _ensure_unit_has_ikind(unit_body, kind_name)
        final.extend(unit_body)
        i = j

    return final


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_f90", help="Fortran source file to add integer kinds to")
    ap.add_argument("--kind", choices=["int32", "int64"], required=True, help="integer kind to use")
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

    new_lines = add_integer_kind(lines, args.kind)

    if args.diff:
        diff = difflib.unified_diff(
            lines, new_lines, fromfile=str(in_path), tofile=str(in_path) + " (int-kind)"
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
