"""Elemental helpers retain scalar behavior and accept conformable arrays."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
NEW_ELEMENTALS = '''isqrt_int mod_pow_int factorial_int factorial_int_i64 comb_int comb_int_i64
perm_int perm_int_i64 preprocess_line count_tokens loadtxt_rank_stop optval_int optval_real
optval_complex optval_logical vm_integral le_nan_last complex_nan_before pct char_in_set
starts_with ends_with str_find str_rfind str_reverse py_affix_bounds append_strvec str_split
str_count str_isdigit str_isalpha str_isalnum str_isspace isclose_scalar_real fft_is_power_of_two
py_int int_text dcpabs'''.split()


def test_runtime_elemental_declarations():
    source = (ROOT / 'python.f90').read_text(encoding='utf-8')
    for name in NEW_ELEMENTALS:
        assert re.search(rf'^\s*pure\s+elemental\s+[^\n]*\b(function|subroutine)\s+{name}\s*\(',
                         source, re.I | re.M), name
    assert not re.search(r'^\s*elemental\b', source, re.I | re.M)


RUNTIME_CHECKS = '''
if (any(optval([1,2], 0) /= [1,2])) error stop 'present optional array'
if (any(optval(default=[4,5]) /= [4,5])) error stop 'absent optional array'
if (optval(default=7) /= 7) error stop 'absent optional scalar'
if (any(abs(optval(default=[1.5_dp,2.5_dp])-[1.5_dp,2.5_dp]) > 1e-12_dp)) error stop 'real optional'
if (.not. all(optval(default=[.true.,.false.]) .eqv. [.true.,.false.])) error stop 'logical optional'
if (any(py_int(['12','-3']) /= [12,-3])) error stop 'parse integers'
if (any(str_reverse(['abc','xyz']) /= ['cba','zyx'])) error stop 'reverse strings'
if (any(str_find(['abab','baba'], 'ab') /= [0,1])) error stop 'find strings'
if (any(str_rfind(['abab','baba'], 'ab') /= [2,1])) error stop 'reverse find strings'
if (any(str_count(['abab','baba'], 'ab') /= [2,1])) error stop 'count strings'
if (.not. all(starts_with(['abab','abzz'], 'ab'))) error stop 'prefix strings'
if (.not. all(ends_with(['abab','zzab'], 'ab'))) error stop 'suffix strings'
if (.not. all(str_isdigit(['12','34']))) error stop 'digit strings'
if (.not. all(str_isalpha(['ab','XY']))) error stop 'alpha strings'
if (.not. all(str_isalnum(['a1','b2']))) error stop 'alnum strings'
if (.not. all(str_isspace(['  ',achar(9)//achar(10)]))) error stop 'space strings'
parts = str_split(['a,b','c,d'], ',')
if (size(parts(1)%v) /= 2 .or. size(parts(2)%v) /= 2) error stop 'split shapes'
if (any(parts(1)%v /= ['a','b']) .or. any(parts(2)%v /= ['c','d'])) error stop 'split values'
'''


@pytest.mark.skipif(shutil.which('gfortran') is None, reason='gfortran required')
@pytest.mark.parametrize('module', ['python_mod', 'numpy_fortran'])
def test_elemental_array_calls(tmp_path, module):
    if module == 'numpy_fortran':
        extracted = subprocess.run(
            [sys.executable, str(ROOT / 'xextract_fortran_lib.py'), '--out', str(tmp_path), '--no-compile'],
            capture_output=True, text=True, check=False)
        assert extracted.returncode == 0, extracted.stdout + extracted.stderr
        runtime = tmp_path / 'numpy_fortran.f90'
    else:
        runtime = ROOT / 'python.f90'
    program = tmp_path / 'elemental.f90'
    text = (ROOT / "tests" / "fortran_numpy" / "elemental_arrays.f90").read_text(encoding="utf-8")
    if module == "python_mod":
        text = text.replace("use numpy_fortran", "use python_mod")
        text = text.replace("pure subroutine checks()", "pure subroutine checks()\ntype(strvec_t) :: parts(2)")
        text = text.replace("end subroutine checks", RUNTIME_CHECKS + "\nend subroutine checks")
    program.write_text(text, encoding="utf-8")
    lapack = subprocess.run(['gfortran', '-O0', '-c', str(ROOT / 'lapack_d.f90'), '-o', 'lapack.o'],
                            cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert lapack.returncode == 0, lapack.stdout + lapack.stderr
    build = subprocess.run(
        ['gfortran', '-std=f2018', '-ffree-line-length-none', '-O0', '-fcheck=all',
         str(runtime), str(program), 'lapack.o', '-o', 'elemental.exe'],
        cwd=tmp_path, capture_output=True, text=True, timeout=300)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / 'elemental.exe')], cwd=tmp_path,
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'PASS elemental arrays' in run.stdout
