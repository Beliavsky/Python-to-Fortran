# Sortrows validation, September 21, 2026

The core `sortrows` routine is copied unchanged from John Burkardt's
MIT-licensed `C:\python\public_domain\burkardt\sortrows\sortrows.py`:

```python
x = x[np.lexsort(x.T[::-1])]
```

## Confirmed transpiler bug and fix

For real inputs, the initial generated function declared its argument and result
integer and its caller emitted `sortrows(int(x))`. Fractional keys were truncated
before sorting. For the fractional fixture, Python's first sorted value was
-0.25, whereas Fortran produced 0. The separately emitted permutation of the
original real keys was correct, isolating the failure to argument inference.

The final semantic-integer-context inference recursively inspected names inside
an indexing expression, including arguments to `lexsort`. But an integer-valued
function result does not imply integer inputs. The inference now stops at call
boundaries. Focused regressions cover real keys passed to both `lexsort` and
`argsort` inside indexing expressions.

## Deterministic checks

`python check.py` validates real fixtures; `python check.py --integer` validates
integer fixtures using `probe_int.py`. Both pass all eight cases and 147 tagged
records after the fix. Cases include ties across multiple columns, duplicate
rows, negative values, a single column, a single row, zero rows with three
columns, fractional real keys, and input whose first/last-column orders differ.

The checker compares sorted entries and permutations against NumPy and an
independent Python tuple-key sort. Duplicate rows test stable index order.
Shape and preservation of the original input are checked explicitly. Integer
fixtures use integer-valued constructor literals; their fractional-fixture
counterpart uses the corresponding truncated integer values.

Logs and separate real/integer `analysis.json` files retain the results. The
external Burkardt source is unchanged. These checks do not certify NaNs,
infinities, complex keys, every integer width, or all array layouts.

## Constructor follow-up: fixed

The initial integer control used real constructor literals with `dtype=np.int64`.
That exposed a separate code-generation problem: inference chooses an integer
argument, but the inline constructor is emitted as a real array without the
requested conversion, causing a compile-time argument mismatch.
`float_constructor.py` isolates that follow-up. It now compiles and produces
the expected integer 1 after a separate constructor-emission fix. Explicit
integer dtypes are applied to list elements before constructing the Fortran
array, including nested rows and lists of row vectors. The constructor path
also uses the shared dtype parser, covering string spellings such as 'int64'.
Regression tests compare inline arguments and named assignments for positive
and negative fractions, mixed literals, empty arrays, and int/np.int32/np.int64
and string dtype spellings. This fixes conversion placement; it does not claim
new support for every NumPy integer width or out-of-range float-to-int casts.
