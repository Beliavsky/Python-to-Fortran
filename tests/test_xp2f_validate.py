"""Fast tests for conservative execution-output comparison."""
import xp2f_validate as validate


def test_integer_comparison_is_exact_above_float_precision():
    assert not validate.close_tokens('9007199254740992', '9007199254740993')
    assert validate.compare_text('1 2 3', '1 2 4')['status'] == 'mismatched'


def test_printed_precision_and_exponent_formats():
    assert validate.close_tokens('0.035879', '0.35878594979556103E-001')
    assert validate.close_tokens('1.250000', '1.25D+00')
    assert not validate.close_tokens('0.035879', '0.0358801')
    assert validate.compare_text('answer=1.25', 'answer=1.250000')['status'] == 'matched'


def test_text_and_missing_output_are_not_silently_ignored():
    assert validate.compare_text('success 12', 'failure 12')['status'] == 'unverified'
    assert validate.compare_text('1 2 3', '1 2')['status'] == 'mismatched'
    assert validate.compare_text('r8 value 1', 'r8 value 2')['python_numbers'] == 1


def test_complex_layout_requires_specialized_comparison():
    result = validate.compare_text('[1.+2.j 3.-4.j]', '(1.0,2.0) (3.0,-4.0)')
    assert result['status'] == 'unverified'
    assert 'Complex' in result['reason']


def test_narrow_timestamp_and_version_normalization():
    a = 'Sun Sep 20 01:02:03 2026\nPython version: 3.13\nvalue 4\n'
    b = 'Sun Sep 20 02:03:04 2026\npython version: unknown\nvalue   4\n'
    assert validate.compare_text(a, b)['status'] == 'matched'
    assert validate.compare_text('time 1.0000', 'time 2.0000')['status'] == 'mismatched'


def test_unsupported_rng_is_flagged():
    assert validate.nondeterminism('import random\nx = random.random()') == ['stdlib random']
    assert validate.nondeterminism('x = rng.integers(10)') == ['integers']
    assert validate.nondeterminism('x = rng.uniform()') == []
    assert validate.nondeterminism('def get_seed():\n    return time.time()') == ['clock-derived seed']


def test_changed_and_new_output_files(tmp_path):
    (tmp_path / 'input.txt').write_text('same')
    initial = {'input.txt': validate.sha(tmp_path / 'input.txt')}
    assert validate.output_files(tmp_path, initial) == {}
    (tmp_path / 'output.txt').write_text('new')
    (tmp_path / 'input.txt').write_text('changed')
    assert set(validate.output_files(tmp_path, initial)) == {'input.txt', 'output.txt'}
