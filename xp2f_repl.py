#!/usr/bin/env python3
"""Interactive Python workspace with p2f translation and replay commands."""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import shlex
import sys

from p2f_session import LocalBackend, LocalOptions, PythonWorkspace, Result, Session, input_status, replay_source


HELP = """Enter Python normally; finish an indented block with a blank line.
Python input executes once in the live workspace. Run commands replay ALL saved
source from the beginning in fresh processes, repeating any program side effects.

:translate           Translate the accumulated source
:run                 Compile and run Fortran
:run-python          Run the source in fresh Python
:run-both            Run Python and Fortran
:diff                Run both and compare output
:time, :time-python, :time-both
                     Time fresh execution (xp2f reports its individual stages)
:replay              Reset and rebuild the live Python workspace from saved source
:list                List saved input with line numbers
:source              Show source with explicit prints used for replay
:fortran             Show latest generated Fortran, including its stale/current status
:load PATH           Replace saved source; use :replay to execute it
:save PATH           Save original Python source
:save-source PATH    Save Python source with replay expression printing
:save-fortran PATH   Save current Fortran; translate first if it is stale
:undo                Remove last input block and reset Python; use :replay afterward
:clear               Clear source, generated Fortran, and Python workspace
:help, :quit          quit() and exit() also end the session

Quote filenames containing spaces. Ctrl+C cancels an input block or running job;
EOF exits. Exiting does not execute or automatically save the session.
"""


def show_result(result: Result, *, timing: bool = False) -> None:
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    if timing:
        print(f"Elapsed: {result.seconds:.4f} s ({'ok' if result.ok else 'failed'})")


def command_words(text: str) -> list[str]:
    # Non-POSIX splitting preserves Windows backslashes; remove surrounding quotes.
    return [word[1:-1] if len(word) >= 2 and word[0] == word[-1] and word[0] in "\"'" else word
            for word in shlex.split(text, posix=False)]


def handle_command(text: str, session: Session, *, timing: bool = False) -> bool:
    """Handle a colon command. Return False only for an exit command."""
    try:
        words = command_words(text[1:])
        if not words:
            return True
        command, *arguments = words
        command = command.lower()
        path_commands = {"load", "save", "save-source", "save-fortran"}
        if command in path_commands:
            if len(arguments) != 1:
                raise ValueError(f"usage: :{command} PATH")
        elif arguments:
            raise ValueError(f":{command} takes no arguments")
        if command in {"quit", "exit"}:
            return False
        if command == "help":
            print(HELP)
        elif command == "list":
            for number, line in enumerate(session.source.splitlines(), 1):
                print(f"{number:4}: {line}")
        elif command == "source":
            print(replay_source(session.source), end="")
        elif command == "fortran":
            if session.last_fortran:
                print("Generated Fortran is current." if session.fortran_current else
                      "Generated Fortran is stale; use :translate to update it.")
                print(session.last_fortran, end="" if session.last_fortran.endswith("\n") else "\n")
            else:
                print("No generated Fortran. Use :translate.")
        elif command == "clear":
            session.clear()
            if isinstance(session.backend, LocalBackend):
                session.backend.options.source_name = "main.py"
            print("Session cleared.")
        elif command == "undo":
            if session.undo():
                print("Last block removed; Python workspace reset." +
                      (" Use :replay to restore it." if not session.workspace_synced else ""))
            else:
                print("Session is empty.")
        elif command == "replay":
            print("Replaying saved source into a new live Python workspace.")
            result = session.replay_workspace()
            show_result(result, timing=timing)
            if result.exit_code is not None:
                raise SystemExit(result.exit_code)
        elif command == "load":
            path = Path(arguments[0]).expanduser()
            source = path.read_text(encoding="utf-8-sig")
            ast_check(source)
            session.load(source)
            if isinstance(session.backend, LocalBackend):
                session.backend.options.source_name = path.name
            print(f"Loaded {path}; use :replay to execute it, or :run-both to compare it.")
        elif command in {"save", "save-source", "save-fortran"}:
            path = Path(arguments[0]).expanduser()
            if command == "save-fortran" and not session.fortran_current:
                raise ValueError("No current Fortran translation; use :translate first.")
            source = (session.last_fortran if command == "save-fortran" else
                      replay_source(session.source) if command == "save-source" else session.source)
            if path.exists() and input(f"Overwrite {path}? [y/N] ").strip().lower() != "y":
                return True
            path.write_text(source, encoding="utf-8")
            print(f"Saved {path}")
        elif command in LocalBackend.MODES:
            if command != "translate":
                print("Replaying all saved source in fresh processes.")
            show_result(session.run(command), timing=timing or command.startswith("time"))
        else:
            raise ValueError(f"unknown command :{command}; use :help")
    except (OSError, SyntaxError, ValueError) as error:
        print(f"p2f: {error}", file=sys.stderr)
    return True


