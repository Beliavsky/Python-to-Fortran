"""Reproduce and independently validate the original five-city TSP driver."""
import itertools
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports/burkardt_recheck_20260915'))
from recheck import command, COMPILER

source = Path('C:/python/public_domain/burkardt/tsp_brute/tsp_brute.py')
valid = OUT / 'valid'
missing = OUT / 'missing'
missing.mkdir(exist_ok=True)
generated = OUT / 'tsp_brute_p.f90'
rc, _ = command([sys.executable, str(ROOT / 'xp2f.py'), str(source),
                 str(ROOT / 'python.f90'), str(ROOT / 'lapack_d.f90'),
                 '--out', str(generated), '--compile', '--compiler', COMPILER],
                OUT, OUT / 'build.log', 240)
assert rc == 0, (OUT / 'build.log').read_text()
matrix = [[float(v) for v in row.split()] for row in (valid / 'five.txt').read_text().splitlines()]
costs = [sum(matrix[p[i]][p[(i+1) % 5]] for i in range(5))
         for p in itertools.permutations(range(5))]
expected = {'Minimum': min(costs), 'Average': sum(costs)/len(costs), 'Maximum': max(costs)}
for label, cmd in [('python', [sys.executable, str(source)]), ('fortran', [str(generated.with_suffix('.exe'))])]:
    rc, _ = command(cmd, valid, OUT / f'{label}.log', 60)
    assert rc == 0, label
    output = (OUT / f'{label}.log').read_text()
    count = int(re.search(r'Number of paths checked =\s*(\d+)', output)[1])
    assert count == len(costs) == 120, (label, count)
    for name, value in expected.items():
        actual = float(re.search(name + r' length =\s*([\d.eE+-]+)', output)[1])
        assert abs(actual-value) < 1e-10, (label, name, actual, value)
    table = output.split('Step  From  To', 1)[1].split('----', 1)[0]
    edges = re.findall(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+([\d.eE+-]+)\s*$', table, re.M)
    assert len(edges) == 5, (label, edges)
    assert sorted(int(a) for _, a, _, _ in edges) == list(range(5))
    for i, (_, a, b, cost) in enumerate(edges):
        assert int(b) == int(edges[(i+1) % 5][1])
        assert float(cost) == matrix[int(a)][int(b)]
    assert sum(float(e[3]) for e in edges) == expected['Minimum']
    rc, _ = command(cmd, missing, OUT / f'{label}_missing.log', 60)
    assert rc != 0, (label, 'missing file incorrectly succeeded')
    assert 'five.txt' in (OUT / f'{label}_missing.log').read_text()
    print(label, 'PASS: 120 paths, three statistics, optimal itinerary, missing-file failure', flush=True)
print(json.dumps(expected), flush=True)
