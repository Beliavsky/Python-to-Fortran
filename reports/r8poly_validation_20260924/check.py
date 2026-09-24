"""Validate the original rank-guarded printer and root-polynomial tests."""
import argparse
import ast
import math
from pathlib import Path
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=Path('C:/python/public_domain/burkardt/r8poly/r8poly.py'))
args = parser.parse_args()


def run(command, label, timeout=600):
    proc = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=timeout)
    (OUT / (label + '.stdout')).write_text(proc.stdout, encoding='utf-8')
    (OUT / (label + '.stderr')).write_text(proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


source = args.source.read_text(encoding='utf-8')
functions = [ast.get_source_segment(source, n) for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef)]
probe = OUT / 'corpus_probe.py'
probe.write_text('\n\n'.join(functions) + '''
import numpy as np
roots_to_r8poly_test()
r8vec_even_test()
r8vec_print(2, np.array([1.25, -2.5]), 'real vector')
r8vec_print(2, np.array([[3.75], [-4.5]]), 'real matrix')
r8vec_print(2, np.array([7, -8], dtype=int), 'integer vector')
''', encoding='utf-8')
output = OUT / 'corpus_probe_p.f90'
build = run([sys.executable, str(ROOT / 'xp2f.py'), str(probe),
             '--out', str(output), '--compile', '--report-specializations'], 'build')
assert 'Build: PASS' in build, build
python_output = run([sys.executable, str(probe)], 'python', 60)
fortran_output = run([str(output.with_suffix('.exe'))], 'fortran', 60)


def tokens(text):
    lines = [line for line in text.splitlines() if line.strip()]
    lines = [line for line in lines if 'version' not in line.lower()]
    return re.findall(r'[-+]?\d+(?:\.\d*)?(?:[Ee][-+]?\d+)?|[A-Za-z_]+|[^\s\[\]]', '\n'.join(lines))


py, ft = tokens(python_output), tokens(fortran_output)
assert len(py) == len(ft), f'Token counts differ: {len(py)} / {len(ft)}; inspect logs'
for i, (p, f) in enumerate(zip(py, ft)):
    if p == f:
        continue
    try:
        matches = math.isclose(float(p), float(f), rel_tol=1e-6, abs_tol=1e-10)
    except ValueError:
        matches = False
    assert matches, f'Token {i}: Python {p!r}, Fortran {f!r}'
print(f'MATCH: {len(py)} tokens (version banners/layout excluded; numeric tolerance 1e-6 relative, 1e-10 absolute)')
