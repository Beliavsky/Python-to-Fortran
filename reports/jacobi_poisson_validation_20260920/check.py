"""Separate formatting divergence from numerical solution checks."""
from pathlib import Path
import math
import re
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path('C:/python/public_domain/burkardt/jacobi_poisson_1d/jacobi_poisson_1d.py')
FLAGS = 'gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wfatal-errors'
def run(cmd, name):
    proc = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True, timeout=240)
    (OUT / (name+'.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout

if '--check-rejection' in sys.argv:
    proc = subprocess.run([sys.executable, str(ROOT/'xp2f.py'), str(SOURCE),
                           '--out', str(OUT/'rejected_p.f90')], cwd=OUT,
                          capture_output=True, text=True, timeout=240)
    assert proc.returncode != 0
    assert 'arguments supplied but no conversion specifier' in proc.stdout + proc.stderr
    print(proc.stdout + proc.stderr)
    sys.exit(0)

for value in [1., np.float64(1), np.int64(1), (np.float64(1),)]:
    try:
        print(type(value).__name__, repr('label' % value))
    except TypeError as exc:
        print(type(value).__name__, 'TypeError:', str(exc))
generated = OUT / 'jacobi_poisson_1d_p.f90'
run([sys.executable, str(ROOT/'xp2f.py'), str(SOURCE), str(ROOT/'python.f90'),
     str(ROOT/'lapack_d.f90'), '--out', str(generated), '--compile', '--compiler', FLAGS], 'build')
outputs = [run([sys.executable, str(SOURCE)], 'python'), run([str(generated.with_suffix('.exe'))], 'fortran')]

# Independent scalar Thomas solve of -u[i-1]+2*u[i]-u[i+1]=h*h*f[i].
h = 1/32
diagonal = [2.] * 31
rhs = [-((i*h)*(i*h+3)*math.exp(i*h))*h*h for i in range(1,32)]
for i in range(1,31):
    factor = -1 / diagonal[i-1]
    diagonal[i] += factor
    rhs[i] -= factor * rhs[i-1]
solution = [0.] * 33
for i in range(30,-1,-1):
    solution[i+1] = (rhs[i]+solution[i+2])/diagonal[i]
pattern = r'^\s*(\d+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)\s*$'
tables = []
for label, output in zip(('python','fortran'), outputs):
    rows = re.findall(pattern, output, re.M)
    assert len(rows) == 33
    tables.append([[float(v) for v in row] for row in rows])
    for i, row in enumerate(tables[-1]):
        assert row[0] == i and abs(row[1]-i*h) <= .000050001
        exact = (i*h)*(i*h-1)*math.exp(i*h)
        for printed, reference in [(row[2],exact),(row[3],solution[i]),(row[4],solution[i])]:
            # The solution columns use %.4g; allow half a displayed unit.
            tolerance = 0 if reference == 0 else .5*10**(math.floor(math.log10(abs(reference)))-3)
            assert abs(printed-reference) <= tolerance + 1e-7, (label,i,printed,reference)
    residual = float(re.search(r'RMS of linear residual\s+([\d.eE+-]+)',output)[1])
    iterations = int(re.search(r'Number of Jacobi iterations taken was\s+(\d+)',output)[1])
    assert residual <= 1e-6
    print(label, '33 rows agree with independent solve at printed precision;', iterations, 'iterations; residual', residual)
assert tables[0] == tables[1]
print('Python/Fortran solution tables match exactly at displayed precision.')
for label, output in zip(('python','fortran'), outputs):
    for line in output.splitlines():
        if 'RMS Jacobi error' in line or 'RMS discretization error' in line:
            print(label, repr(line))
