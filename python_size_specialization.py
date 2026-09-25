"""Bounded specialization of singleton-unwrapping NumPy functions.

This is deliberately not general value-dependent return-type inference. Unknown
sizes remain untouched, so the normal translator can issue its diagnostic.
"""
import ast
import copy


def _name(node, name):
    return isinstance(node, ast.Name) and node.id == name


def _numpy_call(node, aliases, name):
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in aliases and node.func.attr == name)


def _size_of(node, name):
    return (isinstance(node, ast.Call) and _name(node.func, 'len')
            and len(node.args) == 1 and _name(node.args[0], name)) or (
        isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute)
        and node.value.attr == 'shape' and _name(node.value.value, name)
        and isinstance(node.slice, ast.Constant) and node.slice.value == 0)


def _pattern(fn, aliases):
    if (fn.decorator_list or fn.args.defaults or fn.args.kwonlyargs
            or fn.args.vararg or fn.args.kwarg or len(fn.body) < 4):
        return None
    branch, ret = fn.body[-2:]
    if not (isinstance(ret, ast.Return) and isinstance(ret.value, ast.Name)
            and isinstance(branch, ast.If) and not branch.orelse
            and len(branch.body) == 1):
        return None
    result = ret.value.id
    assign = branch.body[0]
    if not (isinstance(assign, ast.Assign) and len(assign.targets) == 1
            and _name(assign.targets[0], result)
            and isinstance(assign.value, ast.Subscript)
            and _name(assign.value.value, result)
            and isinstance(assign.value.slice, ast.Constant)
            and type(assign.value.slice.value) is int
            and assign.value.slice.value == 0):
        return None
    test = branch.test
    if not (isinstance(test, ast.Compare) and len(test.ops) == 1
            and isinstance(test.ops[0], ast.Eq) and isinstance(test.left, ast.Name)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value == 1):
        return None
    count = test.left.id
    args = fn.args.posonlyargs + fn.args.args
    for index, arg in enumerate(args):
        normalizations = [st for st in fn.body[:-2] if isinstance(st, ast.Assign)
                          and len(st.targets) == 1 and _name(st.targets[0], arg.arg)
                          and _numpy_call(st.value, aliases, 'atleast_1d')
                          and len(st.value.args) == 1 and not st.value.keywords
                          and _name(st.value.args[0], arg.arg)]
        if len(normalizations) != 1:
            continue
        norm = normalizations[0]
        if any(not isinstance(st, (ast.Import, ast.ImportFrom)) and not (
                isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)
                and isinstance(st.value.value, str))
               for st in fn.body[:fn.body.index(norm)]):
            continue
        sizes = [st for st in fn.body[:-2] if isinstance(st, ast.Assign)
                 and len(st.targets) == 1 and _name(st.targets[0], count)
                 and _size_of(st.value, arg.arg)]
        if len(sizes) != 1 or fn.body.index(sizes[0]) <= fn.body.index(norm):
            continue
        nodes = list(ast.walk(fn))
        if any(isinstance(n, (ast.Global, ast.Nonlocal, ast.AsyncFunctionDef,
                              ast.Lambda, ast.Yield, ast.YieldFrom)) for n in nodes):
            continue
        if sum(isinstance(n, ast.FunctionDef) for n in nodes) != 1:
            continue
        if sum(isinstance(n, ast.Return) for n in nodes) != 1:
            continue
        if any(sum(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                   and n.id == name for n in nodes) != 1 for name in (arg.arg, count)):
            continue
        # No arbitrary calls (which could resize aliased inputs), or attribute
        # writes such as x.shape = ..., in this narrowly supported idiom.
        if any(isinstance(n, ast.Delete) or (isinstance(n, ast.Attribute)
               and isinstance(n.ctx, ast.Store)) for n in nodes):
            continue
        if any(isinstance(n, ast.Call) and not (
                _numpy_call(n, aliases, 'atleast_1d') or _numpy_call(n, aliases, 'ones')
                or (_name(n.func, 'len') and len(n.args) == 1)
                or (_name(n.func, 'range') and not n.keywords)) for n in nodes):
            continue
        if any((isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                and n.id in ('len', 'range')) or (isinstance(n, ast.arg)
                and n.arg in ('len', 'range')) for n in nodes):
            continue
        return index, arg.arg, fn.body.index(norm)
    return None


