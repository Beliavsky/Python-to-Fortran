"""Validate original divided-difference kernels and an adapted fixed-rank evaluator."""
import argparse
import ast
import copy
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
    # Deliberately adapted API, NOT a validation of the original dif_value:
    # keep vector results even for length one, with a separate scalar wrapper.
    evaluator = copy.deepcopy(next(node for node in ast.parse(text).body
                                   if isinstance(node, ast.FunctionDef) and node.name == 'dif_value'))
    evaluator.name = 'dif_value_vector'
    assert isinstance(evaluator.body[-2], ast.If)
    assert ast.unparse(evaluator.body[-2]) == 'if nv == 1:\n    yv = yv[0]'
    evaluator.body.pop(-2)
    normalization = [node for node in evaluator.body if isinstance(node, ast.Assign)
                     and ast.unparse(node) == 'xv = np.atleast_1d(xv)']
    assert len(normalization) == 1
    evaluator.body.remove(normalization[0])
    functions.append(ast.unparse(evaluator))
    functions.append('''def dif_value_scalar(nd, xd, yd, x):
    xv = np.array([x])
    result = dif_value_vector(nd, xd, yd, xv)
    return result[0]
''')
    driver = '''
import numpy as np
x = np.array([-1.0, 0.0, 2.0])
y = 1.25 - 0.5 * x + 2.0 * x * x
d = data_to_dif(3, x, y)
c = data_to_r8poly(3, x, y)
for i in range(3):
    print(d[i], c[i], x[i], y[i])
empty = dif_value_vector(3, x, d, np.array([], dtype=float))
print(empty.size)
singleton = dif_value_vector(3, x, d, np.array([0.0]))
print(singleton.size, singleton[0])
vector = dif_value_vector(3, x, d, x)
print(vector.size)
for i in range(3):
    print(vector[i], dif_value_scalar(3, x, d, x[i]))
'''
    probe = work / 'probe.py'
    probe.write_text('\n\n'.join(functions) + driver, encoding='utf-8')
    py = subprocess.run([sys.executable, str(probe)], cwd=work,
                        capture_output=True, text=True, timeout=60)
    assert py.returncode == 0, py.stdout + py.stderr
    expected = [3.75, 1.25, -1.0, 3.75, -2.5, -0.5, 0.0, 1.25, 2.0, 2.0, 2.0, 8.25]
    expected += [0, 1, 1.25, 3, 3.75, 3.75, 1.25, 1.25, 8.25, 8.25]
    assert list(map(float, py.stdout.split())) == expected, py.stdout
    proc = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(probe),
                           '--compile', '--run-diff'], cwd=work,
                          capture_output=True, text=True, timeout=300)
    (out / 'run.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0 and 'Run diff: MATCH' in proc.stdout, proc.stdout + proc.stderr
    print('PASS: original kernels and adapted fixed-rank evaluator match Python and known values')


if __name__ == '__main__':
    main()
