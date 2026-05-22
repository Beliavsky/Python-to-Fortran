# Comparison with Pyccel

Python-to-Fortran and [Pyccel](https://github.com/pyccel/pyccel) both translate numerical Python toward compiled languages, but they have different goals and workflows.

## Summary

| Topic | Python-to-Fortran | Pyccel |
| --- | --- | --- |
| Main target | Fortran source from Python scripts | Fortran, C, or C++ extension modules and executables |
| Primary command | `python xp2f.py foo.py` | `pyccel compile foo.py` |
| One-step run/test | `--run`, `--run-both`, and `--run-diff` compile and execute translated code | `pyccel compile` translates and builds; generated artifacts are normally run or imported separately |
| Type information | Tries to infer types and ranks from unannotated code; optional comments can help | Type annotations are central, especially function argument annotations |
| Typical use case | Batch testing and translating existing Fortran-friendly numerical Python scripts | Accelerating annotated scientific Python functions or modules |
| Output style | Standalone Fortran program plus helper runtime | Python extension module; executable if the input has a `__main__` block |
| Maturity | Experimental project built around `xp2f.py` | Larger established project with broader compiler infrastructure |

## Workflow Difference

Python-to-Fortran is designed as both a transpiler and a regression-testing harness. For example:

```console
python xp2f.py foo.py --run-diff
```

This runs the original Python program, transpiles it to Fortran, compiles the Fortran, runs the generated executable, and compares normalized output.

Pyccel has a one-step translate-and-build command:

```console
pyccel compile foo.py
```

That command translates and compiles a single Python file. Pyccel's command-line documentation says the normal endpoint is a CPython extension module, and that an executable can be generated when the input file contains an `if __name__ == "__main__":` block. This is close to one-step compilation, but it is not the same as `xp2f.py --run-both` or `--run-diff`, which are explicitly designed to execute both versions and compare behavior.

## Type Information

Pyccel documentation states that type annotations are an integral part of Pyccel and that function argument annotations are compulsory. Array ranks are commonly supplied using string annotations such as:

```python
def f(x: 'float[:]', a: 'float[:,:]'):
    ...
```

Python-to-Fortran tries to translate many unannotated numerical scripts. It infers scalar and array types where possible and also recognizes optional comment hints such as:

```python
def matvec(n, a, x):
    # integer N, the matrix order.
    # real A(N,N), the matrix.
    # real X(N), the vector.
    return a @ x
```

This makes Python-to-Fortran more convenient for experimenting with existing unannotated code, but also less predictable. When inference is ambiguous, generated Fortran may fail to compile or may need better hints.

## When Pyccel Is a Better Fit

Pyccel is likely the better choice when:

- You can annotate the Python code explicitly.
- You want compiled extension modules that are imported back into Python.
- You want a mature compiler project with support for Fortran, C, and C++ back ends.
- You are optimizing selected kernels inside a larger Python application.

## When Python-to-Fortran Is a Better Fit

Python-to-Fortran is likely the better choice when:

- You want readable standalone Fortran source from a Python script.
- You want to test existing unannotated numerical Python code with minimal editing.
- You want a command that runs Python and translated Fortran and reports whether outputs match.
- You are working through a large corpus and want batch summaries of transpile, compile, and run failures.

## Practical Positioning

The projects are complementary rather than direct substitutes. Pyccel is a more mature Python-to-compiled-extension tool. Python-to-Fortran is narrower and more experimental, but it emphasizes standalone Fortran output, unannotated script translation, and automated comparison of Python and translated Fortran behavior.

