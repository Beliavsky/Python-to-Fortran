# Jaccard distance: set arguments through local calls

Source: `C:\python\public_domain\burkardt\jaccard_distance\jaccard_distance.py`.
The original source was copied unchanged into a temporary build directory.

## Failure and fix

The driver constructs character sets and passes them through
`jaccard_distance(A, B)` to `jaccard_index(A, B)`. Element type and array
rank were retained, but the fact that the operands were sets was lost.
Consequently, `A & B` and `A | B` became Fortran logical operations on
character arrays, preventing compilation.

A flow-sensitive set-provenance analysis now propagates set information
through local arguments, keyword calls, aliases, intermediate expressions,
and single set-valued returns. It iterates over the local call graph to
handle forwarding independently of definition order. Ordinary arrays
remain nonsets, and ambiguous set/nonset operands receive a diagnostic
instead of being guessed. Set union/intersection retain their element kind
rather than acquiring a logical result kind. Procedures using the existing
non-PURE set helpers are no longer incorrectly declared PURE.

## Validation

`python reports\jaccard_validation_20260925\check.py` builds and executes
the original example and saves build/Python/Fortran logs in a printed
temporary directory. All five numerical results match Python within
1e-12:

| Case | Python and Fortran distance |
| --- | --- |
| Vowels / alligator letters | 0.7 |
| Same with duplicate input letters | 0.7 |
| Disjoint sets | 1.0 |
| Identical sets | 0.0 |
| Partially overlapping sets | 0.4285714285714286 |

Raw `--run-diff` still reports a difference: Python set representations
include braces and quotes and have unspecified ordering; the generated
program prints character arrays. Version banners and timestamps also
differ. The validation deliberately compares the five distances, not these
presentation differences.

Focused regression tests cover integer and character arguments through
two levels of calls, set-valued returns, union/intersection/difference/
symmetric difference, disjoint and identical operands, ordinary Boolean
array operations, default-argument provenance, rebinding, and ambiguous
call/branch diagnostics. Results: 6 set-focused tests passed in 223.11 s;
42 additional provenance, string, logical-sum, and purity tests passed in
271.75 s (48 total). Full pytest is left to the user.

## Boundaries and follow-up

This is not a general Python-set implementation: it uses the existing
integer/character set helpers. It does not add mutable-set methods,
higher-order dispatch, or arbitrary heterogeneous element types. Character
set helpers still use fixed-width Fortran comparisons; strings differing
only by significant trailing spaces need separate work. No `len_trim`
change is made here. Both-empty Jaccard inputs still have the source's
undefined zero-denominator case.

An adjacent probe, `np.count_nonzero(a & b)` with Boolean array arguments,
produces `count((a .and. b) /= 0)` and fails because it compares logical
values with integer zero. That separate issue is not fixed by this change.
