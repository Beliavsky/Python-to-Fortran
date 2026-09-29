"""Distinguish lowering hints from user-written annotation contracts."""
import ast
import copy
import shutil
import subprocess
import sys

import pytest

from test_xp2f_cli import EXAMPLES_DIR, REPO_ROOT, XP2F_PATH
import xp2f


@pytest.mark.parametrize("explicit", [False, True])
def test_price_analysis_annotation_provenance(explicit):
    tree = ast.parse((EXAMPLES_DIR / "xfit_hv_no_dates.py").read_text(encoding="utf-8"))
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    analyze = next(fn for fn in funcs if fn.name == "analyze_file")
    horizons = next(arg for arg in analyze.args.args if arg.arg == "horizons")
    if explicit:
        # Deliberately incompatible: normalization must not silently repair
        # a user's annotation or reclassify it as an internal hint.
        horizons.annotation = ast.Name(id="int", ctx=ast.Load())
    xp2f.normalize_price_table_analysis_annotations(tree.body, funcs)
    assert ast.unparse(horizons.annotation) == ("int" if explicit else "'int[:]'")
    assert getattr(horizons, "_xp2f_generated_annotation", False) is not explicit
    xp2f.normalize_price_table_analysis_numeric_pipeline(tree.body, funcs)
    analyze = next(fn for fn in funcs if fn.name == "analyze_file")
    horizons = next(arg for arg in analyze.args.args if arg.arg == "horizons")
    assert ast.unparse(horizons.annotation) == ("int" if explicit else "'int[:]'")
    assert getattr(copy.deepcopy(horizons), "_xp2f_generated_annotation", False) is not explicit


def test_generated_dict_keys_are_integer_vectors():
    tree = ast.parse((EXAMPLES_DIR / "xma_persist.py").read_text(encoding="utf-8"))
    funcs = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    xp2f.normalize_int_array_dict_comp_maps(tree.body, funcs)
    table = next(fn for fn in funcs if fn.name == "print_table")
    keys = next(arg for arg in table.args.args if arg.arg == "sharpe_vals_keys")
    assert xp2f.annotation_type_spec(keys.annotation)[:2] == ("int", 1)
    assert keys._xp2f_generated_annotation


def test_explicit_price_analysis_scalar_annotation_still_rejected(tmp_path):
    source = (EXAMPLES_DIR / "xfit_hv_no_dates.py").read_text(encoding="utf-8")
    source = source.replace(
        "def analyze_file(path, lookback, horizons, weights, annualization):",
        "def analyze_file(path, lookback, horizons: int, weights, annualization):",
    )
    script = tmp_path / "xannotated_price.py"
    script.write_text(source, encoding="utf-8")
    shutil.copy2(REPO_ROOT / "prices_no_dates.csv", tmp_path / "prices_no_dates.csv")
    result = subprocess.run([sys.executable, str(XP2F_PATH), str(script)],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode != 0, result.stdout + result.stderr
    assert "'horizons') of 'analyze_file' is annotated 'int'" in result.stdout + result.stderr
