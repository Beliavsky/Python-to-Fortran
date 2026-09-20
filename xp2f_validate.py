"""Compare successful audited executables with Python; preserve all raw evidence."""
import argparse
import ast
import concurrent.futures
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

from xp2f_audit import fatal_runtime_diagnostic, input_files, input_hashes, save_json, sha

NUMBER = re.compile(r'(?<![\w.])[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eEdD][-+]?\d+)?(?![\w.])')
STAMP = re.compile(r'^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d+\s+\d+:\d+:\d+\s+\d+$')


def normalized(text):
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if STAMP.fullmatch(s) or re.match(r'(?i)^(?:python|numpy) version\s*:', s):
            continue
        lines.append(s)
    return ' '.join(' '.join(lines).split())


def rounding_unit(token):
    if '.' not in token and not re.search('[eEdD]', token):
        return 0.0
    mantissa, *exponent = re.split('[eEdD]', token)
    decimals = len(mantissa.split('.')[1]) if '.' in mantissa else 0
    try:
        return 0.5 * 10.0 ** ((int(exponent[0]) if exponent else 0) - decimals)
    except OverflowError:
        return float('inf')


def close_tokens(a, b):
    if not any(c in a + b for c in '.eEdD'):
        return int(a) == int(b)
    x, y = float(a.lower().replace('d', 'e')), float(b.lower().replace('d', 'e'))
    if not math.isfinite(x) or not math.isfinite(y):
        return x == y
    tolerance = max(rounding_unit(a), rounding_unit(b), 1e-8 * max(abs(x), abs(y)), 1e-10)
    return abs(x - y) <= tolerance * (1 + 1e-12)


def compare_text(python, fortran):
    a, b = normalized(python), normalized(fortran)
    aa, bb = NUMBER.findall(a), NUMBER.findall(b)
    mismatch = []
    for i, (x, y) in enumerate(zip(aa, bb)):
        if not close_tokens(x, y):
            mismatch.append(dict(index=i, python=x, fortran=y))
    shape_a = NUMBER.sub('#', a)
    shape_b = NUMBER.sub('#', b)
    same_numbers = len(aa) == len(bb) and not mismatch
    status = 'matched' if same_numbers and shape_a == shape_b else 'unverified' if same_numbers else 'mismatched'
    complex_layout = bool(re.search(r'[\d.]j\b', a) and re.search(r'\([\s+\-\d.eE]+,', b))
    if complex_layout and shape_a != shape_b:
        status = 'unverified'
    return dict(status=status, python_numbers=len(aa), fortran_numbers=len(bb),
                numeric_mismatches=mismatch[:20], text_structure_equal=shape_a == shape_b,
                reason='Complex array layout/order requires a format-aware comparison' if complex_layout and shape_a != shape_b else
                'Output agrees at printed precision' if status == 'matched' else
                'Numbers agree but text/layout needs review' if status == 'unverified' else
                'Numeric output differs; inspect logs before diagnosing a transpiler defect')


def nondeterminism(source):
    tree = ast.parse(source)
    unsupported = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import) and any(a.name == 'random' for a in n.names):
            unsupported.add('stdlib random')
        if isinstance(n, ast.ImportFrom) and n.module == 'random':
            unsupported.add('stdlib random')
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr in {'integers', 'randint', 'choice', 'shuffle', 'permutation', 'poisson', 'exponential', 'binomial'}:
                unsupported.add(n.func.attr)
        if isinstance(n, ast.FunctionDef) and n.name == 'get_seed':
            unsupported.add('clock-derived seed')
    return sorted(unsupported)


def run(cmd, cwd, prefix, timeout, env):
    started = time.monotonic()
    with prefix.with_suffix('.stdout').open('w', encoding='utf-8') as stdout, prefix.with_suffix('.stderr').open('w', encoding='utf-8') as stderr:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
                                env=env, start_new_session=os.name != 'nt')
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            rc = 124
    return dict(command=cmd, rc=rc, seconds=round(time.monotonic() - started, 2))


def output_files(directory, initial):
    return {str(p.relative_to(directory)): sha(p) for p in directory.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and
            (str(p.relative_to(directory)) not in initial or sha(p) != initial[str(p.relative_to(directory))])}


