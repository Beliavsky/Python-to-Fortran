# Python To Fortran Syntax Guide

This guide explains common numerical Python constructs through modern Fortran equivalents. It is not a complete Python implementation, a full Fortran tutorial, or a promise that every combination shown is accepted by `xp2f.py`.

The Fortran snippets are explanatory equivalents, not exact generated output. Unless labeled as complete programs, they assume suitable declarations and surrounding procedures. Generated code may instead use temporary arrays, specialized procedures, or helpers from `python.f90`. See the [README](README.md) for usage and current library support, and [tests/test_xp2f_cli.py](tests/test_xp2f_cli.py) for executable regression examples.

## A Complete Example

Python:

```python
import numpy as np

x = np.array([1.0, 2.0, 3.0])
total = 0.0
for i in range(len(x)):
    total += x[i] * x[i]
print(total)
```

One equivalent Fortran program:

```fortran
program squares
   use, intrinsic :: iso_fortran_env, only: dp => real64
   implicit none
   real(kind=dp) :: x(3), total
   integer :: i

   x = [1.0_dp, 2.0_dp, 3.0_dp]
   total = 0.0_dp
   do i = 1, size(x)
      total = total + x(i) * x(i)
   end do
   print *, total
end program squares
```

Both print a numeric value of 14. Display formatting can differ. Save the Python example as `squares.py` and check the actual translation with:

```console
python xp2f.py squares.py --run-diff
```

## Values, Types, and Names

Python infers types at runtime; Fortran declarations fix the type of each declared entity. Typical mappings are:

| Python value | Illustrative Fortran declaration/value |
| --- | --- |
| `n = 10` | `integer :: n`; `n = 10` |
| `x = 1.5` | `real(kind=dp) :: x`; `x = 1.5_dp` |
| `flag = True` | `logical :: flag`; `flag = .true.` |
| `z = 1 + 2j` | `complex(kind=dp) :: z`; `z = cmplx(1.0_dp, 2.0_dp, kind=dp)` |
| `text = 'hello'` | `character(len=:), allocatable :: text`; `text = 'hello'` |

Here `dp` denotes double precision, as imported in the complete example. Fortran default `real` need not be double precision. Python integers have arbitrary precision; Fortran integers have a finite range. `--int-kind int64` can widen eligible generated integer declarations, but does not provide arbitrary precision.

Fortran identifiers are case-insensitive. Python names such as `A` and `a` therefore need distinct generated spellings; leading underscores and other naming conflicts may also require renaming.

