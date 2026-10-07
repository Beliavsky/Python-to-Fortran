"""numpy's small integer dtypes (int8, int16, uint8, uint16) for xp2f.py.

xp2f.py has one integer kind: an array created with dtype=np.int8 is a
default Fortran integer array. Its values fit, but numpy does int8
arithmetic in int8 and wraps around (np.int8(100) + np.int8(100) is -56),
and astype(np.int8) / np.uint8(x) wrap out-of-range values. This source
pass, run before translation, follows the small-integer dtype of each
expression with numpy 2's promotion rules (a Python int is "weak":
int8 + 5 is int8) and wraps the result of each operation that can leave
the dtype's range:

    int8:  (x + 128) % 256 - 128        uint8: x % 256

so the default-integer values stay exactly numpy's. Reductions that numpy
widens (sum, prod, cumsum, mean) are left alone. Dtypes are followed
within a scope (module body or function); passing a small-integer value
to a local function is an error rather than a silent loss of its dtype.
`a.dtype` and comparisons such as `a.dtype == np.int8` are resolved here
for small-integer arrays.
"""
import ast
import copy

NARROW = {"int8": (8, True), "int16": (16, True), "uint8": (8, False), "uint16": (16, False)}
_ALIASES = {"i1": "int8", "i2": "int16", "u1": "uint8", "u2": "uint16", "byte": "int8", "ubyte": "uint8",
            "short": "int16", "ushort": "uint16", "i4": "int32", "i8": "int64", "int_": "int64", "intp": "int64",
            "u4": "uint32", "u8": "uint64", "f4": "float32", "f8": "float64", "double": "float64",
            "float_": "float64", "c16": "complex128", "c8": "complex64", "bool_": "bool"}
# np.iinfo(T).min / .max / .bits.
_IINFO = {"int8": (-2 ** 7, 2 ** 7 - 1, 8), "int16": (-2 ** 15, 2 ** 15 - 1, 16),
          "int32": (-2 ** 31, 2 ** 31 - 1, 32), "int64": (-2 ** 63, 2 ** 63 - 1, 64),
          "uint8": (0, 2 ** 8 - 1, 8), "uint16": (0, 2 ** 16 - 1, 16), "uint32": (0, 2 ** 32 - 1, 32)}
WEAK = "weak"      # a Python int: takes the other operand's dtype
OTHER = "other"    # anything else (int64, float, bool, unknown)

# Operations that can leave the range (wrapped); the others stay in range.
_WRAP_OPS = (ast.Add, ast.Sub, ast.Mult, ast.Pow, ast.LShift, ast.MatMult, ast.FloorDiv)
_KEEP_OPS = (ast.Mod, ast.RShift, ast.BitAnd, ast.BitOr, ast.BitXor)
# np.<f>(a, ...): result has a's dtype; wrapped / not wrapped.
_NP_SAME_WRAP = {"abs", "absolute", "negative", "square", "diff"}
_NP_SAME = {"max", "min", "amax", "amin", "sort", "unique", "flip", "fliplr", "flipud", "copy", "ravel",
            "reshape", "transpose", "squeeze", "roll", "atleast_1d", "atleast_2d", "asarray", "array",
            "repeat", "tile", "clip", "sign", "rot90", "triu", "tril", "trim_zeros", "expand_dims"}
_NP_COMBINE_WRAP = {"add", "subtract", "multiply", "dot", "matmul", "power", "inner", "outer", "kron"}
_NP_COMBINE = {"minimum", "maximum", "fmin", "fmax"}
_METHOD_SAME = {"max", "min", "copy", "ravel", "flatten", "reshape", "transpose", "squeeze", "repeat", "clip",
                }
_CREATORS = {"array", "asarray", "zeros", "ones", "full", "empty", "arange", "zeros_like", "ones_like",
             "full_like", "empty_like", "fromiter", "frombuffer"}


def dtype_name(node):
    """'int8', ... for np.int8 / numpy.int8 / 'int8' / 'i1', else None."""
    nm = None
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ("np", "numpy"):
        nm = node.attr
    elif isinstance(node, ast.Constant) and isinstance(node.value, str):
        nm = node.value
    nm = _ALIASES.get(nm, nm)
    return nm if nm in NARROW else None


def _any_dtype_name(node):
    """A dtype spelled in the source (narrow or not), for comparisons."""
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in ("np", "numpy"):
        return _ALIASES.get(node.attr, node.attr)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _ALIASES.get(node.value, node.value)
    if isinstance(node, ast.Name) and node.id in ("int", "float", "bool", "complex"):
        return {"int": "int64", "float": "float64", "bool": "bool", "complex": "complex128"}[node.id]
    return None


