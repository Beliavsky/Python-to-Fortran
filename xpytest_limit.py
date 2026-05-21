#!/usr/bin/env python
"""Run pytest with an optional limit on the number of collected tests."""

from __future__ import annotations

import argparse
import subprocess
import sys


def _parse_args(argv: list[str]) -> tuple[int | None, int | None, list[str]]:
    parser = argparse.ArgumentParser(
        description="Run pytest, optionally limiting execution to the first N collected tests.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="run only the first LIMIT tests after pytest collection and filtering",
    )
    parser.add_argument(
        "--max-fail",
        type=int,
        default=None,
        help="stop after MAX_FAIL pytest failures (alias for pytest --maxfail)",
    )
    ns, pytest_args = parser.parse_known_args(argv)
    if ns.limit is not None and ns.limit < 0:
        parser.error("--limit must be nonnegative")
    if ns.max_fail is not None and ns.max_fail < 1:
        parser.error("--max-fail must be positive")
    return ns.limit, ns.max_fail, pytest_args


def _without_quiet_args(pytest_args: list[str]) -> list[str]:
    return [arg for arg in pytest_args if arg not in {"-q", "-qq", "--quiet"}]


def _pytest_options_only(pytest_args: list[str]) -> list[str]:
    value_options = {
        "-k",
        "-m",
        "-o",
        "--basetemp",
        "--confcutdir",
        "--deselect",
        "--ignore",
        "--ignore-glob",
        "--import-mode",
        "--junitxml",
        "--maxfail",
        "--override-ini",
        "--rootdir",
        "--tb",
    }
    out: list[str] = []
    expect_value = False
    for arg in pytest_args:
        if expect_value:
            out.append(arg)
            expect_value = False
            continue
        if arg == "--":
            break
        if arg.startswith("-"):
            out.append(arg)
            if arg in value_options:
                expect_value = True
            continue
        # Positional selectors are used for collection. Once limited node IDs
        # are chosen, keeping the original selectors would run extra tests.
    return out


def _collect_nodeids(pytest_args: list[str]) -> list[str]:
    cmd = [sys.executable, "-m", "pytest", "--collect-only", "-q", *_without_quiet_args(pytest_args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        sys.stdout.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise SystemExit(proc.returncode)

    nodeids: list[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("<") or line.startswith("="):
            continue
        if line.endswith(" collected in 0.00s") or " test collected in " in line or " tests collected in " in line:
            continue
        if " deselected " in line or line.startswith("no tests collected"):
            continue
        if "::" not in line:
            continue
        nodeids.append(line)
    return nodeids


def main(argv: list[str] | None = None) -> int:
    limit, max_fail, pytest_args = _parse_args(sys.argv[1:] if argv is None else argv)
    if max_fail is not None:
        pytest_args = [f"--maxfail={max_fail}", *pytest_args]

    if limit is None:
        return subprocess.run([sys.executable, "-m", "pytest", *pytest_args], check=False).returncode

    nodeids = _collect_nodeids(pytest_args)
    selected = nodeids[:limit]
    if not selected:
        print("No tests selected.")
        return 5

    return subprocess.run(
        [sys.executable, "-m", "pytest", *_pytest_options_only(pytest_args), *selected],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
