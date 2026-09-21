"""Check fixed tridiagonal solves against exact solutions and dense solves."""
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
FLAGS='gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wfatal-errors'
stem='control' if '--control' in sys.argv else 'probe'
def run(cmd,name):
    proc=subprocess.run(cmd,cwd=OUT,capture_output=True,text=True,timeout=240)
    (OUT/(stem+'_'+name+'.log')).write_text(proc.stdout+proc.stderr,encoding='utf-8')
    assert proc.returncode==0,proc.stdout+proc.stderr
    return proc.stdout
python=run([sys.executable,str(OUT/(stem+'.py'))],'python')
run([sys.executable,str(ROOT/'xp2f.py'),str(OUT/(stem+'.py')),str(ROOT/'python.f90'),str(ROOT/'lapack_d.f90'),
     '--compile','--compiler',FLAGS],'build')
fortran=run([str(OUT/(stem+'_p.exe'))],'fortran')
results={}
for label,text in [('python',python),('fortran',fortran)]:
    rows={}
    shapes={}
    for line in text.splitlines():
        fields=line.split()
        if fields[0]=='shape':
            n=int(fields[1])
            assert n not in shapes
            shapes[n]=list(map(int,fields[2:]))
            assert shapes[n]==[1,2,1,2,n,n,2], shapes[n]
            continue
        key=(fields[0],)+tuple(map(int,fields[1:-1]))
        assert key not in rows
        rows[key]=float(fields[-1])
    assert len(rows)==5*sum((1,2,5,9))
    if stem=='probe':
        assert set(shapes)=={1,2,5,9}
    checks=[]
    for n in (1,2,5,9):
        A=np.diag(4.+.125*np.arange(n))+np.diag(np.full(n-1,-.75),-1)+np.diag(np.full(n-1,.5),1)
        exact=np.column_stack((.25*np.arange(n)-1.,(np.arange(n)+1.)*(-1.)**np.arange(n)))
        rhs=A@exact
        got_rhs=np.array([[rows['rhs',n,i,j] for j in range(2)] for i in range(n)])
        vector=np.array([rows['vector',n,i] for i in range(n)])
        matrix=np.array([[rows['matrix',n,i,j] for j in range(2)] for i in range(n)])
        assert np.allclose(got_rhs,rhs,rtol=0,atol=1e-13)
        assert np.allclose(matrix,exact,rtol=0,atol=1e-12)
        assert np.allclose(vector,exact[:,0],rtol=0,atol=1e-12)
        dense=np.linalg.solve(A,rhs)
        assert np.allclose(matrix,dense,rtol=0,atol=1e-12)
        residual=np.linalg.norm(A@matrix-rhs)/(np.linalg.norm(A)*np.linalg.norm(matrix)+np.linalg.norm(rhs))
        assert residual<1e-14
        checks.append(dict(size=n,max_solution_error=float(np.max(np.abs(matrix-exact))),relative_residual=float(residual)))
    results[label]=checks
(OUT/(stem+'_analysis.json')).write_text(json.dumps(results,indent=2),encoding='utf-8')
print(json.dumps(results,indent=2))
