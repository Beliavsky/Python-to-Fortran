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

Helper boundaries: the vendored helper sources (python.f90, lapack_d.f90,
minpack.f90, the optimizer bridges, the DataFrame modules, ...) are static
Fortran with default-kind INTEGER dummies. Their signatures are scanned
(dummy position, name, intent, optional/allocatable/pointer, and whether
the dummy is a default integer), including generic interfaces and
type-bound bindings. Every generated integer is widened, and each helper
call is converted argument by argument:

- a literal, or an array constructor of literals, keeps the default kind;
- any other value for an intent(in) default-integer dummy is converted --
  with the checked `narrow_int` from python.f90 for int64, which stops the
  program rather than pass a truncated value, and with `int` for int32;
- a variable passed to an out/inout, allocatable or pointer dummy, or as a
  plain name to an optional one (it may be an absent optional argument,
  which can be passed on but not converted), stays default kind. A local
  procedure whose dummy stays default kind that way is itself a boundary
  for its callers, and a default-kind variable passed to a widened
  intent(in) dummy is converted with `int(..., kind=ikind)`;
- a generic with a specific for other integer kinds (py_str_int64,
  py_format_int64) is left to resolve by itself, keeping the full value.

Integer-result intrinsics without a KIND argument (size, len, nint, ...)
get `kind=ikind`, and interface bodies import `ikind`.

Every bare integer LITERAL constant also gets an `_ikind` suffix (skipping
string/comment content) -- this mirrors xp2f.py's own existing, proven
approach for REAL literals (every real constant it emits already gets a
`_dp` suffix, e.g. `0.5` -> `0.5_dp`): Fortran requires an actual argument
passed to a procedure under an explicit interface to match its dummy's kind
EXACTLY (unlike assignment or arithmetic, which freely widen) -- so a
literal like `foo(3, 4)` fails to compile once `foo`'s own parameters
become `integer(kind=ikind)`, the same way an unsuffixed real literal would
fail against a `real(kind=dp)` parameter.

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
_BOUNDARY_SOURCE_FILES = (
    "python.f90", "lapack_d.f90", "minpack.f90", "bfgs.f90", "lbfgsb.f90", "fmin.f90", "root.f90",
)
_BOUNDARY_SOURCE_GLOB = "*_bridge.f90"
_BOUNDARY_SOURCE_GLOBS = (_BOUNDARY_SOURCE_GLOB, "dataframe_*.f90", "time_sleep_*.f90")

_boundary_calls_cache: Optional[frozenset] = None
_boundary_sigs_cache = None

_INTENT_RE = re.compile(r"\bintent\s*\(\s*(in\s*out|inout|out|in)\s*\)", re.IGNORECASE)
_TYPE_DECL_RE = re.compile(
    r"^\s*(?P<type>integer|real|complex|logical|character|type\s*\(|class\s*\(|double\s+precision)"
    r"(?P<sel>\s*\([^:]*?\))?(?P<attrs>[^:]*)::(?P<names>.*)$",
    re.IGNORECASE,
)


def _boundary_source_paths() -> List[Path]:
    base_dir = Path(__file__).resolve().parent
    paths = [base_dir / f for f in _BOUNDARY_SOURCE_FILES]
    for pattern in _BOUNDARY_SOURCE_GLOBS:
        paths.extend(sorted(base_dir.glob(pattern)))
    return [p for p in dict.fromkeys(paths) if p.exists()]


def _unit_dummies(unit) -> List[dict]:
    """Per dummy argument of a scanned unit, in order: whether it is a
    default-kind INTEGER, its intent, and whether it is allocatable/pointer
    or a derived-type object (a type-bound procedure's passed object)."""
    info = {a.lower(): {"name": a.lower(), "int": False, "intent": None, "alloc": False, "opt": False,
                        "kinded_int": False, "obj": False}
            for a in unit["args"]}
    for _ln, stmt in fscan.iter_fortran_statements(unit["body_lines"]):
        m = _TYPE_DECL_RE.match(stmt)
        if m is None:
            continue
        typ = m.group("type").lower().replace(" ", "")
        default_int = typ == "integer" and not m.group("sel")
        attrs = m.group("attrs")
        im = _INTENT_RE.search(attrs)
        intent = re.sub(r"\s+", "", im.group(1).lower()) if im else None
        if intent is None and re.search(r"\bvalue\b", attrs, re.IGNORECASE):
            intent = "in"
        alloc = bool(re.search(r"\b(allocatable|pointer)\b", attrs, re.IGNORECASE))
        # A variable passed to an optional dummy may be an absent optional
        # argument of the caller, which can be passed on but not converted
        # (`optval(int(max_iter), 1000)` read a missing argument).
        opt = bool(re.search(r"\boptional\b", attrs, re.IGNORECASE))
        for chunk in fscan._split_top_level_commas(m.group("names")):
            nm = re.match(r"^\s*([A-Za-z_]\w*)", chunk)
            if nm and nm.group(1).lower() in info:
                d = info[nm.group(1).lower()]
                d.update(int=default_int, intent=intent, alloc=alloc, opt=opt, obj=typ in ("type(", "class("),
                         kinded_int=typ == "integer" and bool(m.group("sel")))
    return [info[a.lower()] for a in unit["args"]]


