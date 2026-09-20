# mesh_vtoe runtime validation

The original, unmodified Burkardt `mesh_vtoe.py` compiles and runs with current
xp2f and runtime checks enabled. No new transpiler fix was required.

Two synthetic, zero-based fixtures exercise both original drivers:

- `valid/boxy_elements.txt`: four triangular elements, seven vertex slots,
  twelve incidences, and unused vertex 3.
- `valid/pool_elements.txt`: four quadrilateral elements, eleven vertex slots,
  sixteen incidences, and unused vertices 3 and 7.

An independent calculation builds each vertex's list of containing elements
directly from the input rows, then constructs cumulative pointers. Every printed
pointer and every adjacency list from both Python and Fortran matches exactly,
including empty lists for unused vertices. These fixtures are synthetic, not
Burkardt's original datasets. One-based numbering and other input shapes were
not validated by this check.

With missing input, current Python and Fortran both fail and identify
`boxy_elements.txt`. The Fortran diagnostic is now the explicit loadtxt open
error, rather than the old invalid-index failure.

The saved audit executable also succeeds on the valid fixtures (exit 0), while
missing input reproduces its negative-index runtime error (exit 2). The old
failure is therefore covered by the existing missing-file handling fix for the
tested scenario; it does not establish a remaining connectivity translation bug.

`check.py` reproduces the build, independent validation, missing-input tests and,
when available, historical-executable reruns. Build and run logs are retained in
this directory. Only validation files were added; no full pytest rerun is needed.
