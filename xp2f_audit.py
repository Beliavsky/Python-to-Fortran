"""Resumable build/run audit of historical Burkardt failures (no numerical verdict).

Example: python xp2f_audit.py --out reports/burkardt_audit_20260920
Resume:  python xp2f_audit.py --out reports/burkardt_audit_20260920 --resume
The compiler must be on PATH. Original sources and previous reports are not edited.
"""
import argparse
import collections
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
COMPILER = 'gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wfatal-errors'
GENERATED = {'.f90', '.f', '.o', '.obj', '.mod', '.smod', '.exe', '.dll', '.pyd', '.flags', '.pyc'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def parse_cases(text):
    cases = [dict(source=source, old_outcome=outcome, name=Path(source).stem)
             for source, outcome in re.findall(
                 r'^(\S+\.py)\s+FAIL\s+(transpile_fail|compile_fail|run_fail)\b', text, re.M)]
    if not cases or len({c['name'].lower() for c in cases}) != len(cases):
        raise ValueError('Expected a nonempty failure inventory with unique program names')
    return cases


def input_files(source):
    if not source.exists():
        return []
    return sorted(p for p in source.parent.iterdir()
                  if p.is_file() and p.suffix.lower() not in GENERATED)


def input_hashes(source):
    # Include sibling Python modules as well as runtime data.
    return {p.name: sha(p) for p in input_files(source)}


def command(cmd, cwd, logfile, limit):
    started = time.monotonic()
    with logfile.open('w', encoding='utf-8') as stream:
        stream.write(subprocess.list2cmdline(cmd) + '\n')
        stream.flush()
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=os.name != 'nt',
                                env={**os.environ, 'PYTHONUNBUFFERED': '1'})
        try:
            rc = proc.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True)
            else:
                os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            stream.write(f'\nAUDIT TIMEOUT after {limit}s\n')
            rc = 124
    return rc, round(time.monotonic() - started, 2)


def diagnostic(text, outcome):
    match = re.search(r'^Transpile: FAIL.*|^Error:.*|^Fortran runtime error:.*|'
                      r'^Program received signal.*|^.*(?:Error|Exception):.*|^AUDIT TIMEOUT.*', text, re.M)
    if match:
        return match[0]
    return 'Executed successfully; numerical agreement unverified' if outcome == 'run_pass' else outcome


def fatal_runtime_diagnostic(text):
    """Fortran STOP with a message can return zero; do not call that a pass.

    Conservatively flag textual STOP messages for review. Bare STOP and STOP 0
    are allowed; ordinary mentions of errors in descriptive prose are not matched.
    """
    for line in text.splitlines():
        s = line.strip()
        if (re.match(r'^ERROR STOP\b', s)
                or re.match(r'^STOP\s+(?!0\s*$).+', s)
                or re.search(r'(?i)(?:^|:\s*)Fatal error[!:]', s)
                or s.startswith(('Fortran runtime error:', 'Program received signal'))):
            return s
    return None


def diagnostic_group(message):
    # Group diagnostics without hiding their original details in the inventory.
    message = re.sub(r' at line \d+:.*', '', message)
    message = re.sub(r"'[^']*'", "'<name>'", message)
    return re.sub(r'\b\d+\b', '#', message)


