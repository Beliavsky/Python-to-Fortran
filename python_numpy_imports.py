"""Resolve NumPy star imports without executing the input program."""

import ast


def normalize_numpy_wildcard_imports(tree):
    """Qualify statically resolved exports before type/rank inference.

    Ordinary module statements are resolved in order; functions use lexical
    locals and conservative late-bound globals/closures. NumPy is imported
    only to read its installed export list, never to execute user code.
    Mixed star imports, conditional rebinding, classes, and lazy generators
    are deliberately diagnosed rather than approximated. Use explicit NumPy
    imports for those cases. Trees without NumPy star imports are unchanged.
    """
    stars = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             and n.module == "numpy" and not n.level and any(a.name == "*" for a in n.names)]
    if not stars:
        return tree
    if any(n not in tree.body for n in stars):
        raise NotImplementedError("NumPy wildcard imports must be unconditional module-level imports")
    if any(isinstance(n, ast.ImportFrom) and (n.module != "numpy" or n.level)
           and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        raise NotImplementedError("NumPy wildcard import mixed with another wildcard import is ambiguous; use explicit imports")
    try:
        import numpy
    except ImportError as exc:
        raise NotImplementedError("NumPy must be installed to resolve its wildcard exports") from exc
    exports = set(numpy.__all__)

    # The downstream compiler uses np as its canonical NumPy namespace.
    # Move a conflicting user identifier out of that namespace first.
    collision = any(
        (isinstance(n, ast.Name) and n.id == "np" and isinstance(n.ctx, (ast.Store, ast.Del)))
        or (isinstance(n, ast.arg) and n.arg == "np")
        or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name == "np")
        or (isinstance(n, ast.Import) and any((a.asname or a.name.split('.')[0]) == "np" and a.name != "numpy" for a in n.names))
        or (isinstance(n, ast.ImportFrom) and any((a.asname or a.name) == "np" for a in n.names))
        for n in ast.walk(tree)
    )
    if not any(isinstance(n, ast.Import) and any(a.name == "numpy" and a.asname == "np" for a in n.names) for n in ast.walk(tree)):
        collision |= any(isinstance(n, ast.Name) and n.id == "np" for n in ast.walk(tree))
    if collision:
        if any(isinstance(n, ast.keyword) and n.arg == "np" for n in ast.walk(tree)):
            raise NotImplementedError("NumPy wildcard import with a conflicting np keyword parameter: rename np or use explicit imports")
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        used |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
        used |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
        used |= {n.asname or n.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.alias)}
        alias = "xp2f_user_np"
        while alias in used:
            alias += "_"

        class Rename(ast.NodeTransformer):
            def visit_Name(self, node):
                if node.id == "np":
                    node.id = alias
                return node

            def visit_arg(self, node):
                if node.arg == "np":
                    node.arg = alias
                return self.generic_visit(node)

            def visit_FunctionDef(self, node):
                if node.name == "np":
                    node.name = alias
                return self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef
            visit_ClassDef = visit_FunctionDef

            def visit_Import(self, node):
                for a in node.names:
                    if (a.asname or a.name.split('.')[0]) == "np":
                        a.asname = alias
                return node

            def visit_ImportFrom(self, node):
                for a in node.names:
                    if (a.asname or a.name) == "np":
                        a.asname = alias
                return node

            def visit_Global(self, node):
                node.names = [alias if s == "np" else s for s in node.names]
                return node

            visit_Nonlocal = visit_Global

        tree = Rename().visit(tree)

    numpy_bindings = exports | {
        a.asname or a.name for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "numpy" and not n.level
        for a in n.names if a.name != "*"
    }

    class Bindings(ast.NodeVisitor):
        def __init__(self):
            self.names = set()

        def visit_Name(self, node):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                self.names.add(node.id)

        def visit_FunctionDef(self, node):
            self.names.add(node.name)

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Lambda(self, node):
            pass

        def visit_ListComp(self, node):
            pass

        visit_SetComp = visit_ListComp
        visit_DictComp = visit_ListComp
        visit_GeneratorExp = visit_ListComp

        def visit_Import(self, node):
            self.names.update(a.asname or a.name.split('.')[0] for a in node.names)

        def visit_ImportFrom(self, node):
            self.names.update(a.asname or a.name for a in node.names if a.name != "*")

        def visit_ExceptHandler(self, node):
            if node.name:
                self.names.add(node.name)
            self.generic_visit(node)

        def visit_MatchAs(self, node):
            if node.name:
                self.names.add(node.name)
            self.generic_visit(node)

        visit_MatchStar = visit_MatchAs

        def visit_MatchMapping(self, node):
            if node.rest:
                self.names.add(node.rest)
            self.generic_visit(node)

    unknown = object()

    class Resolver(ast.NodeTransformer):
        def __init__(self):
            self.env = {}
            self.history = {}
            self.deferred = []
            self.module = True

        def bind(self, name, value):
            self.env[name] = value
            self.history.setdefault(name, set()).add(value)

        def visit_Name(self, node):
            value = self.env.get(node.id)
            if isinstance(node.ctx, ast.Load):
                if value is unknown:
                    raise NotImplementedError(f"NumPy wildcard binding for {node.id!r} is ambiguous at line {node.lineno}; use explicit imports or distinct names")
                if isinstance(value, str):
                    return ast.copy_location(ast.Attribute(value=ast.Name(id="np", ctx=ast.Load()), attr=value, ctx=ast.Load()), node)
            return node

        def visit_ImportFrom(self, node):
            if node.module == "numpy" and not node.level:
                for a in node.names:
                    if a.name == "*":
                        for name in exports:
                            self.bind(name, name)
                    else:
                        self.bind(a.asname or a.name, a.name)
                return ast.copy_location(ast.Pass(), node)
            for a in node.names:
                self.bind(a.asname or a.name, None)
            return node

        def visit_Import(self, node):
            for a in node.names:
                self.bind(a.asname or a.name.split('.')[0], None)
            return node

        def visit_Assign(self, node):
            node.value = self.visit(node.value)
            node.targets = [self.visit(t) for t in node.targets]
            for target in node.targets:
                bindings = Bindings()
                bindings.visit(target)
                for name in bindings.names:
                    self.bind(name, None)
            return node

        def visit_AnnAssign(self, node):
            node.annotation = self.visit(node.annotation)
            if node.value:
                node.value = self.visit(node.value)
            node.target = self.visit(node.target)
            if isinstance(node.target, ast.Name) and node.value:
                self.bind(node.target.id, None)
            return node

        def visit_NamedExpr(self, node):
            node.value = self.visit(node.value)
            self.bind(node.target.id, None)
            return node

        def visit_AugAssign(self, node):
            if isinstance(node.target, ast.Name) and self.env.get(node.target.id) is not None:
                raise NotImplementedError("Augmented assignment to a NumPy wildcard binding requires an explicit local variable")
            return self.generic_visit(node)

        def visit_Delete(self, node):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.bind(target.id, unknown)
            return node

        def visit_Global(self, node):
            if any(name in numpy_bindings for name in node.names):
                raise NotImplementedError("global/nonlocal NumPy wildcard bindings require explicit imports or distinct names")
            return node

        visit_Nonlocal = visit_Global

        def visit_FunctionDef(self, node):
            node.decorator_list = [self.visit(n) for n in node.decorator_list]
            node.args = self.visit(node.args)
            if node.returns:
                node.returns = self.visit(node.returns)
            self.bind(node.name, None)
            self.defer(node)
            return node

        visit_AsyncFunctionDef = visit_FunctionDef

        def defer(self, node):
            self.deferred.append((node, None if self.module else self.env,
                                  dict(self.env) if self.module else None))

        def function_body(self, node, env):
            saved_env, saved_module, saved_history = self.env, self.module, self.history
            self.env, self.module = dict(env), False
            self.history = {}
            bindings = Bindings()
            statements = [ast.Expr(value=node.body)] if isinstance(node, ast.Lambda) else node.body
            for stmt in statements:
                bindings.visit(stmt)
            args = node.args.posonlyargs + node.args.args + node.args.kwonlyargs
            args += [a for a in (node.args.vararg, node.args.kwarg) if a]
            for name in bindings.names | {a.arg for a in args}:
                self.env[name] = None
            statements = [self.visit(s) for s in statements]
            node.body = statements[0].value if isinstance(node, ast.Lambda) else statements
            for name, values in self.history.items():
                if len(values) > 1 and any(isinstance(v, str) for v in values):
                    self.env[name] = unknown
            self.env, self.module, self.history = saved_env, saved_module, saved_history

        def visit_Lambda(self, node):
            node.args = self.visit(node.args)
            self.defer(node)
            return node

        def visit_ListComp(self, node):
            if any(isinstance(n, ast.NamedExpr) for n in ast.walk(node)):
                raise NotImplementedError("Assignment expressions in comprehensions with NumPy wildcard imports require explicit imports")
            saved = self.env
            self.env = dict(saved)
            for gen in node.generators:
                gen.iter = self.visit(gen.iter)
                bindings = Bindings()
                bindings.visit(gen.target)
                for name in bindings.names:
                    self.env[name] = None
                gen.ifs = [self.visit(n) for n in gen.ifs]
            for field in ("elt", "key", "value"):
                if hasattr(node, field):
                    setattr(node, field, self.visit(getattr(node, field)))
            self.env = saved
            return node

        visit_SetComp = visit_ListComp
        visit_DictComp = visit_ListComp

        def visit_GeneratorExp(self, node):
            raise NotImplementedError("Lazy generator expressions with NumPy wildcard imports require explicit imports")

        def control(self, node):
            if any(isinstance(n, ast.ImportFrom) and n.module == "numpy" for n in ast.walk(node)):
                raise NotImplementedError("Conditional NumPy imports with wildcard bindings require explicit unconditional imports")
            bindings = Bindings()
            bindings.visit(node)
            if any(self.env.get(name) is not None for name in bindings.names):
                raise NotImplementedError("Conditional/loop rebinding of a NumPy wildcard name is ambiguous; use distinct names or explicit imports")
            return self.generic_visit(node)

        visit_If = control
        visit_For = control
        visit_While = control
        visit_Try = control
        visit_With = control
        visit_Match = control

        def visit_ClassDef(self, node):
            raise NotImplementedError("NumPy wildcard imports with class definitions require explicit NumPy imports")

    resolver = Resolver()
    tree = resolver.visit(tree)
    globals_env = dict(resolver.env)
    for name, values in resolver.history.items():
        if len(values) > 1 and any(isinstance(v, str) for v in values):
            globals_env[name] = unknown
    # Processing a function may enqueue nested functions as well.
    for node, closure, definition_env in resolver.deferred:
        env = globals_env if closure is None else closure
        if definition_env is not None:
            env = dict(env)
            for name, value in env.items():
                if isinstance(value, str) and definition_env.get(name) != value:
                    env[name] = unknown
        resolver.function_body(node, env)
    index = 0
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) and isinstance(tree.body[0].value.value, str):
        index = 1
    while index < len(tree.body) and isinstance(tree.body[index], ast.ImportFrom) and tree.body[index].module == "__future__":
        index += 1
    tree.body.insert(index, ast.Import(names=[ast.alias(name="numpy", asname="np")]))
    return ast.fix_missing_locations(tree)
