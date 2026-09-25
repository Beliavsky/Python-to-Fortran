"""Validate the unchanged packing driver using identical recorded RNG draws."""
import argparse
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/circle_circles_packing/circle_circles_packing.py'))
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    root = out.parents[1]
    work = out / 'work'
    work.mkdir(exist_ok=True)
    source = work / 'circle_circles_packing.py'
    shutil.copy2(args.source, source)
    proc = subprocess.run(
        [sys.executable, str(root / 'xp2f.py'), str(source),
         '--compile', '--run-diff', '--rng-replay'],
        cwd=work, capture_output=True, text=True, timeout=300)
    text = proc.stdout
    (out / 'run.log').write_text(text + proc.stderr, encoding='utf-8')
    assert 'Build: PASS' in text and 'Run: PASS' in text, text + proc.stderr
    py = text.split('Run (python): PASS\n', 1)[1].split('\nwrote ', 1)[0]
    ft = text.split('Run: PASS\n', 1)[1].split('\nRun diff:', 1)[0]
    (out / 'python.stdout').write_text(py, encoding='utf-8')
    (out / 'fortran.stdout').write_text(ft, encoding='utf-8')
    labels = ['Number of "cars" parked', 'Number of parking trials',
              'density_obs', 'jamming density']

    def values(output):
        result = []
        for label in labels:
            matches = re.findall(re.escape(label) + r'\s*=\s*([-+\d.eE]+)', output)
            assert len(matches) == 1, (label, output)
            result.append(float(matches[0]))
        return result

    p, f = values(py), values(ft)
    assert p[:2] == f[:2], (p, f)
    assert all(math.isclose(a, b, rel_tol=1.e-12, abs_tol=1.e-12)
               for a, b in zip(p[2:], f[2:])), (p, f)
    assert p[0] > 0 and p[1] >= p[0] + 5000, p
    assert math.isclose(p[2], p[0] / 400.0, rel_tol=1.e-12), p
    print(f'PASS: parked={int(p[0])}, trials={int(p[1])}, density={p[2]}; '
          'both counts and both densities match with RNG replay')
    print('Comparison excludes timestamps and version banners; source unchanged.')


if __name__ == '__main__':
    main()
