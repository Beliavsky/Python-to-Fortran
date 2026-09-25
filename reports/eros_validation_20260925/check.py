"""Save a full unchanged eros.py compile/run comparison with RNG replay."""
import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys


def compare_log(text, out):
    assert 'Build: PASS' in text and 'Run: PASS' in text, text[-2000:]
    py = text.split('Run (python): PASS\n', 1)[1].split('\nwrote ', 1)[0]
    ft = text.split('Run: PASS\n', 1)[1].split('\nRun diff:', 1)[0]
    (out / 'python.stdout').write_text(py, encoding='utf-8')
    (out / 'fortran.stdout').write_text(ft, encoding='utf-8')

    def numbers(output):
        lines = [line for line in output.splitlines() if 'version:' not in line
                 and not re.match(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun) ', line)]
        return [float(v) for v in re.findall(
            r'(?<![A-Za-z_])[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', '\n'.join(lines))]

    def differences(a, b):
        return [(i, x, y) for i, (x, y) in enumerate(zip(a, b))
                if not math.isclose(x, y, rel_tol=1.e-6, abs_tol=1.e-8)]

    for name, next_name in [('gauss_test1', 'gauss_test2'), ('gauss_test2', 'gauss_det_test')]:
        def section(output):
            return numbers(output.split(name + '():', 1)[1].split(next_name + '():', 1)[0])
        a, b = section(py), section(ft)
        assert len(a) == len(b) and not differences(a, b), (name, a, b)
        print(f'MATCH: {name}, {len(a)} numeric tokens')
    a, b = numbers(py), numbers(ft)
    mismatches = differences(a, b)
    print(f'Full numeric streams: {len(a)} Python / {len(b)} Fortran tokens')
    if len(a) != len(b) or mismatches:
        print('DIFF: first numeric mismatches (zero-based index, Python, Fortran):', mismatches[:8])
        return 1
    print('MATCH: full numeric streams (not a byte-for-byte text comparison)')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/eros/eros.py'))
    parser.add_argument('--check-log', action='store_true')
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    if args.check_log:
        return compare_log((out / 'run.log').read_text(encoding='utf-8'), out)
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    source = work / 'eros.py'
    shutil.copy2(args.source, source)
    proc = subprocess.run(
        [sys.executable, str(root / 'xp2f.py'), str(source),
         '--compile', '--run-diff', '--rng-replay'],
        cwd=work, input='', capture_output=True, text=True, timeout=300)
    (out / 'run.log').write_text(proc.stdout + proc.stderr, encoding='utf-8')
    for line in proc.stdout.splitlines():
        if line.startswith(('Transpile:', 'Build:', 'Run:', 'Run (python):', 'Run diff:')):
            print(line)
    print('Full output saved to', out / 'run.log')
    # A successful process exit alone does not certify numerical agreement.
    return proc.returncode or compare_log(proc.stdout, out)


if __name__ == '__main__':
    raise SystemExit(main())
