"""Compile the standalone runtime tests without using the transpiler."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module', params=['gfortran', 'ifx'])
def compiled_runtime(request, tmp_path_factory):
    compiler = request.param
    if shutil.which(compiler) is None:
        pytest.skip(f'{compiler} required')
    tmp_path = tmp_path_factory.mktemp(f'xpython_runtime_{compiler}')
    flags = ['-O0', '-g', '-ffree-line-length-none', '-fcheck=all', '-fbacktrace'] if compiler == 'gfortran' else ['-O0']
    objects = []
    # Compile the large helpers once, then reuse them for varied problem sizes.
    for name in ('python', 'lapack_d'):
        obj = tmp_path / f'{name}.o'
        build = subprocess.run([compiler, *flags, '-c', str(ROOT / f'{name}.f90'), '-o', str(obj)],
                               cwd=tmp_path, capture_output=True, text=True, timeout=300)
        assert build.returncode == 0, build.stdout + build.stderr
        objects.append(str(obj))
    return compiler, flags, objects, tmp_path


def build_and_run(tmp_path, compiled_runtime, sizes):
    compiler, flags, objects, runtime_dir = compiled_runtime
    source = (ROOT / 'xpython.f90').read_text(encoding='utf-8')
    for name, value in sizes.items():
        source, count = re.subn(rf'(integer, parameter :: {name}\s*=\s*)\d+',
                                rf'\g<1>{value}', source)
        assert count == 1, name
    src = tmp_path / 'xpython.f90'
    src.write_text(source, encoding='utf-8')
    exe = tmp_path / 'xpython.exe'
    build = subprocess.run([compiler, *flags, *objects, str(src), '-o', str(exe)],
                           cwd=runtime_dir, capture_output=True, text=True, timeout=120)
    assert build.returncode == 0, build.stdout + build.stderr
    return subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize('sizes', [
    pytest.param({}, id='default'),
    pytest.param(dict(n_stats=2, n_array=1, n_random=1, n_fft=1, n_matrix=1,
                      n_lstsq_rows=1, n_lstsq_cols=1, n_grid=2, n_quadrature=1), id='minimum'),
    pytest.param(dict(n_stats=7, n_array=9, n_random=23, n_fft=10, n_matrix=8,
                      n_lstsq_rows=13, n_lstsq_cols=5, n_grid=10, n_quadrature=3), id='varied-non-power-two'),
    pytest.param(dict(n_fft=7), id='odd-real-fft'),
])
def test_standalone_python_runtime(tmp_path, compiled_runtime, sizes):
    run = build_and_run(tmp_path, compiled_runtime, sizes)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'PASS python_mod standalone tests' in run.stdout
    assert '; failures: 0' in run.stdout


def test_invalid_problem_sizes_rejected(tmp_path, compiled_runtime):
    run = build_and_run(tmp_path, compiled_runtime, dict(n_stats=1))
    assert run.returncode != 0
    assert 'Invalid problem sizes:' in run.stdout
    assert 'scalar helpers checked' not in run.stdout