def run_case(case, worker, out, config):
    source = Path(case['source'])
    dest = out / 'cases' / case['name']
    dest.mkdir(parents=True, exist_ok=True)
    result = dict(case, input_sha256=input_hashes(source), numerical_agreement='unverified')
    try:
        if not source.exists():
            result.update(outcome='missing_source', diagnostic='Original source does not exist')
        else:
            for p in input_files(source):
                if p.suffix.lower() != '.py':
                    shutil.copy2(p, dest / p.name)
            snapshot = out / 'toolchain'
            generated = dest / (source.stem + '_p.f90')
            cmd = [sys.executable, str(snapshot / 'xp2f.py'), str(source),
                   str(snapshot / 'python.f90'), str(snapshot / 'lapack_d.f90'),
                   '--out', str(generated), '--compile', '--compiler', config['compiler']]
            rc, seconds = command(cmd, worker, dest / 'build.log', config['build_timeout'])
            result.update(build_rc=rc, build_seconds=seconds)
            text = (dest / 'build.log').read_text(encoding='utf-8', errors='replace')
            if rc == 124:
                outcome = 'build_timeout'
            elif 'Transpile: FAIL' in text:
                outcome = 'transpile_fail'
            elif rc != 0 or 'Build: PASS' not in text:
                outcome = 'compile_fail' if 'Build: FAIL' in text else 'transpiler_crash'
            else:
                exe = generated.with_suffix('.exe')
                rc, seconds = command([str(exe)], dest, dest / 'run.log', config['run_timeout'])
                result.update(run_rc=rc, run_seconds=seconds)
                outcome = 'run_pass' if rc == 0 else 'run_timeout' if rc == 124 else 'run_fail'
                text = (dest / 'run.log').read_text(encoding='utf-8', errors='replace')
                fatal = fatal_runtime_diagnostic(text)
                if rc == 0 and fatal:
                    outcome = 'run_fail'
                    result['fatal_runtime_diagnostic'] = fatal
            result.update(outcome=outcome, diagnostic=diagnostic(text, outcome))
            if result.get('fatal_runtime_diagnostic'):
                result['diagnostic'] = result['fatal_runtime_diagnostic']
            if result['input_sha256'] != input_hashes(source):
                result.update(outcome='input_changed', diagnostic='Source/data changed during this case; use a new audit directory')
    except Exception as exc:
        result.update(outcome='audit_error', diagnostic=repr(exc))
    save_json(dest / 'result.json', result)
    return result


