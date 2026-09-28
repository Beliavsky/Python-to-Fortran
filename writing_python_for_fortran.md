# Writing Python for Fortran Translation

Small choices in numerical Python can make translation more predictable and the generated Fortran easier to understand. This guide explains those choices; the [syntax guide](python_to_fortran_syntax_guide.md) explains how constructs map to Fortran, and the [README](README.md) describes usage and current support.

These are recommendations, not a definition of good Python or a list of mandatory restrictions. `xp2f.py` handles some type and rank changes, name collisions, and function specialization. Conversely, following these recommendations does not guarantee that every library call or combination of features is supported. Examples below illustrate source structure, not a complete compatibility specification. Fragments assume `import numpy as np` where needed.

## Keep variable types and ranks stable

Prefer one numeric type and one array rank for each variable within a function. Rank means the number of array dimensions: a vector has rank 1 and a matrix rank 2.

Less translation-friendly:

```python
values = np.array([1.0, 2.0, 3.0])
values = values.reshape((3, 1))
values = values.sum()
print(values)
```

Prefer names for the distinct stages:

```python
values = np.array([1.0, 2.0, 3.0])
column = values.reshape((3, 1))
total = column.sum()
print(total)
```

Likewise, avoid reusing an integer index as a real-valued measurement or an array as a Boolean flag. Separate names make declarations and data flow clearer.

The same advice applies across calls to persistent state, such as function
attributes. Storing `2.0` in `store.saved` and later replacing it with
`"Shazam!"` is valid Python, but mixed numeric/string persistent storage is
not supported. Use separate fixed-type fields, such as `store.value` and
`store.message`. Procedure specialization does not solve this: different
overloads would still need to share the same changing-type value. The
transpiler diagnoses some statically evident cases; absence of a diagnostic
does not imply support for arbitrary mixed-type state.

Fixed rank does **not** mean fixed size. A vector can have a length determined at runtime, and supported allocatable arrays can change size without changing rank. Scalar broadcasting is also natural numerical code:

```python
offset = 2.0
values = np.array([1.0, 3.0, 5.0])
shifted = values - offset
```

Here `offset` remains a scalar; it does not need to become an array.

## Choose names that remain distinct without case

Python distinguishes `A` from `a`; Fortran does not. Within a scope, prefer names that differ by more than capitalization.

Less convenient for translation:

```python
A = np.eye(3)
a = np.ones(3)
b = A @ a
```

Clearer generated names:

```python
matrix = np.eye(3)
vector = np.ones(3)
product = matrix @ vector
```

The transpiler can rename conflicting identifiers in supported cases, so case-only differences are not automatically an error. Avoiding them reduces renaming and makes it easier to compare the two programs. Apply the same principle to argument names and fields.

## Make numeric intent explicit

Initialize accumulators with the intended type, and specify array element types when the default is not what the algorithm needs:

```python
total = 0.0
count = 0
indices = np.zeros(5, dtype=int)
weights = np.zeros(5, dtype=float)
```

An integer array is appropriate for indices, but not for values that may become fractional. Adding `dtype=int` is a numerical conversion, not merely a translation hint: it can discard fractional parts. Similarly, changing `0` to `0.0` should reflect the intended arithmetic, not conceal an inference bug.

Keep `/` and `//` intentional. Do not replace division by floor division just to obtain an integer declaration. Python integers have arbitrary precision, whereas generated Fortran integers have a finite range. Widening integers can help within that range but does not provide arbitrary precision.

Use homogeneous numeric arrays for numerical work. Mixed numeric types may be promoted by NumPy; containers mixing numbers, strings, and arbitrary objects need a different representation and are harder to translate.

## Keep function interfaces predictable

Prefer arguments with clear roles and results with consistent types and ranks across branches. For tuple results, keep the number and meaning of components consistent as well.

For example, a function returning a vector on success and a scalar sentinel on failure has a less predictable interface than one returning a vector and a separate status flag:

```python
def normalize(values):
    norm = np.sqrt(np.sum(values * values))
    if norm == 0.0:
        return values.copy(), False
    return values / norm, True
```

Both branches return a vector and a Boolean when `values` is a vector. Callers must check the flag. This is an interface design choice, not a reason to silently change an existing function's failure semantics.

