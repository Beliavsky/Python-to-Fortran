"""Validate locally corrected Burkardt R8BB routines against dense references."""
import json
from pathlib import Path
import subprocess
import sys

import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
CASES = [(4, 2, 1, 2, False), (5, 0, 2, 1, False), (0, 3, 0, 0, False),
         (1, 1, 0, 0, False), (3, 2, 0, 0, False), (4, 2, 1, 1, True)]


def run(command, name):
    if '--saved' in sys.argv:
        return (OUT / (name + '.log')).read_text(encoding='utf-8')
    p = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT / (name + '.log')).write_text(p.stdout + p.stderr, encoding='utf-8')
    assert p.returncode == 0, p.stdout + p.stderr
    return p.stdout


python = run([sys.executable, 'probe.py'], 'python')
run([sys.executable, str(ROOT / 'xp2f.py'), 'probe.py', '--compile'], 'build')
fortran = run([str(OUT / 'probe_p.exe')], 'fortran')
results = {}
all_rows = {}
for language, output in [('python', python), ('fortran', fortran)]:
    rows = {}
    for line in output.splitlines():
        f = line.split()
        key = (f[0],) + tuple(map(int, f[1:-1]))
        assert key not in rows, key
        rows[key] = float(f[-1])
    assert len(rows) == sum(1 + 5*(n1+n2) + (n1+n2)**2
                           for n1,n2,_,mu,_ in CASES)
    all_rows[language] = rows
    checks = []
    for case, (n1,n2,ml,mu,pivot_case) in enumerate(CASES):
        n = n1+n2
        i,j = np.indices((n,n))
        dense = np.where((i>=n1) | (j>=n1) | ((i-j<=ml) & (j-i<=mu)),
                         np.where(i==j, 8.+i, .125*(1+2*i-j)), 0.)
        if pivot_case:
            dense[0,0], dense[1,0] = .125, 3.
        exact = (np.arange(n)+1.) * (-1.)**np.arange(n)
        rhs = dense @ exact
        unpacked = np.array([[rows['dense',case,i,j] for j in range(n)] for i in range(n)])
        solution = np.array([rows['solution',case,i] for i in range(n)])
        assert rows['info',case] == 0
        assert np.array_equal(unpacked, dense)
        assert np.allclose([rows['rhs',case,i] for i in range(n)], rhs, rtol=0, atol=1e-13)
        mv = np.array([rows['mv',case,i] for i in range(n)])
        trans = np.array([rows['trans',case,i] for i in range(n)])
        mv_error = float(np.max(np.abs(mv-rhs)))
        trans_error = float(np.max(np.abs(trans-dense.T@exact)))
        assert np.allclose(mv,rhs,rtol=0,atol=1e-13)
        assert np.allclose(trans,dense.T@exact,rtol=0,atol=1e-13)
        assert np.allclose(solution, exact, rtol=0, atol=1e-12)
        assert np.allclose(solution, np.linalg.solve(dense,rhs), rtol=0, atol=1e-12)
        residual = np.linalg.norm(dense@solution-rhs)/(np.linalg.norm(dense)*np.linalg.norm(solution)+np.linalg.norm(rhs))
        assert residual < 1e-14
        if pivot_case:
            assert rows['pivot',case,0] == 2  # LINPACK one-based pivot index.
        checks.append(dict(case=case, n1=n1, n2=n2, ml=ml, mu=mu,
                           mv_error=mv_error, transpose_mv_error=trans_error,
                           max_solution_error=float(np.max(np.abs(solution-exact))),
                           relative_residual=float(residual)))
    results[language] = checks
assert all_rows['python'].keys() == all_rows['fortran'].keys()
for key in all_rows['python']:
    assert np.isclose(all_rows['python'][key],all_rows['fortran'][key],rtol=1e-13,atol=1e-13), key
(OUT/'analysis.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
