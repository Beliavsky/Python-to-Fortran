"""Exercise run logging with small subprocess suites, never the transpiler suite."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_suite(tmp_path, source, *args):
    shutil.copy2(ROOT / "pytest_runlog.py", tmp_path / "pytest_runlog.py")
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["pytest_runlog"]\n', encoding="utf-8")
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "test_sample.py").write_text(source, encoding="utf-8")
    env = os.environ.copy()
    for key in ("PYTEST_ADDOPTS", "PYTEST_XDIST_WORKER", "PYTEST_XDIST_WORKER_COUNT", "PYTEST_CURRENT_TEST"):
        env.pop(key, None)
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", *args], cwd=tmp_path,
                          env=env, capture_output=True, text=True, timeout=90)
    logs = list((tmp_path / "reports" / "pytest").glob("*.jsonl"))
    assert len(logs) == 1, proc.stdout + proc.stderr
    events = [json.loads(line) for line in logs[0].read_text(encoding="utf-8").splitlines()]
    report = logs[0].with_suffix(".txt").read_text(encoding="utf-8")
    assert events[0]["event"] == "session_start"
    assert events[-1]["event"] == "session_finish", proc.stdout + proc.stderr
    return proc, events, report


@pytest.mark.parametrize("workers", ["0", "2"])
def test_runlog_outcomes_and_reruns(tmp_path, workers):
    source = '''
import pytest
attempt = 0
def test_pass(): pass
def test_fail():
    print("captured failure output")
    assert False, "persistent failure"
def test_flaky():
    global attempt
    attempt += 1
    assert attempt > 1, "first attempt failed"
@pytest.mark.skip(reason="skip reason")
def test_skip(): pass
@pytest.mark.xfail(reason="expected")
def test_xfail(): assert False
@pytest.mark.xfail(reason="unexpected", strict=False)
def test_xpass(): pass
@pytest.fixture
def broken_setup(): raise RuntimeError("setup failure")
def test_setup(broken_setup): pass
@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("teardown failure")
def test_teardown(broken_teardown): pass
'''
    proc, events, report = run_suite(tmp_path, source, "-n", workers, "--reruns", "1")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    final = events[-1]
    assert final["status"] == "finished"
    assert final["counts"]["collected"] == 8
    assert final["counts"]["completed"] == 8
    assert {k: final["counts"][k] for k in ("passed", "failed", "skipped", "xfailed", "xpassed", "reruns")} == {
        "passed": 2, "failed": 3, "skipped": 1, "xfailed": 1, "xpassed": 1, "reruns": 4}
    for text in ("persistent failure", "first attempt failed", "setup failure", "teardown failure", "captured failure output"):
        assert text in report
    flaky = next(t for t in final["tests"] if t["nodeid"].endswith("test_flaky"))
    assert flaky["attempts"] == 2 and flaky["outcome"] == "passed"
    assert flaky["start"] <= flaky["end"] and flaky["duration"] >= 0
    assert final["elapsed"] > 0
    assert events[0]["tracked_dirty"] is None  # isolated directory, no Git repository


def test_runlog_interrupted(tmp_path):
    proc, events, report = run_suite(tmp_path, "def test_a(): pass\ndef test_b(): raise KeyboardInterrupt()\n", "-n", "0")
    assert proc.returncode == 2
    assert events[-1]["status"] == "incomplete"
    assert events[-1]["counts"]["passed"] == 1
    assert events[-1]["counts"]["incomplete"] == 1
    assert any(e["event"] == "interrupted" for e in events)
    assert "incomplete" in report


@pytest.mark.parametrize("workers", ["0", "2"])
def test_runlog_collection_error(tmp_path, workers):
    proc, events, report = run_suite(tmp_path, "raise RuntimeError('collection broken')\n", "-n", workers)
    assert proc.returncode != 0
    assert events[-1]["counts"]["collection_errors"] == 1
    assert "collection broken" in report


def test_runlog_failfast(tmp_path):
    proc, events, report = run_suite(tmp_path, "def test_a(): assert False\ndef test_b(): pass\n", "-n", "0", "-x")
    assert proc.returncode == 1
    assert events[-1]["status"] == "incomplete"
    assert events[-1]["counts"]["collected"] == 2
    assert events[-1]["counts"]["completed"] == 1


def fake_config(tmp_path):
    return SimpleNamespace(rootpath=tmp_path, invocation_params=SimpleNamespace(args=()),
                           getini=lambda name: [], getoption=lambda name, default=None: default)


def test_runlog_incremental_and_unique_paths(tmp_path):
    from pytest_runlog import RunLog
    first = RunLog(fake_config(tmp_path))
    second = RunLog(fake_config(tmp_path))
    try:
        assert first.path != second.path
        first.pytest_runtest_logstart("test_sample.py::test_pending", None)
        events = [json.loads(line) for line in first.path.with_suffix(".jsonl").read_text(encoding="utf-8").splitlines()]
        assert [event["event"] for event in events] == ["session_start", "test_start"]
        assert "running/incomplete" in first.path.with_suffix(".txt").read_text(encoding="utf-8")
    finally:
        first.pytest_unconfigure(None)
        second.pytest_unconfigure(None)


def test_runlog_unwritable_destination_is_nonfatal(tmp_path, capsys):
    from pytest_runlog import RunLog
    (tmp_path / "reports").write_text("not a directory", encoding="utf-8")
    log = RunLog(fake_config(tmp_path))
    assert log.disabled
    log.event("ignored")
    log.pytest_sessionfinish(SimpleNamespace(testscollected=0), 0)
    log.pytest_unconfigure(None)
    assert "pytest run logging disabled" in capsys.readouterr().err
