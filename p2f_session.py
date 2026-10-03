"""Session and local execution support shared by p2f user interfaces.

The terminal interface lives in xp2f_repl.py. Importing this module neither
imports the transpiler nor starts a Python interpreter.
"""
from __future__ import annotations

import ast
import codeop
import contextlib
from dataclasses import dataclass, field
import io
import json
import linecache
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from typing import Protocol


@dataclass
class Result:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    seconds: float = 0.0
    fortran: str = ""
    command: list[str] = field(default_factory=list)
    workspace_lost: bool = False
    matches: bool | None = None


def input_status(source: str) -> str:
    """Return complete, incomplete, or invalid for an interactive input block."""
    try:
        code = codeop.compile_command(source, filename="<p2f>", symbol="single")
    except (SyntaxError, OverflowError, ValueError):
        return "invalid"
    return "incomplete" if code is None else "complete"


_OUTPUT_CALLS = {"print", "exec", "exit", "quit"}
_MUTATING_METHODS = {
    "append", "extend", "insert", "remove", "sort", "reverse", "clear",
    "update", "add", "discard", "write", "writelines", "flush", "close",
    "seed", "sleep", "save", "savez", "savetxt", "to_csv",
}


def replay_source(source: str, *, keep_last_value: bool = False) -> str:
    """Give top-level value expressions explicit print calls for file replay.

    Keep original formatting, comments, and line numbers. Existing print calls
    and common calls made for side effects are left intact. Expressions inside
    functions and control-flow blocks retain ordinary Python semantics.
    """
    tree = ast.parse(source)
    uses_last_value = keep_last_value or any(
        isinstance(node, ast.Name) and node.id == "_" and isinstance(node.ctx, ast.Load)
        for node in ast.walk(tree))
    lines = source.splitlines(keepends=True)
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line))

    def position(line: int, byte_column: int) -> int:
        # AST column offsets count UTF-8 bytes, not Unicode characters.
        prefix = lines[line - 1].encode("utf-8")[:byte_column].decode("utf-8")
        return starts[line - 1] + len(prefix)

    # A locally defined procedure without a value return is called for effects.
    no_result = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            pending = list(node.body)
            returns_value = False
            while pending:
                child = pending.pop()
                if isinstance(child, ast.Return) and child.value is not None:
                    if not (isinstance(child.value, ast.Constant) and child.value.value is None):
                        returns_value = True
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                    pending.extend(ast.iter_child_nodes(child))
            if not returns_value:
                no_result.add(node.name)

    replacements = []
    for index, node in enumerate(tree.body):
        if not isinstance(node, ast.Expr):
            continue
        value = node.value
        if isinstance(value, ast.Constant) and value.value is None:
            continue
        if (index == 0 and isinstance(value, ast.Constant) and isinstance(value.value, str)
                and any(isinstance(item, ast.ImportFrom) and item.module == "__future__"
                        for item in tree.body)):
            continue  # A future import must follow the optional module docstring.
        if isinstance(value, ast.Call):
            function = value.func
            if isinstance(function, ast.Name) and function.id in _OUTPUT_CALLS | no_result:
                continue
            if isinstance(function, ast.Attribute) and function.attr in _MUTATING_METHODS:
                continue
        start = position(node.lineno, node.col_offset)
        end = position(node.end_lineno, node.end_col_offset)
        expression = source[start:end]
        printed = ("_ = " + expression + "; print(_)" if uses_last_value else
                   "print(" + expression + ")")
        replacements.append((start, end, printed))
    for start, end, text in reversed(replacements):
        source = source[:start] + text + source[end:]
    return source.rstrip() + "\n" if source.strip() else ""


def _popen_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    if process.poll() is None:
        process.kill()
    process.wait()


class Workspace(Protocol):
    def evaluate(self, source: str, *, display: bool = True) -> Result: ...
    def reset(self) -> None: ...
    def close(self) -> None: ...


class Backend(Protocol):
    def run(self, source: str, mode: str) -> Result: ...
    def close(self) -> None: ...


