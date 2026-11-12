"""Compile checked-in Fortran programs against the extracted module only."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from test_fortran_numpy_library import (assert_series_output, assert_roots_output,
                                       assert_standalone_output)

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'tests' / 'fortran_numpy'
SOURCES = sorted(CASES.glob('*.f90'))
CHECKS = {'polynomial_series': assert_series_output,
          'polynomial_roots': assert_roots_output,
          'standalone': assert_standalone_output}


def checked(command, cwd, timeout=300):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, f'{command}\n{result.stdout}{result.stderr}'
    return result


@pytest.fixture(scope='module')
def library(tmp_path_factory):
    if shutil.which('gfortran') is None:
        pytest.skip('gfortran required')
    build = tmp_path_factory.mktemp('numpy_fortran_cases')
    checked([sys.executable, str(ROOT / 'xextract_fortran_lib.py'), '--out', str(build),
             '--no-compile'], build)
    # Do not compile or link python.f90: this verifies the standalone library.
    checked(['gfortran', '-std=f2018', '-O0', '-g', '-fcheck=all',
             '-ffree-line-length-none', '-c', 'numpy_fortran.f90', '-o', 'numpy_fortran.o'], build)
    # Bundled legacy LAPACK is built without the modern-language restriction.
    checked(['gfortran', '-O0', '-c', str(ROOT / 'lapack_d.f90'), '-o', 'lapack.o'], build)
    return build


def compile_case(source, library, destination):
    executable = destination / (source.stem + '.exe')
    checked(['gfortran', '-std=f2018', '-O0', '-g', '-fcheck=all', '-fbacktrace',
             '-ffree-line-length-none', '-I', str(library), str(source),
             str(library / 'numpy_fortran.o'), str(library / 'lapack.o'),
             '-o', str(executable)], destination)
    return executable


@pytest.mark.parametrize('source', SOURCES, ids=lambda source: source.stem)
def test_standalone_program(source, library, tmp_path):
    executable = compile_case(source, library, tmp_path)
    args = ['valid'] if source.stem == 'error_probe' else []
    result = checked([str(executable), *args], tmp_path, timeout=30)
    if source.stem in CHECKS:
        CHECKS[source.stem](result.stdout)
    elif source.stem == 'elemental_arrays':
        assert 'PASS elemental arrays' in result.stdout
    elif source.stem == 'error_probe':
        assert 'REACHED END' in result.stdout
    else:
        # pure_numerical_helpers uses ERROR STOP assertions, including inside
        # a PURE caller, so successful termination is its result check.
        assert source.stem == 'pure_numerical_helpers'


@pytest.fixture(scope='module')
def error_executable(library, tmp_path_factory):
    return compile_case(CASES / 'error_probe.f90', library,
                        tmp_path_factory.mktemp('numpy_error_probe'))


@pytest.mark.parametrize('mode, message', [
    ('delete', 'np.delete index out of range'),
    ('gamma', 'random_gamma: shape must be > 0'),
    ('binomial', 'random_binomial: p must be in [0,1]'),
    ('cholesky_shape', 'linalg_cholesky: matrix must be square'),
    ('cholesky_definite', 'linalg_cholesky: matrix is not positive definite'),
])
def test_standalone_error(error_executable, mode, message):
    result = subprocess.run([str(error_executable), mode], cwd=error_executable.parent,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, result.stdout + result.stderr
    assert message in result.stdout + result.stderr
    assert 'REACHED END' not in result.stdout
