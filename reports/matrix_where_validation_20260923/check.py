"""Check matrix-where lowering and deterministic Burkardt integrand values."""
import ast
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    'C:/python/public_domain/burkardt/test_int_2d/test_int_2d.py')


def run(source, name):
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'xp2f.py'), str(source), '--compile', '--run-diff'],
        cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT / (name + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0 and 'Run diff: MATCH' in proc.stdout, proc.stdout + proc.stderr
    return 'MATCH'


results = {'probe': run(OUT / 'probe.py', 'probe')}
source = SOURCE.read_text(encoding='utf-8')
names = {'p00_fun'} | {f'p{i:02d}_fun' for i in range(1, 9)}
functions = [ast.get_source_segment(source, n) for n in ast.parse(source).body
             if isinstance(n, ast.FunctionDef) and n.name in names]
assert len(functions) == 9
driver = '''
import numpy as np
x = np.array([0.0, 0.25, 1.0, 0.5, 1.0, 0.0])
y = np.array([0.0, 0.5, 1.0, 0.25, 1.0, 0.5])
xm = np.reshape(x, (2, 3))
ym = np.reshape(y, (2, 3))
for problem in range(1, 9):
    v = p00_fun(problem, x, y)
    m = p00_fun(problem, xm, ym)
    for k in range(6):
        print(problem, k, v[k])
    for r in range(2):
        for c in range(3):
            print(problem, r, c, m[r,c])
'''
probe = OUT / 'corpus_probe.py'
probe.write_text('\n\n'.join(functions) + '\n' + driver, encoding='utf-8')
results['eight_integrands_vector_and_matrix'] = run(probe, 'corpus_probe')
proc = subprocess.run([sys.executable, str(ROOT / 'xp2f.py'), str(SOURCE),
                       '--out', str(OUT / 'test_int_2d_p.f90'), '--compile'],
                      cwd=OUT, capture_output=True, text=True, timeout=300)
(OUT / 'full_compile.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
assert proc.returncode == 0, proc.stdout + proc.stderr
results['full_compile'] = 'PASS'
(OUT / 'analysis.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
