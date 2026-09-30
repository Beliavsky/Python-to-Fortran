"""Optional FPM packaging for programs sharing stateless local Python modules.

The ordinary translator first infers each procedure in its caller's context.
Only identical emitted implementations (modulo comments and dummy/result
names) are shared. Specializations and host-dependent code are not guessed.
Existing output directories are never overwritten.
"""

import argparse
import ast
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import fortran_scan as scan
from xpfunc2f import UnsupportedFunction, parse_module

ROOT = Path(__file__).resolve().parent


def statements(text):
    return [code for _, code in scan.iter_fortran_statements(text.splitlines())]


def canonical_procedure(text):
    units = scan.split_fortran_units_simple(text)
    if len(units) != 1 or units[0]["kind"] != "function":
        raise ValueError("shared procedures currently require single function results")
    unit = units[0]
    mapping = {name: f"dummy_{i}" for i, name in enumerate(unit["args"])}
    mapping[unit["result"] or unit["name"]] = "result_value"
    tokens = re.findall(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|[a-zA-Z_]\w*|[^\s]", "\n".join(statements(text)))
    return tuple(token if token.startswith(("'", '"')) else mapping.get(token.lower(), token.lower()) for token in tokens)


def shared_functions(path):
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    functions = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            if node.decorator_list or any(isinstance(n, (ast.Global, ast.Nonlocal)) for n in ast.walk(node)):
                raise ValueError(f"{path}: shared functions must not use decorators or global/nonlocal state")
            functions[node.name.lower()] = node
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            pass
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            pass
        else:
            raise ValueError(f"{path}: shared modules currently support imports and functions only")
    if not functions:
        raise ValueError(f"{path}: no shared functions")
    return functions


def split_shared(generated, shared_specs):
    """Extract shared routines, rejecting context-dependent implementations."""
    selected = {}
    owners = {}
    for path, names in shared_specs.items():
        for name in names:
            if name in owners:
                raise ValueError(f"shared procedure name collision: {name}")
            owners[name] = path
    parsed = {}
    uses = set()
    for driver, text in generated.items():
        try:
            module, header, lines, procedures = parse_module(text)
        except UnsupportedFunction as exc:
            raise ValueError(f"{driver}: cannot extract shared procedures: {exc}") from exc
        parsed[driver] = (module, lines, procedures)
        uses.update(s for s in statements("\n".join(header)) if re.match(r"use\b", s, re.I))
        for name in owners.keys() & procedures.keys():
            start, end = procedures[name]
            body = "\n".join(lines[start:end + 1])
            key = canonical_procedure(body)
            if name in selected and selected[name][0] != key:
                raise ValueError(f"{name}: inferred implementations differ between {selected[name][2]} and {driver}; cannot share safely")
            selected.setdefault(name, (key, body, driver))
    absent = owners.keys() - selected.keys()
    if absent:
        raise ValueError("No inferred callable implementation for shared function(s): " + ", ".join(sorted(absent)))
    libraries = {}
    for path, names in shared_specs.items():
        module = path.stem.lower() + "_shared_mod"
        # Keeping the original USE statements retains intrinsic/helper bindings,
        # but not caller-owned declarations or optimizer callback state.
        header = [f"module {module}", *sorted(uses), "implicit none", "private",
                  "integer, parameter :: dp = real64"]
        header += [f"public :: {name}" for name in sorted(names)]
        libraries[path.stem] = "\n".join(header + ["contains"] +
                                        [selected[name][1] for name in sorted(names)] + [f"end module {module}", ""])
    apps = {}
    for driver, (module, lines, procedures) in parsed.items():
        removals = set()
        imports = []
        for path, names in shared_specs.items():
            found = sorted(names.keys() & procedures.keys())
            for name in found:
                start, end = procedures[name]
                removals.update(range(start, end + 1))
            imports += [f"   use {path.stem.lower()}_shared_mod, only: {name}" for name in found]
        output = []
        for i, line in enumerate(lines):
            if i not in removals:
                output.append(line)
                if re.match(rf"\s*module\s+{re.escape(module)}\s*$", line, re.I):
                    output.extend(imports)
        apps[driver] = "\n".join(output) + "\n"
    return libraries, apps


def generate_project(drivers, shared, out_dir, data=()):
    import xp2f

    drivers = [Path(p).resolve() for p in drivers]
    shared = [Path(p).resolve() for p in shared]
    data = [Path(p).resolve() for p in data]
    out_dir = Path(out_dir).resolve()
    for path in drivers + shared + data:
        if not path.is_file():
            raise ValueError(f"missing input file: {path}")
    for paths in (drivers, shared, data):
        if len({p.name.lower() for p in paths}) != len(paths):
            raise ValueError("input filenames must be unique (case-insensitive)")
    for path in drivers + shared:
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", path.stem):
            raise ValueError(f"unsupported project identifier: {path.stem}")
    if out_dir.exists():
        raise ValueError(f"output directory already exists; choose a new directory: {out_dir}")
    specs = {p: shared_functions(p) for p in shared}
    for driver in drivers:
        tree = ast.parse(driver.read_text(encoding="utf-8-sig"))
        imports_shared = False
        for path in shared:
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module == path.stem:
                    imports_shared = True
                    if node.level or any(a.name == "*" or a.asname for a in node.names):
                        raise ValueError("shared imports currently require explicit, unaliased function names")
                    if (driver.parent / (path.stem + ".py")).resolve() != path:
                        raise ValueError(f"{driver}: shared module must resolve to {path}")
                    if any(isinstance(n, ast.FunctionDef) and n.name.lower() in specs[path] for n in tree.body):
                        raise ValueError(f"{driver}: local function shadows a shared import")
        if not imports_shared:
            raise ValueError(f"{driver}: no explicit import from the requested shared module(s)")
    work = out_dir / "translation"
    work.mkdir(parents=True)
    generated = {}
    helpers = {}
    for driver in drivers:
        dest = work / driver.stem
        dest.mkdir()
        for path in data:
            shutil.copy2(path, dest / path.name)
        output = dest / (driver.stem + "_p.f90")
        cmd = [sys.executable, str(ROOT / "xp2f.py"), str(driver), "--out", str(output), "--ignore-comments"]
        result = subprocess.run(cmd, cwd=dest, capture_output=True, text=True)
        (dest / "translation.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        if result.returncode:
            raise ValueError(f"translation failed: {driver}\n{result.stdout}{result.stderr}")
        generated[driver.stem] = output.read_text(encoding="utf-8")
        helper_files, _, missing = xp2f.resolve_helper_files_for_build(output, [])
        if missing:
            raise ValueError(f"missing helper sources: {missing}")
        for helper in helper_files:
            path = Path(helper).resolve()
            if path.name.lower() in helpers and helpers[path.name.lower()] != path:
                raise ValueError(f"helper filename collision: {path}")
            helpers[path.name.lower()] = path
        print(f"Translated: {driver.name}", flush=True)
    libraries, apps = split_shared(generated, specs)
    src = out_dir / "src"
    src.mkdir()
    for name, text in libraries.items():
        (src / (name + "_shared.f90")).write_text(text, encoding="utf-8")
    helper_dir = src / "helpers"
    helper_dir.mkdir()
    for helper in helpers.values():
        shutil.copy2(helper, helper_dir / helper.name)
    manifest = ['name = "xp2f-project"', 'version = "0.1.0"', '', '[build]',
                'auto-executables = false', 'auto-tests = false', 'auto-examples = false',
                '', '[fortran]', 'implicit-typing = true', 'implicit-external = true', 'source-form = "free"']
    # Vendored legacy LAPACK uses implicit external interfaces; those settings
    # retain the existing direct-build semantics rather than altering sources.
    for name, text in apps.items():
        app = out_dir / "app" / name
        app.mkdir(parents=True)
        (app / (name + ".f90")).write_text(text, encoding="utf-8")
        manifest += ['', '[[executable]]', f'name = "{name}"',
                     f'source-dir = "app/{name}"', f'main = "{name}.f90"']
    (out_dir / "fpm.toml").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    for path in data:
        if (out_dir / path.name).exists():
            raise ValueError(f"data file collides with generated project content: {path.name}")
        shutil.copy2(path, out_dir / path.name)
    (out_dir / "xp2f-project.json").write_text(json.dumps({
        "drivers": [str(p) for p in drivers], "shared": [str(p) for p in shared],
        "data": [str(p) for p in data], "shared_functions": {p.stem: sorted(names) for p, names in specs.items()},
        "helpers": [str(p) for p in helpers.values()],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Generated FPM project: {out_dir}", flush=True)
    return out_dir


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("drivers", nargs="+", help="Python executable drivers")
    parser.add_argument("--shared", action="append", required=True, help="stateless shared Python module (repeatable)")
    parser.add_argument("--out-dir", required=True, help="new FPM project directory; never overwritten")
    parser.add_argument("--data", action="append", default=[], help="runtime data file copied to project root")
    parser.add_argument("--build", action="store_true", help="also run fpm build")
    parser.add_argument("--compiler", default="gfortran", help="compiler executable; initial build flags target gfortran")
    args = parser.parse_args(argv)
    try:
        dest = generate_project(args.drivers, args.shared, args.out_dir, args.data)
        if args.build:
            cmd = ["fpm", "build", "--compiler", args.compiler, "--flag", "-ffree-line-length-none"]
            result = subprocess.run(cmd, cwd=dest, capture_output=True, text=True)
            (dest / "fpm-build.log").write_text(result.stdout + result.stderr, encoding="utf-8")
            print(result.stdout + result.stderr)
            return result.returncode
    except (ValueError, OSError) as exc:
        print(f"FPM project: FAIL ({exc})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
