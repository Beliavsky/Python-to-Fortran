"""Check Burkardt row sorting, key priority, stability, and input preservation."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
INTEGER = '--integer' in sys.argv
STEM = 'probe_int' if INTEGER else 'probe'
PREFIX = 'integer_' if INTEGER else ''
CASES = [
    [[2.,0.,9.],[1.,4.,2.],[1.,3.,8.],[1.,3.,7.],[2.,-1.,5.],[1.,3.,7.]],
    [[-2.,5.],[-1.,-4.],[-2.,-3.],[0.,-9.]],
    [[3.],[-2.],[3.],[0.],[-2.]], [[4.,-2.,1.]], np.zeros((0,3)),
    [[1.,1.],[1.,1.],[1.,1.]], [[.5,2.],[.25,9.],[.5,-1.],[-.25,8.]],
    [[3.,1.],[2.,2.],[1.,3.],[0.,4.]],
]


def run(command, name):
    p = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT/(PREFIX+name+'.log')).write_text(p.stdout+p.stderr, encoding='utf-8')
    assert p.returncode == 0, p.stdout+p.stderr
    return p.stdout


python = run([sys.executable, STEM+'.py'], 'python')
run([sys.executable, str(ROOT/'xp2f.py'), STEM+'.py', '--compile'], 'build')
fortran = run([str(OUT/(STEM+'_p.exe'))], 'fortran')
observed = {}
for language, output in [('python',python),('fortran',fortran)]:
    rows = {}
    for line in output.splitlines():
        fields = line.split()
        key = (fields[0],)+tuple(map(int,fields[1:-1]))
        assert key not in rows, key
        rows[key] = float(fields[-1])
    expected = {}
    for case, data in enumerate(CASES):
        a = np.asarray(data, dtype=np.int64 if INTEGER else float)
        nr,nc = a.shape
        order = sorted(range(nr), key=lambda i: tuple(a[i]))
        assert order == np.lexsort(a.T[::-1]).tolist()
        expected['shape',case,nr] = nc
        for i, index in enumerate(order):
            expected['order',case,i] = index
            for j in range(nc):
                expected['sorted',case,i,j] = a[index,j]
                expected['original',case,i,j] = a[i,j]
    assert rows.keys() == expected.keys(), (language,rows.keys() ^ expected.keys())
    for key,value in expected.items():
        assert rows[key] == value, (language,key,rows[key],value)
    observed[language] = rows
assert observed['python'] == observed['fortran']
result = dict(status='PASS', cases=len(CASES), records=len(observed['python']))
(OUT/(PREFIX+'analysis.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
