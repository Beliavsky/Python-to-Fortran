"""Fast audit-harness tests; no transpilation or Fortran compiler required."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('xp2f_audit', Path(__file__).resolve().parents[1] / 'xp2f_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_parse_inventory():
    text = 'c:/src/a.py FAIL compile_fail\nc:/src/b.py PASS run_pass\nc:/src/c.py FAIL run_fail\n'
    assert [c['name'] for c in audit.parse_cases(text)] == ['a', 'c']
    with pytest.raises(ValueError):
        audit.parse_cases(text + 'c:/other/a.py FAIL compile_fail\n')


def test_input_fingerprint_tracks_sibling_modules_and_data(tmp_path):
    source = tmp_path / 'a.py'
    source.write_text('print(1)')
    (tmp_path / 'helper.py').write_text('value = 1')
    (tmp_path / 'data.txt').write_text('1')
    (tmp_path / 'a_p.f90').write_text('generated')
    before = audit.input_hashes(source)
    assert set(before) == {'a.py', 'helper.py', 'data.txt'}
    (tmp_path / 'helper.py').write_text('value = 2')
    assert audit.input_hashes(source) != before


@pytest.mark.parametrize('build_rc,build_text,run_rc,outcome', [
    (1, 'Transpile: FAIL (unsupported at line 3: x)', None, 'transpile_fail'),
    (1, 'Build: FAIL\nError: Rank mismatch', None, 'compile_fail'),
    (1, 'Traceback\nValueError: broken', None, 'transpiler_crash'),
    (124, 'AUDIT TIMEOUT after 240s', None, 'build_timeout'),
    (0, 'Build: PASS', 0, 'run_pass'),
    (0, 'Build: PASS', 2, 'run_fail'),
    (0, 'Build: PASS', 124, 'run_timeout'),
])
def test_checkpoint_outcomes(tmp_path, monkeypatch, build_rc, build_text, run_rc, outcome):
    srcdir = tmp_path / 'source'
    srcdir.mkdir()
    source = srcdir / 'a.py'
    source.write_text('print(1)')
    def fake_command(cmd, cwd, logfile, limit):
        build = logfile.name == 'build.log'
        logfile.write_text(build_text if build else 'Fortran runtime error: test' if run_rc == 2 else '')
        return (build_rc if build else run_rc), 0.1
    monkeypatch.setattr(audit, 'command', fake_command)
    result = audit.run_case(dict(source=str(source), name='a', old_outcome='compile_fail'), tmp_path,
                            tmp_path / 'out', dict(compiler='unused', build_timeout=240, run_timeout=30))
    assert result['outcome'] == outcome
    assert result['numerical_agreement'] == 'unverified'
    assert json.loads((tmp_path / 'out/cases/a/result.json').read_text()) == result


def test_report_does_not_call_execution_numerically_correct(tmp_path):
    result = dict(name='a', outcome='run_pass', old_outcome='compile_fail', diagnostic='Executed successfully; numerical agreement unverified')
    audit.report(tmp_path, [result], dict(cases=[{}, {}]), {})
    text = (tmp_path / 'report.md').read_text(encoding='utf-8')
    assert 'Completed: 1/2' in text
    assert 'NOT proof of numerical agreement' in text
    assert 'not recorded → run_pass: 1' in text


def test_missing_source_is_checkpointed(tmp_path):
    case = dict(source=str(tmp_path / 'missing.py'), name='missing', old_outcome='compile_fail')
    result = audit.run_case(case, tmp_path, tmp_path / 'out', {})
    assert result['outcome'] == 'missing_source'
    assert (tmp_path / 'out/cases/missing/result.json').exists()


@pytest.mark.parametrize('text', ['STOP random_choice_norep: invalid sizes',
                                 'ERROR STOP bad file', 'distance_from_file(): Fatal error!',
                                 'STOP 1', 'Fortran runtime error: bad index'])
def test_fatal_runtime_messages(text):
    assert audit.fatal_runtime_diagnostic(text) == text


@pytest.mark.parametrize('text', ['STOP', 'STOP 0', '  Normal end of execution.',
                                 'This test prints a fatal error estimate.'])
def test_normal_runtime_messages(text):
    assert audit.fatal_runtime_diagnostic(text) is None


def test_zero_exit_fatal_stop_is_not_a_pass(tmp_path, monkeypatch):
    source = tmp_path / 'a.py'
    source.write_text('print(1)')
    def fake_command(cmd, cwd, logfile, limit):
        logfile.write_text('Build: PASS' if logfile.name == 'build.log' else 'STOP invalid sizes\n')
        return 0, 0.1
    monkeypatch.setattr(audit, 'command', fake_command)
    r = audit.run_case(dict(source=str(source), name='a', old_outcome='compile_fail'), tmp_path,
                       tmp_path / 'out', dict(compiler='unused', build_timeout=240, run_timeout=30))
    assert r['outcome'] == 'run_fail'
    assert r['run_rc'] == 0
    assert r['diagnostic'] == 'STOP invalid sizes'


def test_resume_skips_completed_cases_and_rejects_changed_inputs(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    root.mkdir()
    (root / 'xp2f.py').write_text('# snapshot')
    src = tmp_path / 'source'
    src.mkdir()
    source = src / 'a.py'
    source.write_text('print(1)')
    log = tmp_path / 'historical.txt'
    log.write_text(f'{source.as_posix()} FAIL compile_fail\n')
    baseline = tmp_path / 'baseline.json'
    baseline.write_text('[]')
    out = tmp_path / 'audit'
    args = ['--out', str(out), '--log', str(log), '--baseline', str(baseline)]
    calls = []
    def fake_command(cmd, cwd, logfile, limit):
        calls.append(logfile.name)
        logfile.write_text('Build: PASS' if logfile.name == 'build.log' else 'done')
        return 0, 0.1
    monkeypatch.setattr(audit, 'ROOT', root)
    monkeypatch.setattr(audit, 'command', fake_command)
    monkeypatch.setattr(audit.subprocess, 'check_output', lambda *a, **k: 'test compiler\n')
    audit.main(args)
    original_manifest = (out / 'manifest.json').read_bytes()
    assert calls == ['build.log', 'run.log']
    audit.main(args + ['--resume'])
    assert calls == ['build.log', 'run.log']
    assert not (out / 'audit.lock').exists()
    with pytest.raises(SystemExit):
        audit.main(args)  # Cannot overwrite the first audit.
    with pytest.raises(SystemExit):
        audit.main(args + ['--resume', '--build-timeout', '241'])
    assert (out / 'manifest.json').read_bytes() == original_manifest
    source.write_text('print(2)')
    with pytest.raises(SystemExit):
        audit.main(args + ['--resume'])
    assert not (out / 'audit.lock').exists()
    source.write_text('print(1)')
    (out / 'toolchain/xp2f.py').write_text('# corrupted snapshot')
    with pytest.raises(SystemExit):
        audit.main(args + ['--resume'])
