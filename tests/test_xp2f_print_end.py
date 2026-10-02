"""Regression tests for host constants and nonadvancing scalar output."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_multi_argument_custom_end(tmp_path):
    source = """elapsed = 1.25
print('Execution Time:', elapsed, end=' ')
print('checksum', 42)
print('a', 2, 'b', sep='|', end='!')
print('done')
print('a', 2, 'b', sep='', end='')
print('done')
print('Mercury', 'Venus', sep=', ', end=', ')
print('Earth')
print('flag', True, end=':')
print('done')
print('left', 7, end='\n')
print('right')
""".replace("end='\n'", "end='\\n'")
    src = tmp_path / 'xprint_end.py'
    src.write_text(source, encoding='utf-8')
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'xp2f.py'), str(src), '--compile', '--run-diff'],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'Run diff: MATCH' in proc.stdout, proc.stdout + proc.stderr
    run = subprocess.run([str(tmp_path / 'xprint_end_p.exe')], cwd=tmp_path,
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    lines = run.stdout.splitlines()
    # Check physical lines and exact custom separators, not merely run-diff's
    # whitespace normalization. Real number formatting remains g0-based.
    assert len(lines) == 7, run.stdout
    assert lines[0].startswith('Execution Time: 1.25')
    assert lines[0].split()[-2:] == ['checksum', '42']
    assert lines[1:5] == ['a|2|b!done', 'a2bdone', 'Mercury, Venus, Earth', 'flag True:done']