def specialize_singleton_returns(tree):
    """Rewrite provable calls to separate scalar/length-one/vector versions."""
    if any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(tree)):
        return tree
    if any(isinstance(n, ast.ImportFrom) and any(a.name == '*' for a in n.names)
           for n in ast.walk(tree)):
        return tree
    aliases = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
               for a in n.names if a.name == 'numpy'}
    # Rebinding NumPy aliases defeats the deliberately simple name resolution.
    bound = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)
             and isinstance(n.ctx, ast.Store)}
    bound |= {a.asname or a.name.split('.')[0] for n in ast.walk(tree)
              if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names
              if not (isinstance(n, ast.Import) and a.name == 'numpy')}
    aliases -= bound
    aliases -= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    aliases -= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    patterns = {name: p for name, fn in functions.items()
                if (p := _pattern(fn, aliases)) is not None and name not in bound
                and sum(isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name
                        for n in ast.walk(tree)) == 1}
    if bound.intersection({'len', 'range'}) or set(functions).intersection({'len', 'range'}):
        return tree
    if not patterns:
        return tree
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | set(functions)
    used |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    clones = {}

    def fresh(stem):
        name = stem
        while name.lower() in {s.lower() for s in used}:
            name += '_'
        used.add(name)
        return name

    # Facts are ('scalar', optional numeric constant) or ('vector', length).
    def scalar_dtype(node):
        names = {'int', 'float', 'bool', 'complex', 'int32', 'int64',
                 'float32', 'float64', 'complex64', 'complex128', 'bool_'}
        return (isinstance(node, ast.Name) and node.id in {'int', 'float', 'bool', 'complex'}
                or isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in names
                or isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in aliases and node.attr in names)

    def fact(node, env):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float, bool):
            return 'scalar', node.value
        if isinstance(node, ast.Name):
            return env.get(node.id)
        if isinstance(node, ast.UnaryOp):
            f = fact(node.operand, env)
            if f and f[0] == 'scalar':
                value = f[1]
                if value is not None and isinstance(node.op, ast.USub):
                    value = -value
                elif not isinstance(node.op, ast.UAdd):
                    value = None
                return 'scalar', value
        if isinstance(node, ast.BinOp):
            a, b = fact(node.left, env), fact(node.right, env)
            if a and b and a[0] == b[0] == 'scalar':
                return 'scalar', None
        if (_numpy_call(node, aliases, 'array') and len(node.args) == 1
                and all(kw.arg == 'dtype' and scalar_dtype(kw.value) for kw in node.keywords)):
            seq = node.args[0]
            if isinstance(seq, (ast.List, ast.Tuple)) and all(
                    (f := fact(e, env)) and f[0] == 'scalar' for e in seq.elts):
                return 'vector', len(seq.elts)
        if _numpy_call(node, aliases, 'linspace'):
            if len(node.args) > 3 or any(kw.arg not in {'start', 'stop', 'num', 'endpoint', 'dtype'}
                                       or kw.arg == 'dtype' and not scalar_dtype(kw.value)
                                       for kw in node.keywords):
                return None
            num = node.args[2] if len(node.args) > 2 else next(
                (kw.value for kw in node.keywords if kw.arg == 'num'), ast.Constant(50))
            f = fact(num, env)
            endpoints = list(node.args[:2]) + [kw.value for kw in node.keywords
                                              if kw.arg in ('start', 'stop')]
            if (len(endpoints) == 2 and all((v := fact(e, env)) and v[0] == 'scalar'
                                          for e in endpoints)
                    and f and type(f[1]) is int and f[1] >= 0
                    and not any(kw.arg in ('retstep', 'axis') for kw in node.keywords)):
                return 'vector', f[1]
        return None

    def safe_expr(node):
        return not any(isinstance(n, ast.Call) and not any(
            _numpy_call(n, aliases, name) for name in ('array', 'linspace'))
                       for n in ast.walk(node))

    def rewrite_expr(node, env, shadowed):
        # Do not cross lexical scopes or comprehension scopes.
        if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
                             ast.GeneratorExp)):
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if name in patterns and name not in shadowed and all(
                    safe_expr(a) for a in node.args) and all(
                    kw.arg and safe_expr(kw.value) for kw in node.keywords):
                index, param, norm_index = patterns[name]
                actual = node.args[index] if len(node.args) > index else next(
                    (kw.value for kw in node.keywords if kw.arg == param), None)
                f = fact(actual, env)
                if f:
                    mode = 'scalar' if f[0] == 'scalar' else ('one' if f[1] == 1 else 'vector')
                    key = name, mode
                    if key not in clones:
                        clone = copy.deepcopy(functions[name])
                        clone.name = fresh(name + '_size_' + mode)
                        incoming = fresh(param + '_input')
                        (clone.args.posonlyargs + clone.args.args)[index].arg = incoming
                        clone.body[norm_index].value.args[0].id = incoming
                        branch = clone.body.pop(-2)
                        if mode != 'vector':
                            clone.body[-1].value = copy.deepcopy(branch.body[0].value)
                        clones[key] = clone, incoming
                    clone, incoming = clones[key]
                    node.func.id = clone.name
                    for kw in node.keywords:
                        if kw.arg == param:
                            kw.arg = incoming
        for child in ast.iter_child_nodes(node):
            rewrite_expr(child, env, shadowed)
        # Calls are visited in evaluation order. A sibling call can resize an
        # argument before a later call in the very same statement.
        if isinstance(node, ast.Call) and not any(
                _numpy_call(node, aliases, name) for name in ('array', 'linspace')):
            forget_vectors(env)

    def forget_vectors(env):
        for name in list(env):
            if env[name][0] == 'vector':
                del env[name]

    def block(stmts, env, shadowed):
        for st in stmts:
            if isinstance(st, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                continue
            if isinstance(st, ast.For):
                # Loop-carried facts and aliases cannot be treated as constants.
                local = {k: v for k, v in env.items() if v[0] == 'scalar'}
                for n in ast.walk(st):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                        local.pop(n.id, None)
                        env.pop(n.id, None)
                if (isinstance(st.target, ast.Name) and isinstance(st.iter, ast.Call)
                        and _name(st.iter.func, 'range') and 'range' not in shadowed):
                    local[st.target.id] = 'scalar', None
                block(st.body, local, shadowed)
                block(st.orelse, {}, shadowed)
                forget_vectors(env)
                continue
            if isinstance(st, (ast.If, ast.While, ast.Try, ast.With)):
                # Conservative at joins; do not propagate assumptions into them.
                for field in ('body', 'orelse', 'finalbody'):
                    block(getattr(st, field, []), {}, shadowed)
                env.clear()
                continue
            if any(isinstance(n, ast.NamedExpr) for n in ast.walk(st)):
                env.clear()
                continue
            if any(isinstance(n, (ast.Attribute, ast.Subscript))
                   and isinstance(n.ctx, (ast.Store, ast.Del)) for n in ast.walk(st)):
                # Assignment targets are evaluated after the RHS, unlike AST
                # field order. Do not specialize through such side effects.
                env.clear()
                continue
            rewrite_expr(st, env, shadowed)
            value = fact(st.value, env) if isinstance(st, ast.Assign) else None
            if any(isinstance(n, ast.Call) for n in ast.walk(st)):
                forget_vectors(env)
            # A vector alias or shape mutation invalidates all length facts.
            if isinstance(st, ast.Assign) and (isinstance(st.value, ast.Name)
                    or any(not isinstance(t, ast.Name) for t in st.targets)):
                forget_vectors(env)
                if value and value[0] == 'vector':
                    value = None
            for n in ast.walk(st):
                if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
                    env.pop(n.id, None)
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and value:
                env[st.targets[0].id] = value

    for name, fn in functions.items():
        if name not in patterns:
            shadowed = {n.arg for n in ast.walk(fn) if isinstance(n, ast.arg)}
            shadowed |= {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
                         and isinstance(n.ctx, ast.Store)}
            block(fn.body, {}, shadowed)
    block(tree.body, {}, bound)
    # An unresolved use keeps the original and its existing rejection path.
    refs = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    specialized = {name for name, _ in clones}
    tree.body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef)
                 and n.name in specialized and n.name not in refs)]
    # Keep future imports and the module docstring in their required positions.
    insertion = next((i for i, n in enumerate(tree.body)
                      if not isinstance(n, (ast.Import, ast.ImportFrom)) and not (
                          isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                          and isinstance(n.value.value, str))), len(tree.body))
    tree.body[insertion:insertion] = [clone for clone, _ in clones.values()]
    return ast.fix_missing_locations(tree)
