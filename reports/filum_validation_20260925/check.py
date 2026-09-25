"""Validate FILUM filename_inc without modifying the corpus source."""
import ast
import re
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    source_path = Path('C:/python/public_domain/burkardt/filum/filum.py')
    source = source_path.read_text(encoding='utf-8')
    tree = ast.parse(source)
    functions = [ast.get_source_segment(source, fn) for fn in tree.body
                 if isinstance(fn, ast.FunctionDef) and fn.name in {'filename_inc', 'filename_inc_test'}]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    for helper in ['python.f90', 'lapack_d.f90']:
        if not (work / helper).exists():
            shutil.copy2(root / helper, work / helper)
    kernel = work / 'filename_probe.py'
    driver = '\nfilename_inc_test()\n'
    # Separate scalar calls avoid the independent fixed-width string-list
    # padding limitation; trailing spaces in each filename are intentional.
    for name in ['', 'cat.txt', 'file072.dat', 'a7to99.txt', 'a9to99.txt', '2cat9.dat  ', 'fred99.txt ']:
        driver += f'result = filename_inc({name!r})\n' + '''copied = result
print(result, copied, result is None, None == copied)
if result is not None:
    print(len(result))
    for i in range(len(result)):
        print(ord(result[i]))
'''
    kernel.write_text('\n\n'.join(functions) + driver, encoding='utf-8')
    for src in [kernel, out / 'probe.py']:
        proc = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(src),
                               '--out', str(work / (src.stem + '_p.f90')), '--compile', '--run-diff'],
                              cwd=work, capture_output=True, text=True, timeout=300)
        (out / (src.stem + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
        print(src.name, proc.returncode, proc.stdout[-1500:], proc.stderr)
        assert proc.returncode == 0 and 'Run diff: MATCH' in proc.stdout
        if src.name == 'probe.py':
            fortran = proc.stdout.split('Run: PASS\n', 1)[1].split('Run diff:', 1)[0]
            delimited = [line.strip() for line in fortran.splitlines() if line.lstrip().startswith('[')]
            assert delimited == ['[None]', '[None]', '[None]', '[abc  ]', '[]'], delimited
    full = work / 'filum.py'
    shutil.copy2(source_path, full)
    proc = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(full), '--compile'],
                          cwd=work, capture_output=True, text=True, timeout=300)
    (out / 'full_build.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    print('Full build:', proc.returncode, proc.stdout[-2000:], proc.stderr)
    assert proc.returncode == 0
    # The corpus checkout lacks these two input files. Use explicit synthetic
    # fixtures for the full-driver smoke comparison, not invented originals.
    (work / 'r8mat_write_test.txt').write_text('# three columns\n1.5 2.5 3.5\n4.5 5.5 6.5\n', encoding='utf-8')
    (work / 'i4mat_write_test.txt').write_text('# two rows\n1 2 3\n4 5 6\n', encoding='utf-8')
    outputs = []
    for label, command in [('python', [sys.executable, str(full)]),
                           ('fortran', [str(work / 'filum_p.exe')])]:
        run = subprocess.run(command, cwd=work, capture_output=True, text=True, timeout=120)
        (out / (label + '_run.log')).write_text(run.stdout + run.stderr, encoding='utf-8')
        assert run.returncode == 0, run.stdout + run.stderr
        outputs.append([' '.join(line.split()) for line in run.stdout.splitlines()
                        if line.strip() and 'version:' not in line.lower()
                        and not re.match(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s', line)])
    assert outputs[0] == outputs[1], '\n'.join(outputs[0]) + '\nVERSUS\n' + '\n'.join(outputs[1])
    print('PASS: full driver matches with synthetic fixtures (excluding version/time banners and whitespace)')


if __name__ == '__main__':
    main()
