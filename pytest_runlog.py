"""Controller-only, incremental pytest run reports (no extra dependencies)."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def _stamp(seconds):
    return dt.datetime.fromtimestamp(seconds).astimezone().isoformat(timespec="milliseconds")


def _git(root, *args):
    try:
        proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                              text=True, errors="replace", timeout=3)
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def pytest_configure(config):
    if not hasattr(config, "workerinput"):
        config.pluginmanager.register(RunLog(config), "automatic-run-log")


class RunLog:
    def __init__(self, config):
        self.config = config
        self.tests = {}
        self.collected = set()
        self.collection_errors = {}
        self.internal_errors = []
        self.deselected = 0
        self.stream = None
        self.disabled = False
        self.started = _now()
        self.clock = time.perf_counter()
        root = Path(config.rootpath)
        directory = root / "reports" / "pytest"
        name = dt.datetime.now().strftime("pytest_%Y%m%d_%H%M%S_%f") + f"_{os.getpid()}_{uuid.uuid4().hex[:8]}"
        self.path = directory / name
        status = _git(root, "status", "--porcelain", "--untracked-files=no")
        self.metadata = dict(start=self.started, root=str(root),
                             command=list(config.invocation_params.args),
                             executable=sys.executable, ini_addopts=config.getini("addopts"),
                             environment_addopts=os.environ.get("PYTEST_ADDOPTS", ""),
                             workers=config.getoption("numprocesses", default=0),
                             python=sys.version, pytest=pytest.__version__,
                             commit=_git(root, "rev-parse", "HEAD"),
                             tracked_dirty=None if status is None else bool(status))
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.stream = self.path.with_suffix(".jsonl").open("x", encoding="utf-8")
            self.path.with_suffix(".txt").write_text(
                f"Started {self.started}\nStatus: running/incomplete\n"
                "Incremental results are in the matching .jsonl file.\n", encoding="utf-8")
            self.event("session_start", **self.metadata)
        except OSError as exc:
            self.disable(exc)

    def disable(self, exc):
        if not self.disabled:
            print(f"pytest run logging disabled: {exc}", file=sys.stderr)
        self.disabled = True
        if self.stream:
            try:
                self.stream.close()
            except OSError:
                pass
            self.stream = None

    def event(self, event, **data):
        if self.stream and not self.disabled:
            try:
                self.stream.write(json.dumps(dict(event=event, recorded_at=_now(), **data), ensure_ascii=False) + "\n")
                self.stream.flush()
            except OSError as exc:
                self.disable(exc)

    def pytest_collection_finish(self, session):
        self.collected.update(item.nodeid for item in session.items)
        self.event("collection", count=session.testscollected)

    @pytest.hookimpl(optionalhook=True)
    def pytest_xdist_node_collection_finished(self, node, ids):
        self.collected.update(ids)
        self.event("collection", worker=node.gateway.id, count=len(ids))

    def pytest_deselected(self, items):
        self.deselected += len(items)

    def pytest_collectreport(self, report):
        if report.failed:
            detail = str(report.longrepr)
            self.collection_errors[report.nodeid] = detail
            self.event("collection_error", nodeid=report.nodeid, traceback=detail)

    def pytest_runtest_logstart(self, nodeid, location):
        self.tests.setdefault(nodeid, dict(start=_now(), attempts={}))
        self.event("test_start", nodeid=nodeid)

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_logreport(self, report):
        state = self.tests.setdefault(report.nodeid, dict(start=_now(), attempts={}))
        attempt = int(getattr(report, "rerun", 0)) + 1
        start, stop = getattr(report, "start", None), getattr(report, "stop", None)
        data = dict(nodeid=report.nodeid, attempt=attempt, phase=report.when,
                    outcome=report.outcome, duration=report.duration,
                    start=_stamp(start) if start is not None else None,
                    end=_stamp(stop) if stop is not None else None,
                    worker=getattr(report, "worker_id", None),
                    wasxfail=str(report.wasxfail) if hasattr(report, "wasxfail") else None,
                    traceback=str(report.longrepr) if report.longrepr else None,
                    output=[dict(name=name, text=text) for name, text in report.sections])
        state["attempts"].setdefault(attempt, []).append(data)
        self.event("test_report", **data)

    def pytest_internalerror(self, excrepr, excinfo):
        self.internal_errors.append(str(excrepr))
        self.event("internal_error", traceback=str(excrepr))

    def pytest_keyboard_interrupt(self, excinfo):
        self.event("interrupted", detail=str(excinfo))

    def results(self):
        results = []
        for nodeid, state in self.tests.items():
            attempts = state["attempts"]
            reports = [r for rs in attempts.values() for r in rs]
            last = attempts[max(attempts)] if attempts else []
            if any(r["outcome"] == "failed" for r in last):
                outcome = "failed"
            elif not any(r["phase"] == "teardown" for r in last) or any(r["outcome"] == "rerun" for r in last):
                outcome = "incomplete"
            elif any(r["outcome"] == "skipped" for r in last):
                outcome = "xfailed" if any(r["wasxfail"] for r in last) else "skipped"
            else:
                outcome = "xpassed" if any(r["wasxfail"] for r in last) else "passed"
            starts = [r["start"] for r in reports if r["start"]]
            ends = [r["end"] for r in reports if r["end"]]
            results.append(dict(nodeid=nodeid, outcome=outcome, attempts=len(attempts),
                                start=min(starts) if starts else state["start"],
                                end=max(ends) if ends else None,
                                duration=sum(r["duration"] for r in reports),
                                reruns=sum(any(r["outcome"] == "rerun" for r in rs) for rs in attempts.values())))
        return results

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        results = self.results()
        counts = {key: sum(r["outcome"] == key for r in results)
                  for key in ("passed", "failed", "skipped", "xfailed", "xpassed", "incomplete")}
        counts.update(collected=max(session.testscollected, len(self.collected)),
                      started=len(results), completed=len(results) - counts["incomplete"],
                      reruns=sum(r["reruns"] for r in results),
                      collection_errors=len(self.collection_errors),
                      deselected=None if self.metadata["workers"] else self.deselected)
        incomplete = (int(exitstatus) not in (0, 1, 5) or bool(counts["incomplete"])
                      or counts["completed"] < counts["collected"])
        summary = dict(end=_now(), elapsed=time.perf_counter() - self.clock,
                       exitstatus=int(exitstatus), status="incomplete" if incomplete else "finished",
                       counts=counts, tests=results)
        self.event("session_finish", **summary)
        lines = [f"Started {self.started}", f"Ended {summary['end']}",
                 f"Elapsed: {summary['elapsed']:.3f} seconds", f"Status: {summary['status']}",
                 f"Exit code: {exitstatus}", "Metadata: " + json.dumps(self.metadata, ensure_ascii=False),
                 "Counts: " + json.dumps(counts), "", "Tests (duration includes setup, call, teardown, and attempts):"]
        for r in results:
            lines.append(f"{r['outcome'].upper()} {r['nodeid']} | {r['start']} -> {r['end']} | "
                         f"{r['duration']:.6f}s | {r['attempts']} attempt(s)")
        for state in self.tests.values():
            for reports in state["attempts"].values():
                for r in reports:
                    if r["outcome"] in ("failed", "rerun"):
                        lines += ["", f"{r['outcome'].upper()} {r['nodeid']} attempt {r['attempt']} ({r['phase']})",
                                  r["traceback"] or "(No traceback supplied)"]
                        for section in r["output"]:
                            lines += [section["name"], section["text"]]
        for nodeid, detail in self.collection_errors.items():
            lines += ["", "COLLECTION ERROR " + nodeid, detail]
        lines += self.internal_errors
        if not self.disabled:
            try:
                self.path.with_suffix(".txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
            except OSError as exc:
                self.disable(exc)

    def pytest_unconfigure(self, config):
        if self.stream:
            try:
                self.stream.close()
            except OSError as exc:
                self.disable(exc)
