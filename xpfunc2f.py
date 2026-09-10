# xpfunc2f.py
# Translate ONE function (and its local dependencies) from a Python script
# to Fortran, compile it with f2py, and generate a thin Python wrapper --
# same name, same call signature -- that calls the compiled Fortran.
#
# Unlike xp2f.py, which translates an entire program into a standalone
# Fortran executable, this tool extracts one function's transitive
# dependency closure out of xp2f.py's own (unmodified) whole-program
# translation, keeps only that subset, and bridges it back into Python via
# numpy.f2py -- so the rest of the original script keeps running as
# ordinary Python, with just the target function now backed by compiled
# Fortran.
#
# usage:
#   python xpfunc2f.py script.py function_name
#   python xpfunc2f.py script.py function_name --out-dir build --verify
#   python xpfunc2f.py script.py --all           (bridge every top-level
#     function except main(), independently; --run-both/--time-both are
#     attempted afterward only if ALL of them bridged)
#
# Scope (deliberately narrow, matching xp2f.py's own "narrow first cut"
# philosophy): the TARGET function -- the only one directly exposed to
# Python via f2py -- must be scalar-only, or gets one further allowance:
# a rank-1 NumPy array argument, and/or a rank-1 array return whose
# length is a simple function of the target's own arguments (e.g.
# `np.array([... for k in range(1, n + 1)])` -- length n) -- rewritten
# (see rewrite_target_for_f2py) into an f2py-bridgeable explicit-shape
# form, paired with a generated `.f2py_f2cmap` file (see
# write_f2cmap_file) that a confirmed, otherwise-silent f2py precision
# bug needs. A data-dependent return length (e.g. "the primes in this
# array" -- not a simple function of the input) needs a different
# technique this tool doesn't implement: a bridge subroutine, over-
# allocated to a size PROVABLY no larger than some input (for a
# filter/subset result, the input's own length), paired with a count
# output the Python wrapper trims to. A function outside all of this is
# rejected with a clear message rather than silently producing something
# broken.
#
# A DEPENDENCY the target transitively calls has NO such restriction --
# an array argument/result, or even a derived type, is completely
# ordinary Fortran for an internal Fortran-to-Fortran call, needing no
# f2py-facing rewrite at all. It's simply kept PRIVATE in the trimmed
# module (never itself exposed to Python) so f2py's own Fortran cracker
# -- which only ever attempts to wrap a module's PUBLIC surface --
# never gets anywhere near its signature.

from __future__ import annotations

import argparse
import ast
import difflib
import math
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import xp2f

PYTHON_MOD_PATH = Path(__file__).resolve().with_name("python.f90")

MOD_START_RE = re.compile(r"^\s*module\s+([a-z]\w*)\s*$", re.IGNORECASE)
MOD_END_RE = re.compile(r"^\s*end\s+module\b", re.IGNORECASE)
CONTAINS_RE = re.compile(r"^\s*contains\s*$", re.IGNORECASE)
# The parenthesized part allows ONE level of nesting -- needed for a
# dynamic-length character function like `character(len=len(s))`
# (python.f90's own `to_lower`), whose type spec's own inner `len=...`
# argument is itself a call with its own parens. A plain `[^()]*` (no
# nesting at all) can't match past the first `(` it hits inside, so
# `to_lower`'s own signature line went unrecognized by PROC_START_RE
# entirely -- confirmed via inline_python_mod_helpers failing to find it
# in parse_module's own procedure table despite it being an ordinary,
# self-contained function.
_FUNC_TYPE_PREFIX_RE = (
    r"(?:real|integer|logical|character|complex|double\s+precision)"
    r"(?:\s*\((?:[^()]|\([^()]*\))*\)|\s*\*\s*\d+)?"
)
PROC_START_RE = re.compile(
    r"^\s*(?:(?:pure|elemental|impure|recursive)\s+)*"
    rf"(?:{_FUNC_TYPE_PREFIX_RE}\s+)?"
    r"(function|subroutine)\s+([a-z]\w*)",
    re.IGNORECASE,
)
PROC_END_RE = re.compile(r"^\s*end\s+(function|subroutine)\s+([a-z]\w*)", re.IGNORECASE)
# Tracked so a callback's own nested `end function` (inside an abstract
# interface block declared in the enclosing procedure's own declaration
# section) is never mistaken for the enclosing procedure's own end --
# the same hazard fixed this session in several other line-scanning
# passes (declaration coalescing, blank-line spacing, ...).
INTERFACE_START_RE = re.compile(r"^\s*(?:abstract\s+)?interface\b", re.IGNORECASE)
INTERFACE_END_RE = re.compile(r"^\s*end\s+interface\b", re.IGNORECASE)
PUBLIC_RE = re.compile(r"^(\s*public\s*::\s*)(.+)$", re.IGNORECASE)
ARRAY_DECL_RE = re.compile(r"\bdimension\b|::[^\n]*\(\s*:", re.IGNORECASE)
DERIVED_TYPE_RE = re.compile(r"^\s*type\s*\(", re.IGNORECASE)
SIG_RE = re.compile(
    r"^(?P<prefix>\s*(?:(?:pure|elemental|impure|recursive)\s+)*)"
    r"(?P<kind>function|subroutine)\s+(?P<name>[a-z]\w*)\s*"
    r"\((?P<args>[^)]*)\)"
    r"(?P<result>\s*result\s*\(\s*[a-z_]\w*\s*\))?"
    r"\s*$",
    re.IGNORECASE,
)
RESULT_NAME_RE = re.compile(r"\bresult\s*\(\s*([a-z_]\w*)\s*\)", re.IGNORECASE)
# A single arange_int(start, stop, step) call's length, wrapped in size(...)
# -- this project's own idiomatic Fortran for a Python `range(...)`-length
# comprehension (see rewrite_listcomp_array_assign_calls_to_loop and
# expr()'s own ListComp lowering). Recognized so an array RESULT's
# allocate() size expression built from it can be symbolically rewritten
# into an equivalent closed-form expression legal in a dummy argument's
# own explicit-shape bound (a specification expression) -- confirmed
# empirically that gfortran rejects `size(some_pure_function_call(...))`
# there outright ("'array' argument of 'size' intrinsic ... must be an
# array"), even though the same call is perfectly fine as an ordinary
# executable-statement argument to size().
RANGE_LEN_RE = re.compile(r"^\s*size\s*\(\s*arange_int\s*\((.*)\)\s*\)\s*$", re.IGNORECASE)


def _split_top_level(text, sep=","):
    """Split `text` on `sep` at paren/bracket-depth 0 only."""
    parts = []
    depth = 0
    cur = []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts]


# Recognized python.f90 builtin array-returning helpers whose OWN result
# length is a simple, safe function of their own call-site argument TEXT
# -- keyed by the (generic) call name xp2f.py's own codegen emits. Used
# by _infer_rank1_size below to resolve an array result's size through a
# call to one of these, never through a call to some OTHER, user-defined
# dependency function (which would need inspecting THAT function's own
# body -- a genuinely open-ended, cross-procedure analysis this doesn't
# attempt; see the module docstring's discussion of what's out of scope).
#
# `_ARRAY_HELPER_ARG_IS_SIZE`: the result's length IS that argument's own
# VALUE (never its own `size(...)`) -- e.g. `rnorm(k)` (python.f90's
# `rnorm1`, reached through the generic `rnorm` interface) has length k.
_ARRAY_HELPER_ARG_IS_SIZE = {"rnorm": 0}
# `_ARRAY_HELPER_ARG_LIKE_SIZE`: the result's length equals that
# argument's OWN length -- e.g. `lfilter_real(b, a, x[, zi])`
# (python.f90's scipy.signal.lfilter port) has the same length as `x`.
_ARRAY_HELPER_ARG_LIKE_SIZE = {"lfilter_real": 2}
# Ordinary elementwise Fortran math intrinsics: applied to a single
# argument, the RESULT has exactly that argument's own shape (a basic
# Fortran language guarantee for any elementwise intrinsic, unlike the
# two registries above -- which need special, function-specific
# knowledge). Used so e.g. `log(S / K)` is recognized as having the same
# length as `S / K` itself, without needing its own entry.
_ELEMENTWISE_UNARY_INTRINSICS = {
    "abs", "sqrt", "exp", "log", "log10", "erf", "erfc",
    "sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh",
    "real", "aint", "anint", "nint", "int", "dble",
}
_NUM_LITERAL_RE = re.compile(
    r"^[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[deDE][+-]?\d+)?(?:_[a-z]\w*)?$", re.IGNORECASE
)
_ARRAY_CTOR_TYPE_PREFIX_RE = re.compile(r"^\s*[a-z]\w*\s*(?:\([^()]*\))?\s*::\s*(.*)$", re.IGNORECASE | re.DOTALL)

# Sentinel returned by _infer_rank1_size for an expression PROVABLY
# scalar (a numeric literal, a name known to be scalar-typed, or a
# single-element subscript `arr(i)` of a known array) -- distinct from
# None (genuinely unresolvable: might itself be an array this walk just
# can't identify). The distinction matters for elementwise binary ops:
# scalar-combined-with-scalar is safely still scalar, but
# unresolvable-combined-with-anything must stay unresolved rather than
# silently guessed at.
_SCALAR = object()


def _split_top_level_op(expr, ops):
    """Find the LAST occurrence of one of the operator token strings in
    `ops` (e.g. `("+", "-")`, `("*", "/")`, or `("**",)`) at paren/
    bracket-depth 0 that is a genuine BINARY operator -- not a unary
    +/- (at the very start of `expr`, or right after another operator/
    open-paren/open-bracket/comma, or part of a `1.0e-5`/`1.0d+3`
    exponent), and, when looking for a lone `*`, not either `*` of a
    `**` (a SEPARATE call with `ops=("**",)` is how `**` itself is
    found -- kept as its own token so it's never confused with two
    single `*`s the way scanning char-by-char would). Returns
    `(left, op, right)`, or None if there's no such split. Any single
    valid split (this picks the rightmost) is enough for size-inference
    purposes -- true operator associativity doesn't matter here, since
    each operand is resolved independently.
    """
    depth = 0
    n = len(expr)
    result = None
    i = 0
    while i < n:
        ch = expr[i]
        if ch in "([":
            depth += 1
            i += 1
            continue
        if ch in ")]":
            depth -= 1
            i += 1
            continue
        if depth != 0:
            i += 1
            continue
        op = next((o for o in ops if expr[i : i + len(o)] == o), None)
        if op is None:
            i += 1
            continue
        prev = expr[:i].rstrip()
        if op in ("+", "-"):
            if not prev or prev[-1] in "+-*/,([":
                i += 1
                continue  # unary
            if len(prev) >= 2 and prev[-1].lower() in "ed" and (prev[-2].isdigit() or prev[-2] == "."):
                i += 1
                continue  # exponent marker, e.g. "1.0e-5" / "1.0d+3"
        if op == "*":
            if expr[i : i + 2] == "**" or (i > 0 and expr[i - 1] == "*"):
                i += 1
                continue  # part of a '**', not a lone '*'
        result = (expr[:i], op, expr[i + len(op) :])
        i += len(op)
    return result


def _combine_elementwise(left, right, size_of, scalar_names, dependency_resolver=None):
    """For two operands of a binary elementwise Fortran arithmetic op,
    return whichever operand's own length resolves as a genuine rank-1
    array size (NumPy/Fortran broadcasting: combining an array with a
    scalar preserves the array's own length -- and if BOTH resolve to a
    real size, the original code could only be valid Fortran if they're
    equal at runtime, so either is equally correct to return). Returns
    `_SCALAR` only if BOTH operands are provably scalar (so the combined
    expression is too), or None if either side is genuinely unresolvable
    and neither side had a real size (might itself hide an array).
    """
    ls = _infer_rank1_size(left, size_of, scalar_names, dependency_resolver)
    if isinstance(ls, str):
        return ls
    rs = _infer_rank1_size(right, size_of, scalar_names, dependency_resolver)
    if isinstance(rs, str):
        return rs
    if ls is _SCALAR and rs is _SCALAR:
        return _SCALAR
    return None


def _infer_rank1_size(expr, size_of, scalar_names, dependency_resolver=None):
    """Try to symbolically classify the rank-1-or-scalar Fortran
    expression `expr`, given `size_of` (a dict mapping a lowercase
    local/dummy array NAME already known to have a safe, caller-visible
    size expression to that expression's own text) and `scalar_names`
    (lowercase names already known to be scalar-typed). Returns one of:
      - a size expression STRING, if `expr` is provably rank-1 array-
        valued with that length;
      - the `_SCALAR` sentinel, if `expr` is provably scalar-valued
        (never itself an array);
      - None, if `expr` isn't one of the forms recognized here --
        conservative on purpose: an unrecognized form is left unresolved
        rather than guessed at, same spirit as the rest of this module.

    Recognizes, recursively:
      - a numeric literal (`_SCALAR`).
      - a bare NAME: a real size if in `size_of`, `_SCALAR` if in
        `scalar_names`, else unresolvable.
      - unary `-EXPR`, and a single EXPRESSION wholly wrapped in one
        balanced `(...)` pair (both rank/scalar-ness-preserving).
      - a binary elementwise arithmetic op (`+ - * / **`) at paren/
        bracket-depth 0, combined via `_combine_elementwise` above.
      - an array constructor `[TYPE :: part, part, ...]` or
        `[part, ...]` -- total length is the SUM of each part's own
        length (`_SCALAR` parts contribute exactly 1 each; any part that
        resolves to None bails the WHOLE constructor, since it might
        itself be an unresolvable array).
      - a slice `BASE(A:B)` -- length `(B) - (A) + 1`, with any
        `size(BASE)` appearing in A or B substituted for BASE's own
        already-resolved size first (e.g. `xfull(burnin + 1:
        size(xfull))`).
      - a single-argument call to one of the ordinary elementwise math
        intrinsics in `_ELEMENTWISE_UNARY_INTRINSICS` (rank/scalar-ness-
        preserving), or to one of the small set of recognized python.f90
        builtin array-returning helpers in `_ARRAY_HELPER_ARG_IS_SIZE`/
        `_ARRAY_HELPER_ARG_LIKE_SIZE` above.
      - `NAME(single_subscript)` where NAME is a known array (in
        `size_of`) -- `_SCALAR` (an ordinary single-element access).
      - a call to some OTHER, locally-defined dependency procedure, IF
        `dependency_resolver` is given -- see
        _make_local_dependency_resolver's own docstring.
    """
    expr = expr.strip()
    if not expr:
        return None

    if _NUM_LITERAL_RE.match(expr):
        return _SCALAR

    m = re.match(r"^([a-z_]\w*)$", expr, re.IGNORECASE)
    if m:
        nm = m.group(1).lower()
        if nm in size_of:
            return size_of[nm]
        if nm in scalar_names:
            return _SCALAR
        return None

    m = re.match(r"^-\s*(.+)$", expr, re.DOTALL)
    if m:
        return _infer_rank1_size(m.group(1), size_of, scalar_names, dependency_resolver)

    if expr.startswith("(") and expr.endswith(")"):
        depth = 0
        whole = True
        for i, ch in enumerate(expr):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0 and i != len(expr) - 1:
                    whole = False
                    break
        if whole:
            return _infer_rank1_size(expr[1:-1], size_of, scalar_names, dependency_resolver)

    for ops in (("+", "-"), ("*", "/"), ("**",)):
        split = _split_top_level_op(expr, ops)
        if split:
            left, _op, right = split
            return _combine_elementwise(left, right, size_of, scalar_names, dependency_resolver)

    m = re.match(r"^\[\s*(.*)\]\s*$", expr, re.DOTALL)
    if m:
        body = m.group(1)
        tm = _ARRAY_CTOR_TYPE_PREFIX_RE.match(body)
        if tm:
            body = tm.group(1)
        parts = [p for p in _split_top_level(body) if p.strip()]
        if not parts:
            return "0"
        sizes = []
        for part in parts:
            s = _infer_rank1_size(part.strip(), size_of, scalar_names, dependency_resolver)
            if s is None:
                return None  # might itself be an unresolvable array -- bail
            sizes.append("1" if s is _SCALAR else f"({s})")
        return " + ".join(sizes)

    m = re.match(r"^([a-z_]\w*)\s*\((.*)\)\s*$", expr, re.IGNORECASE | re.DOTALL)
    if m:
        base = m.group(1)
        inner = m.group(2)
        colon_parts = _split_top_level(inner, sep=":")
        if len(colon_parts) == 2:
            a_expr, b_expr = colon_parts
            base_size = size_of.get(base.lower())

            def _sub_size(text):
                if base_size is None:
                    return text
                return re.sub(
                    rf"\bsize\s*\(\s*{re.escape(base)}\s*\)",
                    f"({base_size})",
                    text,
                    flags=re.IGNORECASE,
                )

            return f"({_sub_size(b_expr)}) - ({_sub_size(a_expr)}) + 1"
        if len(colon_parts) == 1:
            fname = base.lower()
            arg_parts = _split_top_level(inner) if inner.strip() else []
            if fname in _ARRAY_HELPER_ARG_IS_SIZE:
                idx = _ARRAY_HELPER_ARG_IS_SIZE[fname]
                return arg_parts[idx].strip() if idx < len(arg_parts) else None
            if fname in _ARRAY_HELPER_ARG_LIKE_SIZE:
                idx = _ARRAY_HELPER_ARG_LIKE_SIZE[fname]
                return (
                    _infer_rank1_size(arg_parts[idx], size_of, scalar_names, dependency_resolver)
                    if idx < len(arg_parts)
                    else None
                )
            if fname in _ELEMENTWISE_UNARY_INTRINSICS and len(arg_parts) == 1:
                return _infer_rank1_size(arg_parts[0], size_of, scalar_names, dependency_resolver)
            if fname in size_of:
                return _SCALAR  # an ordinary single-element subscript of a known array
            if dependency_resolver is not None:
                resolved = dependency_resolver(fname, arg_parts)
                if isinstance(resolved, str):
                    return resolved
            return None

    return None


class UnsupportedFunction(Exception):
    """Raised when the target function's own Fortran translation falls
    outside what a thin f2py wrapper can bridge for free (see module
    docstring)."""


def _strip_comment(line: str) -> str:
    return line.split("!", 1)[0]


def parse_module(f90_text: str):
    """Locate the single `module NAME ... contains ... end module` block
    xp2f.py's structured output always produces, and every procedure
    (function/subroutine) defined in it.

    Returns (mod_name, header_lines, all_lines, procedures) where
    procedures maps each procedure's lowercase name to its own
    (start_line_idx, end_line_idx) span, inclusive, covering its own
    signature line through its own `end function`/`end subroutine` line.
    """
    lines = f90_text.splitlines()
    mod_name = None
    mod_start = mod_end = contains_idx = None
    for i, ln in enumerate(lines):
        code = _strip_comment(ln)
        if mod_start is None:
            m = MOD_START_RE.match(code)
            if m:
                mod_name = m.group(1)
                mod_start = i
            continue
        if contains_idx is None and CONTAINS_RE.match(code):
            contains_idx = i
        if MOD_END_RE.match(code):
            mod_end = i
            break
    if mod_start is None or mod_end is None or contains_idx is None:
        raise UnsupportedFunction(
            "the translated output has no `module ... contains ... end module` "
            "block to extract a procedure from -- either xp2f.py used --flat-style "
            "output (a single program, no callable module) for this script, or the "
            "target function was simple enough to be inlined directly into the "
            "program body rather than emitted as its own callable procedure"
        )

    procedures: dict[str, tuple[int, int]] = {}
    i = contains_idx + 1
    depth = 0
    cur_name = None
    cur_start = None
    while i < mod_end:
        code = _strip_comment(lines[i])
        if INTERFACE_START_RE.match(code):
            depth += 1
        elif INTERFACE_END_RE.match(code):
            depth = max(0, depth - 1)
        elif depth == 0:
            if cur_name is None:
                m = PROC_START_RE.match(code)
                if m:
                    cur_name = m.group(2)
                    cur_start = i
            else:
                m = PROC_END_RE.match(code)
                if m and m.group(2).lower() == cur_name.lower():
                    procedures[cur_name.lower()] = (cur_start, i)
                    cur_name = None
        i += 1

    header = lines[mod_start:contains_idx]
    return mod_name, header, lines, procedures


def find_calls(lines, start, end, known_names, self_name):
    """Which OTHER known procedure names does lines[start:end+1] call?
    A conservative substring/regex scan (word-boundary matched), matching
    this project's own established style for this kind of line-level
    pass -- not a full expression parser, but sufficient to find a call
    `NAME(...)` anywhere in the procedure body.
    """
    text = "\n".join(lines[start : end + 1])
    found = set()
    for name in known_names:
        if name == self_name:
            continue
        if re.search(rf"\b{re.escape(name)}\s*\(", text, re.IGNORECASE):
            found.add(name)
    return found


def collect_closure(target_name, procedures, lines):
    target = target_name.lower()
    if target not in procedures:
        raise UnsupportedFunction(
            f"function {target_name!r} was not found as a top-level procedure in "
            f"xp2f.py's own translation of this script (translated names: "
            f"{', '.join(sorted(procedures)) or '(none)'})"
        )
    known = set(procedures.keys())
    needed = {target}
    frontier = [target]
    while frontier:
        nm = frontier.pop()
        start, end = procedures[nm]
        for dep in find_calls(lines, start, end, known, nm):
            if dep not in needed:
                needed.add(dep)
                frontier.append(dep)
    return needed


def check_f2py_compatible(lines, start, end, name):
    """Reject (with a clear reason) the TARGET procedure itself if its own
    signature line declares an array-shaped or derived-type dummy
    argument or result that rewrite_target_for_f2py couldn't rewrite away
    (e.g. rank >= 2, or a residual shape none of its own rewrites cover)
    -- outside what a thin, no-custom-marshalling f2py wrapper can
    bridge, since the target itself must be directly exposed to Python.
    A DEPENDENCY is never checked here at all -- kept PRIVATE in the
    trimmed module instead (see main()'s own comment where every
    dependency is stripped from `public ::`), which sidesteps this
    entirely: f2py's own Fortran cracker only ever attempts to wrap a
    module's public surface, so a private dependency's own array-shaped
    or derived-type signature never gets anywhere near it.

    Scoped to just the declaration section (signature line through the
    first executable-looking line is overkill to detect precisely here,
    so this conservatively scans the WHOLE procedure body text instead --
    a false "unsupported" from matching something in an unrelated context
    only costs an unnecessary rejection, never a wrong bridge).

    Skips content inside a nested `interface ... end interface` block (a
    callback dummy argument's own abstract interface, e.g. `procedure(f_cb_if)
    :: f`) -- that interface's own dummy arguments (e.g. `x(:)`) are a
    DIFFERENT declaration than the target's own outer one of the same name,
    and f2py's own callback-marshalling handles it directly; only the
    target's own outer signature is what a thin f2py wrapper must bridge.
    Confirmed a real bug without this: the callback interface's own nested
    `real(kind=dp), intent(in) :: x(:)` line (left correctly untouched, since
    it's the callback's OWN abstract signature, not the target's) was
    mistaken for an unrewritten array-shaped dummy of the TARGET itself,
    rejecting the whole bridge even after rewrite_target_for_f2py correctly
    rewrote the target's own outer `x(:)`.
    """
    sig_line = _strip_comment(lines[start])
    # A FUNCTION's own result variable is array-shaped exactly when its own
    # declaration line is array-shaped -- but unlike a dummy argument, a
    # result variable's declaration never carries an `intent` attribute (it
    # isn't a dummy), so the `"intent" in code` check below can't see it.
    # Resolve its name from an explicit `result(NAME)` clause, or fall back
    # to the function's own name when there is none.
    result_name = None
    m_func = re.match(r"^\s*(?:(?:pure|elemental|impure|recursive)\s+)*function\s+([a-z]\w*)", sig_line, re.IGNORECASE)
    if m_func:
        m_result = re.search(r"\bresult\s*\(\s*([a-z_]\w*)\s*\)", sig_line, re.IGNORECASE)
        result_name = (m_result.group(1) if m_result else m_func.group(1)).lower()

    in_interface = False
    for i in range(start, end + 1):
        code = _strip_comment(lines[i])
        if INTERFACE_START_RE.match(code):
            in_interface = True
            continue
        if INTERFACE_END_RE.match(code):
            in_interface = False
            continue
        if in_interface:
            continue
        if DERIVED_TYPE_RE.match(code.strip()):
            raise UnsupportedFunction(
                f"{name!r} uses a derived type (line: {code.strip()!r}) -- not "
                f"bridgeable by a thin f2py wrapper yet (e.g. a pandas DataFrame "
                f"has no path back into a real pandas object this way)"
            )
        if not ARRAY_DECL_RE.search(code):
            continue
        is_result_decl = result_name is not None and re.search(
            rf"::\s*{re.escape(result_name)}\b", code, re.IGNORECASE
        )
        if "intent" in code.lower() or is_result_decl:
            raise UnsupportedFunction(
                f"{name!r} has an array-shaped dummy argument or result (line: "
                f"{code.strip()!r}) not covered by rewrite_target_for_f2py's own "
                f"rewrites (e.g. rank >= 2, or an allocatable result whose size "
                f"isn't a simple function of the arguments) -- out of scope for "
                f"this first version, since the target itself must be exposed to "
                f"Python directly (unlike a dependency, which is kept private and "
                f"never needs this)."
            )


