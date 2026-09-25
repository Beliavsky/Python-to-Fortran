"""Validate original divided-difference kernels, including singleton unwrapping."""
import argparse
import ast
import copy
import math
from pathlib import Path
import re
import subprocess
import sys


def compare_full_output(output):
    """Audit full output separately from the CLI's version-banner mismatch."""
    assert 'Build: PASS' in output and 'Run: PASS' in output, output[-4000:]
    python_output = output.split('Run (python): PASS\n', 1)[1].split('\nwrote ', 1)[0]
    fortran_output = output.split('Run: PASS\n', 1)[1].split('\nRun diff:', 1)[0]
    def lines(text):
        return [' '.join(line.split()) for line in text.splitlines() if line.strip()
                and not re.match(r'\s*(python|numpy) version:', line, re.I)
                and not re.fullmatch(r'\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\w+\s+\d+\s+\d+:\d+:\d+\s+\d+\s*', line)]
    py, ft = lines(python_output), lines(fortran_output)
    assert len(py) == len(ft), (len(py), len(ft))
    number = re.compile(r'(?<![\w.])[+-]?(?:\d+\.?\d*|\.\d+)(?:[eEdD][+-]?\d+)?')
    count = 0
    for line_no, (left, right) in enumerate(zip(py, ft), 1):
        a, b = number.findall(left), number.findall(right)
        assert number.sub('#', left) == number.sub('#', right), (line_no, left, right)
        assert len(a) == len(b), (line_no, left, right)
        for x, y in zip(a, b):
            assert math.isclose(float(x.replace('D', 'e').replace('d', 'e')),
                                float(y.replace('D', 'e').replace('d', 'e')),
                                rel_tol=1e-5, abs_tol=1e-10), (line_no, x, y)
            count += 1
    return len(py), count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/divdif/divdif.py'))
    parser.add_argument('--full', action='store_true', help='Also translate and run the full original source')
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    text = args.source.read_text(encoding='utf-8')
    names = {'data_to_dif', 'data_to_r8poly', 'dif_to_r8poly', 'r8vec_is_distinct', 'dif_value'}
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
original_empty = dif_value(3, x, d, np.array([], dtype=float))
print(original_empty.size)
print(dif_value(3, x, d, np.array([0.0])))
original_vector = dif_value(3, x, d, np.array([-1.0, 0.0, 2.0]))
print(original_vector.size)
for i in range(3):
    print(original_vector[i])
print(dif_value(3, x, d, -1.0))
print(dif_value(3, x, d, 0.0))
print(dif_value(3, x, d, 2.0))
'''
    probe = work / 'probe.py'
    probe.write_text('\n\n'.join(functions) + driver, encoding='utf-8')
    py = subprocess.run([sys.executable, str(probe)], cwd=work,
                        capture_output=True, text=True, timeout=60)
    assert py.returncode == 0, py.stdout + py.stderr
    expected = [3.75, 1.25, -1.0, 3.75, -2.5, -0.5, 0.0, 1.25, 2.0, 2.0, 2.0, 8.25]
    expected += [0, 1, 1.25, 3, 3.75, 3.75, 1.25, 1.25, 8.25, 8.25]
    expected += [0, 1.25, 3, 3.75, 1.25, 8.25, 3.75, 1.25, 8.25]
    assert list(map(float, py.stdout.split())) == expected, py.stdout
    proc = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(probe),
                           '--compile', '--run-diff'], cwd=work,
                          capture_output=True, text=True, timeout=300)
    (out / 'run.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0 and 'Run diff: MATCH' in proc.stdout, proc.stdout + proc.stderr
    print('PASS: original kernels, original dif_value, and adapted evaluator match Python and known values')
    if args.full:
        full = work / 'divdif.py'
        full.write_text(text, encoding='utf-8')
        proc = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(full),
                               '--compile', '--run-diff'], cwd=work,
                              capture_output=True, text=True, timeout=600)
        (out / 'full.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
        assert proc.returncode in (0, 1), proc.stdout[-4000:] + proc.stderr
        line_count, number_count = compare_full_output(proc.stdout)
        print(f'PASS: full original divdif.py: {line_count} lines and {number_count} numeric values match '
              '(excluding version banners/timestamps; rtol=1e-5, atol=1e-10)')


if __name__ == '__main__':
    main()
