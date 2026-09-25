"""Compile/run unchanged Burkardt abc.py and check its persistent-state trace."""
import argparse
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/persistence/abc.py'))
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    source = args.source.resolve()
    py = subprocess.run([sys.executable, str(source)], cwd=work,
                        capture_output=True, text=True, timeout=60)
    (out / 'python.stdout').write_text(py.stdout, encoding='utf-8')
    assert py.returncode == 0, py.stdout + py.stderr
    generated = work / 'abc_p.f90'
    build = subprocess.run([sys.executable, str(root / 'xp2f.py'), str(source),
                            '--out', str(generated), '--compile'], cwd=work,
                           capture_output=True, text=True, timeout=300)
    (out / 'build.log').write_text(build.stdout + build.stderr, encoding='utf-8')
    assert build.returncode == 0, build.stdout + build.stderr
    exe = generated.with_suffix('.exe' if sys.platform == 'win32' else '')
    ft = subprocess.run([str(exe)], cwd=work, capture_output=True, text=True, timeout=60)
    (out / 'fortran.stdout').write_text(ft.stdout, encoding='utf-8')
    (out / 'fortran.stderr').write_text(ft.stderr, encoding='utf-8')
    assert ft.returncode == 0, ft.stdout + ft.stderr
    def states(text):
        return [tuple(map(float, re.findall(r'[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?', line)))
                for line in text.splitlines() if re.match(r'\s*[+-]?\d', line)
                and re.search(r'=\s*abc\s*\(', line)]
    expected = [(1.0, 2.0, 3.0), (1.0, 19.0, 3.0),
                (50.0, 60.0, 70.0, 50.0, 60.0, 70.0), (50.0, 60.0, 70.0)]
    assert states(py.stdout) == expected, py.stdout
    assert states(ft.stdout) == expected, ft.stdout
    print('PASS: unchanged abc.py compiles/runs; all 4 reported state transitions match Python and known values')


if __name__ == '__main__':
    main()