def promote(a, b):
    if a == OTHER or b == OTHER or a is None or b is None:
        return OTHER
    if a == WEAK:
        return b
    if b == WEAK:
        return a
    if a == b:
        return a
    (ba, sa), (bb, sb) = NARROW[a], NARROW[b]
    if sa == sb:
        return a if ba >= bb else b
    sbits, ubits = (ba, bb) if sa else (bb, ba)
    if sbits > ubits:
        return f"int{sbits}"
    return f"int{2 * ubits}" if 2 * ubits < 32 else OTHER


def wrap(node, dt):
    bits, signed = NARROW[dt]
    m = ast.Constant(value=2 ** bits)
    if not signed:
        return ast.BinOp(left=node, op=ast.Mod(), right=m)
    h = 2 ** (bits - 1)
    inner = ast.BinOp(left=ast.BinOp(left=node, op=ast.Add(), right=ast.Constant(value=h)), op=ast.Mod(), right=m)
    return ast.BinOp(left=inner, op=ast.Sub(), right=ast.Constant(value=h))


def _is_np(func, names):
    return (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
            and func.value.id in ("np", "numpy") and func.attr in names)


class _Scope:
    def __init__(self, funcs, env=None, calls=None):
        self.funcs = funcs          # local function name -> return dtype (or OTHER)
        self.env = dict(env or {})  # name -> dtype (narrow or WEAK)
        self.returns = []
        # Local function name -> per call, {parameter position or name: dtype}.
        self.calls = calls if calls is not None else {}

    # -- expressions ---------------------------------------------------
    def rw(self, e):
        """(rewritten expression, its dtype)."""
        if isinstance(e, ast.Constant):
            if isinstance(e.value, int) and not isinstance(e.value, bool):
                return e, WEAK
            return e, OTHER
        if isinstance(e, ast.Name):
            return e, self.env.get(e.id, OTHER)
        if isinstance(e, ast.BinOp):
            l, dl = self.rw(e.left)
            r, dr = self.rw(e.right)
            e.left, e.right = l, r
            if isinstance(e.op, ast.Div):
                return e, OTHER
            dt = promote(dl, dr)
            if dt in NARROW and isinstance(e.op, _WRAP_OPS):
                return wrap(e, dt), dt
            if dt in NARROW and isinstance(e.op, _KEEP_OPS):
                return e, dt
            return e, dt if dt == WEAK else OTHER
        if isinstance(e, ast.UnaryOp):
            v, dv = self.rw(e.operand)
            e.operand = v
            if isinstance(e.op, ast.Not):
                return e, OTHER
            if dv in NARROW and isinstance(e.op, ast.USub):
                return wrap(e, dv), dv
            return e, dv
        if isinstance(e, ast.IfExp):
            e.test = self.rw(e.test)[0]
            b, db = self.rw(e.body)
            o, do = self.rw(e.orelse)
            e.body, e.orelse = b, o
            return e, promote(db, do)
        if isinstance(e, ast.Subscript):
            v, dv = self.rw(e.value)
            e.value = v
            e.slice = self.rw(e.slice)[0]
            return e, dv if dv in NARROW else OTHER
        if isinstance(e, ast.Attribute):
            iinfo = _iinfo_value(e)
            if iinfo is not None:
                return iinfo, WEAK
            v, dv = self.rw(e.value)
            e.value = v
            if dv in NARROW and e.attr == "dtype":
                return ast.Constant(value=dv), OTHER
            if dv in NARROW and e.attr == "T":
                return e, dv
            return e, OTHER
        if isinstance(e, ast.Compare):
            folded = self._dtype_compare(e)
            if folded is not None:
                return folded, OTHER
            self._generic(e)
            return e, OTHER
        if isinstance(e, ast.Call):
            return self._call(e)
        self._generic(e)
        return e, OTHER

    def _generic(self, e):
        for field, val in ast.iter_fields(e):
            if isinstance(val, ast.expr):
                setattr(e, field, self.rw(val)[0])
            elif isinstance(val, list):
                setattr(e, field, [self.rw(x)[0] if isinstance(x, ast.expr) else self._node(x) for x in val])
            elif isinstance(val, ast.AST):
                self._node(val)

    def _node(self, x):
        if isinstance(x, ast.keyword):
            x.value = self.rw(x.value)[0]
        elif isinstance(x, ast.comprehension):
            x.iter = self.rw(x.iter)[0]
            x.ifs = [self.rw(c)[0] for c in x.ifs]
        return x

    def _dtype_compare(self, e):
        """a.dtype == np.int8 for a small-integer array a: a constant."""
        if len(e.ops) != 1 or not isinstance(e.ops[0], (ast.Eq, ast.NotEq)):
            return None
        left, right = e.left, e.comparators[0]
        for x, y in ((left, right), (right, left)):
            if isinstance(x, ast.Attribute) and x.attr == "dtype":
                dv = self.rw(copy.deepcopy(x.value))[1]
                other = _any_dtype_name(y)
                if other is None:
                    continue
                if dv in NARROW:
                    same = dv == other
                    return ast.Constant(value=same if isinstance(e.ops[0], ast.Eq) else not same)
                # Otherwise x.dtype translates to numpy's name ("int64",
                # "float64", ...): compare it with that name as a string.
                x.value = self.rw(x.value)[0]
                const = ast.Constant(value=other)
                e.left, e.comparators = (x, [const]) if x is left else (const, [x])
                return e
        return None

    def _call(self, e):
        f = e.func
        if isinstance(f, ast.Name) and f.id in ("type", "isinstance"):
            return e, OTHER  # type(np.int16(3)) is about the type itself
        # np.int8(v): truncate to an int, then wrap.
        if isinstance(f, ast.Attribute) and dtype_name(f) and len(e.args) == 1 and not e.keywords:
            dt = dtype_name(f)
            v, _dv = self.rw(e.args[0])
            if not (isinstance(v, ast.Constant) and isinstance(v.value, int)):
                v = ast.Call(func=ast.Name(id="int", ctx=ast.Load()), args=[v], keywords=[])
            return wrap(v, dt), dt
        # x.astype(np.int8)
        if isinstance(f, ast.Attribute) and f.attr == "astype" and len(e.args) == 1 and dtype_name(e.args[0]):
            dt = dtype_name(e.args[0])
            f.value = self.rw(f.value)[0]
            e.args = [ast.Name(id="int", ctx=ast.Load())]
            return wrap(e, dt), dt
        # Creation with a small-integer dtype: a default-integer array.
        if _is_np(f, _CREATORS):
            for kw in e.keywords:
                if kw.arg == "dtype" and dtype_name(kw.value):
                    dt = dtype_name(kw.value)
                    kw.value = ast.Name(id="int", ctx=ast.Load())
                    self._generic(e)
                    return e, dt
        args = []
        dts = []
        for a in e.args:
            na, da = self.rw(a)
            args.append(na)
            dts.append(da)
        e.args = args
        for kw in e.keywords:
            kw.value = self.rw(kw.value)[0]
        if isinstance(f, ast.Attribute):
            f.value, dself = self.rw(f.value)
        else:
            dself = OTHER
        d0 = dts[0] if dts else OTHER
        if _is_np(f, _NP_SAME_WRAP) and d0 in NARROW:
            return wrap(e, d0), d0
        if _is_np(f, _NP_SAME) and d0 in NARROW:
            return e, d0
        if _is_np(f, _NP_COMBINE_WRAP | _NP_COMBINE) and len(dts) >= 2:
            dt = promote(dts[0], dts[1])
            if dt in NARROW:
                return (wrap(e, dt) if f.attr in _NP_COMBINE_WRAP else e), dt
            return e, OTHER
        if _is_np(f, {"where"}) and len(dts) == 3:
            dt = promote(dts[1], dts[2])
            return e, dt if dt in NARROW else OTHER
        if _is_np(f, {"concatenate", "stack", "vstack", "hstack"}) and e.args and isinstance(
                e.args[0], (ast.List, ast.Tuple)):
            ds = [self.rw(copy.deepcopy(x))[1] for x in e.args[0].elts]
            if ds and all(d == ds[0] for d in ds) and ds[0] in NARROW:
                return e, ds[0]
            return e, OTHER
        is_method = isinstance(f, ast.Attribute) and not (
            isinstance(f.value, ast.Name) and f.value.id in ("np", "numpy"))
        if is_method and dself in NARROW:
            if f.attr in _METHOD_SAME:
                return e, dself
            return e, OTHER
        if isinstance(f, ast.Name):
            if f.id == "abs" and d0 in NARROW:
                return wrap(e, d0), d0
            if f.id in ("int", "len") or (f.id in ("abs", "round") and d0 == WEAK):
                return e, WEAK
            if f.id in self.funcs:
                arg_dts = dict(enumerate(dts))
                for kw in e.keywords:
                    if kw.arg is not None:
                        arg_dts[kw.arg] = self.rw(copy.deepcopy(kw.value))[1]
                self.calls.setdefault(f.id, []).append(arg_dts)
                return e, self.funcs[f.id]
        return e, OTHER

    # -- statements ----------------------------------------------------
    def body(self, stmts):
        out = []
        for st in stmts:
            r = self.stmt(st)
            out.extend(r if isinstance(r, list) else [r])
        return out

    @staticmethod
    def _merge(envs):
        """Join point: a name keeps a small-integer dtype only if no path
        gives it another one (a path that does not assign it does not count)."""
        merged = {}
        for n in set().union(*[set(e) for e in envs]):
            ds = {e[n] for e in envs if n in e}
            narrow = {d for d in ds if d in NARROW}
            if narrow and len(ds) > 1 and ds != narrow | {WEAK}:
                raise NotImplementedError(
                    f"{n} is {sorted(narrow)[0]} on one path and another dtype on another; a small-integer "
                    "dtype must be the same on every path")
            if len(narrow) > 1:
                raise NotImplementedError(f"{n} is {' or '.join(sorted(narrow))} on different paths")
            merged[n] = narrow.pop() if narrow else (WEAK if ds == {WEAK} else OTHER)
        return merged

    def _branch(self, stmts):
        s = _Scope(self.funcs, self.env, self.calls)
        out = s.body(stmts)
        self.returns.extend(s.returns)
        return out, s.env

    def _loop_env(self, stmts, setup=None):
        """Settle the dtypes a loop body leaves behind (two dry runs)."""
        for _ in range(2):
            s = _Scope(self.funcs, self.env, {})
            if setup:
                setup(s)
            s.body(copy.deepcopy(stmts))
            self.env = self._merge([self.env, s.env])

    def _assign_name(self, name, dt):
        self.env[name] = dt if dt in NARROW or dt == WEAK else OTHER

    def stmt(self, st):
        if isinstance(st, ast.FunctionDef):
            return st  # handled by rewrite_small_int_dtypes
        if isinstance(st, ast.Assign):
            st.value, dt = self.rw(st.value)
            for t in st.targets:
                if isinstance(t, ast.Name):
                    self._assign_name(t.id, dt)
                elif isinstance(t, ast.Subscript):
                    t.value, dbase = self.rw(t.value)
                    t.slice = self.rw(t.slice)[0]
                    if dbase in NARROW and dt != dbase and dt != OTHER:
                        st.value = wrap(st.value, dbase)
                elif isinstance(t, (ast.Tuple, ast.List)):
                    for x in ast.walk(t):
                        if isinstance(x, ast.Name):
                            self.env[x.id] = OTHER
            return st
        if isinstance(st, ast.AnnAssign) and st.value is not None:
            st.value, dt = self.rw(st.value)
            if isinstance(st.target, ast.Name):
                self._assign_name(st.target.id, dt)
            return st
        if isinstance(st, ast.AugAssign):
            tgt_load = copy.deepcopy(st.target)
            for x in ast.walk(tgt_load):
                if hasattr(x, "ctx"):
                    x.ctx = ast.Load()
            _t, dtgt = self.rw(copy.deepcopy(tgt_load))
            if dtgt in NARROW:
                val, _dv = self.rw(st.value)
                if isinstance(st.op, _KEEP_OPS) and _dv in (dtgt, WEAK):
                    st.value = val
                    return st
                expr = ast.BinOp(left=tgt_load, op=st.op, right=val)
                if isinstance(st.op, ast.Div):
                    raise NotImplementedError(f"true division in place on an {dtgt} array is not supported")
                new = ast.Assign(targets=[st.target], value=wrap(expr, dtgt))
                return ast.copy_location(new, st)
            st.value, dv = self.rw(st.value)
            if isinstance(st.target, ast.Name):
                self._assign_name(st.target.id, promote(dtgt, dv) if dtgt == WEAK else OTHER)
            return st
        if isinstance(st, ast.For):
            st.iter, dit = self.rw(st.iter)
            is_range = isinstance(st.iter, ast.Call) and isinstance(st.iter.func, ast.Name) and \
                st.iter.func.id == "range"
            tdt = WEAK if is_range else (dit if dit in NARROW else OTHER)

            def setup(s):
                if isinstance(st.target, ast.Name):
                    s._assign_name(st.target.id, tdt)
            self._loop_env(st.body, setup)
            setup(self)
            body, env = self._branch(st.body)
            st.body = body
            self.env = self._merge([self.env, env])
            st.orelse = self.body(st.orelse)
            return st
        if isinstance(st, ast.While):
            self._loop_env(st.body)
            st.test = self.rw(st.test)[0]
            body, env = self._branch(st.body)
            st.body = body
            self.env = self._merge([self.env, env])
            st.orelse = self.body(st.orelse)
            return st
        if isinstance(st, ast.If):
            st.test = self.rw(st.test)[0]
            b, eb = self._branch(st.body)
            o, eo = self._branch(st.orelse)
            st.body, st.orelse = b, o
            self.env = self._merge([eb, eo])
            return st
        if isinstance(st, ast.Return):
            if st.value is not None:
                st.value, dt = self.rw(st.value)
                self.returns.append(dt)
            return st
        if isinstance(st, (ast.With, ast.Try)):
            for field in ("body", "orelse", "finalbody"):
                if isinstance(getattr(st, field, None), list):
                    setattr(st, field, self.body(getattr(st, field)))
            for h in getattr(st, "handlers", []):
                h.body = self.body(h.body)
            return st
        if isinstance(st, ast.ClassDef):
            return st
        self._generic(st)
        return st