class PythonWorkspace:
    """A persistent Python subprocess, discarded after a timeout or interrupt."""

    def __init__(self, work_dir: Path, timeout: float = 60.0, python: str = sys.executable):
        self.work_dir = Path(work_dir).resolve()
        self.timeout = timeout
        self.python = python
        self.process = None
        self.responses = queue.Queue()

    def _start(self) -> None:
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [self.python, "-u", str(Path(__file__).resolve()), "--worker"],
            cwd=self.work_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
            **_popen_options(),
        )
        process, responses = self.process, self.responses

        def read_responses():
            try:
                for line in process.stdout:
                    responses.put(line)
            finally:
                responses.put(None)

        threading.Thread(target=read_responses, daemon=True).start()

    def evaluate(self, source: str, *, display: bool = True) -> Result:
        started = time.perf_counter()
        try:
            if self.process is None:
                self._start()
            self.process.stdin.write(json.dumps({"source": source, "display": display}) + "\n")
            self.process.stdin.flush()
            response = self.responses.get(timeout=self.timeout)
            if response is None:
                raise EOFError("Python interpreter exited; its workspace was lost.")
            data = json.loads(response)
            return Result(**data, seconds=time.perf_counter() - started)
        except queue.Empty:
            self.close()
            return Result(False, stderr=f"Python timed out after {self.timeout:g} s; its workspace was lost.\n",
                          seconds=time.perf_counter() - started, workspace_lost=True)
        except KeyboardInterrupt:
            self.close()
            return Result(False, stderr="Python interrupted; its workspace was lost.\n",
                          seconds=time.perf_counter() - started, workspace_lost=True)
        except (OSError, EOFError, ValueError) as error:
            self.close()
            return Result(False, stderr=str(error) + "\n", workspace_lost=True,
                          seconds=time.perf_counter() - started)

    def close(self) -> None:
        if self.process is not None:
            _stop_process(self.process)
            for stream in (self.process.stdin, self.process.stdout):
                if stream is not None:
                    stream.close()
            self.process = None

    def reset(self) -> None:
        self.close()


def _workspace_worker() -> None:
    # Save the protocol streams; user code gets separate stdin/stdout/stderr.
    protocol_in, protocol_out = sys.stdin, sys.stdout
    namespace = {"__name__": "__main__", "__builtins__": __builtins__}
    sys.path.insert(0, str(Path.cwd()))
    compiler = codeop.CommandCompiler()
    number = 0
    for request in protocol_in:
        data = json.loads(request)
        source = data["source"]
        number += 1
        filename = f"<p2f-input-{number}>"
        linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as out, \
                tempfile.TemporaryFile(mode="w+", encoding="utf-8") as err:
            old_out, old_err = os.dup(1), os.dup(2)
            old_stdin = sys.stdin
            old_hook = sys.displayhook
            try:
                os.dup2(out.fileno(), 1)
                os.dup2(err.fileno(), 2)
                sys.stdin = io.StringIO("")

                def displayhook(value):
                    if value is not None:
                        namespace["_"] = value
                        print(repr(value))

                sys.displayhook = displayhook
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    try:
                        # 'single' emits Python's normal interactive displayhook.
                        code = compiler(source, filename, "single" if data["display"] else "exec")
                        if code is None:
                            raise SyntaxError("incomplete input")
                        exec(code, namespace)
                        ok = True
                    except BaseException:
                        traceback.print_exc()
                        ok = False
            finally:
                out.flush()
                err.flush()
                os.dup2(old_out, 1)
                os.dup2(old_err, 2)
                os.close(old_out)
                os.close(old_err)
                sys.stdin = old_stdin
                sys.displayhook = old_hook
            out.seek(0)
            err.seek(0)
            protocol_out.write(json.dumps({"ok": ok, "stdout": out.read(), "stderr": err.read()}) + "\n")
            protocol_out.flush()


@dataclass
class LocalOptions:
    xp2f: Path = field(default_factory=lambda: Path(__file__).with_name("xp2f.py"))
    work_dir: Path = field(default_factory=Path.cwd)
    python: str = sys.executable
    timeout: float = 60.0
    compiler: str = ""
    int_kind: str | None = None
    pretty: bool = False
    rng_replay: bool = False
    numeric_diff: bool = False
    numeric_diff_tol: float = 1.0e-12
    round_digits: int | None = None