_INT_RESULT_HELPERS: Set[str] = set()


def _function_returns_default_int(unit) -> bool:
    header_type = unit.get("header_type") if isinstance(unit, dict) else None
    res = (unit.get("result") or unit["name"]).lower()
    for _ln, stmt in fscan.iter_fortran_statements(unit["body_lines"]):
        m = _TYPE_DECL_RE.match(stmt)
        if m is None:
            continue
        for chunk in fscan._split_top_level_commas(m.group("names")):
            nm = re.match(r"^\s*([A-Za-z_]\w*)", chunk)
            if nm and nm.group(1).lower() == res:
                return m.group("type").lower() == "integer" and not m.group("sel")
    return bool(header_type) and header_type.lower() == "integer"


def _scan_boundary_signatures():
    """Signatures of the vendored helper procedures (python.f90, LAPACK,
    MINPACK, the optimizer bridges, the DataFrame modules, ...): name ->
    list of dummy lists (several for a generic interface), plus type-bound
    binding names -> implementation names. Cached."""
    global _boundary_sigs_cache
    if _boundary_sigs_cache is not None:
        return _boundary_sigs_cache
    sigs = {}
    bindings = {}
    int_results = set()
    generics = {}
    for path in _boundary_source_paths():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for unit in fscan.split_fortran_units_simple(text):
            if unit["kind"] in ("subroutine", "function"):
                sigs.setdefault(unit["name"].lower(), []).append(_unit_dummies(unit))
            if unit["kind"] == "function" and _function_returns_default_int(unit):
                int_results.add(unit["name"].lower())
        for m_if in re.finditer(
            r"^\s*interface\s+([A-Za-z_]\w*)\s*$(.*?)^\s*end\s+interface\b",
            text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
        ):
            for m_mp in re.finditer(r"^\s*module\s+procedure\s+(.+)$", m_if.group(2), flags=re.IGNORECASE | re.MULTILINE):
                for nm in m_mp.group(1).split(","):
                    if nm.strip():
                        sigs.setdefault(m_if.group(1).lower(), []).append(("generic", nm.strip().lower()))
                        generics.setdefault(m_if.group(1).lower(), []).append(nm.strip().lower())
        # Type-bound bindings: `procedure :: a, b=>impl_b` in a type definition.
        for _ln, stmt in fscan.iter_fortran_statements(text.splitlines()):
            m_b = re.match(r"^\s*(procedure|generic)\b[^:]*::(.*)$", stmt, re.IGNORECASE)
            if m_b is None:
                continue
            for part in m_b.group(2).split(","):
                if "=>" in part:
                    bname, impls = part.split("=>", 1)
                    targets = [impls.strip().lower()]
                else:
                    bname, targets = part, [part.strip().lower()]
                if bname.strip():
                    bindings.setdefault(bname.strip().lower(), []).extend(x for x in targets if x)
    # Resolve generic entries to the specifics' dummy lists.
    resolved = {}
    for name, entries in sigs.items():
        out = []
        for e in entries:
            if isinstance(e, tuple):
                out.extend(x for x in sigs.get(e[1], []) if not isinstance(x, tuple))
            else:
                out.append(e)
        resolved[name] = out
    # A generic whose specifics all return a default integer does too.
    for name, specifics in generics.items():
        if specifics and all(s in int_results for s in specifics):
            int_results.add(name)
    _INT_RESULT_HELPERS.clear()
    _INT_RESULT_HELPERS.update(int_results)
    _boundary_sigs_cache = (resolved, bindings)
    return _boundary_sigs_cache


def _scan_external_boundary_calls() -> frozenset:
    """Names of helper procedures with at least one default-kind INTEGER
    dummy (kept for callers of the older name-only interface)."""
    global _boundary_calls_cache
    if _boundary_calls_cache is not None:
        return _boundary_calls_cache
    sigs, _bindings = _scan_boundary_signatures()
    _boundary_calls_cache = frozenset(
        nm for nm, lists in sigs.items() if any(d["int"] for dl in lists for d in dl))
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

