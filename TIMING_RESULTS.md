# Timing Results

`xp2f.py` was timed on a set of Burkardt numerical Python programs that fully passed the pipeline:

1. Run the original Python program.
2. Transpile it to Fortran.
3. Compile the generated Fortran.
4. Run the generated Fortran successfully.

The timings below exclude known non-comparable timing cases such as programs where the generated Fortran omits non-numerical side effects. Times are in seconds.

## Summary

```text
Full pipeline pass rows:
            python  transpile    compile  fortran_run      total    elapsed  fortran/python
mean         7.851      3.971      0.865        0.999     13.686   2307.158           0.745
median       0.590      0.878      0.656        0.463      2.781   2021.142           0.766
geomean      0.814      1.175      0.752        0.442      4.078   1478.614           0.542
std         67.964     13.145      0.626        7.937     69.460   1586.891           0.903
min          0.490      0.327      0.397        0.080      1.346      4.154           0.001
max       1014.946    104.114      5.505      121.577   1017.258   5418.071          13.549
total     1829.209    925.172    201.654      232.777   3188.821 537567.828           0.127
```

The main runtime comparison is `fortran/python`, which is the generated Fortran run time divided by the original Python run time.

- The median ratio is `0.766`, so the typical successful Fortran run was about `1 / 0.766 = 1.3x` faster than Python.
- The geometric mean ratio is `0.542`, corresponding to about `1.8x` faster on a multiplicative-average basis.
- The total ratio is `0.127`, so across all fully passing programs in this timing set, generated Fortran runtime was about `7.9x` faster than Python runtime.

The total ratio is much lower than the median because several Python-loop-heavy programs dominate aggregate Python time.

## Largest Speedups

```text
Times are in seconds.
Smallest Fortran/Python time ratios (10 rows):
                    code     python  fortran_run fortran/python
         test_nearest.py   1014.946        1.312         0.0010
                  mxm.py    118.389        0.563         0.0050
               quad2d.py    114.284        0.767         0.0070
   reactor_simulation.py     51.175        0.642         0.0130
    wedge_monte_carlo.py     50.264        0.716         0.0140
      wedge_integrals.py     48.891        0.736         0.0150
        satisfy_brute.py     48.092        0.799         0.0170
       knapsack_brute.py    123.925        2.333         0.0190
            rng_cliff.py     25.564        0.674         0.0260
monty_hall_simulation.py     48.799        1.499         0.0310
```

These are real numerical workloads where the generated Fortran appears to do comparable work to the Python source. The large speedups occur mostly in programs dominated by scalar Python loops, such as nearest-neighbor search, brute-force enumeration, matrix multiplication loop nests, quadrature loops, and Monte Carlo simulation loops.

For such cases, the translated Fortran removes Python interpreter overhead from deeply nested loops. That is the clearest performance use case for the transpiler.

## Interpretation

The timing results should be read in two different ways:

- `fortran_run` vs `python` measures runtime after the Fortran has already been generated and compiled.
- `total` includes transpilation and compilation, so it is the relevant number for a one-off run.

For one-off executions, transpilation and compilation overhead usually dominate. The median full-pipeline total time is `2.781` seconds, compared with a median Python runtime of `0.590` seconds.

For repeated runs, long computations, or generated Fortran reused downstream, the runtime comparison is more relevant. In that setting, the generated Fortran is often faster, and sometimes dramatically faster.

## Caveats

This project is an experimental transpiler, not a general Python compiler. Timing comparisons are meaningful only when the generated Fortran performs comparable work to the original Python program.

Some programs can compile and run but still be poor timing comparisons, for example if the Python code calls external plotting, movie generation, file-generation, or other side-effect-heavy libraries that are not represented in Fortran. Such cases should be excluded from timing summaries.

Correctness and comparability should be checked with output comparison, code inspection, and targeted tests before drawing conclusions from very large speedups.
