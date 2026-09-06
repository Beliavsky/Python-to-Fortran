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
import os
import re
import shlex
import subprocess
import sys
import time
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


def _combine_elementwise(left, right, size_of, scalar_names):
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
    ls = _infer_rank1_size(left, size_of, scalar_names)
    if isinstance(ls, str):
        return ls
    rs = _infer_rank1_size(right, size_of, scalar_names)
    if isinstance(rs, str):
        return rs
    if ls is _SCALAR and rs is _SCALAR:
        return _SCALAR
    return None


def _infer_rank1_size(expr, size_of, scalar_names):
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
        return _infer_rank1_size(m.group(1), size_of, scalar_names)

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
            return _infer_rank1_size(expr[1:-1], size_of, scalar_names)

    for ops in (("+", "-"), ("*", "/"), ("**",)):
        split = _split_top_level_op(expr, ops)
        if split:
            left, _op, right = split
            return _combine_elementwise(left, right, size_of, scalar_names)

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
            s = _infer_rank1_size(part.strip(), size_of, scalar_names)
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
                return _infer_rank1_size(arg_parts[idx], size_of, scalar_names) if idx < len(arg_parts) else None
            if fname in _ELEMENTWISE_UNARY_INTRINSICS and len(arg_parts) == 1:
                return _infer_rank1_size(arg_parts[0], size_of, scalar_names)
            if fname in size_of:
                return _SCALAR  # an ordinary single-element subscript of a known array
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

    for i in range(start, end + 1):
        code = _strip_comment(lines[i])
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


