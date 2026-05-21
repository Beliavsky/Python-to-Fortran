#!/usr/bin/env python3
"""
Compare two xp2f_batch.py result files and report regressions in the newer run.

A regression is currently defined as a source file that was effectively PASS in
the baseline file and FAIL in the newer file. Files missing from the newer file
can also be reported as regressions with --missing-is-regression.
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path


ENTRY_RE = re.compile(r"^\[(\d+)/(\d+)\]\s+(.*\S)\s*$")
FAIL_RE = re.compile(r"^\s+FAIL(?:\s|\(|$)")


@dataclass
class Entry:
    path: str
    status: str
    outcome: str | None
    fail_summary: str | None


def _first_nonempty(lines: list[str]) -> str | None:
    for line in lines:
        txt = line.strip()
        if txt:
            return txt
    return None


def parse_results(path: Path) -> dict[str, Entry]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    out: dict[str, Entry] = {}

    current_path: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_path, current_lines
        if current_path is None:
            return
        status = "PASS"
        fail_summary = None
        for i, line in enumerate(current_lines):
            if FAIL_RE.match(line):
                status = "FAIL"
                tail = [line.strip()]
                nxt = _first_nonempty(current_lines[i + 1 : i + 4])
                if nxt is not None:
                    tail.append(nxt)
                fail_summary = " | ".join(tail)
                break
        out[current_path.lower()] = Entry(
            path=current_path,
            status=status,
            outcome="full_pass" if status == "PASS" else None,
            fail_summary=fail_summary,
        )
        current_path = None
        current_lines = []

    for line in lines:
        m = ENTRY_RE.match(line)
        if m:
            flush()
            current_path = m.group(3)
            current_lines = []
            continue
        if current_path is not None:
            current_lines.append(line)
    flush()

    # xp2f_batch.py also writes a compact summary table at the end. Use it
    # when present because it distinguishes transpile/compile/run/other fails.
    summary_re = re.compile(
        r"^(?P<path>.*?\.py)\s+(?P<status>PASS|FAIL)\s+(?P<outcome>\S+)\s+"
    )
    for line in lines:
        m = summary_re.match(line.strip())
        if not m:
            continue
        key = m.group("path").lower()
        old = out.get(key)
        if old is None:
            out[key] = Entry(
                path=m.group("path"),
                status=m.group("status"),
                outcome=m.group("outcome"),
                fail_summary=None,
            )
        else:
            old.status = m.group("status")
            old.outcome = m.group("outcome")
    return out


def _outcomes(path: Path) -> list[tuple[str, str]]:
    outcome = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Outcomes:"):
            outcome = line.removeprefix("Outcomes:").strip()
    if outcome is None:
        return []
    return re.findall(r"(\S+?)=(\S+)", outcome)


def _print_outcomes_table(
    baseline_name: str,
    baseline_entries: int,
    baseline_outcomes: list[tuple[str, str]],
    newer_name: str,
    newer_entries: int,
    newer_outcomes: list[tuple[str, str]],
) -> None:
    labels = ["entries"] + [name for name, _ in baseline_outcomes]
    if not labels:
        labels = ["entries"] + [name for name, _ in newer_outcomes]
    baseline_values = {"entries": str(baseline_entries), **dict(baseline_outcomes)}
    newer_values = {"entries": str(newer_entries), **dict(newer_outcomes)}
    diff_values: dict[str, str] = {}
    for name in labels:
        try:
            diff = int(newer_values.get(name, "0")) - int(baseline_values.get(name, "0"))
        except ValueError:
            diff_values[name] = ""
            continue
        diff_values[name] = f"{diff:+d}"
    run_width = max(len("baseline"), len("newer"), len("diff"))
    file_width = max(len(baseline_name), len(newer_name), len("file"))
    col_widths = [
        max(
            len(name),
            len(baseline_values.get(name, "")),
            len(newer_values.get(name, "")),
            len(diff_values.get(name, "")),
        )
        for name in labels
    ]
    print(
        f"{'':<{run_width}}  {'file':<{file_width}}  "
        + "  ".join(f"{name:>{width}}" for name, width in zip(labels, col_widths))
    )
    print(
        f"{'baseline':<{run_width}}  {baseline_name:<{file_width}}  "
        + "  ".join(f"{baseline_values.get(name, ''):>{width}}" for name, width in zip(labels, col_widths))
    )
    print(
        f"{'newer':<{run_width}}  {newer_name:<{file_width}}  "
        + "  ".join(f"{newer_values.get(name, ''):>{width}}" for name, width in zip(labels, col_widths))
    )
    print(
        f"{'diff':<{run_width}}  {'':<{file_width}}  "
        + "  ".join(f"{diff_values.get(name, ''):>{width}}" for name, width in zip(labels, col_widths))
    )


def _default_result_pair() -> tuple[Path, Path]:
    files = [
        p
        for p in Path.cwd().glob("burkardt_python_results*")
        if p.is_file()
    ]
    if len(files) < 2:
        raise FileNotFoundError(
            "need at least 2 files in the current directory matching burkardt_python_results*"
        )
    files.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
    return files[-2], files[-1]


def _sorted_default_results() -> list[Path]:
    files = [
        p
        for p in Path.cwd().glob("burkardt_python_results*")
        if p.is_file()
    ]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name.lower()))
    return files


def main() -> int:
    ap = argparse.ArgumentParser(
        description="compare two xp2f_batch.py results files and list regressions in the second run"
    )
    ap.add_argument("baseline", nargs="?", help="older results file")
    ap.add_argument("newer", nargs="?", help="newer results file")
    ap.add_argument(
        "--missing-is-regression",
        action="store_true",
        help="treat files present in baseline but absent in newer results as regressions",
    )
    ap.add_argument(
        "--all-status-changes",
        action="store_true",
        help="also print non-regression status changes",
    )
    args = ap.parse_args()

    if args.baseline is None and args.newer is None:
        baseline_path, newer_path = _default_result_pair()
    elif args.baseline is not None and args.newer is not None:
        baseline_path = Path(args.baseline)
        newer_path = Path(args.newer)
    elif args.baseline is not None:
        files = _sorted_default_results()
        if len(files) < 2:
            ap.error("need at least 2 files matching burkardt_python_results* in the current directory")
        given = Path(args.baseline)
        latest = files[-1]
        if given.resolve() == latest.resolve():
            baseline_path, newer_path = files[-2], files[-1]
        else:
            baseline_path, newer_path = given, latest
    else:
        ap.error("provide zero, one, or two results files")

    baseline = parse_results(baseline_path)
    newer = parse_results(newer_path)
    baseline_outcomes = _outcomes(baseline_path)
    newer_outcomes = _outcomes(newer_path)
    _print_outcomes_table(
        baseline_path.name,
        len(baseline),
        baseline_outcomes,
        newer_path.name,
        len(newer),
        newer_outcomes,
    )

    regressions: list[str] = []
    improvements: list[str] = []
    new_failures: list[str] = []
    other_changes: list[str] = []
    failure_outcomes = {"transpile_fail", "compile_fail", "run_fail", "other_fail"}

    for key, old in baseline.items():
        new = newer.get(key)
        if new is None:
            if args.missing_is_regression:
                regressions.append(f"MISSING {old.path}")
            continue
        if old.status == "PASS" and new.status == "FAIL":
            msg = f"REGRESSION {new.path}"
            if new.fail_summary:
                msg += f"\n  {new.fail_summary}"
            regressions.append(msg)
        elif old.status == "FAIL" and new.status == "PASS":
            improvements.append(os.path.basename(new.path))

        old_outcome = old.outcome or old.status.lower()
        new_outcome = new.outcome or new.status.lower()
        if old_outcome != new_outcome and new_outcome in failure_outcomes:
            msg = f"{new_outcome} {new.path}  ({old_outcome} -> {new_outcome})"
            if new.fail_summary:
                msg += f"\n  {new.fail_summary}"
            new_failures.append(msg)
        elif args.all_status_changes and old_outcome != new_outcome:
            msg = f"STATUS {new.path}: {old_outcome} -> {new_outcome}"
            if new.fail_summary:
                msg += f"\n  {new.fail_summary}"
            other_changes.append(msg)

    print(f"regressions {len(regressions)}")
    print(f"improvements {len(improvements)}")
    print(f"new_failures {len(new_failures)}")

    if regressions:
        print("")
        print("[REGRESSIONS]")
        for item in regressions:
            print(item)

    if improvements:
        print("")
        print("[IMPROVEMENTS]")
        for item in sorted(improvements, key=str.lower):
            print(item)

    if new_failures:
        print("")
        print("[NEW FAILURES]")
        for item in sorted(new_failures, key=str.lower):
            print(item)

    if args.all_status_changes and other_changes:
        print("")
        print("[OTHER STATUS CHANGES]")
        for item in other_changes:
            print(item)

    return 1 if regressions else 0


if __name__ == "__main__":
    raise SystemExit(main())
