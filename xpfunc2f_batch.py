#!/usr/bin/env python3
"""Batch runner for xpfunc2f.py over explicit files, glob patterns, and @list files.

Unlike xp2f_batch.py (which transpiles a WHOLE program to a standalone
Fortran executable -- a clean, uniform pass/fail per file), xpfunc2f.py
bridges ONE function inside a script (auto-defaulted when not given) to a
compiled-Fortran-backed Python wrapper. This batch runner exists to
stress-test THAT narrower, newer pipeline against a real corpus: every one
of xpfunc2f.py's own hand-picked test cases so far has surfaced a genuine
bug, so a larger corpus run is expected to find more.

Each file is run as `xpfunc2f.py <file> --run-both` (or --time-both) with
NO explicit function_name -- relying on xpfunc2f.py's own auto-defaulting
(the first function the script's top-level code calls, skipping `main`)
and on --run-both needing no per-file arguments (it patches the target's
own call site into the original script and reruns it with whatever inputs
the script already provides -- unlike --verify, which needs --verify-args
shaped for a specific target's own signature, not knowable generically
for an arbitrary corpus file).

Deliberately narrower than xp2f_batch.py's own flag surface: most of its
options (--strict, --strict-fix, --flat, --type, --autofix, ...) are
xp2f.py-specific concepts xpfunc2f.py has no equivalent of. Reuses its
general input-expansion/tee/resume infrastructure directly (imported,
not duplicated) since none of that is xp2f.py-specific either.

usage:
  python xpfunc2f_batch.py script1.py script2.py
  python xpfunc2f_batch.py @file_list.txt --jobs 4 --blockers
"""

from __future__ import annotations

import argparse
import atexit
import re
import subprocess
import sys
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List

from xp2f_batch import (
    InputExpansionError,
    TeeWriter,
    _default_tee_prefix,
    _expand_inputs,
    _path_key,
    _processed_from_log,
    _resolve_resume_anchor,
)

XPFUNC2F_PATH = Path(__file__).with_name("xpfunc2f.py").resolve()

_TARGET_DEFAULTED_RE = re.compile(r"^\s*Target:\s*'([^']*)'\s*\(defaulted", re.IGNORECASE)
_STAGE_FAIL_RE = re.compile(
    r"^\s*(Target|Transpile|Extract|F2PY Build|Run \(python\)|Run \(fortran-backed\)):\s*FAIL\b",
    re.IGNORECASE,
)
_EXTRACT_FAIL_REASON_RE = re.compile(r"^\s*Extract:\s*FAIL\s*\((.*)\)\s*$", re.IGNORECASE)
_RUN_BOTH_RE = re.compile(r"^\s*Run-both:\s*(MATCH|DIFF)\s*$", re.IGNORECASE)


@dataclass
class CaseResult:
    index: int
    source: str
    ok: bool
    rc: int
    stage: str  # "full_pass", or the stage the run stopped/failed at
    fail_reason: str | None
    target_name: str | None
    output: str = ""


def _extract_target_name(stdout: str) -> str | None:
    for ln in stdout.splitlines():
        m = _TARGET_DEFAULTED_RE.match(ln)
        if m:
            return m.group(1)
    return None


def _extract_extract_fail_reason(stdout: str) -> str | None:
    for ln in stdout.splitlines():
        m = _EXTRACT_FAIL_REASON_RE.match(ln)
        if m:
            return m.group(1).strip()
    return None


def _classify_stage(ok: bool, stdout: str) -> str:
    if ok:
        return "full_pass"
    for ln in stdout.splitlines():
        m = _STAGE_FAIL_RE.match(ln)
        if m:
            return m.group(1).lower().replace(" (", "_").replace(")", "").replace(" ", "_")
    for ln in stdout.splitlines():
        m = _RUN_BOTH_RE.match(ln)
        if m and m.group(1).upper() == "DIFF":
            return "run_both_diff"
    return "other_fail"