def _split_multi_name_decls(target_lines):
    """Normalize any declaration line listing SEVERAL names --
    `TYPE, ATTR1, ATTR2 :: name1(shape1), name2(shape2), ...` -- into one
    line PER name, each carrying the exact same type/attribute prefix. A
    no-op for a line that already declares just one name.

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
        if "::" not in code:
            out.append(ln)
            continue
        prefix, _, names_part = code.partition("::")
        names = _split_top_level(names_part)
        if len(names) <= 1:
            out.append(ln)
            continue
        trailing = ln[len(code) :]  # preserve any trailing comment text verbatim
        for nm in names:
            out.append(f"{prefix}:: {nm.strip()}")
        out[-1] += trailing
    return out


def rewrite_target_for_f2py(lines, start, end, target_name):
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
        for i in range(1, len(target_lines)):
            code = _strip_comment(target_lines[i])
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
        # A GENERIC single-assignment line `NAME = EXPR` -- used both to
        # find `name`'s own (last) assignment and, for the no-allocate()
        # fallback below, to walk every OTHER local array variable's own
        # single assignment too (so `group(1)` must be checked against
        # whichever name is actually wanted, unlike a name-specific regex).
        assign_re = re.compile(r"^\s*([a-z_]\w*)\s*=\s*(.+?)\s*$", re.IGNORECASE)

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
            # _infer_rank1_size's own docstring): a whole-array copy from
            # one of the procedure's own already explicit-shape array
            # arguments (`out = choice`), a slice of a LOCAL array whose
            # own size this same walk can resolve (`func_res = xfull
            # (burnin + 1:size(xfull))`), a Fortran array-constructor
            # concatenation (`ar_poly = [dp :: [1.0_dp], -ar]`), elementwise
            # arithmetic over already-known arrays/scalars (`p(1) * x +
            # p(2) - y`), and a call to one of a small set of recognized
            # python.f90 builtin array-returning helpers (rnorm's
            # `rnorm(k)`, lfilter_real's `lfilter_real(b, a, x[, zi])`). A
            # call to some OTHER, user-defined dependency function is
            # deliberately NOT resolved -- that would need inspecting THAT
            # function's own body, a genuinely open-ended cross-procedure
            # analysis out of scope here (see the module docstring).
            size_of = {}
            for a in arg_names:
                a_i, a_m = _find_decl(a)
                if a_i is not None and a_m.group(3) and a_m.group(3).strip() != ":":
                    size_of[a.lower()] = a_m.group(3).strip()

            # A local PARAMETER (compile-time-constant) array, declared
            # `TYPE, parameter :: NAME(*) = [literal, ...]` -- its own
            # size is exactly its own initializer's, resolvable the same
            # way as any other array constructor.
            param_re = re.compile(
                r"^\s*.*?\bparameter\b.*?::\s*([a-z_]\w*)\s*\(\s*\*\s*\)\s*=\s*(.+)$", re.IGNORECASE
            )
            for i in range(1, len(target_lines)):
                pm = param_re.match(_strip_comment(target_lines[i]))
                if pm and pm.group(1).lower() not in size_of:
                    psize = _infer_rank1_size(pm.group(2), size_of, scalar_names)
                    if isinstance(psize, str):
                        size_of[pm.group(1).lower()] = psize

            for i in range(1, len(target_lines)):
                lm = assign_re.match(_strip_comment(target_lines[i]))
                if not lm:
                    continue
                lname = lm.group(1)
                if lname.lower() == name.lower() or lname.lower() in size_of:
                    continue  # `name` itself resolved below; already known otherwise
                li, lm2 = _find_decl(lname)
                if li is None or lm2.group(3) is None or lm2.group(3).strip() != ":":
                    continue  # not a rank-1 allocatable local
                resolved = _infer_rank1_size(lm.group(2), size_of, scalar_names)
                if isinstance(resolved, str):
                    size_of[lname.lower()] = resolved

            name_rhs = None
            for i in range(1, len(target_lines)):
                am = assign_re.match(_strip_comment(target_lines[i]))
                if am and am.group(1).lower() == name.lower():
                    name_rhs = am.group(2)
            size_expr = None
            if name_rhs is not None:
                resolved = _infer_rank1_size(name_rhs, size_of, scalar_names)
                if isinstance(resolved, str):
                    size_expr = resolved
            if size_expr is None:
                raise UnsupportedFunction(
                    f"{target_name!r}'s own array result has no `allocate(...)` "
                    f"statement, and no recognized whole-array-copy/slice/"
                    f"constructor/elementwise-arithmetic/known-helper "
                    f"expression, this rewrite can safely derive a caller-"
                    f"visible size from -- can't determine one for it"
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
BLOCK_DECL_RE = re.compile(r"^\s*(integer|real|logical|character)\b.*::\s*([a-z_]\w*)\s*$", re.IGNORECASE)


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
    grouping, never a text edit.
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
        out.append(" ".join(parts))
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

    Returns (new_text, unresolved_names) -- unresolved_names lists any
    requested helper this couldn't inline (not found in python.f90, or
    itself calling something outside python_mod), left for the caller to
    reject with a clear message rather than silently ship a broken build.
    """
    m = PYTHON_MOD_USE_RE.search(trimmed_text)
    if not m:
        return trimmed_text, []
    requested = [n.strip() for n in m.group(2).split(",") if n.strip()]

    py_mod_text = PYTHON_MOD_PATH.read_text(encoding="utf-8", errors="ignore")
    _mod_name, py_header, py_lines, py_procs = parse_module(py_mod_text)
    py_interfaces = _find_python_mod_interfaces(py_header)
    known = set(py_procs.keys())

    # Names declared in python.f90's own SPECIFICATION section (outside
    # `contains`) -- e.g. `rng_replay_enabled`, `rng_replay_bin_u` (the
    # private bookkeeping `rnorm`'s own concrete overloads read/write
    # directly, never as one of their own dummy arguments). This
    # function only ever copies a PROCEDURE's own body text into the
    # trimmed module, never anything from the specification section, so
    # a helper that touches one of these can't be inlined at all -- it'd
    # reference a symbol nothing declares, an undetected-until-build-
    # time "has no IMPLICIT type" error, confirmed via examples/
    # xsim_fit_nagarch.py's own `simulate_nagarch` (calls `rnorm()`,
    # whose `rnorm0` overload touches this replay state). `dp` is the
    # one exception -- always separately declared by the trimmed module
    # itself already, so a reference to it is harmless.
    module_state_names = set()
    for ln in py_header:
        code = _strip_comment(ln)
        if "::" not in code or code.strip().lower().startswith(("use", "public", "private", "implicit")):
            continue
        for part in _split_top_level(code.split("::", 1)[1]):
            dm = re.match(r"^\s*([a-z_]\w*)", part, re.IGNORECASE)
            if dm and dm.group(1).lower() != "dp":
                module_state_names.add(dm.group(1).lower())

    def _touches_module_state(start_names):
        seen = set()
        stack = list(start_names)
        while stack:
            nm = stack.pop()
            if nm in seen or nm not in py_procs:
                continue
            seen.add(nm)
            start, end = py_procs[nm]
            # A state name that's ALSO locally declared within this same
            # procedure (a dummy argument, its own named result, or a
            # plain local) is shadowed -- a coincidental reuse of a
            # module-level name, not an actual reference to it.
            # Confirmed a real false-positive risk: python.f90 uses
            # `result(v)` as a common naming convention across MANY
            # otherwise-unrelated functions, and `v` also happens to be
            # a genuine module-level name -- without this exclusion,
            # optval_real's own `result(v)` falsely tripped this check.
            local_names = set()
            for i in range(start, end + 1):
                code = _strip_comment(py_lines[i])
                if "::" not in code:
                    continue
                for part in _split_top_level(code.split("::", 1)[1]):
                    dm = re.match(r"^\s*([a-z_]\w*)", part, re.IGNORECASE)
                    if dm:
                        local_names.add(dm.group(1).lower())
            # A plain RESULT_NAME_RE *search* (not requiring a full
            # SIG_RE match) so a TYPE-PREFIXED function signature --
            # `pure integer function optval_int(x, default) result(v)`,
            # which SIG_RE itself doesn't match at all, since its own
            # `prefix` group only recognizes pure/elemental/impure/
            # recursive, never a leading type name -- still has its own
            # `result(v)` found and excluded. Confirmed a real false
            # positive without this: `v` is ALSO a genuine module-level
            # name, and 3 of optval's own 4 concrete overloads use this
            # exact type-prefixed form.
            proc_m = PROC_START_RE.match(_strip_comment(py_lines[start]))
            rm = RESULT_NAME_RE.search(_strip_comment(py_lines[start]))
            if rm:
                local_names.add(rm.group(1).lower())
            elif proc_m and proc_m.group(1).lower() == "function":
                local_names.add(proc_m.group(2).lower())
            body_text = "\n".join(py_lines[start : end + 1])
            for state_name in module_state_names - local_names:
                if re.search(rf"\b{re.escape(state_name)}\b", body_text, re.IGNORECASE):
                    return True
            stack.extend(find_calls(py_lines, start, end, known, nm))
        return False

    needed = set()  # concrete procedure names to inline into `contains`
    needed_interfaces = set()  # generic interface names to inline into the spec section
    frontier = []
    unresolved = []
    for n in requested:
        nl = n.lower()
        if nl in py_procs:
            if _touches_module_state([nl]):
                unresolved.append(n)
            else:
                frontier.append(nl)
        elif nl in py_interfaces:
            members = [mem.lower() for mem in py_interfaces[nl][2]]
            if _touches_module_state(members):
                unresolved.append(n)
            else:
                needed_interfaces.add(nl)
                frontier.extend(members)
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

    inlined_body = []
    for nm in sorted(needed, key=lambda n: py_procs[n][0]):
        start, end = py_procs[nm]
        inlined_body.extend(py_lines[start : end + 1])
        inlined_body.append("")

    interface_body = []
    for nm in sorted(needed_interfaces, key=lambda n: py_interfaces[n][0]):
        start, end, _members = py_interfaces[nm]
        interface_body.extend(py_header[start : end + 1])
        interface_body.append("")

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

    if interface_body:
        contains_re = re.compile(r"^\s*contains\s*$", re.IGNORECASE | re.MULTILINE)
        cm = contains_re.search(new_text)
        if cm is not None:
            insertion = "\n".join(interface_body) + "\n"
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


