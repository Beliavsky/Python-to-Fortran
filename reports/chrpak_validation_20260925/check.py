"""Validate unmodified Burkardt ROT13/ROT5 and retry the full chrpak build."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    original = (Path(sys.argv[1]) if len(sys.argv) > 1 else
                Path('C:/python/public_domain/burkardt/chrpak/chrpak.py'))
    source = original.read_text(encoding='utf-8')
    fn = next(n for n in ast.parse(source).body
              if isinstance(n, ast.FunctionDef) and n.name == 'ch_to_rot13')
    work = out / 'work'
    work.mkdir(exist_ok=True)
    if not (work / 'python.f90').exists():
        shutil.copy2(root / 'python.f90', work / 'python.f90')
    kernel = work / 'rot13.py'
    kernel.write_text(ast.get_source_segment(source, fn) + '''
for k in range(32, 127):
    ch = chr(k)
    mapped = ch_to_rot13(ch)
    restored = ch_to_rot13(mapped)
    print(k, ord(mapped), ord(restored))
''', encoding='utf-8')
    run = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(kernel),
                          '--compile', '--run-diff'], cwd=work,
                         capture_output=True, text=True, timeout=300)
    (out / 'rot13.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    assert run.returncode == 0 and 'Run diff: MATCH' in run.stdout, run.stdout + run.stderr
    assert run.stderr.count('changes type from integer to character') == 1
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(original), 'exec'), namespace)
    rotate = namespace['ch_to_rot13']
    for code in range(32, 127):
        assert rotate(rotate(chr(code))) == chr(code)
    print('PASS: all 95 printable ASCII mappings match Python; double application restores input')
    full = work / 'chrpak.py'
    shutil.copy2(original, full)
    run = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(full), '--compile'],
                         cwd=work, capture_output=True, text=True, timeout=300)
    (out / 'full_build.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    print('Full chrpak build return code:', run.returncode)
    print((run.stdout + run.stderr)[-3000:])
    if run.returncode == 0:
        for label, command in [('python', [sys.executable, str(full)]),
                               ('fortran', [str(work / 'chrpak_p.exe')])]:
            execution = subprocess.run(command, cwd=work, capture_output=True,
                                       text=True, timeout=120)
            (out / (label + '_run.log')).write_text(execution.stdout + execution.stderr,
                                                   encoding='utf-8')
            print(label, 'execution return code:', execution.returncode)
            assert execution.returncode == 0, execution.stdout[-2000:] + execution.stderr


if __name__ == '__main__':
    main()