def _normalize_blocker(reason: str) -> str:
    r = reason.strip()
    if "no `module ... contains ... end module` block" in r:
        return "inlined_or_flat_no_module"
    if "uses a derived type" in r:
        return "derived_type_unsupported"
    if "rank-2-or-higher array" in r:
        return "rank2_plus_array"
    if "depends on" in r and "computed inside the function's own body" in r:
        return "array_result_size_data_dependent"
    if "only the common step=1 case" in r:
        return "array_result_range_step_not_1"
    if "has no `allocate(...)` statement" in r:
        return "array_result_no_allocate_recognized"
    if "isn't recognized as safely derivable from the function's own arguments" in r:
        return "array_result_size_not_derivable"
    if "has an array-shaped dummy argument or result" in r:
        return "array_in_dependency"
    if "needs helper(s)" in r:
        return "unbridgeable_helper_module"
    if "was not found as a top-level procedure" in r:
        return "target_not_found_in_translation"
    if "no top-level function found to use as a default target" in r:
        return "no_default_target"
    if r.startswith("no top-level `def") and "found in the source script" in r:
        return "target_def_not_found"
    trunc = r if len(r) <= 80 else r[:77] + "..."
    return f"other:{trunc}"


def _print_blocker_report(results: List[CaseResult], top_n: int = 0) -> None:
    blocker_to_files: dict[str, set[str]] = {}
    for r in results:
        if r.ok or r.stage != "extract" or not r.fail_reason:
            continue
        key = _normalize_blocker(r.fail_reason)
        blocker_to_files.setdefault(key, set()).add(r.source)

    print("")
    print("Blockers (Extract: FAIL reasons only -- the xpfunc2f.py-specific signal;")
    print("a Transpile: FAIL is a pre-existing xp2f.py-level gap, already tracked by")
    print("xp2f_batch.py's own blocker report on the same corpus):")
    if not blocker_to_files:
        print("(no Extract: FAIL cases)")
        return
    total_files = len(set().union(*blocker_to_files.values()))
    print(f"Files with an Extract-stage blocker: {total_files}")

    items = sorted(blocker_to_files.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    shown = items[:top_n] if top_n > 0 else items
    print(f"Top {top_n} blockers by unique-file impact:" if top_n > 0 else "Blockers by unique-file impact:")
    for i, (key, files) in enumerate(shown, 1):
        print(f"{i:2d}. {key:<40} files={len(files)}")

    # Greedy order by unique-file gain (same idea as xp2f_batch.py's own).
    unresolved = set().union(*blocker_to_files.values())
    remaining = list(blocker_to_files.items())
    print(f"Greedy implementation order (top {top_n}):" if top_n > 0 else "Greedy implementation order:")
    covered = 0
    step = 0
    while unresolved and remaining and (top_n <= 0 or step < top_n):
        best_key = None
        best_gain = -1
        best_cover: set[str] = set()
        for key, files in remaining:
            gain_set = files & unresolved
            if len(gain_set) > best_gain:
                best_gain = len(gain_set)
                best_key = key
                best_cover = gain_set
        if best_key is None or best_gain <= 0:
            break
        step += 1
        covered += best_gain
        print(f"{step:2d}. {best_key:<40} gain={best_gain:4d} covered_so_far={covered:4d}")
        unresolved -= best_cover
        remaining = [(k, v) for (k, v) in remaining if k != best_key]
    print(f"Remaining unresolved files: {len(unresolved)}")


def main() -> int:
    t0 = time.perf_counter()
    run_started = datetime.now()
    ap = argparse.ArgumentParser(description="Run xpfunc2f.py on multiple Python files/globs/@list files.")
    ap.add_argument("inputs", nargs="+", help="Python files, directories, glob patterns, and/or @list files.")
    ap.add_argument(
        "--work-dir",
        default=None,
        help="Root directory for per-file generated artifacts "
        "(default: xpfunc2f_batch_work_<timestamp>, one subfolder per file).",
    )
    ap.add_argument(
        "--time-both",
        action="store_true",
        help="Forward --time-both to xpfunc2f.py instead of --run-both.",
    )
    ap.add_argument(
        "--compile",
        action="store_true",
        help="Build only (Transpile+Extract+F2PY Build) -- neither --run-both nor "
        "--time-both, so the original script is never actually rerun. Much faster over "
        "a large corpus, at the cost of not checking the bridged function's own output "
        "still matches Python's. Mutually exclusive with --time-both.",
    )
    ap.add_argument(
        "--backend",
        choices=["f2py", "ctypes"],
        default="f2py",
        help="Forward --backend to xpfunc2f.py (default: f2py). 'ctypes' bridges via a "
        "bind(c) shim + plain gfortran -shared build instead of f2py's own crackfortran/"
        "meson pipeline.",
    )
    ap.add_argument("--maxfail", type=int, default=0, help="Stop after this many failures (0 = no limit).")
    ap.add_argument("--skip", type=int, default=0, help="Skip this many matched files before applying --limit.")
    ap.add_argument("--limit", type=int, default=0, help="Process at most this many matched files (0 = no limit).")
    ap.add_argument("--jobs", type=int, default=1, help="Run up to this many independent xpfunc2f.py jobs concurrently.")
    ap.add_argument("--timeout", type=float, default=0.0, help="Per-file timeout in seconds (0 = no timeout).")
    ap.add_argument(
        "--status-interval",
        type=float,
        default=60.0,
        help="Seconds between parallel progress reports while waiting (0 = disabled).",
    )
    ap.add_argument("--resume", help="Resume from a prior xpfunc2f_batch log by skipping already-processed files.")
    ap.add_argument("--resume-after", help="Start after this Python source path in matched ordering.")
    ap.add_argument("--resume-with", help="Start with this Python source path in matched ordering.")
    ap.add_argument(
        "-tee",
        "--tee",
        nargs="?",
        const="",
        help="Also write console output to this file; omit file to use "
        "<input-prefix>_results_YYYYMMDD_HHMMam.txt.",
    )
    ap.add_argument("--verbose", action="store_true", help="Print full xpfunc2f.py output for PASS cases too.")
    ap.add_argument("--terse", action="store_true", help="Show only failing cases (plus final totals).")
    ap.add_argument("--blockers", action="store_true", help="Print Extract-stage blocker summary at end.")
    ap.add_argument("--blockers-top", type=int, default=0, help="Limit blocker lists to top N items (0 = no limit).")
    args = ap.parse_args()

    tee_file = None
    original_stdout = sys.stdout
    if args.tee is not None:
        tee_name = args.tee
        if tee_name == "":
            tee_prefix = _default_tee_prefix(args.inputs)
            tee_name = f"{tee_prefix}_{run_started.strftime('%Y%m%d_%I%M%p').lower()}.txt"
        try:
            tee_path = Path(tee_name)
            if tee_path.parent and str(tee_path.parent) not in {"", "."}:
                tee_path.parent.mkdir(parents=True, exist_ok=True)
            tee_file = tee_path.open("w", encoding="utf-8", errors="ignore")
            sys.stdout = TeeWriter(original_stdout, tee_file)
            atexit.register(tee_file.close)
            print("Command:", "python " + subprocess.list2cmdline(sys.argv))
        except OSError as e:
            print(f"Invalid options: could not open tee file {tee_name!r}: {e}")
            return 1

    if args.resume_after and args.resume_with:
        print("Invalid options: --resume-after and --resume-with are mutually exclusive.")
        return 1
    if args.compile and args.time_both:
        print("Invalid options: --compile and --time-both are mutually exclusive.")
        return 1
    if args.jobs < 1:
        print("Invalid options: --jobs must be >= 1.")
        return 1
    if args.timeout < 0:
        print("Invalid options: --timeout must be >= 0.")
        return 1
    if args.status_interval < 0:
        print("Invalid options: --status-interval must be >= 0.")
        return 1
    if args.jobs > 1 and args.maxfail > 0:
        print("Invalid options: --jobs > 1 cannot be combined with --maxfail.")
        return 1

    try:
        py_files = _expand_inputs(args.inputs)
    except InputExpansionError as exc:
        print(f"Invalid input: {exc}")
        return 1
    if not py_files:
        print("No Python files matched the provided inputs.")
        return 1

    if args.resume:
        resume_path = Path(args.resume)
        if not resume_path.exists() or not resume_path.is_file():
            print(f"Invalid options: --resume file not found: {resume_path}")
            return 1
        done_keys = _processed_from_log(resume_path)
        before = len(py_files)
        py_files = [p for p in py_files if _path_key(p) not in done_keys]
        skipped = before - len(py_files)
        print(f"Resume: skipped {skipped} already-processed file(s) from {resume_path}.")
        if not py_files:
            print("Resume: no remaining files to process.")
            return 0

    if args.resume_after or args.resume_with:
        anchor_raw = args.resume_with if args.resume_with else args.resume_after
        anchor_resolved, err = _resolve_resume_anchor(py_files, anchor_raw)
        if anchor_resolved is None:
            print(f"Invalid options: {err}")
            return 1
        keys = [_path_key(p) for p in py_files]
        anchor_key = _path_key(anchor_resolved)
        idx = keys.index(anchor_key)
        if args.resume_after:
            py_files = py_files[idx + 1 :]
            print(f"Resume-after: starting after {anchor_resolved}. Remaining: {len(py_files)} file(s).")
        else:
            py_files = py_files[idx:]
            print(f"Resume-with: starting with {anchor_resolved}. Remaining: {len(py_files)} file(s).")
        if not py_files:
            print("Resume: no remaining files to process.")
            return 0

    if args.skip < 0:
        print("Invalid options: --skip must be >= 0.")
        return 1
    if args.skip > 0:
        py_files = py_files[args.skip :]
    if args.limit < 0:
        print("Invalid options: --limit must be >= 0.")
        return 1
    if args.limit > 0:
        py_files = py_files[: args.limit]

    if not XPFUNC2F_PATH.exists():
        print(f"Missing script: {XPFUNC2F_PATH}")
        return 1

    # A dedicated subfolder per file (index-prefixed, so name collisions
    # are impossible even for two same-named files in different corpus
    # directories) -- generated filenames are keyed by the TARGET
    # FUNCTION's own name, not the script's, so a shared --out-dir across
    # many files risks collisions, and --jobs > 1 makes that a real race,
    # not just a naming nuisance.
    work_root = (
        Path(args.work_dir)
        if args.work_dir
        else Path(f"xpfunc2f_batch_work_{run_started.strftime('%Y%m%d_%H%M%S')}")
    )
    work_root.mkdir(parents=True, exist_ok=True)

    results: List[CaseResult] = []
    failures = 0
    total = len(py_files)

    def _run_case(i: int, pyf: Path) -> CaseResult:
        rel = str(pyf)
        source_abs = pyf.resolve()
        out_dir = work_root / f"{i:04d}_{pyf.stem}"
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, str(XPFUNC2F_PATH), str(source_abs), "--out-dir", str(out_dir)]
        if args.backend != "f2py":
            cmd.extend(["--backend", args.backend])
        if not args.compile:
            cmd.append("--time-both" if args.time_both else "--run-both")

        try:
            cp = subprocess.run(
                cmd,
                # The script's OWN directory, matching how a user would
                # normally run it themselves -- xpfunc2f.py's --run-both
                # reruns the ORIGINAL script as its own subprocess with
                # no explicit cwd of its own, so it inherits whatever
                # cwd THIS subprocess.run uses; a corpus script reading
                # a local data file via a relative path would otherwise
                # silently break if run from out_dir instead.
                cwd=str(source_abs.parent),
                stdin=subprocess.DEVNULL,
                text=True,
                capture_output=True,
                encoding="utf-8",
                errors="ignore",
                timeout=(args.timeout if args.timeout > 0 else None),
            )
        except subprocess.TimeoutExpired as e:
            stdout = e.stdout or ""
            stderr = e.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="ignore")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="ignore")
            timeout_msg = f"TIMEOUT after {args.timeout:g} seconds: {' '.join(cmd)}"
            stderr = (stderr.rstrip() + "\n" + timeout_msg).lstrip()
            cp = subprocess.CompletedProcess(cmd, 124, stdout, stderr)

        stdout = cp.stdout or ""
        ok = cp.returncode == 0
        stage = _classify_stage(ok, stdout)
        target_name = _extract_target_name(stdout)
        fail_reason = _extract_extract_fail_reason(stdout) if stage == "extract" else None

        out_lines: list[str] = []
        if ok:
            if args.verbose and not args.terse:
                if stdout.strip():
                    out_lines.append(stdout.rstrip())
                if cp.stderr and cp.stderr.strip():
                    out_lines.append(cp.stderr.rstrip())
        else:
            if args.terse:
                out_lines.append(f"[{i}/{total}] {rel}")
            out_lines.append(f"  FAIL (exit {cp.returncode}, stage={stage})")
            if stdout.strip():
                out_lines.append(stdout.rstrip())
            if cp.stderr and cp.stderr.strip():
                out_lines.append(cp.stderr.rstrip())

        return CaseResult(
            index=i,
            source=rel,
            ok=ok,
            rc=cp.returncode,
            stage=stage,
            fail_reason=fail_reason,
            target_name=target_name,
            output="\n".join(out_lines),
        )

    def _record_result(r: CaseResult) -> bool:
        nonlocal failures
        results.append(r)
        if not r.ok:
            failures += 1
        if not args.terse:
            tgt = f" (target={r.target_name})" if r.target_name else ""
            print(f"[{r.index}/{total}] {r.source}{tgt}")
        if r.output:
            print(r.output)
        if (not args.terse) and r.index < total:
            print("")
        if args.maxfail > 0 and failures >= args.maxfail:
            print(f"Stopped at maxfail={args.maxfail}.")
            return True
        return False

    if args.jobs == 1:
        for i, pyf in enumerate(py_files, start=1):
            if _record_result(_run_case(i, pyf)):
                break
    else:
        print(f"Jobs: running up to {args.jobs} xpfunc2f.py subprocesses concurrently.")
        pending = {}
        next_idx = 1
        with ThreadPoolExecutor(max_workers=args.jobs) as executor:
            while next_idx <= total and len(pending) < args.jobs:
                fut = executor.submit(_run_case, next_idx, py_files[next_idx - 1])
                pending[fut] = next_idx
                next_idx += 1
            while pending:
                wait_timeout = args.status_interval if args.status_interval > 0 else None
                done, _ = wait(pending, timeout=wait_timeout, return_when=FIRST_COMPLETED)
                if not done:
                    active = ", ".join(f"[{idx}/{total}] {py_files[idx - 1]}" for idx in sorted(pending.values()))
                    print(f"Still running: {active}", flush=True)
                    continue
                for fut in sorted(done, key=lambda f: pending[f]):
                    pending.pop(fut)
                    _record_result(fut.result())
                    if next_idx <= total:
                        nfut = executor.submit(_run_case, next_idx, py_files[next_idx - 1])
                        pending[nfut] = next_idx
                        next_idx += 1

    results.sort(key=lambda r: r.index)

    print("")
    print("Summary:")
    summary_rows = [r for r in results if (not args.terse or not r.ok)]
    if args.terse and not summary_rows:
        print("(no failures)")
    src_w = max(len("source"), *(len(r.source) for r in summary_rows)) if summary_rows else len("source")
    stage_w = max(len("stage"), *(len(r.stage) for r in summary_rows)) if summary_rows else len("stage")
    tgt_w = max(len("target"), *(len(r.target_name or "") for r in summary_rows)) if summary_rows else len("target")
    if summary_rows:
        print(f"{'source':<{src_w}}  {'status':<6}  {'stage':<{stage_w}}  {'target':<{tgt_w}}")
        for r in summary_rows:
            status = "PASS" if r.ok else "FAIL"
            print(f"{r.source:<{src_w}}  {status:<6}  {r.stage:<{stage_w}}  {(r.target_name or ''):<{tgt_w}}")
    n_pass = sum(1 for r in results if r.ok)
    n_fail = len(results) - n_pass
    print(f"Totals: {len(results)} files, {n_pass} pass, {n_fail} fail")

    stage_counts: dict[str, int] = {}
    for r in results:
        stage_counts[r.stage] = stage_counts.get(r.stage, 0) + 1
    print("Outcomes: " + "  ".join(f"{k}={v}" for k, v in sorted(stage_counts.items())))

    if args.blockers:
        _print_blocker_report(results, top_n=args.blockers_top)

    elapsed = time.perf_counter() - t0
    print(f"Elapsed: {elapsed:.3f} s at {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}")
    print(f"Work dir: {work_root}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
