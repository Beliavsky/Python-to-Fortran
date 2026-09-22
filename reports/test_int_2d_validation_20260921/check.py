"""Recheck the reduced integrands and record the full corpus blocker."""
import json
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = Path('C:/python/public_domain/burkardt/test_int_2d/test_int_2d.py')


def run(args, name):
    proc = subprocess.run([sys.executable, str(ROOT / 'xp2f.py'), *args],
                          cwd=OUT, capture_output=True, text=True, timeout=300)
    (OUT / (name + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
    return proc


probe = run(['probe.py', '--compile', '--run-diff'], 'probe')
assert probe.returncode == 0 and 'Run diff: MATCH' in probe.stdout, probe.stdout + probe.stderr
full = run([str(SOURCE), '--out', 'test_int_2d_p.f90', '--compile'], 'full')
result = dict(probe='PASS', full_returncode=full.returncode,
              full_diagnostic=(full.stdout + full.stderr).strip())
(OUT / 'analysis.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
