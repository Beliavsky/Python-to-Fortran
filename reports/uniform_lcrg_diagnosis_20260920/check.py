"""Compare the reduced original arithmetic to arbitrary-precision integers."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FLAGS = 'gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wfatal-errors'
def run(cmd, name):
    proc = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True, timeout=240)
    (OUT/(name+'.log')).write_text(proc.stdout+proc.stderr,encoding='utf-8')
    assert proc.returncode == 0, proc.stdout+proc.stderr
    return proc.stdout
if '--check-rejection' in sys.argv:
    proc = subprocess.run([sys.executable,str(ROOT/'xp2f.py'),str(OUT/'probe.py'),
                           '--out',str(OUT/'probe_rejected_p.f90')],cwd=OUT,
                          capture_output=True,text=True,timeout=240)
    assert proc.returncode != 0
    assert "integer-comment parameter 'x' of 'lcrg_evaluate'" in proc.stdout+proc.stderr
    print(proc.stdout+proc.stderr)
    sys.exit(0)

run([sys.executable,str(ROOT/'xp2f.py'),str(OUT/'probe.py'),str(ROOT/'python.f90'),
     '--compile','--compiler',FLAGS], 'build')
outputs = [run([sys.executable,str(OUT/'probe.py')],'python'),run([str(OUT/'probe_p.exe')],'fortran')]
run([sys.executable,str(ROOT/'xp2f.py'),str(OUT/'probe.py'),str(ROOT/'python.f90'),
     '--ignore-comments','--out',str(OUT/'probe_ignore_comments_p.f90'),
     '--compile','--compiler',FLAGS], 'ignore_comments_build')
outputs.append(run([str(OUT/'probe_ignore_comments_p.exe')],'ignore_comments'))
a,b,c = 16807,0,2147483647
spec = importlib.util.spec_from_file_location('original','C:/python/public_domain/burkardt/uniform/uniform.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
for n in range(11):
    an,bn = original.lcrg_anbn(a,b,c,n)
    assert an == pow(a,n,c) and bn == 0
an = pow(a,4,c)
exact = {}
state = 12345
for n in range(12):
    exact[n] = state
    state = (a*state+b)%c
results = {'multiplier':an,'original_coefficients_checked':11,'rows':{}}
for label,output in zip(('python','fortran','ignore_comments'),outputs):
    rows=[]
    for line in output.splitlines():
        f = line.split()
        if f[0] == 'scalar':
            assert int(float(f[2])) == exact[int(f[1])]
        elif f[0] == 'array':
            j,n,x,y = int(f[1]),int(f[2]),int(float(f[3])),int(float(f[4]))
            rows.append(dict(j=j,n=n,input=x,result=y,exact=exact[n],
                             integer_product=an*x,float_product=int(float(an)*float(x)),
                             exact_step=(an*x)%c,float_step=(float(an)*float(x))%c))
    assert len(rows)==8
    results['rows'][label] = rows
assert all(row['result']==row['exact'] for row in results['rows']['fortran'])
assert results['rows']['python'] == results['rows']['ignore_comments']
assert results['rows']['python'] != results['rows']['fortran']
text=json.dumps(results,indent=2)
(OUT/'analysis.json').write_text(text,encoding='utf-8')
print(text)
