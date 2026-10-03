from __future__ import annotations

import ast
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from p2f_session import LocalBackend, LocalOptions, PythonWorkspace, Result, Session, input_status, replay_source
from xp2f_repl import command_words, handle_command


@pytest.mark.parametrize("source, status", [
    ("x = 1", "complete"),
    ("def f(x):", "incomplete"),
    ("def f(x):\n    return x + 1", "incomplete"),
    ("def f(x):\n    return x + 1\n", "complete"),
    ("x = (1 +", "incomplete"),
    ('x = """hello', "incomplete"),
    ("x = [1,\n2]", "complete"),
    ("if True:\n    print(1)\n", "complete"),
    ("@decorator\ndef f():", "incomplete"),
    ("x = )", "invalid"),
])
def test_input_completion(source, status):
    assert input_status(source) == status


def test_replay_expression_printing_preserves_lines_comments_and_unicode():
    source = "é = 2; é + 1  # result\ndef f(x):\n    return x * x\nf(3)\nprint(4)\n"
    normalized = replay_source(source)
    assert normalized == "é = 2; print(é + 1)  # result\ndef f(x):\n    return x * x\nprint(f(3))\nprint(4)\n"
    assert len(normalized.splitlines()) == len(source.splitlines())
    ast.parse(normalized)


def test_replay_handles_strings_future_imports_and_side_effect_calls():
    assert replay_source("'hello'\n") == "print('hello')\n"
    source = '"doc"\nfrom __future__ import annotations\nx = []\nx.append(1)\n'
    assert replay_source(source) == source
    source = "def show():\n    def nested():\n        return 3\n    print(1)\nshow()\n"
    assert replay_source(source) == source


def test_replay_preserves_last_expression_value(workspace):
    source = "2 + 3\n_ * 2\n"
    normalized = replay_source(source)
    assert "_ = 2 + 3" in normalized
    result = workspace.evaluate(normalized, display=False)
    assert result.ok and result.stdout == "5\n10\n"


@pytest.fixture
def workspace(tmp_path):
    worker = PythonWorkspace(tmp_path, timeout=10)
    try:
        yield worker
    finally:
        worker.close()


def test_python_workspace_persists_definitions_and_expression_results(workspace):
    assert workspace.evaluate("x = 4").ok
    assert workspace.evaluate("x + 2").stdout == "6\n"
    assert workspace.evaluate("_ * 2").stdout == "12\n"
    assert workspace.evaluate("def twice(x):\n    return 2*x\n").ok
    assert workspace.evaluate("twice(x)").stdout == "8\n"
    assert workspace.evaluate("print('done')").stdout == "done\n"
    assert workspace.evaluate("None").stdout == ""


def test_workspace_captures_traceback_low_level_output_and_survives_error(workspace):
    result = workspace.evaluate("import os; os.write(1, b'raw\\n'); print('text')")
    assert result.ok
    assert "raw\n" in result.stdout and "text\n" in result.stdout
    result = workspace.evaluate("x = 9; 1 / 0")
    assert not result.ok
    assert "ZeroDivisionError" in result.stderr and "x = 9; 1 / 0" in result.stderr
    assert workspace.evaluate("x").stdout == "9\n"


def test_workspace_reports_system_exit_without_traceback(workspace):
    result = workspace.evaluate("raise SystemExit(2)")
    assert not result.ok and result.exit_code == 2
    assert result.stderr == "" and workspace.process is None


def test_workspace_future_flags_and_reset(workspace):
    assert workspace.evaluate("from __future__ import annotations").ok
    assert workspace.evaluate("def f(x: Unknown):\n    return x\n").ok
    assert workspace.evaluate("f.__annotations__").stdout == "{'x': 'Unknown'}\n"
    workspace.reset()
    assert not workspace.evaluate("f(1)").ok


def test_workspace_timeout_discards_state_and_can_restart(tmp_path):
    worker = PythonWorkspace(tmp_path, timeout=5)
    try:
        assert worker.evaluate("x = 1").ok
        worker.timeout = 0.15
        result = worker.evaluate("while True:\n    pass\n")
        assert not result.ok and result.workspace_lost
        assert "timed out" in result.stderr
        assert worker.process is None
        worker.timeout = 5
        assert not worker.evaluate("x").ok
        assert worker.evaluate("2 + 2").stdout == "4\n"
    finally:
        worker.close()