def find_target_def(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
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


def generate_wrapper(mod_name, ext_name, func_name, arg_names) -> str:
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
    # way the original Python function did.
    call_args = ", ".join(f"{a.lower()}={a}" for a in arg_names)
    return (
        f"# Generated by xpfunc2f.py -- a thin wrapper around the f2py-compiled\n"
        f"# Fortran translation of `{func_name}`. Same name, same call signature\n"
        f"# as the original Python function; drop-in replacement at call sites.\n"
        f"import {ext_name}\n\n\n"
        f"def {func_name}({args_sig}):\n"
        f"    return {ext_name}.{mod_name}.{func_name}({call_args})\n"
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
    # Fortran dummy's own name for its generated Python-facing keyword.
    call_args = ", ".join(f"{a.lower()}={a}" for a in arg_names)
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
        f"    {unpack} = {ext_name}.{mod_name}.{bridge_name}({call_args})\n"
        f"    return {trims}\n"
    )


def build_run_both_source(src: str, func_name: str, wrapper_stem: str) -> str:
    """Return the original script's own source with just the target
    function's `def` replaced by an import of its Fortran-backed wrapper
    (same name) -- so everything else (its own dependency functions, any
    other code) keeps running as ordinary Python, and only the one call
    site the user named is rerouted to compiled Fortran.

    This is what --run-both/--time-both diff against the original: the
    WHOLE script's real, natural output, in situ -- a stronger check than
    --verify's isolated call on manually supplied arguments.
    """
    tree = ast.parse(src)
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            replacement = ast.ImportFrom(
                module=wrapper_stem, names=[ast.alias(name=func_name, asname=None)], level=0
            )
            tree.body[i] = ast.copy_location(replacement, node)
            ast.fix_missing_locations(tree)
            return ast.unparse(tree)
    raise UnsupportedFunction(f"no top-level `def {func_name}(...)` found in the source script")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input_py", help="input python source containing the target function")
    ap.add_argument(
        "function_name",
        nargs="?",
        default=None,
        help="name of the top-level function to translate (default: the first function "
        "the script's own top-level code calls, skipping a call to 'main')",
    )
    ap.add_argument("--out-dir", help="directory for generated files (default: alongside input_py)")
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
    func_name = args.function_name

    timings: dict = {}

    src = py_path.read_text(encoding="utf-8-sig")
    py_tree = ast.parse(src)
    if func_name is None:
        try:
            func_name = default_target_function_name(py_tree)
        except UnsupportedFunction as e:
            print(f"Target: FAIL ({e})")
            return 1
        print(f"Target: {func_name!r} (defaulted -- first function called at the top level, "
              f"skipping 'main')")
    try:
        target_def = find_target_def(py_tree, func_name)
    except UnsupportedFunction as e:
        print(f"Target: FAIL ({e})")
        return 1
    arg_names = [a.arg for a in target_def.args.args]

    # Reuse xp2f.py's own, unmodified whole-program translation wholesale
    # -- same type inference, same codegen, zero new risk to it -- then
    # extract just the target function's transitive dependency closure
    # out of the result.
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
    had_array = False
    bridge_name = None
    bridge_text = None
    n_bridge_outputs = 0
    try:
        mod_name, header, lines, procedures = parse_module(f90_text)
        needed = collect_closure(func_name, procedures, lines)
        target_key = func_name.lower()
        t_start, t_end = procedures[target_key]

        # Try the "provably bounded, data-dependent-length accumulator"
        # bridge FIRST (a distinct codegen shape from rewrite_target_
        # for_f2py's own "size is a simple function of the arguments"
        # case, cheaply told apart by trying this one first) -- only
        # falls through to rewrite_target_for_f2py when the target
        # doesn't match that idiom at all.
        bridge_spec = try_build_bridge_for_target(lines, t_start, t_end, func_name)
        if bridge_spec is not None:
            had_array = True
            bridge_name = f"{func_name}_bridge"
            bridge_text, _bridge_counts = build_bridge_procedure(
                lines, t_start, t_end, func_name, bridge_spec, bridge_name
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
            target_lines, had_array = rewrite_target_for_f2py(lines, t_start, t_end, func_name)

        if bridge_name is None:
            check_f2py_compatible(target_lines, 0, len(target_lines) - 1, target_key)
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
    except UnsupportedFunction as e:
        print(f"Extract: FAIL ({e})")
        return 1
    print(f"Extract: PASS ({func_name} + {len(needed) - 1} dependency function(s): "
          f"{', '.join(sorted(needed - {func_name.lower()})) or '(none)'})")
    if bridge_name is not None:
        print(f"Extract: {func_name!r} has (a) data-dependent-length array result(s) -- "
              f"bridged via a generated {bridge_name!r} subroutine (over-allocated to a "
              f"provable bound, trimmed by its own true count in the wrapper)")
    elif had_array:
        print(f"Extract: {func_name!r} has a rank-1 array argument/result -- "
              f"rewritten to an f2py-bridgeable explicit-shape form")

    trimmed_text = build_trimmed_module(
        mod_name, header, lines, procedures, needed, override_lines={target_key: target_lines}
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
        trimmed_text = remove_from_public(trimmed_text, func_name)
        trimmed_text = append_procedure_to_module(trimmed_text, bridge_text, bridge_name)
    # A `python_mod` helper (e.g. mean_1d) the trimmed module still needs
    # is INLINED directly rather than compiled/linked as a separate
    # object -- confirmed empirically that both alternatives fail on this
    # toolchain (see inline_python_mod_helpers's own docstring).
    trimmed_text, unresolved_helpers = inline_python_mod_helpers(trimmed_text)
    if unresolved_helpers:
        print(f"Extract: FAIL (needs helper(s) {', '.join(unresolved_helpers)!r} this "
              f"tool can't yet bridge -- only simple python_mod helpers inlinable "
              f"directly into the trimmed module are supported, not a helper module "
              f"requiring its own separate compile/link, e.g. LAPACK-backed routines "
              f"or a pandas DataFrame companion type)")
        return 1
    trimmed_path = out_dir / f"{func_name}_f.f90"
    trimmed_path.write_text(trimmed_text, encoding="utf-8")

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
    t0 = time.perf_counter() if args.time_both else None
    proc = subprocess.run(
        f2py_cmd,
        cwd=out_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if args.time_both:
        timings["compile"] = time.perf_counter() - t0
    if proc.returncode != 0:
        print("F2PY Build: FAIL")
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        return 1
    print("F2PY Build: PASS")

    wrapper_path = out_dir / f"{func_name}_f.py"
    if bridge_name is not None:
        wrapper_path.write_text(
            generate_bridge_wrapper(mod_name, ext_name, func_name, arg_names, bridge_name, n_bridge_outputs),
            encoding="utf-8",
        )
    else:
        wrapper_path.write_text(
            generate_wrapper(mod_name, ext_name, func_name, arg_names), encoding="utf-8"
        )
    print(f"Wrapper: {wrapper_path}")

    if args.verify:
        verify_args = ast.literal_eval(args.verify_args)
        if not isinstance(verify_args, tuple):
            verify_args = (verify_args,)
        ns: dict = {}
        exec(compile(py_tree, str(py_path), "exec"), ns)
        py_result = ns[func_name](*verify_args)
        sys.path.insert(0, str(out_dir))
        wrapper_mod = __import__(wrapper_path.stem)
        f_result = getattr(wrapper_mod, func_name)(*verify_args)
        match = _results_match(py_result, f_result)
        print(f"Verify: {'MATCH' if match else 'MISMATCH'} (python={py_result!r} fortran={f_result!r})")
        if not match:
            return 1

    if args.run_both or args.time_both:
        run_both_src = build_run_both_source(src, func_name, wrapper_path.stem)
        run_both_path = out_dir / f"{func_name}_run_both.py"
        run_both_path.write_text(run_both_src, encoding="utf-8")

        # The patched script needs both the wrapper module and its compiled
        # f2py extension importable; both were just written into out_dir.
        run_env = os.environ.copy()
        existing_pp = run_env.get("PYTHONPATH", "")
        run_env["PYTHONPATH"] = str(out_dir) + (os.pathsep + existing_pp if existing_pp else "")

        t0 = time.perf_counter() if args.time_both else None
        py_rc, py_out, py_err, _ = xp2f.run_capture([sys.executable, str(py_path)], env=run_env)
        if args.time_both:
            timings["python_run"] = time.perf_counter() - t0
        print(f"Run (python): {'PASS' if py_rc == 0 else f'FAIL (exit {py_rc})'}")
        if py_out.strip():
            print(py_out.rstrip())
        if py_rc != 0:
            if py_err.strip():
                print(py_err.rstrip())
            return 1

        t0 = time.perf_counter() if args.time_both else None
        fb_rc, fb_out, fb_err, _ = xp2f.run_capture([sys.executable, str(run_both_path)], env=run_env)
        if args.time_both:
            timings["fortran_run"] = time.perf_counter() - t0
        print(f"Run (fortran-backed): {'PASS' if fb_rc == 0 else f'FAIL (exit {fb_rc})'}")
        if fb_out.strip():
            print(fb_out.rstrip())
        if fb_rc != 0:
            if fb_err.strip():
                print(fb_err.rstrip())
            return 1

        def _norm(text: str) -> list[str]:
            return text.replace("\r\n", "\n").rstrip("\n").splitlines()

        py_lines = _norm(py_out)
        fb_lines = _norm(fb_out)
        run_both_match = py_lines == fb_lines
        print(f"Run-both: {'MATCH' if run_both_match else 'DIFF'}")
        if not run_both_match:
            for dl in difflib.unified_diff(py_lines, fb_lines, fromfile="python", tofile="fortran-backed", lineterm=""):
                print(dl)

        if not run_both_match:
            return 1

    if args.time_both:
        # Same stage set and layout as xp2f.py's own timing summary
        # ("python run" / "transpile" / "compile" / "fortran run" /
        # "total") so the two tools' reported speedups read side by side.
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
