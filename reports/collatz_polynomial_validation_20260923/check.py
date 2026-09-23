"""Validate local parameter rebinding and original Collatz polynomial tests."""
import ast
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    'C:/python/public_domain/burkardt/collatz_polynomial/collatz_polynomial.py')


def canonical(text):
    lines = []
    for line in text.splitlines():
        if not line.strip() or 'version:' in line:
            continue
        tokens = re.findall(r'\d+(?:\.\d*)?(?:[Ee][+-]?\d+)?|[A-Za-z_]+|[^\s\[\]]', line)
        lines.append(tuple(format(Decimal(t).normalize(), 'f') if t[0].isdigit() else t for t in tokens))
    return lines


def run(source, name, compare=True, require_match=True):
    command = [sys.executable, str(ROOT / 'xp2f.py'), str(source), '--compile',
               '--out', str(OUT / (name + '_p.f90'))]
    if compare:
        command.append('--run-diff')
    proc = subprocess.run(command, cwd=OUT, capture_output=True, text=True, timeout=180)
    (OUT / (name + '.log')).write_text(proc.stdout + proc.stderr, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    if compare and require_match:
        if name == 'corpus_probe':
            python_output = proc.stdout.split('Run (python): PASS\n', 1)[1].split('\nwrote ', 1)[0]
            fortran_output = proc.stdout.split('\nRun: PASS\n', 1)[1].split('\nRun diff:', 1)[0]
            assert canonical(python_output) == canonical(fortran_output), proc.stdout + proc.stderr
            return 'NORMALIZED MATCH (version banners, whitespace, array brackets excluded)'
        assert 'Run diff: MATCH' in proc.stdout, proc.stdout + proc.stderr
    return ('MATCH' if 'Run diff: MATCH' in proc.stdout else 'DIFF') if compare else 'COMPILE PASS'


results = {'focused': run(OUT / 'probe.py', 'probe')}
source = SOURCE.read_text(encoding='utf-8')
functions = [ast.get_source_segment(source, node) for node in ast.parse(source).body
             if isinstance(node, ast.FunctionDef)]
# Keep the original function bodies; omit only the top-level timestamp wrapper.
driver = '''
import numpy as np
collatz_polynomial_test()
original = np.array([1.0, 0.0, 1.0])
collatz_polynomial_sequence(original)
print(len(original))
for i in range(len(original)):
    print(original[i])
'''
probe = OUT / 'corpus_probe.py'
probe.write_text('\n\n'.join(functions) + '\n' + driver, encoding='utf-8')
results['original_tests_and_caller_preservation'] = run(probe, 'corpus_probe')
results['full_original'] = run(SOURCE, 'full', compare=False)
# Record a distinct, unresolved argument-kind inference issue without treating
# successful compilation of that exploratory variant as numerical validation.
fractional = OUT / 'fractional_probe.py'
fractional.write_text((OUT / 'probe.py').read_text(encoding='utf-8')
                      .replace('7.0', '7.25').replace('[1.0, 2.0, 3.0]', '[1.5, 2.5, 3.5]'),
                      encoding='utf-8')
results['fractional_forwarding_followup'] = run(fractional, 'fractional_probe', require_match=False)
(OUT / 'analysis.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
