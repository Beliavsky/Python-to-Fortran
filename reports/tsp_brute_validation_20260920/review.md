# tsp_brute runtime validation

The original, unmodified Burkardt `tsp_brute.py` compiles and runs with the current
transpiler and runtime checks enabled. No new transpiler fix was needed.

The synthetic symmetric five-city fixture in `valid/five.txt` has zero diagonal
and deliberately varied integer edge weights. Independent enumeration using
`itertools.permutations` gives 120 tours, minimum cost 19, average cost 27.5, and
maximum cost 36. Both Python and generated Fortran match these statistics.
Each printed optimal itinerary visits all five cities once, closes correctly,
uses the input edge costs, and totals the independently established minimum.

With no `five.txt`, both current implementations fail rather than reporting a
result. The Fortran diagnostic identifies the missing input file. The existing
loadtxt error-handling fix covers this case.

The saved September 20 audit executable was also rerun unchanged: it succeeds
with the valid fixture (exit 0) but reproduces SIGFPE when the file is absent
(exit 3). This confirms that the old runtime failure depended on missing input,
not the tour calculation on this valid fixture.

`check.py` reproduces the current build, Python/Fortran runs, independent
statistics and itinerary checks, and missing-file checks. `build.log`,
`python.log`, `fortran.log`, and the missing-file logs preserve the evidence.
`historical_valid.log` and `historical_missing.log` record the separate reruns
of the saved executable. This is a bounded validation, not a proof for all sizes
or invalid inputs. No full pytest run is needed for this report-only work.
