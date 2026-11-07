"""Preserve direct list/ndarray identity before value-based Fortran inference.

This is storage-name normalization, not a general Python object runtime.
Bindings must be statically known within one scope. Views still use xp2f's
separate view analysis; control-flow-dependent bindings are diagnosed.
"""
import ast


def normalize_direct_array_aliases(tree):
    occupied = {n.id.lower() for n in ast.walk(tree) if isinstance(n, ast.Name)}
    occupied.update(n.arg.lower() for n in ast.walk(tree) if isinstance(n, ast.arg))
    occupied.update(n.name.lower() for n in ast.walk(tree)
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    numpy_names = {a.asname or a.name for n in ast.walk(tree) if isinstance(n, ast.Import)
                   for a in n.names if a.name == 'numpy'}
    constructors = {'array', 'zeros', 'ones', 'empty', 'full', 'arange', 'linspace',
                    'zeros_like', 'ones_like', 'empty_like', 'full_like', 'eye', 'identity'}
    functions = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    scipy_linalg_names = {a.asname or a.name for n in ast.walk(tree)
                          if isinstance(n, ast.ImportFrom) and n.module == 'scipy'
                          for a in n.names if a.name == 'linalg'}

    def fresh(name):
        index = 1
        while f'{name}_binding_{index}'.lower() in occupied:
            index += 1
        result = f'{name}_binding_{index}'
        occupied.add(result.lower())
        return result

    def fail(node, why):
        raise NotImplementedError(
            f"unsupported array alias binding at line {getattr(node, 'lineno', '?')}: {why}; "
            "use independent .copy() values or keep shared bindings straight-line")

    def scope(body, arguments=()):
        # Do not let equally spelled names in another scope supply evidence.
        nodes = []
        def collect(n):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                return
            nodes.append(n)
            for child in ast.iter_child_nodes(n):
                collect(child)
        for st in body:
            collect(st)
        modules = numpy_names - set(arguments) - {
            n.id for n in nodes if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}

        def kind(value, known):
            if isinstance(value, (ast.List, ast.ListComp)):
                return 'list'
            if isinstance(value, ast.Name):
                return known.get(value.id)
            if isinstance(value, ast.Subscript) and isinstance(value.slice, ast.Slice):
                if isinstance(value.value, ast.Name) and known.get(value.value.id) == 'list':
                    return 'list'
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute):
                f = value.func
                if (isinstance(f.value, ast.Name) and f.value.id in modules
                        and f.attr in constructors
                        and not any(k.arg == 'copy' and (
                                        not isinstance(k.value, ast.Constant) or k.value.value is not True)
                                    for k in value.keywords)):
                    return 'numpy'
                if f.attr == 'copy' and not value.args and not value.keywords:
                    return kind(f.value, known)
            return None

        assignments = [n for n in nodes if isinstance(n, ast.Assign)]
        known = {}
        for _ in range(len(assignments) + 1):
            before = dict(known)
            for st in assignments:
                value_kind = kind(st.value, known)
                if value_kind:
                    for t in st.targets:
                        if isinstance(t, ast.Name):
                            known[t.id] = value_kind
            if before == known:
                break
        participants = set()
        # This pass owns only straight-line bindings. A loop's own buffer
        # rotation (x = x_new) must not mark every assignment in that loop
        # as an unsupported shared binding. It remains with the existing
        # list/view lowering unless a sharing group already exists outside.
        for st in body:
            if not isinstance(st, ast.Assign):
                continue
            if isinstance(st.value, ast.Name) and st.value.id in known:
                participants.add(st.value.id)
                participants.update(t.id for t in st.targets if isinstance(t, ast.Name))

        def readonly_numpy_sharing():
            # Rebinding P in a Riccati iteration is not an in-place write
            # to Q in `P = Q`. Value copies are equivalent while no member
            # of the sharing group is modified, captured, or passed to an
            # unknown procedure. Include aliases introduced inside blocks.
            group = set(participants)
            for _ in range(len(assignments) + 1):
                previous = set(group)
                for st in assignments:
                    if isinstance(st.value, ast.Name) and st.value.id in group:
                        group.update(t.id for t in st.targets if isinstance(t, ast.Name))
                if group == previous:
                    break
            if not group or any(known.get(n) != 'numpy' for n in group):
                return False
            def touches(node):
                return any(isinstance(n, ast.Name) and n.id in group for n in ast.walk(node))
            safe_numpy = {'dot', 'matmul', 'transpose', 'copy', 'zeros', 'ones', 'empty',
                          'full', 'array', 'zeros_like', 'ones_like', 'empty_like', 'full_like',
                          'sum', 'mean', 'min', 'max', 'abs', 'sqrt', 'sin', 'cos', 'exp', 'log',
                          'solve', 'cholesky'}
            for node in nodes:
                if (isinstance(node, ast.Compare) and any(isinstance(op, (ast.Is, ast.IsNot)) for op in node.ops)
                        and touches(node)):
                    return False
                if isinstance(node, (ast.Global, ast.Nonlocal)) and set(node.names) & group:
                    return False
                if isinstance(node, ast.Lambda) and touches(node):
                    return False
                targets = node.targets if isinstance(node, ast.Assign) else (
                    [node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else [])
                for target in targets:
                    if (isinstance(node, ast.AugAssign) or not isinstance(target, ast.Name)) and touches(target):
                        return False
                if isinstance(node, (ast.Return, ast.Yield, ast.YieldFrom, ast.Delete)) and touches(node):
                    return False
                if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                    value = node.value
                    # A new view could mutate the group through a name not
                    # included in the direct-binding analysis below.
                    if isinstance(value, (ast.Subscript, ast.Attribute)) and touches(value):
                        return False
                    if (isinstance(value, ast.Call) and isinstance(value.func, ast.Attribute)
                            and value.func.attr == 'transpose' and touches(value)):
                        return False
                if not isinstance(node, ast.Call) or not touches(node):
                    continue
                if any(k.arg == 'out' and touches(k.value) for k in node.keywords):
                    return False
                if any(k.arg == 'copy' and not (isinstance(k.value, ast.Constant)
                                               and k.value.value is True)
                       for k in node.keywords):
                    return False
                if any(k.arg in {'overwrite_a', 'overwrite_b'}
                       and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                       for k in node.keywords):
                    return False
                f = node.func
                if isinstance(f, ast.Name) and f.id in {'print', 'len', 'range'}:
                    continue
                if isinstance(f, ast.Attribute):
                    root = f.value
                    while isinstance(root, ast.Attribute):
                        root = root.value
                    if (isinstance(root, ast.Name) and f.attr in safe_numpy
                            and root.id in modules | scipy_linalg_names | group):
                        continue
                return False
            for st in body:
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and touches(st):
                    return False
            return group

        # Process child scopes independently, even if this one has no aliases.
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in ast.walk(st.args) if isinstance(a, ast.arg)]
                if participants:
                    locals_ = set(args) | {n.id for n in ast.walk(st)
                                          if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
                    free = {n.id for n in ast.walk(st) if isinstance(n, ast.Name)
                            and isinstance(n.ctx, ast.Load)} - locals_
                    if free & participants:
                        fail(st, 'shared names captured by another procedure')
                st.body = scope(st.body, args)
        if not participants:
            return body

        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if st.name in participants:
                    fail(st, 'procedure/class definition rebinding a shared name')
                if isinstance(st, ast.ClassDef) and any(
                        isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in participants
                        for n in ast.walk(st)):
                    fail(st, 'shared names captured by a class')
                continue
            if isinstance(st, (ast.Import, ast.ImportFrom)):
                if {a.asname or a.name.split('.')[0] for a in st.names} & participants:
                    fail(st, 'import rebinding a shared name')
            if not isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Expr, ast.Return,
                                   ast.Import, ast.ImportFrom)):
                for n in ast.walk(st):
                    if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and n.id in participants:
                        # Whole-array += is in-place, not a new binding.
                        if any(isinstance(a, ast.AugAssign) and a.target is n for a in ast.walk(st)):
                            continue
                        readonly_group = readonly_numpy_sharing()
                        if readonly_group:
                            class Materialize(ast.NodeTransformer):
                                def visit_FunctionDef(self, node):
                                    return node
                                visit_AsyncFunctionDef = visit_FunctionDef
                                visit_ClassDef = visit_FunctionDef
                                def visit_Assign(self, node):
                                    if isinstance(node.value, ast.Name) and node.value.id in readonly_group:
                                        node.value = ast.copy_location(ast.Call(
                                            func=ast.Attribute(value=node.value, attr='copy', ctx=ast.Load()),
                                            args=[], keywords=[]), node.value)
                                    return self.generic_visit(node)
                            return [Materialize().visit(s) for s in body]
                        fail(n, 'control-flow-dependent shared names')
            for n in ast.walk(st):
                if isinstance(n, (ast.Global, ast.Nonlocal)) and set(n.names) & participants:
                    fail(n, 'global/nonlocal shared names')
                if isinstance(n, ast.NamedExpr) and isinstance(n.target, ast.Name) and n.target.id in participants:
                    fail(n, 'assignment expressions changing shared names')
                if isinstance(n, ast.Lambda) and any(isinstance(v, ast.Name) and v.id in participants
                                                      for v in ast.walk(n)):
                    fail(n, 'shared names captured by a lambda')
            if (isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name)
                    and st.target.id in participants):
                fail(st, 'annotated rebinding of shared names')
            if isinstance(st, ast.Assign) and len(st.targets) != 1 and any(
                    isinstance(t, ast.Name) and t.id in participants for t in st.targets):
                fail(st, 'chained shared bindings')
            if isinstance(st, ast.Assign) and any(
                    isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id in participants
                    for t in st.targets if not isinstance(t, ast.Name) for n in ast.walk(t)):
                fail(st, 'unpacking into shared names')

        env, storage_kind = {}, {}

        class Rename(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id in env:
                    return ast.copy_location(ast.Name(id=env[node.id], ctx=node.ctx), node)
                return node

            def visit_Lambda(self, node):
                return node  # Escaping bindings are not rewritten across scopes.

            def visit_ListComp(self, node):
                saved = dict(env)
                try:
                    for gen in node.generators:
                        gen.iter = self.visit(gen.iter)
                        for t in ast.walk(gen.target):
                            if isinstance(t, ast.Name):
                                env.pop(t.id, None)
                        gen.ifs = [self.visit(c) for c in gen.ifs]
                    node.elt = self.visit(node.elt)
                    return node
                finally:
                    env.clear()
                    env.update(saved)

            visit_GeneratorExp = visit_ListComp
            visit_SetComp = visit_ListComp

            def visit_DictComp(self, node):
                saved = dict(env)
                try:
                    for gen in node.generators:
                        gen.iter = self.visit(gen.iter)
                        for t in ast.walk(gen.target):
                            if isinstance(t, ast.Name):
                                env.pop(t.id, None)
                        gen.ifs = [self.visit(c) for c in gen.ifs]
                    node.key, node.value = self.visit(node.key), self.visit(node.value)
                    return node
                finally:
                    env.clear()
                    env.update(saved)

            def visit_Call(self, node):
                if isinstance(node.func, ast.Name) and node.func.id in functions:
                    fn = functions[node.func.id]
                    args = {a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg)}
                    mutated = False
                    for st in ast.walk(fn):
                        targets = st.targets if isinstance(st, ast.Assign) else (
                            [st.target] if isinstance(st, (ast.AugAssign, ast.AnnAssign)) else [])
                        for target in targets:
                            while isinstance(target, (ast.Subscript, ast.Attribute)):
                                target = target.value
                            mutated |= isinstance(target, ast.Name) and target.id in args
                        if isinstance(st, ast.Call) and isinstance(st.func, ast.Attribute):
                            mutated |= isinstance(st.func.value, ast.Name) and st.func.value.id in args
                        if isinstance(st, ast.Call) and isinstance(st.func, ast.Name):
                            mutated |= st.func.id in functions  # May forward to a mutating procedure.
                    if (any(isinstance(a, ast.Starred) for a in node.args)
                            or any(k.arg is None for k in node.keywords)) and any(
                                isinstance(n, ast.Name) and n.id in participants for n in ast.walk(node)):
                        fail(node, 'expanded shared actual arguments')
                    actuals = [a for a in node.args if isinstance(a, ast.Name)]
                    actuals += [k.value for k in node.keywords if isinstance(k.value, ast.Name)]
                    roots = [env.get(a.id, a.id) for a in actuals]
                    roots = [r for r in roots if storage_kind.get(r)]
                    if mutated and len(roots) != len(set(roots)):
                        fail(node, 'overlapping actual arguments to a mutating procedure')
                return self.generic_visit(node)

            def visit_FunctionDef(self, node):
                return node

            visit_AsyncFunctionDef = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef

        result = []
        for st in body:
            if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name):
                target = st.targets[0].id
                value = st.value
                if isinstance(value, ast.Name) and storage_kind.get(env.get(value.id, value.id)):
                    env[target] = env.get(value.id, value.id)
                    continue
                value_kind = kind(value, {n: storage_kind.get(s) for n, s in env.items()})
                st.value = Rename().visit(value)
                # The original spelling may still store an object retained
                # by another binding. Allocate the NEW value under a new name
                # instead of overwriting the old object's storage.
                retained = any(n != target and s == target for n, s in env.items())
                destination = fresh(target) if retained else target
                env[target] = destination
                storage_kind[destination] = value_kind
                st.targets[0].id = destination
                result.append(st)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                result.append(st)
            else:
                result.append(Rename().visit(st))
        return result

    tree.body = scope(tree.body)
    return ast.fix_missing_locations(tree)
