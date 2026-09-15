"""Infer and inject pyccel-compatible type annotations into an
unannotated (or partially-annotated) Python script's top-level
function definitions.

Motivation: pyccel requires argument type annotations to translate a
function (it does no whole-program inference across call sites);
xp2f.py does not (see xp2f.py's own inference machinery), but it DOES
already accept pyccel's own annotation syntax as input -- plain scalar
annotations (`x: int`, `x: float`) and string array annotations
(`x: "float[:,:]"`). So a single annotated copy of a script can serve
as input to BOTH tools, letting their translations be cross-checked
against each other (and against plain Python) from the same source.

This script deliberately does NOT reuse xp2f.py's own inference code:
that machinery is deeply entangled with Fortran-emission decisions and
has its own share of Fortran-motivated heuristic shortcuts (some found
to be outright wrong for a couple of specific contexts). This is a
fresh, independent, deliberately conservative inference pass whose
only job is producing correct pyccel annotations -- it would rather
leave a parameter unannotated (and say so) than guess wrong.

Scope (matches the "cross-validate specific scripts" use case, not a
general-purpose bulletproof pipeline):
  - Only top-level (module-scope) function defs are annotated; nested
    functions, methods, and classes are left untouched.
  - Only direct, module-level `f(...)` calls (by the function's own
    bare name) are considered call sites -- not calls through an
    alias, not calls where `f` is itself passed as a callback.
  - `*args`/`**kwargs` parameters are left unannotated.
  - An existing annotation on a parameter or return is never
    overwritten.
  - Only scalar kinds (bool/int/float/complex/str) and NumPy array
    rank/dtype (via literal shapes, np.zeros/ones/full/empty/array
    calls, and simple call-site array literals) are inferred.

Usage:
    python xannotate_for_pyccel.py script.py [-o output.py] [--verbose]

Prints a summary of what was annotated and what was left alone (and
why) to stderr.
"""

from __future__ import annotations

import argparse
import ast
import sys
from typing import Dict, List, Optional, Tuple

# A type descriptor is (kind, rank, width) where:
#   kind:  "bool" | "int" | "float" | "complex" | "str" | None (unknown)
#   rank:  0 for scalar, 1/2/3/... for array
#   width: 32 | 64 | None (bit width for numeric kinds; None = default)
TypeDesc = Tuple[Optional[str], int, Optional[int]]

UNKNOWN: TypeDesc = (None, 0, None)

_KIND_WIDEN_ORDER = ["bool", "int", "float", "complex"]


