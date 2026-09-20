"""Compile the diagnostic and quantify Gram-Schmidt invariants."""
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FLAGS = 'gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wfatal-errors'
def run(cmd, name):
    proc = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True, timeout=240)
    (OUT/(name+'.log')).write_text(proc.stdout+proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout+proc.stderr
    return proc.stdout

run([sys.executable,str(ROOT/'xp2f.py'),str(OUT/'probe.py'),str(ROOT/'python.f90'),
     '--compile','--compiler',FLAGS], 'build')
outputs = [run([sys.executable,str(OUT/'probe.py')],'python'), run([str(OUT/'probe_p.exe')],'fortran')]
A = np.array([[-9.,8.,8.,2.],[6.,7.,7.,-1.],[9.,9.,1.,-8.]])
results = {}
arrays = []
for label, output in zip(('python','fortran'), outputs):
    U, raw, norms = np.zeros((3,4)), np.zeros((3,4)), np.zeros(4)
    counts = {'u':0,'raw':0,'norm':0}
    for line in output.splitlines():
        fields = line.split()
        if not fields or fields[0] not in counts:
            continue
        key = fields[0]
        counts[key] += 1
        if key == 'norm':
            norms[int(fields[1])] = float(fields[2])
        else:
            (U if key == 'u' else raw)[int(fields[1]),int(fields[2])] = float(fields[3])
    assert counts == {'u':12,'raw':12,'norm':4}
    Q = U[:,:3]
    metrics = dict(residual_norms=norms.tolist(), fourth_raw=raw[:,3].tolist(), fourth_unit=U[:,3].tolist(),
                   orthogonality_first_three=float(np.linalg.norm(Q.T@Q-np.eye(3))),
                   reconstruction_relative=float(np.linalg.norm(A-Q@(Q.T@A))/np.linalg.norm(A)),
                   fourth_correlations=(Q.T@U[:,3]).tolist())
    assert metrics['orthogonality_first_three'] < 1e-14
    assert metrics['reconstruction_relative'] < 1e-14
    assert norms[3] < 1e-14*np.linalg.norm(A[:,3])
    assert np.max(np.abs(Q.T@U[:,3])) > .5
    results[label] = metrics
    arrays.append(U)

spec = importlib.util.spec_from_file_location('original', 'C:/python/public_domain/burkardt/gram_schmidt/gram_schmidt.py')
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
assert np.array_equal(original.cgs2(A),arrays[0])
serial = np.zeros_like(A)
def serial_dot(a,b):
    total = 0.
    for i in range(3):
        total += float(a[i])*float(b[i])
    return total
for j in range(4):
    v = A[:,j].copy()
    for k in range(j):
        v2 = serial[:,k]
        p = serial_dot(v,v2)/math.sqrt(serial_dot(v2,v2))
        v = v-p*v2
    norm = math.sqrt(serial_dot(v,v))
    if norm > 0:
        v = v/norm
    serial[:,j] = v
assert np.allclose(serial,arrays[1],rtol=0,atol=1e-15)
results['comparison'] = dict(first_three_max_difference=float(np.max(np.abs(arrays[0][:,:3]-arrays[1][:,:3]))),
                             fourth_max_difference=float(np.max(np.abs(arrays[0][:,3]-arrays[1][:,3]))),
                             input_rank=int(np.linalg.matrix_rank(A)),
                             original_cgs4_fourth=original.cgs4(A,1000*np.finfo(float).eps)[:,3].tolist(),
                             serial_python_vs_fortran_max_difference=float(np.max(np.abs(serial-arrays[1]))))
text = json.dumps(results,indent=2)
(OUT/'analysis.json').write_text(text,encoding='utf-8')
print(text)
