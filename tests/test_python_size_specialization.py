import ast

import pytest

from python_size_specialization import specialize_singleton_returns


PREFIX = '''import numpy as np
def evaluate(x):
    x = np.atleast_1d(x)
    n = x.shape[0]
    y = x * 2.0
    if n == 1:
        y = y[0]
    return y
'''


@pytest.mark.parametrize('driver', [
    'def forward(x):\n    return evaluate(x)',
    'x = np.array([1., 2.])\nx = obtain()\nevaluate(x)',
    'x = np.array([1., 2.])\nalias = x\nalias.resize(1)\nevaluate(x)',
    'x = np.array([1., 2.])\nx.shape = (1, 2)\nevaluate(x)',
    'x = np.array([1., 2.])\nx.shape: object = (1, 2)\nevaluate(x)',
    'x = np.array([1., 2.])\nmutate(x)\nevaluate(x)',
    'x = np.array([1., 2.])\nprint(mutate(x), evaluate(x))',
    'x = np.array([1., 2.])\nif flag:\n    x = np.array([1.])\nevaluate(x)',
    'def f(evaluate):\n    return evaluate(1.0)',
    'xs = [evaluate(x) for x in values]',
    'def f(n):\n    x = np.linspace(0., 1., n)\n    return evaluate(x)',
    'evaluate(np.array([1., 2.], ndmin=2))',
    'evaluate(np.array([1., 2.], dtype=np.dtype((float, (2,)))))',
])
def test_unknown_sizes_are_not_specialized(driver):
    tree = specialize_singleton_returns(ast.parse(PREFIX + driver))
    assert 'def evaluate_size_' not in ast.unparse(tree)
    assert 'def evaluate(x)' in ast.unparse(tree)


@pytest.mark.parametrize('value,mode', [
    ('1.5', 'scalar'), ('np.array([1.5])', 'one'),
    ('np.array([], dtype=float)', 'vector'), ('np.array([1., 2.])', 'vector'),
    ('np.linspace(0., 1., 3)', 'vector'),
])
def test_proven_sizes_preserve_python_semantics(value, mode):
    source = PREFIX + f'result = evaluate({value})'
    original, rewritten = {}, {}
    exec(source, original)
    tree = specialize_singleton_returns(ast.parse(source))
    exec(compile(tree, '<specialized>', 'exec'), rewritten)
    import numpy as np
    np.testing.assert_array_equal(original['result'], rewritten['result'])
    assert np.ndim(original['result']) == np.ndim(rewritten['result'])
    assert f'def evaluate_size_{mode}' in ast.unparse(tree)
    assert 'def evaluate(x)' not in ast.unparse(tree)


def test_unused_candidate_is_not_removed():
    assert 'def evaluate(x)' in ast.unparse(specialize_singleton_returns(ast.parse(PREFIX)))


def test_boolean_subscript_is_not_scalar_unwrapping():
    source = PREFIX.replace('y = y[0]', 'y = y[False]') + 'evaluate(1.5)'
    tree = specialize_singleton_returns(ast.parse(source))
    assert 'def evaluate_size_' not in ast.unparse(tree)


def test_partial_specialization_keeps_unknown_entry_point():
    tree = specialize_singleton_returns(ast.parse(PREFIX + '''
def forward(x):
    return evaluate(x)
result = evaluate(1.5)
'''))
    source = ast.unparse(tree)
    assert 'def evaluate(x)' in source
    assert 'def evaluate_size_scalar' in source


def test_forward_definition_order_and_loop_scalars():
    source = '''def driver():
    result = []
    for i in range(3):
        x = i / 2.0
        result.append(evaluate(x))
    return result
''' + PREFIX + '\nresult = driver()'
    tree = specialize_singleton_returns(ast.parse(source))
    namespace = {}
    exec(compile(tree, '<specialized>', 'exec'), namespace)
    assert namespace['result'] == [0., 1., 2.]
    assert 'def evaluate_size_scalar' in ast.unparse(tree)