def _widen_kind(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if a is None:
        return b
    if b is None:
        return a
    if a == b:
        return a
    if a == "str" or b == "str":
        return None  # str can't widen with a numeric kind
    ia = _KIND_WIDEN_ORDER.index(a) if a in _KIND_WIDEN_ORDER else -1
    ib = _KIND_WIDEN_ORDER.index(b) if b in _KIND_WIDEN_ORDER else -1
    if ia < 0 or ib < 0:
        return None
    return _KIND_WIDEN_ORDER[max(ia, ib)]


def _widen_width(a: Optional[int], b: Optional[int]) -> Optional[int]:
    if a is None or b is None:
        return None
    return max(a, b)


def _widen(a: TypeDesc, b: TypeDesc) -> TypeDesc:
    ka, ra, wa = a
    kb, rb, wb = b
    if ra != rb:
        # Rank mismatch across call sites -- genuinely ambiguous, give up.
        return UNKNOWN
    k = _widen_kind(ka, kb)
    w = _widen_width(wa, wb)
    return (k, ra, w)


def _is_numpy_root(node: ast.AST, numpy_names: set) -> bool:
    return isinstance(node, ast.Name) and node.id in numpy_names


def _dtype_kw_to_desc(node: ast.expr) -> Tuple[Optional[str], Optional[int]]:
    """Infer (kind, width) from a `dtype=...` keyword's value node."""
    name = None
    if isinstance(node, ast.Attribute):
        name = node.attr
    elif isinstance(node, ast.Name):
        name = node.id
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        name = node.value
    if name is None:
        return (None, None)
    name = name.lower()
    table = {
        "float64": ("float", 64), "double": ("float", 64), "float_": ("float", 64),
        "float32": ("float", 32), "single": ("float", 32),
        "int64": ("int", 64), "int_": ("int", 64), "int": ("int", 64), "long": ("int", 64),
        "int32": ("int", 32),
        "int16": ("int", 32), "int8": ("int", 32),
        "complex128": ("complex", 64), "complex_": ("complex", 64),
        "complex64": ("complex", 32),
        "bool": ("bool", None), "bool_": ("bool", None),
    }
    return table.get(name, (None, None))


class Inferrer:
    """Infers TypeDescs for AST expression nodes, given a small table of
    already-known variable types (module-level and per-function-local)."""

    def __init__(self, numpy_names: set):
        self.numpy_names = numpy_names

    def infer(self, node: ast.expr, known: Dict[str, TypeDesc]) -> TypeDesc:
        if node is None:
            return UNKNOWN
        if isinstance(node, ast.Constant):
            v = node.value
            if isinstance(v, bool):
                return ("bool", 0, None)
            if isinstance(v, int):
                return ("int", 0, 64)
            if isinstance(v, float):
                return ("float", 0, 64)
            if isinstance(v, complex):
                return ("complex", 0, 64)
            if isinstance(v, str):
                return ("str", 0, None)
            return UNKNOWN
        if isinstance(node, ast.UnaryOp):
            return self.infer(node.operand, known)
        if isinstance(node, ast.BinOp):
            return _widen(self.infer(node.left, known), self.infer(node.right, known))
        if isinstance(node, ast.Name):
            return known.get(node.id, UNKNOWN)
        if isinstance(node, (ast.List, ast.Tuple)):
            return self._infer_literal_array(node, known)
        if isinstance(node, ast.Call):
            return self._infer_call(node, known)
        return UNKNOWN

    def _infer_literal_array(self, node, known: Dict[str, TypeDesc]) -> TypeDesc:
        if not node.elts:
            return UNKNOWN
        if all(isinstance(e, (ast.List, ast.Tuple)) for e in node.elts):
            inner = self._infer_literal_array(node.elts[0], known)
            for e in node.elts[1:]:
                inner = _widen(inner, self._infer_literal_array(e, known))
            if inner[0] is None:
                return UNKNOWN
            return (inner[0], inner[1] + 1, inner[2])
        kind, width = None, None
        for e in node.elts:
            k, r, w = self.infer(e, known)
            if r != 0:
                return UNKNOWN
            kind = _widen_kind(kind, k)
            width = _widen_width(width, w) if (width is not None and w is not None) else (width or w)
        return (kind, 1, width)

    def _infer_call(self, node: ast.Call, known: Dict[str, TypeDesc]) -> TypeDesc:
        func = node.func
        if isinstance(func, ast.Attribute) and _is_numpy_root(func.value, self.numpy_names):
            attr = func.attr
            if attr in {"zeros", "ones", "empty", "full"} and node.args:
                shape_node = node.args[0]
                if isinstance(shape_node, (ast.List, ast.Tuple)):
                    rank = max(1, len(shape_node.elts))
                elif isinstance(shape_node, ast.Constant) and isinstance(shape_node.value, int):
                    rank = 1
                else:
                    rank = 1
                kind, width = "float", 64
                for kw in node.keywords:
                    if kw.arg == "dtype":
                        k2, w2 = _dtype_kw_to_desc(kw.value)
                        if k2:
                            kind, width = k2, w2
                if attr == "full" and len(node.args) >= 2:
                    fk, fr, fw = self.infer(node.args[1], known)
                    if fk and not any(kw.arg == "dtype" for kw in node.keywords):
                        kind, width = fk, fw
                return (kind, rank, width)
            if attr == "array" and node.args:
                inner = self.infer(node.args[0], known)
                kind, rank, width = inner
                for kw in node.keywords:
                    if kw.arg == "dtype":
                        k2, w2 = _dtype_kw_to_desc(kw.value)
                        if k2:
                            kind, width = k2, w2
                if rank == 0:
                    rank = 1  # np.array(scalar_list_like) -- be safe, treat as unknown-shape
                return (kind, rank, width)
            if attr == "arange" and node.args:
                kind, width = "int", 64
                if any(isinstance(a, ast.Constant) and isinstance(a.value, float) for a in node.args):
                    kind, width = "float", 64
                for kw in node.keywords:
                    if kw.arg == "dtype":
                        k2, w2 = _dtype_kw_to_desc(kw.value)
                        if k2:
                            kind, width = k2, w2
                return (kind, 1, width)
            if attr == "linspace":
                return ("float", 1, 64)
        return UNKNOWN


def _collect_numpy_names(tree: ast.Module) -> set:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "numpy":
                    names.add(alias.asname or "numpy")
    return names


def _iter_module_scope_nodes(tree: ast.Module):
    """Like ast.walk, but never descends into a function/class's own
    body -- yields only genuine module-scope nodes (including inside
    module-level `if`/`for`/`while`/`try`/`with` blocks, e.g. the
    `if __name__ == "__main__":` guard). Keeping this separate from a
    per-function local-variable table (see `func_locals` in
    annotate_source) matters: without it, a plain whole-file
    `ast.walk` would also sweep up OTHER functions' own local
    variables under the same flat namespace, risking a wrong
    cross-function name collision (e.g. two different functions each
    having their own, differently-typed local `x`)."""
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        yield node
        stack.extend(ast.iter_child_nodes(node))


def _collect_module_level_var_types(tree: ast.Module, inf: Inferrer) -> Dict[str, TypeDesc]:
    known: Dict[str, TypeDesc] = {}
    # Two passes: literals/no-dependency first, then anything referencing
    # already-known names, iterated to a fixed point (small file, cheap).
    assigns = []
    for node in _iter_module_scope_nodes(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            assigns.append((node.targets[0].id, node.value))
    for _ in range(3):
        changed = False
        for name, value in assigns:
            d = inf.infer(value, known)
            if d != UNKNOWN and known.get(name, UNKNOWN) != d:
                known[name] = d
                changed = True
        if not changed:
            break
    return known


def _call_context_map(tree: ast.Module) -> Dict[int, Optional[str]]:
    """Maps id(call_node) -> the name of the top-level function whose
    body directly contains that call, or None for a call at module
    scope. Needed so a call's actual-argument expressions can be
    resolved against the CALLING function's own parameters/locals
    (e.g. `find_nearest(nv, mind, connected)` inside `dijkstra_distance`
    needs dijkstra_distance's own `mind` parameter's type, not just
    whatever's known at module level)."""
    ctx: Dict[int, Optional[str]] = {}
    for node in _iter_module_scope_nodes(tree):
        if isinstance(node, ast.Call):
            ctx[id(node)] = None
    for fn in tree.body:
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    ctx[id(node)] = fn.name
    return ctx


def _desc_to_annotation(desc: TypeDesc) -> Optional[str]:
    kind, rank, width = desc
    if kind is None:
        return None
    base = kind
    if kind in {"int", "float", "complex"} and width == 32:
        base = {"int": "int32", "float": "float32", "complex": "complex64"}[kind]
    elif kind in {"int", "float", "complex"} and width == 64:
        base = {"int": "int", "float": "float", "complex": "complex"}[kind]
    if rank == 0:
        return base  # bare (unquoted) scalar annotation
    dims = ",".join(":" for _ in range(rank))
    return repr(f"{base}[{dims}]")


def _build_call_actuals_by_position(
    call: ast.Call, param_names: List[str]
) -> Dict[int, ast.expr]:
    actuals: Dict[int, ast.expr] = {}
    for i, a in enumerate(call.args):
        if i < len(param_names):
            actuals[i] = a
    for kw in call.keywords:
        if kw.arg is not None and kw.arg in param_names:
            actuals[param_names.index(kw.arg)] = kw.value
    return actuals


def _default_arg_descs(args: ast.arguments, inf: Inferrer, known: Dict[str, TypeDesc]) -> Dict[int, TypeDesc]:
    # A defaulted parameter that no call site ever supplies explicitly
    # (every call relies on its default): the default literal itself is
    # direct, unambiguous evidence of the intended type (e.g.
    # `def f1(x, n=2, m=3)` called only as `f1(1)` -- n/m are always
    # 2/3, so "int" is not a guess). Positional defaults only apply to
    # the trailing `args.args`; kwonlyargs pair 1:1 with kw_defaults
    # (None = no default there).
    default_by_pos: Dict[int, ast.expr] = {}
    n_no_default = len(args.args) - len(args.defaults)
    for j, d in enumerate(args.defaults):
        default_by_pos[n_no_default + j] = d
    for j, d in enumerate(args.kw_defaults):
        if d is not None:
            default_by_pos[len(args.args) + j] = d
    out: Dict[int, TypeDesc] = {}
    for i, d_node in default_by_pos.items():
        dd = inf.infer(d_node, known)
        if dd != UNKNOWN:
            out[i] = dd
    return out


def _is_multi_value_return(fn) -> bool:
    """True if any `return` in fn's body returns a bare tuple of 2+
    elements (`return a, b`) -- Python's multi-value-return idiom, NOT
    an array literal. This must never go through the general array-
    literal inference path (which would misread `return d, v` as a
    rank-1 array of d's/v's own scalar kind)."""
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Return)
            and isinstance(node.value, ast.Tuple)
            and len(node.value.elts) >= 2
        ):
            return True
    return False