def test_workspace_detects_abrupt_exit(workspace):
    result = workspace.evaluate("import os; os._exit(3)")
    assert not result.ok and result.workspace_lost
    assert workspace.evaluate("3").stdout == "3\n"


class FakeBackend:
    def __init__(self):
        self.calls = []

    def run(self, source, mode):
        self.calls.append((source, mode))
        return Result(True, fortran="program session\nend program\n")

    def close(self):
        pass


def test_session_failed_source_undo_replay_and_stale_fortran(workspace):
    backend = FakeBackend()
    session = Session(workspace, backend)
    assert session.submit("x = 2").ok
    session.run("translate")
    assert session.fortran_current
    assert session.submit("x + 3").stdout == "5\n"
    assert not session.fortran_current
    result = session.submit("x = 6; 1 / 0")
    assert not result.ok
    assert "1 / 0" in session.source and not session.workspace_synced
    assert not session.submit("x").ok
    assert session.undo()
    assert "1 / 0" not in session.source
    assert session.replay_workspace().ok
    assert workspace.evaluate("_").stdout == "5\n"
    assert session.submit("x").stdout == "2\n"
    session.clear()
    assert session.source == "" and session.last_fortran == ""
    assert session.workspace_synced


def test_load_does_not_execute_and_fresh_runs_do_not_change_live_state(workspace, tmp_path):
    session = Session(workspace, FakeBackend())
    session.load("from pathlib import Path\nPath('marker').write_text('ran')\nx = 7\n")
    assert not (tmp_path / "marker").exists()
    assert not session.workspace_synced
    assert not session.submit("x").ok
    session.load("x = 7\n")
    assert session.replay_workspace().ok
    session.run("run-both")
    assert session.submit("x").stdout == "7\n"


def test_commands_accept_windows_paths_and_stale_save_is_rejected(workspace, tmp_path, capsys):
    assert command_words(r'load "C:\my project\input.py"') == ["load", r"C:\my project\input.py"]
    assert command_words(r"load C:\python\input.py") == ["load", r"C:\python\input.py"]
    session = Session(workspace, FakeBackend())
    assert handle_command(":save-fortran " + str(tmp_path / "session.f90"), session)
    assert not (tmp_path / "session.f90").exists()
    assert "translate first" in capsys.readouterr().err
    assert not handle_command(":quit", session)


def test_backend_routes_options_and_treats_cli_diff_as_failure(tmp_path):
    fake = tmp_path / "fake_xp2f.py"
    fake.write_text("import sys\nprint('Run diff: DIFF')\n", encoding="utf-8")
    options = LocalOptions(xp2f=fake, work_dir=tmp_path, compiler="gfortran -O0",
                           int_kind="int64", rng_replay=True, numeric_diff=True)
    backend = LocalBackend(options)
    source_path = backend.source_path
    try:
        command = backend.command("diff")
        assert "--run-diff" in command and "--rng-replay" in command and "--numeric-diff" in command
        assert command[command.index("--compiler") + 1] == "gfortran -O0"
        assert "--rng-replay" not in backend.command("run")
        result = backend.run("print(1)\n", "diff")
        assert not result.ok and result.matches is False
    finally:
        backend.close()
    assert not source_path.exists()


def test_fresh_python_uses_working_directory_and_imports(tmp_path):
    (tmp_path / "helper.py").write_text("value = 8\n", encoding="utf-8")
    (tmp_path / "data.txt").write_text("sample\n", encoding="utf-8")
    backend = LocalBackend(LocalOptions(work_dir=tmp_path))
    try:
        result = backend.run("from helper import value\nprint(value)\nprint(open('data.txt').read().strip())\n", "run-python")
        assert result.ok and result.stdout == "8\nsample\n"
    finally:
        backend.close()


