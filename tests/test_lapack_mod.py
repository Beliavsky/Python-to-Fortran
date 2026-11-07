"""Opt-in modular LAPACK: reproducibility and actual python_mod integration."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest

from xmake_lapack_mod import adapt_runtime, wrap

ROOT = Path(__file__).resolve().parents[1]


def test_lapack_module_matches_generator():
    original = (ROOT / 'lapack_d.f90').read_text(encoding='utf-8')
    module = (ROOT / 'lapack_mod.f90').read_text(encoding='utf-8')
    assert module == wrap(original)
    assert 'module lapack_mod\n' in module
    assert 'external SELECT' in module or 'external select' in module


def test_runtime_adapter_removes_shadowing_external_interfaces():
    runtime = (ROOT / 'python.f90').read_text(encoding='utf-8')
    adapted = adapt_runtime(runtime, (ROOT / 'lapack_d.f90').read_text(encoding='utf-8'))
    for name in ('dgesv', 'dpotrf', 'dgetrf', 'dgetri', 'dgeev', 'dsyev', 'dgeqrf', 'dorgqr', 'dgesvd'):
        assert f'use lapack_mod, only: {name}\n' in adapted
        assert f'subroutine {name}(' not in adapted
    assert 'use lapack_mod' not in runtime  # Default runtime remains independent.


@pytest.mark.parametrize('compiler', ['gfortran', 'ifx'])
@pytest.mark.parametrize('optimization', ['debug', 'optimized'])
def test_modular_lapack_with_python_runtime(tmp_path, compiler, optimization):
    if shutil.which(compiler) is None:
        pytest.skip(f'{compiler} required')
    lapack = (ROOT / 'lapack_d.f90').read_text(encoding='utf-8')
    runtime = tmp_path / 'python_lapack_mod.f90'
    runtime.write_text(adapt_runtime((ROOT / 'python.f90').read_text(encoding='utf-8'), lapack),
                       encoding='utf-8')
    flags = (['-O0', '-g', '-fcheck=all', '-fbacktrace', '-ffree-line-length-none']
             if compiler == 'gfortran' else ['/Od'] if os.name == 'nt' else ['-O0'])
    if optimization == 'optimized':
        # Legacy DLAMC* probes depend on rounded intermediate arithmetic.
        # Intel's default fast FP mode can optimize away DLAMC3's purpose
        # when these routines share a module, making DLAMCH loop forever.
        flags = (['-O3', '-ffree-line-length-none'] if compiler == 'gfortran'
                 else ['/O3', '/fp:precise'] if os.name == 'nt'
                 else ['-O3', '-fp-model', 'precise'])
    # No lapack_d.f90 object is linked: unresolved old external symbols must fail.
    build = subprocess.run([compiler, *flags, str(ROOT / 'lapack_mod.f90'), str(runtime),
                            str(ROOT / 'tests' / 'xpython_lapack_test.f90'), '-o', 'check.exe'],
                           cwd=tmp_path, capture_output=True, text=True, timeout=900)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / 'check.exe')], cwd=tmp_path, capture_output=True,
                         text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'PASS python_mod LAPACK operations' in run.stdout


@pytest.mark.skipif(shutil.which('gfortran') is None, reason='gfortran required')
def test_lapack_driver_with_original_runtime(tmp_path):
    build = subprocess.run(['gfortran', '-O0', '-fcheck=all', '-ffree-line-length-none',
                            str(ROOT / 'python.f90'), str(ROOT / 'lapack_d.f90'),
                            str(ROOT / 'tests' / 'xpython_lapack_test.f90'), '-o', 'check.exe'],
                           cwd=tmp_path, capture_output=True, text=True, timeout=900)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(tmp_path / 'check.exe')], cwd=tmp_path, capture_output=True,
                         text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'PASS python_mod LAPACK operations' in run.stdout