def validate(case, audit, out, timeout):
    dest = out / 'cases' / case['name']
    dest.mkdir(parents=True)
    result = dict(name=case['name'], status='unverified', reason='', comparison_scope='stdout and generated files')
    try:
        source = Path(case['source'])
        if input_hashes(source) != case['input_sha256']:
            raise ValueError('Original inputs changed since audit; cannot validate the saved executable against them')
        py, ft = dest / 'python', dest / 'fortran'
        py.mkdir()
        ft.mkdir()
        for p in input_files(source):
            shutil.copy2(p, py / p.name)
            if p.suffix.lower() != '.py':
                shutil.copy2(p, ft / p.name)
        initial_py = {p.name: sha(p) for p in py.iterdir()}
        initial_ft = {p.name: sha(p) for p in ft.iterdir()}
        executable = audit / 'cases' / case['name'] / (case['name'] + '_p.exe')
        result['executable_sha256'] = sha(executable)
        result['input_sha256'] = case['input_sha256']
        result['uncontrolled_randomness'] = nondeterminism(source.read_text(encoding='utf-8'))
        replay = dest / 'rng_replay'
        env = {**os.environ, 'PYTHONUNBUFFERED': '1', 'MPLBACKEND': 'Agg',
               'PYTHONPATH': str(py), 'XP2F_RNG_REPLAY_STEM': str(replay)}
        wrapper = out / 'rng_wrapper.py'
        result['python_run'] = run([sys.executable, str(wrapper), str(py / source.name), str(replay)], py, dest / 'python', timeout, env)
        if result['python_run']['rc']:
            result['reason'] = 'Python reference failed or timed out; see python.stderr'
        else:
            result['rng_recorded_calls'] = len(replay.with_suffix('.meta').read_text().splitlines())
            result['fortran_run'] = run([str(executable)], ft, dest / 'fortran', timeout, env)
            stderr = (dest / 'fortran.stderr').read_text(errors='replace')
            runtime_text = (dest / 'fortran.stdout').read_text(errors='replace') + '\n' + stderr
            if result['fortran_run']['rc'] or 'rng replay:' in stderr or fatal_runtime_diagnostic(runtime_text):
                result['reason'] = 'Fortran failed, timed out, or rejected RNG replay; see fortran.stderr'
            else:
                comparison = compare_text((dest / 'python.stdout').read_text(errors='replace'),
                                          (dest / 'fortran.stdout').read_text(errors='replace'))
                result.update(comparison)
                result['stdout_comparison'] = comparison
                generated_py, generated_ft = output_files(py, initial_py), output_files(ft, initial_ft)
                result['generated_python_files'] = generated_py
                result['generated_fortran_files'] = generated_ft
                artifacts = {}
                for name in sorted(generated_py.keys() | generated_ft.keys()):
                    if not (py / name).exists() or not (ft / name).exists():
                        artifacts[name] = dict(status='unverified', reason='File produced by only one implementation')
                    elif sha(py / name) == sha(ft / name):
                        artifacts[name] = dict(status='matched', reason='Identical bytes')
                    else:
                        try:
                            artifacts[name] = compare_text((py / name).read_text(encoding='utf-8'), (ft / name).read_text(encoding='utf-8'))
                        except UnicodeError:
                            artifacts[name] = dict(status='unverified', reason='Different binary files; format-specific comparison needed')
                result['artifacts'] = artifacts
                if any(v['status'] == 'mismatched' for v in artifacts.values()):
                    result.update(status='mismatched', reason='Generated file numerical contents differ')
                elif result['status'] == 'matched' and any(v['status'] != 'matched' for v in artifacts.values()):
                    result.update(status='unverified', reason='Generated files require review')
                if result['uncontrolled_randomness']:
                    result.update(status='unverified', reason='Unsupported randomness/clock-derived seed; differences cannot yet establish equivalence or a defect')
        if input_hashes(source) != case['input_sha256']:
            result.update(status='unverified', reason='Original inputs changed during validation')
    except Exception as exc:
        result.update(status='unverified', reason=repr(exc))
    save_json(dest / 'result.json', result)
    return result


def report(out, results, total):
    save_json(out / 'results.json', sorted(results, key=lambda r: r['name']))
    counts = {s: sum(r['status'] == s for r in results) for s in ('matched', 'mismatched', 'unverified')}
    lines = ['# Burkardt execution validation', '', f'Completed: {len(results)}/{total}. {counts}', '',
             'Matched means observed output agrees, not proof of all internal results. Mismatches are candidates for investigation, not confirmed transpiler bugs.',
             'Numeric comparison: integers exact; reals allow half a printed last-place unit, relative tolerance 1e-8, or absolute tolerance 1e-10. Only timestamp/version lines and whitespace are normalized.',
             'Unsupported RNG methods and clock-derived seeds remain unverified. Replay validates supported recorded draws, not RNG distributions.', '',
             '| Program | Status | Reason |', '|---|---|---|']
    for r in sorted(results, key=lambda r: r['name']):
        reason = r['reason'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f"| [{r['name']}](cases/{r['name']}/result.json) | {r['status']} | {reason} |")
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args()
    audit, out = args.audit.resolve(), args.out.resolve()
    if min(args.workers, args.timeout) <= 0:
        parser.error('Workers and timeout must be positive')
    if out.exists() and any(out.iterdir()):
        parser.error('Use a new empty output directory; previous results are never overwritten')
    manifest = json.loads((audit / 'manifest.json').read_text())
    for name, digest in manifest['toolchain_sha256'].items():
        if sha(audit / 'toolchain' / name) != digest:
            parser.error('Audit toolchain snapshot changed')
    cases = [r for r in json.loads((audit / 'results.json').read_text()) if r['outcome'] == 'run_pass']
    out.mkdir(parents=True, exist_ok=True)
    # Generate the recorder from the audited transpiler, not the current workspace.
    subprocess.run([sys.executable, '-c', 'import sys; from pathlib import Path; import xp2f; xp2f._write_rng_replay_wrapper(Path(sys.argv[1]))',
                    str(out / 'rng_wrapper.py')], cwd=audit / 'toolchain', check=True)
    save_json(out / 'manifest.json', dict(audit=str(audit), audit_manifest_sha256=sha(audit / 'manifest.json'),
              validator_sha256=sha(Path(__file__)), python=sys.version, numpy=importlib.metadata.version('numpy'),
              timeout=args.timeout, cases=[r['name'] for r in cases]))
    results = []
    report(out, results, len(cases))
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(validate, c, audit, out, args.timeout) for c in cases]
        for f in concurrent.futures.as_completed(futures):
            r = f.result()
            results.append(r)
            report(out, results, len(cases))
            print(f"[{len(results)}/{len(cases)}] {r['name']}: {r['status']} — {r['reason']}", flush=True)
    print(f'Validation complete: {out / "report.md"}', flush=True)


if __name__ == '__main__':
    main()
