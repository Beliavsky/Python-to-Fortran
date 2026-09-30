"""Resolve scientific-library star imports without executing the input program."""

import ast
import importlib


# Start with operations whose SciPy defaults match the existing lowering
# (Cholesky has its own NumPy/SciPy orientation normalizer). Other exports
# remain legal to import, but are diagnosed when referenced.
SCIPY_LINALG_WILDCARD_SUPPORTED = {"solve", "cholesky", "det", "inv", "norm"}


def normalize_numpy_wildcard_imports(tree):
    """Qualify statically resolved exports before type/rank inference.

    Ordinary module statements are resolved in order; functions use lexical
    locals and conservative late-bound globals/closures. Libraries are imported
    only to read their installed export lists, never to execute user code.
    NumPy and scipy.linalg imports share import-order tracking. Other mixed
    star imports, conditional rebinding, classes, and lazy generators are
    diagnosed rather than approximated. Use explicit imports for those cases.
    The historical function name is retained for existing callers.
    """
    stars = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
             and (n.module == "numpy" or (n.module or "").split('.')[0] == "scipy")
             and not n.level and any(a.name == "*" for a in n.names)]
    if not stars:
        return tree
    supported_modules = {"numpy", "scipy.linalg"}
    for node in stars:
        if node.module not in supported_modules:
            raise NotImplementedError(f"Unsupported SciPy wildcard import: {node.module}; currently supported: scipy.linalg (use explicit imports for other submodules)")
    if any(n not in tree.body for n in stars):
        raise NotImplementedError("NumPy/SciPy wildcard imports must be unconditional module-level imports")
    if any(isinstance(n, ast.ImportFrom) and (n.module not in supported_modules or n.level)
           and any(a.name == "*" for a in n.names) for n in ast.walk(tree)):
        raise NotImplementedError("NumPy/SciPy wildcard import mixed with another wildcard import is ambiguous; use explicit imports")
    module_exports = {}
    for module in {node.module for node in stars}:
        try:
            library = importlib.import_module(module)
        except ImportError as exc:
            raise NotImplementedError(f"{module} must be installed to resolve its wildcard exports") from exc
        module_exports[module] = set(getattr(library, "__all__", [n for n in vars(library) if not n.startswith('_')]))
    exports = set().union(*module_exports.values())
    # Include explicit imports in a wildcard-using script in the same scope
    # analysis, so a later NumPy Cholesky import can override SciPy's binding.
    resolved_modules = supported_modules | {"numpy.linalg"}
    used_names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    used_names |= {n.arg for n in ast.walk(tree) if isinstance(n, ast.arg)}
    used_names |= {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
    used_names |= {n.asname or n.name.split('.')[0] for n in ast.walk(tree) if isinstance(n, ast.alias)}
    scipy_alias = "xp2f_scipy_linalg"
    while scipy_alias in used_names:
        scipy_alias += "_"
    uses_scipy = False

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
        if isinstance(n, ast.ImportFrom) and n.module in resolved_modules and not n.level
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
            nonlocal uses_scipy
            value = self.env.get(node.id)
            if isinstance(node.ctx, ast.Load):
                if value is unknown:
                    raise NotImplementedError(f"NumPy/SciPy wildcard binding for {node.id!r} is ambiguous at line {node.lineno}; use explicit imports or distinct names")
                if isinstance(value, str):
                    if value.startswith("scipy.linalg."):
                        name = value.rsplit('.', 1)[1]
                        if name not in SCIPY_LINALG_WILDCARD_SUPPORTED:
                            raise NotImplementedError(f"Unsupported SciPy operation: {value} (wildcard normalization, line {node.lineno})")
                        uses_scipy = True
                        return ast.copy_location(ast.Attribute(value=ast.Name(id=scipy_alias, ctx=ast.Load()), attr=name, ctx=ast.Load()), node)
                    return ast.copy_location(ast.parse("np." + value, mode="eval").body, node)
            return node

        def visit_Call(self, node):
            self.generic_visit(node)
            if (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == scipy_alias and node.func.attr != "cholesky"):
                nargs = {"solve": 2, "det": 1, "inv": 1, "norm": 1}[node.func.attr]
                if len(node.args) != nargs or node.keywords:
                    raise NotImplementedError(f"Unsupported SciPy call options: scipy.linalg.{node.func.attr}; wildcard support currently requires {nargs} positional argument(s) and default options")
            return node

        def visit_ImportFrom(self, node):
            if node.module in resolved_modules and not node.level:
                prefix = {"numpy": "", "numpy.linalg": "linalg.", "scipy.linalg": "scipy.linalg."}[node.module]
                for a in node.names:
                    if a.name == "*":
                        if node.module not in module_exports:
                            raise NotImplementedError(f"Unsupported wildcard import mixed with NumPy/SciPy: {node.module}")
                        for name in module_exports[node.module]:
                            self.bind(name, prefix + name)
                    else:
                        self.bind(a.asname or a.name, prefix + a.name)
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
                raise NotImplementedError("Augmented assignment to a NumPy/SciPy wildcard binding requires an explicit local variable")
            return self.generic_visit(node)

        def visit_Delete(self, node):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.bind(target.id, unknown)
            return node

        def visit_Global(self, node):
            if any(name in numpy_bindings for name in node.names):
                raise NotImplementedError("global/nonlocal NumPy/SciPy wildcard bindings require explicit imports or distinct names")
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
                raise NotImplementedError("Assignment expressions in comprehensions with NumPy/SciPy wildcard imports require explicit imports")
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
            raise NotImplementedError("Lazy generator expressions with NumPy/SciPy wildcard imports require explicit imports")

        def control(self, node):
            if any(isinstance(n, ast.ImportFrom) and n.module in resolved_modules for n in ast.walk(node)):
                raise NotImplementedError("Conditional NumPy/SciPy imports with wildcard bindings require explicit unconditional imports")
            bindings = Bindings()
            bindings.visit(node)
            if any(self.env.get(name) is not None for name in bindings.names):
                raise NotImplementedError("Conditional/loop rebinding of a NumPy/SciPy wildcard name is ambiguous; use distinct names or explicit imports")
            return self.generic_visit(node)

        visit_If = control
        visit_For = control
        visit_While = control
        visit_Try = control
        visit_With = control
        visit_Match = control

        def visit_ClassDef(self, node):
            raise NotImplementedError("NumPy/SciPy wildcard imports with class definitions require explicit imports")

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
    if uses_scipy:
        tree.body.insert(index + 1, ast.Import(names=[ast.alias(name="scipy.linalg", asname=scipy_alias)]))
    return ast.fix_missing_locations(tree)
