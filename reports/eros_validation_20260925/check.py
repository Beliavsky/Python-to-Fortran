"""Save a full unchanged eros.py compile/run comparison with RNG replay."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(
        'C:/python/public_domain/burkardt/eros/eros.py'))
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
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
    return proc.returncode


if __name__ == '__main__':
    raise SystemExit(main())