def test_terminal_multiline_and_expression_input(tmp_path):
    source = "def twice(x):\n    return 2*x\n\ntwice(3)\n:list\n:quit\n"
    result = subprocess.run([sys.executable, str(ROOT / "xp2f_repl.py"), "--work-dir", str(tmp_path)],
                            input=source, text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "6\n" in result.stdout and "return 2*x" in result.stdout
    assert "SyntaxError" not in result.stderr
    assert not list(tmp_path.glob("p2f_repl_*.py"))


@pytest.mark.parametrize("expression, code, message", [
    ("quit()", 0, ""),
    ("exit()", 0, ""),
    ("raise SystemExit", 0, ""),
    ("import sys; sys.exit(3)", 3, ""),
    ("quit('goodbye')", 1, "goodbye"),
])
def test_terminal_python_exit_commands(tmp_path, expression, code, message):
    result = subprocess.run([sys.executable, str(ROOT / "xp2f_repl.py"), "--work-dir", str(tmp_path)],
                            input=f"quit\n{expression}\nprint('SHOULD NOT RUN')\n",
                            text=True, capture_output=True, timeout=15)
    assert result.returncode == code, result.stdout + result.stderr
    assert "SHOULD NOT RUN" not in result.stdout
    assert "Traceback" not in result.stderr and "Source was retained" not in result.stderr
    assert result.stderr.strip() == message
    assert not list(tmp_path.glob("p2f_repl_*.py"))


def test_shadowed_quit_is_executed_as_normal_python(workspace):
    assert workspace.evaluate("def quit():\n    return 7\n").ok
    result = workspace.evaluate("quit()")
    assert result.ok and result.exit_code is None and result.stdout == "7\n"


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran is required")
def test_real_transpiler_compiles_and_compares_repl_expressions(tmp_path):
    (tmp_path / "helper.py").write_text("def twice(x):\n    return 2*x\n", encoding="utf-8")
    backend = LocalBackend(LocalOptions(work_dir=tmp_path, timeout=90))
    try:
        result = backend.run("def square(x: float) -> float:\n    return x * x\n", "translate")
        assert result.ok, result.stdout + result.stderr
        assert "module" in result.fortran and "function square" in result.fortran
        assert "module main_proc_mod\n" in result.fortran
        source = "from helper import twice\nx = 3\ntwice(x)\nfor i in range(3):\n    print(i*i)\n"
        result = backend.run(source, "diff")
        assert result.ok and result.matches is True, result.stdout + result.stderr
        assert "Run diff: MATCH" in result.stdout
        assert "program" in result.fortran
        assert "program main\n" in result.fortran
        assert "from main.py on" in result.fortran
        assert backend.source_path.stem not in result.fortran
    finally:
        backend.close()


@pytest.mark.skipif(shutil.which("gfortran") is None, reason="gfortran is required")
def test_real_numpy_rng_replay_and_int64(tmp_path):
    pytest.importorskip("numpy")
    backend = LocalBackend(LocalOptions(work_dir=tmp_path, timeout=120,
                                       rng_replay=True, int_kind="int64"))
    try:
        result = backend.run("import numpy as np\n"
                             "a = np.random.uniform(size=3)\n"
                             "print(np.sum(a * a))\n", "diff")
        assert result.ok and result.matches is True, result.stdout + result.stderr
        assert "Run diff: MATCH" in result.stdout
        assert "int64" in result.fortran
    finally:
        backend.close()


def test_logical_source_names_keep_unique_files_and_cli_defaults(tmp_path):
    existing = tmp_path / "main.py"
    existing.write_text("# user's file\n", encoding="utf-8")
    first = LocalBackend(LocalOptions(work_dir=tmp_path))
    second = LocalBackend(LocalOptions(work_dir=tmp_path, source_name="my-model.py"))
    try:
        assert first.source_path != second.source_path and first.source_path != existing
        for backend, name, program in ((first, "main.py", "main"),
                                       (second, "my-model.py", "my_model")):
            result = backend.run("print(2)\n", "translate")
            assert result.ok, result.stdout + result.stderr
            assert f"from {name} on" in result.fortran
            assert f"program {program}\n" in result.fortran
            assert backend.source_path.stem not in result.fortran
            assert backend.fortran_path.name == Path(name).stem + ".f90"
        assert existing.read_text(encoding="utf-8") == "# user's file\n"
        source = tmp_path / "ordinary.py"
        source.write_text("print(2)\n", encoding="utf-8")
        proc = subprocess.run([sys.executable, str(ROOT / "xp2f.py"), str(source)],
                              cwd=tmp_path, capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stdout + proc.stderr
        generated = (tmp_path / "ordinary_p.f90").read_text(encoding="utf-8")
        assert "program ordinary\n" in generated and "from ordinary.py on" in generated
    finally:
        first.close()
        second.close()
