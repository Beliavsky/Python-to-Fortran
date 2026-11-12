"""Helper failures must report failure, in either runtime distribution."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fortran_purity


def test_runtime_has_no_normal_stop_statements():
    lines = (ROOT / 'python.f90').read_text(encoding='utf-8').splitlines()
    normal_stops = [(number, statement) for number, statement in
                    fortran_purity.iter_fortran_statements(lines)
                    if re.match(r'^stop(?:\s*$|\s+[\x22\x27\d])',
                                fortran_purity.executable_action(statement), re.I)]
    assert normal_stops == []
    # These are identifiers, not termination statements.
    assert 'function arange_int(start, stop, step)' in '\n'.join(lines)
    assert 'stop = start + ny - 1' in '\n'.join(lines)


@pytest.mark.parametrize('name', ['random_gamma', 'rng_replay_maybe_init', 'loadtxt_real_2d',
                                  'py_omp_set_num_threads'])
def test_side_effecting_helpers_remain_impure(name):
    lines = (ROOT / 'python.f90').read_text(encoding='utf-8').splitlines()
    procedures = [p for p in fortran_purity.parse_procedures(lines) if p.name == name]
    assert len(procedures) == 1
    assert not procedures[0].is_pure_or_elemental


@pytest.fixture(scope='module', params=['runtime', 'extracted'])
def error_probe(request, tmp_path_factory):
    if shutil.which('gfortran') is None:
        pytest.skip('gfortran required')
    directory = tmp_path_factory.mktemp('helper_errors_' + request.param)
    if request.param == 'extracted':
        extracted = subprocess.run(
            [sys.executable, str(ROOT / 'xextract_fortran_lib.py'), '--out', str(directory), '--no-compile'],
            capture_output=True, text=True, check=False)
        assert extracted.returncode == 0, extracted.stdout + extracted.stderr
        module = 'numpy_fortran'
        source = directory / 'numpy_fortran.f90'
    else:
        module = 'python_mod'
        source = ROOT / 'python.f90'
    # Compile the helpers once; reuse them for successful and failing calls.
    build = subprocess.run(
        ['gfortran', '-O0', '-std=f2018', '-ffree-line-length-none', '-c', str(source), '-o', 'helpers.o'],
        cwd=directory, capture_output=True, text=True, timeout=300)
    assert build.returncode == 0, build.stdout + build.stderr
    lapack = subprocess.run(['gfortran', '-O0', '-c', str(ROOT / 'lapack_d.f90'), '-o', 'lapack.o'],
                            cwd=directory, capture_output=True, text=True, timeout=300)
    assert lapack.returncode == 0, lapack.stdout + lapack.stderr
    probe = directory / 'probe.f90'
    probe.write_text((ROOT / "tests" / "fortran_numpy" / "error_probe.f90").read_text(encoding="utf-8")
                     .replace("use numpy_fortran", f"use {module}"), encoding="utf-8")
    link = subprocess.run(['gfortran', '-std=f2018', 'probe.f90', 'helpers.o', 'lapack.o', '-o', 'probe.exe'],
                          cwd=directory, capture_output=True, text=True, timeout=120)
    assert link.returncode == 0, link.stdout + link.stderr
    return directory / 'probe.exe'


@pytest.mark.parametrize('mode, message', [
    ('delete', 'np.delete index out of range'),
    ('gamma', 'random_gamma: shape must be > 0'),
    ('binomial', 'random_binomial: p must be in [0,1]'),
    ('cholesky_shape', 'linalg_cholesky: matrix must be square'),
    ('cholesky_definite', 'linalg_cholesky: matrix is not positive definite'),
])
def test_helper_errors_return_failure(error_probe, mode, message):
    result = subprocess.run([str(error_probe), mode], cwd=error_probe.parent,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0, result.stdout + result.stderr
    assert message in result.stdout + result.stderr
    assert 'REACHED END' not in result.stdout


def test_pure_delete_valid_input(error_probe):
    result = subprocess.run([str(error_probe), 'valid'], cwd=error_probe.parent,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'REACHED END' in result.stdout