def _iinfo_value(e):
    """np.iinfo(T).min/.max/.bits as a constant, or None."""
    c = e.value
    if not (e.attr in ("min", "max", "bits") and isinstance(c, ast.Call) and _is_np(c.func, {"iinfo"})
            and len(c.args) == 1):
        return None
    nm = _any_dtype_name(c.args[0])
    if nm not in _IINFO:
        if nm == "uint64":
            raise NotImplementedError("np.iinfo(np.uint64) is not supported (its max exceeds int64)")
        return None
    lo, hi, bits = _IINFO[nm]
    v = {"min": lo, "max": hi, "bits": bits}[e.attr]
    if v in (-2 ** 31, -2 ** 63):
        # -2147483647 - 1: the literal 2147483648 alone overflows its kind.
        return ast.BinOp(left=ast.UnaryOp(op=ast.USub(), operand=ast.Constant(value=-v - 1)), op=ast.Sub(),
                         right=ast.Constant(value=1))
    return ast.Constant(value=v)


def _mentions_small_int(tree):
    for n in ast.walk(tree):
        if isinstance(n, ast.Attribute) and n.attr in ("iinfo", "dtype"):
            return True
        if isinstance(n, ast.Attribute) and _ALIASES.get(n.attr, n.attr) in NARROW:
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and _ALIASES.get(n.value, n.value) in NARROW:
            return True
    return False