# Consume an entire numeric token, including signed real exponents, before
# deciding whether it is a bare integer. Otherwise the 3 in 1e-3 is rewritten.
_NUMERIC_TOKEN_RE = re.compile(
    r"\d+(?:\.\d*)?(?:[eEdDqQ][+-]?\d+)?(?:_[A-Za-z0-9_]+)?"
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
            token_match = _NUMERIC_TOKEN_RE.match(code, i)
            j = token_match.end()
            prev_ch = code[i - 1] if i > 0 else ""
            next_ch = code[j] if j < n else ""
            # Empty strings compare as members of every Python string; they
            # are token boundaries, not identifier/real/suffix characters.
            is_ident_or_real_prefix = bool(prev_ch) and (prev_ch.isalnum() or prev_ch in "_.")
            is_real_or_suffixed_or_ident = bool(next_ch) and (next_ch in "._" or next_ch.isalpha())
            is_leading_kind_selector = protected_span == (i, j)
            token = code[i:j]
            if (not token.isdigit() or is_ident_or_real_prefix
                    or is_real_or_suffixed_or_ident or is_leading_kind_selector):
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


_LITERAL_ARG_RE = re.compile(r"^\s*[+-]?\s*\d+(?:_ikind)?\s*$", re.IGNORECASE)
_LITERAL_CTOR_RE = re.compile(
    r"^\s*\[\s*[+-]?\s*\d+(?:_ikind)?(?:\s*,\s*[+-]?\s*\d+(?:_ikind)?)*\s*\]\s*$", re.IGNORECASE)
_VAR_ARG_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?:\(.*\))?\s*$", re.DOTALL)
_WIDE_INT_CAST_RE = re.compile(r"^\s*int\s*\((.*),\s*kind\s*=\s*ikind\s*\)\s*$", re.IGNORECASE | re.DOTALL)
_IDENT_RE = re.compile(r"[A-Za-z_]\w*")
_HEADER_RE = re.compile(
    r"^\s*(?:(?:pure|impure|elemental|recursive|module)\s+)*"
    r"(?:(?:integer|real|complex|logical|character|type)\s*(?:\([^)]*\))?\s+)?(?:function|subroutine)\s+\w+",
    re.IGNORECASE)
_KEYWORD_ARG_RE = re.compile(r"^(\s*[A-Za-z_]\w*\s*=)(?!=)(.*)$", re.DOTALL)


def _match_paren(code: str, open_idx: int) -> Optional[int]:
    depth = 0
    quote = None
    for i in range(open_idx, len(code)):
        ch = code[i]
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "'\"":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
    return None


_INT_INTRINSICS = frozenset({
    "int", "nint", "floor", "ceiling", "size", "len", "len_trim", "index", "scan", "verify",
    "count", "lbound", "ubound", "iachar", "ichar", "mod", "modulo", "abs", "max", "min",
    "sum", "product", "maxval", "minval", "merge", "huge", "kind", "ishft", "iand", "ior", "ieor",
    # Type-preserving: integer exactly when their arguments are, which the
    # check requires anyway (print_matrix(matmul(a, b)) with int64 a, b).
    "matmul", "transpose", "reshape", "spread", "pack", "unpack", "cshift", "eoshift",
    "dot_product", "sign", "dim",
})


def _is_integer_expr(body: str, int_names: Set[str]) -> bool:
    """True when `body` is clearly integer-valued: every variable in it is
    declared integer, every function returns an integer, and it has no real
    literal, string or `.` operator. False when unsure."""
    if re.search(r"['\"]|\d\.|\.\d|\.[a-z]+\.|_dp\b|\*\*", body, re.IGNORECASE):
        return False
    for m in re.finditer(r"(?<![\w%])([A-Za-z_]\w*)(\s*\()?", body):
        name = m.group(1).lower()
        if name in ("ikind", "kind"):
            continue
        if m.group(2):
            if name not in _INT_INTRINSICS and name not in _INT_RESULT_HELPERS:
                return False
        elif name not in int_names:
            return False
    return True


