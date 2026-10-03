from __future__ import annotations

from pathlib import Path
import shutil
import sys
import threading
import time
import pytest

tk = pytest.importorskip("tkinter")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from p2f_session import LocalBackend, LocalOptions, Result
from xp2f_ide import BackgroundJobs, Request, Xp2fIde, line_count, python_indent, python_tokens, split_run_output, syntax_status


@pytest.mark.parametrize("source,status", [
    ("def f(x):", "incomplete"),
    ("def f(x):\n    return x * x", "complete"),
    ("x = [1,\n", "incomplete"),
    ('x = """hello', "incomplete"),
    ("x = )", "invalid"),
    ("import numpy as np\nx = np.zeros(3)\n", "complete"),
])
def test_whole_buffer_completion(source, status):
    assert syntax_status(source)[0] == status


def test_python_coloring_and_indent_handle_comments_and_strings():
    source = "text = 'if # not a comment'\nif True: # actual comment\n    print(3.0)\n"
    tagged = list(python_tokens(source))
    assert ("string", (1, 7), (1, 27)) in tagged
    assert sum(tag == "comment" for tag, _, _ in tagged) == 1
    assert python_indent("if True: # comment", "if True: # comment") == "    "
    assert python_indent("text = 'hello:'", "text = 'hello:'") == ""
    assert python_indent('s = """hello\ninside:', "inside:") == ""
    assert line_count("") == 0 and line_count("a\nb\n") == 2


def test_output_split_preserves_python_file_messages_and_stage_timings():
    result = Result(True, stdout="Run (python): PASS\n1\nwrote data.csv\nwrote C:\\build\\session.f90\n"
                    "Build: PASS\nRun: PASS\n1\nRun diff: MATCH\n\nTiming summary (seconds):\n"
                    "  stage        seconds\n  python run   0.100000\n  transpile    0.200000\n"
                    "  compile      0.300000\n  fortran run  0.010000\n  total        0.510000\n",
                    command=["python", "xp2f.py", "input.py", "--out", "C:\\build\\session.f90"])
    panes = split_run_output(result, "time-both")
    assert panes.python == "1\nwrote data.csv"
    assert panes.fortran == "1"
    assert panes.timings["compile"] == 0.3 and panes.timings["fortran run"] == 0.01


def test_backend_gui_runs_script_without_repl_expression_printing(tmp_path):
    backend = LocalBackend(LocalOptions(work_dir=tmp_path))
    try:
        result = backend.run("1 + 2\nprint('script')\n", "run-python", expression_printing=False)
        assert result.ok and result.stdout == "script\n"
    finally:
        backend.close()


def test_backend_job_cancellation_and_cleanup(tmp_path):
    fake = tmp_path / "sleeping_transpiler.py"
    fake.write_text("import time\nprint('started', flush=True)\ntime.sleep(30)\n", encoding="utf-8")
    backend = LocalBackend(LocalOptions(work_dir=tmp_path, xp2f=fake, timeout=20))
    cancel = threading.Event()
    timer = threading.Timer(0.5, cancel.set)
    timer.start()
    try:
        result = backend.run("print(1)\n", "translate", expression_printing=False, cancel=cancel)
        assert not result.ok and result.cancelled
        assert result.seconds < 5
    finally:
        timer.cancel()
        source = backend.source_path
        replay_stem = source.with_name(source.stem + "_rng_replay")
        replay_stem.with_suffix(".bin").write_bytes(b"temporary")
        replay_stem.with_suffix(".meta").write_text("temporary", encoding="utf-8")
        backend.close()
    assert not source.exists() and not replay_stem.with_suffix(".bin").exists()


class FakeFactory:
    def __init__(self):
        self.calls = []
        self.gate = None
        self.closed = 0

    def __call__(self, options):
        factory = self

        class FakeBackend:
            def run(self, source, mode, *, expression_printing, cancel):
                factory.calls.append((source, mode, expression_printing, threading.get_ident()))
                if factory.gate is not None:
                    while not factory.gate.wait(0.01):
                        if cancel.is_set():
                            return Result(False, cancelled=True)
                return Result(True, stdout="wrote session.f90\n", seconds=0.1,
                              fortran="program example\nprint *, 1\nend program\n")

            def close(self):
                factory.closed += 1

        return FakeBackend()


