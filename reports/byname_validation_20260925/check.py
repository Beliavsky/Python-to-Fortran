"""Check the unchanged byname function with a numeric-only state trace."""
import argparse
import ast
from pathlib import Path
import re
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/persistence/byname.py'))
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    source = args.source.resolve()
    text = source.read_text(encoding='utf-8')
    fn = next(n for n in ast.parse(text).body
              if isinstance(n, ast.FunctionDef) and n.name == 'byname')
    probe = work / 'numeric_byname.py'
    probe.write_text(ast.get_source_segment(text, fn) + '\n\n' + '\n'.join([
        'byname()',
        'print(byname("GET", "Alpha"))',
        'print(byname("Set", "beta", -2.5))',
        'print(byname("get", "BETA"))',
        'print(byname("set", "gamma", 0.0))',
        'print(byname("get", "gamma"))',
        'print(byname("reset", "beta"))',
        'byname("reset", None, None)',
        'byname(None, None, None)',
        'print(byname(action="get", name="gamma"))',
        '',
    ]), encoding='utf-8')

    def run(command, label):
        proc = subprocess.run(command, cwd=work, capture_output=True,
                              text=True, timeout=300)
        (out / (label + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
        return proc

    # Preserve evidence of the remaining full-program blocker as well.
    full = run([sys.executable, str(root / 'xp2f.py'), str(source),
                '--out', str(work / 'byname_p.f90'), '--compile'], 'full')
    print('Full original build:', 'PASS' if full.returncode == 0 else 'FAIL (see full.log)')
    py = run([sys.executable, str(probe)], 'python')
    assert py.returncode == 0, py.stdout + py.stderr
    generated = work / 'numeric_byname_p.f90'
    build = run([sys.executable, str(root / 'xp2f.py'), str(probe),
                 '--out', str(generated), '--compile'], 'build')
    assert build.returncode == 0, build.stdout + build.stderr
    ft = run([str(generated.with_suffix('.exe' if sys.platform == 'win32' else ''))], 'fortran')
    assert ft.returncode == 0, ft.stdout + ft.stderr
    expected = [1, 2, 3, 1, -2.5, -2.5, 0, 0, 2, 1, 2, 3, 3]
    def values(output):
        return [float(x) for x in re.findall(r'[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?', output)]
    assert values(py.stdout) == expected, py.stdout
    assert values(ft.stdout) == expected, ft.stdout
    assert re.sub(r'\s+', '', py.stdout).count('alpha=') == 2
    assert re.sub(r'\s+', '', ft.stdout).count('alpha=') == 2
    print('PASS: numeric-only driver, unchanged function, 13 values match Python and known state trace')


if __name__ == '__main__':
    main()
