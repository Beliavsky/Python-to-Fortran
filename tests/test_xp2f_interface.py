"""Interface extraction must not depend on body translation or execution."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xp2f_interface import InterfaceError, build_contract, main, render


def source(tmp_path, text):
    path = tmp_path / "source.py"
    path.write_text(text, encoding="utf-8")
    return path


def test_no_execution_or_body_translation_and_no_overwrite(tmp_path):
    src = source(tmp_path, "import nonexistent_library\nraise RuntimeError('do not execute')\ndef calculate(x: float) -> float:\n    return nonexistent_library.solve(x)\n")
    output = tmp_path / "contract"
    proc = subprocess.run([sys.executable, str(ROOT / "xp2f_interface.py"), str(src),
                           "calculate", "--out-dir", str(output)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    contract = json.loads((output / "contract.json").read_text())
    assert contract["arguments"][0]["intent"] == "in"
    assert contract["result"]["kind"] == "real"
    stub = output / "implementation.f90"
    stub.write_text("hand edited implementation", encoding="utf-8")
    assert main([str(src), "calculate", "--out-dir", str(output)]) == 1
    assert stub.read_text() == "hand edited implementation"


@pytest.mark.parametrize("text,kwargs,message", [
    ("def f(x): pass", {}, "missing type"),
    ("def f(x: 'float[:]') -> float: pass", {}, "requires --intent"),
    ("def f(x: int) -> 'float[:]': pass", {}, "result-storage"),
    ("def f(x: int) -> float: pass", {"intents": ["x=inout"]}, "scalar x"),
    ("def f(x: int = 2) -> float: pass", {}, "default arguments"),
    ("def f(x: 'float[5]') -> float: pass", {}, "unsupported type"),
    ("def f(x: int) -> tuple[float, float]: pass", {}, "unsupported type"),
    ("def f(x: int) -> float: pass", {"arg_types": ["z=float"]}, "unknown arguments"),
    ("def f(x: int) -> float: pass", {"arg_types": ["x=int", "x=float"]}, "duplicate"),
    ("def f(x: 'float[:]') -> float: pass", {"intents": ["x=other"]}, "invalid intent"),
    ("@deco\ndef f(x: int) -> float: pass", {}, "decorated"),
    ("def f(*x: int) -> float: pass", {}, "ordinary"),
    ("def f(x: int) -> None: pass", {"result_storage": "allocatable"}, "only to array"),
])
def test_reject_ambiguous_contracts(tmp_path, text, kwargs, message):
    with pytest.raises(InterfaceError, match=message):
        build_contract(source(tmp_path, text), "f", **kwargs)


def test_invalid_cli_does_not_create_output(tmp_path):
    src = source(tmp_path, "def f(x): pass")
    output = tmp_path / "invalid"
    assert main([str(src), "f", "--out-dir", str(output)]) == 1
    assert not output.exists()


def test_override_nagarch_signature_and_hash(tmp_path):
    c = build_contract(ROOT / "examples" / "nagarch_t_model.py", "neg_loglik",
                       arg_types=["params=float[:]", "r=float[:]"],
                       intents=["params=in", "r=in"], result_type="float")
    assert [a["rank"] for a in c["arguments"]] == [1, 1]
    assert c["result"]["kind"] == "real"
    src = source(tmp_path, "def f(x: float) -> float: return x")
    first = build_contract(src, "f")
    src.write_text("def f(x: float) -> float: return x + 1", encoding="utf-8")
    assert first["function_ast_sha256"] != build_contract(src, "f")["function_ast_sha256"]


def compile_run(tmp_path, c, implementation=None, driver=None):
    compiler = shutil.which("gfortran")
    if not compiler:
        pytest.skip("gfortran is required")
    interface, stub = render(c)
    (tmp_path / "interface.f90").write_text(interface, encoding="utf-8")
    if implementation:
        stub = stub.replace('error stop "Unimplemented Python procedure"', implementation)
    (tmp_path / "implementation.f90").write_text(stub, encoding="utf-8")
    command = [compiler, "-std=f2008", "-fcheck=all", "interface.f90", "implementation.f90"]
    if driver:
        (tmp_path / "driver.f90").write_text(driver, encoding="utf-8")
        exe = tmp_path / "driver.exe"
        command.extend(["driver.f90", "-o", str(exe)])
    else:
        command.append("-c")
    build = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    if driver:
        return subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True)


@pytest.mark.parametrize("kind", ["float", "int", "bool", "complex"])
def test_scalar_stub_compiles_and_fails_loudly(tmp_path, kind):
    c = build_contract(source(tmp_path, f"def calculate(x: {kind}) -> {kind}: pass"), "calculate", int_kind="int64")
    literal = {"float": "2.0_real64", "int": "2_int64", "bool": ".true.", "complex": "(2.0_real64, 1.0_real64)"}[kind]
    run = compile_run(tmp_path, c, driver=f"program test\nuse {c['fortran_module']}\nuse iso_fortran_env\nprint *, {c['fortran_procedure']}({literal})\nend program\n")
    assert run.returncode != 0
    assert "Unimplemented Python procedure" in run.stdout + run.stderr


def test_array_result_manual_implementation(tmp_path):
    c = build_contract(source(tmp_path, "def twice(x: 'float[:,:]') -> 'float[:,:]': pass"),
                       "twice", intents=["x=in"], result_storage="allocatable")
    run = compile_run(tmp_path, c, "result_value = 2.0_real64 * x", f"program test\nuse {c['fortran_module']}\nuse iso_fortran_env\nreal(real64), allocatable :: y(:,:)\ny = twice(reshape([1.0_real64,2.0_real64,3.0_real64,4.0_real64],[2,2]))\nif (any(shape(y) /= [2,2])) stop 1\nif (any(y /= reshape([2.0_real64,4.0_real64,6.0_real64,8.0_real64],[2,2]))) stop 2\nend program\n")
    assert run.returncode == 0, run.stdout + run.stderr


def test_subroutine_array_mutation(tmp_path):
    c = build_contract(source(tmp_path, "def update(x: 'int[:]', y: 'int[:]') -> None: pass"),
                       "update", intents=["x=inout", "y=out"])
    run = compile_run(tmp_path, c, "x = x + 1\n      y = x", f"program test\nuse {c['fortran_module']}\nuse iso_fortran_env\ninteger(int32) :: x(2) = [1,2], y(2)\ncall update(x,y)\nif (any(x /= [2,3]) .or. any(y /= x)) stop 1\nend program\n")
    assert run.returncode == 0, run.stdout + run.stderr


def test_case_collisions_and_reserved_names_compile(tmp_path):
    c = build_contract(source(tmp_path, "def sum(x: float, X: int, real64: complex, result_value: bool) -> float: pass"), "sum")
    names = [a["fortran_name"] for a in c["arguments"]]
    assert len(set(n.lower() for n in names)) == 4
    assert names[0] != names[1]
    assert names[2] != "real64"
    compile_run(tmp_path, c)


def test_no_argument_subroutine_compiles(tmp_path):
    c = build_contract(source(tmp_path, "def work() -> None: pass"), "work")
    compile_run(tmp_path, c)


@pytest.mark.parametrize("kind", ["int", "bool", "complex"])
def test_other_array_kinds_compile(tmp_path, kind):
    c = build_contract(source(tmp_path, f"def work(x: '{kind}[:,:,:]') -> '{kind}[:,:,:]': pass"),
                       "work", intents=["x=in"], result_storage="allocatable")
    compile_run(tmp_path, c, "result_value = x")


def test_compiler_enforces_contract_for_caller(tmp_path):
    compiler = shutil.which("gfortran")
    if not compiler:
        pytest.skip("gfortran is required")
    c = build_contract(source(tmp_path, "def calculate(x: float) -> float: pass"), "calculate")
    compile_run(tmp_path, c, "result_value = x * x")
    (tmp_path / "bad.f90").write_text(f"program bad\nuse {c['fortran_module']}\nprint *, calculate(.true.)\nend program\n", encoding="utf-8")
    proc = subprocess.run([compiler, "-c", "bad.f90"], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "mismatch" in proc.stderr.lower()
