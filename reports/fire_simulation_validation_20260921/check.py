"""Compare deterministic forest-fire trajectories to a distance-based oracle."""
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CASES = [
    (1, 0, 0, 0), (1, 1, 0, 0), (2, 0, 0, 0), (2, 1, 0, 0),
    (5, 0, 2, 2), (5, 1, 2, 2), (5, 0, 0, 4), (5, 1, 0, 4),
    (4, 1, 0, 2), (4, 0, 0, 2), (3, 1, -1, -1),
]


def run(command, name):
    proc = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT / (name + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert 'STOP' not in proc.stdout + proc.stderr, proc.stdout + proc.stderr
    return proc.stdout


expected = {}
snapshots = 0
for case, (n, prob, row, col) in enumerate(CASES):
    last = (max(row, n-1-row) + max(col, n-1-col) + 2) if prob else 2
    if row < 0:
        last = 0
    expected['steps', case] = last
    for step in range(-1, last+1):
        snapshots += 1
        states = []
        for i in range(n):
            for j in range(n):
                distance = abs(i-row) + abs(j-col)
                if step < 0 or row < 0 or (not prob and distance != 0) or distance > step:
                    state = 0
                else:
                    state = min(3, step-distance+1)
                states.append(state)
                expected['cell', case, step, i, j] = state
        expected['active', case, step] = int(any(s in (1, 2) for s in states))
        expected['fraction', case, step] = states.count(3) / (n*n)

python = run([sys.executable, 'probe.py'], 'python')
run([sys.executable, str(ROOT / 'xp2f.py'), 'probe.py', '--compile'], 'build')
fortran = run([str(OUT / 'probe_p.exe')], 'fortran')
observed = {}
for language, output in [('python', python), ('fortran', fortran)]:
    records = {}
    for line in output.splitlines():
        fields = line.split()
        key = (fields[0],) + tuple(map(int, fields[1:-1]))
        assert key not in records, (language, key)
        records[key] = float(fields[-1])
    assert records.keys() == expected.keys(), (language, records.keys() ^ expected.keys())
    for key, value in expected.items():
        tolerance = 2e-15 if key[0] == 'fraction' else 0
        assert abs(records[key] - value) <= tolerance, (language, key, records[key], value)
    observed[language] = len(records)
result = dict(status='PASS', cases=len(CASES), snapshots=snapshots, records=observed,
              scope='Fixed ignition, spread probabilities zero and one, every intermediate cell, activity, burned fraction and termination',
              limitation='Random ignition and intermediate spread probabilities are not validated')
(OUT / 'analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
