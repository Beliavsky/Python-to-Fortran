"""Standalone module generation, without synthetic executable callers."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def translate(tmp_path, source, *options):
    path = tmp_path / 'library.py'
    path.write_text(source, encoding='utf-8')
    proc = subprocess.run([sys.executable, str(ROOT / 'xp2f.py'), str(path),
                           '--module', *options], cwd=tmp_path, capture_output=True, text=True)
    return proc, path.with_name('library_p.f90')


def test_module_retains_all_functions(tmp_path):
    proc, output = translate(tmp_path, '''"A library."
def twice(x: float) -> float:
    return 2.0*x
def thrice(x: float) -> float:
    return 3.0*x
''', '--elemental')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text().lower()
    assert 'module library_proc_mod' in text
    assert 'function twice(' in text and 'function thrice(' in text
    assert '\nprogram ' not in text
    assert 'elemental' in text


def test_module_rejects_ambiguous_interface(tmp_path):
    proc, output = translate(tmp_path, 'def twice(x):\n    return 2.0*x\n')
    assert proc.returncode == 1
    assert 'cannot infer argument type/rank for twice.x' in proc.stdout
    assert not output.exists()


@pytest.mark.parametrize('rank_option', ['--assume-scalar', '--elemental'])
def test_module_explicit_assumptions(tmp_path, rank_option):
    proc, output = translate(tmp_path, 'def twice(x):\n    return 2.0*x\n',
                             '--assume-float', rank_option)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'assuming twice.x is real' in proc.stderr
    assert 'real(kind=dp)' in output.read_text().lower()


def test_module_typed_internal_caller(tmp_path):
    proc, output = translate(tmp_path, '''def twice(x):
    return 2*x
def six():
    return twice(3)
def unused(x: float):
    return x+1.0
''')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = output.read_text()
    assert 'function twice(' in text
    assert 'function unused(' in text
    assert 'assuming' not in proc.stderr


@pytest.mark.parametrize('option', ['--run', '--run-both', '--run-diff', '--time'])
def test_module_rejects_execution(tmp_path, option):
    proc, output = translate(tmp_path, 'def f(x: float):\n    return x\n', option)
    assert proc.returncode == 1
    assert 'Invalid options' in proc.stdout
    assert not output.exists()


def test_module_rejects_top_level_execution(tmp_path):
    proc, output = translate(tmp_path, 'def f():\n    return 1\nprint(f())\n')
    assert proc.returncode == 1
    assert 'top-level initialization or driver' in proc.stdout
    assert not output.exists()


def test_module_float_assumption_does_not_imply_scalar(tmp_path):
    proc, output = translate(tmp_path, 'def f(x):\n    return 2*x\n', '--assume-float')
    assert proc.returncode == 1
    assert 'cannot infer argument type/rank' in proc.stdout


def test_module_scalar_assumption_does_not_override_indexing(tmp_path):
    proc, output = translate(tmp_path, 'def f(x):\n    return x[0]\n',
                             '--assume-float', '--assume-scalar')
    assert proc.returncode == 1
    assert 'indexed/attribute use needs an explicit interface' in proc.stdout
    assert not output.exists()


def test_module_rejects_ineligible_elemental_assumption(tmp_path):
    proc, output = translate(tmp_path, 'def f(x):\n    print(x)\n    return x\n',
                             '--assume-float', '--elemental')
    assert proc.returncode == 1
    assert 'not eligible for ELEMENTAL' in proc.stdout
    assert not output.exists()


def test_module_rejects_conflicting_call_evidence(tmp_path):
    proc, output = translate(tmp_path, '''def f(x: float):
    return x
def caller():
    return f(True)
''')
    assert proc.returncode == 1
    assert 'conflicting type/rank evidence' in proc.stdout


def test_module_does_not_treat_reduction_as_elementwise(tmp_path):
    proc, output = translate(tmp_path, 'import numpy as np\ndef f(x):\n    return np.sum(x)\n',
                             '--assume-float', '--elemental')
    assert proc.returncode == 1
    assert 'not eligible for ELEMENTAL rank inference' in proc.stdout
    assert not output.exists()


@pytest.mark.skipif(shutil.which('gfortran') is None, reason='requires gfortran')
def test_module_array_interface_and_external_driver(tmp_path):
    proc, output = translate(tmp_path, '''def twice(x: 'float[:]'):
    return 2.0*x
''', '--compile')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    driver = tmp_path / 'driver.f90'
    driver.write_text('''program driver
use library_proc_mod, only: twice, dp
implicit none
real(dp) :: a(2)
a = twice([1.25_dp, 2.5_dp])
if (any(abs(a - [2.5_dp, 5.0_dp]) > 1e-12_dp)) stop 1
end program
''', encoding='utf-8')
    build = subprocess.run(['gfortran', str(driver), str(output.with_suffix('.o')),
                            '-o', 'driver.exe'], cwd=tmp_path, capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / 'driver.exe')], cwd=tmp_path, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.mark.skipif(shutil.which('gfortran') is None, reason='requires gfortran')
@pytest.mark.parametrize('assume', [False, True])
def test_module_compile_random_library(tmp_path, assume):
    source = '''import numpy as np
def rnorm(n):
    return np.random.normal(size=n)
def twice(x: float):
    return 2.0*x
def thrice(x: float):
    return 3.0*x
'''
    if assume:
        source = source.replace('x: float', 'x')
    proc, output = translate(tmp_path, source, '--compile', '--elemental',
                             *(['--assume-float'] if assume else []))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert output.with_suffix('.o').exists()
    assert (tmp_path / 'library_proc_mod.mod').exists()
    assert not output.with_suffix('.exe').exists()
    if assume:
        assert 'assuming twice.x' in proc.stderr and 'assuming thrice.x' in proc.stderr
        assert 'assuming rnorm.n' not in proc.stderr
    else:
        assert 'assuming' not in proc.stderr
