from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(shutil.which('gfortran') is None, reason='requires gfortran')


def build(tmp_path, source, *options):
    path = tmp_path / 'sleep_case.py'
    path.write_text(source, encoding='utf-8')
    proc = subprocess.run([sys.executable, str(ROOT / 'xp2f.py'), str(path), *options],
                          cwd=tmp_path, capture_output=True, text=True, timeout=120)
    return proc, path.with_name('sleep_case_p.exe')


@pytest.mark.parametrize('imports, call', [
    ('import time', 'time.sleep'), ('import time as clock', 'clock.sleep'),
    ('from time import sleep as pause', 'pause'),
])
def test_sleep_aliases_fractional_and_zero(tmp_path, imports, call):
    proc, exe = build(tmp_path, f'{imports}\nprint("before")\n{call}(0)\n{call}(0.05)\nprint("after")\n', '--compile')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated = exe.with_suffix('.f90').read_text()
    assert 'call py_sleep(' in generated
    assert 'time_sleep_mod' in generated
    started = time.monotonic()
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert time.monotonic() - started >= 0.045
    assert run.returncode == 0, run.stdout + run.stderr
    assert run.stdout.split() == ['before', 'after']


def test_sleep_inside_function_is_impure(tmp_path):
    proc, exe = build(tmp_path, 'import time\ndef pause(seconds: float):\n    time.sleep(seconds)\npause(0.001)\n', '--compile')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    generated = exe.with_suffix('.f90').read_text().lower()
    assert 'pure subroutine pause' not in generated
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert run.returncode == 0, run.stdout + run.stderr


@pytest.mark.parametrize('duration, message', [('-0.001', 'nonnegative'),
                                            ('float("nan")', 'finite'),
                                            ('float("inf")', 'finite'),
                                            ('1e20', 'too large')])
def test_sleep_invalid_duration_stops(tmp_path, duration, message):
    proc, exe = build(tmp_path, f'import time\ntime.sleep({duration})\nprint("unreachable")\n', '--compile')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    run = subprocess.run([str(exe)], cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert run.returncode != 0
    assert message in run.stdout + run.stderr
    assert 'unreachable' not in run.stdout


@pytest.mark.parametrize('call', ['time.sleep()', 'time.sleep(0, 1)', 'time.sleep(secs=0)',
                                 'time.sleep("0")', 'time.sleep([0.0])'])
def test_sleep_invalid_signature_diagnosed(tmp_path, call):
    proc, _ = build(tmp_path, f'import time\n{call}\n')
    assert proc.returncode == 1
    assert 'time.sleep requires' in proc.stdout


def test_sleep_original_example_compiles(tmp_path):
    proc, _ = build(tmp_path, (ROOT / 'examples' / 'xtime_sleep.py').read_text(), '--compile')
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_posix_helper_syntax(tmp_path):
    proc = subprocess.run(['gfortran', '-c', str(ROOT / 'time_sleep_posix.f90'), '-o', 'posix.o'],
                          cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