def _detect_eol(source: str) -> str:
    """The file's own dominant line-ending style, so a rewritten `def`
    header's newline matches -- writing a bare "\\n" into a file that
    otherwise uses "\\r\\n" (or vice versa) would silently mix line
    endings within one file."""
    crlf = source.count("\r\n")
    lf_only = source.count("\n") - crlf
    return "\r\n" if crlf >= lf_only and crlf > 0 else "\n"


def annotate_source(source: str, verbose: bool = False) -> str:
    tree = ast.parse(source)
    eol = _detect_eol(source)
    lines = source.splitlines(keepends=True)
    numpy_names = _collect_numpy_names(tree)
    inf = Inferrer(numpy_names)
    module_known = _collect_module_level_var_types(tree, inf)
    call_ctx = _call_context_map(tree)

    top_fns = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    fn_by_name = {fn.name: fn for fn in top_fns}
    param_names_by_fn: Dict[str, List[str]] = {}
    param_nodes_by_fn: Dict[str, List[ast.arg]] = {}
    report: List[str] = []
    for fn in top_fns:
        args = fn.args
        if args.vararg is not None or args.kwarg is not None:
            report.append(f"{fn.name}: skipped (uses *args/**kwargs)")
            continue
        pnodes = list(args.args) + list(args.kwonlyargs)
        param_names_by_fn[fn.name] = [a.arg for a in pnodes]
        param_nodes_by_fn[fn.name] = pnodes

    all_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    calls_by_target: Dict[str, List[ast.Call]] = {}
    for c in all_calls:
        calls_by_target.setdefault(c.func.id, []).append(c)

    # func_locals[fname]: this function's OWN best-known variable types
    # (its own parameters, once resolved, plus its own body-local
    # assignments) -- kept separate per function so that two different
    # functions' same-named locals never collide. Resolving a call's
    # actual arguments needs the CALLING function's own func_locals
    # entry (see call_ctx above), and a function's own locals need its
    # OWN params resolved first -- a genuine mutual dependency across
    # the call graph, so this is iterated to a fixed point rather than
    # computed in one pass.
    func_locals: Dict[str, Dict[str, TypeDesc]] = {name: {} for name in param_names_by_fn}
    inferred_by_pos_by_fn: Dict[str, Dict[int, TypeDesc]] = {}

    def _context_known(ctx_name: Optional[str]) -> Dict[str, TypeDesc]:
        if ctx_name is None or ctx_name not in func_locals:
            return module_known
        merged = dict(module_known)
        merged.update(func_locals[ctx_name])
        return merged

    for _round in range(6):
        changed = False
        for fname, pnames in param_names_by_fn.items():
            fn = fn_by_name[fname]
            calls = calls_by_target.get(fname, [])
            inferred_by_pos: Dict[int, TypeDesc] = {}
            for call in calls:
                actuals = _build_call_actuals_by_position(call, pnames)
                ctx_known = _context_known(call_ctx.get(id(call)))
                for i, a in actuals.items():
                    d = inf.infer(a, ctx_known)
                    inferred_by_pos[i] = (
                        _widen(inferred_by_pos[i], d) if i in inferred_by_pos else d
                    )
            for i, d in _default_arg_descs(fn.args, inf, module_known).items():
                if i not in inferred_by_pos:
                    inferred_by_pos[i] = d
            inferred_by_pos_by_fn[fname] = inferred_by_pos

            new_local: Dict[str, TypeDesc] = {}
            for i, a in enumerate(param_nodes_by_fn[fname]):
                d = inferred_by_pos.get(i, UNKNOWN)
                if d != UNKNOWN:
                    new_local[a.arg] = d
            for _ in range(3):
                local_changed = False
                for node in ast.walk(fn):
                    if (
                        isinstance(node, ast.Assign)
                        and len(node.targets) == 1
                        and isinstance(node.targets[0], ast.Name)
                    ):
                        ctx_known = dict(module_known)
                        ctx_known.update(new_local)
                        d = inf.infer(node.value, ctx_known)
                        if d != UNKNOWN and new_local.get(node.targets[0].id, UNKNOWN) != d:
                            new_local[node.targets[0].id] = d
                            local_changed = True
                if not local_changed:
                    break

            if new_local != func_locals.get(fname, {}):
                changed = True
            func_locals[fname] = new_local
        if not changed:
            break

    edits: List[Tuple[int, int, str]] = []

    for fname, param_nodes in param_nodes_by_fn.items():
        fn = fn_by_name[fname]
        calls = calls_by_target.get(fname, [])
        inferred_by_pos = inferred_by_pos_by_fn.get(fname, {})
        local_known = dict(module_known)
        local_known.update(func_locals.get(fname, {}))

        new_param_annotations: Dict[str, str] = {}
        for i, a in enumerate(param_nodes):
            if a.annotation is not None:
                continue
            desc = inferred_by_pos.get(i, UNKNOWN)
            ann = _desc_to_annotation(desc)
            if ann is not None:
                new_param_annotations[a.arg] = ann
                report.append(f"{fname}({a.arg}): annotated as {ann}")
            else:
                reason = "never called" if not calls else "ambiguous/unknown call-site type(s)"
                report.append(f"{fname}({a.arg}): left unannotated ({reason})")

        new_return_annotation = None
        if fn.returns is None:
            if _is_multi_value_return(fn):
                report.append(
                    f"{fname}() -> return left unannotated (multi-value tuple return -- not attempted)"
                )
            else:
                return_descs = []
                for node in ast.walk(fn):
                    if isinstance(node, ast.Return) and node.value is not None:
                        return_descs.append(inf.infer(node.value, local_known))
                if return_descs:
                    combined = return_descs[0]
                    for d in return_descs[1:]:
                        combined = _widen(combined, d)
                    ann = _desc_to_annotation(combined)
                    if ann is not None:
                        new_return_annotation = ann
                        report.append(f"{fname}() -> annotated return as {ann}")
                    else:
                        report.append(f"{fname}() -> return left unannotated (ambiguous/unknown)")

        if not new_param_annotations and new_return_annotation is None:
            continue

        edits.append(
            _rewrite_def_header(
                fn, lines, new_param_annotations, new_return_annotation, eol
            )
        )

    edits.sort(key=lambda e: e[0])
    out_lines = list(lines)
    for start0, end0, new_text in reversed(edits):
        out_lines[start0:end0] = [new_text]
    result = "".join(out_lines)

    if verbose or True:
        for line in report:
            print("  " + line, file=sys.stderr)
    return result


