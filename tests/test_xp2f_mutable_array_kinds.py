"""Local array mutation must retain each caller's dtype."""
import ast

import pytest

from test_xp2f_cli import EXAMPLES_DIR, _run_xp2f_compile_diff


@pytest.mark.parametrize("extra_arg", [False, True])
def test_mutating_returned_array_preserves_integer_and_real_calls(tmp_path, extra_arg):
    source = (EXAMPLES_DIR / "xknapsack_inferred.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "subset_next")
    # Keep the original comments: the integer hint must not erase a real
    # array caller's dtype when the same procedure is also called with ints.
    lines = source.splitlines()[fn.lineno - 1:fn.end_lineno]
    if extra_arg:
        lines[0] = "def subset_next(s, unused):"
    tail = ", 0" if extra_arg else ""
    _run_xp2f_compile_diff(tmp_path, "xmutable_kinds.py", [
        "import numpy as np", *lines,
        "a = np.zeros(3, dtype=int)",
        "b = np.zeros(3)",
        "for i in range(9):",
        f"    ra = subset_next(a{tail})",
        f"    rb = subset_next(b{tail})",
        "    for j in range(3):",
        "        print(a[j], ra[j], b[j], rb[j])",
        "b[0] = 0.5",
        f"rb = subset_next(b{tail})",
        "print(b[0], rb[0])",
    ])


def test_knapsack_numerical_results(tmp_path):
    source = (EXAMPLES_DIR / "xknapsack_inferred.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = []
    for fn in tree.body:
        if isinstance(fn, ast.FunctionDef) and fn.name in {"knapsack_brute", "subset_next"}:
            lines.extend(source.splitlines()[fn.lineno - 1:fn.end_lineno])
    _run_xp2f_compile_diff(tmp_path, "xknapsack_values.py", [
        "import numpy as np", *lines,
        # A second real-array caller reproduces the original mixed profile.
        "s = np.zeros(3)",
        "s = subset_next(s)",
        "v = np.array([6.0, 10.0, 12.0])",
        "w = np.array([1.0, 2.0, 3.0])",
        "value, weight, chosen = knapsack_brute(3, v, w, 5.0)",
        "print(value, weight)",
        "for i in range(3):",
        "    print(chosen[i])",
    ])


def test_knapsack_original_test_cases(tmp_path):
    source = (EXAMPLES_DIR / "xknapsack_inferred.py").read_text(encoding="utf-8")
    # Exercise the original numerical drivers without platform-version or
    # wall-clock output, which necessarily differs between runtimes.
    # The tenth case enumerates 2**24 subsets; the first nine already
    # exercise the algorithm through 15 items without slowing the suite.
    source = source.replace("if ( n_data == 0 ):", "if ( n_data == 0 or n_data > 9 ):")
    lines = source.split("if ( __name__ == '__main__' ):")[0].splitlines()
    _run_xp2f_compile_diff(tmp_path, "xknapsack_original.py", lines + [
        "subset_next_test()", "knapsack_brute_test01()",
    ])
