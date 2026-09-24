"""Validate unchanged divided-difference kernels, isolated from dif_value."""
import argparse
import ast
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/divdif/divdif.py'))
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    text = args.source.read_text(encoding='utf-8')
    names = {'data_to_dif', 'data_to_r8poly', 'dif_to_r8poly', 'r8vec_is_distinct'}
    functions = [ast.get_source_segment(text, node) for node in ast.parse(text).body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(functions) == len(names)
    driver = '''
import numpy as np
x = np.array([-1.0, 0.0, 2.0])
y = 1.25 - 0.5 * x + 2.0 * x * x
d = data_to_dif(3, x, y)
c = data_to_r8poly(3, x, y)
for i in range(3):
    print(d[i], c[i], x[i], y[i])
'''
    probe = work / 'probe.py'
    probe.write_text('\n\n'.join(functions) + driver, encoding='utf-8')
    py = subprocess.run([sys.executable, str(probe)], cwd=work,
                        capture_output=True, text=True, timeout=60)
    assert py.returncode == 0, py.stdout + py.stderr
    expected = [3.75, 1.25, -1.0, 3.75, -2.5, -0.5, 0.0, 1.25, 2.0, 2.0, 2.0, 8.25]
    assert list(map(float, py.stdout.split())) == expected, py.stdout
    proc = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(probe),
                           '--compile', '--run-diff'], cwd=work,
                          capture_output=True, text=True, timeout=300)
    (out / 'run.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0 and 'Run diff: MATCH' in proc.stdout, proc.stdout + proc.stderr
    print('PASS: original kernels match Python and known polynomial coefficients; input arrays unchanged')


if __name__ == '__main__':
    main()
