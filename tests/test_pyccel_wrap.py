"""Regression check for pyccel_wrap.py against the examples/pyccel_bench/
corpus -- the one set of driver scripts this project has actually
verified as pyccel-compatible (see the whole-session comparison work
this tool grew out of). Deliberately NOT run against xp2f.py's own much
broader test_xp2f_cli.py suite: that suite exercises pandas/scipy/csv and
many other features pyccel doesn't support at all, and asserts on the
exact structure of xp2f.py's OWN generated Fortran (variable names,
helper-call shapes) -- neither kind of check has a meaningful pyccel
analog, so running pyccel_wrap.py over it would mostly produce expected,
uninteresting "pyccel doesn't support this" noise rather than real
signal about pyccel_wrap.py's own correctness.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PYCCEL_WRAP_PATH = REPO_ROOT / "pyccel_wrap.py"
PYCCEL_BENCH_DIR = REPO_ROOT / "examples" / "pyccel_bench"

# Only these 3 of the 15 examples/pyccel_bench/ driver scripts (built and
# verified against xp2f.py earlier this session) also translate, build,
# and run correctly through pyccel_wrap.py as they stand today. The other
# 12 hit a real limitation of pyccel itself, unrelated to pyccel_wrap.py:
#
# - f-string format specifiers (f'{x:.6f}') -- used by every one of the
#   other drivers' own print() calls for readable output -- aren't
#   syntax pyccel's parser supports at all: run_bellman_ford.py,
#   run_poisson_2d.py, run_md.py, run_euler.py,
#   run_midpoint_explicit.py, run_midpoint_fixed.py, run_rk4.py,
#   run_ode_euler.py, run_cfd_cavity_flow.py.
# - np.set_printoptions isn't a function pyccel recognizes:
#   run_linearconv_1d.py, run_nonlinearconv_1d.py.
# - run_splines.py hits a genuine bug in pyccel's OWN generated Fortran
#   for its Spline class translation (an invalid `deallocate` on a
#   temporary that was never declared allocatable) -- nothing to do
#   with pyccel_wrap.py, and unrelated to xp2f.py's own class-method
#   feature, since pyccel translates splines.py's Spline class
#   completely independently.
#
# Maps each driver script to the local sibling module(s) it needs
# alongside it.
PYCCEL_WRAP_CASES: dict[str, list[str]] = {
    "run_ackermann.py": ["ackermann_mod.py"],
    "run_dijkstra.py": ["dijkstra.py"],
    "run_laplace_2d.py": ["laplace_2d_mod.py"],
}

_PYCCEL_AVAILABLE = shutil.which("pyccel") is not None


def _run_pyccel_wrap(tmp_path: Path, driver_name: str) -> subprocess.CompletedProcess:
    for name in [driver_name, *PYCCEL_WRAP_CASES[driver_name]]:
        shutil.copy2(PYCCEL_BENCH_DIR / name, tmp_path / name)
    return subprocess.run(
        [
            sys.executable,
            str(PYCCEL_WRAP_PATH),
            str(tmp_path / driver_name),
            "--run-both",
            "--numeric-diff",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.skipif(not _PYCCEL_AVAILABLE, reason="pyccel is not installed")
@pytest.mark.parametrize("driver_name", sorted(PYCCEL_WRAP_CASES))
def test_pyccel_wrap_run_both_matches_python(tmp_path: Path, driver_name: str) -> None:
    # Runs safely under this project's own default parallel `pytest.ini`
    # `-n 4` config: pyccel_wrap.py locates pyccel's own output directory
    # dynamically (`__pyccel__` + `PYTEST_XDIST_WORKER`, matching pyccel's
    # own convention for exactly this reason -- see pyccel_wrap.py's own
    # module docstring), so each worker gets its own, non-colliding
    # `__pyccel__gwN` directory.
    proc = _run_pyccel_wrap(tmp_path, driver_name)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run numeric diff: MATCH" in proc.stdout, proc.stdout + proc.stderr