class _Boundary:
    """Calls whose integer arguments must keep the default kind: the
    vendored helpers (by signature), local procedures with dummies that had
    to stay default kind, and bare names with no known signature (every
    argument then gets the older treatment).

    For each such argument, per call: a literal, or an array constructor of
    literals, loses its `_ikind` suffix; an intent(in) value is converted
    with `int(...)`; a variable passed to an out/inout, allocatable or
    pointer dummy is reported so that its declaration stays default kind."""

    def __init__(self, sigs=None, bindings=None, legacy_names=frozenset()):
        self.sigs = dict(sigs or {})
        self.bindings = dict(bindings or {})
        self.legacy = frozenset(n.lower() for n in legacy_names)
        # How an integer(kind=ikind) value is brought to the default kind.
        self.narrow = "int"
        # Variables of the file being rewritten: `active(i)` is an array
        # element there even though lbfgsb.f90 has a routine `active`.
        self.shadowed: Set[str] = set()

    @classmethod
    def coerce(cls, boundary):
        if isinstance(boundary, cls):
            return boundary
        return cls(legacy_names=frozenset(boundary))

    def names(self) -> frozenset:
        return frozenset(self.sigs) | self.legacy

    def candidates(self, name: str, typebound: bool):
        """Dummy lists for a call, None if it is not a boundary call, or []
        for a name with no known signature."""
        if typebound:
            out = []
            for impl in self.bindings.get(name, []):
                for dl in self.sigs.get(impl, []):
                    out.append(dl[1:] if dl and dl[0]["obj"] else dl)
            return out or None
        if name in self.sigs:
            return self.sigs[name]
        if name in self.legacy:
            return []
        return None

    def calls(self, code: str):
        """(name, typebound, open_idx, close_idx) of boundary calls in
        `code`, left to right, outer calls before those nested in them."""
        i, n = 0, len(code)
        quote = None
        while i < n:
            ch = code[i]
            if quote:
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in "'\"":
                quote = ch
                i += 1
                continue
            m = _IDENT_RE.match(code, i)
            if m and (i == 0 or not (code[i - 1].isalnum() or code[i - 1] == "_")):
                k = m.end()
                while k < n and code[k] == " ":
                    k += 1
                if k < n and code[k] == "(":
                    typebound = i > 0 and code[i - 1] == "%"
                    name = m.group(0).lower()
                    close = _match_paren(code, k)
                    if (close is not None and (typebound or name not in self.shadowed)
                            and self.candidates(name, typebound) is not None):
                        yield name, typebound, k, close
                i = m.end()
                continue
            i += 1

    def arg_roles(self, name: str, typebound: bool, args: List[str]) -> List[Optional[str]]:
        """Per actual argument: None (no default-integer dummy), "in" (an
        intent(in) default integer in every matching specific), "maybe_in"
        (in some), "out" (out/inout/allocatable/pointer/no intent), or
        "legacy" (no known signature)."""
        cands = self.candidates(name, typebound)
        roles: List[Optional[str]] = []
        for pos, arg in enumerate(args):
            if not cands:
                roles.append("legacy")
                continue
            kw = _KEYWORD_ARG_RE.match(arg)
            found = []
            for dl in cands:
                d = None
                if kw:
                    kwname = kw.group(1).strip().rstrip("=").strip().lower()
                    d = next((x for x in dl if x["name"] == kwname), None)
                elif pos < len(dl):
                    d = dl[pos]
                if d is not None:
                    found.append(d)
            ints = [d for d in found if d["int"]]
            value = kw.group(2) if kw else arg
            if not ints or any(d.get("kinded_int") for d in found):
                # No default-integer dummy here, or a generic with a specific
                # for other integer kinds (py_str_int64), which then resolves.
                roles.append(None)
            elif any(d["alloc"] or d["intent"] != "in" for d in ints) or (
                    any(d.get("opt") for d in ints) and re.fullmatch(r"\s*[A-Za-z_]\w*\s*", value)):
                roles.append("out")
            else:
                roles.append("in" if len(ints) == len(found) else "maybe_in")
        return roles

    def excluded_actuals(self, text: str) -> Set[str]:
        """Variables that must stay default kind because of this statement."""
        names: Set[str] = set()
        for name, typebound, op, cl in self.calls(text):
            args = fscan._split_top_level_commas(text[op + 1:cl])
            for arg, role in zip(args, self.arg_roles(name, typebound, args)):
                kw = _KEYWORD_ARG_RE.match(arg)
                value = kw.group(2) if kw else arg
                if role == "out":
                    m = _VAR_ARG_RE.match(value)
                    if m:
                        names.add(m.group(1).lower())
                elif role == "legacy":
                    v = re.sub(r"'([^']|'')*'|\"([^\"]|\"\")*\"", " ", value)
                    names.update(re.findall(r"\b[a-z_]\w*\b", v.lower()))
        return names

    def rewrite(self, code: str, int_names: Set[str]) -> str:
        """Apply the per-argument conversions to one statement whose
        literals are already suffixed."""
        out: List[str] = []
        pos = 0
        for name, typebound, op, cl in self.calls(code):
            if op < pos:
                continue  # nested in a call already rewritten
            out.append(code[pos:op + 1])
            args = fscan._split_top_level_commas(code[op + 1:cl])
            roles = self.arg_roles(name, typebound, args)
            new_args = []
            for arg, role in zip(args, roles):
                kw = _KEYWORD_ARG_RE.match(arg)
                prefix, value = (kw.group(1).strip(), kw.group(2)) if kw else ("", arg)
                body = self.rewrite(value, int_names).strip()
                if role == "legacy":
                    body = re.sub(r"(?<![\w.])(\d+)_ikind\b", r"\1", body)
                elif role in ("in", "maybe_in", "out"):
                    var = _VAR_ARG_RE.match(body)
                    if _LITERAL_ARG_RE.match(body) or _LITERAL_CTOR_RE.match(body):
                        body = re.sub(r"(\d+)_ikind\b", r"\1", body)
                    elif role == "in" or (role == "maybe_in" and (
                            (var and var.group(1).lower() in int_names) or _is_integer_expr(body, int_names))):
                        wide = _WIDE_INT_CAST_RE.match(body)
                        if self.narrow == "int":
                            body = f"int({wide.group(1).strip()})" if wide else f"int({body})"
                        else:
                            body = f"{self.narrow}({body})"
                new_args.append(prefix + body)
            out.append(", ".join(new_args))
            out.append(")")
            pos = cl + 1
        out.append(code[pos:])
        return "".join(out)


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


