"""Validate exact string lengths and the formerly failing FILUM list driver."""
import ast
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    for helper in ['python.f90', 'lapack_d.f90']:
        if not (work / helper).exists():
            shutil.copy2(root / helper, work / helper)
    shutil.copy2(out / 'probe.py', work / 'probe.py')
    source = Path('C:/python/public_domain/burkardt/filum/filum.py').read_text(encoding='utf-8')
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'filename_inc')
    (work / 'filum_list.py').write_text(ast.get_source_segment(source, fn) + '''
for filename in ['', 'cat.txt', 'file072.dat', 'a7to99.txt', 'a9to99.txt', '2cat9.dat  ', 'fred99.txt ']:
    result = filename_inc(filename)
    print(result, result is None)
    if result is not None:
        print(len(result))
        print('[', result, ']', sep='')
        for i in range(len(result)):
            print(ord(result[i]))
''', encoding='utf-8')
    for filename in ['probe.py', 'filum_list.py']:
        src = work / filename
        run = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(src), '--compile', '--run-diff'],
                             cwd=work, capture_output=True, text=True, timeout=300)
        (out / (src.stem + '.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
        assert run.returncode == 0 and 'Run diff: MATCH' in run.stdout, run.stdout + run.stderr
        print(filename, 'matches Python')
        if filename == 'probe.py':
            py = subprocess.run([sys.executable, str(src)], capture_output=True, text=True, check=True)
            ft = subprocess.run([str(src.with_name(src.stem + '_p.exe'))], capture_output=True, text=True, check=True)
            assert [s.strip() for s in py.stdout.splitlines()] == [s.strip() for s in ft.stdout.splitlines()]
            print('Delimiter comparison preserves empty strings and intentional spaces exactly')


if __name__ == '__main__':
    main()