A function accepting vectors on some calls and matrices on others can be perfectly good Python. `xp2f.py` specializes supported local functions for different argument ranks; `--report-specializations` enables informational notes about those specializations. Separate vector and matrix entry points can simplify a complicated interface, but are not universally necessary. Arbitrary runtime type or rank dispatch is not implied by specialization support.

Accurate annotations and the supported [declaration-style comments](README.md#optional-type-and-rank-hints-in-comments) can clarify intent. They are not substitutes for consistent code, nor does an annotation perform a runtime conversion in Python.

## Use distinct targets for nested loops

Python leaves a loop's target variable visible after each iteration and after the loop. Reusing it in an inner loop can change a value the outer body still needs.

Prefer:

```python
for row in range(3):
    for col in range(4):
        print(row, col)
```

over using `i` for both targets. Reusing a name in separate, sequential loops is different and is often harmless. If changing existing nested loops, check the intended behavior: renaming a target can change results when the original code deliberately relied on its final value.

## Make array ownership and mutation clear

In Python, `other = values` shares the same array; `other = values.copy()` creates independent storage. Many NumPy slices are views. Ordinary Fortran array assignment instead copies values, so aliasing and mutation require special handling during translation.

When independent storage is intended, say so:

```python
original = np.array([1.0, 2.0, 3.0])
adjusted = original.copy()
adjusted[0] = 0.0
```

Do not add copies everywhere: they cost time and memory, and can change behavior when shared mutation is intentional. Prefer straightforward ownership, document functions that mutate their inputs, and test those side effects. Overlapping slices, multiple aliases, and rebinding combined with mutation deserve particular attention; general Python reference semantics should not be assumed to be supported.

## Separate numerical kernels from dynamic application logic

Small functions with explicit inputs and outputs are easier to translate and test than numerical calculations interleaved with plotting, interactive input, or dynamically constructed objects.

For example, keep a calculation such as:

```python
def sum_squares(values):
    total = 0.0
    for i in range(values.size):
        total += values[i] * values[i]
    return total
```

separate from reading files and displaying results. Whole-array NumPy expressions are also appropriate; this is not a recommendation to rewrite all vectorized operations as loops.

Pass changing state as arguments where practical. Global constants can be useful, but mutable global state makes interfaces less apparent. Reflection, `eval`, dynamic attributes, and heterogeneous object structures are outside the straightforward numerical subset. Check current library support rather than assuming that a NumPy or SciPy import makes every operation available.

When only the kernel needs compilation, consider the supported function-extraction workflow with `xpfunc2f.py`. Its bridge has its own interface and result-shape limitations; standalone translation support does not automatically imply bridge support.

## Validate behavior, not just compilation

Make intended output explicit. A bare expression such as `np.all(values > 0)`
displays a result in a Python REPL, but discards it in a script. Use
`print(np.all(values > 0))` to display it, or assign it to a variable for later
use. For supported standalone `np.all` and `np.any` calls, the transpiler
evaluates and discards the result and warns about its non-use; it does not
insert printing into the generated program.

Start with a small deterministic driver that exercises the actual calculation and prints meaningful results. From the project directory, compare its Python and Fortran output with:

```console
python xp2f.py example.py --compile --run-diff
```

Also test properties that printed output may omit, such as array shapes, input mutation, and failure behavior. A successful comparison covers the exercised inputs, not all possible executions.

Useful cases include:

- Empty and singleton arrays, where the algorithm permits them.
- First and last indices, negative values, and zero-valued inputs.
- Each intended argument rank and each result branch.
- Integer-range boundaries and numerically sensitive inputs.
- Side effects on arrays shared between callers and callees.

For random algorithms, use fixed input data or a controlled replay of random draws when comparing individual results. The same seed alone does not guarantee identical draws from different random-number implementations. Statistical checks may be more appropriate for validating a distribution.

Choose numerical tolerances for the problem and printed precision. Neither successful compilation nor a completed run proves numerical equivalence. See [Numerical Limitations](NUMERICAL_LIMITATIONS.md) for diagnosed examples and caveats.

If valid, straightforward numerical Python produces an incorrect translation, reduce it to a small reproducer and report it. These recommendations help users structure code; they do not excuse incorrect generated results.