def _scoped_exclusions(stmts, boundary):
    """Resolve boundary actual names to declarations, respecting local shadows.

    `boundary` is a _Boundary, or a set of procedure names whose every
    argument is treated as a default-kind integer (the older policy).

    A real LAPACK argument named `r` must not prevent an unrelated integer
    accumulator `r` in another procedure from being widened. Host-associated
    integers, however, must remain default-kind when a contained routine uses
    them at an external boundary.
    """
    boundary = _Boundary.coerce(boundary)
    scopes = [{"parent": None, "names": set(), "excluded": set()}]
    stack = [0]
    owners = {}
    opening = re.compile(
        r"^(?:(?:pure|impure|elemental|recursive|module)\s+)*"
        r"(?:(?:integer|real|complex|logical|character)(?:\s*\([^)]*\))?\s+|double\s+precision\s+)?"
        r"(?:function|subroutine)\s+\w+\s*\(|^(?:module|program)\s+\w+\s*$|^block\s*$",
        re.IGNORECASE)
    closing = re.compile(r"^end\s*(?:function|subroutine|module|program|block)\b|^end$", re.IGNORECASE)
    for lineno, text in stmts:
        if opening.match(text) and not re.match(r"^module\s+procedure\b", text, re.IGNORECASE):
            scopes.append({"parent": stack[-1], "names": set(), "excluded": set()})
            stack.append(len(scopes) - 1)
            # Calls to a local routine that reaches an external boundary are
            # kept default-kind as a whole by the existing boundary policy.
            # Its dummy declarations must agree even for dummies that are not
            # themselves forwarded to the external helper.
            procedure = re.search(r"\b(?:function|subroutine)\s+(\w+)\s*\(([^)]*)\)", text, re.IGNORECASE)
            if procedure and procedure.group(1).lower() in boundary.legacy:
                scopes[stack[-1]]["excluded"].update(
                    arg.strip().lower() for arg in procedure.group(2).split(",") if arg.strip())
        owners[lineno] = stack[-1]
        if re.match(r"^(?:integer|real|complex|logical|character|type\s*\(|class\s*\()", text, re.IGNORECASE) and "::" in text:
            for part in fscan._split_top_level_commas(text.split("::", 1)[1]):
                name = re.match(r"\s*([A-Za-z_]\w*)", part)
                if name:
                    scopes[stack[-1]]["names"].add(name.group(1).lower())
        if closing.match(text) and len(stack) > 1:
            stack.pop()
    for lineno, text in stmts:
        if _HEADER_RE.match(text):
            continue
        names = boundary.excluded_actuals(text)
        for name in names:
            scope = owners[lineno]
            while scope is not None and name not in scopes[scope]["names"]:
                scope = scopes[scope]["parent"]
            if scope is not None:
                scopes[scope]["excluded"].add(name)
    result = {}
    for lineno, own in owners.items():
        excluded, shadowed = set(), set()
        scope = own
        while scope is not None:
            excluded.update(scopes[scope]["excluded"] - shadowed)
            shadowed.update(scopes[scope]["names"])
            scope = scopes[scope]["parent"]
        # Kind selectors are compile-time kind numbers, not runtime integers.
        result[lineno] = excluded | {"dp", "sp", "ikind"}
    return result


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


