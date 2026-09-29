from pathlib import Path
import os
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import xp2f


def helper(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    return str(path)


def test_transitive_order_and_use_syntax(tmp_path):
    leaf = helper(tmp_path, 'leaf.f90', 'module leaf_mod\nend module\n')
    middle = helper(tmp_path, 'middle.f90', 'module middle_mod\nuse, non_intrinsic :: &\n & LEAF_MOD\nend module\n')
    top = helper(tmp_path, 'top.f90', 'module top_mod\nuse :: middle_mod\nuse, intrinsic :: iso_fortran_env\nend module\n')
    ordered, prerequisites = xp2f._order_helper_files([top, middle, leaf])
    assert ordered == [leaf, middle, top]
    assert prerequisites[top] == {leaf, middle}


def test_bundled_modules_and_source_aliases(tmp_path, monkeypatch):
    bundled = helper(tmp_path, 'bundle.f90', 'module a\nend module\nmodule b\nuse a\nend module\n')
    user = helper(tmp_path, 'user.f90', 'module consumer\nuse b\nend module\n')
    monkeypatch.chdir(tmp_path)
    ordered, _ = xp2f._order_helper_files([user, bundled, './bundle.f90', 'libx.a', 'libx.a'])
    assert ordered == [bundled, user, 'libx.a', 'libx.a']


def test_unknown_modules_remain_compiler_resolved(tmp_path):
    path = helper(tmp_path, 'user.f90', 'module consumer\nuse vendor_mod\nend module\n')
    assert xp2f._order_helper_files([path])[0] == [path]


def test_cycles_reported_before_compiler(tmp_path, monkeypatch):
    a = helper(tmp_path, 'a.f90', 'module a\nuse b\nend module\n')
    b = helper(tmp_path, 'b.f90', 'module b\nuse a\nend module\n')
    monkeypatch.setattr(xp2f.subprocess, 'run', lambda *a, **kw: pytest.fail('compiler should not run'))
    inputs, proc, _ = xp2f._prepare_helper_link_inputs([a, b], ['gfortran'])
    assert inputs is None and proc.returncode == 1
    assert 'dependency cycle' in proc.stderr
    assert 'a.f90' in proc.stderr and 'b.f90' in proc.stderr


def test_duplicate_providers_diagnosed(tmp_path):
    a = helper(tmp_path, 'a.f90', 'module shared\nend module\n')
    b = helper(tmp_path, 'b.f90', 'module shared\nend module\n')
    with pytest.raises(ValueError, match='multiple helpers provide'):
        xp2f._order_helper_files([a, b])


def test_vendored_bridge_order():
    paths = [str(ROOT / name) for name in ('lbfgsb_bridge.f90', 'powell_bridge.f90', 'lbfgsb.f90', 'fmin.f90')]
    ordered, _ = xp2f._order_helper_files(paths)
    assert ordered.index(paths[2]) < ordered.index(paths[0])
    assert ordered.index(paths[3]) < ordered.index(paths[1])


@pytest.mark.skipif(shutil.which('gfortran') is None, reason='requires gfortran')
def test_cold_and_warm_cache_dependency_rebuild(tmp_path, monkeypatch, capsys):
    dependency = helper(tmp_path, 'base.f90', 'module base_mod\ninteger, parameter :: value=1\nend module\n')
    consumer = helper(tmp_path, 'consumer.f90', 'module consumer_mod\nuse base_mod\ninteger, parameter :: answer=value\nend module\n')
    monkeypatch.chdir(tmp_path)
    objects, proc, _ = xp2f._prepare_helper_link_inputs([consumer, dependency], ['gfortran', '-O0'])
    assert proc is None, proc.stderr if proc else ''
    assert objects == ['base.o', 'consumer.o']
    assert (tmp_path / 'base_mod.mod').exists() and (tmp_path / 'consumer_mod.mod').exists()
    capsys.readouterr()
    assert xp2f._prepare_helper_link_inputs([consumer, dependency], ['gfortran', '-O0'])[1] is None
    assert 'Build helper:' not in capsys.readouterr().out
    # Force both the live cache and per-flags cache to be stale through a dependency.
    newer = (tmp_path / 'consumer.o').stat().st_mtime + 1
    os.utime(dependency, (newer, newer))
    assert xp2f._prepare_helper_link_inputs([consumer, dependency], ['gfortran', '-O0'])[1] is None
    assert capsys.readouterr().out.count('Build helper:') == 2


@pytest.mark.skipif(shutil.which('gfortran') is None, reason='requires gfortran')
@pytest.mark.parametrize('method', ['L-BFGS-B', 'Powell'])
def test_optimizer_bridge_cold_build(tmp_path, method):
    source = tmp_path / 'fit.py'
    code = '''from scipy.optimize import minimize
def objective(x):
    return (x[0] - 1.0)**2 + (x[1] - 2.5)**2
res = minimize(objective, [0.0, 0.0], method="METHOD")
print(res.x[0])
print(res.x[1])
print(res.fun)
'''.replace('METHOD', method)
    if method == 'L-BFGS-B':
        code = (ROOT / 'examples' / 'xlbfgsb.py').read_text(encoding='utf-8')
    source.write_text(code, encoding='utf-8')
    proc = subprocess.run([sys.executable, str(ROOT / 'xp2f.py'), str(source), '--compile',
                           '--compiler', 'gfortran -O0 -g -fcheck=all -fbacktrace'],
                          cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    solver, bridge = ('lbfgsb', 'lbfgsb_bridge') if method == 'L-BFGS-B' else ('fmin', 'powell_bridge')
    builds = [line for line in proc.stdout.splitlines() if line.startswith('Build helper:')]
    assert next(i for i, line in enumerate(builds) if f'{solver}.f90' in line) < next(
        i for i, line in enumerate(builds) if f'{bridge}.f90' in line)
    run = subprocess.run([str(source.with_name('fit_p.exe'))], cwd=tmp_path,
                         capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stdout + run.stderr
    values = [float(line) for line in run.stdout.splitlines() if line.strip()]
    assert values == pytest.approx([1.0, 2.5, 0.0], abs=1e-5)
