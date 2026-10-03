#!/usr/bin/env python3
"""Local p2f GUI: edit Python, inspect Fortran, and explicitly run either."""
from __future__ import annotations

import argparse
import builtins
import codeop
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import io
import keyword
import math
from pathlib import Path
import queue
import re
import shlex
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk
import tokenize
import traceback

from p2f_session import LocalBackend, LocalOptions, Result


DEFAULT_XP2F = Path(__file__).with_name("xp2f.py")
EXAMPLE = "def square(x: float) -> float:\n    return x * x\n\nprint(square(1.5))\nprint(square(3.0))\n"
FORTRAN_WORDS = set("allocatable allocate block call case character class complex contains continue cycle "
                    "deallocate dimension do double elemental else elseif end enddo endif entry error exit "
                    "external function generic if implicit import in inout integer intent interface intrinsic "
                    "kind len logical module none only optional out parameter pointer precision private procedure "
                    "program public pure rank real recursive result return save select stop subroutine target "
                    "then type use value where while".split())
FORTRAN_LEXER = re.compile(r"(?P<string>'(?:[^']|'')*'|\"(?:[^\"]|\"\")*\")|"
                           r"(?P<comment>![^\n]*)|(?P<number>\b\d+(?:\.\d*)?(?:[eEdD][+-]?\d+)?(?:_\w+)?)|"
                           r"(?P<word>\b[A-Za-z_]\w*\b)")
HELP = """p2f desktop editor

Translate generates Fortran. Live translation does the same after an editing
pause, once Python syntax is complete. It never executes your program.

Run Python, Run Fortran, Run Both, Compare, and Time Both execute the complete
current script from scratch. Use explicit print statements to display results.
Run Fortran always translates the current source before compilation.

Compare uses xp2f.py's existing output checks. RNG replay makes supported Python
random draws available to Fortran when running both languages. Numeric diff
also reports comparisons of numeric values independent of surrounding text.

The working directory controls data files and sibling Python imports. It follows
opened files unless --work-dir was specified. Each job has a temporary source
file and generated Fortran; usual CLI helper object caching still applies.

Generated Fortran is read-only. Save it for manual editing in another editor.
Edits or option changes mark previous translations and results stale. Old jobs
cannot replace results for newer input. Stop cancels the current process tree.

Ctrl+O opens, Ctrl+S saves Python, F5 translates, F6 runs both, and Ctrl+Return
compares. Tab indents four spaces; Shift+Tab unindents. Editors support undo.
Programs expecting interactive input are not supported by this initial GUI.
"""


def line_count(text: str) -> int:
    return len(text.splitlines()) if text else 0


def line_label(text: str) -> str:
    count = line_count(text)
    return f"{count} {'line' if count == 1 else 'lines'}"


def syntax_status(source: str) -> tuple[str, str]:
    """Check an entire editor buffer without importing or executing its code."""
    try:
        compiled = codeop.compile_command(source, filename="<Python editor>", symbol="exec")
    except (SyntaxError, OverflowError, ValueError) as error:
        return "invalid", str(error)
    return ("incomplete", "Waiting for complete Python syntax") if compiled is None else ("complete", "")


def python_tokens(source: str):
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            tag = None
            if token.type == tokenize.COMMENT:
                tag = "comment"
            elif token.type == tokenize.STRING:
                tag = "string"
            elif token.type == tokenize.NUMBER:
                tag = "number"
            elif token.type == tokenize.NAME:
                if keyword.iskeyword(token.string):
                    tag = "keyword"
                elif token.string in vars(builtins):
                    tag = "builtin"
            if tag:
                yield tag, token.start, token.end
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # The editor routinely contains unfinished input.


def python_indent(prefix: str, line: str) -> str:
    indent = re.match(r"[ \t]*", line)[0].expandtabs(4)
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(prefix).readline))
        meaningful = [token for token in tokens if token.type not in
                      {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT,
                       tokenize.DEDENT, tokenize.ENDMARKER}]
        if meaningful and meaningful[-1].type == tokenize.OP and meaningful[-1].string == ":":
            indent += "    "
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    return indent


@dataclass
class DisplayResult:
    python: str = ""
    fortran: str = ""
    timings: dict[str, float] | None = None