def _widen_default_actuals(code: str, widened_sigs, excluded: Set[str]) -> str:
    """A variable kept at the default kind (it reaches a helper's out,
    inout or optional argument) passed to a local procedure's widened
    intent(in) dummy is converted with `int(..., kind=ikind)`."""
    if not widened_sigs or not excluded:
        return code
    conv = _Boundary(sigs={nm: [dl] for nm, dl in widened_sigs.items()})
    out: List[str] = []
    pos = 0
    for name, typebound, op, cl in conv.calls(code):
        if op < pos or typebound:
            continue
        args = fscan._split_top_level_commas(code[op + 1:cl])
        roles = conv.arg_roles(name, typebound, args)
        new_args = []
        for arg, role in zip(args, roles):
            kw = _KEYWORD_ARG_RE.match(arg)
            prefix, value = (kw.group(1).strip(), kw.group(2).strip()) if kw else ("", arg.strip())
            if role == "in" and re.fullmatch(r"[A-Za-z_]\w*", value) and value.lower() in excluded:
                value = f"int({value}, kind=ikind)"
            new_args.append(prefix + value)
        out.append(code[pos:op + 1])
        out.append(", ".join(new_args))
        out.append(")")
        pos = cl + 1
    out.append(code[pos:])
    return "".join(out)


def _names_defined_in(stmts) -> Set[str]:
    """Procedure and variable names defined in the file (an intrinsic of the
    same name is then not an intrinsic there)."""
    names: Set[str] = set()
    for _ln, text in stmts:
        m = re.search(r"\b(?:function|subroutine)\s+([A-Za-z_]\w*)", text, re.IGNORECASE)
        if m and _HEADER_RE.match(text):
            names.add(m.group(1).lower())
        m = _TYPE_DECL_RE.match(text)
        if m:
            for chunk in fscan._split_top_level_commas(m.group("names")):
                nm = re.match(r"^\s*([A-Za-z_]\w*)", chunk)
                if nm:
                    names.add(nm.group(1).lower())
    return names


def _variable_names_in(stmts) -> Set[str]:
    """Names declared as variables (not procedures) in the file."""
    names: Set[str] = set()
    for _ln, text in stmts:
        m = _TYPE_DECL_RE.match(text)
        if m and not re.search(r"\bexternal\b", m.group("attrs"), re.IGNORECASE):
            for chunk in fscan._split_top_level_commas(m.group("names")):
                nm = re.match(r"^\s*([A-Za-z_]\w*)", chunk)
                if nm:
                    names.add(nm.group(1).lower())
    return names


def _integer_names_in(stmts) -> Set[str]:
    names: Set[str] = set()
    for _ln, text in stmts:
        m = _TYPE_DECL_RE.match(text)
        if m and m.group("type").lower() == "integer":
            for chunk in fscan._split_top_level_commas(m.group("names")):
                nm = re.match(r"^\s*([A-Za-z_]\w*)", chunk)
                if nm:
                    names.add(nm.group(1).lower())
    return names


def _propagate_local_boundaries(lines, stmts, boundary: "_Boundary"):
    """Scoped exclusions, extended to local procedures: a dummy that must
    stay default kind (it reaches a helper's out/inout argument) makes calls
    to its procedure a boundary for that argument, and so on until nothing
    changes. Returns the per-line exclusions."""
    text = "\n".join(_line_eol(ln)[0] for ln in lines)
    units = {u["name"].lower(): u for u in fscan.split_fortran_units_simple(text)
             if u["kind"] in ("subroutine", "function")}
    headers = {}
    for lineno, stmt in stmts:
        m = re.search(r"\b(?:function|subroutine)\s+([A-Za-z_]\w*)", stmt, re.IGNORECASE)
        if m and _HEADER_RE.match(stmt) and m.group(1).lower() in units:
            headers.setdefault(m.group(1).lower(), lineno)
    widened = boundary.__dict__.setdefault("_widened", {})
    for _round in range(20):
        excluded_by_line = _scoped_exclusions(stmts, boundary)
        changed = False
        for name, unit in units.items():
            lineno = headers.get(name)
            if lineno is None:
                continue
            if name in boundary.sigs and name not in boundary.__dict__.get("_local", {}):
                continue  # a helper of the same name
            dummies = _unit_dummies(unit)
            kept = excluded_by_line.get(lineno, set())
            # Dummies that are widened, for converting default-kind actuals.
            widened[name] = [dict(d, int=d["int"] and d["name"] not in kept) for d in dummies]
            sig = [dict(d, int=d["int"] and d["name"] in kept) for d in dummies]
            if not any(d["int"] for d in sig):
                continue
            local = boundary.__dict__.setdefault("_local", {})
            if local.get(name) != sig:
                local[name] = sig
                boundary.sigs[name] = [sig]
                changed = True
        if not changed:
            return excluded_by_line
    return excluded_by_line


