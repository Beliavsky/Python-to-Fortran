"""Validate the transferred EROS slice-view diagnostic with the main transpiler."""
import ast
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    # Keep helper objects/modules local; never rebuild the repository copies.
    for name in ('python.f90', 'lapack_d.f90'):
        if not (work / name).exists():
            shutil.copy2(root / name, work / name)
    probe = work / 'view_probe.py'
    shutil.copy2(out / 'view_probe.py', probe)
    run = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(probe),
                          '--compile', '--run-diff'], cwd=work,
                         capture_output=True, text=True, timeout=300)
    (out / 'view.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    print(run.stdout[-1800:])
    assert run.returncode != 0 and 'unsupported NumPy slice-view swap' in run.stdout

    # Explicit copying requests snapshot semantics and must remain supported.
    snapshot_probe = work / 'snapshot_probe.py'
    snapshot_probe.write_text(probe.read_text().replace('t = a[0, :]', 't = a[0, :].copy()'), encoding='utf-8')
    run = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(snapshot_probe),
                          '--compile', '--run-diff'], cwd=work,
                         capture_output=True, text=True, timeout=300)
    (out / 'snapshot.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    assert run.returncode == 0 and 'Run diff: MATCH' in run.stdout, run.stdout + run.stderr
    print('PASS: explicit-copy swap matches Python')

    original = Path('C:/python/public_domain/burkardt/eros/eros.py').read_text(encoding='utf-8')
    fn = next(n for n in ast.parse(original).body
              if isinstance(n, ast.FunctionDef) and n.name == 'gauss_plu')
    body = ast.get_source_segment(original, fn)
    # Diagnostic variants only: the corpus source is never edited.
    snapshot = body.replace('T      = P[j,:]', 'T      = P[j,:].copy()')
    snapshot = snapshot.replace('T      = U[j,:]', 'T      = U[j,:].copy()')
    snapshot = snapshot.replace('T        = L[j,1:j]', 'T        = L[j,1:j].copy()')
    corrected = snapshot.replace('p = p + j - 1', 'p = p + j')
    corrected = corrected.replace('L[j,1:j]', 'L[j,0:j]').replace('L[p,1:j]', 'L[p,0:j]')
    driver = '''
import numpy as np
A = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 8.0], [7.0, 8.0, 9.0]])
P, L, U = gauss_plu(A)
print(np.linalg.norm(A - P.T @ L @ U))
print(P)
'''
    for name, version in [('original_float', body), ('snapshot_float', snapshot),
                          ('corrected_float', corrected)]:
        src = work / (name + '.py')
        src.write_text(version + '\n' + driver, encoding='utf-8')
        run = subprocess.run([sys.executable, str(src)], cwd=work,
                             capture_output=True, text=True, timeout=60)
        (out / (name + '.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
        print(name, run.returncode, run.stdout.strip(), run.stderr.strip())

    src = work / 'corrected_float.py'
    run = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(src),
                          '--compile', '--run-diff'], cwd=work,
                         capture_output=True, text=True, timeout=300)
    (out / 'corrected_translation.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    assert 'Build: PASS' in run.stdout and 'Run: PASS' in run.stdout, run.stdout + run.stderr
    p = run.stdout.split('Run (python): PASS\n', 1)[1].split('\nwrote ', 1)[0]
    f = run.stdout.split('Run: PASS\n', 1)[1].split('\nRun diff:', 1)[0]
    def numbers(text):
        return [float(x) for x in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', text)]
    a, b = numbers(p), numbers(f)
    assert len(a) == len(b) == 10 and all(math.isclose(x, y, abs_tol=1.e-12)
                                        for x, y in zip(a, b)), (a, b)
    assert abs(a[0]) < 1.e-12 and abs(b[0]) < 1.e-12, (a, b)
    print('PASS: corrected floating-point PLU example matches; residual below 1e-12')


if __name__ == '__main__':
    main()
