import ast
import contextlib
import io
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from python_array_aliases import normalize_direct_array_aliases


CASES = {
    'numpy_readonly_loop_rebinding': '''import numpy as np
q = np.array([1.0, 2.0])
p = q
for i in range(3):
    p = p + q
print(p[0], p[1], q[0], q[1])
p = q
for i in range(2):
    p = 2.0 * p
print(p[0], p[1], q[0], q[1])
''',
    'loop_buffer_rotation': '''import numpy as np
x = np.array([1.0, 2.0])
for i in range(3):
    new_x = x.copy()
    new_x[0] = x[0] + 1.0
    x = new_x
print(x[0], x[1])
''',
    'list_rebind': '''a = [1, 2]
b = a
a = [3, 4]
print(a[0], a[1], b[0], b[1])
b[0] = 8
print(a[0], b[0])
''',
    'list_slice': '''a = [1, 2, 3]
b = a[1:]
b[0] = 9
print(a[0], a[1], a[2], b[0], b[1])
a[2] = 7
print(a[2], b[1])
''',
    'numpy_call': '''import numpy as np
def bump(x):
    x[0] += 10
a = np.array([1, 2])
b = a
bump(b)
print(a[0], b[0])
''',
    'numpy_rebind': '''import numpy as np
def bump(x):
    x[0] += 10
a = np.array([1, 2])
b = a
c = b
a = np.array([3, 4])
bump(c)
print(a[0], b[0], c[0])
b = np.array([5, 6])
bump(c)
print(a[0], b[0], c[0])
''',
    'list_chain': '''a = [1, 2]
b = a
c = b
b = [3, 4]
c[0] = 9
print(a[0], b[0], c[0])
a = c
a[1] = 8
print(a[1], c[1])
''',
    'local_scope': '''def example():
    a = [1, 2]
    b = a
    a = [3, 4]
    print(a[0], b[0])
example()
''',
    'numpy_copy': '''import numpy as np
a = np.array([1, 2])
b = a.copy()
c = a
b[0] = 8
c[0] = 9
print(a[0], b[0], c[0])
''',
    'numpy_matrix_call': '''import numpy as np
def set_first(x):
    x[0, 0] = 9.5
a = np.array([[1.5, 2.5], [3.5, 4.5]])
b = a
set_first(b)
print(a[0, 0], b[0, 0])
''',
    'list_slice_alias': '''a = [1, 2, 3]
c = a
b = c[::-1]
b[0] = 9
print(a[2], c[2], b[0])
c[0] = 8
print(a[0], b[2])
''',
    'list_to_scalar': '''a = [1, 2]
b = a
a = 42
print(a, b[0], b[1])
''',
}


@pytest.mark.parametrize('source', CASES.values(), ids=CASES.keys())
def test_direct_alias_normalization_preserves_python(source):
    def output(program):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            exec(compile(program, '<alias-test>', 'exec'), {})
        return stream.getvalue()
    tree = normalize_direct_array_aliases(ast.parse(source))
    assert output(tree) == output(source)
    before = ast.dump(tree)
    assert ast.dump(normalize_direct_array_aliases(tree)) == before


@pytest.mark.parametrize('name', CASES)
def test_xp2f_direct_alias_results(tmp_path, name):
    src = tmp_path / ('xalias_' + name + '.py')
    src.write_text(CASES[name], encoding='utf-8')
    run = subprocess.run([sys.executable, str(ROOT / 'xp2f.py'), str(src), '--compile', '--run-diff'],
                         cwd=tmp_path, capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    assert 'Run diff: MATCH' in run.stdout, run.stdout + run.stderr


@pytest.mark.parametrize('tail', [
    'if flag:\n    a = [3, 4]',
    'for i in range(2):\n    b = a',
    'def get():\n    return b',
    'a: list = [3, 4]',
    'read = lambda: b',
    'import math as b',
    'a, b = [3, 4], [5, 6]',
    'class Box:\n    value = b',
])
def test_uncertain_alias_bindings_are_diagnosed(tail):
    with pytest.raises(NotImplementedError, match='unsupported array alias binding'):
        normalize_direct_array_aliases(ast.parse('a = [1, 2]\nb = a\n' + tail))


def test_overlapping_mutating_arguments_are_diagnosed():
    source = 'def f(x, y):\n    x[0] = y[0] + 1\na = [1, 2]\nb = a\nf(a, b)'
    with pytest.raises(NotImplementedError, match='overlapping actual arguments'):
        normalize_direct_array_aliases(ast.parse(source))


def test_scalar_aliases_are_unchanged():
    tree = ast.parse('a = 1\nb = a\na = 2\nprint(a, b)')
    before = ast.dump(tree)
    assert ast.dump(normalize_direct_array_aliases(tree)) == before


@pytest.mark.parametrize('tail', [
    'for i in range(2):\n    b = a\n    b[0] = 9',
    'for i in range(2):\n    b = np.add(a, 1, out=a)',
    'for i in range(2):\n    b = unknown(a)',
    'view = a[:]\nfor i in range(2):\n    b = a + 1\n    view[0] = 9',
    'view = np.array(a, copy=False)\nfor i in range(2):\n    b = a + 1\n    view[0] = 9',
])
def test_loop_sharing_with_mutation_is_not_materialized(tail):
    with pytest.raises(NotImplementedError, match='unsupported array alias binding'):
        normalize_direct_array_aliases(ast.parse(
            'import numpy as np\na = np.array([1, 2])\nb = a\n' + tail))