# Integer-result intrinsics that take an optional KIND argument. Without one
# they return a default integer, which then mismatches widened integers in
# array constructors and actual arguments ([size(w), 3_ikind]).
_KIND_INTRINSICS = (
    "size", "len", "len_trim", "index", "scan", "verify", "count", "lbound", "ubound", "shape",
    "minloc", "maxloc", "findloc", "iachar", "ichar", "nint", "floor", "ceiling",
)
_KIND_INTRINSIC_RE = re.compile(r"\b(" + "|".join(_KIND_INTRINSICS) + r")\s*\(", re.IGNORECASE)


def _widen_kind_intrinsics_in_code(code: str, defined: Set[str]) -> str:
    """Add `kind=ikind` to calls of _KIND_INTRINSICS that have no kind
    argument, unless the file defines a procedure or variable of that name.
    Helper-call arguments are converted back afterward where needed."""
    out: List[str] = []
    pos = 0
    for m in _KIND_INTRINSIC_RE.finditer(code):
        if m.start() < pos:
            continue
        if m.start() > 0 and (code[m.start() - 1].isalnum() or code[m.start() - 1] in "_%"):
            continue
        if m.group(1).lower() in defined:
            continue
        before = code[:m.start()]
        if before.count("'") % 2 or before.count('"') % 2:
            continue
        close = _match_paren(code, m.end() - 1)
        if close is None:
            continue
        inner = code[m.end():close]
        args = fscan._split_top_level_commas(inner)
        if not args or any(re.match(r"^\s*kind\s*=", a, re.IGNORECASE) for a in args):
            continue
        out.append(code[pos:close])
        out.append(", kind=ikind")
        pos = close
    out.append(code[pos:])
    return "".join(out)


def _use_narrow_int(lines: List[str]) -> List[str]:
    """Make python_mod's narrow_int visible in each module/program unit that
    calls it: add it to the unit's `use python_mod, only:` list, or add
    that use statement after the unit's first line."""
    out = list(lines)
    i = 0
    while i < len(out):
        m = _UNIT_OPEN_RE.match(_split_code_comment(out[i])[0])
        if m is None:
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
        unit = out[i:j]
        if any(re.search(r"\bnarrow_int\s*\(", _split_code_comment(ln)[0], re.IGNORECASE) for ln in unit):
            spec_end = next((k for k, ln in enumerate(unit)
                             if re.match(r"^\s*contains\b", _split_code_comment(ln)[0], re.IGNORECASE)), len(unit))
            use_k = next((k for k in range(1, spec_end)
                          if re.match(r"^\s*use\s+python_mod\s*,\s*only\s*:", _split_code_comment(unit[k])[0],
                                      re.IGNORECASE)), None)
            eol = "\n" if out[i].endswith("\n") else ""
            if use_k is not None:
                # Continued `use` lists end on the last physical line.
                last = use_k
                while _split_code_comment(_line_eol(unit[last])[0])[0].rstrip().endswith("&") and last + 1 < spec_end:
                    last += 1
                body, e = _line_eol(unit[last])
                code, comment = _split_code_comment(body)
                if not re.search(r"\bnarrow_int\b", " ".join(unit[use_k:last + 1]), re.IGNORECASE):
                    unit[last] = code.rstrip() + ", narrow_int" + comment + e
            else:
                indent = "   "
                unit.insert(1, f"{indent}use python_mod, only: narrow_int{eol}")
            out[i:j] = unit  # the unit's `end` line (at j) is not in `unit`
            j = i + len(unit)
        i = j + 1
    return out