def split_run_output(result: Result, mode: str) -> DisplayResult:
    """Extract output panes from CLI status markers; retain raw logs separately."""
    if mode in {"run-python", "time-python"}:
        return DisplayResult(result.stdout + result.stderr, timings={"python run": result.seconds})
    python, fortran = [], []
    active = None
    timings = {}
    in_timings = False
    output_path = (result.command[result.command.index("--out") + 1] if "--out" in result.command else None)
    boundaries = ("Build:", "Build helper:", "Auto helper files:", "Run diff:",
                  "Numeric diff:", "Timing summary (seconds):")
    for line in result.stdout.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        if stripped.startswith("Run (python): PASS"):
            active = python
            continue
        if stripped.startswith("Run (python): FAIL"):
            active = python
            continue
        if stripped.startswith(("Run: PASS", "Run: FAIL")):
            active = fortran
            continue
        if stripped.startswith(boundaries) or (stripped == "wrote " + output_path if output_path else
                                               stripped.startswith("wrote ") and stripped.endswith(".f90")):
            active = None
        if stripped == "Timing summary (seconds):":
            in_timings = True
        elif in_timings:
            match = re.match(r"\s*(python run|fortran run|transpile|compile|total)\s+([\d.eE+-]+)", stripped)
            if match:
                timings[match[1]] = float(match[2])
        elif active is not None:
            active.append(line)
    return DisplayResult("".join(python).rstrip("\r\n"), "".join(fortran).rstrip("\r\n"), timings)


@dataclass
class Request:
    revision: int
    source: str
    mode: str
    options: LocalOptions
    automatic: bool = False


class BackgroundJobs:
    """One cancellable execution at a time; results are consumed by the UI thread."""

    def __init__(self, backend_factory=LocalBackend):
        self.backend_factory = backend_factory
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="p2f-ide")
        self.results = queue.Queue()
        self.active: Request | None = None
        self.cancel_event = None

    def submit(self, request: Request) -> bool:
        if self.active is not None:
            return False
        self.active = request
        cancel = self.cancel_event = threading.Event()

        def work():
            backend = None
            try:
                backend = self.backend_factory(request.options)
                result = backend.run(request.source, request.mode, expression_printing=False, cancel=cancel)
            except Exception:
                result = Result(False, stderr=traceback.format_exc())
            finally:
                if backend is not None:
                    try:
                        backend.close()
                    except Exception:
                        result = Result(False, stderr=traceback.format_exc())
            self.results.put((request, result))

        self.executor.submit(work)
        return True

    def cancel(self) -> None:
        if self.cancel_event is not None:
            self.cancel_event.set()

    def take(self):
        try:
            item = self.results.get_nowait()
        except queue.Empty:
            return None
        self.active = None
        self.cancel_event = None
        return item

    def close(self) -> None:
        self.cancel()
        self.executor.shutdown(wait=False)


