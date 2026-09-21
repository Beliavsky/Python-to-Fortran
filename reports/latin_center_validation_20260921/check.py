"""Validate Latin-center invariants independently in Python and Fortran."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CASES = [(1, 1), (5, 1), (1, 17), (2, 10), (7, 31), (3, 0), (4, 100)] * 3


def run(command, name):
    proc = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT / (name + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


python = run([sys.executable, 'probe.py'], 'python')
run([sys.executable, str(ROOT / 'xp2f.py'), 'probe.py', '--compile'], 'build')
fortran = run([str(OUT / 'probe_p.exe')], 'fortran')
counts = {}
for language, output in [('python', python), ('fortran', fortran)]:
    records = {}
    for line in output.splitlines():
        fields = line.split()
        key = (fields[0],) + tuple(map(int, fields[1:-1]))
        assert key not in records, (language, key)
        records[key] = float(fields[-1])
    expected_keys = set()
    for case, (dims, points) in enumerate(CASES):
        shape_key = ('shape', case, points)
        expected_keys.add(shape_key)
        assert records[shape_key] == dims, (language, case, 'shape')
        matrices = {}
        for tag in ['value', 'sorted']:
            a = np.empty((points, dims))
            for i in range(points):
                for j in range(dims):
                    key = (tag, case, i, j)
                    expected_keys.add(key)
                    a[i, j] = records[key]
            assert np.all(np.isfinite(a)), (language, case, tag)
            assert np.all((a > 0) & (a < 1)), (language, case, tag)
            midpoints = (np.arange(points) + 0.5) / max(points, 1)
            for j in range(dims):
                np.testing.assert_allclose(
                    np.sort(a[:, j]), midpoints, rtol=0, atol=2e-15,
                    err_msg=f'{language} case {case} {tag} column {j}',
                )
            matrices[tag] = a
        original = matrices['value']
        order = sorted(range(points), key=lambda i: tuple(original[i]))
        np.testing.assert_array_equal(matrices['sorted'], original[order])
    assert records.keys() == expected_keys, (language, records.keys() ^ expected_keys)
    counts[language] = len(records)
result = dict(
    status='PASS', cases_per_language=len(CASES), records=counts,
    scope='Shape, finite interior coordinates, one midpoint per stratum per column, and lexicographic sorting',
    limitation='Does not establish identical random streams or statistical uniformity of permutations',
)
(OUT / 'analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
