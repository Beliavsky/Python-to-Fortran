"""Check deterministic Sobol state transitions and integer bit boundaries."""
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]


def run(command, name):
    p = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT/(name+'.log')).write_text(p.stdout+p.stderr, encoding='utf-8')
    assert p.returncode == 0, p.stdout+p.stderr
    return [line.split() for line in p.stdout.splitlines() if line.strip()]


python = run([sys.executable, 'probe.py'], 'python')
run([sys.executable, str(ROOT/'xp2f.py'), 'probe.py', '--compile'], 'build')
fortran = run([str(OUT/'probe_p.exe')], 'fortran')
assert len(python) == len(fortran), (len(python),len(fortran))
for i,(p,f) in enumerate(zip(python,fortran)):
    assert p[0] == f[0], (i,p,f)
    assert list(map(float,p[1:])) == list(map(float,f[1:])), (i,p,f)
    if p[0]=='bit':
        n,hi,lo = map(int,p[1:])
        assert hi == n.bit_length()
        assert lo == ((n+1) & -(n+1)).bit_length()
    elif p[0]=='seed':
        dim,seed,next_seed = map(int,p[1:])
        assert next_seed == max(0,seed)+1
    elif p[0]=='point':
        dim,seed,j = map(int,p[1:4])
        value = float(p[4])
        assert 0 <= value < 1
        if j == 0:
            # First Sobol coordinate is the binary radical inverse of Gray(seed).
            seed = max(0,seed)
            gray = seed ^ (seed >> 1)
            expected = 0.
            weight = .5
            while gray:
                expected += (gray & 1)*weight
                gray >>= 1
                weight *= .5
            assert value == expected, (p,expected)
result = dict(status='PASS', records=len(python),
              calls=sum(p[0]=='seed' for p in python),
              coordinates=sum(p[0]=='point' for p in python),
              bit_cases=sum(p[0]=='bit' for p in python))
(OUT/'analysis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
