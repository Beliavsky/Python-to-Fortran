"""Generate a checked Fortran contract and stub, without translating Python bodies."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

from xp2f import FORTRAN_RESERVED_IDENTIFIERS, annotation_type_spec


class InterfaceError(ValueError):
    """A signature cannot safely be represented by this initial interface tool."""


def parse_type(text: str) -> dict:
    # Deliberately narrower than the transpiler's inference: dimensions here are
    # contractual ranks, not guessed from expressions or dimension comments.
    text = text.strip()
    if text == "None":
        return {"kind": "void", "rank": 0}
    if not re.fullmatch(
        r"(?:float|double|real|int|integer|bool|complex)(?:\[\s*:\s*(?:,\s*:\s*)*\])?",
        text,
    ):
        raise InterfaceError(f"unsupported type {text!r}; use float, int, bool, complex, or e.g. float[:,:]")
    kind, rank, _ = annotation_type_spec(ast.Constant(value=text))
    if rank > 15:
        raise InterfaceError("Fortran supports at most 15 array dimensions")
    return {"kind": kind, "rank": rank}


def overrides(items: list[str], label: str) -> dict[str, str]:
    result = {}
    for item in items:
        name, sep, value = item.partition("=")
        name, value = name.strip(), value.strip()
        if not sep or not name or not value or name in result:
            raise InterfaceError(f"invalid or duplicate {label}: {item!r}; expected NAME=VALUE")
        result[name] = value
    return result


def annotated_type(annotation: ast.expr | None, override: str | None, label: str) -> dict:
    if override is not None:
        return parse_type(override)
    if annotation is None:
        raise InterfaceError(f"missing type for {label}; supply an annotation or explicit override")
    text = annotation.value if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str) else ast.unparse(annotation)
    return parse_type(text)


def safe_name(name: str, used: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9_]", "_", name.lower())
    if not stem or not stem[0].isalpha():
        stem = "py_" + stem
    stem = stem[:50]
    candidate, index = stem, 1
    while candidate in used:
        candidate = f"{stem}_{index}"
        index += 1
    used.add(candidate)
    return candidate


def build_contract(source: Path, function: str, *, arg_types: list[str] = (),
                   intents: list[str] = (), result_type: str | None = None,
                   result_storage: str | None = None, int_kind: str = "int32") -> dict:
    if int_kind not in {"int32", "int64"}:
        raise InterfaceError("integer kind must be int32 or int64")
    text = source.read_text(encoding="utf-8-sig")
    tree = ast.parse(text, filename=str(source))
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == function]
    if len(matches) != 1:
        raise InterfaceError(f"expected one top-level definition of {function!r}, found {len(matches)}")
    fn = matches[0]
    if isinstance(fn, ast.AsyncFunctionDef) or fn.decorator_list:
        raise InterfaceError("async functions and decorated functions are not supported")
    args = fn.args
    if args.vararg or args.kwarg or args.posonlyargs or args.kwonlyargs:
        raise InterfaceError("only ordinary positional-or-keyword parameters are supported")
    if args.defaults:
        raise InterfaceError("default arguments are not yet supported; expose a wrapper with explicit arguments")
    types, intent_map = overrides(arg_types, "argument type"), overrides(intents, "intent")
    names = {a.arg for a in args.args}
    unknown = (types.keys() | intent_map.keys()) - names
    if unknown:
        raise InterfaceError("unknown arguments: " + ", ".join(sorted(unknown)))
    used = {s.lower() for s in FORTRAN_RESERVED_IDENTIFIERS} | {"real64", "int32", "int64", "result_value"}
    procedure = safe_name(function, used)
    module = safe_name(procedure + "_interface_mod", used)
    implementation = safe_name(procedure + "_implementation", used)
    parameters = []
    for arg in args.args:
        spec = annotated_type(arg.annotation, types.get(arg.arg), arg.arg)
        if spec["kind"] == "void":
            raise InterfaceError(f"argument {arg.arg} cannot have type None")
        intent = intent_map.get(arg.arg)
        if spec["rank"] and intent is None:
            raise InterfaceError(f"array {arg.arg} requires --intent {arg.arg}=in|out|inout")
        intent = intent or "in"
        if intent not in {"in", "out", "inout"}:
            raise InterfaceError(f"invalid intent {intent!r} for {arg.arg}")
        if not spec["rank"] and intent != "in":
            raise InterfaceError(f"scalar {arg.arg} must be intent(in); return modified scalar values instead")
        parameters.append(dict(spec, python_name=arg.arg, fortran_name=safe_name(arg.arg, used),
                               intent=intent, type_source="override" if arg.arg in types else "annotation"))
    result = annotated_type(fn.returns, result_type, "result (--result)")
    if result["rank"]:
        if result_storage != "allocatable":
            raise InterfaceError("array result requires --result-storage allocatable")
    elif result_storage is not None:
        raise InterfaceError("--result-storage applies only to array results")
    result.update(storage=result_storage, fortran_name="result_value",
                  type_source="override" if result_type is not None else "annotation")
    return dict(schema_version=1, source=str(source.resolve()), python_function=function,
                function_ast_sha256=hashlib.sha256(ast.dump(fn, include_attributes=False).encode()).hexdigest(),
                fortran_procedure=procedure, fortran_module=module,
                fortran_submodule=implementation, integer_kind=int_kind,
                real_kind="real64", arguments=parameters, result=result,
                limitations=["No source execution, body translation, caller inference, or behavioral verification.",
                             "Type overrides and array intents are user assertions.",
                             "Arrays have assumed shape and lower bound 1; inout arrays cannot be resized.",
                             "Array result extents, allocation and aliasing semantics are the implementer's responsibility.",
                             "Integer arithmetic is fixed-width, unlike Python integers.",
                             "No pure/elemental promise, C ABI, f2py wrapper, or automatic caller integration.",
                             "The source hash records provenance; automatic stale-contract checking is not implemented."])


def declaration(spec: dict, int_kind: str, *, result: bool = False) -> str:
    dtype = {"real": "real(real64)", "int": f"integer({int_kind})",
             "complex": "complex(real64)", "logical": "logical"}[spec["kind"]]
    attributes = ", allocatable" if result and spec["rank"] else ""
    if not result:
        attributes += f", intent({spec['intent']})"
    shape = "(" + ",".join(":" for _ in range(spec["rank"])) + ")" if spec["rank"] else ""
    return f"{dtype}{attributes} :: {spec['fortran_name']}{shape}"


def render(contract: dict) -> tuple[str, str]:
    c = contract
    name, module = c["fortran_procedure"], c["fortran_module"]
    is_function = c["result"]["kind"] != "void"
    category = "function" if is_function else "subroutine"
    suffix = " result(result_value)" if is_function else ""
    header = f"      module {category} {name}("
    if c["arguments"]:
        header += "&\n" + ", &\n".join("         " + a["fortran_name"] for a in c["arguments"])
    header += ")" + suffix
    lines = ["! Generated interface contract; implementation lives in a separate submodule.",
             f"module {module}", "   use, intrinsic :: iso_fortran_env, only: real64, int32, int64",
             "   implicit none", "   private", f"   public :: {name}", "   interface", header]
    lines.extend("         " + declaration(a, c["integer_kind"]) for a in c["arguments"])
    if is_function:
        lines.append("         " + declaration(c["result"], c["integer_kind"], result=True))
    lines.extend([f"      end {category} {name}", "   end interface", f"end module {module}", ""])
    stub = [f"submodule ({module}) {c['fortran_submodule']}", "   implicit none", "contains",
            f"   module procedure {name}",
            "      ! TODO: implement the Python semantics. Arguments/result are inherited.",
            "      ! Review contract.json; allocate array results before assigning elements.",
            '      error stop "Unimplemented Python procedure"',
            f"   end procedure {name}", f"end submodule {c['fortran_submodule']}", ""]
    return "\n".join(lines), "\n".join(stub)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("function", help="top-level Python function")
    parser.add_argument("--out-dir", type=Path, required=True, help="new directory; existing directories are never overwritten")
    parser.add_argument("--arg", action="append", default=[], metavar="NAME=TYPE", help="explicit type override, e.g. x=float[:]")
    parser.add_argument("--intent", action="append", default=[], metavar="NAME=INTENT", help="required for arrays: in, out, inout")
    parser.add_argument("--result", help="result type override; None for subroutines")
    parser.add_argument("--result-storage", choices=["allocatable"])
    parser.add_argument("--int-kind", choices=["int32", "int64"], default="int32")
    args = parser.parse_args(argv)
    try:
        contract = build_contract(args.source, args.function, arg_types=args.arg, intents=args.intent,
                                  result_type=args.result, result_storage=args.result_storage, int_kind=args.int_kind)
        interface, stub = render(contract)
        # Validate everything before creating output, and never overwrite manual work.
        args.out_dir.mkdir(parents=True, exist_ok=False)
        (args.out_dir / "interface.f90").write_text(interface, encoding="utf-8")
        (args.out_dir / "implementation.f90").write_text(stub, encoding="utf-8")
        (args.out_dir / "contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    except (OSError, SyntaxError, InterfaceError) as exc:
        print(f"Interface: FAIL ({exc})")
        return 1
    print(f"Interface: PASS ({args.out_dir})")
    print("Generated interface.f90, implementation.f90, contract.json; implement the stub before use.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