class CodeEditor(ttk.Frame):
    def __init__(self, parent, *, language: str, readonly: bool = False):
        super().__init__(parent)
        self.language = language
        self.readonly = readonly
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.numbers = tk.Text(self, width=5, padx=4, borderwidth=0, state="disabled",
                               takefocus=False, background="#eeeeee", foreground="#666666",
                               font=("Consolas", 11), wrap="none")
        self.text = tk.Text(self, wrap="none", width=1, undo=not readonly, maxundo=200,
                            font=("Consolas", 11), padx=6)
        self.text.configure(tabs=(tkfont.Font(font=self.text.cget("font")).measure("    "),))
        self.vertical = ttk.Scrollbar(self, command=self.scroll)
        self.horizontal = ttk.Scrollbar(self, orient="horizontal", command=self.text.xview)
        self.text.configure(yscrollcommand=self.scrolled, xscrollcommand=self.horizontal.set)
        self.numbers.grid(row=0, column=0, sticky="ns")
        self.text.grid(row=0, column=1, sticky="nsew")
        self.vertical.grid(row=0, column=2, sticky="ns")
        self.horizontal.grid(row=1, column=1, sticky="ew")
        for tag, color in {"keyword": "#713599", "builtin": "#126582", "string": "#955000",
                           "number": "#28602a", "comment": "#707070"}.items():
            self.text.tag_configure(tag, foreground=color)
        if readonly:
            self.text.configure(state="disabled")
        else:
            self.text.bind("<Return>", self.newline)
            self.text.bind("<Tab>", lambda event: self.indent(False))
            self.text.bind("<Shift-Tab>", lambda event: self.indent(True))

    def value(self) -> str:
        return self.text.get("1.0", "end-1c")

    def set_value(self, value: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value)
        if self.readonly:
            self.text.configure(state="disabled")
        self.refresh()

    def scrolled(self, first, last) -> None:
        self.vertical.set(first, last)
        self.numbers.yview_moveto(first)

    def scroll(self, *args) -> None:
        self.text.yview(*args)
        self.numbers.yview_moveto(self.text.yview()[0])

    def refresh(self) -> None:
        source = self.value()
        # Keep one gutter line for an empty buffer and for the final blank line.
        self.numbers.configure(state="normal")
        self.numbers.delete("1.0", "end")
        self.numbers.insert("1.0", "\n".join(map(str, range(1, int(self.text.index("end-1c").split(".")[0]) + 1))))
        self.numbers.configure(state="disabled")
        self.numbers.yview_moveto(self.text.yview()[0])
        for tag in ("keyword", "builtin", "string", "number", "comment"):
            self.text.tag_remove(tag, "1.0", "end")
        if self.language == "python":
            for tag, start, end in python_tokens(source):
                self.text.tag_add(tag, f"{start[0]}.{start[1]}", f"{end[0]}.{end[1]}")
        else:
            for match in FORTRAN_LEXER.finditer(source):
                tag = match.lastgroup
                if tag == "word":
                    if match[0].lower() not in FORTRAN_WORDS:
                        continue
                    tag = "keyword"
                self.text.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def newline(self, event=None):
        line = self.text.get("insert linestart", "insert")
        prefix = self.text.get("1.0", "insert")
        indent = python_indent(prefix, line)
        if self.text.tag_ranges("sel"):
            self.text.delete("sel.first", "sel.last")
        self.text.insert("insert", "\n" + indent)
        self.text.see("insert")
        return "break"

    def indent(self, backwards: bool):
        selected = self.text.tag_ranges("sel")
        if not selected and not backwards:
            column = int(self.text.index("insert").split(".")[1])
            self.text.insert("insert", " " * (4 - column % 4))
            return "break"
        first = int(self.text.index("sel.first" if selected else "insert").split(".")[0])
        last_index = self.text.index("sel.last" if selected else "insert")
        last, column = map(int, last_index.split("."))
        if selected and last > first and column == 0:
            last -= 1
        self.text.edit_separator()
        for number in range(first, last + 1):
            position = f"{number}.0"
            if backwards:
                line = self.text.get(position, f"{number}.end")
                count = min(4, len(line) - len(line.lstrip(" ")))
                if line.startswith("\t"):
                    count = 1
                if count:
                    self.text.delete(position, f"{position}+{count}c")
            else:
                self.text.insert(position, "    ")
        self.text.edit_separator()
        return "break"


def output_widget(parent):
    frame = ttk.Frame(parent)
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    text = tk.Text(frame, wrap="none", width=1, font=("Consolas", 10), state="disabled", height=9)
    scroll = ttk.Scrollbar(frame, command=text.yview)
    horizontal = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
    text.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
    text.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    return frame, text


