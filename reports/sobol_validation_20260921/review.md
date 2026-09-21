# Sobol deterministic validation, September 21, 2026

`probe.py` copies `i4_sobol`, `i4_bit_hi1`, and `i4_bit_lo0` unchanged from
`C:\python\public_domain\burkardt\sobol\sobol.py` (John Burkardt, MIT license).
The new deterministic driver avoids the original randomized helper tests.

## Confirmed and corrected transpiler defect

The initial probe failed compilation because its loop target `dim` was
declared/read as `xdim` but assigned as `dim`. `dimension` had the same issue.
The two-line `loop_dim.py` isolates the defect independently of Sobol.
Iterable-loop emission bypassed the name-alias mapping when assigning the
element and the `enumerate` index. Both assignments now use `_aliased_name`.
The corresponding type marking, including the `enumerate` prescan, also uses
the mapped names so reserved-name filtering does not discard their declarations.
Focused regressions cover `dim` and `dimension`, ordinary and enumerated
loops, and reading the final loop targets after the loop.

## Numerical/state checks

With the correction, the probe compiles and all 297 records match Python
exactly after numeric parsing:

- 44 Sobol calls, producing 236 coordinates.
- Sequential seeds 0 through 15; forward jumps to 31, 32, and 100;
  backward jumps, repeated seeds, zero and negative-seed resets.
- Dimension changes among 1, 3, 40, and 2, including entering each dimension
  at nonzero seed 5 before resetting to zero.
- 17 bit-helper inputs, including neighbors of powers of two and 2**31-1.

Independent checks verify the bit positions using Python integer operations,
the returned next seed, coordinate bounds, and the first coordinate using
the binary radical inverse of the Gray-coded seed. Other coordinates are
compared with the original Python routine, not an independent Sobol library.

Run `python check.py` to rebuild and validate. Logs and `analysis.json` retain
the outputs. The external Burkardt source is unchanged.

## Remaining limitation

Gfortran still warns about real-valued `j` loop variables and `maxcol` used
as array indices/bounds. The tested numerical values agree, but those legacy
extensions are a separate type-inference/Fortran-portability issue worth
investigating next. This validation does not certify strict-standard compilation,
every dimension/seed, or out-of-range seed handling. The original randomized
driver and a full pytest suite were not run for this investigation.