class LocalBackend:
    """Fresh replay through the existing xp2f CLI, with isolated session files."""

    MODES = {"translate", "run", "run-python", "run-both", "diff", "time", "time-python", "time-both"}

    def __init__(self, options: LocalOptions):
        self.options = options
        # Source is a sibling of local modules so xp2f can resolve their imports.
        handle, name = tempfile.mkstemp(prefix="p2f_repl_", suffix=".py", dir=options.work_dir)
        os.close(handle)
        self.source_path = Path(name)
        self._tmp = tempfile.TemporaryDirectory(prefix="p2f_repl_build_")
        self.fortran_path = Path(self._tmp.name) / "session.f90"

    def close(self) -> None:
        self.source_path.unlink(missing_ok=True)
        self._tmp.cleanup()

    def command(self, mode: str) -> list[str]:
        if mode not in self.MODES:
            raise ValueError(f"unknown execution mode: {mode}")
        opts = self.options
        if mode in {"run-python", "time-python"}:
            return [opts.python, str(self.source_path)]
        command = [opts.python, str(Path(opts.xp2f).resolve()), str(self.source_path),
                   "--out", str(self.fortran_path)]
        flag = {"run": "--run", "run-both": "--run-both", "diff": "--run-diff",
                "time": "--time", "time-both": "--time-both"}.get(mode)
        if flag:
            command.append(flag)
        if opts.compiler:
            command.extend(["--compiler", opts.compiler])
        if opts.int_kind:
            command.extend(["--int-kind", opts.int_kind])
        if opts.pretty:
            command.append("--pretty")
        if opts.round_digits is not None:
            command.extend(["--round-both", str(opts.round_digits)])
        if opts.rng_replay and mode in {"run-both", "diff", "time-both"}:
            command.append("--rng-replay")
        if opts.numeric_diff and mode == "diff":
            command.extend(["--numeric-diff", "--numeric-diff-tol", str(opts.numeric_diff_tol)])
        return command

    def run(self, source: str, mode: str) -> Result:
        if not source.strip():
            return Result(False, stderr="The session is empty.\n")
        try:
            normalized = replay_source(source)
        except (SyntaxError, ValueError) as error:
            return Result(False, stderr=f"Cannot replay source: {error}\n")
        self.source_path.write_text(normalized, encoding="utf-8")
        self.fortran_path.unlink(missing_ok=True)
        command = self.command(mode)
        if mode == "translate":
            statements = ast.parse(normalized).body
            declarations = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            if statements and all(isinstance(node, declarations) for node in statements):
                command.append("--module")
        started = time.perf_counter()
        process = None
        try:
            process = subprocess.Popen(command, cwd=self.options.work_dir,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace",
                                       env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **_popen_options())
            stdout, stderr = process.communicate(timeout=self.options.timeout)
            ok = process.returncode == 0
        except subprocess.TimeoutExpired:
            _stop_process(process)
            stdout, stderr = process.communicate()
            stderr += f"\nReplay timed out after {self.options.timeout:g} s.\n"
            ok = False
        except KeyboardInterrupt:
            if process is not None:
                _stop_process(process)
                stdout, stderr = process.communicate()
            else:
                stdout, stderr = "", ""
            stderr += "\nReplay interrupted.\n"
            ok = False
        except OSError as error:
            stdout, stderr, ok = "", str(error) + "\n", False
        matches = None
        if mode == "diff" and ok:
            # xp2f currently returns zero even when its output comparison differs.
            markers = [line for line in stdout.splitlines() if line.startswith("Run diff: ")]
            matches = bool(markers) and markers[-1].startswith("Run diff: MATCH")
            ok = matches
        fortran = self.fortran_path.read_text(encoding="utf-8") if self.fortran_path.exists() else ""
        return Result(ok, stdout, stderr, time.perf_counter() - started, fortran, command, matches=matches)


class Session:
    """Source history and workspace state, independent of the user interface."""

    def __init__(self, workspace: Workspace, backend: Backend):
        self.workspace = workspace
        self.backend = backend
        self.blocks: list[str] = []
        self.workspace_synced = True
        self.last_fortran = ""
        self.fortran_source: str | None = None

    @property
    def source(self) -> str:
        return "\n".join(block.rstrip("\n") for block in self.blocks) + ("\n" if self.blocks else "")

    @property
    def fortran_current(self) -> bool:
        return bool(self.last_fortran) and self.fortran_source == self.source

    def submit(self, source: str) -> Result:
        if not self.workspace_synced:
            return Result(False, stderr="Python workspace needs :replay or :clear before entering more code.\n")
        try:
            ast.parse(source)
        except (SyntaxError, ValueError) as error:
            return Result(False, stderr=f"{error}\n")
        self.blocks.append(source)
        result = self.workspace.evaluate(source)
        if not result.ok:
            self.workspace_synced = False
            result.stderr += "Source was retained. Use :undo, :clear, or correct the source and :replay.\n"
        return result

    def load(self, source: str) -> None:
        self.workspace.reset()
        self.blocks = [source] if source.strip() else []
        self.workspace_synced = not self.blocks

    def undo(self) -> bool:
        if not self.blocks:
            return False
        self.blocks.pop()
        self.workspace.reset()
        self.workspace_synced = not self.blocks
        return True

    def clear(self) -> None:
        self.load("")
        self.last_fortran = ""
        self.fortran_source = None

    def replay_workspace(self) -> Result:
        try:
            source = replay_source(self.source, keep_last_value=True)
        except (SyntaxError, ValueError) as error:
            return Result(False, stderr=f"Cannot replay source: {error}\n")
        self.workspace.reset()
        self.workspace_synced = False
        result = self.workspace.evaluate(source, display=False)
        self.workspace_synced = result.ok
        return result

    def run(self, mode: str) -> Result:
        result = self.backend.run(self.source, mode)
        if result.fortran:
            self.last_fortran = result.fortran
            self.fortran_source = self.source
        return result

    def close(self) -> None:
        self.workspace.close()
        self.backend.close()


if __name__ == "__main__" and sys.argv[1:] == ["--worker"]:
    _workspace_worker()