def ast_check(source: str) -> None:
    import ast
    ast.parse(source)


def run_repl(session: Session, *, timing: bool = False) -> int:
    print("p2f interactive Python-to-Fortran session. Type :help for commands.")
    print("Run commands replay saved source; ordinary Python input executes once.")
    pending: list[str] = []
    while True:
        try:
            line = input("...> " if pending else "p2f> ")
        except EOFError:
            print()
            if pending:
                print("Incomplete input was discarded.", file=sys.stderr)
            return 0
        except KeyboardInterrupt:
            pending.clear()
            print("\nInput block cancelled.")
            continue
        if not pending and line.lstrip().startswith(":"):
            try:
                if not handle_command(line.lstrip(), session, timing=timing):
                    return 0
            except KeyboardInterrupt:
                print("\nCommand cancelled.")
            continue
        if not pending and not line.strip():
            continue
        pending.append(line)
        source = "\n".join(pending)
        status = input_status(source)
        if status == "incomplete":
            continue
        if status == "invalid":
            try:
                compile(source, "<p2f>", "single")
            except (SyntaxError, OverflowError, ValueError) as error:
                print(f"{type(error).__name__}: {error}", file=sys.stderr)
        else:
            result = session.submit(source)
            show_result(result, timing=timing)
            if result.exit_code is not None:
                return result.exit_code
        pending.clear()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", help="Python file to load without executing")
    parser.add_argument("--xp2f", type=Path, default=Path(__file__).with_name("xp2f.py"))
    parser.add_argument("--python", default=sys.executable, help="Python executable for evaluation and replay")
    parser.add_argument("--work-dir", type=Path, help="working directory; default: source file's directory or current directory")
    parser.add_argument("--compiler", default="", help="compiler command forwarded to xp2f.py")
    parser.add_argument("--timeout", type=float, default=60.0, help="timeout per evaluation or replay, seconds")
    parser.add_argument("--int-kind", choices=["int32", "int64"])
    parser.add_argument("--rng-replay", action="store_true")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--round", type=int, dest="round_digits", help="round both replay outputs to N decimal places")
    parser.add_argument("--numeric-diff", action="store_true")
    parser.add_argument("--numeric-diff-tol", type=float, default=1.0e-12)
    parser.add_argument("--time", action="store_true", help="show elapsed time for evaluations and commands")
    parser.add_argument("--batch", action="store_true", help="run the source file once and exit")
    parser.add_argument("--mode", choices=sorted(LocalBackend.MODES), default="diff", help="execution mode for --batch")
    args = parser.parse_args(argv)
    if (not math.isfinite(args.timeout) or args.timeout <= 0
            or not math.isfinite(args.numeric_diff_tol) or args.numeric_diff_tol < 0
            or (args.round_digits is not None and args.round_digits < 0)):
        parser.error("timeout must be positive; tolerance and output rounding must be nonnegative")
    if args.batch and not args.source:
        parser.error("--batch requires a source file")
    source_path = Path(args.source).resolve() if args.source else None
    work_dir = (args.work_dir or (source_path.parent if source_path else Path.cwd())).resolve()
    if not work_dir.is_dir():
        parser.error(f"working directory does not exist: {work_dir}")
    if not args.xp2f.is_file():
        parser.error(f"transpiler does not exist: {args.xp2f}")
    try:
        source = source_path.read_text(encoding="utf-8-sig") if source_path else ""
        ast_check(source)
        options = LocalOptions(args.xp2f.resolve(), work_dir, args.python, args.timeout,
                               args.compiler, args.int_kind, args.pretty, args.rng_replay,
                               args.numeric_diff, args.numeric_diff_tol, args.round_digits)
        options.source_name = source_path.name if source_path else "main.py"
        session = Session(PythonWorkspace(work_dir, args.timeout, args.python), LocalBackend(options))
        try:
            if source_path:
                session.load(source)
                print(f"Loaded {source_path} ({len(source.splitlines())} lines).")
                if not args.batch:
                    print("Use :replay to build the Python workspace, or a run command for fresh execution.")
            if args.batch:
                result = session.run(args.mode)
                show_result(result, timing=args.time or args.mode.startswith("time"))
                return 0 if result.ok else 1
            return run_repl(session, timing=args.time)
        finally:
            session.close()
    except (OSError, SyntaxError, ValueError) as error:
        print(f"p2f: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