def wait_for(root, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("GUI did not reach expected state")


@pytest.fixture
def gui(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    factory = FakeFactory()
    ide = Xp2fIde(root, live=False, work_dir=tmp_path, jobs=BackgroundJobs(factory))
    try:
        yield ide, factory
    finally:
        ide.jobs.cancel()
        if ide.jobs.active is not None:
            wait_for(root, lambda: ide.jobs.active is None)
        ide.finish_close()


def set_source(ide, source):
    ide.python_editor.set_value(source)
    ide.root.update()
    ide.refresh_source()


def test_gui_live_translation_never_runs_code_and_waits_for_syntax(gui):
    ide, factory = gui
    set_source(ide, "def square(x):")
    ide.live_translate()
    assert factory.calls == []
    assert "Waiting" in ide.status_var.get()
    set_source(ide, "print(1)\n")
    ide.live_translate()
    wait_for(ide.root, lambda: ide.jobs.active is None)
    assert factory.calls[0][1:3] == ("translate", False)
    assert factory.calls[0][3] != threading.get_ident()
    assert ide.fortran_count.get() == "3 lines" and ide.python_count.get() == "1 line"
    assert ide.fortran_editor.text.cget("state") == "disabled"
    assert ide.fortran_revision == ide.revision


def test_gui_background_work_keeps_events_responsive_and_discards_stale_result(gui):
    ide, factory = gui
    factory.gate = threading.Event()
    set_source(ide, "print(1)\n")
    ide.start("translate")
    wait_for(ide.root, lambda: bool(factory.calls))
    ticks = []
    ide.root.after(1, lambda: ticks.append(1))
    set_source(ide, "print(2)\n")
    wait_for(ide.root, lambda: bool(ticks))
    factory.gate.set()
    wait_for(ide.root, lambda: ide.jobs.active is None)
    assert ide.current_fortran == ""
    assert "Previous source" in ide.diagnostics.get("1.0", "end")
    assert ide.python_editor.value() == "print(2)\n"


def test_gui_stop_and_source_edit_mark_results_stale(gui):
    ide, factory = gui
    set_source(ide, "print(1)\n")
    ide.start("translate")
    wait_for(ide.root, lambda: ide.jobs.active is None)
    set_source(ide, "print(2)\n")
    assert ide.fortran_revision != ide.revision
    assert "Previous" in ide.fortran_state.get()
    factory.gate = threading.Event()
    ide.start("translate")
    ide.stop()
    wait_for(ide.root, lambda: ide.jobs.active is None)
    assert ide.status_var.get() == "Cancelled"
    assert factory.closed == 2


def test_gui_editor_indentation_saving_and_unsaved_protection(gui, tmp_path, monkeypatch):
    ide, _ = gui
    set_source(ide, "def square(x):")
    ide.python_editor.text.mark_set("insert", "end-1c")
    assert ide.python_editor.newline() == "break"
    assert ide.python_editor.value() == "def square(x):\n    "
    path = tmp_path / "saved.py"
    monkeypatch.setattr("xp2f_ide.filedialog.asksaveasfilename", lambda **kwargs: str(path))
    assert ide.save_source()
    assert path.read_text(encoding="utf-8") == ide.python_editor.value()
    assert not ide.dirty
    set_source(ide, "print(2)\n")
    monkeypatch.setattr("xp2f_ide.messagebox.askyesnocancel", lambda *args, **kwargs: None)
    ide.new_source()
    assert ide.python_editor.value() == "print(2)\n"
    assert ide.dirty


def test_gui_load_file_sets_working_directory_and_preserves_script(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    path = tmp_path / "input.py"
    path.write_text("print('loaded')\n", encoding="utf-8")
    ide = Xp2fIde(root, source=path, live=False, jobs=BackgroundJobs(FakeFactory()))
    try:
        root.update()
        assert ide.work_dir_var.get() == str(tmp_path)
        assert ide.python_editor.value() == "print('loaded')\n" and not ide.dirty
        assert ide.jobs.active is None
        assert ide.options().source_name == "input.py"
    finally:
        ide.finish_close()


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran required")
def test_gui_real_run_both_and_comparison(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(str(error))
    root.withdraw()
    ide = Xp2fIde(root, live=False, work_dir=tmp_path)
    try:
        set_source(ide, "def square(x):\n    return x * x\nprint(square(3))\n")
        ide.start("diff")
        wait_for(root, lambda: ide.jobs.active is None, timeout=90)
        assert "MATCH" in ide.status_var.get(), ide.diagnostics.get("1.0", "end")
        assert ide.python_output.get("1.0", "end").strip() == "9"
        assert ide.fortran_output.get("1.0", "end").strip() == "9"
        assert "function square" in ide.current_fortran
        assert "program main\n" in ide.current_fortran
        assert "from main.py on" in ide.current_fortran
    finally:
        if ide.jobs.active is not None:
            ide.stop()
            wait_for(root, lambda: ide.jobs.active is None, timeout=10)
        ide.finish_close()