def _fmt_arg(a: ast.arg, new_annotations: Dict[str, str]) -> str:
    if a.arg in new_annotations:
        return f"{a.arg}: {new_annotations[a.arg]}"
    if a.annotation is not None:
        return f"{a.arg}: {ast.unparse(a.annotation)}"
    return a.arg


def _rewrite_def_header(
    fn,
    lines: List[str],
    new_param_annotations: Dict[str, str],
    new_return_annotation: Optional[str],
    eol: str = "\n",
) -> Tuple[int, int, str]:
    """Rebuild just this function's `def ...:` header (which may span
    several source lines) as a single new line, preserving defaults,
    positional-only/keyword-only markers, and any annotations the
    source already had. Everything else in the file (the body, blank
    lines, comments elsewhere) is left untouched."""
    args = fn.args
    parts: List[str] = []
    defaults = list(args.defaults)
    pos_args = list(args.args)
    n_no_default = len(pos_args) - len(defaults)
    for i, a in enumerate(pos_args):
        s = _fmt_arg(a, new_param_annotations)
        if i >= n_no_default:
            default_node = defaults[i - n_no_default]
            s += f" = {ast.unparse(default_node)}"
        parts.append(s)
    if args.kwonlyargs:
        parts.append("*")
        for a, d in zip(args.kwonlyargs, args.kw_defaults):
            s = _fmt_arg(a, new_param_annotations)
            if d is not None:
                s += f" = {ast.unparse(d)}"
            parts.append(s)
    header = f"def {fn.name}(" + ", ".join(parts) + ")"
    if new_return_annotation is not None:
        header += f" -> {new_return_annotation}"
    elif fn.returns is not None:
        header += f" -> {ast.unparse(fn.returns)}"
    header += ":" + eol

    # Determine the header's own source line span: from `def` up to (and
    # including) the colon that starts the body, found via the first
    # body statement's own line number (the colon+newline right before it).
    start0 = fn.lineno - 1
    first_body_lineno = fn.body[0].lineno
    end0 = first_body_lineno - 1
    # Preserve a docstring-only special case: if the body's first
    # statement starts on the same physical line as part of a one-liner
    # `def f(): return x`, fall back to not touching it (too risky to
    # rewrite safely as a single header line).
    if end0 <= start0 and "\n" not in "".join(lines[start0:start0 + 1]):
        pass
    indent = lines[start0][: len(lines[start0]) - len(lines[start0].lstrip())]
    return (start0, max(end0, start0 + 1), indent + header)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("input", help="Python script to annotate")
    ap.add_argument("-o", "--out", default=None, help="Output path (default: <stem>_annotated.py)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    # newline="" on both read and write disables Python's universal-
    # newline translation entirely, so the file's own original line
    # endings (LF or CRLF) are read verbatim and, since annotate_source
    # matches any newly-inserted line to that same detected style,
    # written back out exactly as they were -- rather than silently
    # normalizing (or platform-translating) them.
    with open(args.input, "r", encoding="utf-8", newline="") as f:
        source = f.read()

    print(f"Inferring annotations for {args.input}:", file=sys.stderr)
    result = annotate_source(source, verbose=args.verbose)

    out_path = args.out
    if out_path is None:
        if args.input.endswith(".py"):
            out_path = args.input[: -len(".py")] + "_annotated.py"
        else:
            out_path = args.input + "_annotated.py"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write(result)
    print(f"wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