def report(out, results, manifest, baseline):
    results = sorted(results, key=lambda r: r['name'])
    save_json(out / 'results.json', results)
    counts = collections.Counter(r['outcome'] for r in results)
    lines = ['# Burkardt failure audit', '',
             f"Completed: {len(results)}/{len(manifest['cases'])}. Outcomes: {dict(counts)}", '',
             'Successful execution is NOT proof of numerical agreement. No Python/output comparison is performed.',
             'Missing data, interactive input and timeouts need manual triage; they are not automatically transpiler bugs.', '',
             '| Program | Historical | Previous audit | Current | First diagnostic |',
             '|---|---|---|---|---|']
    groups = collections.defaultdict(list)
    transitions = collections.Counter()
    for r in results:
        previous = baseline.get(r['name'], {}).get('outcome', 'not recorded')
        transitions[(previous, r['outcome'])] += 1
        log = 'run.log' if r['outcome'].startswith('run_') else 'build.log'
        message = r['diagnostic'].replace('|', '\\|').replace('\n', ' ')
        lines.append(f"| [{r['name']}](cases/{r['name']}/{log}) | {r['old_outcome']} | {previous} | {r['outcome']} | {message} |")
        if r['outcome'] != 'run_pass':
            groups[diagnostic_group(r['diagnostic'])].append(r['name'])
    lines += ['', '## Previous-to-current transitions', '']
    lines += [f'- {old} → {new}: {count}' for (old, new), count in sorted(transitions.items())]
    lines += ['', '## First-diagnostic groups (not distinct bug counts)', '']
    lines += [f'- {message}: {", ".join(names)}' for message, names in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))]
    temp = out / 'report.md.tmp'
    temp.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temp.replace(out / 'report.md')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--build-timeout', type=int, default=240)
    parser.add_argument('--run-timeout', type=int, default=30)
    parser.add_argument('--log', type=Path, default=ROOT / 'burkardt_python_results_20260816_7pm.txt')
    parser.add_argument('--baseline', type=Path, default=ROOT / 'reports/burkardt_recheck_20260915/results.json')
    args = parser.parse_args(argv)
    if min(args.workers, args.build_timeout, args.run_timeout) <= 0:
        parser.error('Workers and timeouts must be positive')
    out = args.out.resolve()
    cases = parse_cases(args.log.read_text(encoding='utf-8', errors='replace'))
    baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
    baseline = {r['name']: r for r in baseline}
    version = subprocess.check_output(['gfortran', '--version'], text=True).splitlines()[0]
    config = dict(compiler=COMPILER, compiler_version=version, python=sys.version,
                  python_executable=sys.executable, build_timeout=args.build_timeout,
                  run_timeout=args.run_timeout, historical_sha256=sha(args.log),
                  baseline_sha256=sha(args.baseline))
    if args.resume:
        manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['config'] != config or manifest['cases'] != cases:
            parser.error('Resume configuration differs from the saved audit; use a new output directory')
        if manifest['audit_script_sha256'] != sha(Path(__file__)):
            parser.error('Audit runner changed; use the saved runner in toolchain/ or a new output directory')
        for name, digest in manifest['toolchain_sha256'].items():
            if sha(out / 'toolchain' / name) != digest:
                parser.error('Audit toolchain snapshot changed; use a new output directory')
    else:
        if out.exists() and any(out.iterdir()):
            parser.error('Output directory is not empty; use --resume or a new directory')
        out.mkdir(parents=True, exist_ok=True)
        snapshot = out / 'toolchain'
        snapshot.mkdir()
        hashes = {}
        for p in sorted(ROOT.iterdir()):
            if p.is_file() and p.suffix.lower() in {'.py', '.f90', '.f', '.inc', '.pyf'}:
                shutil.copy2(p, snapshot / p.name)
                hashes[p.name] = sha(snapshot / p.name)
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
        dirty = subprocess.run(['git', 'status', '--short', '--untracked-files=no'], cwd=ROOT, capture_output=True, text=True)
        manifest = dict(created_utc=datetime.now(timezone.utc).isoformat(), config=config,
                        git_revision=revision.stdout.strip(), tracked_changes=dirty.stdout.strip(),
                        toolchain_sha256=hashes, cases=cases,
                        audit_script_sha256=sha(Path(__file__)), baseline=str(args.baseline.resolve()))
        save_json(out / 'manifest.json', manifest)
    # Exclusive lock prevents two resumptions from sharing helper caches/results.
    lock = out / 'audit.lock'
    try:
        handle = lock.open('x', encoding='utf-8')
    except FileExistsError:
        parser.error('audit.lock exists: another audit may be running. Remove it only after verifying its PID is no longer running.')
    try:
        with handle:
            handle.write(str(os.getpid()))
        results, pending = [], []
        for case in cases:
            saved = out / 'cases' / case['name'] / 'result.json'
            if saved.exists():
                r = json.loads(saved.read_text(encoding='utf-8'))
                if r['input_sha256'] != input_hashes(Path(case['source'])):
                    parser.error(f"Inputs for {case['name']} changed; use a new audit directory")
                results.append(r)
            else:
                pending.append(case)
        report(out, results, manifest, baseline)
        print(f"Audit: {len(cases)} cases; {len(results)} resumed; {len(pending)} pending. Snapshot: {out / 'toolchain'}", flush=True)
        workers = queue.Queue()
        for i in range(args.workers):
            worker = out / f'worker_{i}'
            worker.mkdir(exist_ok=True)
            workers.put(worker)
        def work(case):
            worker = workers.get()
            try:
                return run_case(case, worker, out, config)
            finally:
                workers.put(worker)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(work, case) for case in pending]
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                results.append(r)
                report(out, results, manifest, baseline)
                print(f"[{len(results)}/{len(cases)}] {r['name']}: {r['old_outcome']} -> {r['outcome']}", flush=True)
        print(f"Audit complete: {out / 'report.md'}", flush=True)
    finally:
        lock.unlink()


if __name__ == '__main__':
    main()