def _find_top_level_double_colon(code):
    """Return the index of the first `::` token at paren/bracket-depth 0
    in `code`, or None if there isn't one -- distinguishes a genuine
    Fortran declaration's own `TYPE, ATTRS :: names` separator from a
    `::` that merely appears NESTED inside something else on the same
    line, e.g. an array constructor's own type-spec (`[real(kind=dp) ::
    1.0_dp, -ar]`). Confirmed a real bug without this distinction:
    naively treating ANY line containing `::` as a declaration split
    `ar_poly = [real(kind=dp) :: [1.0_dp], -ar]` (an ordinary ASSIGNMENT,
    not a declaration at all) at its own top-level comma, producing two
    broken, unbalanced lines ("syntax error in array constructor").
    """
    depth = 0
    i = 0
    n = len(code)
    while i < n - 1:
        ch = code[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and ch == ":" and code[i + 1] == ":":
            return i
        i += 1
    return None


def _split_multi_name_decls(target_lines):
    """Normalize any declaration line listing SEVERAL names --
    `TYPE, ATTR1, ATTR2 :: name1(shape1), name2(shape2), ...` -- into one
    line PER name, each carrying the exact same type/attribute prefix. A
    no-op for a line that already declares just one name, OR that isn't
    actually a declaration at all (see _find_top_level_double_colon).

    Several downstream per-name rewrites (see _convert_array_result)
    modify a matched declaration line AS A WHOLE, which is only safe
    when it declares exactly one name -- confirmed via a real bug
    (examples/xsim_fit_nagarch.py's own `simulate_nagarch`, whose `r`/
    `h` outputs share one `real(kind=dp), allocatable, intent(out) ::
    r(:), h(:)` line): rewriting `r`'s own shape collaterally stripped
    the SHARED `allocatable` attribute off the WHOLE line, silently
    leaving `h` unresolved -- worse, no longer even recognized as
    needing this rewrite at all, since `h`'s own "is this allocatable?"
    check then failed too, on the very next loop iteration.
    """
    out = []
    for ln in target_lines:
        code = _strip_comment(ln)
        idx = _find_top_level_double_colon(code)
        if idx is None:
            out.append(ln)
            continue
        prefix, names_part = code[:idx], code[idx + 2 :]
        names = _split_top_level(names_part)
        if len(names) <= 1:
            out.append(ln)
            continue
        trailing = ln[len(code) :]  # preserve any trailing comment text verbatim
        for nm in names:
            out.append(f"{prefix}:: {nm.strip()}")
        out[-1] += trailing
    return out


def _derive_no_alloc_array_size(proc_lines, name, arg_names, scalar_names, dependency_resolver=None):
    """Try to derive `name`'s own caller-visible array-result size
    expression from `proc_lines` (an already merge/split-normalized copy
    of ONE procedure's own lines) when there's no `allocate(name(...))`
    statement at all -- the "no allocate() fallback" set of forms
    _infer_rank1_size recognizes (a whole-array copy/slice, an array
    constructor, elementwise arithmetic, a recognized python.f90 helper
    call, and -- if `dependency_resolver` is given -- a call to some
    OTHER, locally-defined dependency procedure). Shared by
    _convert_array_result (for the xpfunc2f.py TARGET's own array
    result) and _make_local_dependency_resolver (recursively, for a
    DEPENDENCY's own array result, when the target's own size expression
    calls it) -- read-only, never mutates `proc_lines`. Returns a size
    expression string in terms of `arg_names` (`proc_lines`'s OWN dummy
    arguments), or None if not derivable this way.
    """

    def _find_decl(nm):
        for i in range(1, len(proc_lines)):
            code = _strip_comment(proc_lines[i])
            if "::" not in code:
                continue
            m = re.search(rf"(?:::|,)\s*({re.escape(nm)})\b(\s*\(([^()]*)\))?", code, re.IGNORECASE)
            if m:
                return i, m
        return None, None

    assign_re = re.compile(r"^\s*([a-z_]\w*)\s*=\s*(.+?)\s*$", re.IGNORECASE)
    size_of = {}
    for a in arg_names:
        a_i, a_m = _find_decl(a)
        if a_i is not None and a_m.group(3) and a_m.group(3).strip() != ":":
            size_of[a.lower()] = a_m.group(3).strip()

    # A local PARAMETER (compile-time-constant) array, declared `TYPE,
    # parameter :: NAME(*) = [literal, ...]` -- its own size is exactly
    # its own initializer's, resolvable the same way as any other array
    # constructor.
    param_re = re.compile(r"^\s*.*?\bparameter\b.*?::\s*([a-z_]\w*)\s*\(\s*\*\s*\)\s*=\s*(.+)$", re.IGNORECASE)
    for i in range(1, len(proc_lines)):
        pm = param_re.match(_strip_comment(proc_lines[i]))
        if pm and pm.group(1).lower() not in size_of:
            psize = _infer_rank1_size(pm.group(2), size_of, scalar_names, dependency_resolver)
            if isinstance(psize, str):
                size_of[pm.group(1).lower()] = psize

    for i in range(1, len(proc_lines)):
        lm = assign_re.match(_strip_comment(proc_lines[i]))
        if not lm:
            continue
        lname = lm.group(1)
        if lname.lower() == name.lower() or lname.lower() in size_of:
            continue  # `name` itself resolved below; already known otherwise
        li, lm2 = _find_decl(lname)
        if li is None or lm2.group(3) is None or lm2.group(3).strip() != ":":
            continue  # not a rank-1 allocatable local
        resolved = _infer_rank1_size(lm.group(2), size_of, scalar_names, dependency_resolver)
        if isinstance(resolved, str):
            size_of[lname.lower()] = resolved

    name_rhs = None
    for i in range(1, len(proc_lines)):
        am = assign_re.match(_strip_comment(proc_lines[i]))
        if am and am.group(1).lower() == name.lower():
            name_rhs = am.group(2)
    if name_rhs is not None:
        resolved = _infer_rank1_size(name_rhs, size_of, scalar_names, dependency_resolver)
        if isinstance(resolved, str):
            return resolved
    return None


def _make_local_dependency_resolver(lines, procedures, target_name):
    """Build a `_infer_rank1_size`-compatible `dependency_resolver`:
    given a call `fname(arg_texts...)` to some OTHER procedure defined
    in the SAME already-transpiled module (`procedures`, from
    parse_module) -- not the xpfunc2f.py TARGET itself, and only tried
    after every recognized python.f90 helper/intrinsic already failed to
    match -- try to derive THAT procedure's own array result size
    (recursively, via the exact same set of forms _infer_rank1_size and
    _derive_no_alloc_array_size already recognize, including a call to
    yet ANOTHER local dependency), then substitute its own dummy
    argument names for the ACTUAL argument text at THIS call site.

    Confirmed a real, common shape: examples/xarma_nagarch_fit.py's own
    `simulate_arma_nagarch` computes `eps = simulate_nagarch_noise(n +
    burnin, omega, alpha, theta, beta)`, where `simulate_nagarch_noise`
    is a plain, locally-defined function with `allocate(eps(n))` --
    its own length is simply its own first argument, `n`. Substituting
    the call site's own actual first argument (`n + burnin`) for that
    gives `simulate_arma_nagarch`'s own use of `eps` a caller-visible
    size, with NO cross-procedure ambiguity: the dependency's own
    signature positionally maps 1:1 onto the call site's own arguments.

    Conservative on purpose, matching this project's own established
    style: only a plain FUNCTION with a rank-1 allocatable result is
    handled (a subroutine's own multi-value-return convention is a
    single-source-of-truth ambiguity this doesn't attempt -- WHICH
    intent(out) dummy is "the" array result a caller-side expression
    means isn't well-defined the way a function's own single result is);
    a result whose size expression references anything other than the
    dependency's OWN dummy arguments (a value computed inside ITS OWN
    body) is rejected, the same "not knowable ahead of the call" check
    _convert_array_result already applies to the xpfunc2f.py target
    itself. A dependency's own resolution is cached (memoized) across
    repeated calls, and guarded against infinite recursion for a
    (theoretical) circular dependency chain.
    """
    cache: dict[str, tuple[list[str], str] | None] = {}

    def _resolve(fname, arg_texts):
        key = fname.lower()
        if key == target_name.lower() or key not in procedures:
            return None
        if key not in cache:
            cache[key] = None  # guards against infinite recursion for a circular call chain
            cache[key] = _resolve_one(key)
        cached = cache[key]
        if cached is None:
            return None
        dep_arg_names, size_expr = cached
        if len(arg_texts) < len(dep_arg_names):
            return None  # fewer args than the dependency's own signature (e.g. an omitted optional)
        substituted = size_expr
        for dep_arg, actual_text in zip(dep_arg_names, arg_texts):
            substituted = re.sub(
                rf"\b{re.escape(dep_arg)}\b", f"({actual_text.strip()})", substituted, flags=re.IGNORECASE
            )
        return substituted

    def _resolve_one(key):
        dep_start, dep_end = procedures[key]
        dep_lines = _split_multi_name_decls(_merge_continuations(list(lines[dep_start : dep_end + 1])))
        dep_sig_m = SIG_RE.match(_strip_comment(dep_lines[0]))
        if not dep_sig_m or dep_sig_m.group("kind").lower() != "function":
            return None
        dep_arg_names = [a for a in _split_top_level(dep_sig_m.group("args")) if a]
        dep_result_name = key
        if dep_sig_m.group("result"):
            rm = RESULT_NAME_RE.search(dep_sig_m.group("result"))
            if rm:
                dep_result_name = rm.group(1)

        dep_scalar_names = set()
        for i in range(1, len(dep_lines)):
            code = _strip_comment(dep_lines[i])
            if "::" not in code:
                continue
            decl_part = code.split("::", 1)[1]
            for decl in _split_top_level(decl_part):
                dm = re.match(r"^\s*([a-z_]\w*)\s*(\([^()]*\))?\s*$", decl.strip(), re.IGNORECASE)
                if dm and not dm.group(2):
                    dep_scalar_names.add(dm.group(1).lower())

        dep_ri, dep_rm = None, None
        for i in range(1, len(dep_lines)):
            code = _strip_comment(dep_lines[i])
            if "::" not in code:
                continue
            rm2 = re.search(rf"(?:::|,)\s*({re.escape(dep_result_name)})\b(\s*\(([^()]*)\))?", code, re.IGNORECASE)
            if rm2:
                dep_ri, dep_rm = i, rm2
                break
        if dep_ri is None or dep_rm.group(3) is None or "," in dep_rm.group(3) or dep_rm.group(3).strip() != ":":
            return None  # not a plain rank-1 allocatable result -- out of scope here

        size_expr = None
        alloc_stmt_re = re.compile(r"^\s*allocate\s*\(", re.IGNORECASE)
        for i in range(1, len(dep_lines)):
            code = _strip_comment(dep_lines[i])
            pm = alloc_stmt_re.match(code)
            if not pm:
                continue
            start = pm.end()
            depth = 1
            j = start
            while j < len(code) and depth > 0:
                if code[j] == "(":
                    depth += 1
                elif code[j] == ")":
                    depth -= 1
                j += 1
            if depth != 0:
                continue
            inner = code[start : j - 1]
            for item in _split_top_level(inner):
                im = re.match(
                    rf"^\s*{re.escape(dep_result_name)}\s*\((.*)\)\s*$", item.strip(), re.IGNORECASE | re.DOTALL
                )
                if im:
                    size_expr = im.group(1).strip()
                    break
            if size_expr is not None:
                break
        if size_expr is None:
            size_expr = _derive_no_alloc_array_size(
                dep_lines, dep_result_name, dep_arg_names, dep_scalar_names, dependency_resolver=_resolve
            )
        if size_expr is None:
            return None

        declared = {n.lower() for n in dep_arg_names} | {dep_result_name.lower()}
        local_names = set()
        for i in range(1, len(dep_lines)):
            code = _strip_comment(dep_lines[i])
            if "::" not in code or "intent" in code.lower():
                continue
            decl_part = code.split("::", 1)[1]
            for decl in _split_top_level(decl_part):
                dm = re.match(r"^\s*([a-z_]\w*)", decl, re.IGNORECASE)
                if dm and dm.group(1).lower() not in declared:
                    local_names.add(dm.group(1).lower())
        if any(re.search(rf"\b{re.escape(nm)}\b", size_expr, re.IGNORECASE) for nm in local_names):
            return None  # depends on a value computed inside the dependency's OWN body
        if "size(" in size_expr.lower():
            return None

        return dep_arg_names, size_expr

    return _resolve


def rewrite_target_for_f2py(lines, start, end, target_name, procedures=None):
    """Rewrite the TARGET procedure's own array-shaped dummy arguments and
    (if a function) array-shaped allocatable result into f2py-bridgeable
    explicit-shape forms, in an ISOLATED copy of its own lines -- never
    touching any dependency procedure, which stays exactly as xp2f.py
    emitted it. Only the TARGET needs this: it alone is exposed directly
    to Python, so f2py's own C-shim needs its array shapes explicit. A
    dependency is only ever called internally (ordinary Fortran-to-
    Fortran, no f2py-facing rewrite needed at all) and is kept PRIVATE in
    the trimmed module precisely so f2py's own Fortran cracker never
    tries to wrap it in the first place (see main()'s own comment where
    every dependency is stripped from `public ::`).

    Three rewrites, applied only when provably safe:

    1. Each rank-1 ASSUMED-SHAPE array dummy argument `name(:)` becomes
       explicit-shape `name(SYNTH)`, with a new `integer, intent(in) ::
       SYNTH` dummy appended to the signature (f2py auto-infers it from
       the array's own shape at the call site -- invisible to the
       Python-facing wrapper, which never lists it). Confirmed
       empirically: an array argument alongside this project's `dp =
       real64` kind parameter silently mis-resolves to single precision
       UNLESS both this rewrite and a `.f2py_f2cmap` file (see
       write_f2cmap_file) are used together -- either alone still fails.

    2. A FUNCTION whose own result is a rank-1 ALLOCATABLE array becomes
       a SUBROUTINE with an explicit-shape `intent(out)` array result
       instead (mirroring this project's own existing convention for a
       multi-value Python return), ONLY when its own `allocate(RESULT
       (SIZE_EXPR))` size expression can be proven to reference nothing
       but the procedure's OWN dummy arguments (and this project's
       `arange_int`-range-length idiom, symbolically rewritten to an
       equivalent closed-form expression -- confirmed empirically that
       gfortran rejects the verbatim `size(arange_int(...))` call as a
       dummy argument's own explicit-shape bound: "'array' argument of
       'size' intrinsic ... must be an array") -- never a LOCAL variable
       computed inside the procedure's own body, which the CALLER cannot
       possibly know ahead of the call. A size expression that fails
       this check (e.g. depends on a runtime-computed count, as a
       genuine data-dependent filter/subset result would) is correctly
       left rejected -- see the module docstring's discussion of the
       "primes in an array" case, which needs a different technique
       (a bridge subroutine, over-allocated to a provable bound) not
       implemented by this rewrite.

    3. A FUNCTION whose own result is a plain SCALAR (any type) becomes
       a SUBROUTINE with that result as an `intent(out)` scalar instead,
       unconditionally -- f2py generates its own separate scalar-
       function wrapper file for any bridged FUNCTION (never a
       subroutine), and that generated wrapper references this
       project's `dp` kind parameter without importing it whenever a
       real(kind=dp) argument or result is involved ("has no IMPLICIT
       type") -- a real f2py code-generation bug confirmed with the
       simplest possible case (`def f(x): return x ** 2 - 2.0`, no array
       anywhere). Converting to a subroutine sidesteps it entirely.

    `procedures` (from parse_module, the FULL already-transpiled
    module's own name -> (start, end) table) is optional -- when given,
    an array result's own size expression may ALSO resolve through a
    call to some OTHER, locally-defined dependency procedure (see
    _make_local_dependency_resolver's own docstring), not just a
    recognized python.f90 helper.

    Returns (new_lines, had_array). Raises UnsupportedFunction for a
    genuinely unsupported shape (rank >= 2, or an unrecoverable result
    size expression) -- same exception type/spirit as
    check_f2py_compatible, so main()'s existing handling covers it too.
    """
    # Merged to ONE logical line per statement FIRST -- xp2f.py's own
    # line-wrapping means the SIGNATURE itself (a long dummy-argument
    # list, e.g. this project's own multi-value-return convention with
    # several outputs) or a declaration line can `&`-continue across
    # several physical lines. SIG_RE's own match against target_lines[0]
    # ALONE used to fail outright whenever the signature itself
    # continued this way (confirmed via examples/xarma_nagarch_fit.py's
    # own `simulate_arma_nagarch` and examples/xfit_hv_no_dates.py's own
    # `analyze_file`, silently leaving the WHOLE rewrite skipped, no
    # error at all -- had_array stayed False and the target's own
    # unrewritten assumed-shape argument then failed check_f2py_
    # compatible's later check instead, with a confusing "not covered by
    # rewrite_target_for_f2py's own rewrites" message even though this
    # array shape is exactly the ordinary case it DOES handle).
    target_lines = _split_multi_name_decls(_merge_continuations(list(lines[start : end + 1])))
    sig_m = SIG_RE.match(_strip_comment(target_lines[0]))
    if not sig_m:
        return target_lines, False

    is_function = sig_m.group("kind").lower() == "function"
    arg_names = [a for a in _split_top_level(sig_m.group("args")) if a]
    result_name = target_name
    if sig_m.group("result"):
        rm = RESULT_NAME_RE.search(sig_m.group("result"))
        if rm:
            result_name = rm.group(1)

    def _find_decl(name):
        # Skip content inside a nested `interface ... end interface` block
        # (a callback dummy argument's own abstract interface, e.g.
        # `procedure(f_cb_if) :: f`) -- that interface's own dummy arguments
        # (e.g. `x(:)`) are a DIFFERENT declaration than the TARGET's own
        # outer one of the same name, and must never be mistaken for it.
        # Confirmed a real bug without this: the callback interface's own
        # nested `x(:)` (appearing first, textually, since the interface
        # block precedes the target's own declaration section) was rewritten
        # instead of the target's own outer `x(:)`, leaving the latter
        # unrewritten and rejected later by check_f2py_compatible.
        in_interface = False
        for i in range(1, len(target_lines)):
            code = _strip_comment(target_lines[i])
            if INTERFACE_START_RE.match(code):
                in_interface = True
                continue
            if INTERFACE_END_RE.match(code):
                in_interface = False
                continue
            if in_interface:
                continue
            if "::" not in code:
                continue
            m = re.search(
                rf"(?:::|,)\s*({re.escape(name)})\b(\s*\(([^()]*)\))?", code, re.IGNORECASE
            )
            if m:
                return i, m
        return None, None

    existing_names = set()
    for ln in target_lines:
        for tok in re.findall(r"[A-Za-z_]\w*", ln):
            existing_names.add(tok.lower())

    synth_counter = [0]

    def _next_synth_name():
        while True:
            synth_counter[0] += 1
            cand = f"n_{synth_counter[0]}"
            if cand not in existing_names:
                existing_names.add(cand)
                return cand

    had_array = False
    extra_args = []

    # -- Rewrite each rank-1 assumed-shape array ARGUMENT --
    for name in arg_names:
        i, m = _find_decl(name)
        if i is None:
            continue
        shape = m.group(3)
        if shape is None:
            continue  # scalar dummy, nothing to do
        if "," in shape:
            raise UnsupportedFunction(
                f"{target_name!r} has a rank-2-or-higher array dummy argument "
                f"{name!r} (line: {target_lines[i].strip()!r}) -- only rank-1 "
                f"arrays are bridged for now"
            )
        decl_l = _strip_comment(target_lines[i]).lower()
        if "allocatable" in decl_l:
            # An ALLOCATABLE array dummy is one of this project's own
            # multi-value-return outputs (e.g. `backbin_rc_out_2(:)`),
            # never a true assumed-shape INPUT -- xp2f.py only emits
            # `allocatable` on an intent(out) result-like dummy, never
            # on an actual input/inout array argument. Handled by the
            # array-RESULT rewrite below instead (it needs a completely
            # different treatment: dropping `allocatable` and deriving
            # an explicit-shape bound, not just adding a synth size).
            continue
        if shape.strip() != ":" or "intent" not in decl_l:
            continue  # already explicit-shape, or not actually a dummy's own decl
        had_array = True
        synth = _next_synth_name()
        code = target_lines[i]
        target_lines[i] = re.sub(
            rf"\b{re.escape(name)}\s*\(\s*:\s*\)",
            f"{name}({synth})",
            code,
            count=1,
            flags=re.IGNORECASE,
        )
        extra_args.append(synth)
        target_lines.insert(i + 1, f"   integer, intent(in) :: {synth}")

    # -- Rewrite an array RESULT: a function's own named result, OR --
    # for a target that's already a subroutine, using this project's
    # own multi-value-return convention -- any of ITS intent(out)
    # dummies that is itself an allocatable rank-1 array (never a true
    # assumed-shape INPUT, so the argument loop above deliberately skips
    # it). Both cases need the identical explicit-shape/size-derivation
    # treatment, so it's factored into one helper below.
    made_subroutine = False

    # Names already known to be scalar-typed (no array shape at all) --
    # used only by _infer_rank1_size, to recognize a scalar entry inside
    # an array constructor (see its own docstring).
    scalar_names = set()
    for i in range(1, len(target_lines)):
        code = _strip_comment(target_lines[i])
        if "::" not in code:
            continue
        decl_part = code.split("::", 1)[1]
        for decl in _split_top_level(decl_part):
            dm = re.match(r"^\s*([a-z_]\w*)\s*(\([^()]*\))?\s*$", decl.strip(), re.IGNORECASE)
            if dm and not dm.group(2):
                scalar_names.add(dm.group(1).lower())

    # Lets an array result's own size expression ALSO resolve through a
    # call to some OTHER, locally-defined dependency procedure (see
    # _make_local_dependency_resolver's own docstring) -- only built
    # when the caller actually provided the full module's own procedure
    # table; None otherwise (_infer_rank1_size treats that identically
    # to "no such call recognized", the previous, more limited behavior).
    dependency_resolver = (
        _make_local_dependency_resolver(lines, procedures, target_name) if procedures is not None else None
    )

    def _convert_array_result(ri, name, rshape, is_new_arg=True):
        """Convert the allocatable rank-1 array result/output `name`
        (declared at target_lines[ri], with assumed shape `rshape`) into
        an explicit-shape `intent(out)` dummy, IF its own caller-visible
        size can be proven safe -- either from an `allocate(name(SIZE))`
        statement in its own body, or (when there's no `allocate()` at
        all -- e.g. `name = choice`, a whole-array copy straight from one
        of the procedure's own array arguments, relying on Fortran's
        automatic allocation-on-assignment) from that source argument's
        OWN already-explicit-shape bound. Mutates target_lines in place,
        and appends `name` to extra_args UNLESS `is_new_arg` is False --
        a function's own named RESULT isn't itself one of its dummy
        arguments yet, so it needs adding; a subroutine's own intent(out)
        dummy is already in arg_names, so re-adding it would duplicate
        it in the rebuilt signature. Raises UnsupportedFunction if not
        safely derivable this way.
        """
        if "," in rshape:
            raise UnsupportedFunction(
                f"{target_name!r} has a rank-2-or-higher array result "
                f"(line: {target_lines[ri].strip()!r}) -- only rank-1 arrays "
                f"are bridged for now"
            )
        if rshape.strip() != ":":
            raise UnsupportedFunction(
                f"{target_name!r}'s own array result is not a plain "
                f"allocatable rank-1 array (line: {target_lines[ri].strip()!r})"
            )

        alloc_stmt_re = re.compile(r"^\s*allocate\s*\(", re.IGNORECASE)

        def _find_own_alloc():
            # Finds `name`'s own `NAME(SIZE_EXPR)` array-spec inside an
            # `allocate(...)` statement, via a balanced-paren scan (not a
            # single greedy regex) so neither a trailing keyword argument
            # (`, source=0.0_dp`, `, stat=ios`, ...) NOR another array
            # ALSO being allocated in the SAME statement, before or after
            # `name`'s own spec (`allocate(r(n), h(n))` -- confirmed via
            # examples/xsim_fit_nagarch.py's own `simulate_nagarch`,
            # whose `r`/`h` outputs are allocated together this way),
            # prevents recognizing it -- each top-level, comma-separated
            # item inside the statement's own outer parens is checked in
            # turn for `name`'s own.
            for i in range(1, len(target_lines)):
                code = _strip_comment(target_lines[i])
                pm = alloc_stmt_re.match(code)
                if not pm:
                    continue
                start = pm.end()
                depth = 1
                j = start
                while j < len(code) and depth > 0:
                    if code[j] == "(":
                        depth += 1
                    elif code[j] == ")":
                        depth -= 1
                    j += 1
                if depth != 0:
                    continue  # unbalanced on this line -- not handled
                inner = code[start : j - 1]
                items = _split_top_level(inner)
                for k, item in enumerate(items):
                    im = re.match(rf"^\s*{re.escape(name)}\s*\((.*)\)\s*$", item.strip(), re.IGNORECASE | re.DOTALL)
                    if im:
                        return i, im.group(1).strip(), items, k
            return None, None, None, None

        alloc_i, size_expr, alloc_items, alloc_item_idx = _find_own_alloc()
        if alloc_i is None:
            # No explicit allocate(...) at all -- Fortran auto-(re)
            # allocates on assignment, so try to symbolically derive a
            # caller-visible size from `name`'s own (last) assignment,
            # walking a small, recognized set of forms (see
            # _infer_rank1_size's own docstring, and, when `procedures`
            # was given, _make_local_dependency_resolver's own): a
            # whole-array copy from one of the procedure's own already
            # explicit-shape array arguments (`out = choice`), a slice of
            # a LOCAL array whose own size this same walk can resolve
            # (`func_res = xfull(burnin + 1:size(xfull))`), a Fortran
            # array-constructor concatenation (`ar_poly = [dp ::
            # [1.0_dp], -ar]`), elementwise arithmetic over already-known
            # arrays/scalars (`p(1) * x + p(2) - y`), a call to one of a
            # small set of recognized python.f90 builtin array-returning
            # helpers (rnorm's `rnorm(k)`, lfilter_real's `lfilter_real(b,
            # a, x[, zi])`), or a call to some OTHER, locally-defined
            # dependency function whose OWN array result is itself
            # derivable this way.
            size_expr = _derive_no_alloc_array_size(target_lines, name, arg_names, scalar_names, dependency_resolver)
            if size_expr is None:
                raise UnsupportedFunction(
                    f"{target_name!r}'s own array result has no `allocate(...)` "
                    f"statement, and no recognized whole-array-copy/slice/"
                    f"constructor/elementwise-arithmetic/known-helper/local-"
                    f"dependency expression, this rewrite can safely derive a "
                    f"caller-visible size from -- can't determine one for it"
                )

        # Local variables the size expression must NOT reference -- if
        # it does, the caller can't possibly know the size ahead of the
        # call (the genuinely-unsupported "data-dependent filter/subset
        # result" case).
        declared_names = {n.lower() for n in arg_names} | {name.lower()}
        local_names = set()
        for i in range(1, len(target_lines)):
            code = _strip_comment(target_lines[i])
            if "::" not in code or "intent" in code.lower():
                continue
            decl_part = code.split("::", 1)[1]
            for decl in _split_top_level(decl_part):
                dm = re.match(r"^\s*([a-z_]\w*)", decl, re.IGNORECASE)
                if dm and dm.group(1).lower() not in declared_names:
                    local_names.add(dm.group(1).lower())

        def _forbidden(expr_text):
            for tok in re.findall(r"[A-Za-z_]\w*", expr_text):
                if tok.lower() in local_names:
                    return tok
            return None

        m_range = RANGE_LEN_RE.match(size_expr)
        if m_range:
            parts = _split_top_level(m_range.group(1))
            if len(parts) != 3:
                raise UnsupportedFunction(
                    f"{target_name!r}'s own array result size expression "
                    f"{size_expr!r} isn't recognized as safely derivable "
                    f"from the function's own arguments"
                )
            a_expr, b_expr, c_expr = parts
            bad = _forbidden(a_expr) or _forbidden(b_expr) or _forbidden(c_expr)
            if bad:
                raise UnsupportedFunction(
                    f"{target_name!r}'s own array result size depends on "
                    f"{bad!r}, a value computed inside the function's own "
                    f"body -- not knowable by the caller ahead of the call, "
                    f"so its size isn't a simple function of the arguments"
                )
            # The general closed form for a range's length is
            # max(0, (b - a + c - sign(1, c)) / c) -- but f2py's OWN
            # dimension-expression analyzer can only emit a dummy's
            # explicit-shape bound as a LITERAL C EXPRESSION in its
            # generated wrapper when it can't otherwise symbolically
            # understand it, and neither `sign` nor `max` are C
            # functions -- confirmed empirically: gfortran/Fortran
            # itself accepts the general form fine, but the C compile
            # step then fails ("call to undeclared function 'sign'").
            # Restricted to the overwhelmingly common step=1 case
            # (plain `range(a, b)`, no third argument), where the
            # closed form reduces to plain arithmetic (b - a) --
            # arange_int's own formula, `max(0, (stop - start + step -
            # sign(1, step)) / step)`, reduces at step=1 to `stop -
            # start + 1 - 1` = `stop - start`, matching Python's own
            # EXCLUSIVE-of-stop range length (range(1, n+1) has n
            # elements, not n+1 -- confirmed the hard way: an early
            # off-by-one version of this line used `+ 1`, silently
            # returning one extra element, caught by --verify's own
            # shape mismatch rather than a build failure). Confirmed
            # to both compile AND correctly size the array through
            # f2py. A non-1 step is rejected rather than emitting the
            # untested general form.
            if c_expr.strip() != "1":
                raise UnsupportedFunction(
                    f"{target_name!r}'s own array result size comes from a "
                    f"range with step {c_expr!r} -- only the common step=1 "
                    f"case (plain `range(a, b)`) is bridged for now, since "
                    f"f2py's own dimension-expression analyzer can't emit "
                    f"the general closed form (it needs sign()/max(), "
                    f"neither of which are valid in the plain C expression "
                    f"it falls back to)"
                )
            size_expr = f"({b_expr}) - ({a_expr})"
        else:
            bad = _forbidden(size_expr)
            if bad or "size(" in size_expr.lower():
                raise UnsupportedFunction(
                    f"{target_name!r}'s own array result size expression "
                    f"{size_expr!r} isn't recognized as safely derivable "
                    f"from the function's own arguments"
                )

        # allocate() is no longer legal/needed for an intent(out)
        # explicit-shape array -- the CALLER already allocated it. Only
        # `name`'s own item is removed from the statement -- a sibling
        # array ALSO allocated in the SAME statement (`allocate(r(n),
        # h(n))`) needs its own item left intact for its OWN, separate
        # processing (confirmed via examples/xsim_fit_nagarch.py's own
        # `simulate_nagarch`: deleting the WHOLE line after handling `r`
        # left `h`'s own `allocate(...)` unfindable when its turn came).
        # The whole line is only dropped if NOTHING resembling an actual
        # allocation target (as opposed to a trailing keyword argument
        # like `source=`/`stat=`, which can't stand alone) remains.
        if alloc_i is not None:
            remaining = [it for k, it in enumerate(alloc_items) if k != alloc_item_idx]
            has_target = any(
                re.match(r"^\s*[a-z_]\w*\s*\(.*\)\s*$", it.strip(), re.IGNORECASE | re.DOTALL) for it in remaining
            )
            if has_target:
                indent = re.match(r"^(\s*)", target_lines[alloc_i]).group(1)
                target_lines[alloc_i] = f"{indent}allocate({', '.join(it.strip() for it in remaining)})"
            else:
                del target_lines[alloc_i]
        decl_code = target_lines[ri]
        new_decl = re.sub(
            rf"\ballocatable\s*(?:,\s*)?::\s*{re.escape(name)}\s*\(\s*:\s*\)",
            f"intent(out) :: {name}({size_expr})",
            decl_code,
            flags=re.IGNORECASE,
        )
        if new_decl == decl_code:
            # allocatable/:: ordering can vary; fall back to a plain
            # attribute-strip-then-reattach approach.
            new_decl = re.sub(r"\ballocatable\s*,\s*", "", decl_code, flags=re.IGNORECASE)
            new_decl = re.sub(r",\s*allocatable\b", "", new_decl, flags=re.IGNORECASE)
            new_decl = re.sub(
                rf"::\s*{re.escape(name)}\s*\(\s*:\s*\)",
                f":: {name}({size_expr})",
                new_decl,
                flags=re.IGNORECASE,
            )
            if "intent" not in new_decl.lower():
                new_decl = new_decl.replace("::", "intent(out) ::", 1)
        target_lines[ri] = new_decl
        if is_new_arg:
            extra_args.append(name)

    if is_function:
        ri, rm2 = _find_decl(result_name)
        if ri is not None and rm2.group(3) is None:
            # A SCALAR function result -- not itself array-shaped, but
            # f2py generates its OWN separate scalar-function wrapper
            # (an "<ext>-f2pywrappers2.f90" file) for ANY function
            # (never a subroutine) it wraps, and that generated wrapper
            # subroutine references the module's own `dp` kind
            # parameter for a real(kind=dp) argument or result WITHOUT
            # importing it ("use ..., only: FUNC_NAME" only, no `dp`) --
            # a real f2py code-generation bug, not merely an f2cmap
            # question. Confirmed empirically with the simplest possible
            # case: `def f(x): return x ** 2 - 2.0`, no array involved
            # at all. Converting to a subroutine (mirroring this
            # project's own existing multi-value-return convention)
            # sidesteps it entirely -- f2py never generates that wrapper
            # for a subroutine. Done unconditionally (any result type,
            # not just real/complex) for simplicity and uniformity.
            code = target_lines[ri]
            new_decl = code if "intent" in code.lower() else re.sub(r"\s*::", ", intent(out) ::", code, count=1)
            target_lines[ri] = new_decl
            extra_args.append(result_name)
            made_subroutine = True
        elif ri is not None and rm2.group(3) is not None:
            had_array = True
            _convert_array_result(ri, result_name, rm2.group(3))
            made_subroutine = True
    else:
        # Already a subroutine -- check each of ITS OWN dummy arguments
        # for an allocatable rank-1 array (this project's own multi-
        # value-return convention), skipped by the argument loop above.
        for name in arg_names:
            ri, m = _find_decl(name)
            if ri is None:
                continue
            if "allocatable" not in _strip_comment(target_lines[ri]).lower():
                continue
            rshape = m.group(3)
            if rshape is None:
                continue
            had_array = True
            _convert_array_result(ri, name, rshape, is_new_arg=False)

    if extra_args:
        new_args_text = ", ".join(arg_names + extra_args)
        prefix = sig_m.group("prefix")
        if made_subroutine or not is_function:
            # Either we just converted a function result to an intent(out)
            # argument (made_subroutine), or the target was already a
            # subroutine to begin with (e.g. it only needed its array
            # argument rewritten) -- either way the rebuilt signature must
            # say "subroutine", not "function", to match the untouched
            # "end subroutine ..." line below.
            new_sig = f"{prefix}subroutine {target_name}({new_args_text})"
        else:
            new_sig = f"{prefix}function {target_name}({new_args_text}){sig_m.group('result') or ''}"
        target_lines[0] = new_sig

    if made_subroutine:
        end_re = re.compile(rf"^(\s*end\s+)function(\s+{re.escape(target_name)}\b.*)$", re.IGNORECASE)
        for i in range(len(target_lines) - 1, -1, -1):
            m = end_re.match(_strip_comment(target_lines[i]))
            if m:
                target_lines[i] = f"{m.group(1)}subroutine{m.group(2)}"
                break

    return target_lines, had_array


FINAL_SLICE_ASSIGN_RE = re.compile(
    r"^\s*([a-z_]\w*)\s*=\s*([a-z_]\w*)\s*\(\s*1\s*:\s*([a-z_]\w*)\s*\)\s*$", re.IGNORECASE
)
DO_LOOP_RE = re.compile(r"^\s*do\s+[a-z_]\w*\s*=\s*1\s*,\s*(.+?)\s*$", re.IGNORECASE)
END_DO_RE = re.compile(r"^\s*end\s*do\b", re.IGNORECASE)


def _find_enclosing_do_bound(target_lines, line_idx):
    """Walking upward from line_idx, find the bound expression of the
    NEAREST enclosing `do VAR = 1, EXPR` loop (matching do/end do
    nesting depth -- if/else nesting in between is irrelevant and
    correctly ignored), or None if there isn't one.
    """
    depth = 0
    for i in range(line_idx - 1, -1, -1):
        code = _strip_comment(target_lines[i])
        if END_DO_RE.match(code):
            depth += 1
            continue
        m = DO_LOOP_RE.match(code)
        if m:
            if depth == 0:
                return m.group(1)
            depth -= 1
    return None


def _base_type_of_decl(code):
    """Strip `allocatable`/`intent(...)` attributes from the part of a
    declaration line before `::`, leaving just the base type (e.g.
    `real(kind=dp)`) -- reused for both a dummy argument's own type (to
    re-declare it, explicit-shape, in a generated bridge signature) and
    an output's own type.
    """
    t = code.split("::", 1)[0]
    t = re.sub(r"\ballocatable\b\s*,?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\bintent\s*\([^)]*\)\s*,?\s*", "", t, flags=re.IGNORECASE)
    return t.strip().rstrip(",").strip()


def _decl_line_for_name(target_lines, name):
    for ln in target_lines[1:]:
        code = _strip_comment(ln)
        if "::" not in code:
            continue
        if re.search(rf"(?:::|,)\s*{re.escape(name)}\b", code, re.IGNORECASE):
            return code
    return None


BLOCK_START_RE = re.compile(r"^\s*block\s*$", re.IGNORECASE)
BLOCK_END_RE = re.compile(r"^\s*end\s*block\b", re.IGNORECASE)
# The trailing `(...)` is OPTIONAL -- a block-local declared with a
# shape (e.g. `integer, allocatable :: tmp_out_2_50(:)`, xp2f.py's own
# temp-holder for one of several values a tuple-unpacking call site
# returns) needs hoisting exactly like a bare scalar local does.
# Confirmed a real bug without it: the ORIGINAL regex required the line
# to end immediately after the bare name, so a shaped local's own decl
# line never matched at all -- the block-decl-collecting loop below
# stops at the first non-matching line, so it silently stopped short,
# leaving that decl line stranded IN the body (right where the `block`
# line used to be) rather than hoisted -- illegal Fortran once the
# `block`/`end block` wrapper is gone ("data declaration statement
# cannot appear after executable statements"), confirmed via examples/
# xchoice_tuple_repro.py's own `other_call`.
BLOCK_DECL_RE = re.compile(
    r"^\s*(integer|real|logical|character)\b.*::\s*([a-z_]\w*)\s*(?:\([^()]*\))?\s*$", re.IGNORECASE
)


def unwrap_block_constructs(target_lines, existing_names):
    """Rewrite each `block ... end block` construct in a procedure's own
    body by hoisting its own local declaration(s) to the procedure's top-
    level declaration section (renaming on any collision) and deleting
    the `block`/`end block` lines themselves.

    Confirmed empirically: f2py's own Fortran cracker badly mis-parses a
    `block` construct ("crackline: Mismatch of blocks encountered. Trying
    to fix it by assuming 'end' statement"), which corrupts the symbol
    name it generates for a LATER, unrelated procedure in the SAME file
    (an undefined-symbol link failure for a bridge subroutine that
    otherwise builds fine) -- even though the construct itself is
    ordinary, valid modern Fortran gfortran itself compiles without any
    complaint. Needed because a target's own array-result accumulator
    loop (xp2f.py's own codegen convention, using `block` ONLY to scope
    its own synthesized loop-counter variable) is kept, unmodified
    otherwise, right alongside a generated bridge in the very file f2py
    parses -- see try_build_bridge_for_target's own docstring for why
    the original can't just be excluded from what f2py sees instead.

    Only handles the exact shape xp2f.py's own codegen produces (a
    `block` whose own body starts with one or more simple `TYPE :: NAME`
    declaration lines, nothing else, before its matching `end block`) --
    a `block` some other shape is left completely alone, unrecognized;
    conservative on purpose, matching this project's own established
    style for this kind of narrow rewrite.
    """
    lines = list(target_lines)

    # The signature itself may span several physical lines (xp2f.py's own
    # line-wrapping, confirmed for a subroutine with several dummy
    # arguments -- e.g. its own multi-value-return convention with
    # several array outputs, long enough to wrap) -- skip past ALL of
    # them before looking for the procedure's own declarations, so a
    # continuation line (never itself a declaration) can't be mistaken
    # for the end of the declaration section.
    sig_line_count = 1
    while sig_line_count <= len(lines) and _strip_comment(lines[sig_line_count - 1]).rstrip().endswith("&"):
        sig_line_count += 1

    decl_end = sig_line_count
    i = sig_line_count
    while i < len(lines):
        code = _strip_comment(lines[i]).strip()
        if not code:
            i += 1
            continue
        if BLOCK_START_RE.match(code):
            break
        if "::" in code or code.lower().startswith(("implicit", "use ")):
            # This declaration/use/implicit line may ITSELF continue
            # across several physical lines via trailing "&" (confirmed
            # for xp2f.py's own multi-value-return convention with
            # several array outputs sharing one `intent(out)` decl).
            j = i
            while _strip_comment(lines[j]).rstrip().endswith("&"):
                j += 1
            decl_end = j + 1
            i = j + 1
        else:
            break

    hoisted = []
    out = []
    i = 0
    while i < len(lines):
        code = _strip_comment(lines[i]).strip()
        if not BLOCK_START_RE.match(code):
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        block_decls = []
        while j < len(lines):
            dm = BLOCK_DECL_RE.match(_strip_comment(lines[j]).strip())
            if dm is None:
                break
            block_decls.append((lines[j], dm.group(2)))
            j += 1
        depth = 0
        k = j
        end_idx = None
        while k < len(lines):
            kcode = _strip_comment(lines[k]).strip()
            if BLOCK_START_RE.match(kcode):
                depth += 1
            elif BLOCK_END_RE.match(kcode):
                if depth == 0:
                    end_idx = k
                    break
                depth -= 1
            k += 1
        if end_idx is None:
            # Not the simple shape this rewrite understands -- leave the
            # `block` line (and everything else) completely alone.
            out.append(lines[i])
            i += 1
            continue

        rename = {}
        for decl_line, name in block_decls:
            new_name = name
            if new_name.lower() in existing_names:
                n = 0
                while True:
                    n += 1
                    cand = f"{name}_blk{n}"
                    if cand.lower() not in existing_names:
                        new_name = cand
                        break
            existing_names.add(new_name.lower())
            rename[name] = new_name
            hoisted.append(re.sub(rf"\b{re.escape(name)}\b", new_name, decl_line, count=1, flags=re.IGNORECASE))

        body = lines[j:end_idx]
        for old, new in rename.items():
            if old != new:
                body = [re.sub(rf"\b{re.escape(old)}\b", new, ln, flags=re.IGNORECASE) for ln in body]
        out.extend(body)
        i = end_idx + 1

    out[decl_end:decl_end] = hoisted
    return out


def _merge_continuations(phys_lines):
    """Return a list of LOGICAL lines from `phys_lines`, joining any line
    ending in `&` onto the line(s) that continue it (a leading `&` on
    the continuation is stripped too) -- so downstream, per-line regex-
    based scanning (this project's own established style for this kind
    of pass) sees one complete statement per entry, regardless of how
    xp2f.py's own line-wrapping happened to split it across physical
    lines (confirmed for BOTH a long signature -- several dummy
    arguments, e.g. xp2f.py's own multi-value-return convention with
    several array outputs -- AND a single declaration shared by several
    of those same outputs). Blank/comment-only/non-continued lines are
    preserved as their own, unchanged entries -- this is a pure re-
    grouping, never a text edit (the merged line's own INDENTATION is
    preserved too, taken from the first physical line -- confirmed a
    real cosmetic bug without this: the first part's own leading
    whitespace was unconditionally stripped and never restored, so a
    continued statement's merged line always came out at column 0 in
    the final generated .f90 file, regardless of its actual nesting --
    e.g. examples/xxbs.py's own `black_scholes`, whose `func_res = ...`
    assignment is `&`-continued in xp2f.py's own original translation,
    came out unindented relative to its own enclosing `if ... then` /
    `end if` once merged, even though nothing about its Fortran meaning
    changed).
    """
    out = []
    i = 0
    n = len(phys_lines)
    while i < n:
        code = _strip_comment(phys_lines[i]).rstrip()
        if not code.endswith("&"):
            out.append(phys_lines[i])
            i += 1
            continue
        indent = phys_lines[i][: len(phys_lines[i]) - len(phys_lines[i].lstrip())]
        parts = [code[:-1].rstrip().lstrip()]
        i += 1
        while i < n:
            nxt = _strip_comment(phys_lines[i]).rstrip()
            cont = nxt.endswith("&")
            body = (nxt[:-1].rstrip() if cont else nxt).lstrip()
            if body.startswith("&"):
                body = body[1:].lstrip()
            parts.append(body)
            i += 1
            if not cont:
                break
        out.append(indent + " ".join(parts))
    return out


def try_build_bridge_for_target(lines, start, end, target_name):
    """Detect xp2f.py's own growable-accumulator idiom -- an array
    output built by incrementing a count variable by exactly 1 inside a
    loop bounded by `size(ARRAY_ARG)`, then sliced `OUT = LOCAL(1:
    COUNT)` as the output's final value -- for EVERY array-shaped
    output of the target procedure (its own result, if a function; each
    intent(out) dummy argument, if a subroutine -- xp2f.py's own
    multi-value-return convention). If EVERY array output matches, this
    is exactly the "primes in an array"-style case discussed alongside
    this feature: a result whose true length is data-dependent, only
    known after running the loop, so there's no legal explicit-shape
    bound to give the ORIGINAL procedure's own signature the way
    rewrite_target_for_f2py does for a simple, argument-derivable size.

    Instead, returns a "bridge spec" for build_bridge_procedure to turn
    into an ADDITIONAL, new f2py-bridgeable subroutine that calls the
    ORIGINAL procedure UNCHANGED (kept exactly as xp2f.py emitted it --
    real Fortran-to-Fortran calls handle its own allocatable output(s)
    perfectly well) and copies each true result into an explicit-shape
    buffer sized to the PROVEN bound (the corresponding array argument's
    own length -- an accumulator can never emit more elements than it
    read), plus that output's own true count for the Python wrapper to
    trim by.

    Returns None if ANY array output doesn't match this exact idiom --
    conservative on purpose: a false negative just falls back to the
    existing rejection (or rewrite_target_for_f2py's own, different
    "simple function of the arguments" case), never a wrong bridge.
    """
    target_lines = _merge_continuations(lines[start : end + 1])
    sig_m = SIG_RE.match(_strip_comment(target_lines[0]))
    if not sig_m:
        return None
    is_function = sig_m.group("kind").lower() == "function"
    arg_names = [a for a in _split_top_level(sig_m.group("args")) if a]
    result_name = target_name
    if sig_m.group("result"):
        rm = RESULT_NAME_RE.search(sig_m.group("result"))
        if rm:
            result_name = rm.group(1)

    if is_function:
        true_inputs = arg_names
        outputs = [result_name]
    else:
        true_inputs = []
        outputs = []
        for name in arg_names:
            decl = _decl_line_for_name(target_lines, name)
            if decl and "intent(out)" in decl.lower() and re.search(
                rf"(?:::|,)\s*{re.escape(name)}\b\s*\(", decl, re.IGNORECASE
            ):
                outputs.append(name)
            else:
                true_inputs.append(name)
        if not outputs:
            return None

    known_array_args = set()
    for name in true_inputs:
        decl = _decl_line_for_name(target_lines, name)
        if decl and "intent" in decl.lower() and re.search(
            rf"(?:::|,)\s*{re.escape(name)}\b\s*\(\s*:\s*\)", decl, re.IGNORECASE
        ):
            known_array_args.add(name)
    if not known_array_args:
        return None

    bounds = {}
    for out_name in outputs:
        slice_i = local_name = count_name = None
        for i in range(len(target_lines) - 1, 0, -1):
            m = FINAL_SLICE_ASSIGN_RE.match(_strip_comment(target_lines[i]))
            if m and m.group(1).lower() == out_name.lower():
                slice_i, local_name, count_name = i, m.group(2), m.group(3)
                break
        if slice_i is None:
            return None

        incr_re = re.compile(
            rf"^\s*{re.escape(count_name)}\s*=\s*{re.escape(count_name)}\s*\+\s*1\s*$", re.IGNORECASE
        )
        incr_lines = [i for i in range(1, len(target_lines)) if incr_re.match(_strip_comment(target_lines[i]))]
        if len(incr_lines) != 1:
            return None

        bound_expr = _find_enclosing_do_bound(target_lines, incr_lines[0])
        if bound_expr is None:
            return None
        bm = re.match(r"^\s*size\s*\(\s*([a-z_]\w*)\s*\)\s*$", bound_expr, re.IGNORECASE)
        if not bm or bm.group(1) not in known_array_args:
            return None
        bounds[out_name] = bm.group(1)

    return {
        "is_function": is_function,
        "true_inputs": true_inputs,
        "outputs": outputs,
        "bounds": bounds,
    }


def build_bridge_procedure(lines, start, end, target_name, spec, bridge_name):
    """Turn a bridge spec (see try_build_bridge_for_target) into the
    Fortran source of a new subroutine, `bridge_name`, that calls
    `target_name` (referenced by name only -- its own lines, elsewhere
    in the same trimmed module, are left completely untouched) and
    copies each true array output into an explicit-shape, provably-
    bounded buffer plus its own true count.
    """
    target_lines = _merge_continuations(lines[start : end + 1])
    true_inputs = spec["true_inputs"]
    outputs = spec["outputs"]
    bounds = spec["bounds"]

    existing_names = set()
    for ln in lines:
        for tok in re.findall(r"[A-Za-z_]\w*", ln):
            existing_names.add(tok.lower())
    counter = [0]

    def _next_name(prefix):
        while True:
            counter[0] += 1
            cand = f"{prefix}_{counter[0]}"
            if cand not in existing_names:
                existing_names.add(cand)
                return cand

    array_args = sorted(set(bounds.values()))
    synth_size = {a: _next_name("n") for a in array_args}

    sig_args = []
    decls = []
    for name in true_inputs:
        decl = _decl_line_for_name(target_lines, name)
        base_type = _base_type_of_decl(decl) if decl else "real(kind=dp)"
        if name in synth_size:
            sig_args.append(name)
            decls.append(f"   {base_type}, intent(in) :: {name}({synth_size[name]})")
        else:
            sig_args.append(name)
            decls.append(f"   {base_type}, intent(in) :: {name}")
    for a in array_args:
        sig_args.append(synth_size[a])
        decls.append(f"   integer, intent(in) :: {synth_size[a]}")

    count_names = {}
    tmp_names = {}
    for out_name in outputs:
        bound_arg = bounds[out_name]
        decl = _decl_line_for_name(target_lines, out_name)
        out_type = _base_type_of_decl(decl) if decl else "real(kind=dp)"
        cn = _next_name("cnt")
        count_names[out_name] = cn
        tmp_names[out_name] = _next_name("tmp_res")
        sig_args.append(out_name)
        decls.append(f"   {out_type}, intent(out) :: {out_name}({synth_size[bound_arg]})")
        sig_args.append(cn)
        decls.append(f"   integer, intent(out) :: {cn}")
        decls.append(f"   {out_type}, allocatable :: {tmp_names[out_name]}(:)")

    body = []
    if spec["is_function"]:
        out_name = outputs[0]
        tmp = tmp_names[out_name]
        body.append(f"   {tmp} = {target_name}(" + ", ".join(true_inputs) + ")")
        body.append(f"   {count_names[out_name]} = size({tmp})")
        body.append(f"   {out_name}(1:{count_names[out_name]}) = {tmp}")
    else:
        call_args = true_inputs + [tmp_names[o] for o in outputs]
        body.append(f"   call {target_name}(" + ", ".join(call_args) + ")")
        for out_name in outputs:
            tmp = tmp_names[out_name]
            body.append(f"   {count_names[out_name]} = size({tmp})")
            body.append(f"   {out_name}(1:{count_names[out_name]}) = {tmp}")

    header = f"pure subroutine {bridge_name}(" + ", ".join(sig_args) + ")"
    text = "\n".join([header] + decls + [""] + body + [f"end subroutine {bridge_name}"])
    return text, count_names


def append_procedure_to_module(trimmed_text: str, proc_text: str, proc_name: str) -> str:
    """Add a new procedure (e.g. a generated bridge) to a trimmed
    module's own `public ::` line and `contains` section.
    """
    pub_re = re.compile(r"^(\s*public\s*::\s*)(.+)$", re.IGNORECASE | re.MULTILINE)
    m = pub_re.search(trimmed_text)
    if m:
        new_pub = f"{m.group(1)}{m.group(2)}, {proc_name}"
        trimmed_text = trimmed_text[: m.start()] + new_pub + trimmed_text[m.end() :]
    end_mod_re = re.compile(r"^\s*end\s+module\b.*$", re.IGNORECASE | re.MULTILINE)
    em = end_mod_re.search(trimmed_text)
    if em is None:
        return trimmed_text
    insertion = proc_text + "\n\n"
    return trimmed_text[: em.start()] + insertion + trimmed_text[em.start() :]


def remove_from_public(trimmed_text: str, name: str) -> str:
    """Drop one name from a trimmed module's own `public ::` line --
    used when a bridge subroutine replaces the ORIGINAL target as what
    f2py should wrap; f2py otherwise crawls and tries to wrap EVERY
    public name in the module, including the original (still left with
    its own, un-rewritten allocatable result), hitting the very bug the
    bridge exists to route around.
    """
    pub_re = re.compile(r"^(\s*public\s*::\s*)(.+)$", re.IGNORECASE | re.MULTILINE)
    m = pub_re.search(trimmed_text)
    if not m:
        return trimmed_text
    names = [n.strip() for n in m.group(2).split(",")]
    kept = [n for n in names if n.lower() != name.lower()]
    new_line = f"{m.group(1)}{', '.join(kept)}"
    return trimmed_text[: m.start()] + new_line + trimmed_text[m.end() :]


DATAFRAME_USE_RE = re.compile(
    r"^\s*use\s+dataframe_(?:str_index|index_date|index_datetime)_mod\s*,\s*only\s*:\s*(.+)$",
    re.IGNORECASE | re.MULTILINE,
)


def strip_unused_dataframe_use(trimmed_text: str) -> str:
    """Drop a `use dataframe_str_index_mod`/`dataframe_index_date_mod`/
    `dataframe_index_datetime_mod` header line if NONE of its own
    imported PLAIN names (`DataFrame_str_index`, `nrow`, `ncol`, ...) are
    actually referenced anywhere else in the trimmed module's own kept
    text. xp2f.py emits this line at MODULE level whenever the SCRIPT AS
    A WHOLE uses a pandas DataFrame ANYWHERE -- not just within the
    target's own dependency closure -- so extracting a target that
    doesn't touch pandas at all can leave this orphaned, needing a
    companion module (dataframe_str_index.f90, ...) never compiled/
    linked into this standalone f2py build. Confirmed via examples/
    xmix.py's own `simulate_normal_mixture` (its own SCRIPT builds a
    DataFrame elsewhere to report fit results, but the target itself
    doesn't): gfortran failed with "Cannot open module file
    'dataframe_str_index_mod.mod' for reading" -- a real, but
    completely different, error than the F2PY Build failure's own
    unhelpfully swallowed stdout suggested at first.

    An `only:` entry that's an `operator(+)`-style specifier is never
    itself checked for -- an operator overload is invoked via the bare
    symbol (`a + b`), never by writing `operator(+)` in executable code,
    and ordinary numeric code uses `+`/`-`/`*`/`/` constantly regardless
    of pandas -- so only the PLAIN names (a real DataFrame type/function
    name) are informative here. A DEPENDENCY that genuinely still needs
    one of these names (kept, now private, but still real Fortran-to-
    Fortran code) keeps its own `use` line intact.
    """

    def _maybe_strip(match: re.Match) -> str:
        names = [n.strip() for n in _split_top_level(match.group(1))]
        plain_names = [n for n in names if not re.match(r"operator\s*\(", n, re.IGNORECASE)]
        rest = trimmed_text[match.end() :]
        for nm in plain_names:
            if re.search(rf"\b{re.escape(nm)}\b", rest, re.IGNORECASE):
                return match.group(0)
        return ""

    return DATAFRAME_USE_RE.sub(_maybe_strip, trimmed_text)


PYTHON_MOD_USE_RE = re.compile(r"^(\s*use\s+python_mod\s*,\s*only\s*:\s*)(.+)$", re.IGNORECASE | re.MULTILINE)


INTERFACE_NAME_RE = re.compile(r"^\s*interface\s+([a-z]\w*)\s*$", re.IGNORECASE)
MODULE_PROCEDURE_RE = re.compile(r"^\s*module\s+procedure\s*(?:::)?\s*(.+)$", re.IGNORECASE)


def _find_python_mod_interfaces(header_lines):
    """Scan python.f90's own module HEADER (specification section, before
    `contains`) for a named generic `interface NAME ... end interface`
    block -- e.g. `optval`, dispatching to `optval_int`/`optval_real`/
    `optval_logical`/`optval_char` by argument type via one `module
    procedure` line per overload. NOT tracked by parse_module's own
    procedure table (which deliberately skips interface bodies, since
    an interface itself isn't a procedure), so a request to inline a
    generic name needs its own, separate lookup here.

    Returns {name.lower(): (start, end, [member_names])}, spans relative
    to `header_lines` itself (as returned by parse_module).
    """
    out = {}
    i = 0
    n = len(header_lines)
    while i < n:
        code = _strip_comment(header_lines[i])
        m = INTERFACE_NAME_RE.match(code)
        if not m:
            i += 1
            continue
        name = m.group(1)
        start = i
        members = []
        j = i + 1
        while j < n and not INTERFACE_END_RE.match(_strip_comment(header_lines[j])):
            mm = MODULE_PROCEDURE_RE.match(_strip_comment(header_lines[j]))
            if mm:
                members.extend(p.strip() for p in mm.group(1).split(",") if p.strip())
            j += 1
        if j < n:
            out[name.lower()] = (start, j, members)
            i = j + 1
        else:
            i += 1  # unterminated -- not a block this recognizes
    return out


def _dedent_lines(lines):
    """Strip the common leading whitespace shared by every NON-BLANK
    line in `lines` -- a plain re-grouping, never a text edit to any
    line's OWN relative indentation (nested content stays exactly as
    indented relative to its own enclosing construct). A no-op if the
    minimum indent is already 0, or if `lines` is entirely blank.
    """
    non_blank = [ln for ln in lines if ln.strip()]
    if not non_blank:
        return lines
    min_indent = min(len(ln) - len(ln.lstrip()) for ln in non_blank)
    if min_indent == 0:
        return lines
    return [ln[min_indent:] if ln[:min_indent].strip() == "" else ln.lstrip() for ln in lines]


def inline_python_mod_helpers(trimmed_text: str):
    """Rewrite a `use python_mod, only: NAME1, NAME2, ...` line in the
    trimmed module by INLINING each simple NAME's own Fortran source
    directly into the trimmed module's own body (transitively, for
    anything an inlined helper itself calls that's ALSO in python_mod) --
    rather than compiling and linking python.f90 (and lapack_d.f90,
    which python.f90's own LAPACK-backed routines need at link time) as
    a separate object for the f2py build.

    Confirmed empirically that BOTH alternatives fail on this exact
    toolchain: f2py's own Fortran cracker can't parse python.f90's full
    public surface at all (many procedures, several returning something
    it can't map to a Python type -- a hard `KeyError: 'void'` crash) or
    lapack_d.f90 (a "crackline: groupcounter(=0) is nonpositive" hard
    crash on its legacy F77-style formatting); and linking a separately-
    compiled python.o in via a bare filename on the f2py -c command line
    doesn't work either (the meson/lld backend confirmed NOT to pick it
    up as a link input the way it would for xp2f.py's own direct gfortran
    invocation, and independently, gfortran runtime bits needing
    __gthr_win32_* symbols aren't resolved by lld's own default link
    flags regardless).

    A requested name that's a GENERIC interface (e.g. `optval`,
    dispatching to `optval_int`/`optval_real`/`optval_logical`/
    `optval_char`) is handled specially: ALL of its own concrete
    overloads are inlined (transitively, same as any other helper), AND
    the `interface optval ... end interface` block ITSELF is also
    inlined -- into the trimmed module's own SPECIFICATION section
    (before `contains`), never the executable body -- since a plain
    inlining of just the concrete overloads would leave the caller's own
    `optval(...)` call site with no generic name to resolve through at
    all.

    A helper that touches python.f90's own MODULE-LEVEL state (e.g.
    `rnorm`/`runif`, whose own concrete overloads read/write private RNG
    -replay bookkeeping -- `rng_replay_enabled`, `rng_replay_bin_u`, ...
    -- declared in python.f90's own specification section, never as one
    of their own dummy arguments) is ALSO handled: every such state
    name's own declaration is hoisted into the trimmed module's own
    specification section too, exactly like a needed interface block --
    this function otherwise only ever copies a PROCEDURE's own body
    text, never anything from python.f90's own specification section, so
    without this a state-touching helper would reference a symbol
    nothing declares (an undetected-until-build-time "has no IMPLICIT
    type" error, confirmed via examples/xsim_fit_nagarch.py's own
    `simulate_nagarch`, which calls `rnorm()`). `dp` is the one
    exception -- always separately declared by the trimmed module
    itself already, so a reference to it needs no special handling.

    Returns (new_text, unresolved_names) -- unresolved_names lists any
    requested helper this couldn't inline at all (not found in
    python.f90, as either a procedure or a generic interface), left for
    the caller to reject with a clear message rather than silently ship
    a broken build.
    """
    m = PYTHON_MOD_USE_RE.search(trimmed_text)
    if not m:
        return trimmed_text, []
    requested = [n.strip() for n in m.group(2).split(",") if n.strip()]

    py_mod_text = PYTHON_MOD_PATH.read_text(encoding="utf-8", errors="ignore")
    _mod_name, py_header, py_lines, py_procs = parse_module(py_mod_text)
    py_interfaces = _find_python_mod_interfaces(py_header)
    known = set(py_procs.keys())

    # Every name declared in python.f90's own SPECIFICATION section
    # (outside `contains`), other than `dp` (see the docstring above),
    # mapped to its own declaration line -- so a state name any needed
    # helper touches can have that SAME line hoisted into the trimmed
    # module's own specification section.
    module_state_names = set()
    module_state_decls: dict[str, str] = {}
    for ln in py_header:
        code = _strip_comment(ln)
        if "::" not in code or code.strip().lower().startswith(("use", "public", "private", "implicit")):
            continue
        for part in _split_top_level(code.split("::", 1)[1]):
            dm = re.match(r"^\s*([a-z_]\w*)", part, re.IGNORECASE)
            if dm and dm.group(1).lower() != "dp":
                nm_lower = dm.group(1).lower()
                module_state_names.add(nm_lower)
                module_state_decls.setdefault(nm_lower, ln)

    def _state_names_used_by(nm: str) -> set[str]:
        """Which python.f90 module-level state names (if any) does
        procedure `nm`'s own body reference? A state name that's ALSO
        locally declared within this same procedure (a dummy argument,
        its own named result, or a plain local) is shadowed -- a
        coincidental reuse of a module-level name, not an actual
        reference to it. Confirmed a real false-positive risk:
        python.f90 uses `result(v)` as a common naming convention across
        MANY otherwise-unrelated functions, and `v` also happens to be a
        genuine module-level name -- without this exclusion,
        optval_real's own `result(v)` falsely tripped this check.
        """
        start, end = py_procs[nm]
        local_names = set()
        for i in range(start, end + 1):
            code = _strip_comment(py_lines[i])
            if "::" not in code:
                continue
            for part in _split_top_level(code.split("::", 1)[1]):
                dm = re.match(r"^\s*([a-z_]\w*)", part, re.IGNORECASE)
                if dm:
                    local_names.add(dm.group(1).lower())
        # A plain RESULT_NAME_RE *search* (not requiring a full SIG_RE
        # match) so a TYPE-PREFIXED function signature -- `pure integer
        # function optval_int(x, default) result(v)`, which SIG_RE
        # itself doesn't match at all, since its own `prefix` group only
        # recognizes pure/elemental/impure/recursive, never a leading
        # type name -- still has its own `result(v)` found and excluded.
        proc_m = PROC_START_RE.match(_strip_comment(py_lines[start]))
        rm = RESULT_NAME_RE.search(_strip_comment(py_lines[start]))
        if rm:
            local_names.add(rm.group(1).lower())
        elif proc_m and proc_m.group(1).lower() == "function":
            local_names.add(proc_m.group(2).lower())
        body_text = "\n".join(py_lines[start : end + 1])
        return {
            state_name
            for state_name in module_state_names - local_names
            if re.search(rf"\b{re.escape(state_name)}\b", body_text, re.IGNORECASE)
        }

    needed = set()  # concrete procedure names to inline into `contains`
    needed_interfaces = set()  # generic interface names to inline into the spec section
    frontier = []
    unresolved = []
    for n in requested:
        nl = n.lower()
        if nl in py_procs:
            frontier.append(nl)
        elif nl in py_interfaces:
            needed_interfaces.add(nl)
            frontier.extend(mem.lower() for mem in py_interfaces[nl][2])
        else:
            unresolved.append(n)

    while frontier:
        nm = frontier.pop()
        if nm in needed or nm not in py_procs:
            continue
        needed.add(nm)
        start, end = py_procs[nm]
        for dep in find_calls(py_lines, start, end, known, nm):
            if dep not in needed:
                frontier.append(dep)

    if not needed and not needed_interfaces:
        return trimmed_text, unresolved

    # Now that the FULL transitive closure of concrete procedures is
    # known, find every module-level state name any of them actually
    # touches -- each such name's own declaration needs hoisting too
    # (see this function's own docstring).
    needed_state_names: set[str] = set()
    for nm in needed:
        needed_state_names |= _state_names_used_by(nm)

    # A blank line BEFORE the first inlined procedure too, not just
    # between each pair of them -- confirmed a real cosmetic bug without
    # it: the trimmed module's own target procedure's `end
    # subroutine`/`end function` line ran directly into the first
    # inlined helper's own signature line with no separator at all.
    inlined_body = [""]
    for nm in sorted(needed, key=lambda n: py_procs[n][0]):
        start, end = py_procs[nm]
        # python.f90's own procedures are indented relative to SOME
        # outer nesting of its own file layout (its helpers commonly sit
        # at a 6-space base indent) -- dedented here to a flush-left
        # signature/end line, matching the trimmed module's own
        # convention for a procedure directly inside `contains` (e.g.
        # its own TARGET procedure's `subroutine NAME(...)`/`end
        # subroutine NAME` lines never carry python.f90's leftover base
        # indent). Relative indentation WITHIN the procedure (its own
        # body's nesting under `if`/`do`/...) is preserved exactly --
        # only the common leading whitespace shared by every line is
        # removed.
        inlined_body.extend(_dedent_lines(py_lines[start : end + 1]))
        inlined_body.append("")

    interface_body = []
    for nm in sorted(needed_interfaces, key=lambda n: py_interfaces[n][0]):
        start, end, _members = py_interfaces[nm]
        interface_body.extend(py_header[start : end + 1])
        interface_body.append("")

    state_body = [module_state_decls[nm] for nm in sorted(needed_state_names) if nm in module_state_decls]

    remaining = [n for n in requested if n.lower() not in needed and n.lower() not in needed_interfaces]
    if remaining:
        new_use_line = f"{m.group(1)}{', '.join(remaining)}"
        new_text = trimmed_text[: m.start()] + new_use_line + trimmed_text[m.end() :]
    else:
        # Drop the whole `use python_mod, only: ...` line -- nothing left
        # to import from it.
        line_start = trimmed_text.rfind("\n", 0, m.start()) + 1
        line_end = trimmed_text.find("\n", m.end())
        line_end = len(trimmed_text) if line_end == -1 else line_end + 1
        new_text = trimmed_text[:line_start] + trimmed_text[line_end:]

    if state_body or interface_body:
        contains_re = re.compile(r"^\s*contains\s*$", re.IGNORECASE | re.MULTILINE)
        cm = contains_re.search(new_text)
        if cm is not None:
            insertion = "\n".join(state_body + interface_body) + "\n"
            new_text = new_text[: cm.start()] + insertion + new_text[cm.start() :]

    end_mod_re = re.compile(r"^\s*end\s+module\b.*$", re.IGNORECASE | re.MULTILINE)
    em = end_mod_re.search(new_text)
    if em is None:
        return new_text, unresolved
    insertion = "\n".join(inlined_body) + "\n"
    new_text = new_text[: em.start()] + insertion + new_text[em.start() :]
    return new_text, unresolved


def write_f2cmap_file(path: Path) -> None:
    """Write a `.f2py_f2cmap` file mapping this project's own universal
    `dp = real64` kind parameter to `double` -- the standard, documented
    f2py mechanism for a custom KIND name, and the confirmed fix for
    f2py's own generated wrapper otherwise silently mis-resolving `dp` to
    single precision for an array argument/result (a scalar argument/
    result is unaffected -- confirmed working without this file long
    before array support existed).
    """
    path.write_text("dict(real=dict(dp='double'))\n", encoding="utf-8")


# Every LAPACK routine name this project's own python.f90 helpers call
# (confirmed via `grep -oE '\bcall\s+d[a-z]{4,6}\s*\(' python.f90` --
# dpotrf for a Cholesky factorization, the rest for the other
# numpy.linalg-backed helpers: dgeev/dgeqrf/dgesv/dgesvd/dgetrf/dgetri/
# dorgqr/dsyev). A trimmed module referencing any of these (after
# inline_python_mod_helpers has already inlined whichever helper calls
# it) needs lapack_d.f90 -- this project's own vendored, whole-file
# LAPACK reference implementation, already used by xp2f.py's own
# whole-program `--compile` path the same way -- linked in too.
LAPACK_ROUTINE_RE = re.compile(
    r"\b(dgeev|dgeqrf|dgesv|dgesvd|dgetrf|dgetri|dorgqr|dpotrf|dsyev)\s*\(", re.IGNORECASE
)


def _ensure_lapack_archive():
    """Return (lib_dir, lib_stem) for a `-L{lib_dir} -l{lib_stem}` link
    flag pair that resolves every LAPACK_ROUTINE_RE symbol, or None if
    lapack_d isn't available at all (no source to build it from).

    f2py's own `-c` build mode can't just be handed lapack_d.f90
    directly as an extra source file the way plain gfortran can: EVERY
    file f2py is given gets crackfortran-parsed as something to WRAP for
    Python (confirmed empirically -- a bare `.o` object file passed the
    same way is silently just added to that same file list and produces
    no link input at all, no error either, since crackfortran can't read
    binary content as Fortran source and just finds nothing there). The
    fix is the same mechanism this project's own `-lgcc` link flag
    already uses successfully: wrap the already-compiled object in a
    plain static archive (`ar rcs liblapack_d.a lapack_d.o`) and pass it
    as an ordinary `-L`/`-l` linker flag instead -- f2py passes those
    straight through to the final link command untouched.

    Cached (as `liblapack_d.a`, alongside this project's own vendored
    lapack_d.o/lapack_d.f90) so the ~110K-line lapack_d.f90 is compiled
    or re-archived at most once, not on every xpfunc2f.py invocation
    that happens to need it.
    """
    cache_dir = Path(__file__).resolve().parent / ".xpfunc2f_lapack_cache"
    archive_path = cache_dir / "liblapack_d.a"
    if archive_path.exists():
        return cache_dir, "lapack_d"

    here = Path(__file__).resolve().parent
    obj_path = here / "lapack_d.o"
    if not obj_path.exists():
        # No pre-built object -- compile lapack_d.f90 fresh, ONCE, into
        # the cache dir itself (never the repo root -- this is a
        # generated artifact, not something to leave lying around next
        # to the vendored source).
        src_path = here / "lapack_d.f90"
        if not src_path.exists():
            return None
        cache_dir.mkdir(parents=True, exist_ok=True)
        obj_path = cache_dir / "lapack_d.o"
        proc = subprocess.run(
            ["gfortran", "-O2", "-c", str(src_path), "-o", str(obj_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not obj_path.exists():
            return None

    cache_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["ar", "rcs", str(archive_path), str(obj_path)], capture_output=True, text=True)
    if proc.returncode != 0 or not archive_path.exists():
        return None
    return cache_dir, "lapack_d"


# ---------------------------------------------------------------------------
# ctypes/bind(c) backend (--backend ctypes) -- an alternative to f2py that
# sidesteps several f2py-specific quirks (the scalar-function subroutine-
# conversion glue-wrapper bug, --lower case mangling, the .f2py_f2cmap dp-
# resolution dance, f2py's -c mode silently dropping a raw .o link input,
# f2py's own silent array-to-scalar mismarshalling) by using plain
# iso_c_binding interoperability and a direct `gfortran -shared` compile
# instead of f2py's own crackfortran/meson pipeline. PHASE 1 ONLY: plain
# scalar real/integer/logical arguments and result -- no arrays, no
# strings, no callbacks yet (rejected with UnsupportedFunction, same
# fail-clean philosophy as check_f2py_compatible). See the approved plan
# at the time this was written for the full phased design.
# ---------------------------------------------------------------------------


def _c_interoperable_decl(base_type: str) -> str:
    """Map a Fortran base type spec, as `_base_type_of_decl` returns it
    (e.g. `real(kind=dp)`, `integer`, `logical`), to its iso_c_binding
    equivalent for a bind(c) dummy/result declaration. `character` needs
    genuinely different handling (an explicit-length buffer, not a
    simple type-name swap) -- not covered here, a later ctypes-backend
    phase.
    """
    bt = base_type.strip().lower()
    if bt.startswith("real"):
        return "real(c_double)"
    if bt.startswith("integer"):
        return "integer(c_int)"
    if bt.startswith("logical"):
        return "logical(c_bool)"
    raise UnsupportedFunction(f"ctypes backend: no iso_c_binding mapping yet for base type {base_type!r}")


CALLBACK_DECL_RE = re.compile(
    r"^\s*procedure\s*\(\s*([a-z_]\w*)\s*\)\s*(?:,[^:]*)?::\s*([a-z_]\w*)\s*$", re.IGNORECASE
)


def _find_callback_arg(target_lines):
    """Return (cb_arg_name, iface_name) for the target's own callback
    dummy argument -- a `procedure(IFACE) :: name` declaration (xp2f.py's
    own shape for a Python function passed as an argument, e.g.
    examples/xcallback_two_arg_repro.py's own `evaluate(f, x, n)`) -- or
    (None, None) if there isn't one.
    """
    for ln in target_lines[1:]:
        m = CALLBACK_DECL_RE.match(_strip_comment(ln))
        if m:
            return m.group(2), m.group(1)
    return None, None


def _rewrite_callback_interface_for_ctypes(target_lines, cb_arg_name, iface_name):
    """Return (new_target_lines, cb_result_c_type, cb_arg_specs) with the
    named callback interface (a `function`/`subroutine IFACE_NAME(...)
    ... end` block nested inside `interface ... end interface`, xp2f.py's
    own shape for a Python callback argument's OWN signature) rewritten
    for C interoperability: marked `bind(c)`, and its own assumed-shape
    array dummy(s) converted to explicit-shape + a new synth-size dummy
    -- bind(c) forbids assumed-shape on the callback's own interface
    just as much as on the outer target's.

    This is NOT optional cosmetics: a Python-supplied `ctypes.CFUNCTYPE`
    is only callable correctly through a Fortran PROCEDURE POINTER when
    the interface used to type that pointer is ALSO interoperable --
    otherwise Fortran generates its own native (descriptor-based, for an
    assumed-shape array) calling convention at every call site of the
    callback, which is incompatible with the plain-pointer C-ABI
    `CFUNCTYPE` actually provides, corrupting the call. Since the
    callback's own interface, once rewritten, must stay IDENTICAL
    wherever the SAME callback argument is used (the target's own copy,
    and any DEPENDENCY's own copy it forwards the callback to), this
    same rewrite must be applied to every one of them consistently --
    the caller is responsible for finding and rewriting each copy.

    If the target's own body calls the callback DIRECTLY (e.g.
    examples/xcallback_two_arg_repro.py's own `evaluate`, `value = f(x,
    n)` -- unlike examples/xcallback_passthrough_order_repro.py's own
    `driver`, which only ever forwards it along to `evaluate`), that
    call site is rewritten too, appending the new size argument(s).

    `cb_arg_specs` is an ordered list of (c_type, is_array) describing
    the callback's OWN (rewritten) dummy arguments, for building the
    matching `ctypes.CFUNCTYPE` signature. `iface_lines` is the
    rewritten interface block's own full text (from `interface` through
    `end interface`) -- the SHIM needs its own copy of it (a sibling
    procedure can't see another procedure's own locally-scoped interface
    at all), and if the SAME callback is forwarded to a dependency, that
    dependency's own copy of the interface needs the identical rewrite
    too (the caller's own responsibility, not this function's). PHASE 4
    scope only: every callback argument must be a plain scalar real/
    integer/logical or a plain assumed-shape rank-1 array (`x(:)`, never
    `x(:,:)`); the result must be a plain scalar. Raises
    UnsupportedFunction otherwise.
    """
    out = list(target_lines)
    iface_start = proc_start = proc_end = None
    depth = 0
    for i, ln in enumerate(out):
        code = _strip_comment(ln)
        if INTERFACE_START_RE.match(code):
            if depth == 0:
                iface_start = i
            depth += 1
            continue
        if INTERFACE_END_RE.match(code):
            depth -= 1
            continue
        if depth >= 1 and iface_start is not None and proc_start is None:
            m = PROC_START_RE.match(code)
            if m and m.group(2).lower() == iface_name.lower():
                proc_start = i
                continue
        if depth >= 1 and proc_start is not None and proc_end is None:
            m2 = PROC_END_RE.match(code)
            if m2 and m2.group(2).lower() == iface_name.lower():
                proc_end = i
                break
    if proc_start is None or proc_end is None:
        raise UnsupportedFunction(f"ctypes backend: callback interface {iface_name!r} not found")

    sig_m = SIG_RE.match(_strip_comment(out[proc_start]))
    if not sig_m:
        raise UnsupportedFunction(f"ctypes backend: callback interface {iface_name!r}'s own signature didn't parse")
    cb_args = [a for a in _split_top_level(sig_m.group("args")) if a]
    cb_result_name = iface_name
    if sig_m.group("result"):
        rm = RESULT_NAME_RE.search(sig_m.group("result"))
        if rm:
            cb_result_name = rm.group(1)

    def _cb_decl_for(name):
        for j in range(proc_start + 1, proc_end):
            code = _strip_comment(out[j])
            m = re.search(rf"::\s*({re.escape(name)})\s*(\([^()]*\))?\s*$", code, re.IGNORECASE)
            if m and m.group(1).lower() == name.lower():
                return j, code, m.group(2)
        return None, None, None

    existing_names = {tok.lower() for ln in out for tok in re.findall(r"[A-Za-z_]\w*", ln)}
    synth_counter = [0]

    def _next_synth():
        while True:
            synth_counter[0] += 1
            cand = f"cb_n{synth_counter[0]}"
            if cand not in existing_names:
                existing_names.add(cand)
                return cand

    cb_arg_specs = []
    new_args = []
    size_insertions = []
    extra_call_sources = []  # python-side source array names, for the call-site rewrite below
    for name in cb_args:
        j, decl, shape = _cb_decl_for(name)
        if decl is None:
            raise UnsupportedFunction(f"ctypes backend: callback argument {name!r} has no declaration")
        if re.search(r"\bcharacter\b", decl, re.IGNORECASE):
            raise UnsupportedFunction("ctypes backend: a character callback argument isn't yet supported")
        c_type = _c_interoperable_decl(_base_type_of_decl(decl))
        if shape is None:
            # A scalar dummy in a bind(c) interface is passed BY
            # REFERENCE unless explicitly marked VALUE -- Fortran's own
            # native convention for an interoperable procedure, NOT a
            # detail ctypes' own CFUNCTYPE/trampoline can just infer.
            # Confirmed a real, silent-garbage bug without this: the
            # trampoline received a raw ADDRESS reinterpreted as a
            # plain int (a huge, nonsensical value) instead of the
            # actual argument, since the CFUNCTYPE side assumes
            # ordinary by-value C ints for a plain `ctypes.c_int`
            # argtype.
            if not re.search(r"\bvalue\b", decl, re.IGNORECASE):
                out[j] = re.sub(r"(::)", r", value \1", out[j], count=1, flags=re.IGNORECASE)
            new_args.append(name)
            cb_arg_specs.append((c_type, False))
            continue
        shape_txt = shape.strip("()").strip()
        if shape_txt != ":":
            raise UnsupportedFunction(
                f"ctypes backend: callback argument {name!r}'s own shape {shape_txt!r} isn't plain "
                f"assumed-shape -- not yet supported"
            )
        synth = _next_synth()
        out[j] = re.sub(
            rf"\b{re.escape(name)}\s*\(\s*:\s*\)", f"{name}({synth})", out[j], count=1, flags=re.IGNORECASE
        )
        # The new synth-size dummy ALSO needs VALUE, same reasoning as
        # above -- it's a plain scalar the ctypes side passes by value.
        size_insertions.append(f"         integer, intent(in), value :: {synth}")
        new_args.append(name)
        new_args.append(synth)
        cb_arg_specs.append((c_type, True))
        extra_call_sources.append(name)

    rj, rdecl, rshape = _cb_decl_for(cb_result_name)
    if rdecl is None or rshape is not None:
        raise UnsupportedFunction("ctypes backend: a callback result must be a plain scalar")
    cb_result_c_type = _c_interoperable_decl(_base_type_of_decl(rdecl))

    prefix_m = re.match(
        r"^(\s*(?:pure\s+|elemental\s+|impure\s+|recursive\s+)*)(function|subroutine)\s+[a-z_]\w*\s*\(",
        _strip_comment(out[proc_start]),
        re.IGNORECASE,
    )
    result_clause = f" result({cb_result_name})" if sig_m.group("result") else ""
    out[proc_start] = (
        f"{prefix_m.group(1)}{prefix_m.group(2)} {iface_name}({', '.join(new_args)}) bind(c){result_clause}"
    )
    # An IMPORT statement (e.g. `import dp`) must be the FIRST thing in
    # its own scoping unit's specification part -- inserting the new
    # synth-size declaration immediately after the header line broke
    # this ("IMPORT statement ... cannot follow data declaration
    # statement") whenever the interface body had one, which xp2f.py's
    # own codegen always does for a callback referencing `dp`. Insert
    # after any leading IMPORT line(s) instead.
    insert_at = proc_start + 1
    while insert_at <= proc_end and re.match(r"^\s*import\b", _strip_comment(out[insert_at]), re.IGNORECASE):
        insert_at += 1
    for ins in reversed(size_insertions):
        out.insert(insert_at, ins)
        proc_end += 1

    # The interface block's own closing line -- everything from
    # iface_start through here is what the SHIM needs its own copy of
    # (see this function's own docstring: a sibling procedure can't see
    # another procedure's own LOCALLY-scoped interface at all).
    iface_end = None
    for i in range(proc_end + 1, len(out)):
        if INTERFACE_END_RE.match(_strip_comment(out[i])):
            iface_end = i
            break
    if iface_end is None:
        raise UnsupportedFunction(f"ctypes backend: no closing 'end interface' found for {iface_name!r}")

    if extra_call_sources:
        call_re = re.compile(rf"\b{re.escape(cb_arg_name)}\s*\(([^()]*)\)")
        for i in range(iface_end + 1, len(out)):
            code = _strip_comment(out[i])
            m = call_re.search(code)
            if not m:
                continue
            call_arg_texts = [a.strip() for a in _split_top_level(m.group(1))]
            new_call = (
                f"{cb_arg_name}("
                + ", ".join(call_arg_texts + [f"size({src})" for src in extra_call_sources])
                + ")"
            )
            out[i] = out[i][: m.start()] + new_call + out[i][m.end() :]
            break  # exactly one direct call site expected -- see this function's own docstring

    iface_lines = out[iface_start : iface_end + 1]
    return out, cb_result_c_type, cb_arg_specs, iface_lines


def _inner_call_arg(name: str, c_type: str) -> str:
    """The expression to pass for `name` (an INPUT dummy of the shim's
    own bind(c) declaration) when calling the inner, already-f2py-
    rewritten target -- plain passthrough for real/integer, but a
    `logical(c_bool)` value/array needs converting to the inner target's
    own default `logical` kind first: the two kinds have DIFFERENT
    storage sizes (1 byte vs 4), so passing one directly where the other
    is expected is a real kind mismatch, not just a style choice --
    confirmed via examples/xchoice_tuple_repro.py's own `reject`
    argument ("Error: Type mismatch in argument 'reject' ... LOGICAL(1)
    to LOGICAL(4)"). Fortran's own `LOGICAL(x)` conversion intrinsic is
    ELEMENTAL, so this same wrap is valid for a logical ARRAY argument
    too, not just a scalar.
    """
    if c_type == "logical(c_bool)":
        return f"logical({name})"
    return name


def _array_result_size_expr_to_python(shape, size_source, arg_names_l, decls):
    """Translate a Fortran array-result size expression -- built ONLY
    from the target's own arguments, a synth-size dummy, integer
    literals, and +/-/parens arithmetic (rewrite_target_for_f2py's own
    size derivation -- see _derive_no_alloc_array_size/_infer_rank1_size
    -- never produces anything else) -- into an equivalent Python
    expression string for the ctypes wrapper's own pre-allocation.
    Fortran's `+`/`-`/parens/integer-literal syntax is ALREADY valid
    Python verbatim, and an ordinary scalar argument's own Fortran name
    IS its Python name too -- the only substitution ever needed is a
    synth-size dummy name (never itself Python-facing) -> `len(<its own
    source array's Python name>)`.

    Returns None if the expression references anything else (an unknown
    name -- some other local Fortran variable that leaked through,
    never actually seen in practice) -- the caller then raises
    UnsupportedFunction, same fail-clean philosophy as everywhere else
    in this backend, rather than emitting a Python expression that could
    raise `NameError` or silently compute the wrong thing.
    """
    result = shape
    for nm in set(re.findall(r"[a-z_]\w*", shape, re.IGNORECASE)):
        nm_l = nm.lower()
        if nm_l in size_source:
            result = re.sub(rf"\b{re.escape(nm)}\b", f"len({size_source[nm_l]})", result, flags=re.IGNORECASE)
        elif nm_l in arg_names_l and decls.get(nm_l, (None, None, None))[1] is None:
            pass  # already a valid Python name (a plain scalar argument) -- no substitution needed
        else:
            return None
    return result


def _strip_matching_outer_parens(s: str) -> str:
    """Strip exactly the OUTERMOST matching paren pair wrapping the
    whole (already-trimmed) string `s`, if there is one -- unlike a
    plain `.strip("()")`, which removes EVERY leading/trailing paren
    character regardless of nesting, corrupting a shape expression with
    nested parens of its own (e.g. `(((n + burnin)) - (burnin + 1) +
    1)`: `.strip("()")` over-strips to `n + burnin)) - (burnin + 1) +
    1`, silently mismatched parens). A no-op if `s` isn't wrapped in one
    single pair spanning its entire length.
    """
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        return s
    depth = 0
    for i, ch in enumerate(s):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return s[1:-1].strip() if i == len(s) - 1 else s
    return s


def build_ctypes_shim(
    target_lines,
    arg_names,
    omit_args,
    orig_is_function,
    func_name,
    cb_arg_name=None,
    cb_iface_name=None,
    cb_result_c_type=None,
    cb_arg_specs_inner=None,
    cb_iface_lines=None,
):
    """Build a thin `bind(c)` shim procedure that calls `target_lines`
    (already rewritten by rewrite_target_for_f2py -- explicit-shape,
    scalar-function-converted-to-subroutine, exactly as the f2py backend
    already produces it) unchanged, restoring genuine Fortran FUNCTION
    semantics at the ctypes-visible boundary when `orig_is_function` is
    True AND the target's own result turns out scalar (never an array --
    see below): rewrite_target_for_f2py's own scalar-function-to-subroutine
    conversion exists ONLY to dodge a real f2py code-generation bug (its
    own generated glue wrapper for a module FUNCTION references `dp`
    without importing it) that has no bind(c)/ctypes equivalent at all --
    ctypes' own `restype` handles a genuine function result directly. The
    shim itself decides its own calling convention independent of what
    the INNER target's own post-rewrite shape happens to be; it never
    needs modifying `target_lines` itself, so this carries zero risk to
    the already-tested f2py rewrite it's built on top of.

    Phase 4 adds a callback argument -- `cb_arg_name`/`cb_iface_name`/
    `cb_result_c_type`/`cb_arg_specs_inner`/`cb_iface_lines` are the
    products of _rewrite_callback_interface_for_ctypes, already run by
    the CALLER (never here) on `target_lines` BEFORE it's handed to
    build_trimmed_module -- unlike every other rewrite this function
    itself performs, that one MUST happen before this function runs, not
    inside it: build_trimmed_module is what actually writes the target's
    own body into the trimmed module, so the rewritten (interoperable)
    interface has to already be baked into the `target_lines` the caller
    passes in, or the body written to disk still has the OLD interface,
    mismatched against what this function's own shim expects (see
    _rewrite_callback_interface_for_ctypes's own docstring for exactly
    this bug, confirmed via examples/xcallback_two_arg_repro.py's own
    `evaluate`). Left as optional/`None` parameters (rather than
    detecting the callback here too) specifically so this function can
    never accidentally re-run that rewrite a second time on an
    already-rewritten interface, which would raise (its own explicit-
    shape dummy no longer looks assumed-shape) rather than silently
    misbehave.

    Phase 2 adds rank-1 array arguments/results -- already explicit-shape
    (`x(n_1)` + a synthesized `integer, intent(in) :: n_1` dummy) thanks
    to rewrite_target_for_f2py's own array rewrite, which is bind(c)-legal
    AS-IS modulo the iso_c_binding type mapping (no `type(c_ptr)`/
    `c_f_pointer` indirection needed -- an explicit-shape array of
    interoperable type is directly legal in a bind(c) interface). A
    synth-size dummy (an appended, scalar, integer dummy referenced as
    SOME array's own shape text) is NEVER exposed in the shim's own
    Python-facing signature at all -- ctypes computes it automatically
    from that array's own `len()` (see generate_ctypes_wrapper) the same
    way a caller never has to think about it in the original Python
    function either. An array RESULT's own size is resolved the same
    way, when it's simply one of these known synth-size names (the
    common case, confirmed via examples/xfsolve.py's own `equations` and
    examples/xchoice_tuple_repro.py's own `backbin_rc` -- both size their
    own array output directly off an existing synth-size dummy, never a
    more complex expression). Still not yet supported: `character`
    arguments/results (a later phase), and any size expression that
    ISN'T simply a known synth-size name (raises UnsupportedFunction --
    the data-dependent-length "bridge" convention and a genuinely
    computed size expression are deferred pending a real example, since
    none exists in the corpus yet to verify a design against).

    Returns (shim_text, c_arg_specs, is_shim_function, shim_symbol,
    result_c_type) -- `result_c_type` is the iso_c_binding type string for
    the shim's own SCALAR function result when `is_shim_function` is
    True, else None (a subroutine-shaped shim returns nothing in C terms;
    ctypes' own `restype` must be set to `None`, not skipped, or it
    defaults to `c_int` and misinterprets whatever garbage happens to be
    in that register). `c_arg_specs` is an ordered list of
    (python_arg_name, c_type_str, kind, meta) for every dummy the shim's
    own Python-facing signature EXPOSES (an `omit_args` name, and any
    synth-size dummy, are both dropped entirely -- see above). `kind` is
    one of:
    - `"value"`: an ordinary by-VALUE scalar input.
    - `"out_ref"`: a scalar `intent(out)` dummy (no VALUE attribute, so
      passed by ADDRESS) -- ctypes needs `POINTER(c_type)` and
      `ctypes.byref(...)`.
    - `"array_in"`: a rank-1 array argument, passed as a plain pointer --
      `meta` is the array's own synth-size dummy name (or a literal
      shape string), used to compute how much of the caller's own numpy
      array to read.
    - `"array_out"`: a rank-1 array result, passed as a pointer to a
      buffer the WRAPPER must pre-allocate before calling -- `meta` is
      the Python expression (already translated) for how many elements
      to allocate.
    - `"size_of"`: NOT user-facing -- a synth-size dummy tied to some
      array argument (`meta` names it); its own value is computed
      automatically as `len(<that array>)`.
    - `"string_in"`: a scalar character INPUT argument, passed as a raw
      byte buffer (`c_type` is the literal string `"character"`, not an
      iso_c_binding type name -- handled specially, never looked up in
      `_CTYPES_TYPE_NAMES`). Always immediately followed by one
      `"strlen_of"` entry.
    - `"strlen_of"`: NOT user-facing -- the companion byte-length dummy
      for the `"string_in"` entry immediately before it (`meta` names
      that string argument); computed automatically as
      `len(<that argument's own encoded bytes>)`.
    - `"callback"`: a user-supplied Python callable (`c_type` is the
      literal string `"callback"`, never looked up in
      `_CTYPES_TYPE_NAMES`), passed as a raw `ctypes.CFUNCTYPE` instance.
      `meta` is `(iface_name, cb_result_c_type, cb_arg_specs)` -- see
      _rewrite_callback_interface_for_ctypes's own docstring for
      `cb_arg_specs`' own shape -- used to build the matching CFUNCTYPE
      signature and a small trampoline converting a raw array pointer
      argument back into a numpy array before calling the user's own
      function.
    `generate_ctypes_wrapper` uses this to build the matching ctypes
    `argtypes`/`restype` and marshaling code.
    """
    sig_m = SIG_RE.match(_strip_comment(target_lines[0]))
    if not sig_m:
        raise UnsupportedFunction("ctypes backend: target's own post-rewrite signature line didn't parse")
    post_args = [a for a in _split_top_level(sig_m.group("args")) if a]
    arg_names_l = {a.lower() for a in arg_names}
    # Any post-rewrite dummy NOT among the target's own ORIGINAL Python
    # arguments is one rewrite_target_for_f2py itself appended -- the
    # scalar function's own converted result, an array result's own
    # dummy, or a synthesized array-size dummy.
    appended = {a.lower() for a in post_args if a.lower() not in arg_names_l}

    def _decl_for(name):
        # Skip content inside a nested `interface ... end interface`
        # block -- a callback argument's own abstract interface -- same
        # reasoning as rewrite_target_for_f2py's OWN _find_decl: that
        # interface's own dummy arguments (e.g. `x(:)`) are a DIFFERENT
        # declaration than the target's own outer one of the same name,
        # and must never be mistaken for it.
        in_interface = False
        for ln in target_lines[1:]:
            code = _strip_comment(ln)
            if INTERFACE_START_RE.match(code):
                in_interface = True
                continue
            if INTERFACE_END_RE.match(code):
                in_interface = False
                continue
            if in_interface:
                continue
            idx = code.rfind("::")
            if idx == -1:
                continue
            tail = code[idx + 2 :].strip()
            nm = re.match(rf"^{re.escape(name)}\b", tail, re.IGNORECASE)
            if not nm:
                continue
            rest = tail[nm.end() :].strip()
            if not rest:
                return code, None  # plain scalar, no shape at all
            if not rest.startswith("("):
                continue  # some other suffix (e.g. a DIFFERENT name sharing this prefix) -- not a match
            # A derived array-result size expression can nest parens
            # arbitrarily (e.g. rewrite_target_for_f2py's own closed-form
            # range length, `func_res(((n + burnin)) - (burnin + 1) +
            # 1)`) -- a plain non-nesting `\([^()]*\)` regex silently
            # fails to match the WHOLE shape at all here, confirmed a
            # real bug via examples/xarma_aic_fit.py's own
            # `simulate_arma`: "no declaration found for 'func_res'"
            # (the line existed, the regex just couldn't see it). Track
            # paren depth by hand instead.
            depth = 0
            end = None
            for i, ch in enumerate(rest):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            if end is None:
                continue  # unbalanced -- not a match
            return code, rest[: end + 1]
        return None, None

    decls = {}  # name.lower() -> (decl_line, shape_or_None, is_char)
    for name in post_args:
        decl, shape = _decl_for(name)
        if decl is None:
            raise UnsupportedFunction(f"ctypes backend: no declaration found for {name!r}")
        is_char = bool(re.search(r"\bcharacter\b", decl, re.IGNORECASE))
        decls[name.lower()] = (decl, _strip_matching_outer_parens(shape) if shape else None, is_char)

    # A synth-size dummy: appended, scalar (no shape of its own), and
    # referenced as some OTHER dummy's own shape text -- its VALUE is
    # computed automatically by the wrapper from that array's own
    # length, never exposed as a distinct Python-facing parameter.
    # Prefer an ARRAY_IN source over an array_out one (an output's own
    # size is derived from an input the caller already provided, never
    # the reverse) when more than one array happens to share the same
    # synth-size name.
    size_source: dict[str, str] = {}
    for name in post_args:
        _decl, shape, _is_char = decls[name.lower()]
        if shape and re.match(r"^[a-z_]\w*$", shape, re.IGNORECASE) and shape.lower() in appended:
            if shape.lower() not in size_source or name.lower() not in appended:
                size_source[shape.lower()] = name
    size_dummy_names = set(size_source.keys())

    c_arg_specs = []
    shim_call_args = []
    shim_decls = []
    shim_dummy_names = []  # the shim's OWN Fortran argument list, in order
    shim_body_extra = []  # executable statements needed BEFORE the inner call (e.g. string reconstruction)
    shim_body_after = []  # executable statements needed AFTER the inner call (e.g. logical result conversion)
    result_c_type = None
    result_name = None

    for name in post_args:
        name_l = name.lower()
        if name_l in size_dummy_names:
            # Never exposed as a distinct PYTHON-facing parameter -- see
            # size_source above -- but still a real dummy in the SHIM's
            # own Fortran signature (bind(c) explicit-shape arrays always
            # need an explicit int length passed alongside) and thus a
            # real slot in the ACTUAL ctypes call `generate_ctypes_wrapper`
            # has to build. "size_of" tells it to compute this argument's
            # own value automatically, as `len(<source array's own
            # Python name>)`, instead of asking the caller for it.
            c_type = _c_interoperable_decl(_base_type_of_decl(decls[name_l][0]))
            shim_decls.append(f"   {c_type}, value :: {name}")
            shim_call_args.append(f"{name}={name}")
            shim_dummy_names.append(name)
            c_arg_specs.append((name, c_type, "size_of", size_source[name_l]))
            continue
        decl, shape, is_char = decls[name_l]
        is_array = shape is not None
        is_appended = name_l in appended
        if cb_arg_name is not None and name_l == cb_arg_name.lower():
            # The callback dummy itself -- `procedure(IFACE) :: f`
            # becomes `type(c_funptr), value :: f` in the shim (the raw
            # C function pointer ctypes actually hands over), converted
            # to a genuine Fortran PROCEDURE POINTER via
            # `c_f_procpointer` before being passed, unchanged, to the
            # inner (untouched) target -- which still expects
            # `procedure(IFACE) :: f` exactly as xp2f.py emitted it, now
            # satisfied because IFACE's own interface was ALREADY
            # rewritten to be interoperable (see
            # _rewrite_callback_interface_for_ctypes's own docstring for
            # why that rewrite, not just this pointer conversion, is
            # what actually makes the call safe).
            ptr_name = f"{name}_ptr"
            shim_decls.append(f"   type(c_funptr), value :: {name}")
            shim_decls.append(f"   procedure({cb_iface_name}), pointer :: {ptr_name}")
            shim_body_extra.append(f"   call c_f_procpointer({name}, {ptr_name})")
            shim_call_args.append(f"{name}={ptr_name}")
            shim_dummy_names.append(name)
            c_arg_specs.append((name, "callback", "callback", (cb_iface_name, cb_result_c_type, cb_arg_specs_inner)))
            continue
        if is_char:
            # A plain SCALAR character INPUT argument (e.g.
            # examples/xxbs.py's own `black_scholes(..., option="call")`)
            # -- xp2f.py always emits this as `character(len=*),
            # intent(in)` (assumed-length), illegal in a bind(c)
            # interface as-is. Not yet supported: a character ARRAY, or
            # a character RESULT (`character(len=:), allocatable` --
            # xp2f.py's own return convention for a `str`) -- deferred,
            # same reasoning as the array-result "bridge" case: no
            # corpus example currently needs either, so nothing to
            # verify a length-bound design against.
            if is_array or is_appended:
                raise UnsupportedFunction(
                    f"ctypes backend: {name!r} is a character array/result -- not yet supported"
                )
            len_name = f"{name}_len"
            str_name = f"{name}_str"
            shim_decls.append(f"   character(kind=c_char), intent(in) :: {name}({len_name})")
            shim_decls.append(f"   integer(c_int), value :: {len_name}")
            shim_decls.append(f"   character(len={len_name}) :: {str_name}")
            shim_decls.append(f"   integer :: {name}_i")
            shim_body_extra.append(
                f"   do {name}_i = 1, {len_name}\n"
                f"      {str_name}({name}_i:{name}_i) = {name}({name}_i)\n"
                f"   end do"
            )
            shim_call_args.append(f"{name}={str_name}")
            shim_dummy_names.append(name)
            shim_dummy_names.append(len_name)
            # TWO c_arg_specs entries, matching the TWO actual Fortran
            # dummy slots in order -- "strlen_of" (like "size_of" for an
            # array) is never user-facing; its own value is computed
            # automatically as `len(<source string arg's own encoded
            # bytes>)`, never asked of the caller directly.
            c_arg_specs.append((name, "character", "string_in", None))
            c_arg_specs.append((len_name, "integer(c_int)", "strlen_of", name))
            continue
        c_type = _c_interoperable_decl(_base_type_of_decl(decl))
        if is_array:
            if is_appended:
                # Array RESULT/output. Its own shape is a Fortran
                # expression built (by rewrite_target_for_f2py's own
                # size derivation -- see _derive_no_alloc_array_size/
                # _infer_rank1_size) from ONLY: the target's own
                # arguments, a synth-size dummy, integer literals, and
                # +/-/parens arithmetic -- e.g. examples/xar_acf.py's own
                # `(nacf + 1) - (1)` (`nacf` a plain scalar argument) or
                # examples/xarma_aic_fit.py's own `((n + burnin)) -
                # (burnin + 1) + 1` (`n`/`burnin` both plain scalar
                # arguments). Fortran's own `+`/`-`/parens/integer-
                # literal syntax is ALREADY valid Python verbatim, and an
                # ordinary scalar argument's own Fortran name IS its
                # Python name too -- the ONLY substitution ever needed is
                # a synth-size dummy (never itself Python-facing) ->
                # `len(<its own source array's Python name>)`. See
                # _array_result_size_expr_to_python's own docstring.
                alloc_expr = _array_result_size_expr_to_python(shape, size_source, arg_names_l, decls)
                if alloc_expr is None:
                    raise UnsupportedFunction(
                        f"ctypes backend: {name!r}'s own array-result size expression {shape!r} "
                        f"references something other than a known synth-size dummy, an integer "
                        f"literal, or a plain scalar argument -- not yet supported"
                    )
                shim_decls.append(f"   {c_type}, intent(out) :: {name}({shape})")
                shim_call_args.append(f"{name}={name}")
                shim_dummy_names.append(name)
                c_arg_specs.append((name, c_type, "array_out", alloc_expr))
            else:
                # Array argument -- intent(in) OR intent(inout) (mirror
                # the INNER target's own declared intent exactly; a bare
                # `intent(in)` guess broke examples/xchoice_tuple_repro.py's
                # own `choice`, an inout array, with a real gfortran
                # error: "Dummy argument 'choice' with INTENT(IN) in
                # variable definition context"). Both marshal identically
                # on the ctypes side either way: a numpy array's own
                # buffer is already mutable in place, so passing its
                # pointer once naturally reflects an in-place mutation
                # back to the caller with no special handling needed.
                intent_kw = "inout" if re.search(r"intent\s*\(\s*inout\s*\)", decl, re.IGNORECASE) else "in"
                shim_decls.append(f"   {c_type}, intent({intent_kw}) :: {name}({shape})")
                shim_call_args.append(f"{name}={_inner_call_arg(name, c_type)}")
                shim_dummy_names.append(name)
                c_arg_specs.append((name, c_type, "array_in", shape))
            continue
        if is_appended:
            result_c_type, result_name = c_type, name
            if orig_is_function:
                # We already know (the `if is_array` branch above didn't
                # fire) that THIS appended name is scalar -- regardless
                # of whether some OTHER argument happens to be an array.
                if c_type == "logical(c_bool)":
                    # Same by-value real-vs-c_bool kind mismatch as
                    # _inner_call_arg fixes for an INPUT -- but this is
                    # the OUTPUT direction (writing the inner target's
                    # own default-`logical` result INTO the shim's own
                    # `logical(c_bool)` one), so a plain conversion-
                    # wrapped expression won't do; the inner call needs a
                    # genuine local variable of the INNER target's own
                    # kind to write through, converted afterward.
                    # Confirmed a real bug via examples/xprime.py's own
                    # `is_prime` (a logical-returning function): "Type
                    # mismatch in argument 'func_res' ... LOGICAL(1) to
                    # LOGICAL(4)".
                    tmp_name = f"{name}_tmp"
                    shim_decls.append(f"   logical :: {tmp_name}")
                    shim_call_args.append(f"{name}={tmp_name}")
                    shim_body_after.append(f"   xpc_{name} = logical({tmp_name}, kind=c_bool)")
                else:
                    shim_call_args.append(f"{name}=xpc_{name}")
                # No dummy declaration at all -- this becomes the SHIM's
                # own function result variable instead, declared in the
                # `result(...)` clause built below.
                continue
            shim_decls.append(f"   {c_type}, intent(out) :: {name}")
            shim_call_args.append(f"{name}={name}")
            shim_dummy_names.append(name)
            c_arg_specs.append((name, c_type, "out_ref", None))
            continue
        if name_l in omit_args:
            # Genuinely unused by the target's own body (see
            # _unused_scalar_target_args) -- the inner target already
            # accepts a call omitting it (already marked `optional` by
            # _mark_args_optional), so the shim just never declares it.
            # KEYWORD calls throughout (see the SAME reasoning right
            # above `inner_call`'s own construction) are exactly what
            # makes simply omitting this one safe -- a POSITIONAL call
            # would silently shift every LATER argument into the wrong
            # slot instead (confirmed a real bug via
            # examples/xequicorr_turnover.py's own `rng`, followed by
            # its own array result `turnover`: "Type mismatch in
            # argument 'rng' ... passed REAL(8) to INTEGER(4)").
            continue
        shim_decls.append(f"   {c_type}, value :: {name}")
        shim_call_args.append(f"{name}={_inner_call_arg(name, c_type)}")
        shim_dummy_names.append(name)
        c_arg_specs.append((name, c_type, "value", None))

    shim_symbol = f"xpc_{func_name}"
    inner_call = f"call {func_name}(" + ", ".join(shim_call_args) + ")"
    # A sibling procedure can't see another procedure's own locally-
    # scoped interface at all -- the shim needs its own copy of the
    # (already-rewritten, interoperable) callback interface too.
    iface_block = list(cb_iface_lines) if cb_iface_lines else []
    body = (
        ["   use, intrinsic :: iso_c_binding"] + iface_block + shim_decls + [""] + shim_body_extra
        + [f"   {inner_call}"] + shim_body_after
    )
    arglist = ", ".join(shim_dummy_names)

    if orig_is_function and result_name is not None:
        header = f"function {shim_symbol}({arglist}) bind(c, name=\"{shim_symbol}\") result(xpc_{result_name})"
        body.insert(1, f"   {result_c_type} :: xpc_{result_name}")
        text = "\n".join([header] + body + [f"end function {shim_symbol}"])
        return text, c_arg_specs, True, shim_symbol, result_c_type

    header = f"subroutine {shim_symbol}({arglist}) bind(c, name=\"{shim_symbol}\")"
    text = "\n".join([header] + body + [f"end subroutine {shim_symbol}"])
    return text, c_arg_specs, False, shim_symbol, None


def build_ctypes_extension(trimmed_path: Path, out_dir: Path, compiler_flags: list[str], needs_lapack: bool):
    """Compile `trimmed_path` (the trimmed module, with a ctypes shim
    already appended via append_procedure_to_module) into a shared
    library via a PLAIN `gfortran -shared` invocation -- no meson, no
    crackfortran, no f2cmap, none of f2py's own pipeline. Confirmed
    empirically: a `bind(c, name=...)` symbol is exported and callable
    via `ctypes.CDLL(...)` with NO extra export flags needed on this
    toolchain (a minimal proof-of-concept built and called cleanly
    without `-Wl,--export-all-symbols` or any DLLEXPORT attribute).

    Returns the compiled library's own Path, or None on a build failure
    (already printed, matching this project's own established per-stage
    reporting style).
    """
    dll_path = out_dir / f"{trimmed_path.stem}_ctypes_ext.dll"
    cmd = ["gfortran", "-shared", "-fPIC", "-O2"]
    if compiler_flags:
        cmd.extend(compiler_flags)
    cmd.extend(["-o", str(dll_path), str(trimmed_path)])
    if needs_lapack:
        lapack_lib = _ensure_lapack_archive()
        if lapack_lib is not None:
            lapack_dir, lapack_stem = lapack_lib
            cmd.extend([f"-L{lapack_dir}", f"-l{lapack_stem}"])
    proc = subprocess.run(cmd, cwd=out_dir, capture_output=True, text=True)
    if proc.returncode != 0 or not dll_path.exists():
        print("Ctypes Build: FAIL")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        return None
    return dll_path


_CTYPES_TYPE_NAMES = {
    "real(c_double)": "ctypes.c_double",
    "integer(c_int)": "ctypes.c_int",
    "logical(c_bool)": "ctypes.c_bool",
}
_CTYPES_NP_DTYPE = {
    "real(c_double)": "np.float64",
    "integer(c_int)": "np.intc",
    "logical(c_bool)": "np.bool_",
}


def generate_ctypes_wrapper(
    dll_path: Path,
    func_name: str,
    shim_symbol: str,
    c_arg_specs,
    is_shim_function: bool,
    result_c_type,
    arg_names,
    omit_args,
) -> str:
    """Like generate_wrapper, but for the ctypes backend: loads the
    compiled shared library via `ctypes.CDLL`, sets `argtypes`/`restype`
    on the bind(c) shim symbol, and writes a thin Python function with
    the SAME name/signature as the original -- same filename convention
    (`{func_name}_f.py`) as the f2py backend's own wrapper, so --run-both/
    --all/--except/build_run_both_source need no changes at all to work
    with either backend.

    `arg_names`/`omit_args` (the target's own ORIGINAL Python argument
    names, in order, and which of them build_ctypes_shim's own
    `_unused_scalar_target_args` check found genuinely unused) are needed
    because an omitted name is dropped from `c_arg_specs` ENTIRELY --
    without them, this function would have no way to know the outer,
    Python-facing signature is still supposed to ACCEPT (just silently
    ignore) that argument too, matching both the original Python
    function's own signature and generate_wrapper's own f2py-backend
    contract. Confirmed a real bug without this: `simulate_turnover`'s
    own ctypes wrapper only accepted 4 arguments where the original
    (and the f2py-backend wrapper) both accept 5, breaking any caller
    that still passes the unused `rng` positionally (`TypeError:
    simulate_turnover() takes 4 positional arguments but 5 were given`).

    `c_arg_specs` (see build_ctypes_shim's own docstring) is the shim's
    OWN complete, ordered Fortran argument list -- `argtypes` and the
    actual ctypes call are built by iterating it directly, one clause per
    `mode`:
    - `"value"`: an ordinary user-supplied scalar, passed by value.
    - `"size_of"`: NOT user-facing at all -- its own value is computed
      automatically as `len(<source array>)` (`meta` names which one).
    - `"out_ref"`: passed by ADDRESS (`ctypes.byref(...)`) to a fresh
      local ctypes instance, whose own `.value` is read back afterward
      and returned.
    - `"array_in"`: a user-supplied array-like, converted to a
      C-contiguous numpy array of the matching dtype (accepts a plain
      Python list too, not just an existing ndarray) and passed as a raw
      pointer via `.ctypes.data_as(...)`.
    - `"array_out"`: a fresh numpy buffer the wrapper itself pre-allocates
      (sized by `meta`, an already-Python-valid size expression) and
      passes as a pointer, returned once the call fills it in.
    - `"string_in"`: a user-supplied `str`, encoded to utf-8 bytes and
      passed as a plain `c_char_p`. Always immediately followed by a
      `"strlen_of"` entry, NOT user-facing, whose own value is the byte
      length of that same encoded string.
    """
    # `is_scalar_only`'s own fast path calls `_shim(args_sig)` DIRECTLY,
    # passing every name in `args_sig` straight through positionally --
    # only safe when args_sig exactly matches the shim's own real
    # argument list, which isn't true when an omitted name is mixed in
    # (it must still appear in the OUTER Python-facing signature below,
    # but never reaches the shim at all).
    is_scalar_only = (
        is_shim_function and not omit_args and all(mode == "value" for _, _, mode, _ in c_arg_specs)
    )
    input_specs = [s for s in c_arg_specs if s[2] in ("value", "array_in", "string_in", "callback")]
    # A purely scalar target still needs numpy for its own vectorize
    # fallback below (an external caller, unlike this project's own
    # generated Fortran, might pass an array anyway -- see its own
    # comment), not just when an array mode is already present.
    needs_numpy = is_scalar_only or any(
        mode in ("array_in", "array_out", "callback") for _, _, mode, _ in c_arg_specs
    )
    # The FULL original argument list, in ORIGINAL order, including any
    # omitted name -- see this function's own docstring for why (the
    # outer, Python-facing signature must still ACCEPT it, even though
    # it's never forwarded to the shim at all).
    args_sig = ", ".join(arg_names)

    # A callback argument needs its own MODULE-LEVEL ctypes.CFUNCTYPE
    # (its argtypes/restype describe the callback's OWN, already-
    # rewritten-for-interop signature -- see
    # _rewrite_callback_interface_for_ctypes's own docstring for
    # `cb_arg_specs`' shape) -- built once here, referenced both in
    # `_shim.argtypes` and when wrapping the user's own callable before
    # each call.
    functype_decls = []
    functype_var = {}
    for n, t, mode, meta in c_arg_specs:
        if mode != "callback":
            continue
        _iface_name, cb_result_c_type, cb_arg_specs_inner = meta
        cb_argtypes = []
        for cb_c_type, cb_is_array in cb_arg_specs_inner:
            cb_ct = _CTYPES_TYPE_NAMES[cb_c_type]
            if cb_is_array:
                cb_argtypes.append(f"ctypes.POINTER({cb_ct})")
                cb_argtypes.append("ctypes.c_int")
            else:
                cb_argtypes.append(cb_ct)
        var = f"_{n}_functype"
        functype_var[n] = var
        functype_decls.append(
            f"{var} = ctypes.CFUNCTYPE({_CTYPES_TYPE_NAMES[cb_result_c_type]}, {', '.join(cb_argtypes)})\n"
        )

    def _argtype_for(n, t, mode):
        if mode == "string_in":
            return "ctypes.c_char_p"
        if mode == "callback":
            return functype_var[n]
        if mode in ("value", "size_of", "strlen_of"):
            return _CTYPES_TYPE_NAMES[t]
        return f"ctypes.POINTER({_CTYPES_TYPE_NAMES[t]})"

    argtypes_src = ", ".join(_argtype_for(n, t, mode) for n, t, mode, _ in c_arg_specs)
    # ctypes defaults an unset `restype` to `c_int`, silently misreading
    # whatever happens to be in that register -- a void (subroutine-
    # shaped) shim needs `restype = None` explicitly, not just omitted.
    restype_src = _CTYPES_TYPE_NAMES[result_c_type] if is_shim_function else "None"

    header = (
        "# Generated by xpfunc2f.py -- a thin ctypes wrapper around the compiled\n"
        f"# bind(c) translation of `{func_name}`. Same name, same call signature\n"
        "# as the original Python function; drop-in replacement at call sites.\n"
        "import ctypes\n"
        "import os\n" + ("import numpy as np\n" if needs_numpy else "") + "\n"
        f"_dll = ctypes.CDLL(os.path.join(os.path.dirname(os.path.abspath(__file__)), {dll_path.name!r}))\n"
        + "".join(functype_decls)
        + f"_shim = _dll.{shim_symbol}\n"
        f"_shim.argtypes = [{argtypes_src}]\n"
        f"_shim.restype = {restype_src}\n\n\n"
    )

    if is_scalar_only:
        # A target with NO array argument/result at all is exactly the
        # case where an external caller -- unlike this project's own
        # generated Fortran, which only ever calls it scalar-wise --
        # might pass an array anyway, e.g. scipy's `curve_fit` calling
        # its own `model` callback with the WHOLE xdata array at once.
        # f2py's OWN vectorize_scalars fallback (generate_wrapper) exists
        # for the exact same reason; ctypes has no automatic marshaling
        # at all for a scalar dummy given an array, so without this it
        # would just raise a plain ctypes ArgumentError instead of
        # working -- falls back to elementwise dispatch (matching
        # ordinary numpy broadcasting) whenever any argument passed is
        # itself array-like, while an ordinary scalar call still goes
        # straight to the compiled extension with no per-call overhead.
        if not args_sig:
            return header + f"def {func_name}():\n    return _shim()\n"
        return header + (
            f"def {func_name}({args_sig}):\n"
            f"    if any(hasattr(_v, '__len__') for _v in ({args_sig},)):\n"
            f"        return np.vectorize(_shim)({args_sig})\n"
            f"    return _shim({args_sig})\n"
        )

    body = [f"def {func_name}({args_sig}):\n"]
    call_parts = []
    out_names = []
    for n, t, mode, meta in c_arg_specs:
        ct = _CTYPES_TYPE_NAMES.get(t)
        if mode == "value":
            call_parts.append(n)
        elif mode == "size_of":
            call_parts.append(f"len({meta})")
        elif mode == "string_in":
            body.append(f"    _{n}_bytes = str({n}).encode('utf-8')\n")
            call_parts.append(f"_{n}_bytes")
        elif mode == "strlen_of":
            call_parts.append(f"len(_{meta}_bytes)")
        elif mode == "array_in":
            body.append(f"    _{n}_arr = np.ascontiguousarray({n}, dtype={_CTYPES_NP_DTYPE[t]})\n")
            body.append(f"    _{n}_p = _{n}_arr.ctypes.data_as(ctypes.POINTER({ct}))\n")
            call_parts.append(f"_{n}_p")
        elif mode == "out_ref":
            body.append(f"    _{n} = {ct}()\n")
            call_parts.append(f"ctypes.byref(_{n})")
            out_names.append(f"_{n}.value")
        elif mode == "array_out":
            body.append(f"    _{n}_arr = np.empty({meta}, dtype={_CTYPES_NP_DTYPE[t]})\n")
            body.append(f"    _{n}_p = _{n}_arr.ctypes.data_as(ctypes.POINTER({ct}))\n")
            call_parts.append(f"_{n}_p")
            out_names.append(f"_{n}_arr")
        elif mode == "callback":
            # A small trampoline matching the callback's OWN rewritten,
            # interoperable signature exactly -- one parameter per
            # `cb_arg_specs_inner` entry (a POINTER+length PAIR for an
            # array, a plain scalar otherwise), converting a raw array
            # pointer back into a numpy array (`np.ctypeslib.as_array`)
            # before calling the user's OWN Python callable with
            # arguments matching what it originally expected.
            _iface_name, _cb_result_c_type, cb_arg_specs_inner = meta
            params = []
            call_inner_args = []
            trampoline_body = []
            for idx, (cb_c_type, cb_is_array) in enumerate(cb_arg_specs_inner):
                if cb_is_array:
                    p_ptr, p_n = f"_p{idx}", f"_n{idx}"
                    params.append(p_ptr)
                    params.append(p_n)
                    arr_var = f"_arr{idx}"
                    trampoline_body.append(f"        {arr_var} = np.ctypeslib.as_array({p_ptr}, shape=({p_n},))\n")
                    call_inner_args.append(arr_var)
                else:
                    p = f"_p{idx}"
                    params.append(p)
                    call_inner_args.append(p)
            trampoline_name = f"_{n}_trampoline"
            body.append(f"    def {trampoline_name}({', '.join(params)}):\n")
            body.extend(trampoline_body)
            body.append(f"        return {n}({', '.join(call_inner_args)})\n")
            call_parts.append(f"{functype_var[n]}({trampoline_name})")

    if is_shim_function:
        body.append(f"    return _shim({', '.join(call_parts)})\n")
        return header + "".join(body)

    body.append(f"    _shim({', '.join(call_parts)})\n")
    body.append("    return " + (out_names[0] if len(out_names) == 1 else ", ".join(out_names)) + "\n")
    return header + "".join(body)


PROGRAM_START_RE = re.compile(r"^\s*program\s+([a-z_]\w*)\s*$", re.IGNORECASE)
PROGRAM_END_RE = re.compile(r"^\s*end\s+program\b", re.IGNORECASE)
_LITERAL_TOKEN_RE = re.compile(
    r"""^(?:
        [+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?(?:_[a-z]\w*)?  # numeric, optional _dp-style kind suffix
        |\.(?:true|false)\.                                        # logical
        |'[^']*'                                                    # char literal, single-quoted
        |"[^"]*"                                                    # char literal, double-quoted
    )$""",
    re.IGNORECASE | re.VERBOSE,
)


def _find_program_block(lines):
    """(start, end) inclusive line-index span of the `program ... end
    program` block xp2f.py's own whole-program translation emits after
    the module (the script's own top-level entry point) -- or (None,
    None) if there isn't one (e.g. a module-only/--flat-style
    translation).
    """
    start = end = None
    for i, ln in enumerate(lines):
        code = _strip_comment(ln)
        if start is None:
            if PROGRAM_START_RE.match(code):
                start = i
            continue
        if PROGRAM_END_RE.match(code):
            end = i
            break
    return start, end


_TYPE_DECL_PREFIX_RE = re.compile(
    r"^\s*(integer|real|logical|complex|character|double\s+precision|type|class)\b", re.IGNORECASE
)


def _split_multi_name_var_decls(header):
    """Like _split_multi_name_decls, but scoped to ONLY a genuine TYPE
    declaration line (one whose own prefix starts with a real Fortran
    type keyword) -- never a `use ..., only: a, b, c` header line, which
    ALSO has a top-level `::` (right after `intrinsic`) and top-level
    commas of its own, but means something completely different: naively
    running the general splitter over the WHOLE header corrupted it,
    confirmed a real bug via examples/xma_persist.py's own `use,
    intrinsic :: ieee_arithmetic, only: ieee_value, ieee_quiet_nan,
    ieee_is_nan` -- split into several bogus, syntactically-broken `use`
    lines (one of them literally `use, intrinsic :: only: ieee_value`),
    a silent corruption that built and failed ONLY once f2py itself
    tried to compile the result (well past Extract/every earlier check).
    """
    out = []
    for ln in header:
        code = _strip_comment(ln)
        idx = _find_top_level_double_colon(code)
        if idx is None or not _TYPE_DECL_PREFIX_RE.match(code[:idx]):
            out.append(ln)
            continue
        prefix, names_part = code[:idx], code[idx + 2 :]
        names = _split_top_level(names_part)
        if len(names) <= 1:
            out.append(ln)
            continue
        trailing = ln[len(code) :]
        for nm in names:
            out.append(f"{prefix}:: {nm.strip()}")
        out[-1] += trailing
    return out


def _module_level_var_decls(header):
    """Yield (line_idx, prefix, name, shape_or_None) for each plain
    module-level VARIABLE declared in `header` that does NOT already
    carry its own inline initializer -- skips `parameter`s (already a
    compile-time constant, nothing to hoist) and any declaration that
    already has one (e.g. `= 0.0_dp`). A candidate set for
    hoist_global_initializers below.
    """
    for i, ln in enumerate(header):
        code = _strip_comment(ln)
        idx = _find_top_level_double_colon(code)
        if idx is None:
            continue
        prefix = code[:idx]
        if re.search(r"\bparameter\b", prefix, re.IGNORECASE):
            continue
        # A genuine TYPE declaration only -- `public ::`/`private ::` (an
        # ACCESS specification, not a declaration) shares the same `::`
        # syntax and would otherwise be misread as declaring a scalar
        # variable named after each name it lists (confirmed a real bug:
        # `public :: dp, f, r`'s own `dp` was mistaken for an
        # uninitialized module-level variable needing to be hoisted).
        if not re.match(
            r"^\s*(integer|real|logical|complex|character|double\s+precision|type|class)\b",
            prefix,
            re.IGNORECASE,
        ):
            continue
        for decl in _split_top_level(code[idx + 2 :]):
            decl = decl.strip()
            if "=" in decl:
                continue
            m = re.match(r"^([a-z_]\w*)\s*(?:\(([^()]*)\))?\s*$", decl, re.IGNORECASE)
            if m:
                yield i, prefix, m.group(1), m.group(2)


def _hoistable_literal_value(rhs: str):
    """If `rhs` (an assignment's own right-hand side text) is either a
    single literal token, or an array-constructor `[literal, literal,
    ...]` (an optional leading `TYPE ::` type-spec accepted, xp2f.py's
    own idiom for a typed constructor) of ONLY literal elements, return
    (value_text_to_emit, element_count_or_None) -- element_count is None
    for a scalar. Returns None for anything else (a name reference, a
    function call, an operator between two operands, ...) -- deliberately
    conservative, same "only when provably safe" spirit as
    _derive_no_alloc_array_size.
    """
    rhs = rhs.strip()
    m = re.match(r"^\[\s*(?:[a-z]\w*(?:\([^()]*\))?\s*::\s*)?(.*)\]$", rhs, re.IGNORECASE | re.DOTALL)
    if m:
        elems = [e.strip() for e in _split_top_level(m.group(1)) if e.strip()]
        if elems and all(_LITERAL_TOKEN_RE.match(e) for e in elems):
            return rhs, len(elems)
        return None
    if _LITERAL_TOKEN_RE.match(rhs):
        return rhs, None
    return None


def _name_declared_locally(body_lines, name):
    """True if `name` is declared as its OWN dummy argument or local
    variable somewhere in `body_lines[1:]` (its own signature line,
    body_lines[0], is skipped -- every dummy argument's name necessarily
    appears there regardless of shadowing, so it says nothing either
    way). Ordinary Fortran scoping: a local/dummy of this name SHADOWS a
    module-level global of the same name completely within this one
    procedure -- any bare reference to `name` inside it means the LOCAL
    one, never the global.
    """
    decl_re = re.compile(rf"::\s*{re.escape(name)}\s*(\([^()]*\))?\s*$", re.IGNORECASE)
    return any(decl_re.search(_strip_comment(ln)) for ln in body_lines[1:])


def hoist_global_initializers(header, lines, needed_bodies):
    """Return a NEW header (list of lines) with each module-level global
    genuinely REFERENCED by `needed_bodies` (a list of per-procedure
    line-lists -- the target's own already-rewritten body, plus every
    dependency's own raw body) given an inline initializer, hoisted from
    the script's own top-level `program` block -- when it's safely
    derivable. Never mutates `header` itself.

    Each procedure's own body is checked SEPARATELY (not flattened into
    one blob) so a same-named LOCAL variable or dummy argument in ONE of
    them -- which, by ordinary Fortran scoping, SHADOWS the module-level
    global entirely within that procedure (see _name_declared_locally)
    -- is correctly excluded from counting as a genuine reference.
    Confirmed a real bug without this: examples/xsim_fit_nagarch_t.py's
    own module-level `r` was never actually referenced by ITS OWN name
    anywhere, but a COMPLETELY UNRELATED dummy argument also happening
    to be named `r(:)`, in a totally different (dependency) procedure,
    was mistaken for a genuine use of the module-level global -- wrongly
    rejecting a bridge that built and ran correctly before this hoisting
    step existed at all (caught by the project's own regression suite).

    xp2f.py's own whole-program translation puts a Python module-level
    assignment's own Fortran equivalent in the `program` block (the
    script's own top-level entry point), never in the module's own
    declaration section -- ordinary Fortran has no equivalent of
    Python's "module-level code runs at import time" for a plain
    variable declaration. Bridging a single function standalone never
    runs that `program` block at all, so a referenced global left merely
    DECLARED (never assigned) is read as garbage -- confirmed
    empirically via examples/xglobal_repro3.py's own module-level `r =
    np.array([1.0, 2.0, 3.0])`, referenced by the bridged function via
    `np.sum(r)`: an unallocated `sum(r)` crashes the Fortran-backed run
    with an access violation (0xC0000005), well past every earlier check
    (Extract/F2PY Build both report PASS -- this only surfaces once the
    compiled extension actually RUNS).

    Only ever hoists a PROVABLY SAFE initializer: a single top-level
    assignment (the program block's own BASE indentation -- the first
    executable statement's own, taken as the "not nested in any do/if/
    ... block" level) to a literal value/array-constructor, with no
    OTHER assignment to the same name anywhere in the program block (a
    later reassignment would make "hoist the first one" silently wrong).
    Raises UnsupportedFunction for anything else (multiple assignments,
    a computed/runtime-dependent value, no program block at all, ...) --
    a clean Extract-time rejection instead of a silent runtime crash.
    """
    prog_start, prog_end = _find_program_block(lines)
    # Merged to ONE logical line per statement first -- xp2f.py's own
    # line-wrapping means even a plain `use ..., only: a, b, c` can
    # `&`-continue across several physical lines, and a raw per-PHYSICAL-
    # line scan used to badly misjudge the block's own base indentation
    # from a continuation line's own (different) leading whitespace,
    # confirmed via examples/xma_persist.py's own multi-line `use`
    # statement: its own base_indent came out as the CONTINUATION line's
    # indent, so the real first statement (`pairwise_corr = 0.3_dp`, at
    # the TRUE base indent) never matched, and a genuinely safe, single,
    # unambiguous `t_cost_one_way = 0.001_dp` assignment was wrongly
    # reported as "found 0" -- a regression this hoisting step itself
    # introduced (a bridge that built and ran fine before it existed).
    prog_lines = _merge_continuations(lines[prog_start : prog_end + 1]) if prog_start is not None else []
    base_indent = None
    if prog_lines:
        for j in range(1, len(prog_lines)):
            code = _strip_comment(prog_lines[j])
            stripped = code.strip()
            if not stripped or stripped.lower() == "implicit none" or stripped.lower().startswith("use "):
                continue
            base_indent = len(prog_lines[j]) - len(prog_lines[j].lstrip())
            break

    # Split to ONE name per declaration line FIRST -- a shared line
    # (`real(kind=dp) :: pairwise_corr, t_cost_one_way`) rewritten IN
    # PLACE for just one of its names would otherwise clobber the WHOLE
    # line, silently dropping every sibling name sharing it. Confirmed a
    # real bug via this exact case (examples/xma_persist.py's own
    # `pairwise_corr`/`t_cost_one_way`, declared together): rewriting
    # `t_cost_one_way`'s own hoisted initializer overwrote `pairwise_corr`
    # right off the line entirely, gfortran rejecting the now-orphaned
    # `public :: ..., pairwise_corr, ...` with "has no IMPLICIT type".
    new_header = _split_multi_name_var_decls(_merge_continuations(list(header)))
    for i, prefix, name, shape in list(_module_level_var_decls(new_header)):
        referenced = False
        for body_lines in needed_bodies:
            if _name_declared_locally(body_lines, name):
                continue  # shadowed by a local/dummy of the same name in THIS procedure
            if any(
                re.search(rf"\b{re.escape(name)}\b", _strip_comment(ln), re.IGNORECASE)
                for ln in body_lines[1:]
            ):
                referenced = True
                break
        if not referenced:
            continue  # not referenced by the target/its dependency closure at all
        if prog_start is None:
            raise UnsupportedFunction(
                f"references module-level global {name!r}, which has no inline "
                f"initializer and there's no top-level program block to derive "
                f"one from -- can't safely bridge standalone"
            )
        assign_re = re.compile(rf"^(\s*){re.escape(name)}\s*=\s*(.+?)\s*$", re.IGNORECASE)
        matches = []
        for j in range(1, len(prog_lines) - 1):
            m = assign_re.match(_strip_comment(prog_lines[j]))
            if m and (base_indent is None or len(m.group(1)) == base_indent):
                matches.append(m.group(2))
        if len(matches) != 1:
            raise UnsupportedFunction(
                f"references module-level global {name!r}, whose own top-level "
                f"initializer isn't a single, unambiguous assignment in the "
                f"program body (found {len(matches)}) -- can't safely hoist"
            )
        hoistable = _hoistable_literal_value(matches[0])
        if hoistable is None:
            raise UnsupportedFunction(
                f"references module-level global {name!r}, whose own top-level "
                f"initializer ({matches[0]!r}) isn't a literal value/array "
                f"constructor -- can't safely hoist a runtime-computed value into "
                f"the bridged module's own declaration"
            )
        value_text, count = hoistable
        new_prefix = re.sub(r",?\s*allocatable\s*", "", prefix, flags=re.IGNORECASE).rstrip()
        if count is not None:
            if shape is None:
                raise UnsupportedFunction(
                    f"module-level global {name!r} is assigned an array literal "
                    f"but declared as a scalar -- unexpected shape mismatch"
                )
            new_header[i] = f"{new_prefix} :: {name}({count}) = {value_text}"
        else:
            new_header[i] = f"{new_prefix} :: {name} = {value_text}"
    return new_header


def build_trimmed_module(mod_name, header, lines, procedures, needed, override_lines=None):
    override_lines = override_lines or {}
    dropped = {nm for nm in procedures if nm not in needed}
    new_header = []
    # Merged to ONE logical line per statement first -- a `public ::`
    # statement listing many names (common in Burkardt-derived modules)
    # is often `&`-continued across several physical lines, and this
    # loop used to filter dropped names off only the FIRST physical line
    # (the only one PUBLIC_RE's own per-line match ever sees), leaving a
    # continuation line's own names completely unfiltered -- a dropped
    # (no-longer-emitted) procedure name then survived into the trimmed
    # module's own `public ::` list, which gfortran rejects outright
    # ("has no IMPLICIT type", since `public` requires the entity to
    # actually exist). Confirmed via examples/xasa183_inferred.py's own
    # `timestamp` target: none of ITS OWN dependencies (r8_uni,
    # r8_random_test03, ...) belong in `needed`, but they still showed up
    # verbatim, unfiltered, on the public statement's own continuation
    # line. Safe to merge unconditionally here -- the resulting list can
    # only ever be shorter (dropped names removed), never longer, so a
    # single re-joined line is never a problem free-form Fortran can't
    # already handle.
    for ln in _merge_continuations(header):
        m = PUBLIC_RE.match(_strip_comment(ln))
        if m:
            names = [n.strip() for n in m.group(2).split(",")]
            kept = [n for n in names if n.lower() not in dropped]
            new_header.append(f"{m.group(1)}{', '.join(kept)}")
        else:
            new_header.append(ln)

    # `block ... end block` (xp2f.py's own idiom for scoping a loop
    # counter -- confirmed only ever used that way) badly confuses f2py's
    # own Fortran cracker ("crackline: Mismatch of blocks encountered.
    # Trying to fix it by assuming 'end' statement"), corrupting its
    # parsing of EVERYTHING AFTER it in the same file -- not just the
    # enclosing procedure, but every LATER procedure too (see
    # unwrap_block_constructs's own docstring). Previously only ever
    # exercised for the bridge-subroutine's own kept-unchanged copy of
    # the ORIGINAL target; now that a DEPENDENCY's own body is ALSO
    # handed to f2py (kept PRIVATE, so its own array shape or derived
    # type is never itself a problem -- see main()'s own comment -- but
    # a `block` construct is a different kind of trouble, a parser bug
    # rather than a marshalling one), confirmed via examples/
    # xequicorr_bands.py's own `equicorr_cov` dependency: its own
    # `block` corrupted f2py's parsing of the LATER, unrelated inlined
    # python_mod helpers in the same file ("appenddecl: 'dimension' not
    # implemented" on one of them, which -- being unrelated -- would
    # otherwise have built fine). Applied to every procedure copied into
    # the trimmed module's own body, not just the target.
    all_names = {tok.lower() for ln in lines for tok in re.findall(r"[A-Za-z_]\w*", ln)}

    body = []
    for nm in sorted(needed, key=lambda n: procedures[n][0]):
        if nm in override_lines:
            proc_lines = override_lines[nm]
        else:
            start, end = procedures[nm]
            proc_lines = lines[start : end + 1]
        body.extend(unwrap_block_constructs(list(proc_lines), all_names))
        body.append("")

    return "\n".join(new_header + ["contains", ""] + body + [f"end module {mod_name}"]) + "\n"


def find_target_def(tree: ast.Module, name: str, py_path: "Path | None" = None) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    # Not found directly -- the target itself may be defined in a sibling
    # module and only reach the main script via `import`/`from ... import`
    # (xp2f.py's own inline_local_from_imports resolves that at transpile
    # time, which is why Transpile: PASS can succeed for a name this plain
    # tree.body scan never sees). Retry against the same inlined view
    # xp2f.py's Fortran translation already used, rather than reporting a
    # false "not found" for a target this tool can actually bridge.
    if py_path is not None:
        merged = xp2f.inline_local_from_imports(tree, py_path)
        if merged is not tree:
            for node in merged.body:
                if isinstance(node, ast.FunctionDef) and node.name == name:
                    return node
        # Still not found -- covers the `import sibling_module` (attribute-
        # access, `sibling_module.name(...)`) case specifically: unlike a
        # `from sibling_module import name` target, whose local name
        # survives inlining unchanged (caught just above), an attribute-
        # style import's own inlined copy gets RENAMED by
        # inline_local_from_imports (e.g. `sibling_module_name`) to avoid
        # collisions between two sibling modules that both happen to
        # define e.g. `model` -- so no node in the merged tree is ever
        # literally named `name` again. Sidestep the rename entirely by
        # re-parsing each directly-imported sibling module's OWN source
        # and looking for `name` there under its true, un-renamed
        # identity -- correct regardless of import style, since a
        # target's own argument list is fully determined by its own
        # `def`, independent of anything it internally calls.
        for node in tree.body:
            mod_names = []
            if isinstance(node, ast.Import):
                mod_names = [al.name for al in node.names]
            elif isinstance(node, ast.ImportFrom) and not getattr(node, "level", 0) and node.module:
                mod_names = [node.module]
            for mod_name in mod_names:
                mod_path = xp2f.resolve_sibling_module_path(mod_name, py_path)
                if mod_path is None:
                    continue
                try:
                    mod_tree = ast.parse(mod_path.read_text(encoding="utf-8-sig"))
                except OSError:
                    continue
                for mod_node in mod_tree.body:
                    if isinstance(mod_node, ast.FunctionDef) and mod_node.name == name:
                        return mod_node
    raise UnsupportedFunction(f"no top-level `def {name}(...)` found in the source script")


def _iter_pre_order(node):
    """DFS pre-order traversal (a node before its own children, children
    in the order their own AST fields are defined -- e.g. a Call's own
    `func` before its `args`) -- a reasonable approximation of textual/
    source order for the common case, without trying to simulate exact
    runtime evaluation order (which argument of a nested call actually
    runs first) that a script's own real behavior would need to nail
    precisely for a much rarer, more convoluted case.
    """
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _iter_pre_order(child)


def _first_call_target_in_body(stmts, known_defs: dict, visited_mains=None) -> str | None:
    """Scan `stmts` (a list of statements -- the script's own top-level
    body, or `main`'s own body) in source order for the first call to a
    known top-level function. A call to `main` is transparently
    ENTERED (its own body scanned the same way, recursively) rather
    than itself being returned: a `def main(): ...` wrapper's own body
    IS effectively the script's real top-level driver code for this
    purpose (the overwhelmingly common `def main(): ...; main()`
    pattern -- confirmed the hard way: an earlier version of this
    search only ever looked at the literal top level, so once `main()`
    was skipped there was nothing else to find there at all, silently
    falling back to the "first def" rule -- exactly the bias this
    heuristic exists to avoid -- even though main's own body plainly
    calls the intended target). Any OTHER call is returned directly,
    never traced further into ITS OWN body -- if the script calls
    count_primes, that's the answer, regardless of what count_primes
    itself goes on to call.

    Deliberately skips descending into any def/class statement OTHER
    than by way of entering `main` above: a call buried inside some
    other function's own body only runs if THAT function is itself
    invoked, so it doesn't reflect what running the script actually
    does.
    """
    if visited_mains is None:
        visited_mains = set()
    for stmt in stmts:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for node in _iter_pre_order(stmt):
            if not (
                isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in known_defs
            ):
                continue
            name = node.func.id
            if name != "main":
                return name
            if name in visited_mains:
                continue  # already entered once; avoid infinite recursion
            visited_mains.add(name)
            found = _first_call_target_in_body(known_defs[name].body, known_defs, visited_mains)
            if found is not None:
                return found
            # main's own body had no further, OTHER call -- keep
            # scanning whatever comes after this statement/call.
    return None


def default_target_function_name(tree: ast.Module) -> str:
    """The function_name to use when none was given on the command line:
    the first function the script actually CALLS (transparently
    entering a `main()` wrapper's own body, since that's effectively
    the script's real top-level driver code -- see
    _first_call_target_in_body), in source/execution order -- skipping
    a call to `main` itself (typically just an entry-point wrapper
    calling the script's OTHER, more interesting functions, not itself
    a good default target) -- a much better proxy for "the thing this
    script is actually about" than which function merely happens to be
    DEFINED first: Python style commonly defines a low-level dependency
    BEFORE the function that uses it, so "first def" is systematically
    biased toward picking a dependency instead of an entry point
    (confirmed empirically: xprime_func.py defines is_prime, a pure
    dependency never itself called from the top level, before
    count_primes, the function its own driver code actually calls --
    "first def" picks the former, "first called" correctly picks the
    latter).

    Falls back to the first top-level `def` (skipping one named `main`)
    when no call to a known function exists at all, anywhere reachable
    this way -- e.g. a library-style script that only defines functions
    without calling any of them directly.
    """
    known_defs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    called = _first_call_target_in_body(tree.body, known_defs)
    if called is not None:
        return called
    for name, node in known_defs.items():
        if name != "main":
            return name
    raise UnsupportedFunction(
        "no top-level function found to use as a default target (no call to one, "
        "skipping 'main', and no top-level def either) -- pass function_name explicitly"
    )


def _results_match(a, b) -> bool:
    """Compare two --verify results, tuple- and NumPy-array-aware -- a
    plain `a == b` raises ValueError for an array result ("truth value
    of an array ... is ambiguous"), never triggered before array support
    existed since every prior result was a plain scalar/tuple-of-scalars.
    """
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(_results_match(x, y) for x, y in zip(a, b))
    import numpy as np

    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a_arr, b_arr = np.asarray(a), np.asarray(b)
        return a_arr.shape == b_arr.shape and bool(np.allclose(a_arr, b_arr))
    return a == b


def _unused_scalar_target_args(target_lines, arg_names):
    """Which of `arg_names` (the target's own ORIGINAL Python argument
    names, order-preserved) are (a) declared as a plain SCALAR dummy (no
    array shape -- kept narrowly scoped to the observed case; an array
    argument's marshalling is already more involved and untested here)
    and (b) referenced NOWHERE in `target_lines` except their own
    declaration line -- i.e. genuinely unused by the procedure's own
    Fortran body.

    xp2f.py's own whole-program translation sometimes keeps such a dummy
    purely for Python-signature compatibility with the original
    function, even though its actual value plays no role internally --
    confirmed via examples/xmix.py's own `simulate_normal_mixture(n,
    weights, means, sds, rng)`: `rng` (a numpy Generator object in
    Python) becomes a bare `integer, intent(in) :: rng` in Fortran,
    never referenced in the body at all (the actual random draws go
    through a completely different mechanism, RNG-replay or a direct
    Fortran RNG call, neither of which touches this dummy). Forwarding
    the real Generator OBJECT to it unconditionally is never going to
    work (f2py reports "can't be converted to int" -- confirmed
    empirically, an outright runtime TypeError past every earlier
    Extract/F2PY Build check) -- but since it's unused, the fix isn't a
    conversion at all: mark it `optional` (see _mark_args_optional) and
    have the wrapper simply not pass it through (see generate_wrapper's
    own `omit_args`), which is exactly equivalent to what the Fortran
    body already does with it (nothing).
    """
    unused = set()
    for name in arg_names:
        name_re = re.compile(rf"\b{re.escape(name)}\b", re.IGNORECASE)
        decl_re = re.compile(rf"::\s*{re.escape(name)}\s*(\([^()]*\))?\s*$", re.IGNORECASE)
        is_scalar_decl = False
        used_elsewhere = False
        # target_lines[0] is the procedure's own signature line -- every
        # dummy argument's name necessarily appears there (in the
        # parameter list itself), so it must be skipped here or EVERY
        # argument would always look "used" and this would never fire.
        for ln in target_lines[1:]:
            code = _strip_comment(ln)
            if not name_re.search(code):
                continue
            dm = decl_re.search(code)
            if dm:
                if dm.group(1) is None:
                    is_scalar_decl = True
                continue  # its own declaration line; not a use
            used_elsewhere = True
        if is_scalar_decl and not used_elsewhere:
            unused.add(name.lower())
    return unused


def _mark_args_optional(target_lines, names):
    """Return a NEW target_lines with `, optional` added to each named
    dummy's own `intent(...)` attribute list -- lets f2py's compiled
    extension accept a call that OMITS it entirely (see
    _unused_scalar_target_args/generate_wrapper's own `omit_args`),
    instead of requiring some value the wrapper has no safe way to
    provide.
    """
    names_l = {n.lower() for n in names}
    out = []
    for ln in target_lines:
        code = _strip_comment(ln)
        m = re.search(r"::\s*([a-z_]\w*)\s*$", code, re.IGNORECASE)
        if (
            m
            and m.group(1).lower() in names_l
            and not re.search(r"\boptional\b", code, re.IGNORECASE)
        ):
            ln = re.sub(r"(intent\s*\([^)]*\))", r"\1, optional", ln, count=1, flags=re.IGNORECASE)
        out.append(ln)
    return out


def generate_wrapper(
    mod_name, ext_name, func_name, arg_names, omit_args=frozenset(), vectorize_scalars=False,
    fortran_func_name=None,
) -> str:
    if not arg_names:
        vectorize_scalars = False  # nothing to broadcast over; avoid a bare "(,)" tuple literal
    args_sig = ", ".join(arg_names)
    # f2py always lowercases a Fortran dummy's own name for its generated
    # Python-facing keyword (Fortran identifiers are case-insensitive, so
    # f2py canonicalizes to lowercase regardless of how the Fortran
    # source itself spelled it) -- confirmed empirically via a mixed-
    # case argument, examples/xbs_vec.py's own `black_scholes(S, K, T, r,
    # sigma, option)`: the compiled extension's own docstring shows
    # `black_scholes(s,k,t,r,sigma,[option])`, all lowercase, and a
    # keyword call using the ORIGINAL case (`S=S`) raises "missing
    # required argument 's'". The wrapper's OWN Python-facing signature
    # (`args_sig` above) still uses the original case, unaffected --
    # this is a drop-in replacement, so it must accept calls the same
    # way the original Python function did. `omit_args` (see
    # _unused_scalar_target_args) are left OUT of this call entirely --
    # marked `optional` on the Fortran side, genuinely unused by its own
    # body, and often impossible to marshal anyway (e.g. a numpy
    # Generator object has no valid conversion to whatever placeholder
    # scalar type the dummy was given).
    call_args = ", ".join(f"{a.lower()}={a}" for a in arg_names if a.lower() not in omit_args)
    # The SAME lowercasing applies to the compiled extension's own MODULE
    # and PROCEDURE attribute names, not just its dummy-argument keywords
    # -- confirmed empirically via examples/xgcd.py's own `Gcd`: the
    # compiled extension exposes it as `gcd` (f2py's own `--lower` pass),
    # so referencing `{ext_name}.{mod_name}.{func_name}` with the
    # ORIGINAL-case `Gcd` raised "'fortran' object has no attribute
    # 'Gcd'. Did you mean: 'gcd'?" at CALL time -- past every earlier
    # check (Extract/F2PY Build all reported PASS), only surfacing when
    # the wrapper actually ran. `func_name` in the DEF line/docstring
    # above stays the original case, unaffected -- only this attribute-
    # access chain into the compiled extension needs lowering.
    mod_attr = mod_name.lower()
    # Normally the same name as func_name, lowered -- differs only for a
    # target reached via `import sibling_module` (attribute access),
    # which xp2f.py's own inline_local_from_imports renames on the way
    # in (see _resolve_fortran_target_name's own docstring): the compiled
    # extension's own attribute is the RENAMED identifier, even though
    # this wrapper's own outer `def` below still needs to be func_name
    # (the CLI/display name, matching what the caller's own code expects
    # to call) -- these two names can't be collapsed into one anymore.
    func_attr = (fortran_func_name or func_name).lower()
    header_comment = (
        f"# Generated by xpfunc2f.py -- a thin wrapper around the f2py-compiled\n"
        f"# Fortran translation of `{func_name}`. Same name, same call signature\n"
        f"# as the original Python function; drop-in replacement at call sites.\n"
    )
    if not vectorize_scalars:
        return (
            header_comment
            + f"import {ext_name}\n\n\n"
            + f"def {func_name}({args_sig}):\n"
            + f"    return {ext_name}.{mod_attr}.{func_attr}({call_args})\n"
        )
    # A PURELY SCALAR target (no array-shaped argument/result at all --
    # rewrite_target_for_f2py never touched it) is NOT actually a safe
    # drop-in replacement as-is: the ORIGINAL Python function, built from
    # ordinary numpy expressions, transparently broadcasts over an
    # array-valued argument (numpy's own elementwise semantics) -- but
    # f2py's compiled scalar dummy does NOT raise a clear error for an
    # array argument, it silently (mis-)reads just one value out of it.
    # Confirmed a real, dangerous silent-wrong-result bug via
    # examples/xcurve_fit.py's own `model(x, a, b, c)`, passed to real
    # scipy `curve_fit` (still running as ordinary Python in --run-both,
    # only `model` itself replaced) -- curve_fit's own convention calls
    # it with the WHOLE `xdata` array at once, and the compiled scalar
    # `model` silently returned `a*exp(-b*0)+c` (as if x were 0.0)
    # regardless of which actual x values were passed, letting the
    # optimizer converge on a completely wrong, constant-model fit with
    # no error at all. Falls back to elementwise dispatch (matching
    # ordinary numpy broadcasting) whenever ANY argument passed is
    # itself array-like -- kept as a FALLBACK, not the only path, so an
    # ordinary plain-scalar call (this tool's originally-intended usage)
    # still goes straight to the compiled extension with no per-call
    # `np.vectorize` overhead.
    impl_name = f"_{func_name}_scalar_impl"
    return (
        header_comment
        + f"import {ext_name}\n"
        + f"import numpy as np\n\n\n"
        + f"def {impl_name}({args_sig}):\n"
        + f"    return {ext_name}.{mod_attr}.{func_attr}({call_args})\n\n\n"
        + f"def {func_name}({args_sig}):\n"
        + f"    if any(hasattr(_v, '__len__') for _v in ({args_sig},)):\n"
        + f"        return np.vectorize({impl_name})({args_sig})\n"
        + f"    return {impl_name}({args_sig})\n"
    )


def generate_bridge_wrapper(mod_name, ext_name, func_name, arg_names, bridge_name, n_outputs) -> str:
    """Like generate_wrapper, but for a target bridged via
    try_build_bridge_for_target/build_bridge_procedure: the compiled
    extension exposes `bridge_name`, not `func_name` itself, and its
    call returns (out_1, cnt_1, out_2, cnt_2, ...) -- each true, data-
    dependent-length array over-allocated to a provable bound alongside
    its own true count -- so the wrapper trims each `out_i[:cnt_i]`
    before returning, matching what the ORIGINAL Python function itself
    returns (a single array, or a tuple of them).
    """
    args_sig = ", ".join(arg_names)
    # See generate_wrapper's own comment: f2py always lowercases a
    # Fortran dummy's own name for its generated Python-facing keyword,
    # and equally its own MODULE/PROCEDURE attribute names -- lower both
    # here too, same reasoning (examples/xgcd.py's own `Gcd`/`gcd`).
    call_args = ", ".join(f"{a.lower()}={a}" for a in arg_names)
    mod_attr = mod_name.lower()
    bridge_attr = bridge_name.lower()
    raw_names = []
    for i in range(n_outputs):
        raw_names.append(f"_out{i}")
        raw_names.append(f"_cnt{i}")
    unpack = ", ".join(raw_names)
    trims = ", ".join(f"_out{i}[:_cnt{i}]" for i in range(n_outputs))
    return (
        f"# Generated by xpfunc2f.py -- a thin wrapper around the f2py-compiled\n"
        f"# Fortran BRIDGE for `{func_name}` (its own true, data-dependent-length\n"
        f"# array output(s) are over-allocated to a provable bound and trimmed\n"
        f"# here by the true count the bridge also returns -- see\n"
        f"# try_build_bridge_for_target's own docstring). Same name, same call\n"
        f"# signature as the original Python function; drop-in replacement at\n"
        f"# call sites.\n"
        f"import {ext_name}\n\n\n"
        f"def {func_name}({args_sig}):\n"
        f"    {unpack} = {ext_name}.{mod_attr}.{bridge_attr}({call_args})\n"
        f"    return {trims}\n"
    )


def build_run_both_source(src: str, targets: list[tuple[str, str]], py_path: "Path | None" = None) -> str:
    """Return the original script's own source with EACH named top-level
    function's own `def` replaced by an import of its own Fortran-backed
    wrapper (same name) -- `targets` is a list of (func_name,
    wrapper_stem) pairs: a single-element list for the ordinary one-
    target case, or several for --all (every function in the script
    successfully bridged) -- so everything else (any code that isn't one
    of these defs) keeps running as ordinary Python, and only the named
    call site(s) are rerouted to compiled Fortran.

    This is what --run-both/--time-both diff against the original: the
    WHOLE script's real, natural output, in situ -- a stronger check than
    --verify's isolated call on manually supplied arguments.
    """
    tree = ast.parse(src)
    remaining = dict(targets)
    new_body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in remaining:
            wrapper_stem = remaining.pop(node.name)
            replacement = ast.ImportFrom(
                module=wrapper_stem, names=[ast.alias(name=node.name, asname=None)], level=0
            )
            new_body.append(ast.copy_location(replacement, node))
            continue
        if isinstance(node, ast.ImportFrom) and not getattr(node, "level", 0) and node.module:
            # A target may instead reach the main script via `from
            # sibling_module import name` rather than its own top-level
            # `def` -- xp2f.py's own inline_local_from_imports resolves
            # that at transpile time (see find_target_def's identical
            # fallback), so there is no FunctionDef node here to replace,
            # only this import. Reroute just the matching alias(es) to
            # the compiled wrapper (keyed on the TRUE name, matching a
            # `def`'s own node.name above -- not any local `as` alias),
            # leaving any other names in the same import statement alone.
            kept_aliases = []
            replaced = []
            for al in node.names:
                if al.name in remaining:
                    wrapper_stem = remaining.pop(al.name)
                    replaced.append((ast.alias(name=al.name, asname=al.asname), wrapper_stem))
                else:
                    kept_aliases.append(al)
            if replaced:
                for al, wrapper_stem in replaced:
                    new_body.append(ast.copy_location(
                        ast.ImportFrom(module=wrapper_stem, names=[al], level=0), node,
                    ))
                if kept_aliases:
                    new_body.append(ast.copy_location(
                        ast.ImportFrom(module=node.module, names=kept_aliases, level=node.level), node,
                    ))
                continue
        if isinstance(node, ast.Import) and py_path is not None:
            # A target may instead be reached only via attribute access
            # on a plain `import sibling_module` (`sibling_module.name(...)`,
            # see find_target_def's identical case) -- there's no bare
            # name anywhere to reroute the way the ImportFrom case above
            # does, so instead keep this import exactly as it is (other
            # attributes of the same module may still be used unmodified
            # elsewhere) and, right after it, rebind just the matching
            # attribute(s) on the already-imported module object to the
            # compiled wrapper's own same-named function -- every later
            # `sibling_module.name(...)` call site then transparently
            # picks up the Fortran-backed version with no call-site
            # rewriting needed at all.
            extra = []
            for al in node.names:
                mod_path = xp2f.resolve_sibling_module_path(al.name, py_path)
                if mod_path is None:
                    continue
                try:
                    mod_tree = ast.parse(mod_path.read_text(encoding="utf-8-sig"))
                except OSError:
                    continue
                local_alias = al.asname or al.name.split(".", 1)[0]
                for mod_node in mod_tree.body:
                    if isinstance(mod_node, ast.FunctionDef) and mod_node.name in remaining:
                        wrapper_stem = remaining.pop(mod_node.name)
                        extra.append(ast.Import(names=[ast.alias(name=wrapper_stem, asname=None)]))
                        extra.append(ast.Assign(
                            targets=[ast.Attribute(
                                value=ast.Name(id=local_alias, ctx=ast.Load()),
                                attr=mod_node.name, ctx=ast.Store(),
                            )],
                            value=ast.Attribute(
                                value=ast.Name(id=wrapper_stem, ctx=ast.Load()),
                                attr=mod_node.name, ctx=ast.Load(),
                            ),
                        ))
            new_body.append(node)
            new_body.extend(ast.copy_location(e, node) for e in extra)
            continue
        new_body.append(node)
    tree.body = new_body
    if remaining:
        raise UnsupportedFunction(
            f"no top-level def(s) found in the source script: {', '.join(sorted(remaining))}"
        )
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _resolve_fortran_target_name(func_name: str, py_tree: ast.Module, py_path: Path, procedures: dict) -> str:
    """Map the CLI/display target name to the identifier it was ACTUALLY
    translated to in the Fortran module -- these differ only for a target
    reached via a plain `import sibling_module` (attribute access,
    `sibling_module.name(...)`): xp2f.py's own inline_local_from_imports
    renames such a function to `f"{prefix}_{name}"` (see
    xp2f.safe_import_prefix) to avoid collisions between two sibling
    modules that happen to define the same name, so `func_name` itself is
    never a key in `procedures` for that case -- everything downstream
    that looks the target up IN THE FORTRAN TEXT (collect_closure,
    rewrite_target_for_f2py, try_build_bridge_for_target, remove_from_
    public, ...) needs this renamed identifier, not the CLI name (find_
    target_def's own identically-shaped fallback resolves the *Python*
    side of this same rename, for arg_names -- kept separate rather than
    merged into one function since one returns an ast.FunctionDef and
    this one returns a plain str, and each is only ever needed by
    different callers). Falls back to `func_name` unchanged if it's
    already a direct match (the overwhelmingly common case: same-file, or
    a `from sibling_module import name` target, whose name inlining
    always preserves) or if no renamed candidate matches either -- in
    which case the existing "not found" error downstream fires exactly
    as it always has.
    """
    if func_name.lower() in procedures:
        return func_name
    for node in py_tree.body:
        if not isinstance(node, ast.Import):
            continue
        for al in node.names:
            mod_path = xp2f.resolve_sibling_module_path(al.name, py_path)
            if mod_path is None:
                continue
            try:
                mod_tree = ast.parse(mod_path.read_text(encoding="utf-8-sig"))
            except OSError:
                continue
            if not any(
                isinstance(mod_node, ast.FunctionDef) and mod_node.name == func_name
                for mod_node in mod_tree.body
            ):
                continue
            local_alias = al.asname or al.name.split(".", 1)[0]
            candidate = f"{xp2f.safe_import_prefix(local_alias)}_{func_name}"
            if candidate.lower() in procedures:
                return candidate
    return func_name


@dataclass
class TargetBridgeResult:
    """Successful outcome of bridging ONE target function -- everything
    the caller (main()'s classic single-target path, or --all's loop)
    needs afterward for --verify/--run-both/--time-both."""

    func_name: str
    wrapper_path: Path
    arg_names: list[str]


def _bridge_one_target(
    func_name: str,
    py_tree: ast.Module,
    py_path: Path,
    out_dir: Path,
    mod_name: str,
    header: list[str],
    lines: list[str],
    procedures: dict,
    compiler_flags: list[str],
    timings: dict,
    backend: str = "f2py",
) -> "TargetBridgeResult | None":
    """Extract, rewrite, and f2py-build ONE target function out of an
    ALREADY-transpiled module -- `mod_name`/`header`/`lines`/`procedures`
    (from parse_module) are shared, read-only inputs, never mutated
    here, so the SAME already-transpiled module can be reused across
    many calls (--all's own loop) without re-running xp2f.py's own
    whole-program translation once per function.

    Prints the same Extract:/F2PY Build:/Wrapper: progress lines this
    tool has always printed, whether called once (main()'s classic
    path) or many times (--all) -- returns a TargetBridgeResult on
    success, or None on any failure (already reported via a printed FAIL
    line, matching this project's own established per-stage reporting
    style; the caller decides what a None result means for its own exit
    code). `timings["compile"]` accumulates the f2py build time across
    calls (so --all's own combined timing summary reports the TOTAL
    build time across every function, not just the last one).
    """
    try:
        target_def = find_target_def(py_tree, func_name, py_path)
    except UnsupportedFunction as e:
        print(f"Target: FAIL ({e})")
        return None
    arg_names = [a.arg for a in target_def.args.args]
    # The identifier actually used for `func_name` in the FORTRAN text --
    # differs from func_name only for a target reached via `import
    # sibling_module` (attribute access), which inline_local_from_imports
    # renames on the way in (see _resolve_fortran_target_name's own
    # docstring). Used for every lookup/rewrite that operates on the
    # Fortran source below; func_name itself stays the CLI/display name,
    # used for the outer wrapper's own exposed Python def name, generated
    # filenames, and TargetBridgeResult (everything callers -- --verify,
    # build_run_both_source -- match back against the ORIGINAL name the
    # user's own code calls it by).
    fortran_name = _resolve_fortran_target_name(func_name, py_tree, py_path, procedures)

    had_array = False
    bridge_name = None
    bridge_text = None
    n_bridge_outputs = 0
    needed = None
    try:
        needed = collect_closure(fortran_name, procedures, lines)
        target_key = fortran_name.lower()
        t_start, t_end = procedures[target_key]
        # Captured BEFORE any rewrite touches lines[t_start] -- the
        # ctypes backend needs to know whether the ORIGINAL target was a
        # function (restoring genuine function-call semantics at its own
        # bind(c) shim boundary is the whole point of not just reusing
        # rewrite_target_for_f2py's own scalar-function-to-subroutine
        # conversion as the final word -- see build_ctypes_shim).
        orig_sig_m = SIG_RE.match(_strip_comment(lines[t_start]))

        # Try the "provably bounded, data-dependent-length accumulator"
        # bridge FIRST (a distinct codegen shape from rewrite_target_
        # for_f2py's own "size is a simple function of the arguments"
        # case, cheaply told apart by trying this one first) -- only
        # falls through to rewrite_target_for_f2py when the target
        # doesn't match that idiom at all.
        bridge_spec = try_build_bridge_for_target(lines, t_start, t_end, fortran_name)
        if bridge_spec is not None:
            had_array = True
            bridge_name = f"{fortran_name}_bridge"
            bridge_text, _bridge_counts = build_bridge_procedure(
                lines, t_start, t_end, fortran_name, bridge_spec, bridge_name
            )
            n_bridge_outputs = len(bridge_spec["outputs"])
            # Kept semantically UNCHANGED -- but f2py's own Fortran
            # cracker still has to parse this file (it can't be split
            # into a separately-compiled, un-cracked object: confirmed
            # empirically that a bare .o file isn't picked up as a link
            # input by this meson backend at all), and its `block ...
            # end block` scoping (xp2f.py's own accumulator-loop idiom)
            # corrupts f2py's parsing of the LATER bridge subroutine in
            # the same file -- see unwrap_block_constructs's own
            # docstring. Rewritten away here, in THIS embedded copy only.
            all_names = {tok.lower() for ln in lines for tok in re.findall(r"[A-Za-z_]\w*", ln)}
            target_lines = unwrap_block_constructs(list(lines[t_start : t_end + 1]), all_names)
        else:
            target_lines, had_array = rewrite_target_for_f2py(lines, t_start, t_end, fortran_name, procedures)

        omit_args = set()
        if bridge_name is None:
            check_f2py_compatible(target_lines, 0, len(target_lines) - 1, target_key)
            # A scalar dummy the Fortran body never actually references
            # (see _unused_scalar_target_args's own docstring, e.g.
            # examples/xmix.py's own `rng`) is marked `optional` and left
            # OUT of the wrapper's own call entirely -- there's often no
            # valid conversion from what Python actually passes (e.g. a
            # numpy Generator object) to whatever placeholder scalar type
            # it was given, and since it's unused, nothing is lost by not
            # passing it at all.
            omit_args = _unused_scalar_target_args(target_lines, arg_names)
            if omit_args:
                target_lines = _mark_args_optional(target_lines, omit_args)
        # else: the target is kept completely UNCHANGED (still
        # allocatable) -- it's never itself exposed to f2py, only called
        # internally by the bridge, so its own shape doesn't need to pass
        # this check.
        #
        # A DEPENDENCY (any OTHER name in `needed`) is never itself
        # checked here at all -- see the "kept private" comment further
        # down, right where every dependency is stripped from the
        # trimmed module's own `public ::` list. f2py's own Fortran
        # cracker only ever attempts to wrap a module's PUBLIC surface;
        # once a dependency is private, its own array-shaped or derived-
        # type signature is invisible to f2py entirely, confirmed
        # empirically to build and run correctly either way (an ordinary
        # internal Fortran-to-Fortran call needs no f2py-facing rewrite
        # at all -- assumed-shape array arguments, allocatable results,
        # and derived types are all completely normal Fortran there).

        # A module-level global referenced by the target or any of its
        # dependencies would otherwise be left merely DECLARED, never
        # ASSIGNED -- its own initializer lives in the script's top-level
        # `program` block, which a standalone f2py bridge never runs.
        # See hoist_global_initializers's own docstring. Kept as
        # SEPARATE per-procedure line-lists (not flattened into one
        # blob) so a same-named local/dummy in one of them can be told
        # apart from a genuine reference to the module-level global.
        needed_bodies = [target_lines] + [
            lines[procedures[nm][0] : procedures[nm][1] + 1] for nm in needed if nm != target_key
        ]
        header = hoist_global_initializers(header, lines, needed_bodies)

        # ctypes backend only: a callback argument's own interface must
        # be rewritten for C interoperability BEFORE build_trimmed_module
        # runs, not after -- that's what actually writes each
        # procedure's own body into the trimmed module, so the rewrite
        # has to already be baked into what gets passed as override_lines
        # (see build_ctypes_shim's own docstring for the bug this avoids).
        # Every DEPENDENCY that ALSO declares a copy of the same callback
        # (e.g. examples/xcallback_passthrough_order_repro.py's own
        # `driver`, which forwards its own callback dummy to `evaluate`)
        # needs the identical treatment for the whole call chain to stay
        # interoperable -- see _rewrite_callback_interface_for_ctypes's
        # own docstring.
        override_lines = {target_key: target_lines}
        cb_shim_info = (None, None, None, None, None)
        if backend == "ctypes":
            cb_arg_name, cb_iface_name = _find_callback_arg(target_lines)
            if cb_arg_name is not None:
                target_lines, cb_result_c_type, cb_arg_specs_inner, cb_iface_lines = (
                    _rewrite_callback_interface_for_ctypes(target_lines, cb_arg_name, cb_iface_name)
                )
                override_lines[target_key] = target_lines
                cb_shim_info = (cb_arg_name, cb_iface_name, cb_result_c_type, cb_arg_specs_inner, cb_iface_lines)
                for nm in needed:
                    if nm == target_key:
                        continue
                    dep_start, dep_end = procedures[nm]
                    dep_lines = list(lines[dep_start : dep_end + 1])
                    dep_cb_arg_name, dep_cb_iface_name = _find_callback_arg(dep_lines)
                    if dep_cb_arg_name is not None:
                        dep_lines, _rct, _cas, _cil = _rewrite_callback_interface_for_ctypes(
                            dep_lines, dep_cb_arg_name, dep_cb_iface_name
                        )
                        override_lines[nm] = dep_lines
    except UnsupportedFunction as e:
        print(f"Extract: FAIL ({e})")
        return None
    print(f"Extract: PASS ({func_name} + {len(needed) - 1} dependency function(s): "
          f"{', '.join(sorted(needed - {fortran_name.lower()})) or '(none)'})")
    if bridge_name is not None:
        print(f"Extract: {func_name!r} has (a) data-dependent-length array result(s) -- "
              f"bridged via a generated {bridge_name!r} subroutine (over-allocated to a "
              f"provable bound, trimmed by its own true count in the wrapper)")
    elif had_array:
        print(f"Extract: {func_name!r} has a rank-1 array argument/result -- "
              f"rewritten to an f2py-bridgeable explicit-shape form")

    trimmed_text = build_trimmed_module(
        mod_name, header, lines, procedures, needed, override_lines=override_lines
    )
    # Every DEPENDENCY (any OTHER name in `needed`) is stripped from the
    # trimmed module's own `public ::` list -- kept PRIVATE, same as any
    # truly-unused procedure already was. Only the target itself (or the
    # bridge, below) is ever actually called from Python; a dependency
    # is only ever called internally, by the target's own Fortran code
    # (or another dependency's), which needs no f2py-facing rewrite at
    # all. Confirmed empirically: f2py's own Fortran cracker only
    # attempts to wrap a module's PUBLIC surface, so a private
    # dependency's own array-shaped or derived-type signature -- the
    # `array_in_dependency`/`derived_type_unsupported` blockers this
    # fixes -- never gets anywhere near it, and an ordinary internal
    # Fortran call to it (assumed-shape array argument, allocatable
    # result, derived type, all completely normal there) builds and
    # runs correctly either way.
    for nm in needed:
        if nm != target_key:
            trimmed_text = remove_from_public(trimmed_text, nm)
    if bridge_name is not None:
        # f2py crawls a module's ENTIRE public interface and tries to
        # wrap every name in it -- including the ORIGINAL target, still
        # kept exactly as-is with its own allocatable result, if it's
        # still public. Confirmed empirically: left public, f2py tries
        # to wrap it too and hits the very allocatable-result bug the
        # bridge exists to route around ("appenddecl: 'dimension' not
        # implemented"). Only the bridge itself should be public.
        trimmed_text = remove_from_public(trimmed_text, fortran_name)
        trimmed_text = append_procedure_to_module(trimmed_text, bridge_text, bridge_name)
    # A `python_mod` helper (e.g. mean_1d) the trimmed module still needs
    # is INLINED directly rather than compiled/linked as a separate
    # object -- confirmed empirically that both alternatives fail on this
    # toolchain (see inline_python_mod_helpers's own docstring).
    trimmed_text, unresolved_helpers = inline_python_mod_helpers(trimmed_text)
    # xp2f.py emits a `use dataframe_..._mod, only: ...` header line
    # whenever the SCRIPT AS A WHOLE uses a pandas DataFrame anywhere --
    # not just within the target's own dependency closure -- so it can
    # be left orphaned (needing a companion module never compiled/linked
    # into this standalone f2py build) once trimmed down to a target
    # that doesn't touch pandas at all. Dropped when nothing kept --
    # including anything just inlined above -- actually still needs it
    # (see strip_unused_dataframe_use's own docstring).
    trimmed_text = strip_unused_dataframe_use(trimmed_text)
    if unresolved_helpers:
        print(f"Extract: FAIL (needs helper(s) {', '.join(unresolved_helpers)!r} this "
              f"tool can't yet bridge -- only simple python_mod helpers inlinable "
              f"directly into the trimmed module are supported, not a helper module "
              f"requiring its own separate compile/link, e.g. LAPACK-backed routines "
              f"or a pandas DataFrame companion type)")
        return None
    trimmed_path = out_dir / f"{func_name}_f.f90"

    if backend == "ctypes":
        # Phase 1 of the ctypes/bind(c) backend -- see build_ctypes_shim's
        # own docstring. Not yet supported: the data-dependent-length
        # bridge path (bridge_name is not None) or anything array-shaped/
        # character (build_ctypes_shim itself rejects those).
        if bridge_name is not None:
            print("Extract: FAIL (ctypes backend: data-dependent-length array-result "
                  "bridge not yet supported)")
            return None
        # Whether the ORIGINAL target was a function at all -- regardless
        # of whether any ARGUMENT is array-shaped (that's independent:
        # e.g. examples/xbfgs.py's own `objective(x)` takes an array but
        # still returns a plain scalar, and a bind(c) function taking an
        # array-pointer argument and returning a scalar is completely
        # ordinary C-ABI shape -- build_ctypes_shim itself decides,
        # per-name, whether the specific appended "result" turns into a
        # genuine function result or an array out-param).
        orig_is_function = orig_sig_m is not None and orig_sig_m.group("kind").lower() == "function"
        cb_arg_name, cb_iface_name, cb_result_c_type, cb_arg_specs_inner, cb_iface_lines = cb_shim_info
        try:
            shim_text, c_arg_specs, is_shim_function, shim_symbol, result_c_type = build_ctypes_shim(
                target_lines, arg_names, omit_args, orig_is_function, fortran_name,
                cb_arg_name, cb_iface_name, cb_result_c_type, cb_arg_specs_inner, cb_iface_lines,
            )
        except UnsupportedFunction as e:
            print(f"Extract: FAIL ({e})")
            return None
        # append_procedure_to_module also adds the shim to the module's
        # own `public ::` list -- harmless (a plain gfortran -shared
        # compile never consults it; a bind(c) symbol is always exported
        # by its own external name regardless), reused here just to avoid
        # a second, near-identical "insert before end module" helper.
        trimmed_text = append_procedure_to_module(trimmed_text, shim_text, shim_symbol)
        trimmed_path.write_text(trimmed_text, encoding="utf-8")
        t0 = time.perf_counter()
        dll_path = build_ctypes_extension(
            trimmed_path, out_dir, compiler_flags, needs_lapack=LAPACK_ROUTINE_RE.search(trimmed_text) is not None
        )
        timings["compile"] = timings.get("compile", 0.0) + (time.perf_counter() - t0)
        if dll_path is None:
            return None
        print("Ctypes Build: PASS")
        wrapper_path = out_dir / f"{func_name}_f.py"
        wrapper_path.write_text(
            generate_ctypes_wrapper(
                dll_path, func_name, shim_symbol, c_arg_specs, is_shim_function, result_c_type,
                arg_names, omit_args,
            ),
            encoding="utf-8",
        )
        print(f"Wrapper: {wrapper_path}")
        return TargetBridgeResult(func_name=func_name, wrapper_path=wrapper_path, arg_names=arg_names)

    trimmed_path.write_text(trimmed_text, encoding="utf-8")

    ext_name = f"{func_name}_fortran_ext"
    f2py_cmd = [sys.executable, "-m", "numpy.f2py", "-c", str(trimmed_path), "-m", ext_name]
    if compiler_flags:
        f2py_cmd.append(f"--f90flags={' '.join(compiler_flags)}")
    # Both of these are applied UNCONDITIONALLY -- not just when
    # had_array -- since both are harmless when not actually needed (an
    # unused f2cmap entry / an unused extra link library) and confirmed
    # empirically to ALSO be needed for a purely scalar target: f2py
    # generates its own separate scalar-function wrapper file for any
    # bridged FUNCTION (never a subroutine) that references this
    # project's `dp` kind parameter without importing it, regardless of
    # whether any array is involved at all (xbrentq.py's own
    # `f(x) = x ** 2 - 2.0` triggers it with no array in sight).
    f2cmap_path = out_dir / f"{func_name}_f2py_f2cmap"
    write_f2cmap_file(f2cmap_path)
    # NOTE: f2py's own arg parser rejects `--f2cmap=<path>` ("Unknown
    # option") -- unlike --f90flags=, this one needs a separate argv
    # entry.
    f2py_cmd.extend(["--f2cmap", str(f2cmap_path)])
    # Confirmed empirically: certain generated Fortran (ieee_arithmetic
    # usage, seen for a NaN-safe comparison; likely other constructs
    # too) needs gfortran's own internal win32-threads GTHR stubs
    # (__gthr_win32_self and friends) at link time -- provided by
    # libgcc.a, which gfortran's own native linker invocation pulls in
    # automatically but f2py's meson/clang/lld pipeline does not.
    gcc_lib = Path(
        subprocess.run(["gfortran", "-print-libgcc-file-name"], capture_output=True, text=True).stdout.strip()
    )
    if gcc_lib.exists():
        f2py_cmd.extend([f"-L{gcc_lib.parent}", "-lgcc"])
    # A trimmed module calling a LAPACK routine (e.g. `dpotrf`, reached
    # through an inlined python_mod helper like `random_mvn_samples` --
    # xp2f.py's own translation of `rng.multivariate_normal(...)`) needs
    # this project's own vendored lapack_d linked in too, the same way
    # xp2f.py's own whole-program `--compile` path already does -- see
    # _ensure_lapack_archive's own docstring for why it's an archived
    # `.o`, not lapack_d.f90 itself, that gets passed here.
    if LAPACK_ROUTINE_RE.search(trimmed_text):
        lapack_lib = _ensure_lapack_archive()
        if lapack_lib is not None:
            lapack_dir, lapack_stem = lapack_lib
            f2py_cmd.extend([f"-L{lapack_dir}", f"-l{lapack_stem}"])
    t0 = time.perf_counter()
    proc = subprocess.run(
        f2py_cmd,
        cwd=out_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    timings["compile"] = timings.get("compile", 0.0) + (time.perf_counter() - t0)
    if proc.returncode != 0:
        print("F2PY Build: FAIL")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        return None
    print("F2PY Build: PASS")

    wrapper_path = out_dir / f"{func_name}_f.py"
    if bridge_name is not None:
        wrapper_path.write_text(
            generate_bridge_wrapper(mod_name, ext_name, func_name, arg_names, bridge_name, n_bridge_outputs),
            encoding="utf-8",
        )
    else:
        # A target that ended up with NO array argument/result at all --
        # `had_array` never went True, and it wasn't already a subroutine
        # to begin with (`is_function` covers the "originally a scalar
        # function" case; a scalar-only SUBROUTINE input is exceedingly
        # rare but the same risk applies either way) -- is exactly the
        # case where an external caller (unlike this project's own
        # generated Fortran, which only ever calls it scalar-wise) might
        # pass an array anyway, e.g. scipy's `curve_fit` calling its own
        # `model` callback with the WHOLE xdata array at once. See
        # generate_wrapper's own `vectorize_scalars` docstring.
        wrapper_path.write_text(
            generate_wrapper(
                mod_name, ext_name, func_name, arg_names, omit_args, vectorize_scalars=not had_array,
                fortran_func_name=fortran_name,
            ),
            encoding="utf-8",
        )
    print(f"Wrapper: {wrapper_path}")
    return TargetBridgeResult(func_name=func_name, wrapper_path=wrapper_path, arg_names=arg_names)


_NUM_CORE_RE_TEXT = r"(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][+-]?\d+)?|(?:inf|nan)"
_SIGNED_NUM_RE_TEXT = rf"[+-]?(?:{_NUM_CORE_RE_TEXT})"
_KV_PREFIX_RE = re.compile(r"^([A-Za-z_][\w.]*=)(.*)$")
_COMPLEX_PAREN_RE = re.compile(
    rf"\(\s*({_SIGNED_NUM_RE_TEXT})\s*,\s*({_SIGNED_NUM_RE_TEXT})\s*\)", re.IGNORECASE
)
_COMPLEX_SUFFIX_RE = re.compile(
    rf"\(?\s*({_SIGNED_NUM_RE_TEXT})\s*([+-])\s*({_NUM_CORE_RE_TEXT})j\s*\)?", re.IGNORECASE
)
_IMAG_ONLY_RE = re.compile(rf"({_SIGNED_NUM_RE_TEXT})j", re.IGNORECASE)


def _parse_tok_num(tok):
    """Parse `tok` as a real or complex number (Fortran `D`/`d` exponent
    marker accepted alongside `E`/`e`; a bracketed `(re, im)` pair or a
    trailing `Xj` imaginary suffix both accepted) -- or None if it isn't
    one at all. A scaled-down copy of xp2f.py's own --run-diff/--numeric-
    diff token parser (that one lives as a closure nested inside its own
    main(), not reusable as-is) -- kept independent rather than sharing
    code across the two tools' very different CLI/argument surfaces.
    """
    t = tok.strip().strip("[],").strip()
    if not t:
        return None
    m = _COMPLEX_PAREN_RE.fullmatch(t)
    if m:
        return complex(
            float(m.group(1).replace("d", "e").replace("D", "E")),
            float(m.group(2).replace("d", "e").replace("D", "E")),
        )
    m = _COMPLEX_SUFFIX_RE.fullmatch(t)
    if m:
        re_part = float(m.group(1).replace("d", "e").replace("D", "E"))
        im_part = float(m.group(3).replace("d", "e").replace("D", "E"))
        if m.group(2) == "-":
            im_part = -im_part
        return complex(re_part, im_part)
    m = _IMAG_ONLY_RE.fullmatch(t)
    if m:
        return complex(0.0, float(m.group(1).replace("d", "e").replace("D", "E")))
    try:
        return complex(float(t.replace("d", "e").replace("D", "E")), 0.0)
    except ValueError:
        return None


def _tok_close(a: str, b: str, tol: float) -> bool:
    """True if tokens `a`/`b` (already whitespace/comma-split) are either
    textually identical, or both numeric and within relative tolerance
    `tol` of each other -- lets a pure precision/formatting difference
    (Python's compact `repr` vs. Fortran's full-precision list-directed
    output, e.g. `12.0` vs `12.000000000000000`) match without masking a
    GENUINE value difference.
    """
    if a == b:
        return True
    # A "label=value" token (e.g. "omega=0.1" vs "omega=0.10000000001")
    # stays fused as one token by the caller's own whitespace/comma
    # split -- peel off a matching "label=" prefix (identical on both
    # sides only; a differing/missing label is a real mismatch) so just
    # the trailing value gets the numeric-tolerant comparison below.
    a_m = _KV_PREFIX_RE.match(a)
    b_m = _KV_PREFIX_RE.match(b)
    a_prefix = a_m.group(1) if a_m else ""
    b_prefix = b_m.group(1) if b_m else ""
    if a_prefix or b_prefix:
        if a_prefix != b_prefix:
            return False
        a, b = a_m.group(2), b_m.group(2)
        if a == b:
            return True
    av, bv = _parse_tok_num(a), _parse_tok_num(b)
    if av is None or bv is None:
        return False
    for ax, bx in ((av.real, bv.real), (av.imag, bv.imag)):
        if math.isnan(ax) or math.isnan(bx):
            if math.isnan(ax) and math.isnan(bx):
                continue
            return False
        if math.isinf(ax) or math.isinf(bx):
            if ax == bx:
                continue
            return False
        if abs(ax - bx) > tol * max(1.0, abs(ax), abs(bx)):
            return False
    return True


def _lines_close(a_lines: list[str], b_lines: list[str], tol: float) -> bool:
    """True if `a_lines`/`b_lines` are equal as whitespace/comma-split
    token streams under `_tok_close`'s own numeric-tolerant comparison --
    line boundaries themselves don't matter (only token order), so a
    trivial line-wrapping difference can't cause a spurious mismatch
    either. Requires the same TOTAL token count -- a genuinely different
    number of values printed is always a real difference, never absorbed
    here.
    """

    def _tokenize(lines):
        toks = []
        for ln in lines:
            for raw in ln.replace("[", " ").replace("]", " ").replace(",", " ").split():
                toks.append(raw)
        return toks

    a_tok, b_tok = _tokenize(a_lines), _tokenize(b_lines)
    if len(a_tok) != len(b_tok):
        return False
    return all(_tok_close(at, bt, tol) for at, bt in zip(a_tok, b_tok))


# Relative tolerance for the numeric-tolerant --run-both/--time-both
# fallback comparison -- tight enough to only absorb a pure precision/
# formatting difference (e.g. Python's `12.0` vs Fortran's
# `12.000000000000000`), never a genuine value divergence (an unconverged
# optimizer result, a diverged RNG stream, ...). Matches xp2f.py's own
# --run-diff default display tolerance (1.0e-12).
RUN_BOTH_NUMERIC_TOL = 1.0e-12


def _run_both_and_report(
    py_path: Path, run_both_src: str, out_dir: Path, run_both_filename: str, time_both: bool, timings: dict
) -> bool:
    """Write `run_both_src` to `out_dir/run_both_filename`, run the
    ORIGINAL script and the patched one (same environment, PYTHONPATH
    extended so the patched script's own wrapper imports resolve), and
    diff normalized stdout -- shared by main()'s classic single-target
    --run-both/--time-both and --all's own combined version (every
    successfully-bridged function's def replaced at once); the two
    differ only in how `run_both_src` itself was built.

    Returns True if both runs succeeded and matched, False otherwise
    (already reported via printed Run (...):/Run-both: lines).
    """
    run_both_path = out_dir / run_both_filename
    run_both_path.write_text(run_both_src, encoding="utf-8")

    # The patched script needs both the wrapper module(s) and their
    # compiled f2py extension(s) importable; all were just written into
    # out_dir.
    run_env = os.environ.copy()
    existing_pp = run_env.get("PYTHONPATH", "")
    run_env["PYTHONPATH"] = str(out_dir) + (os.pathsep + existing_pp if existing_pp else "")

    t0 = time.perf_counter() if time_both else None
    py_rc, py_out, py_err, _ = xp2f.run_capture([sys.executable, str(py_path)], env=run_env)
    if time_both:
        timings["python_run"] = time.perf_counter() - t0
    print(f"Run (python): {'PASS' if py_rc == 0 else f'FAIL (exit {py_rc})'}")
    if py_out.strip():
        print(py_out.rstrip())
    if py_rc != 0:
        if py_err.strip():
            print(py_err.rstrip())
        return False

    t0 = time.perf_counter() if time_both else None
    fb_rc, fb_out, fb_err, _ = xp2f.run_capture([sys.executable, str(run_both_path)], env=run_env)
    if time_both:
        timings["fortran_run"] = time.perf_counter() - t0
    print(f"Run (fortran-backed): {'PASS' if fb_rc == 0 else f'FAIL (exit {fb_rc})'}")
    if fb_out.strip():
        print(fb_out.rstrip())
    if fb_rc != 0:
        if fb_err.strip():
            print(fb_err.rstrip())
        return False

    def _norm(text: str) -> list[str]:
        return text.replace("\r\n", "\n").rstrip("\n").splitlines()

    py_lines = _norm(py_out)
    fb_lines = _norm(fb_out)
    run_both_match = py_lines == fb_lines
    numeric_tolerant = False
    if not run_both_match:
        # A byte-for-byte mismatch is often just a PRECISION/FORMATTING
        # difference, not a real one -- Python's own compact float repr
        # vs. Fortran's full-precision list-directed `print *` output
        # (confirmed via examples/xnested.py's own `nested_polynomial`:
        # "12.0" vs "12.000000000000000", the exact same value). Falls
        # back to a numeric-tolerant comparison (_lines_close) before
        # reporting a genuine DIFF -- tight tolerance (see
        # RUN_BOTH_NUMERIC_TOL), so an actually-wrong result (e.g. an
        # unconverged optimizer returning its initial guess instead of a
        # fitted value) still correctly reports DIFF.
        numeric_tolerant = _lines_close(py_lines, fb_lines, RUN_BOTH_NUMERIC_TOL)
    if run_both_match:
        print("Run-both: MATCH")
    elif numeric_tolerant:
        print("Run-both: MATCH (numeric-tolerant -- byte-for-byte text differs, but every "
              f"value agrees within relative tolerance {RUN_BOTH_NUMERIC_TOL:g})")
    else:
        print("Run-both: DIFF")
        for dl in difflib.unified_diff(py_lines, fb_lines, fromfile="python", tofile="fortran-backed", lineterm=""):
            print(dl)
    return run_both_match or numeric_tolerant


def _print_timing_summary(timings: dict) -> None:
    """Same stage set and layout as xp2f.py's own timing summary
    ("python run" / "transpile" / "compile" / "fortran run" / "total")
    so the two tools' reported speedups read side by side -- shared by
    main()'s classic single-target --time-both and --all's own combined
    version, where "compile" is the SUM of every function's own f2py
    build time (accumulated by _bridge_one_target across each call).
    """
    timings["total"] = (
        timings.get("transpile", 0.0) + timings.get("compile", 0.0) + timings.get("fortran_run", 0.0)
    )
    base = timings.get("python_run", 0.0)

    def _ratio(v: float) -> str:
        return f"{(v / base):.6f}" if base > 0.0 else "n/a"

    rows = []
    if "python_run" in timings:
        rows.append(("python run", timings["python_run"]))
    rows.append(("transpile", timings.get("transpile", 0.0)))
    rows.append(("compile", timings.get("compile", 0.0)))
    if "fortran_run" in timings:
        rows.append(("fortran run", timings["fortran_run"]))
    rows.append(("total", timings["total"]))

    print("")
    print("Timing summary (seconds):")
    stage_w = max(len("stage"), max(len(name) for name, _ in rows))
    sec_vals = [f"{val:.6f}" for _name, val in rows]
    sec_w = max(len("seconds"), max(len(s) for s in sec_vals))
    show_ratio = "python_run" in timings
    if show_ratio:
        ratio_hdr = "ratio(vs python run)"
        ratio_vals = [_ratio(val) for _name, val in rows]
        ratio_w = max(len(ratio_hdr), max(len(r) for r in ratio_vals))
        print(f"  {'stage':<{stage_w}}  {'seconds':>{sec_w}}    {ratio_hdr:>{ratio_w}}")
        for name, val in rows:
            rtxt = _ratio(val)
            print(f"  {name:<{stage_w}}  {val:>{sec_w}.6f}    {rtxt:>{ratio_w}}")
    else:
        print(f"  {'stage':<{stage_w}}  {'seconds':>{sec_w}}")
        for name, val in rows:
            print(f"  {name:<{stage_w}}  {val:>{sec_w}.6f}")


def _run_all_targets(
    args, py_path: Path, py_tree: ast.Module, src: str, out_dir: Path, mod_name: str, header: list[str],
    lines: list[str], procedures: dict, compiler_flags: list[str], timings: dict,
) -> int:
    """--all: bridge EVERY top-level function in the script (except one
    named `main`, typically just an entry-point wrapper rather than a
    good bridge target itself) as an INDEPENDENT target, sharing the one
    already-transpiled module across all of them. Reports pass/fail per
    function and continues past a failure rather than aborting the
    whole run -- the point of --all is maximizing how many functions end
    up bridged, not requiring all-or-nothing.

    --except (args.except_funcs) additionally skips whatever function
    name(s) it lists -- e.g. a data-loading function with no good Fortran
    equivalent (pandas I/O, network calls, ...) that would otherwise just
    fail and clutter the summary, or one the user simply doesn't want
    translated. Checked against the script's own top-level function names
    up front (BEFORE excluding 'main') so a typo'd or nonexistent name is
    caught with a clear error instead of silently matching nothing.

    --run-both/--time-both are only attempted afterward if EVERY
    (non-excepted) function was successfully bridged -- patching them all
    in at once raises real per-function interaction questions (a bridged
    function calling one that's still plain Python, or vice versa) that
    only disappear cleanly when there's no plain-Python function left at
    all -- an intentionally excepted function stays plain Python forever,
    so it's fine for it to remain un-bridged; only an actual FAILURE among
    the rest still blocks --run-both/--time-both.
    """
    top_level_names = {node.name for node in py_tree.body if isinstance(node, ast.FunctionDef)}
    except_names = set(args.except_funcs or [])
    unknown = except_names - top_level_names
    if unknown:
        print(f"Target: FAIL (--except name(s) not found as a top-level function in the "
              f"script: {', '.join(sorted(unknown))})")
        return 1
    all_func_names = [
        node.name for node in py_tree.body
        if isinstance(node, ast.FunctionDef) and node.name != "main" and node.name not in except_names
    ]
    if not all_func_names:
        print("Target: FAIL (no top-level function found in the source script, other than "
              "'main' and any --except name(s), if present)")
        return 1

    results: dict[str, TargetBridgeResult | None] = {}
    for i, func_name in enumerate(all_func_names, start=1):
        print(f"\n[{i}/{len(all_func_names)}] {func_name}")
        results[func_name] = _bridge_one_target(
            func_name, py_tree, py_path, out_dir, mod_name, header, lines, procedures, compiler_flags, timings,
            backend=args.backend,
        )

    n_ok = sum(1 for r in results.values() if r is not None)
    print(f"\nAll-functions summary: {n_ok} of {len(all_func_names)} bridged")
    for func_name, r in results.items():
        print(f"  {'PASS' if r is not None else 'FAIL'}  {func_name}")

    if not (args.run_both or args.time_both):
        return 0 if n_ok > 0 else 1

    if n_ok != len(all_func_names):
        print(f"\nRun-both: SKIPPED (not all {len(all_func_names)} functions bridged: {n_ok} "
              f"succeeded -- --run-both/--time-both need EVERY function backed by Fortran to "
              f"patch the whole script at once)")
        return 1

    run_both_src = build_run_both_source(
        src, [(name, r.wrapper_path.stem) for name, r in results.items()], py_path
    )
    ok = _run_both_and_report(
        py_path, run_both_src, out_dir, f"{py_path.stem}_all_run_both.py", args.time_both, timings
    )
    if args.time_both:
        _print_timing_summary(timings)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_py", help="input python source containing the target function")
    ap.add_argument(
        "function_name",
        nargs="?",
        default=None,
        help="name of the top-level function to translate (default: the first function "
        "the script's own top-level code calls, skipping a call to 'main'); mutually "
        "exclusive with --all/--except",
    )
    ap.add_argument("--out-dir", help="directory for generated files (default: alongside input_py)")
    ap.add_argument(
        "--backend",
        choices=["f2py", "ctypes"],
        default="f2py",
        help="bridging backend (default: f2py). 'ctypes' compiles a bind(c) shim via a plain "
        "gfortran -shared build instead of f2py's own crackfortran/meson pipeline -- currently "
        "PHASE 1 ONLY: a purely scalar real/integer/logical target (no arrays, no strings, no "
        "callbacks yet), restoring genuine Fortran function-call semantics at the ctypes "
        "boundary even when the target's own body was converted to a subroutine internally.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="translate EVERY top-level function in the script (except one named 'main'), "
        "each independently, reporting pass/fail per function -- mutually exclusive with "
        "function_name/--verify. --run-both/--time-both are attempted afterward (patching "
        "every successfully-bridged function in at once) only if ALL of them bridged",
    )
    ap.add_argument(
        "--except",
        dest="except_funcs",
        nargs="+",
        metavar="FUNC",
        default=None,
        help="like --all, but also skip these top-level function name(s) -- e.g. a "
        "data-loading function with no good Fortran equivalent (pandas I/O, network "
        "calls, ...). Implies --all; mutually exclusive with function_name/--verify. "
        "'main' is always skipped regardless, whether or not it's named here too",
    )
    ap.add_argument(
        "--verify",
        action="store_true",
        help="also run the original Python function and the new wrapper on the same "
        "arguments (given via --verify-args, a Python literal tuple) and compare results",
    )
    ap.add_argument(
        "--verify-args",
        default="()",
        help="Python literal tuple of positional arguments to use with --verify (default: no args)",
    )
    ap.add_argument(
        "--run-both",
        action="store_true",
        help="run the original script as-is, and again with the target function backed by "
        "compiled Fortran, and diff normalized stdout",
    )
    ap.add_argument(
        "--time-both",
        action="store_true",
        help="like --run-both, and also report wall-clock timing for each run",
    )
    args = ap.parse_args(argv)

    # --except implies --all's own semantics (translate every top-level
    # function, minus some names) -- always paired together from here on,
    # so every other --all check/branch below also covers --except for free.
    if args.except_funcs:
        args.all = True
    if args.all and args.function_name:
        ap.error("function_name and --all/--except are mutually exclusive")
    if args.all and args.verify:
        ap.error("--verify and --all/--except are mutually exclusive (--verify needs one function's own arguments)")

    # Absolute -- several subprocesses below (the f2py build in
    # particular) run with cwd=out_dir, so a RELATIVE out_dir (or a path
    # built from one, like trimmed_path) would resolve against THAT
    # subprocess's own cwd instead of the one it meant when it was
    # computed, e.g. plain `xpfunc2f.py script.py func` (no --out-dir,
    # the default out_dir=py_path.parent) with a relative script.py path
    # confirmed to break this way: f2py reported "File acf_f.f90 does
    # not exist" because "examples\acf_f.f90" got re-resolved relative
    # to cwd="examples".
    py_path = Path(args.input_py).resolve()
    out_dir = (Path(args.out_dir) if args.out_dir else py_path.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = py_path.stem

    timings: dict = {}

    src = py_path.read_text(encoding="utf-8-sig")
    py_tree = ast.parse(src)

    # Reuse xp2f.py's own, unmodified whole-program translation wholesale
    # -- same type inference, same codegen, zero new risk to it -- then
    # extract just the target function's transitive dependency closure
    # out of the result. Done ONCE regardless of how many functions end
    # up bridged (--all's own loop reuses this same parsed module for
    # every one of them) -- re-running xp2f.py's own whole-program static
    # analysis once per function would be pure waste, since the
    # transpiled output doesn't depend on which function is targeted.
    full_f90_path = out_dir / f"{stem}_p.f90"
    t0 = time.perf_counter() if args.time_both else None
    try:
        xp2f.transpile_file(str(py_path), [], False, no_comment=True, out_path=str(full_f90_path))
    except (NotImplementedError, FileNotFoundError) as e:
        print(f"Transpile: FAIL ({e})")
        return 1
    if args.time_both:
        timings["transpile"] = time.perf_counter() - t0
    print(f"Transpile: PASS ({full_f90_path})")

    f90_text = full_f90_path.read_text(encoding="utf-8")
    try:
        mod_name, header, lines, procedures = parse_module(f90_text)
    except UnsupportedFunction as e:
        # Regression test for a real bug: parse_module used to run INSIDE
        # the per-target try/except (this project's own established
        # style for a clean "Extract: FAIL (...)" report), but hoisting
        # the transpile-once step out of the per-target logic (so --all
        # can share it across every function) moved this call to run
        # BEFORE any try/except existed at all, so a script whose own
        # transpiled output has no `module ... contains ... end module`
        # block (e.g. xp2f.py's own --flat-style output) crashed with an
        # unhandled traceback instead of the same clean message every
        # other unsupported-shape case gets. Confirmed via examples/
        # xalias_repro.py.
        print(f"Extract: FAIL ({e})")
        return 1

    # For --time-both, use xp2f.py's own -O3 -march=native timing flags, so
    # a --run-both/--time-both comparison against `python xp2f.py ...
    # --time-both` is apples-to-apples rather than comparing an unoptimized
    # f2py build against an optimized standalone one. NOT reusing xp2f.py's
    # other default (-O0 -g -fcheck=all -fbacktrace -ffpe-trap=...) here --
    # confirmed empirically that those debug/runtime-check flags break the
    # link step specifically when routed through f2py's meson/ninja/lld
    # build pipeline on this toolchain (undefined symbol: __gthr_win32_self
    # and friends -- gfortran's own direct linker invocation, which is what
    # xp2f.py itself uses, doesn't hit this).
    compiler_flags = shlex.split(xp2f.default_timing_compiler_command())[1:] if args.time_both else []
    print("Compile options:", " ".join(compiler_flags) if compiler_flags else "<none>")

    if args.all:
        return _run_all_targets(
            args, py_path, py_tree, src, out_dir, mod_name, header, lines, procedures, compiler_flags, timings
        )

    func_name = args.function_name
    if func_name is None:
        try:
            func_name = default_target_function_name(py_tree)
        except UnsupportedFunction as e:
            print(f"Target: FAIL ({e})")
            return 1
        print(f"Target: {func_name!r} (defaulted -- first function called at the top level, "
              f"skipping 'main')")

    result = _bridge_one_target(
        func_name, py_tree, py_path, out_dir, mod_name, header, lines, procedures, compiler_flags, timings,
        backend=args.backend,
    )
    if result is None:
        return 1

    if args.verify:
        verify_args = ast.literal_eval(args.verify_args)
        if not isinstance(verify_args, tuple):
            verify_args = (verify_args,)
        ns: dict = {}
        exec(compile(py_tree, str(py_path), "exec"), ns)
        py_result = ns[func_name](*verify_args)
        sys.path.insert(0, str(out_dir))
        wrapper_mod = __import__(result.wrapper_path.stem)
        f_result = getattr(wrapper_mod, func_name)(*verify_args)
        match = _results_match(py_result, f_result)
        print(f"Verify: {'MATCH' if match else 'MISMATCH'} (python={py_result!r} fortran={f_result!r})")
        if not match:
            return 1

    if args.run_both or args.time_both:
        run_both_src = build_run_both_source(src, [(func_name, result.wrapper_path.stem)], py_path)
        ok = _run_both_and_report(
            py_path, run_both_src, out_dir, f"{func_name}_run_both.py", args.time_both, timings
        )
        if not ok:
            return 1

    if args.time_both:
        _print_timing_summary(timings)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
