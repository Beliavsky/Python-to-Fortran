# fem_to_xml runtime validation and str_split bounds fix

The historical failure was a missing `cheby9_nodes.txt`. Supplying valid inputs
exposed a separate runtime-helper bug: str_split read s(3:3) for a two-character
line (`-1`). Its whitespace scanners combined a bound test and substring access
with `.and.`, but Fortran does not guarantee short-circuit evaluation.

Both scanners now check the loop bound before accessing the character. The
focused pytest `test_xp2f_whitespace_split_checks_bounds_before_character_access`
passes with tokens at the end of the string, leading/trailing spaces, and tabs.
No source-program or xp2f.py changes were made.

After the fix, the complete original fem_to_xml driver runs under runtime checks.
Synthetic fixtures cover:

- 1D: five nodes, four intervals, one-based input connectivity.
- 2D: four nodes, two triangles, zero-based input connectivity.
- 3D: five nodes, two tetrahedra, one-based input connectivity.

These are not Burkardt's original meshes; the filenames match the original
driver's expected inputs. Python and Fortran run in separate directories.
The checker parses all six output XML files and verifies dimensions, cell types,
counts, vertex/cell indices, coordinates and every connectivity entry against
the inputs, including one-to-zero-based conversion. All checks pass. Missing
input produces a nonzero exit and a diagnostic naming cheby9_nodes.txt in both
implementations; this source uses ordinary file reads, not np.loadtxt.

## Python output caveat

The original source writes repr() of NumPy scalars into XML attributes. In the
tested environment, Python emits 50 attributes containing wrappers such as
`np.float64(-1.0)` and `np.int32(0)`. These are syntactically legal XML attribute
strings but are not plain numbers suitable for the intended mesh format.
The checker explicitly unwraps these representations to validate their values
and reports the wrapper count; it does not claim raw output equivalence or
successful ingestion by a DOLFIN reader. Fortran emits plain numeric attributes
and has zero such wrappers. Neither the source's repr usage nor general NumPy
repr fidelity was changed by this bounds fix.

`check.py`, the fixtures, and the build/run logs reproduce the successful
post-fix validation. A full pytest checkpoint is recommended because the shared
string helper changed; only the focused regression was run here.