def _param_dtypes(fdef, calls, strict=True):
    """Parameter name -> small-integer dtype passed by every call (with
    strict=False, by any call: the dry runs before the dtypes settle)."""
    names = [a.arg for a in fdef.args.args]
    out = {}
    for pos, nm in enumerate(names):
        ds = set()
        for c in calls:
            ds.add(c.get(pos, c.get(nm, OTHER)))
        narrow = {d for d in ds if d in NARROW}
        if not narrow:
            if ds == {WEAK}:
                out[nm] = WEAK  # only ever a Python int
            continue
        if len(narrow) > 1 or (strict and len(ds) > 1):
            raise NotImplementedError(
                f"function {fdef.name} is called with {' and '.join(sorted(ds - {WEAK, OTHER}) + (['other dtypes'] if ds - narrow else []))} "
                f"for {nm}; a small-integer dtype must be the same at every call")
        out[nm] = narrow.pop()
    return out


def rewrite_small_int_dtypes(tree):
    if not _mentions_small_int(tree):
        return tree
    defs = [st for st in ast.walk(tree) if isinstance(st, ast.FunctionDef)]
    funcs = {d.name: OTHER for d in defs}
    params = {d.name: {} for d in defs}
    # Dry runs: a parameter takes a small-integer dtype when every call
    # passes that dtype; a function returning one dtype passes it on.
    def dry_run():
        calls = {}
        for d in defs:
            s = _Scope(funcs, params[d.name], calls)
            s.body(copy.deepcopy(d.body))
            rets = set(s.returns)
            funcs[d.name] = rets.pop() if len(rets) == 1 and rets <= set(NARROW) else OTHER
        _Scope(funcs, None, calls).body(copy.deepcopy(tree.body))
        return calls

    for _round in range(len(defs) + 2):
        calls = dry_run()
        new = {d.name: _param_dtypes(d, calls.get(d.name, []), strict=False) for d in defs}
        if new == params:
            break
        params = new
    calls = dry_run()
    for d in defs:
        _param_dtypes(d, calls.get(d.name, []))
    for d in defs:
        s = _Scope(funcs, params[d.name])
        d.body = s.body(d.body)
    top = _Scope(funcs)
    tree.body = top.body(tree.body)
    ast.fix_missing_locations(tree)
    return tree
