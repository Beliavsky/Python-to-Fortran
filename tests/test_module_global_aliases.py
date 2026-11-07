"""Shared Python names must have one spelling in every Fortran scope."""
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('int_kind', [None, 'int64'])
def test_leading_underscore_shared_array(tmp_path, int_kind):
    source = tmp_path / 'xshared_names.py'
    source.write_text('''__all__ = ["first", "second"]
v_all__ = 17
def show():
    print(__all__[0], __all__[1])
show()
print(v_all__)
''', encoding='utf-8')
    command = [sys.executable, str(ROOT / 'xp2f.py'), str(source), '--compile', '--run-diff']
    if int_kind:
        command += ['--int-kind', int_kind]
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'Run diff: MATCH' in result.stdout, result.stdout + result.stderr