class Xp2fIde:
    def __init__(self, root: tk.Tk, *, xp2f: Path = DEFAULT_XP2F,
                 python: str = sys.executable, compiler: str = "", timeout: float = 120,
                 source: Path | None = None, work_dir: Path | None = None,
                 live: bool = True, jobs: BackgroundJobs | None = None):
        self.root = root
        self.xp2f = Path(xp2f).resolve()
        self.source_path = None
        self.saved_source = ""
        self.revision = 0
        self.fortran_revision = None
        self.output_revision = None
        self.current_fortran = ""
        self.pending_live = False
        self.live_timer = None
        self.refresh_timer = None
        self.closing = False
        self.fixed_work_dir = work_dir is not None
        self.jobs = jobs or BackgroundJobs()
        self.live_var = tk.BooleanVar(value=live)
        self.compiler_var = tk.StringVar(value=compiler)
        self.python_var = tk.StringVar(value=python)
        self.timeout_var = tk.StringVar(value=str(timeout))
        self.int_kind_var = tk.StringVar(value="default")
        self.pretty_var = tk.BooleanVar(value=False)
        self.rng_var = tk.BooleanVar(value=False)
        self.numeric_var = tk.BooleanVar(value=False)
        self.tolerance_var = tk.StringVar(value="1e-12")
        self.round_var = tk.StringVar(value="")
        self.work_dir_var = tk.StringVar(value=str(Path(work_dir or Path.cwd()).resolve()))
        self.status_var = tk.StringVar(value="Ready")
        self.timing_var = tk.StringVar(value="")
        self.python_count = tk.StringVar(value="0 lines")
        self.fortran_count = tk.StringVar(value="0 lines")
        self.fortran_state = tk.StringVar(value="No translation")
        self.output_state = tk.StringVar(value="No execution results")
        self.build_ui()
        self.python_editor.text.bind("<<Modified>>", self.modified)
        for variable in (self.compiler_var, self.python_var, self.timeout_var, self.int_kind_var,
                         self.pretty_var, self.rng_var, self.numeric_var, self.tolerance_var,
                         self.round_var, self.work_dir_var):
            variable.trace_add("write", self.options_changed)
        self.live_var.trace_add("write", self.live_changed)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_timer = self.root.after(50, self.poll)
        self.update_title()
        if source is not None:
            self.load_source(source)

    @property
    def dirty(self) -> bool:
        return self.python_editor.value() != self.saved_source

    def build_ui(self):
        self.root.geometry(f"{min(1420, self.root.winfo_screenwidth() - 80)}x{min(900, self.root.winfo_screenheight() - 100)}")
        self.root.minsize(960, 580)
        self.root.rowconfigure(3, weight=1)
        self.root.columnconfigure(0, weight=1)
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=False)
        for text, function in (("New", self.new_source), ("Open Python...", self.open_source),
                               ("Save Python", self.save_source), ("Save Python As...", lambda: self.save_source(True)),
                               ("Save Fortran...", self.save_fortran), ("Load example", self.load_example),
                               ("Exit", self.close)):
            file_menu.add_command(label=text, command=function)
        menu.add_cascade(label="File", menu=file_menu)
        menu.add_command(label="Help", command=lambda: messagebox.showinfo("p2f help", HELP, parent=self.root))
        self.root.configure(menu=menu)
        toolbar = ttk.Frame(self.root, padding=6)
        toolbar.grid(row=0, column=0, sticky="ew")
        self.run_buttons = []
        file_row = ttk.Frame(toolbar)
        file_row.pack(fill="x")
        run_row = ttk.Frame(toolbar)
        run_row.pack(fill="x", pady=(4, 0))
        for label, function in (("Open", self.open_source), ("Save Python", self.save_source),
                                ("Save Fortran", self.save_fortran), ("Translate", lambda: self.start("translate")),
                                ("Run Python", lambda: self.start("run-python")),
                                ("Run Fortran", lambda: self.start("run")),
                                ("Run Both", lambda: self.start("run-both")),
                                ("Compare", lambda: self.start("diff")),
                                ("Time Both", lambda: self.start("time-both"))):
            parent = file_row if label in {"Open", "Save Python", "Save Fortran", "Translate"} else run_row
            button = ttk.Button(parent, text=label, command=function)
            button.pack(side="left", padx=(0, 4))
            if label in {"Translate", "Run Python", "Run Fortran", "Run Both", "Compare", "Time Both"}:
                self.run_buttons.append(button)
        self.stop_button = ttk.Button(run_row, text="Stop", command=self.stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(file_row, text="Clear Output", command=self.clear_output).pack(side="right")

        options = ttk.Frame(self.root, padding=(6, 0, 6, 4))
        options.grid(row=1, column=0, sticky="ew")
        basic = ttk.Frame(options)
        basic.pack(fill="x")
        advanced = ttk.Frame(options)
        advanced.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(basic, text="Live translation", variable=self.live_var).pack(side="left", padx=(0, 8))
        ttk.Label(basic, text="Compiler").pack(side="left")
        ttk.Combobox(basic, textvariable=self.compiler_var, width=30,
                     values=("", "gfortran -O0 -g -fcheck=all -fbacktrace", "gfortran -O2", "gfortran -O3",
                             "ifx /O2")).pack(side="left", padx=(4, 8))
        ttk.Label(basic, text="Timeout (s)").pack(side="left")
        ttk.Entry(basic, textvariable=self.timeout_var, width=5).pack(side="left", padx=(4, 8))
        ttk.Label(basic, text="Integers").pack(side="left")
        ttk.Combobox(basic, textvariable=self.int_kind_var, state="readonly", width=7,
                     values=("default", "int32", "int64")).pack(side="left", padx=(4, 8))
        ttk.Checkbutton(advanced, text="Pretty", variable=self.pretty_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(advanced, text="RNG replay", variable=self.rng_var).pack(side="left", padx=(0, 8))
        ttk.Checkbutton(advanced, text="Numeric diff", variable=self.numeric_var).pack(side="left")
        ttk.Label(advanced, text="Tolerance").pack(side="left", padx=(8, 4))
        ttk.Entry(advanced, textvariable=self.tolerance_var, width=9).pack(side="left", padx=(0, 12))
        ttk.Label(advanced, text="Round output").pack(side="left")
        ttk.Entry(advanced, textvariable=self.round_var, width=4).pack(side="left", padx=4)

        locations = ttk.Frame(self.root, padding=(6, 0, 6, 6))
        locations.grid(row=2, column=0, sticky="ew")
        locations.columnconfigure(1, weight=1)
        ttk.Label(locations, text="Working directory").grid(row=0, column=0)
        ttk.Entry(locations, textvariable=self.work_dir_var).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(locations, text="Browse", command=self.choose_directory).grid(row=0, column=2, padx=(0, 12))
        ttk.Label(locations, text="Python executable").grid(row=1, column=0, pady=(4, 0))
        ttk.Entry(locations, textvariable=self.python_var).grid(row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=(4, 0))

        panes = ttk.PanedWindow(self.root, orient="vertical")
        panes.grid(row=3, column=0, sticky="nsew", padx=6)
        editors = ttk.PanedWindow(panes, orient="horizontal")
        editors.bind("<Configure>", self.balance_once)
        for language, title, counter, readonly in (("python", "Python input", self.python_count, False),
                                                    ("fortran", "Generated Fortran", self.fortran_count, True)):
            frame = ttk.Frame(editors)
            frame.rowconfigure(1, weight=1)
            frame.columnconfigure(0, weight=1)
            header = ttk.Frame(frame)
            header.grid(row=0, column=0, sticky="ew", pady=4)
            ttk.Label(header, text=title).pack(side="left")
            ttk.Label(header, textvariable=counter).pack(side="right", padx=8)
            editor = CodeEditor(frame, language=language, readonly=readonly)
            editor.grid(row=1, column=0, sticky="nsew")
            if language == "python":
                self.python_editor = editor
            else:
                self.fortran_editor = editor
                ttk.Label(frame, textvariable=self.fortran_state).grid(row=2, column=0, sticky="w")
            editors.add(frame, weight=1)
        panes.add(editors, weight=3)
        self.notebook = ttk.Notebook(panes)
        execution = ttk.Frame(self.notebook)
        execution.columnconfigure(0, weight=1)
        execution.rowconfigure(1, weight=1)
        ttk.Label(execution, textvariable=self.output_state).grid(row=0, column=0, sticky="w")
        output_panes = ttk.PanedWindow(execution, orient="horizontal")
        output_panes.bind("<Configure>", self.balance_once)
        output_panes.grid(row=1, column=0, sticky="nsew")
        for title, attribute in (("Python output", "python_output"), ("Fortran output", "fortran_output")):
            frame = ttk.LabelFrame(output_panes, text=title)
            container, text = output_widget(frame)
            container.pack(fill="both", expand=True)
            setattr(self, attribute, text)
            output_panes.add(frame, weight=1)
        self.notebook.add(execution, text="Execution outputs")
        container, self.diagnostics = output_widget(self.notebook)
        self.notebook.add(container, text="Diagnostics / full log")
        panes.add(self.notebook, weight=1)
        footer = ttk.Frame(self.root, padding=6)
        footer.grid(row=4, column=0, sticky="ew")
        ttk.Label(footer, textvariable=self.status_var).pack(side="left")
        ttk.Label(footer, textvariable=self.timing_var).pack(side="right")
        for sequence, function in (("<Control-o>", self.open_source), ("<Control-s>", self.save_source),
                                   ("<F5>", lambda: self.start("translate")),
                                   ("<F6>", lambda: self.start("run-both")),
                                   ("<Control-Return>", lambda: self.start("diff"))):
            callback = lambda event, action=function: self.invoke_shortcut(action)
            self.root.bind(sequence, callback)
            for editor in (self.python_editor, self.fortran_editor):
                editor.text.bind(sequence, callback)

    @staticmethod
    def invoke_shortcut(action):
        action()
        return "break"

    @staticmethod
    def balance_once(event):
        pane = event.widget
        if event.width > 100 and not getattr(pane, "balanced", False):
            pane.sashpos(0, event.width // 2)
            pane.balanced = True

    def update_title(self):
        path = str(self.source_path) if self.source_path else "Untitled"
        self.root.title(f"p2f — {path}" + (" *" if self.dirty else ""))

    def modified(self, event=None):
        if not self.python_editor.text.edit_modified():
            return
        self.python_editor.text.edit_modified(False)
        self.changed()
        if self.refresh_timer is not None:
            self.root.after_cancel(self.refresh_timer)
        self.refresh_timer = self.root.after(80, self.refresh_source)

    def refresh_source(self):
        self.refresh_timer = None
        self.python_editor.refresh()
        self.python_count.set(line_label(self.python_editor.value()))
        self.update_title()

    def options_changed(self, *args):
        self.changed()

    def changed(self):
        self.revision += 1
        if self.current_fortran:
            self.fortran_state.set("Previous translation — source or options changed")
        if self.output_revision is not None:
            self.output_state.set("Previous execution results — source or options changed")
        self.timing_var.set("")
        self.schedule_live()

    def live_changed(self, *args):
        if self.live_var.get():
            self.schedule_live()
        else:
            self.pending_live = False
            if self.live_timer is not None:
                self.root.after_cancel(self.live_timer)
                self.live_timer = None

    def schedule_live(self):
        if self.closing or not self.live_var.get():
            return
        if self.live_timer is not None:
            self.root.after_cancel(self.live_timer)
        self.live_timer = self.root.after(750, self.live_translate)

    def live_translate(self):
        self.live_timer = None
        self.start("translate", automatic=True)

    def options(self) -> LocalOptions:
        timeout = float(self.timeout_var.get())
        tolerance = float(self.tolerance_var.get())
        round_digits = int(self.round_var.get()) if self.round_var.get().strip() else None
        work_dir = Path(self.work_dir_var.get()).expanduser().resolve()
        if not work_dir.is_dir():
            raise ValueError("Working directory does not exist")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("Timeout must be a positive finite number")
        if not math.isfinite(tolerance) or tolerance < 0:
            raise ValueError("Numeric tolerance must be nonnegative and finite")
        if round_digits is not None and round_digits < 0:
            raise ValueError("Output rounding must be nonnegative")
        if not self.python_var.get().strip():
            raise ValueError("Choose a Python executable")
        return LocalOptions(xp2f=self.xp2f, work_dir=work_dir, python=self.python_var.get().strip(),
                            timeout=timeout, compiler=self.compiler_var.get(),
                            int_kind=None if self.int_kind_var.get() == "default" else self.int_kind_var.get(),
                            pretty=self.pretty_var.get(), rng_replay=self.rng_var.get(),
                            numeric_diff=self.numeric_var.get(), numeric_diff_tol=tolerance,
                            round_digits=round_digits,
                            source_name=self.source_path.name if self.source_path else "main.py")

    def start(self, mode: str, *, automatic: bool = False):
        if self.closing:
            return
        if self.jobs.active is not None:
            if automatic:
                self.pending_live = True
            return
        source = self.python_editor.value()
        if not source.strip():
            self.status_var.set("Enter Python code")
            return
        status, message = syntax_status(source)
        if status != "complete":
            self.status_var.set("Waiting for complete Python syntax" if automatic else "Python syntax needs correction")
            if not automatic:
                self.set_text(self.diagnostics, message)
                self.notebook.select(1)
            return
        try:
            options = self.options()
        except ValueError as error:
            self.status_var.set(str(error))
            return
        if self.live_timer is not None:
            self.root.after_cancel(self.live_timer)
            self.live_timer = None
        self.pending_live = False
        request = Request(self.revision, source, mode, options, automatic)
        self.jobs.submit(request)
        for button in self.run_buttons:
            button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status_var.set("Translating…" if mode == "translate" else "Running current script…")

    def stop(self):
        self.pending_live = False
        if self.live_timer is not None:
            self.root.after_cancel(self.live_timer)
            self.live_timer = None
        self.jobs.cancel()
        self.status_var.set("Stopping…")

    def poll(self):
        item = self.jobs.take()
        if item is not None:
            request, result = item
            if self.closing:
                self.finish_close()
                return
            for button in self.run_buttons:
                button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.present(request, result)
            if self.pending_live and self.live_var.get():
                self.pending_live = False
                self.schedule_live()
        self.poll_timer = self.root.after(50, self.poll)

    def present(self, request: Request, result: Result):
        stale = request.revision != self.revision or request.source != self.python_editor.value()
        log = ("Previous source/options — results were not applied.\n\n" if stale else "")
        if result.command:
            log += "Command: " + (subprocess_list(result.command)) + "\n\n"
        log += result.stdout + ("\n" + result.stderr if result.stderr else "")
        self.set_text(self.diagnostics, log)
        if stale:
            self.status_var.set("Previous job finished; current input needs translation")
            return
        if result.cancelled:
            self.status_var.set("Cancelled")
            return
        if result.fortran:
            self.current_fortran = result.fortran
            self.fortran_revision = request.revision
            self.fortran_editor.set_value(result.fortran)
            self.fortran_count.set(line_label(result.fortran))
            self.fortran_state.set("Current translation")
        elif request.mode == "translate" and not result.ok:
            self.fortran_revision = None
            self.fortran_state.set("Translation failed — previous translation retained" if self.current_fortran else "Translation failed")
        display = split_run_output(result, request.mode)
        timings = display.timings or {}
        if request.mode == "translate":
            timings["transpile"] = result.seconds
        timings["total"] = result.seconds
        labels = (("python run", "Python"), ("transpile", "Translate"), ("compile", "Compile"),
                  ("fortran run", "Fortran"), ("total", "Total"))
        self.timing_var.set("  ".join(f"{label}: {timings[key]:.3f}s" for key, label in labels if key in timings))
        if request.mode != "translate":
            if request.mode in {"run-python", "time-python", "run-both", "diff", "time-both"}:
                self.set_text(self.python_output, display.python)
            if request.mode not in {"run-python", "time-python"}:
                self.set_text(self.fortran_output, display.fortran)
            self.output_revision = request.revision
            self.output_state.set("Current script — " + request.mode)
            self.notebook.select(0 if result.ok or result.matches is False else 1)
        elif not result.ok and not request.automatic:
            self.notebook.select(1)
        state = "MATCH" if result.matches else "DIFF" if result.matches is False else "Completed" if result.ok else "Failed"
        self.status_var.set(f"{state} in {result.seconds:.3f}s")

    @staticmethod
    def set_text(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def clear_output(self):
        for widget in (self.python_output, self.fortran_output, self.diagnostics):
            self.set_text(widget, "")
        self.output_revision = None
        self.output_state.set("No execution results")
        self.timing_var.set("")

    def confirm_save(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved Python", "Save changes to the Python source?", parent=self.root)
        return self.save_source() if answer else answer is False

    def replace_source(self, text: str, path: Path | None = None, *, saved: bool = False):
        self.stop_if_active()
        self.source_path = path
        self.saved_source = text if saved else ""
        self.python_editor.set_value(text)
        self.python_editor.text.edit_reset()
        self.python_editor.text.edit_modified(False)
        self.current_fortran = ""
        self.fortran_revision = None
        self.fortran_editor.set_value("")
        self.fortran_count.set("0 lines")
        self.fortran_state.set("No translation")
        self.clear_output()
        if path is not None and not self.fixed_work_dir:
            self.work_dir_var.set(str(path.parent))
        self.changed()
        self.refresh_source()
        self.python_editor.text.focus_set()

    def stop_if_active(self):
        if self.jobs.active is not None:
            self.stop()

    def new_source(self):
        if self.confirm_save():
            self.replace_source("")

    def load_example(self):
        if self.confirm_save():
            self.replace_source(EXAMPLE)

    def open_source(self):
        if not self.confirm_save():
            return
        path = filedialog.askopenfilename(parent=self.root, filetypes=[("Python", "*.py *.pyw"), ("All files", "*.*")])
        if path:
            try:
                self.load_source(Path(path))
            except (OSError, UnicodeError) as error:
                messagebox.showerror("Open failed", str(error), parent=self.root)

    def load_source(self, path: Path):
        path = Path(path).resolve()
        source = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
        self.replace_source(source, path, saved=True)

    def save_source(self, save_as: bool = False) -> bool:
        path = self.source_path
        if save_as or path is None:
            name = filedialog.asksaveasfilename(parent=self.root, defaultextension=".py",
                                               filetypes=[("Python", "*.py"), ("All files", "*.*")])
            if not name:
                return False
            path = Path(name).resolve()
        try:
            source = self.python_editor.value()
            path.write_text(source, encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Save failed", str(error), parent=self.root)
            return False
        name_changed = self.source_path != path
        self.source_path = path
        self.saved_source = source
        if name_changed:
            self.options_changed()
        if not self.fixed_work_dir and str(path.parent) != self.work_dir_var.get():
            self.work_dir_var.set(str(path.parent))
        self.update_title()
        self.status_var.set(f"Saved {path}")
        return True

    def save_fortran(self):
        if not self.current_fortran or self.fortran_revision != self.revision:
            messagebox.showinfo("Translate first", "Translate the current source before saving Fortran.", parent=self.root)
            return
        name = filedialog.asksaveasfilename(parent=self.root, defaultextension=".f90",
                                           initialfile=(self.source_path.stem if self.source_path else "main") + ".f90",
                                           filetypes=[("Fortran", "*.f90"), ("All files", "*.*")])
        if name:
            try:
                Path(name).write_text(self.current_fortran, encoding="utf-8")
            except OSError as error:
                messagebox.showerror("Save failed", str(error), parent=self.root)

    def choose_directory(self):
        directory = filedialog.askdirectory(parent=self.root, initialdir=self.work_dir_var.get())
        if directory:
            self.fixed_work_dir = True
            self.work_dir_var.set(directory)

    def close(self):
        if self.closing or not self.confirm_save():
            return
        self.closing = True
        self.stop()
        if self.jobs.active is None:
            self.finish_close()

    def finish_close(self):
        for timer in (self.poll_timer, self.live_timer, self.refresh_timer):
            if timer is not None:
                self.root.after_cancel(timer)
        self.jobs.close()
        self.root.destroy()


def subprocess_list(command):
    import subprocess
    return subprocess.list2cmdline(command) if sys.platform == "win32" else shlex.join(command)


def configure_windows_display():
    if sys.platform == "win32":
        import ctypes
        # Use physical coordinates so the initial size fits a scaled display.
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="optional Python file to open")
    parser.add_argument("--xp2f", type=Path, default=DEFAULT_XP2F)
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    parser.add_argument("--compiler", default="", help="compiler command; blank uses checked CLI defaults")
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--no-live", action="store_true", help="disable automatic translation initially")
    args = parser.parse_args(argv)
    if not args.xp2f.is_file():
        parser.error(f"transpiler not found: {args.xp2f}")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    root = None
    try:
        configure_windows_display()
        root = tk.Tk()
        Xp2fIde(root, xp2f=args.xp2f, python=args.python, compiler=args.compiler,
                timeout=args.timeout, source=args.source, work_dir=args.work_dir, live=not args.no_live)
        root.mainloop()
        return 0
    except (tk.TclError, OSError, UnicodeError) as error:
        if root is not None:
            root.destroy()
        print(f"p2f GUI: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
