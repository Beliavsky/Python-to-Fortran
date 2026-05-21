# xp2f Failure Repros From `burkardt_python_results_20260514_1203am.txt`

Each `xrepro_*.py` file is a reduced pattern from one or more still-failing
Burkardt translations in the 2026-05-14 00:03 batch result.

Run an individual repro with:

```bat
python xp2f.py repros\xrepro_NAME.py --compile
```

Some repros are expected to fail during transpilation, while others generate
Fortran that fails to compile.

Fixed repros kept as regression checks:

- `xrepro_int_real_array_constructor.py`: mixed integer/real constructors now compile.
- `xrepro_complex_real_array_constructor.py`: mixed complex/real constructors now compile.

Current repro coverage:

- `xrepro_bitxor.py`: unsupported Python `^` bitwise xor in arithmetic expression.
- `xrepro_char_or_char.py`: string truthiness lowered to invalid character/integer comparison.
- `xrepro_combinations_with_replacement.py`: unsupported `itertools.combinations_with_replacement`.
- `xrepro_csv_reader_without_with_open.py`: `csv.reader` only supported in `with open(...)` context.
- `xrepro_dict_value_append.py`: append target is a subscript, not a plain list variable.
- `xrepro_for_object_children.py`: class instantiation/object iterator pattern is unsupported.
- `xrepro_import_local_module.py`: unsupported local `from module import symbol`.
- `xrepro_isinstance.py`: unsupported `isinstance`.
- `xrepro_mixed_percent_tuple.py`: old-style `%` format tuple mixes character and numeric values.
- `xrepro_modulo_mixed_kinds.py`: Python `%` with integer/real operands lowers to invalid Fortran `modulo`.
- `xrepro_np_append_axis2d.py`: `np.append(..., axis=0)` unsupported for rank-2 arrays.
- `xrepro_queue.py`: unsupported `queue.Queue`.
- `xrepro_ragged_nested_list.py`: ragged nested list constructor.
- `xrepro_redefine_loop_index.py`: assignment to loop index inside loop.
- `xrepro_sorted_assignment.py`: `sorted(...)` only supported directly in `for` loops.
- `xrepro_string_numeric_compare.py`: string/integer comparison lowers to invalid Fortran.
- `xrepro_sum_scalar.py`: `np.sum` on scalar lowers to invalid Fortran `sum(scalar)`.
- `xrepro_try_except.py`: unsupported `try`/`except`.
- `xrepro_tuple_return_shape.py`: inconsistent tuple return arity.
- `xrepro_tuple_subscript_swap.py`: tuple assignment with subscript targets.
