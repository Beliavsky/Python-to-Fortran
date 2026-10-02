"""Regression tests for host constants and nonadvancing scalar output."""
from pathlib import Path
import re
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("parallel", [False, True])
def test_host_parameter_extent(tmp_path, parallel):
    source = """height = 3
width = 4
def grid():
    output = [0] * (height * width)
    for h in range(height):
        for w in range(width):
            output[h * width + w] = h * width + w + 1
    return output
result = grid()
print(len(result))
print(sum(result))
"""
    if parallel:
        source = ("import numba\n" + source.replace("def grid():", "@numba.njit(parallel=True)\ndef grid():")
                  .replace("in range(", "in numba.prange("))
    _check(tmp_path, source, no_local_width=True)


@pytest.mark.parametrize("binding", ["argument", "assignment", "loop"])
def test_real_local_shadowing(tmp_path, binding):
    bodies = {
        "argument": "def f(width):\n    return width * 2\nprint(f(3))\n",
        "assignment": "def f():\n    width = 3\n    return width * 2\nprint(f())\n",
        "loop": "def f():\n    total = 0\n    for width in range(3):\n        total += width\n    return total\nprint(f())\n",
    }
    _check(tmp_path, "width = 4\n" + bodies[binding] + "print(width)\n")


def _check(tmp_path, source, no_local_width=False):
    src = tmp_path / "xhost_extent.py"
    src.write_text(source, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(ROOT / "xp2f.py"), str(src), "--compile", "--run-diff"],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "Run diff: MATCH" in proc.stdout, proc.stdout + proc.stderr
    if no_local_width:
        generated = src.with_name("xhost_extent_p.f90").read_text(encoding="utf-8")
        body = generated.split("function grid()", 1)[1].split("end function", 1)[0]
        assert not re.search(r"::[^\n]*\bwidth\b", body)
