"""Conservative shared-procedure packaging and an optional real FPM build."""

from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from xp2f_fpm import canonical_procedure, generate_project, shared_functions, split_shared


def fixture_text(module, kind="real(kind=dp)", dummy="x"):
    return f"""module {module}
use, intrinsic :: iso_fortran_env, only: real64
implicit none
integer, parameter :: dp = real64
public :: square
contains
pure function square({dummy}) result(y)
{kind}, intent(in) :: {dummy}
{kind} :: y
y = {dummy} * {dummy}
end function square
end module {module}
program driver
use {module}, only: square
print *, square(2.0_dp)
end program driver
"""


def test_shared_procedure_emitted_once():
    specs = {Path("shared.py"): {"square": None}}
    libs, apps = split_shared({"a": fixture_text("a_mod"), "b": fixture_text("b_mod", dummy="value")}, specs)
    assert libs["shared"].count("pure function square(") == 1
    for text in apps.values():
        assert "use shared_shared_mod, only: square" in text
        assert "function square(" not in text


def test_conflicting_inference_rejected():
    with pytest.raises(ValueError, match="inferred implementations differ"):
        split_shared({"a": fixture_text("a_mod"), "b": fixture_text("b_mod", kind="integer")},
                     {Path("shared.py"): {"square": None}})


def test_comparison_preserves_character_literals():
    a = "function f(x) result(y)\ninteger :: x,y\nprint *, 'X'\ny=x\nend function f"
    assert canonical_procedure(a) != canonical_procedure(a.replace("'X'", "'x'"))


def test_missing_shared_function_rejected():
    with pytest.raises(ValueError, match="No inferred callable"):
        split_shared({"a": fixture_text("a_mod")}, {Path("shared.py"): {"missing": None}})


def test_shared_module_state_rejected(tmp_path):
    path = tmp_path / "shared.py"
    path.write_text("state = 1\ndef f(x):\n    return x + state\n", encoding="utf-8")
    with pytest.raises(ValueError, match="imports and functions only"):
        shared_functions(path)


def test_existing_output_is_not_overwritten(tmp_path):
    source = tmp_path / "a.py"
    source.write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(ValueError, match="already exists"):
        generate_project([source], [source], tmp_path)
    assert source.read_text(encoding="utf-8") == "print(1)\n"


@pytest.mark.skipif(not shutil.which("fpm") or not shutil.which("gfortran"), reason="FPM and gfortran required")
def test_fpm_two_executables_share_one_module(tmp_path):
    shared = tmp_path / "shared.py"
    shared.write_text("def square(x):\n    return x * x\n", encoding="utf-8")
    drivers = []
    for name, value in (("driver_a", 2.0), ("driver_b", 3.0)):
        driver = tmp_path / (name + ".py")
        driver.write_text(f"from shared import square\nprint(square({value}))\n", encoding="utf-8")
        drivers.append(driver)
    project = generate_project(drivers, [shared], tmp_path / "package")
    result = subprocess.run(["fpm", "build", "--compiler", "gfortran", "--flag", "-ffree-line-length-none"],
                            cwd=project, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    for name, value in (("driver_a", 4.0), ("driver_b", 9.0)):
        candidates = [p for p in (project / "build").rglob("*") if p.is_file() and p.name in {name, name + ".exe"}]
        assert len(candidates) == 1
        result = subprocess.run([str(candidates[0])], cwd=project, capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        assert float(result.stdout.strip()) == value
        assert "function square(" not in (project / "app" / name / (name + ".f90")).read_text(encoding="utf-8")