`xp2f.py` infers many declarations without annotations and also accepts selected annotations and [declaration-style comments](README.md#optional-type-and-rank-hints-in-comments). Some Python type/rank changes are implemented through local `BLOCK` declarations or procedure specialization. Arbitrary runtime type changes remain outside the supported model.

## Assignment and Mutation

Scalar assignment uses `=` in both languages. Numeric `x += y` usually becomes `x = x + y`. String concatenation uses `//` in Fortran:

```python
text = 'value: '
text += 'ready '
```

```fortran
text = 'value: '
text = text // 'ready '
```

Spaces are significant: inserting `trim(text)` would change this example. Deferred-length allocatable scalar strings can grow on assignment; a fixed-length character variable can truncate its right-hand side.

Array assignment has a more important semantic difference. In Python, `b = a` normally binds another reference to the same NumPy array; `b = a.copy()` requests independent storage. Ordinary Fortran array assignment copies values. Views, overlapping slices, and mutations therefore require more than replacing syntax. `xp2f.py` handles selected aliasing patterns, but general Python reference semantics should not be assumed.

## Conditions and Loops

| Python | Fortran equivalent |
| --- | --- |
| `if condition:` / `else:` | `if (condition) then` / `else` / `end if` |
| `while condition:` | `do while (condition)` / `end do` |
| `break` | `exit` |
| `continue` | `cycle` |
| `not flag` | `.not. flag` |
| Boolean `a and b`, `a or b` | `.and.`, `.or.` when evaluation is safe |

Python short-circuits `and` and `or`; Fortran does not guarantee short-circuit evaluation. A guard such as `i < len(x) and x[i] > 0` may require nested conditions. Python's operators can also return non-Boolean operands, so the table is not a general textual substitution rule.

`range` excludes its stop value; Fortran counted `do` includes its upper bound. A direct translation preserving the Python induction variable is:

```python
for i in range(n):
    y[i] = x[n - 1 - i]
```

```fortran
do i = 0, n - 1
   y(i + 1) = x(n - i)
end do
```

The arrays here have lower bound 1. An optimizer may instead choose a one-based induction variable, but every use must change consistently. Reverse indices and composite expressions are especially sensitive. A negative-step range also needs endpoint adjustment; it is not enough to copy the Python stop value into a Fortran `do`.

## Indexing and Slices

Assuming Fortran arrays with lower bound 1, valid nonnegative Python bounds, and positive unit stride:

| Python | Fortran |
| --- | --- |
| `x[0]` | `x(1)` |
| `x[i]` | `x(i + 1)` |
| `x[-1]` | `x(size(x))` |
| `x[lo:hi]` | `x(lo + 1:hi)` |
| `a[i, j]` | `a(i + 1, j + 1)` |
| `a[:, j]` | `a(:, j + 1)` |
| `a[i, :]` | `a(i + 1, :)` |
| `x[::-1]` | `x(size(x):1:-1)` |

These formulas are not sufficient for arbitrary negative bounds, omitted endpoints, clipping, or negative steps. Python normalizes slice bounds; Fortran sections do not automatically perform the same normalization. Fortran also permits explicitly declared lower bounds other than 1.

Rank means the number of dimensions, not an array's length. A matrix row selected with `a[i, :]` is rank 1; `a[i:i+1, :]` remains rank 2. Confusing those cases changes procedure interfaces and broadcasting behavior.

## Construction, Shape, and Storage Order

For `np.zeros((n, m))`, an explanatory Fortran equivalent is:

```fortran
real(kind=dp), allocatable :: a(:,:)
! ... executable statements follow all declarations ...
allocate(a(n,m), source=0.0_dp)
```

If `a` might already be allocated, deallocate it before this explicit allocation, or use an appropriate reallocating assignment. Local automatic allocatables and persistent module/SAVE storage have different lifetimes; a global array may retain its allocation between calls.

NumPy defaults to C order for many construction and reshape operations. Fortran stores its first index contiguously. For example:

```python
a = np.array([[1, 2, 3], [4, 5, 6]])
```

```fortran
integer :: a(2,3)
a = reshape([1, 4, 2, 5, 3, 6], [2, 3])
```

The logical rows match even though the constructor lists elements in a different order. Python `reshape`, `ravel`, transpose, and their `order=` choices must preserve element ordering, not just the final shape. `xp2f.py` may use temporaries or explicit transformations; not every NumPy layout/view operation is supported.

## Array Arithmetic, Broadcasting, and Masks

For conforming numeric arrays, `a + b` and `a * b` are elementwise operations in both NumPy and Fortran. A scalar can participate in a Fortran array expression. NumPy's more general broadcasting, however, is not implicit in Fortran: adding a length-`m` vector to each row of an `n`-by-`m` matrix may require `spread(vector, dim=1, ncopies=n)` or loops.

For a rank-1 array, selection by a Boolean mask can be expressed as `pack(x, mask)`. A scalar masked assignment such as `x[x < 0] = 0.0` can become:

```fortran
where (x < 0.0_dp)
   x = 0.0_dp
end where
```

A compact right-hand side with only `count(mask)` elements generally needs scattering, not a same-shape `where` assignment. Masked rows, repeated indices, and overlapping assignments need special care. Supported cases are tested; these are not blanket claims of full NumPy fancy-indexing support.

NumPy converts Boolean values when storing them into a numeric array. Fortran needs an explicit conversion, for example:

```fortran
a(i) = merge(1.0_dp, 0.0_dp, condition)  ! real destination
k(i) = merge(1, 0, condition)            ! integer destination
```

The indexed/sliced/masked Boolean-assignment paths have regression coverage. That does not imply that every mixed Boolean/numeric comparison or arithmetic expression is supported.

## Reductions and Matrix Algebra

| NumPy operation | Fortran equivalent for the stated ranks |
| --- | --- |
| `np.sum(x)` | `sum(x)` |
| `np.sum(a, axis=0)` for a matrix | `sum(a, dim=1)` |
| `np.sum(a, axis=1)` for a matrix | `sum(a, dim=2)` |
| `np.min(x)`, `np.max(x)` | `minval(x)`, `maxval(x)` |
| `np.any(mask)`, `np.all(mask)` | `any(mask)`, `all(mask)` |
| `a.T` for a matrix | `transpose(a)` |
| `a @ b` for two matrices | `matmul(a, b)` |
| `np.matmul(a, x)` for matrix/vector operands | `matmul(a, x)` |
| `np.matmul(x, y)` for two real vectors | `dot_product(x, y)` |

Python's built-in `sum(a)` iterates over the first axis, so for a matrix it differs from NumPy's all-elements `np.sum(a)`. Axis numbering starts at 0 in NumPy and at 1 in Fortran. Options such as `keepdims` also affect the result rank.

For complex vectors, NumPy `matmul` does not conjugate the first operand, whereas Fortran `dot_product` does. The unconjugated equivalent is `sum(x * y)`. Vector/vector `np.matmul` has regression coverage for integer, real, and complex inputs; do not infer identical coverage for every alternate spelling or for higher-rank batched products.

Linear solves, eigenproblems, and other supported `np.linalg`/SciPy calls may use helper routines and numerical-library bridges rather than Fortran intrinsics. A successful translation still needs numerical validation, especially for ill-conditioned problems and differences in floating-point evaluation order.

## Functions and Multiple Results

A scalar-returning Python function can become a Fortran function:

```python
def square(x):
    return x * x
```

```fortran
pure function square(x) result(y)
   real(kind=dp), intent(in) :: x
   real(kind=dp) :: y
   y = x * x
end function square
```

The argument type here is illustrative; `xp2f.py` infers types from the source and callers. `pure` and `elemental` are properties to establish, not automatic attributes of all translated functions. Mutation, I/O, and dependencies matter.

Multiple Python results, such as `point, seed = next_point(seed)`, may be lowered to a subroutine with separate output arguments. Each output has its own type and rank. When an input is also an output, or a destination is an array section, generated temporaries may be necessary to preserve evaluation order and avoid invalid Fortran aliasing.

Fortran optional arguments use `optional` and `present()`. Python defaults and `None` need additional lowering; there is no universal Fortran `None` value. See [`xpfunc2f.py`](xpfunc2f.py) for the separate workflow that exposes supported translated functions back to Python. Its extraction and `f2py` constraints are stricter than standalone compilation.

## Numeric and Output Pitfalls

- Python `/` performs true division even for integer operands; Fortran integer `/` truncates. Real conversion may be required.
- Python `//` floors toward negative infinity. Fortran integer division is not equivalent for negative values; generated code may need a floor-division helper.
- Python `%` has both numeric and string-formatting meanings. Numeric remainder sign rules and formatted field widths must be handled separately.
- `print` output is not portable byte-for-byte between Python and Fortran list-directed I/O. Array layout, exponent spelling, complex-number display, and significant digits can differ.
- Fixed-width Fortran numeric formats may print asterisks on overflow. Python formatting and runtime-string assembly can require helpers rather than a single Fortran format descriptor.
- Random seeds alone do not guarantee the same stream across Python and Fortran generators. For supported draws, `--rng-replay` records and replays Python values when comparing runs.

## Scope and Validation

Supported classes, pandas DataFrames, and SciPy calls use specialized lowering and runtime types; see the [README's support sections](README.md#class-support). This guide does not equate arbitrary Python objects with plain Fortran arrays or derived types.

Start with a small numerical example, inspect the emitted declarations and interfaces, compile with runtime checking, and compare against Python. `--run-diff` is useful for output comparisons, but tolerances and presentation matter. For complex arrays, comparing real and imaginary components separately can be clearer than comparing display syntax. Successful compilation or a zero exit status alone does not establish numerical equivalence.

The examples and cautions here complement the regression suite, including tests for reverse indexing, vector `matmul`, Boolean-to-numeric array assignments, string `+=`, tuple outputs, and repeated global-array allocation. Unsupported combinations should be reduced to small reproducers rather than inferred to work from a conceptual mapping.