def _import_ikind_in_interfaces(lines: List[str]) -> List[str]:
    """An interface body does not see its host's `ikind`: add it to the
    body's `import` statement, or add `import :: ikind`, where it is used."""
    out = list(lines)
    i = 0
    n = len(out)
    while i < n:
        if re.match(r"^\s*(?:abstract\s+)?interface\b", _split_code_comment(out[i])[0], re.IGNORECASE):
            j = i + 1
            body_start = None
            while j < n and not re.match(r"^\s*end\s+interface\b", _split_code_comment(out[j])[0], re.IGNORECASE):
                code = _split_code_comment(out[j])[0]
                if _HEADER_RE.match(code) and not re.match(r"^\s*module\s+procedure\b", code, re.IGNORECASE):
                    body_start = j
                elif re.match(r"^\s*end\s+(?:function|subroutine)\b", code, re.IGNORECASE) and body_start is not None:
                    body = out[body_start:j]
                    if any(re.search(r"\bikind\b", _split_code_comment(b)[0], re.IGNORECASE) for b in body[1:]):
                        imp = next((k for k in range(body_start + 1, j)
                                    if re.match(r"^\s*import\b", _split_code_comment(out[k])[0], re.IGNORECASE)), None)
                        if imp is not None:
                            code_k, comment_k = _split_code_comment(_line_eol(out[imp])[0])
                            _b, eol_k = _line_eol(out[imp])
                            if not re.search(r"\bikind\b", code_k, re.IGNORECASE):
                                if re.match(r"^\s*import\s*$", code_k, re.IGNORECASE):
                                    pass  # a bare `import` already imports everything
                                else:
                                    out[imp] = code_k.rstrip() + ", ikind" + comment_k + eol_k
                        else:
                            hdr = body_start
                            while _split_code_comment(_line_eol(out[hdr])[0])[0].rstrip().endswith("&") and hdr + 1 < j:
                                hdr += 1
                            indent = re.match(r"^(\s*)", out[body_start + 1] if body_start + 1 < j else out[body_start]).group(1)
                            eol = _line_eol(out[hdr])[1] or ("\n" if out[hdr].endswith("\n") else "")
                            out.insert(hdr + 1, f"{indent}import :: ikind{eol}")
                            n += 1
                            j += 1
                    body_start = None
                j += 1
            i = j + 1
            continue
        i += 1
    return out


def add_integer_kind(lines: List[str], kind_name: str) -> List[str]:
    """Rewrite bare `integer` declarations to `integer(kind={kind_name})`
    throughout `lines`, excluding anything passed as an actual argument to
    a known external-boundary call (see module docstring). Returns a new
    list of lines; the input is not mutated."""
    assert kind_name in ("int32", "int64"), kind_name

    stmts = fscan.iter_fortran_statements(lines)
    sigs, bindings = _scan_boundary_signatures()
    # Names without a scanned signature (a test can set the name cache).
    legacy = _scan_external_boundary_calls() - frozenset(sigs)
    boundary = _Boundary(sigs, bindings, legacy)
    if kind_name == "int64":
        # Checked: a value beyond the default range stops the program
        # instead of reaching the helper truncated.
        boundary.narrow = "narrow_int"
    boundary.shadowed = _variable_names_in(stmts)
    excluded_by_line = _propagate_local_boundaries(lines, stmts, boundary)
    file_names = _names_defined_in(stmts)
    int_names = _integer_names_in(stmts)

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
        excluded = excluded_by_line[lineno]
        start_idx = lineno - 1
        if start_idx < consumed_through:
            continue
        out.extend(lines[consumed_through:start_idx])
        end_idx = stmt_last_line(k) - 1

        first_code = _split_code_comment(_line_eol(lines[start_idx])[0])[0]
        indent_m = re.match(r"^(\s*)", first_code)
        indent = indent_m.group(1) if indent_m else ""
        last_body, eol = _line_eol(lines[end_idx])
        _, comment = _split_code_comment(last_body)

        code_line = _widen_bare_int_casts_in_code(f"{indent}{text}")
        code_line = _widen_kind_intrinsics_in_code(code_line, file_names)
        code_line = _suffix_bare_int_literals_in_code(code_line)
        # Arguments of helper calls (and of local procedures whose dummies
        # stayed default kind) are converted back per call.
        if not _HEADER_RE.match(text) and not _TYPE_DECL_RE.match(text):
            code_line = boundary.rewrite(code_line, int_names)
            code_line = _widen_default_actuals(code_line, boundary.__dict__.get("_widened", {}), excluded)
        # ALLOCATE's SOURCE must match the object's kind exactly, unlike
        # ordinary assignment. An excluded integer array still needs its
        # default-kind zero/one initializer, even when extents are widened.
        allocation = re.match(r"^\s*allocate\s*\((.*)\)\s*$", code_line, re.IGNORECASE)
        if allocation:
            parts = fscan._split_top_level_commas(allocation.group(1))
            objects = [p for p in parts if not re.match(r"\w+\s*=", p)]
            if len(objects) == 1:
                obj = re.match(r"([A-Za-z_]\w*)\s*\(", objects[0])
                if obj and obj.group(1).lower() in excluded:
                    code_line = re.sub(r"(\bsource\s*=\s*[+-]?\d+)_ikind\b(?=\s*[,\)])", r"\1", code_line, flags=re.IGNORECASE)
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

    final = _import_ikind_in_interfaces(final)
    if kind_name == "int64":
        final = _use_narrow_int(final)
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
